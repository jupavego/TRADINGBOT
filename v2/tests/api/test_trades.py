"""Libro simulado, bitácora y reproducción (T15): planes persistidos → operaciones."""

from __future__ import annotations

import pytest

from eim.api.config import Settings
from eim.api.main import create_app
from eim.core import AgentReport, Candle, Overlay
from eim.data.store import Store
from eim.data.timeframes import tf_ms
from eim.execution.sim_ledger import build_trades, trade_at
from tests.local_client import LocalClient

STEP = tf_ms("1h")
T0 = 1_700_000_000_000 // STEP * STEP


def _candles(n: int) -> list[Candle]:
    out = []
    for i in range(n):
        p = 2000 + i * 0.5 + (i % 7)
        out.append(Candle(t=T0 + i * STEP, o=p, h=p + 5, l=p - 5, c=p + 1, v=100 + i))
    return out


def _plan_report(i: int, side: str, entry: float, sl: float, tp: list[float],
                 status: str = "VIGENTE", asof_i: int | None = None,
                 t_to: int | None = None) -> AgentReport:
    t = T0 + i * STEP
    geom = {"side": side, "entry": entry, "sl": sl, "tp": tp, "rr": 1.0, "mode": "ANALISIS",
            "status": status}
    ov = Overlay(id=f"plan:{t}", agent_id="plan", kind="trade_plan", t_from=t, t_to=t_to,
                 geometry=geom, label="Plan", confidence=0.6, evidence=[f"plan {side} {i}"])
    return AgentReport(
        agent_id="plan", version="1.0.0", asof=T0 + (asof_i or i + 1) * STEP, bias=0.5,
        confidence=0.6, horizon_bars=10, evidence=[f"plan {side} {i}"],
        metrics={"plan": geom}, overlays=[ov])


LONG = _plan_report(100, "long", 2053.0, 2040.0, [2065.0, 2080.0])
SHORT = _plan_report(150, "short", 2079.0, 2090.0, [2000.0])


def test_trades_coherent_with_plans():
    ts = build_trades("ETHUSDT", "1h", [LONG, SHORT], _candles(300))
    assert [t.side for t in ts] == [1, -1]
    long_t, short_t = ts
    assert long_t.status in ("TP1", "TP2") and long_t.r is not None and long_t.r > 0
    assert short_t.status == "SL" and short_t.exit == 2090.0
    assert -1.2 < short_t.r < -1.0          # −1R más comisiones y funding
    assert all(t.mode == "SIMULADO" for t in ts)
    assert long_t.exit_t > long_t.entry_t


def test_sl_and_tp_same_candle_is_conservative():
    cs = _candles(300)
    cs[110] = Candle(t=cs[110].t, o=2056, h=2100, l=2030, c=2060, v=1)
    long_t = build_trades("ETHUSDT", "1h", [LONG], cs)[0]
    assert long_t.status == "SL" and long_t.exit == 2040.0


def test_invalidated_plan_exits_at_close():
    cs = _candles(300)
    t_to = cs[103].t
    rep = _plan_report(100, "long", 2053.0, 2040.0, [2400.0], "INVALIDADO",
                       asof_i=104, t_to=t_to)
    t = build_trades("ETHUSDT", "1h", [rep], cs)[0]
    assert t.status == "INVALIDADO" and t.exit == cs[103].c and t.exit_t == t_to


def test_open_trade_and_trade_at():
    open_t = build_trades("ETHUSDT", "1h", [LONG], _candles(105))[0]
    assert open_t.status == "ABIERTA" and open_t.r is None
    full = build_trades("ETHUSDT", "1h", [LONG], _candles(300))[0]
    assert trade_at(full, T0 + 100 * STEP) is None
    assert trade_at(full, full.exit_t).status == "ABIERTA"
    assert trade_at(full, full.exit_t + STEP) == full


@pytest.fixture
def client(tmp_path):
    Store(tmp_path).upsert_candles("ETHUSDT", "1h", _candles(300), "test")
    cfg = Settings(data_dir=tmp_path, heartbeat_s=0.2, snapshot_bars=300)

    class Idle:
        name = "idle"

        async def stream(self, symbol, timeframe):
            import asyncio
            yield {"type": "status", "state": "up", "detail": ""}
            await asyncio.sleep(3600)

    with LocalClient(create_app(cfg, source=Idle())) as c:
        c.app.state.reports.save("ETHUSDT", "1h", [LONG])
        c.app.state.reports.save("ETHUSDT", "1h", [SHORT])
        yield c


def test_api_trades_and_journal(client):
    p = {"symbol": "ETHUSDT", "tf": "1h"}
    body = client.get("/v2/trades", params=p).json()
    assert body["mode"] == "SIMULADO" and len(body["trades"]) == 2
    j = client.get("/v2/journal", params=p).json()
    assert len(j["decisions"]) == 2 and len(j["trades"]) == 2
    assert j["decisions"][0]["evidence"] and j["trades"][0]["evidence"]


def test_replay_returns_plan_emitted_at_that_instant(client):
    p = {"symbol": "ETHUSDT", "tf": "1h"}
    asofs = client.get("/v2/replay/asofs", params=p).json()
    assert asofs == [LONG.asof, SHORT.asof]
    early = client.get("/v2/replay", params={**p, "asof": LONG.asof}).json()
    plan = [o for o in early["overlays"] if o["kind"] == "trade_plan"]
    assert len(plan) == 1 and plan[0] == LONG.overlays[0].model_dump()
    assert early["reports"][0] == LONG.model_dump()
    assert early["candles"][-1]["t"] == LONG.asof - STEP     # nada del futuro
    assert [t["plan_id"] for t in early["trades"]] == [LONG.overlays[0].id]
    assert early["trades"][0]["status"] == "ABIERTA"
    late = client.get("/v2/replay", params={**p, "asof": SHORT.asof}).json()
    assert late["overlays"][0] == SHORT.overlays[0].model_dump()
