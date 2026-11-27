"""T91: cada agente de `default_registry` declara sus capacidades, y la ficha no se aparta del
agente (mismo `requires`, mismo `min_bars`). Es la condición (c) de los tests de T91."""
from __future__ import annotations

import pytest

from eim.agents.capabilities import (
    CAPABILITIES,
    PRICED,
    SIBLINGS,
    CostClass,
    VolumeNeed,
)
from eim.agents.eligibility import MISSING, SNAPSHOT_FIELDS
from eim.agents.registry import default_registry
from eim.instruments.models import AssetClass, SessionKind

AGENTS = default_registry().latest()


def test_every_registered_agent_has_capabilities():
    missing = [a.id for a in AGENTS if a.id not in CAPABILITIES]
    assert not missing, f"agentes sin ficha en eim/agents/capabilities.py: {missing}"
    assert set(CAPABILITIES) == {a.id for a in AGENTS}, "fichas de agentes que no existen"


@pytest.mark.parametrize("agent", AGENTS, ids=lambda a: a.id)
def test_capabilities_match_the_agent(agent):
    caps = CAPABILITIES[agent.id]
    assert caps.all_requires == set(agent.requires)
    assert not caps.requires & caps.requires_any
    assert caps.all_requires <= set(SNAPSHOT_FIELDS)
    own = getattr(getattr(agent, "params", None), "min_bars", None)
    if own is not None:
        assert caps.min_bars == own, "min_bars de la ficha distinto del del agente"
    assert caps.asset_classes and caps.session_models and caps.horizon
    assert caps.cost_class is not CostClass.UNMEASURED, "costo medido en T87"


def test_candle_agents_are_portable_with_declared_assumptions():
    candle_only = {a.id for a in AGENTS if set(a.requires) == {"candles"}}
    assert len(candle_only) == 11
    for agent_id in candle_only:
        caps = CAPABILITIES[agent_id]
        assert caps.asset_classes == PRICED and caps.session_models == frozenset(SessionKind)
    assert AssetClass.BOND not in PRICED and AssetClass.OPTION not in PRICED
    assert CAPABILITIES["vwap"].needs_real_volume is VolumeNeed.PREFERRED
    assert CAPABILITIES["technical"].needs_real_volume is VolumeNeed.OPTIONAL
    assert CAPABILITIES["microstructure"].needs_real_volume is VolumeNeed.REQUIRED


def test_cost_classes_follow_t87_measurement():
    cheap = {k for k, c in CAPABILITIES.items() if c.cost_class is CostClass.CHEAP}
    # T87: 13 agentes ≤ 20 ms; T214 suma `vol_surface` (≈ 5 ms con una toma real de 956 opciones)
    assert len(cheap) == 14 and "plan" not in cheap and "vol_surface" in cheap
    assert CAPABILITIES["plan"].cost_class is CostClass.EXPENSIVE


def test_sibling_contracts_only_declare_requires():
    ids = {s.agent_id for s in SIBLINGS}
    assert ids == {"yield_curve", "futures_basis", "options_iv", "fx_carry"}
    assert not ids & set(CAPABILITIES), "un hermano pendiente no es un agente registrado"
    for s in SIBLINGS:
        assert s.requires and s.task in {"T98", "T99", "T100"}
        assert all(f in MISSING for f in s.requires), "cada dato tiene su motivo de ausencia"
