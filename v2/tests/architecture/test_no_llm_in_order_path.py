"""T114 · Ningún LLM en la ruta de una orden (los LLM solo informan, `CLAUDE.md`).

1. Estático: desde los módulos que deciden o envían una orden, el grafo de imports (todos, incluso
   los de dentro de funciones) no alcanza ningún cliente de LLM. `eim/api/risk.py` (RiskDesk) y
   el ciclo de operación no están en el punto de partida: también orquestan el análisis (la vista
   de la API arma el registro de agentes, que conecta el agente `context` con su cliente) y por eso
   el grafo los une con el LLM sin que la decisión lo llame. Eso lo cubre el punto 4.
2. Registro: una fuente LLM no puede tener ruta a ejecución (el registro no arranca) y su
   propuesta se veta con el motivo.
3. Propiedad: lo que diga el agente `context` (LLM) solo puede añadir una pausa; nunca aprueba
   lo vetado ni agranda un tamaño.
4. Dinámico: las cinco rutas reales (las de `test_single_gate.py`, API de riesgo incluida) abren
   con los clientes de LLM saboteados, y ninguno fue llamado.
"""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from eim.core import AgentReport
from eim.risk import authority
from eim.risk.inputs import market_context
from tests.risk.helpers import NOW, account, engine, plan, proposal

EIM = Path(__file__).resolve().parents[2] / "eim"
ORDER_PATH = (
    "eim.execution.gateway", "eim.execution.service", "eim.execution.arb_runner",
    "eim.execution.arb_executor", "eim.execution.reconcile", "eim.risk.engine",
    "eim.risk.arb_engine", "eim.risk.authority", "eim.paper.book", "eim.paper.policy",
    "eim.copytrading.copy_engine", "eim.copytrading.copy_risk", "eim.risk.inputs",
)
LLM_MODULES = ("eim.data.providers.claude_context", "eim.data.providers.claude_library",
               "eim.library.qa")
LLM_PACKAGES = ("anthropic", "openai")


def _file(mod: str) -> Path | None:
    base = EIM.parent.joinpath(*mod.split("."))
    for p in (base.with_suffix(".py"), base / "__init__.py"):
        if p.exists():
            return p
    return None


def _imports(mod: str) -> set[str]:
    p = _file(mod)
    if p is None:
        return set()
    out: set[str] = set()
    for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.add(node.module)
            out |= {f"{node.module}.{a.name}" for a in node.names
                    if _file(f"{node.module}.{a.name}")}
    parents = {".".join(mod.split(".")[:k]) for k in range(1, mod.count(".") + 1)}
    return out | parents


def reachable(start: tuple[str, ...]) -> set[str]:
    seen, todo = set(), list(start)
    while todo:
        m = todo.pop()
        if m in seen:
            continue
        seen.add(m)
        if m.split(".")[0] == "eim":
            todo += sorted(_imports(m) - seen)
    return seen


def test_no_llm_client_is_reachable_from_the_order_path():
    mods = reachable(ORDER_PATH)
    assert len([m for m in mods if m.startswith("eim.")]) > 40     # el grafo es real
    bad = sorted(m for m in mods if m in LLM_MODULES or m.split(".")[0] in LLM_PACKAGES)
    assert bad == [], f"un LLM entró en la ruta de una orden: {bad}"


def test_the_llm_modules_do_exist():
    """Si cambian de nombre, esta prueba deja de proteger: que falle aquí y se actualice."""
    assert all(_file(m) for m in LLM_MODULES)


def test_an_llm_source_cannot_be_registered_with_a_route():
    bad = replace(authority.SOURCES["agents.context"], status="activa",
                  authorities=("risk.engine",))
    with pytest.raises(ValueError, match="LLM"):
        authority._validate({**authority.SOURCES, bad.id: bad})


def test_every_llm_source_only_informs():
    llm = [s for s in authority.SOURCES.values() if s.llm]
    assert llm and all(s.status != "activa" and not s.authorities for s in llm)


def test_a_proposal_from_the_llm_source_is_vetoed_with_its_reason():
    eng, _, _ = engine()
    p = plan()
    d = eng.evaluate(p, account(), _market(), proposal=proposal(p, source="agents.context"))
    assert not d.approved and any("LLM" in r for r in d.reasons)


def _report(agent: str, metrics: dict, status: str = "ok") -> AgentReport:
    return AgentReport(agent_id=agent, version="1", asof=NOW - 5 * 60_000, bias=0.0,
                       confidence=0.5, horizon_bars=0, metrics=metrics, status=status)


def _market(reports: list[AgentReport] = ()):
    base = [_report(a, {}) for a in ("structure", "levels", "plan", "vwap")]
    return market_context([*base, *reports], NOW - 5 * 60_000, NOW, 3_600_000)


CONTEXT_SAYS = [
    {}, {"event_pause": False}, {"event_pause": True, "event_risk": "alto"},
    {"approve": True, "size": 99.0, "risk_per_trade": 0.5, "event_pause": False},
    {"lift_blackout": True, "override": "aprobar"},
]


@pytest.mark.parametrize("says", CONTEXT_SAYS)
def test_the_llm_context_can_only_add_a_pause(says):
    eng, _, _ = engine()
    p = plan()
    base = eng.evaluate(p, account(), _market(), proposal=proposal(p))
    with_llm = eng.evaluate(p, account(), _market([_report("context", says)]),
                            proposal=proposal(p))
    assert base.approved
    if says.get("event_pause"):
        assert not with_llm.approved and with_llm.size == 0     # solo puede vetar
    else:
        assert with_llm.approved == base.approved and with_llm.size == base.size


def test_the_real_routes_open_without_calling_any_llm(tmp_path, monkeypatch):
    from eim.data.providers import claude_context, claude_library
    from tests.architecture.test_single_gate import ROUTES
    calls: list[str] = []

    def trap(name: str):
        def f(*a, **k):
            calls.append(name)
            raise AssertionError(f"{name}: un LLM se llamó en la ruta de una orden")
        return f

    for mod, attrs in ((claude_context, ("build_payload", "make_context_analyzer")),
                       (claude_library, ("build_payload",))):
        for a in attrs:
            monkeypatch.setattr(mod, a, trap(f"{mod.__name__}.{a}"))
    for cls in (claude_context.ClaudeContextAnalyzer, claude_context.CachedContextAnalyzer,
                claude_library.ClaudeLibraryLlm):
        monkeypatch.setattr(cls, "__call__", trap(cls.__name__))
    for k, route in ROUTES.items():
        opened, _ = route(tmp_path / k)
        assert opened > 0, k
    assert calls == []
