"""Persistencia point-in-time de `bot_signals` y servicio de bots (T57)."""

import threading

import duckdb
import pytest

from eim.bots.adapter import empty_signal, version_of
from eim.bots.card import card_of
from eim.bots.hb_directional import BollingerV1, HummingbotDirectionalAdapter
from eim.bots.service import BotService, default_service
from eim.core import NOT_SAVED, VERSION_CHANGED
from eim.data.bots.store import BotSignalStore
from tests.bots.helpers import candles, snapshot

NOW = 10**13  # reloj de guardado muy posterior a las velas del fixture


@pytest.fixture
def store():
    return BotSignalStore(duckdb.connect(":memory:"), threading.Lock())


def one_signal(n=300, strategy="bollinger_v1"):
    sigs = HummingbotDirectionalAdapter().signals(snapshot(n))
    return next(s for s in sigs if s.strategy == strategy)


def test_append_only_first_write_wins(store):
    s = one_signal()
    assert store.append(s, NOW) is True
    changed = s.model_copy(update={"stance": -1.0})
    assert store.append(changed, NOW + 1) is False        # misma clave: no se reescribe
    (back,) = store.query("ETHUSDT", "1h")
    assert back == s and back.stance == s.stance


def test_future_asof_is_rejected(store):
    s = one_signal()
    with pytest.raises(ValueError, match="posterior"):
        store.append(s, s.asof - 1)
    assert store.query("ETHUSDT", "1h") == []


def test_every_row_carries_asof_version_and_status(store):
    for n in (250, 300):
        store.append(one_signal(n), NOW)
    rows = store._con.execute(
        "SELECT asof_ms, version, status, created_ms FROM bot_signals ORDER BY asof_ms").fetchall()
    assert len(rows) == 2 and rows[0][0] < rows[1][0]
    assert all(len(r[1]) == 53 and r[2] == "ok" and r[3] == NOW for r in rows)


def test_new_sha_or_params_creates_a_new_version_row_not_an_overwrite(store):
    s = one_signal()
    store.append(s, NOW)
    tuned = HummingbotDirectionalAdapter(strategies={"bollinger_v1": BollingerV1(bb_std=2.5)})
    t = next(x for x in tuned.signals(snapshot(300)) if x.strategy == "bollinger_v1")
    assert t.version != s.version and t.asof == s.asof
    assert store.append(t, NOW) is True
    assert {x.version for x in store.query("ETHUSDT", "1h")} == {s.version, t.version}


def test_query_filters_and_orders(store):
    for n in (250, 260, 270):
        store.append(one_signal(n), NOW)
    got = store.query("ETHUSDT", "1h")
    assert [g.asof for g in got] == sorted(g.asof for g in got) and len(got) == 3
    assert len(store.query("ETHUSDT", "1h", start=got[1].asof)) == 2
    assert len(store.query("ETHUSDT", "1h", end=got[0].asof)) == 1
    assert store.query("BTCUSDT", "1h") == [] and store.query("ETHUSDT", "4h") == []
    assert len(store.query("ETHUSDT", "1h", bot_id="hummingbot-directional")) == 3
    assert len(store.query("ETHUSDT", "1h", limit=1)) == 1


# --- servicio -------------------------------------------------------------------------------
def test_service_produces_persists_and_attaches(store):
    svc = BotService([HummingbotDirectionalAdapter()], store, clock=lambda: NOW)
    snap = svc.attach(snapshot(300))
    assert {s.strategy for s in snap.bot_signals} == {"bollinger_v1", "macd_bb_v1"}
    assert len(store.query("ETHUSDT", "1h")) == 2
    svc.attach(snapshot(300))                                  # repetir no duplica
    assert len(store.query("ETHUSDT", "1h")) == 2


def test_service_marks_a_version_change_against_the_last_stored(store):
    svc = BotService([HummingbotDirectionalAdapter()], store, clock=lambda: NOW)
    svc.attach(snapshot(300))
    moved = card_of("hummingbot-directional").model_copy(update={"commit_sha": "7" * 40})
    svc2 = BotService([HummingbotDirectionalAdapter(moved)], store, clock=lambda: NOW)
    sigs = svc2.produce(snapshot(310))
    assert sigs and all(any(n.startswith(VERSION_CHANGED) for n in s.data_quality.notes)
                        for s in sigs)
    again = svc2.produce(snapshot(320))                        # misma versión que la última
    assert not any(n.startswith(VERSION_CHANGED) for s in again for n in s.data_quality.notes)


def test_a_failing_adapter_becomes_a_degraded_signal(store):
    class Boom:
        bot_id = "hummingbot-directional"
        card = card_of("hummingbot-directional")

        def signals(self, snapshot):
            raise RuntimeError("explotó")

    svc = BotService([Boom(), HummingbotDirectionalAdapter()], store, clock=lambda: NOW)
    sigs = svc.produce(snapshot(300))
    bad = [s for s in sigs if s.status == "degraded"]
    assert len(bad) == 1 and "explotó" in bad[0].evidence[0] and bad[0].stance == 0
    assert len(sigs) == 3                                       # el otro adaptador siguió


def test_only_usable_cards_take_part(store):
    pending = card_of("hummingbot-directional").model_copy(
        update={"approval": card_of("hummingbot-directional").approval.model_copy(
            update={"state": "pendiente"})})
    svc = BotService([HummingbotDirectionalAdapter(pending)], store, clock=lambda: NOW)
    assert svc.produce(snapshot(300)) == []
    assert svc.attach(snapshot(300)).bot_signals is None


def test_service_never_raises_when_the_store_fails():
    class BrokenStore:
        def last_version(self, *a):
            raise RuntimeError("disco")

        def append(self, *a):
            raise RuntimeError("disco")

    svc = BotService([HummingbotDirectionalAdapter()], BrokenStore())
    assert len(svc.produce(snapshot(300))) == 2


def test_default_service_has_mode_a_and_adds_b_only_when_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("EIM_BOT_FREQTRADE_PY", raising=False)
    assert [a.bot_id for a in default_service(tmp_path, None).adapters] == [
        "hummingbot-directional", "jesse-example-strategies", "trendrider-strategy"]
    (tmp_path / "bots" / "freqtrade-strategies").mkdir(parents=True)
    monkeypatch.setenv("EIM_BOT_FREQTRADE_PY", "/py")
    monkeypatch.setenv("EIM_BOT_FREQTRADE_ENGINE", "2026.9")
    assert [a.bot_id for a in default_service(tmp_path, None).adapters] == [
        "hummingbot-directional", "jesse-example-strategies", "trendrider-strategy",
        "freqtrade-strategies"]


def test_empty_signal_helper_and_version_of():
    snap = snapshot(300)
    card = card_of("hummingbot-directional")
    s = empty_signal(card, "x", version_of(card.commit_sha, {}), snap, "degraded", "motivo")
    assert s.status == "degraded" and s.stance == 0 and s.evidence == ["motivo"]
    assert candles()[0].t < snap.asof


def test_unsaved_signal_is_still_returned_but_marked(store):
    class Full:
        def last_version(self, *a):
            return None

        def append(self, *a):
            raise RuntimeError("disco lleno")

    sigs = BotService([HummingbotDirectionalAdapter()], Full()).produce(snapshot(300))
    assert len(sigs) == 2
    assert all(any(n.startswith(NOT_SAVED) for n in s.data_quality.notes) for s in sigs)


def test_snapshot_with_an_unclosed_candle_produces_no_signals():
    snap = snapshot(300)
    early = snap.model_copy(update={"asof": snap.candles[-1].t + 1})   # la última vela aún abierta
    assert BotService([HummingbotDirectionalAdapter()]).attach(early).bot_signals is None


def test_split_version():
    from eim.bots.adapter import split_version
    assert split_version("a" * 40 + "+0123456789ab") == ("a" * 40, "0123456789ab")


def test_append_many_batches_with_the_same_contract(store):
    base = one_signal()
    sigs = [base.model_copy(update={"asof": base.asof + i * 3_600_000}) for i in range(1200)]
    assert store.append_many(sigs, NOW) == 1200
    changed = [s.model_copy(update={"stance": -1.0}) for s in sigs[:10]]
    new = base.model_copy(update={"asof": sigs[-1].asof + 1})
    assert store.append_many([*changed, new], NOW + 5) == 1   # solo la nueva; nada se reescribe
    assert store.query("ETHUSDT", "1h", limit=5000)[0].stance == sigs[0].stance
    created = {r[0] for r in store._con.execute("SELECT created_ms FROM bot_signals").fetchall()}
    assert created == {NOW, NOW + 5}                         # created_ms original de cada fila
    with pytest.raises(ValueError, match="posterior"):
        store.append_many([sigs[0].model_copy(update={"asof": NOW + 1})], NOW)
    assert store._con.execute("SELECT count(*) FROM bot_signals").fetchone()[0] == 1201


def test_query_lean_keeps_what_scoring_uses(store):
    sigs = HummingbotDirectionalAdapter().signals(snapshot(300))
    store.append_many(sigs, NOW)
    full = {(s.strategy): (s, c) for s, c in store.query_all("ETHUSDT", "1h")}
    for lean, c in store.query_lean("ETHUSDT", "1h"):
        ref, c0 = full[lean.strategy]
        assert (lean.bot_id, lean.version, lean.asof, lean.stance, lean.confidence,
                lean.horizon_bars, lean.status, lean.timeframe, c) == \
               (ref.bot_id, ref.version, ref.asof, ref.stance, ref.confidence,
                ref.horizon_bars, ref.status, ref.timeframe, c0)
        assert not hasattr(lean, "raw")


def test_service_gives_history_only_to_adapters_that_ask_for_it():
    from eim.core import MarketSnapshot

    big = candles()
    seen: dict[str, int] = {}

    class Greedy:
        card = card_of("hummingbot-directional")
        history_bars = 900
        timeframes = ("1h",)

        def signals(self, snap):
            seen["greedy"] = len(snap.candles)
            return []

    class Modest(Greedy):
        history_bars = 0

        def signals(self, snap):
            seen["modest"] = len(snap.candles)
            return []

    calls = []

    def loader(sym, tf, last_t, n):
        calls.append((sym, tf, last_t, n))
        return [c for c in big if c.t <= last_t][-n:]

    base = snapshot(cs=candles()[400:])
    svc = BotService([Greedy(), Modest()], None, history=loader)
    svc.produce(base)
    assert seen == {"greedy": 900, "modest": 600} and len(calls) == 1
    # si las velas del almacén no terminan en la del snapshot, no se toca
    seen.clear()
    BotService([Greedy()], None, history=lambda *a: big[:30]).produce(base)
    assert seen == {"greedy": 600}
    assert isinstance(base, MarketSnapshot) and len(base.candles) == 600
