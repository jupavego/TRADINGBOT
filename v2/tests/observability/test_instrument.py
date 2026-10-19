"""T74: la capa existente emite eventos sin cambiar su comportamiento."""
from __future__ import annotations

import asyncio
import json
import time

import pytest

import eim.observability.emit as E
from eim.agents.registry import default_registry
from eim.agents.runner import run_agents
from eim.observability import hooks_service
from eim.observability import thresholds as T
from eim.observability.catalog import has
from eim.observability.events import ObsEvent, trace_for
from eim.operation.supervisor import Supervisor
from tests.agents.conftest import make_snapshot
from tests.operation.helpers import SYM, H, Market, Rig


def _events(spool) -> list[dict]:
    E.flush()
    return sorted((json.loads(x) for f in spool.glob("*.jsonl")
                   for x in f.read_text(encoding="utf-8").splitlines()),
                  key=lambda r: (r["ts_utc"], r["event_id"]))


@pytest.fixture
def rig(tmp_path):
    r = Rig(tmp_path / "rig", Market())
    r.build()
    yield r
    r.close()


class Boom:
    id, version, requires = "boom", "1", frozenset()

    def run(self, snap):
        raise RuntimeError("falla simulada")


class Slow:
    id, version, requires = "slow", "1", frozenset()

    def run(self, snap):
        time.sleep(0.6)
        raise AssertionError("no debería llegar a usarse")


def test_agent_reports_identical_with_and_without_observability(tmp_path, spool):
    """(a) Las salidas de los 17 agentes son las mismas observando o no (golden intacto)."""
    snap = make_snapshot()
    agents = default_registry().latest()
    E.configure(process="t", spool_dir=tmp_path / "off", enabled=False)
    plain = run_agents(agents, snap)
    E.configure(process="t", spool_dir=spool, enabled=True)
    with E.span("operation.cycle", trace_id=trace_for("ETHUSDT", "1h", snap.asof)):
        observed = run_agents(agents, snap)
    assert [r.model_dump() for r in observed] == [r.model_dump() for r in plain]
    ev = _events(spool)
    sig = [e for e in ev if e["kind"] == "signal"]
    assert {e["component_id"] for e in sig} == {f"agent.{a.id}" for a in agents}
    assert all(e["inputs"][0]["hash"] and e["outputs"][0]["hash"] for e in sig)
    assert {e["status"] for e in sig} <= {"ok", "degraded", "no_data"}


def test_no_trace_means_no_agent_events(spool):
    """Backtests y consultas de la UI usan el mismo corredor y no producen eventos."""
    run_agents(default_registry().latest()[:3], make_snapshot())
    assert _events(spool) == []


def test_closed_candle_leaves_complete_ordered_trace(rig, spool):
    """(b) Una vela cerrada deja datos → señales → síntesis → plan → riesgo → orden → fill."""
    from eim.api.forecast import Forecaster

    rig.op.cycle.forecaster = Forecaster(rig.op.store, rig.reports)
    res = rig.op.step()
    assert res.analyzed == [SYM] and res.decisions[0]["executed"], res
    tid = rig.op.cycle.traces[SYM]
    ev = _events(spool)
    mine = [e for e in ev if e["trace_id"] == tid]
    kinds = [e["kind"] for e in mine]
    for k in ("data_fetch", "signal", "synthesis", "forecast", "plan", "risk_decision",
              "order_intent", "order_sent", "fill"):
        assert k in kinds, (k, sorted(set(kinds)))
    first = {k: next(e["ts_utc"] for e in mine if e["kind"] == k) for k in set(kinds)}
    chain = ["data_fetch", "signal", "synthesis", "plan", "risk_decision", "order_intent",
             "order_sent", "fill"]
    assert [first[k] for k in chain] == sorted(first[k] for k in chain)
    # señal, decisión aprobada y orden enviada son eventos distintos
    assert len({next(e["event_id"] for e in mine if e["kind"] == k)
                for k in ("signal", "risk_decision", "order_sent")}) == 3
    # sin huérfanos: todo run_start tiene su run_end y todo padre existe
    runs = {e["run_id"] for e in ev}
    assert all(e["parent_run_id"] in runs for e in ev if e["parent_run_id"])
    starts = {e["run_id"] for e in ev if e["kind"] == "run_start"}
    ends = {e["run_id"] for e in ev if e["kind"] == "run_end"}
    assert starts == ends
    assert all(e["trace_id"] == tid for e in mine)
    # el contrato del evento y el catálogo
    for e in ev:
        ObsEvent.model_validate(e)
        assert has(e["component_id"]), e["component_id"]
    df = next(e for e in mine if e["kind"] == "data_fetch")
    assert df["source"] and df["detail"]["key"]
    rd = next(e for e in mine if e["kind"] == "risk_decision")
    assert rd["status"] == "ok" and rd["mode"] == "SIMULADO"
    assert rd["outputs"][0]["hash"] and rd["parent_run_id"]
    assert next(e for e in mine if e["kind"] == "fill")["mode"] == "SIMULADO"
    assert len(mine) <= T.MAX_EVENTS_PER_CYCLE


def test_failing_and_slow_agents_emit_failure_and_cycle_continues(rig, spool):
    """(c) Un agente que lanza o excede el tiempo deja su evento de fallo y el ciclo sigue."""
    rig.op.cycle.registry.register(Boom())
    rig.op.cycle.registry.register(Slow())
    rig.op.cycle.p = type(rig.op.cycle.p)(**{**rig.op.cycle.p.__dict__, "agent_timeout_s": 0.2})
    res = rig.op.step()
    # el ciclo sigue: analiza, decide y el riesgo veta por datos degradados (comportamiento previo)
    assert res.analyzed == [SYM] and not res.decisions[0]["approved"]
    assert "degradados" in res.decisions[0]["reasons"][0]
    ev = _events(spool)
    sig = {e["component_id"]: e for e in ev if e["kind"] == "signal"}
    assert sig["agent.boom"]["status"] == "error"
    assert sig["agent.slow"]["status"] == "error"
    assert "timeout" in sig["agent.slow"]["detail"]["error"]
    assert sig["agent.plan"]["status"] == "ok"
    risk = next(e for e in ev if e["kind"] == "risk_decision")
    assert risk["status"] == "rejected" and "datos" in risk["detail"]["failed_rules"]
    end = next(e for e in ev if e["kind"] == "run_end" and e["component_id"] == "agent.boom")
    assert end["status"] == "error" and "falla simulada" in end["detail"]["error"]
    time.sleep(0.5)                                  # el hilo lento termina tarde
    late = [e for e in _events(spool)
            if e["kind"] == "signal" and e["component_id"] == "agent.slow"]
    assert len(late) == 1                            # y no duplica la señal


def _outcome(res):
    return ([{k: v for k, v in d.items()} for d in res.decisions], res.analyzed, res.ok,
            res.errors, res.recon_ok)


def test_cycle_survives_broken_emitter(tmp_path, monkeypatch):
    """(d) Con el emisor roto (disco inválido, o el propio emisor lanzando) el ciclo termina
    igual y con el mismo resultado que sin observar."""
    base = Rig(tmp_path / "a", Market())
    base.build()
    E.configure(process="t", spool_dir=tmp_path / "x", enabled=False)
    ref = _outcome(base.op.step())
    base.close()

    blocker = tmp_path / "f"
    blocker.write_text("x")
    disk = Rig(tmp_path / "b", Market())
    disk.build()
    E.configure(process="t", spool_dir=blocker / "s", enabled=True)
    assert _outcome(disk.op.step()) == ref
    E.flush()
    assert E.stats()["written"] == 0 and E.stats()["dropped"] > 0
    disk.close()

    broken = Rig(tmp_path / "c", Market())
    broken.build()

    def boom(*a, **k):
        raise RuntimeError("emisor roto")

    monkeypatch.setattr(E, "_em", boom)
    assert _outcome(broken.op.step()) == ref
    broken.close()
    monkeypatch.undo()
    E.close()


def test_cycle_overhead_within_budget(tmp_path):
    """(e) Sobrecosto de observar un ciclo real dentro del umbral de T72. Determinista: eventos
    reales del ciclo × coste p95 medido por evento (el reloj de pared de un ciclo corto varía
    más que el propio sobrecosto, sobre todo con la suite completa en marcha)."""
    r = Rig(tmp_path / "rig", Market())
    r.build()
    E.configure(process="t", spool_dir=tmp_path / "s", enabled=True)
    t = time.perf_counter()
    r.op.step()
    cycle_s = time.perf_counter() - t
    E.flush()
    n_events = E.stats()["emitted"]
    r.close()
    lat = []
    for i in range(2000):
        t0 = time.perf_counter()
        E.emit("heartbeat", "operation.supervisor", detail={"i": i})
        lat.append(time.perf_counter() - t0)
    E.close()
    p95 = sorted(lat)[int(len(lat) * 0.95)]
    assert 0 < n_events <= T.MAX_EVENTS_PER_CYCLE, n_events
    assert p95 * 1e6 <= T.EMIT_P95_US_MAX
    overhead = n_events * p95
    assert overhead <= max(T.MAX_CYCLE_OVERHEAD_MS / 1000,
                           T.MAX_CYCLE_OVERHEAD_FRACTION * cycle_s), (overhead, cycle_s)


def test_sync_emits_data_fetch_with_source_and_coverage(rig, spool):
    rig.op.step()
    fetch = [e for e in _events(spool) if e["kind"] == "data_fetch"
             and e["component_id"] == "data.binance_rest"]
    assert fetch and fetch[0]["source"] == "fake" and fetch[0]["coverage"] == 1.0
    assert fetch[0]["detail"]["timeframe"] in ("1h", "15m")


def test_sync_failure_emits_error_and_cycle_goes_on(rig, spool):
    rig.market.down = True
    res = rig.op.step()
    assert not res.ok and res.analyzed == []
    bad = [e for e in _events(spool) if e["kind"] == "data_fetch" and e["status"] == "error"]
    assert bad and "ConnectionError" in bad[0]["detail"]["error"]


def test_services_leave_heartbeat_real_cadence_and_errors(rig, spool, monkeypatch):
    def flaky():
        raise RuntimeError("ciclo roto")

    async def fake_sleep(s):
        return None

    sup = Supervisor(rig.op, sleep=fake_sleep)
    asyncio.run(sup.run(max_cycles=2))                 # dos vueltas buenas
    monkeypatch.setattr(rig.op, "step", flaky)
    asyncio.run(sup.run(max_cycles=1))
    ev = _events(spool)
    hb = [e for e in ev if e["kind"] == "heartbeat" and e["component_id"] == "operation.supervisor"]
    assert len(hb) == 3 and "interval_s" in hb[1]["detail"] and hb[2]["status"] == "degraded"
    cyc = [e for e in ev if e["kind"] == "heartbeat" and e["component_id"] == "operation.cycle"]
    assert len(cyc) == 2 and cyc[0]["duration_ms"] > 0
    err = [e for e in ev if e["kind"] == "alert" and e["status"] == "error"]
    assert err and err[0]["component_id"] == "operation.supervisor"


def test_watchdog_restart_is_an_event(tmp_path, spool):
    from eim.operation.notify import JsonLog
    from eim.operation.watchdog import Watchdog

    class P:
        def poll(self):
            return 1

    wd = Watchdog(["x"], {}, tmp_path / "hb.json", JsonLog(tmp_path / "logs"), check_s=1,
                  spawn=lambda c, e: P(), sleep=lambda s: None, notify=lambda a: None)
    wd.run(max_starts=1)
    ev = [e for e in _events(spool) if e["component_id"] == "operation.watchdog"]
    assert ev and ev[0]["status"] == "error" and ev[0]["detail"]["restarts"] == 1


def test_beat_sampling_and_never_raises(spool):
    for _ in range(5):
        hooks_service.beat("data.micro_collector", min_interval_s=60)
    assert len([e for e in _events(spool) if e["kind"] == "heartbeat"]) == 1
    hooks_service.beat(None, detail=object())            # entrada inválida: se traga
    hooks_service.service_error("x.y", object())


def test_gateway_rejection_is_an_event(rig, spool):
    """Una decisión vetada o alterada deja `order_intent` rechazado, no una orden enviada."""
    rig.op.step()
    from eim.execution.gateway import OrderGateway

    rt, desk = rig.op.desk.rt, rig.op.desk
    view, d = desk.evaluate(SYM, "1h")
    forged = d.model_copy(update={"size": d.size * 10})        # alterada: no autoriza nada
    with pytest.raises(PermissionError):
        OrderGateway(desk.engine, rt.svc).submit(forged, rig.now() + H // 3600)
    rej = [e for e in _events(spool) if e["kind"] == "order_intent" and e["status"] == "rejected"]
    assert rej and rej[0]["detail"]["reason"]
    assert not [e for e in _events(spool) if e["kind"] == "order_sent"
                and e["inputs"][0]["id"] == d.plan_id and e["ts_utc"] > rej[0]["ts_utc"]]


def test_plan_event_without_plan_carries_the_real_reason(spool):
    from eim.core import AgentReport
    from eim.observability import hooks

    rep = AgentReport(agent_id="plan", version="1", asof=1, bias=0, confidence=0, horizon_bars=1,
                      evidence=["sin plan: R:B 0.8 < 1.5"],
                      warnings=["Propuesta analítica, no es una orden"], metrics={"plan": None})
    with E.span("operation.cycle", trace_id="tr_x"):
        hooks.after_agents(hooks.AgentRunCtx(hooks.Ref(type="snapshot", id="s"), "tr_x"),
                           [rep], ["plan"])
    plan = next(e for e in _events(spool) if e["kind"] == "plan")
    assert plan["status"] == "no_data" and "R:B" in plan["detail"]["reason"]
