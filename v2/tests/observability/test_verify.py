"""T74: el veredicto de una traza (`observability.verify`) separa fallos de resultados normales."""
from __future__ import annotations

from eim.observability.verify import check_trace, passed

AGENTS = ["structure", "plan"]


def _e(kind, comp, run, parent=None, status="ok", **kw):
    return {"kind": kind, "component_id": comp, "run_id": run, "parent_run_id": parent,
            "status": status, "source": kw.get("source"), "coverage": kw.get("coverage"),
            "mode": kw.get("mode", "SIMULADO")}


def _base(plan_status="ok"):
    cyc = "operation.cycle"
    return [
        _e("run_start", cyc, "A", "ROOT"), _e("run_end", cyc, "A", "ROOT"),
        _e("data_fetch", "data.store", "d1", "A", source="binance-futures", coverage=1.0),
        _e("signal", "agent.structure", "s1", "A"), _e("signal", "agent.plan", "s2", "A"),
        _e("synthesis", "synthesis.thesis", "y", "A"),
        _e("forecast", "forecast.engine", "f", "A"),
        _e("plan", "agent.plan", "p", "s2", status=plan_status)]


def _run(ev):
    return check_trace(ev, expected_agents=AGENTS, mode="SIMULADO")


def _failed(checks):
    return [c.name for c in checks if not c.ok and c.required]


def test_candle_without_plan_is_a_normal_result():
    assert passed(_run(_base("no_data")))


def test_plan_requires_risk_decision_and_approval_requires_orders():
    ev = _base()
    assert "risk_decision (si hay plan)" in _failed(_run(ev))
    ev.append(_e("risk_decision", "risk.engine", "r", "p"))          # aprobada: exige órdenes
    assert _failed(_run(ev)) == ["order_intent (si el riesgo aprobó)",
                                 "order_sent (si el riesgo aprobó)",
                                 "fill (si el riesgo aprobó)"]
    ev.append(_e("order_intent", "execution.gateway", "o1", "r"))
    assert _failed(_run(ev)) == ["order_sent (si el riesgo aprobó)",
                                 "fill (si el riesgo aprobó)"]
    ev += [_e("order_sent", "execution.service", "o2", "o1"),
           _e("fill", "execution.sim_broker", "o3", "o2")]
    assert passed(_run(ev))


def test_vetoed_plan_needs_no_orders():
    ev = _base() + [_e("risk_decision", "risk.engine", "r", "p", status="rejected")]
    assert passed(_run(ev))


def test_failures_are_detected():
    no_plan_signal = [e for e in _base() if e["component_id"] != "agent.plan"
                      or e["kind"] != "signal"]
    assert "una señal por agente" in _failed(_run(no_plan_signal))
    assert "evento forecast" in _failed(_run([e for e in _base() if e["kind"] != "forecast"]))
    no_src = _base()
    no_src[2]["source"] = ""
    assert "data_fetch declara su fuente" in _failed(_run(no_src))
    open_run = _base()
    open_run.pop(1)
    assert "cada run_start tiene su run_end" in _failed(_run(open_run))
    ghost = _base() + [_e("heartbeat", "x.inexistente", "z")]
    assert "componentes dentro del catálogo" in _failed(_run(ghost))
    real = _base() + [_e("heartbeat", "operation.cycle", "z", mode="REAL")]
    assert "modo SIMULADO en todos los eventos" in _failed(_run(real))


def test_lost_links_are_detected_but_the_cycle_root_is_expected():
    ev = _base("no_data")                          # un solo padre externo (ROOT): esperado
    assert passed(_run(ev))
    ev += [_e("heartbeat", "operation.cycle", "q", "X1"),
           _e("heartbeat", "operation.cycle", "w", "X2")]
    assert "sin eventos huérfanos" in _failed(_run(ev))
