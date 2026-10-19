"""Relleno histórico de `bot_signals` (T58): punto en el tiempo, una fila por cierre."""

import threading

import duckdb

from eim.bots.backfill import HISTORY_BARS, backfill_pure, snapshots
from eim.bots.hb_directional import HummingbotDirectionalAdapter
from eim.bots.service import BotService
from eim.data.bots.store import BotSignalStore
from tests.bots.helpers import STEP, candles


def test_snapshots_hold_only_closed_candles_up_to_each_asof():
    cs = candles()
    out = list(snapshots(cs, "ETHUSDT", "1h", cs[500].t + STEP))
    assert out[0].asof == cs[500].t + STEP and len(out) == len(cs) - 500
    for s in out[::97]:
        assert s.candles[-1].t + STEP == s.asof and len(s.candles) <= HISTORY_BARS


def test_backfill_stores_one_row_per_close_and_is_idempotent():
    cs = candles()
    store = BotSignalStore(duckdb.connect(":memory:"), threading.Lock())
    service = BotService([HummingbotDirectionalAdapter()], store, clock=lambda: 10**15)
    from_asof = cs[-30].t + STEP
    n = backfill_pure(service, cs, "ETHUSDT", "1h", from_asof)
    assert n == 30 * 2                                   # 2 estrategias × 30 cierres
    rows = store.query("ETHUSDT", "1h", limit=1000)
    assert len(rows) == n and all(r.asof >= from_asof for r in rows)
    backfill_pure(service, cs, "ETHUSDT", "1h", from_asof)
    assert len(store.query("ETHUSDT", "1h", limit=1000)) == n    # solo se añade
