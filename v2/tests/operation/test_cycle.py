"""Ciclo completo en paper: datos → agentes → plan → riesgo → SimBroker → reconciliación →
capital → alertas, con reinicio, kill-switch, drawdown, desconexión e informe semanal."""

import asyncio
import json

import pytest

from eim.execution.broker import STOP, TAKE_PROFIT
from eim.execution.service import CLOSED, OPEN
from eim.operation import alerts as A
from eim.operation.supervisor import Supervisor
from eim.operation.weekly import week_bounds
from tests.operation.helpers import START, SYM, H, Market, Q, Rig, StubAgent


@pytest.fixture
def rig(tmp_path):
    r = Rig(tmp_path, Market())
    r.build()
    yield r
    r.close()


def _trade(rig):
    return next(iter(rig.op.desk.rt.svc.trades.values()))


def test_cycle_opens_protected_position(rig):
    res = rig.op.step()
    assert res.analyzed == [SYM] and res.recon_ok
    d = res.decisions[0]
    assert d["approved"] and d["executed"], d
    broker = rig.op.desk.rt.svc.broker
    assert broker.position(SYM).qty > 0
    kinds = {(o.kind, o.trigger) for o in broker.open_orders(SYM)}
    assert (STOP, 1960.0) in kinds and (TAKE_PROFIT, 2080.0) in kinds
    t = _trade(rig)
    assert t.status == OPEN and t.opened_at == rig.now()
    assert rig.op.desk.mode.value == "SIMULADO"
    assert res.equity == pytest.approx(broker.equity())
    assert res.drawdown == pytest.approx(0, abs=1e-3)


def test_same_bar_is_not_reanalyzed(rig):
    rig.op.step()
    rig.advance(60_000)
    res = rig.op.step()
    assert res.analyzed == [] and len(rig.op.desk.rt.svc.trades) == 1


def test_sl_inside_candle_fills_at_trigger(rig):
    rig.op.step()
    rig.market.shocks[START] = (2000.0, 2001.0, 1950.0, 1955.0)
    rig.advance(Q)
    rig.op.step()
    t = _trade(rig)
    assert t.status == CLOSED and t.exit_reason == "SL" and t.exit_price == 1960.0
    assert t.pnl < 0 and t.r == pytest.approx(-1.0)
    assert rig.op.desk.rt.svc.broker.position(SYM).qty == 0
    assert not rig.op.desk.rt.svc.broker.open_orders(SYM)      # TP retirado


def test_gap_through_sl_fills_at_open(rig):
    rig.op.step()
    rig.market.shocks[START] = (1950.0, 1952.0, 1940.0, 1945.0)
    rig.advance(Q)
    rig.op.step()
    assert _trade(rig).exit_price == 1950.0


def test_tp_hit(rig):
    rig.op.step()
    rig.market.shocks[START] = (2000.0, 2090.0, 1999.0, 2085.0)
    rig.advance(Q)
    rig.op.step()
    t = _trade(rig)
    assert t.exit_reason == "TP" and t.exit_price == 2080.0 and t.r == pytest.approx(2.0)


def test_restart_restores_book_without_duplicates(rig):
    rig.op.step()
    qty = rig.op.desk.rt.svc.broker.position(SYM).qty
    rig.advance(H)
    rig.build()                                   # «reinicio» del proceso
    svc = rig.op.desk.rt.svc
    assert len(svc.trades) == 1 and svc.broker.position(SYM).qty == qty
    assert any(o.kind == STOP for o in svc.broker.open_orders(SYM))
    res = rig.op.step()
    assert res.analyzed == [SYM] and res.recon_ok
    assert len(svc.trades) == 1 and not res.decisions[0]["executed"]   # 1 por símbolo


def test_kill_switch_flattens_and_alerts(rig):
    rig.op.step()
    rig.kill.activate("prueba", rig.now(), by="manual")
    rig.advance(60_000)
    rig.op.step()
    svc = rig.op.desk.rt.svc
    assert svc.broker.position(SYM).qty == 0
    assert _trade(rig).exit_reason == "cierre ordenado: kill-switch"
    assert any(a.kind == A.KILL and a.level == A.CRITICAL for a in rig.sent)
    rig.advance(H)
    res = rig.op.step()
    assert not res.decisions[0]["approved"]


def test_drawdown_triggers_kill_switch(rig):
    rig.op.step()
    rig.op.desk.rt.svc.broker.balance -= 2_000       # pérdida del 20 % sobre el pico
    rig.advance(60_000)
    res = rig.op.step()
    assert res.drawdown >= 0.15 and rig.kill.active
    assert "drawdown" in rig.kill.state()["by"]
    assert {a.kind for a in rig.sent} >= {A.DRAWDOWN, A.KILL}


def test_disconnection_alert_and_resolution(rig):
    rig.op.step()
    rig.market.down = True
    rig.advance(60_000)
    assert not rig.op.step().ok
    assert not [a for a in rig.sent if a.kind == A.DISCONNECT]          # aún < 2 min
    rig.advance(150_000)
    rig.op.step()
    down = [a for a in rig.sent if a.kind == A.DISCONNECT]
    assert len(down) == 1 and down[0].level == A.CRITICAL
    rig.market.down = False
    rig.advance(60_000)
    rig.op.step()
    assert [a.resolved for a in rig.sent if a.kind == A.DISCONNECT] == [False, True]


def test_degraded_agent_alert_and_veto(rig):
    class Broken(StubAgent):
        def run(self, snap):
            raise RuntimeError("roto")

    rig.op.cycle.registry._agents[("structure", "1")] = Broken("structure")
    res = rig.op.step()
    assert not res.decisions[0]["approved"]
    deg = [a for a in rig.sent if a.kind == A.DEGRADED]
    assert deg and "structure=degraded" in deg[0].detail


def test_weekly_report_written_once(rig):
    rig.op.step()
    rig.market.shocks[START] = (2000.0, 2001.0, 1950.0, 1955.0)
    rig.advance(Q)
    rig.op.step()
    week_end = week_bounds(START)[1]
    rig.market.now = week_end + 60_000
    rig.op.step()
    out = rig.root / "out"
    mds = list(out.glob("semana_*.md"))
    assert len(mds) == 1
    text = mds[0].read_text(encoding="utf-8")
    for section in ("## Resultados", "## Comparación con el backtest", "### Desviaciones",
                    "## Calibración de escenarios", "## Incidentes", "## Riesgo"):
        assert section in text
    rep = json.loads(mds[0].with_suffix(".json").read_text(encoding="utf-8"))
    assert rep["trades"][SYM]["n"] == 1 and rep["trades"][SYM]["mean_r"] < -1  # comisión
    assert rep["acceptance"]["recon_unresolved"] == 0
    assert any(a.kind == A.REPORT for a in rig.sent)
    rig.advance(60_000)
    rig.op.step()
    assert len(list(out.glob("semana_*.md"))) == 1


def test_supervisor_retries_and_alerts(rig, monkeypatch):
    calls = {"n": 0}
    real = rig.op.step

    def flaky():
        calls["n"] += 1
        if calls["n"] <= 3:
            raise RuntimeError("fallo transitorio")
        return real()

    monkeypatch.setattr(rig.op, "step", flaky)
    waits: list[float] = []

    async def fake_sleep(s):
        waits.append(s)

    asyncio.run(Supervisor(rig.op, max_backoff_s=10, sleep=fake_sleep).run(max_cycles=4))
    st = rig.op.status
    assert st["failures"] == 3 and st["cycles"] == 1 and st["consecutive_failures"] == 0
    assert waits == [2.0, 4.0, 8.0, 1.0]                 # espera creciente, luego normal
    assert [a.kind for a in rig.sent if a.kind == A.SERVICE] == [A.SERVICE]
    hb = json.loads((rig.root / "operation" / "heartbeat.json").read_text(encoding="utf-8"))
    assert hb["last_heartbeat"] == rig.now()
    logs = list((rig.root / "operation" / "logs").glob("op-*.jsonl"))
    events = [json.loads(x)["event"] for x in logs[0].read_text(encoding="utf-8").splitlines()]
    assert events.count("ciclo_fallido") == 3 and "ciclo" in events


def test_extra_timeframe_is_analyzed_with_own_cursor_and_shares_symbol_cap(tmp_path):
    r = Rig(tmp_path, Market(), extra_tfs=("4h",))
    r.build()
    try:
        res = r.op.step()
        assert res.analyzed == [SYM, f"{SYM}:4h"]
        assert [d["tf"] for d in res.decisions] == ["1h", "4h"]
        first, second = res.decisions
        assert first["executed"] and not second["executed"]
        assert len(r.op.desk.rt.svc.trades) == 1
        assert set(r.op.cursors.analyzed) == {SYM, f"{SYM}:4h"}
        r.advance(60_000)
        assert r.op.step().analyzed == []                        # misma vela: no se reanaliza
    finally:
        r.close()
