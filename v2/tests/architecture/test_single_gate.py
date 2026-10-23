"""T114 · Una sola puerta: ninguna ruta real abre una posición sin la autoridad registrada.

Prueba dinámica («fuente sin registrar»): cada fuente ACTIVA del registro recorre su ruta real
dos veces. Con el registro intacto abre (control positivo: la prueba sí pasa por ese camino); con
la fuente borrada del registro no abre nada y el rechazo queda con su motivo. Un atajo que abra
sin pasar por la autoridad hace fallar la segunda mitad.

Prueba estática: el inventario AST de las llamadas que abren, modifican o cierran una posición
(`inventory.py`) es exactamente la lista permitida, cada sitio con su porqué. Un sitio nuevo es
un camino nuevo y falla hasta que se registre (y pase por la puerta).
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from eim.risk import authority
from tests.architecture.inventory import inventory
from tests.copytrading.copy_helpers import engine as copy_engine
from tests.copytrading.copy_helpers import feed
from tests.copytrading.helpers import T0 as CT0
from tests.execution.test_api_execution import GO, _app
from tests.execution.test_arb_runner import _pilot
from tests.local_client import LocalClient
from tests.paper.test_arb_tests import _series
from tests.paper.test_ladder_stop_only_book import book, btc
from tests.risk.test_api_risk import P


def _drop(monkeypatch, source: str) -> None:
    monkeypatch.delitem(authority.SOURCES, source)


# --- una ruta real por fuente activa: (posiciones abiertas, motivos registrados) --------------
def _agents_plan(tmp_path) -> tuple[int, list[str]]:
    """API de riesgo → `RiskDesk.execute` → `OrderGateway` → testnet (simulada en memoria)."""
    app, fx, reports = _app(tmp_path)
    with LocalClient(app) as c:
        body = c.post("/v2/risk/execute", params=P, headers=GO).json()
    reports.close()
    return len(fx.posts("/fapi/v1/order")), list(body["decision"]["reasons"])


def _paper(_tmp_path) -> tuple[int, list[str]]:
    """Libro de un perfil del bróker simulado (escalera) con una idea en vivo."""
    rows = [(70_000.0, 70_050.0, 69_980.0, 70_030.0)] * 6
    st = book("moderado", [replace(btc(1), origin="vivo")], rows)
    why = [e["text"] for e in st.events if e["cat"] == "rechazada"]
    return len(st.slots) + len(st.trades), why + [r for d in st.decisions for r in d.reasons]


def _copy(_tmp_path) -> tuple[int, list[str]]:
    """Motor de copia: el líder abre 4 BTC → orden de la subcuenta tras el riesgo T29."""
    e = copy_engine()
    fills = feed(e, "BTC", 0.0, 4.0, 50_000.0, CT0 + 1_000, 1)
    return len([f for f in fills if f.kind == "open"]), [x.text for x in e.journal
                                                          if x.kind == "reject"]


def _arb(tmp_path) -> tuple[int, list[str]]:
    """Selector automático de arbitraje sobre una fotografía real del escáner."""
    r, pilot, _ = _pilot(tmp_path)
    rep = pilot.cycle()
    return len(r.ex.positions), [x for d in rep["decisions"] for x in d["reasons"]]


def _smoke(_tmp_path) -> tuple[int, list[str]]:
    """Escenarios de fontanería del arbitraje en papel (mismo ejecutor, riesgo y puerta)."""
    from eim.paper.arb_tests import run_all
    rep = run_all(_series(), hold_h=48)
    first = [s["checks"][0] for s in rep["scenarios"]]
    return sum(c["ok"] for c in first), [c["detail"] for c in first]


ROUTES = {"agents.plan": _agents_plan, "paper.strategies": _paper, "copy.leaders": _copy,
          "arb.scanner": _arb, "ops.smoke": _smoke}


def test_every_active_source_has_a_real_route_under_test():
    """Registrar una fuente activa sin añadir aquí su ruta real hace fallar la suite."""
    active = {k for k, s in authority.SOURCES.items() if s.status == "activa"}
    assert active == set(ROUTES)


@pytest.mark.parametrize("source", sorted(ROUTES))
def test_registered_source_opens_through_its_authority(source, tmp_path):
    opened, _ = ROUTES[source](tmp_path)
    assert opened > 0, f"{source}: la ruta real no abrió nada (el control positivo no vale)"


@pytest.mark.parametrize("source", sorted(ROUTES))
def test_unregistered_source_opens_nothing_and_the_rejection_is_recorded(source, tmp_path,
                                                                        monkeypatch):
    _drop(monkeypatch, source)
    opened, reasons = ROUTES[source](tmp_path)
    assert opened == 0, f"{source}: abrió sin pasar por la autoridad registrada"
    assert any("no registrada" in r for r in reasons), reasons


def test_a_decision_without_proposal_never_reaches_an_order():
    """Aprobada y sellada por el motor, pero sin propuesta de una fuente registrada: rechazada
    en la puerta de órdenes (la ruta se verifica otra vez al ejecutar)."""
    from tests.risk.test_gate import FakeBroker, _setup
    from tests.risk.helpers import NOW, account, market, plan
    eng, _, broker, gw = _setup()
    d = eng.evaluate(plan(), account(), market())
    assert d.approved and d.proposal is None
    with pytest.raises(PermissionError, match="sin propuesta"):
        gw.submit(d, NOW)
    assert broker.sent == [] and isinstance(broker, FakeBroker)


def test_a_registered_proposal_cannot_vouch_for_another_plan():
    from tests.risk.helpers import account, engine, market, plan, proposal
    eng, _, _ = engine()
    d = eng.evaluate(plan(sl=97_000.0), account(), market(), proposal=proposal(plan()))
    assert not d.approved and any(r.startswith("propuesta:") for r in d.reasons)


# --- inventario estático ------------------------------------------------------------------
ALLOWED = {
    # abrir: solo tras la autoridad (sello + ruta) o su política registrada
    ("orden al exchange", "execution/gateway.py", "OrderGateway.submit"),
    ("arbitraje al exchange", "execution/gateway.py", "ArbGateway.submit"),
    ("orden firmada", "execution/service.py", "ensure_order"),          # lo usa ExecutionService
    ("decisión del bróker", "paper/policy.py", "decide"),
    ("decisión del bróker", "paper/policy.py", "_no"),
    ("posición del bróker", "paper/book.py", "_open"),                  # policy.verify antes
    ("orden de la copia", "copytrading/copy_engine.py", "CopyEngine.on_signal"),  # crece tras _admit
    ("relleno de la copia", "copytrading/copy_engine.py", "CopyEngine._execute"),
    # modificar o cerrar: solo la regla de salida de la posición o una salvaguarda
    ("llenado del bróker", "paper/book.py", "run_profile"),             # el precio toca la entrada
    ("cancelación del bróker", "paper/book.py", "run_profile"),         # la orden límite vence
    ("cierre del bróker", "paper/book.py", "run_profile"),              # camino de precios
    ("cierre rechazado del bróker", "paper/book.py", "_close"),         # T109: no se ejecuta
    ("orden de la copia", "copytrading/copy_engine.py", "CopyEngine._exit"),     # stop o kill
    ("orden de la copia", "copytrading/copy_control.py", "EngineControl._resync"),  # foto real
    ("cierre testnet", "execution/reconcile.py", "Reconciler.run"),     # kill-switch
    ("cierre testnet", "execution/reconcile.py", "Reconciler._symbol"),  # posición sin SL
    ("cierre testnet", "execution/service.py", "ExecutionService.repair_sl"),  # SL no reponible
    ("cierre testnet", "api/execution.py", "build_execution_router.flatten"),  # manual confirmado
    ("cierre testnet", "execution/smoke.py", "run"),                    # fin de la prueba de humo
    ("cierre de todo el arbitraje", "execution/arb_recon.py", "ArbReconciler.run"),  # kill-switch
    ("cierre de todo el arbitraje", "api/arb_execution.py",
     "build_arb_execution_router.flatten"),                             # manual confirmado
    ("cierre de un arbitraje", "api/arb_execution.py", "build_arb_execution_router.close"),
    ("cierre de un arbitraje", "execution/arb_executor.py", "ArbExecutor.flatten_all"),
    ("cierre de un arbitraje", "execution/arb_runner.py", "ArbAutopilot.manage"),  # manage.decide
    ("cierre de un arbitraje", "execution/arb_smoke.py", "Smoke.carry"),
    ("cierre de un arbitraje", "paper/arb_tests.py", "run_carry"),
    ("rebalanceo de arbitraje", "execution/arb_runner.py", "ArbAutopilot.manage"),
}


def test_position_primitives_are_called_only_from_their_registered_sites():
    found = inventory()
    assert found - ALLOWED == set(), "camino nuevo hacia una posición sin registrar"
    assert ALLOWED - found == set(), "sitio permitido que ya no existe: actualizar la lista"


def test_the_paper_book_opens_only_with_an_approval_of_its_policy():
    """Una `PaperDecision` aprobada que no salió de `policy.decide` no abre nada."""
    from eim.paper.book import ProfileState, _open
    from eim.paper.policy import PaperDecision
    from tests.paper.test_ladder_stop_only_book import P as PROFILES
    st = book("moderado", [btc(1)], [(70_000.0, 70_050.0, 69_980.0, 70_030.0)] * 4)
    forged = PaperDecision(o=next(iter(st.slots.values())).o, approved=True, qty=1.0,
                           leverage=1, margin=1.0)
    fresh = ProfileState(p=PROFILES["moderado"], equity=10_000.0)
    with pytest.raises(PermissionError, match="aprobada por la política"):
        _open(fresh, forged, {}, [], [0])
    assert fresh.slots == {}
