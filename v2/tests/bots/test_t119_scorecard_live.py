"""T119: la puntuación del escuadrón dice de cuándo es, si su recálculo falló y qué leyó de cada
marco (incluido el 5m, que el bróker mantiene al día); ningún bot aparece como vivo si no opina.
Sin red: mercado y posturas sintéticas."""

from __future__ import annotations

import threading
from types import SimpleNamespace

import duckdb
import pytest
from fastapi import FastAPI

from eim.api.bots import build_bots_router, squad_view
from eim.bots import scorer as scorer_mod
from eim.bots.card import default_cards
from eim.bots.hb_directional import HummingbotDirectionalAdapter
from eim.bots.jesse_examples import JesseExamplesAdapter
from eim.bots.scorer import FOUR_H, STALE_MS, BotScorer, freshness
from eim.bots.service import BotService
from eim.bots.trendrider import TrendRiderAdapter
from eim.core import Candle
from eim.data.aggregate import aggregate
from eim.data.bots.scorestore import ScoreStore
from eim.data.bots.store import BotSignalStore
from eim.data.paper_store import PaperStore
from eim.data.store import Store
from eim.paper.service import DeskService
from tests.bots.score_helpers import CRIT, SYMBOL, T0, H, Market, card, oracle_rows, signal
from tests.local_client import LocalClient

BOT, NFI = "hummingbot-directional", "nostalgia-for-infinity"
M = 60_000


def _changes(rows):
    """Solo los cambios de lado (lo que abre operaciones sombra), como en `test_scorer`."""
    prev, out = 0.0, []
    for s, created in rows:
        if s.stance != prev:
            out.append((s, max(created, s.asof)))
        prev = s.stance
    return out


def _scorer(tmp_path, m: Market, extra_cards: dict | None = None):
    store = Store(tmp_path)
    store.upsert_candles(SYMBOL, "1h", m.c1h, "sintético")
    store.upsert_candles(SYMBOL, "15m", m.c15, "sintético")
    con, lock = duckdb.connect(":memory:"), threading.Lock()
    sigs = BotSignalStore(con, lock)
    for s, created in _changes(oracle_rows(m)):
        sigs.append(s, created)
    sc = BotScorer(sigs, ScoreStore(con, lock), store, PaperStore(":memory:"), None,
                   {BOT: card(), **(extra_cards or {})}, CRIT)
    return sc, sigs, store


@pytest.fixture
def api(tmp_path):
    m = Market(days=20)
    sc, sigs, _ = _scorer(tmp_path, m)
    service = BotService([HummingbotDirectionalAdapter(), JesseExamplesAdapter(),
                          TrendRiderAdapter()], sigs)
    app = FastAPI()
    app.include_router(build_bots_router(sigs, service, sc))
    with LocalClient(app) as client:
        yield sc, client, m


def test_freshness_states():
    shown = {"bots": [{}], "asof": 10 * FOUR_H, "computed": 10 * FOUR_H + 60_000}
    now = 10 * FOUR_H + H
    assert freshness(shown, now)["state"] == "vigente"
    f = freshness(shown, now, last_attempt=now, error="OutOfMemoryException: sin memoria")
    assert f["state"] == "fallida" and "sin memoria" in f["reason"] and f["asof"] == shown["asof"]
    old = freshness(shown, shown["asof"] + STALE_MS + 1)
    assert old["state"] == "vieja" and "8 h" in old["reason"]
    assert freshness(None, now)["state"] == "sin_medicion"
    empty = freshness({"bots": [], "error": "sin posturas guardadas de bots"}, now)
    assert empty["state"] == "sin_medicion" and empty["reason"].startswith("sin posturas")


def test_scorecard_route_says_when_and_reports_a_failed_recalculation(api, monkeypatch):
    sc, client, m = api
    now = m.end + H                     # una hora después de la última vela
    monkeypatch.setattr(scorer_mod, "now_ms", lambda: now)
    sc.maybe_run()
    body = client.get("/v2/bots/scorecard", params={"symbol": SYMBOL}).json()
    f = body["freshness"]
    assert body["error"] == "" and f["state"] == "vigente"
    assert f["asof"] == body["asof"] == m.end and f["computed"] == now and f["last_ok"] == now

    def oom(*a, **k):
        raise MemoryError("Out of Memory Error: failed to allocate block")

    later = now + FOUR_H                # el siguiente cierre de 4 h el recálculo cae
    monkeypatch.setattr(sc, "compute", oom)
    monkeypatch.setattr(scorer_mod, "now_ms", lambda: later)
    sc.maybe_run()
    body2 = client.get("/v2/bots/scorecard", params={"symbol": SYMBOL}).json()
    f2 = body2["freshness"]
    assert f2["state"] == "fallida" and "Out of Memory" in f2["reason"]
    assert f2["last_attempt"] == later and f2["last_ok"] == now      # la anterior, dicho
    assert body2["asof"] == body["asof"] and "Out of Memory" in body2["error"]
    sq = client.get("/v2/bots", params={"symbol": SYMBOL, "tf": "1h"}).json()
    assert sq["scorecard"]["state"] == "fallida" and sq["scored_asof"] == body["asof"]

    monkeypatch.undo()                  # vuelve a ir bien: se limpia el fallo
    monkeypatch.setattr(scorer_mod, "now_ms", lambda: later + FOUR_H)
    sc.maybe_run()
    f3 = client.get("/v2/bots/scorecard", params={"symbol": SYMBOL}).json()["freshness"]
    assert f3["last_ok"] == later + FOUR_H        # el fallo se limpia, pero los datos no avanzan:
    assert f3["state"] == "vieja"                 # 9 h sin corte nuevo no pasa por vigente


def test_squad_route_lists_bots_out_of_the_cycle_and_none_looks_live(api):
    _, client, _ = api
    body = client.get("/v2/bots", params={"symbol": SYMBOL, "tf": "1h"}).json()
    off = {b["bot_id"]: b["reason"] for b in body["out_of_cycle"]}
    assert set(off) == {NFI, "freqtrade-strategies", "passivbot"}   # sin entorno de modo B
    assert off[NFI].startswith("solo histórico") and "sin entorno" in off["freqtrade-strategies"]
    # las posturas sintéticas son de 2023: ningún bot aparece como vivo ni cuenta en el apoyo
    assert body["bots"] and not any(b["live"] for b in body["bots"])
    assert body["support"]["total"] == 0 and body["disagreement"] is None
    assert "no está opinando" in body["bots"][0]["reasons"][0]
    assert body["scorecard"]["state"] in ("vieja", "sin_medicion")


def test_squad_view_counts_only_bots_that_are_opining():
    now = T0 + 100 * H
    rows = [signal(now - H, 1.0, strategy="vivo"), signal(now - 10 * H, -1.0, strategy="parado")]
    v = squad_view(rows, default_cards(), None, None, {}, now, [])
    assert {b["strategy"]: b["live"] for b in v["bots"]} == {"vivo": True, "parado": False}
    assert v["support"]["total"] == 1 and v["support"]["up"] == 1 and v["out_of_cycle"] == []
    legacy = squad_view(rows, default_cards(), None, None, {})       # sin reloj: como antes
    assert all(b["live"] for b in legacy["bots"]) and legacy["support"]["total"] == 2


def _five(c15: list[Candle]) -> list[Candle]:
    out = []
    for c in c15:
        for j in range(3):
            o = c.o + (c.c - c.o) * j / 3
            out.append(Candle(t=c.t + j * 300_000, o=o, h=c.h, l=c.l, c=o + (c.c - c.o) / 3,
                              v=3.0))
    return out


def test_scorecard_reads_the_5m_frame_and_a_lagging_5m_is_not_shown_as_current(tmp_path):
    m = Market(days=14)
    sc, sigs, store = _scorer(tmp_path, m, {NFI: default_cards()[NFI]})
    five = [(s.model_copy(update={"bot_id": NFI, "strategy": "X7", "timeframe": "5m"}), cr)
            for s, cr in _changes(oracle_rows(m))]
    for s, created in five:
        sigs.append(s, created)
    lag = 2 * 86_400_000                 # 5m sin velas nuevas desde hace dos días
    c5 = _five(m.c15)
    store.upsert_candles(SYMBOL, "5m", [c for c in c5 if c.t < m.end - lag], "agregado")
    now = m.end + H
    out = sc.compute(SYMBOL, now)
    fr = {f["timeframe"]: f for f in out["frames"]}
    assert fr["5m"]["path_tf"] == "5m" and fr["5m"]["signals"] == len(five)
    assert fr["5m"]["candles_to"] == m.end - lag and fr["5m"]["sets_asof"]
    assert fr["1h"]["path_tf"] == "15m" and not fr["1h"]["sets_asof"]
    assert out["asof"] == m.end - lag    # el 5m atrasado fija el corte de toda la medición…
    assert sc.freshness(sc.latest(SYMBOL), now)["state"] == "vieja"    # …y no pasa por actual
    store.upsert_candles(SYMBOL, "5m", c5, "agregado")                # 5m al día
    out2 = sc.compute(SYMBOL, now + H)
    assert out2["asof"] == m.end
    assert sc.freshness(sc.latest(SYMBOL), now + H)["state"] == "vigente"


def test_regimes_reads_the_same_as_parsing_every_context():
    """La puntuación lee (asof, régimen) sin parsear el contexto entero (pico de memoria)."""
    ps = PaperStore(":memory:")
    for k, reg in enumerate(["range", None, "trend_up", "volatile"]):
        ctx = {"t": T0 + k * H, "signals": [{"id": i, "x": "y" * 50} for i in range(20)]}
        if reg:
            ctx["regime"] = reg
        ps.save(SYMBOL, "1h", ctx, "vivo", 1)
    ps.save(SYMBOL, "15m", {"t": T0, "regime": "otro"}, "vivo", 1)
    full = [(int(c["t"]), c.get("regime")) for c in ps.load(SYMBOL, "1h")]
    assert ps.regimes(SYMBOL, "1h") == full and full[1] == (T0 + H, None)


def _minute(i: int) -> Candle:
    p = 100 + (i % 97) * 0.1
    return Candle(t=i * M, o=p, h=p + 1, l=p - 1, c=p + 0.5, v=1.0, taker_buy_v=0.4, trades=2)


def test_5m_stays_complete_over_days_with_restart_and_outage(tmp_path):
    """Dos días seguidos: cada ciclo del bróker trae el 1m nuevo y mantiene el 5m
    (`DeskService._keep_5m`); un reinicio (almacén nuevo sobre la misma carpeta) y 30 h
    de caída no dejan huecos, y el resultado es el de agregar todo de una vez."""
    days = 2
    exchange = [_minute(i) for i in range(days * 1440)]
    st = Store(tmp_path)
    st.upsert_candles(SYMBOL, "1m", exchange[:60], "t")
    aggregate(st, SYMBOL)                # el 5m se crea una vez (`eim.bots.backfill`)
    synced = 60

    def cycle(store: Store, upto: int) -> None:
        nonlocal synced
        store.upsert_candles(SYMBOL, "1m", exchange[synced:upto], "t")
        synced = upto
        DeskService._keep_5m(SimpleNamespace(store=store), SYMBOL)

    for h in (2, 6, 10):                 # día 1: ciclos con el último grupo de 5 min a medias
        cycle(st, h * 60 + 3)
    st = Store(tmp_path)                 # reinicio de la API…
    cycle(st, (10 + 30) * 60 + 1)        # …tras 30 h sin ciclos (bróker caído)
    cycle(st, 44 * 60 + 7)
    cycle(st, days * 1440)
    got = st.read_candles(SYMBOL, "5m")
    assert [c.t for c in got] == list(range(0, days * 1440 * M, 5 * M))     # sin huecos
    ref = Store(tmp_path / "ref")
    ref.upsert_candles(SYMBOL, "1m", exchange, "t")
    aggregate(ref, SYMBOL)
    assert got == ref.read_candles(SYMBOL, "5m")
