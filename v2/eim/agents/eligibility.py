"""Elegibilidad de un agente para un instrumento, contra los datos REALMENTE disponibles (T91).

Regla aprobada en la ◆ de T87 (punto 4 de la lista de aceptación): **un agente sin el dato que
declara necesitar no corre**; sale `no_data` con el motivo escrito («no hay libro L2», «clase
no soportada», «historial < min_bars»), nunca un número silencioso. La decisión cruza tres
cosas: la ficha del agente (`capabilities.py`), el instrumento (T89) y la cobertura real del
snapshot (`coverage_of`).

`run_eligible` es la puerta de los instrumentos nuevos (el escáner de T93, la prueba de
portabilidad): filtra, adapta los supuestos (`adapt.py`) y corre con `run_agents`. **El ciclo
en vivo de BTC/ETH no pasa por aquí** y no cambia; para un perpetuo 24/7 la adaptación devuelve
los mismos agentes, así que un agente elegible da exactamente lo mismo por las dos vías.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from eim.agents import adapt as adaptation
from eim.agents.base import no_data_report
from eim.agents.capabilities import CAPABILITIES, AgentCapabilities, VolumeNeed
from eim.agents.runner import DEFAULT_TIMEOUT_S, run_agents
from eim.core import Agent, AgentReport, MarketSnapshot
from eim.instruments.models import DataCapability, Instrument

DAY_MS = 86_400_000
DEGRADED = "degradado con aviso"

#: Campos del snapshot que un agente puede declarar en `requires`.
SNAPSHOT_FIELDS = ("candles", "funding", "open_interest", "long_short_ratio", "basis",
                   "orderbook", "micro", "liquidations", "liq_flow", "headlines", "candles_tf",
                   "events", "arb", "leaders", "bot_signals", "intermarket")

#: Dato del snapshot → capacidad del instrumento que lo hace posible (si la hay).
FIELD_CAPABILITY: dict[str, DataCapability] = {
    "candles": DataCapability.CANDLES, "funding": DataCapability.FUNDING,
    "open_interest": DataCapability.OPEN_INTEREST, "micro": DataCapability.DEPTH_L2,
    "orderbook": DataCapability.DEPTH_L2, "curve": DataCapability.CURVE,
    "term_structure": DataCapability.CURVE, "option_chain": DataCapability.OPTION_CHAIN,
}

#: Cómo se dice que falta cada dato.
MISSING: dict[str, str] = {
    "candles": "no hay velas",
    "funding": "no hay funding (no es un perpetuo o no se sincronizó)",
    "open_interest": "no hay interés abierto",
    "long_short_ratio": "no hay ratio long/short",
    "basis": "no hay basis",
    "orderbook": "no hay libro L2",
    "micro": "no hay libro L2 (recolector de microestructura)",
    "liquidations": "no hay liquidaciones históricas",
    "liq_flow": "no hay flujo de liquidaciones en vivo",
    "headlines": "no hay titulares",
    "candles_tf": "no hay velas de otros marcos",
    "events": "no hay calendario económico",
    "arb": "no hay escáner de arbitraje",
    "leaders": "no hay tablero de líderes (copy trading)",
    "bot_signals": "no hay posturas del escuadrón de bots",
    "intermarket": "no hay series de intermercado",
    "curve": "no hay curva", "term_structure": "no hay estructura temporal de futuros",
    "option_chain": "no hay cadena de opciones", "rates": "no hay tipos a corto por moneda",
}


@dataclass(frozen=True)
class DataCoverage:
    """Lo que hay de verdad para un instrumento a `asof` (no lo que se espera que haya)."""

    timeframe: str
    fields: frozenset[str]
    n_bars: int
    span_days: float
    volume: Literal["real", "tick", "none"]
    taker_flow: bool


def _present(value: object) -> bool:
    if value is None:
        return False
    daily = getattr(value, "daily", None)      # `Liquidations`: el objeto existe aunque esté vacío
    if daily is not None:
        return bool(daily)
    try:
        return len(value) > 0                  # type: ignore[arg-type]
    except TypeError:
        return True


def coverage_of(snapshot: MarketSnapshot, inst: Instrument | None = None) -> DataCoverage:
    """Cobertura real del snapshot. El volumen sale del instrumento y se rebaja si los datos no
    lo traen (velas con volumen 0 = sin volumen, aunque la ficha diga otra cosa)."""
    c = snapshot.candles
    fields = frozenset(f for f in SNAPSHOT_FIELDS if _present(getattr(snapshot, f, None)))
    volume = adaptation.instrument_volume(inst) if inst is not None else "real"
    if not any(k.v > 0 for k in c):
        volume = "none"
    return DataCoverage(
        timeframe=snapshot.timeframe, fields=fields, n_bars=len(c),
        span_days=(c[-1].t - c[0].t) / DAY_MS if len(c) > 1 else 0.0, volume=volume,
        taker_flow=bool(c) and all(k.taker_buy_v is not None for k in c))


def _labels(fields: frozenset[str] | set[str]) -> str:
    return "; ".join(MISSING.get(f, f"falta «{f}»") for f in sorted(fields))


def check(caps: AgentCapabilities, inst: Instrument, cov: DataCoverage) -> tuple[bool, str]:
    """Decide con la ficha ya resuelta (ver `eligible`)."""
    if inst.asset_class not in caps.asset_classes:
        return False, (f"clase no soportada: {inst.asset_class.value} (el agente aplica a "
                       f"{', '.join(sorted(a.value for a in caps.asset_classes))})")
    if inst.session not in caps.session_models:
        return False, (f"modelo de sesión no soportado: {inst.session.value} (el agente pide "
                       f"{', '.join(sorted(s.value for s in caps.session_models))})")
    if caps.timeframes is not None and cov.timeframe not in caps.timeframes:
        return False, (f"marco no soportado: {cov.timeframe} (admite "
                       f"{', '.join(sorted(caps.timeframes))})")
    structural = {f for f in caps.all_requires
                  if f in FIELD_CAPABILITY and not inst.has(FIELD_CAPABILITY[f])}
    blocked = caps.requires & structural or (caps.requires_any
                                             and caps.requires_any <= structural)
    if blocked:
        return False, f"{_labels(structural)}: el instrumento no lo ofrece"
    missing = set(caps.requires - cov.fields)
    if missing:
        return False, _labels(missing)
    if caps.requires_any and not caps.requires_any & cov.fields:
        return False, _labels(caps.requires_any)
    if caps.needs_real_volume is VolumeNeed.REQUIRED and cov.volume != "real":
        return False, f"necesita volumen negociado real y el instrumento tiene: {cov.volume}"
    if caps.needs_real_volume is VolumeNeed.PREFERRED and cov.volume == "none":
        return False, "necesita volumen y el instrumento no tiene volumen negociado"
    if cov.n_bars < caps.min_bars:
        return False, f"historial < min_bars ({cov.n_bars} < {caps.min_bars} velas)"
    if cov.span_days < caps.min_history_days:
        return False, (f"historial < {caps.min_history_days:g} días "
                       f"({cov.span_days:.1f} días de velas)")
    degraded = list(_degradations(caps, cov))
    return True, "elegible" + (f", {DEGRADED}: {'; '.join(degraded)}" if degraded else "")


def _degradations(caps: AgentCapabilities, cov: DataCoverage):
    if caps.needs_real_volume in (VolumeNeed.PREFERRED, VolumeNeed.OPTIONAL):
        if cov.volume == "tick":
            yield "volumen de ticks, no negociado"
        elif cov.volume == "none":
            yield "sin volumen negociado: pierde la parte que lo usa"


def eligible(agent: Agent, inst: Instrument, coverage: DataCoverage) -> tuple[bool, str]:
    """(¿corre?, motivo). Sin ficha de capacidades no corre: no se presume lo que no se declara."""
    caps = CAPABILITIES.get(agent.id)
    if caps is None:
        return False, f"sin capacidades declaradas para {agent.id!r} (eim/agents/capabilities.py)"
    return check(caps, inst, coverage)


def ineligible_report(agent: Agent, asof: int, reason: str) -> AgentReport:
    """`no_data` con el motivo en el aviso y en `metrics["eligibility"]` (queda registrado)."""
    rep = no_data_report(agent.id, agent.version, asof, f"no elegible: {reason}")
    return rep.model_copy(update={"metrics": {"eligibility": {"eligible": False,
                                                              "reason": reason}}})


def select(agents: list[Agent], inst: Instrument, coverage: DataCoverage
           ) -> tuple[list[tuple[Agent, str]], list[tuple[Agent, str]]]:
    """(elegibles con su nota, no elegibles con su motivo), en el orden recibido."""
    ok: list[tuple[Agent, str]] = []
    out: list[tuple[Agent, str]] = []
    for a in agents:
        good, why = eligible(a, inst, coverage)
        (ok if good else out).append((a, why))
    return ok, out


def run_eligible(agents: list[Agent], snapshot: MarketSnapshot, inst: Instrument,
                 timeout: float = DEFAULT_TIMEOUT_S) -> list[AgentReport]:
    """Un reporte por agente, en el mismo orden: los elegibles corren adaptados al instrumento;
    los demás salen `no_data` con su motivo. Nunca levanta por un agente (lo hace `run_agents`).
    """
    cov = coverage_of(snapshot, inst)
    extra = adaptation.notes(inst, cov)
    slots: list[AgentReport | None] = [None] * len(agents)
    runnable: list[tuple[int, Agent, str]] = []
    for i, a in enumerate(agents):
        good, why = eligible(a, inst, cov)
        if good:
            runnable.append((i, adaptation.adapt(a, inst, cov), why))
        else:
            slots[i] = ineligible_report(a, snapshot.asof, why)
    reports = run_agents([a for _, a, _ in runnable], snapshot, timeout=timeout)
    for (i, a, why), rep in zip(runnable, reports, strict=True):
        if a is not agents[i] or why != "elegible":
            update: dict = {
                "evidence": [*rep.evidence, *extra, f"Elegibilidad: {why}"],
                "metrics": {**rep.metrics, "eligibility": {"eligible": True, "reason": why}}}
            if DEGRADED in why:          # el aviso se ve también en el estado, no solo en el texto
                update["warnings"] = [*rep.warnings, why]
                if rep.status == "ok":
                    update["status"] = "degraded"
            rep = rep.model_copy(update=update)
        slots[i] = rep
    return [r for r in slots if r is not None]
