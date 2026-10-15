"""Registro de agentes por id y versión."""

from __future__ import annotations

from eim.core import Agent


def _vkey(version: str) -> tuple[int, ...]:
    return tuple(int(p) if p.isdigit() else 0 for p in version.split("."))


class AgentRegistry:
    """Mapa (id, versión) → agente. `get(id)` devuelve la versión más reciente."""

    def __init__(self) -> None:
        self._agents: dict[tuple[str, str], Agent] = {}

    def register(self, agent: Agent) -> Agent:
        key = (agent.id, agent.version)
        if key in self._agents:
            raise ValueError(f"agente ya registrado: {agent.id}@{agent.version}")
        self._agents[key] = agent
        return agent

    def get(self, agent_id: str, version: str | None = None) -> Agent:
        if version is not None:
            try:
                return self._agents[(agent_id, version)]
            except KeyError:
                raise KeyError(f"agente no registrado: {agent_id}@{version}") from None
        versions = [v for (i, v) in self._agents if i == agent_id]
        if not versions:
            raise KeyError(f"agente no registrado: {agent_id}")
        return self._agents[(agent_id, max(versions, key=_vkey))]

    def ids(self) -> list[str]:
        return sorted({i for i, _ in self._agents})

    def latest(self) -> list[Agent]:
        """Última versión de cada agente registrado."""
        return [self.get(i) for i in self.ids()]


def default_registry(arb_assets: tuple[str, ...] | None = None) -> AgentRegistry:
    """Registro con los agentes disponibles (cada tarea nueva añade el suyo aquí).

    `arb_assets` limita los activos del agente de arbitraje (foco); None = los del motor."""
    from eim.agents.arbitrage import ArbitrageAgent
    from eim.agents.arbitrage.params import ArbAgentParams
    from eim.agents.calendar import CalendarAgent
    from eim.agents.context import ContextAgent
    from eim.agents.derivatives import DerivativesAgent
    from eim.agents.elliott import ElliottAgent
    from eim.agents.ema import EMAAgent
    from eim.agents.levels import LevelsAgent
    from eim.agents.liquidations import LiquidationsAgent
    from eim.agents.microstructure import MicrostructureAgent
    from eim.agents.plan import PlanAgent
    from eim.agents.price_action import PriceActionAgent
    from eim.agents.regime import RegimeAgent
    from eim.agents.seasonality import SeasonalityAgent
    from eim.agents.structure import StructureAgent
    from eim.agents.technical import TechnicalAgent
    from eim.agents.vwap import VWAPAgent

    reg = AgentRegistry()
    for agent in (StructureAgent(), EMAAgent(), VWAPAgent(), PriceActionAgent(),
                  ElliottAgent(), SeasonalityAgent(), LiquidationsAgent(), LevelsAgent(),
                  DerivativesAgent(), MicrostructureAgent(), RegimeAgent(), ContextAgent(),
                  TechnicalAgent(), CalendarAgent(), _arb(ArbitrageAgent, ArbAgentParams,
                                                          arb_assets), PlanAgent()):
        reg.register(agent)
    return reg


def _arb(agent_cls, params_cls, assets: tuple[str, ...] | None):
    if assets is None:
        return agent_cls()
    base = params_cls()
    return agent_cls(params_cls(engine=base.engine.model_copy(update={"assets": assets})))
