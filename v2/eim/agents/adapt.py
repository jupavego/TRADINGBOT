"""Adaptación de los supuestos de tiempo y volumen de un agente al instrumento (T91).

Los agentes son puros y no saben de calendarios: lo que cambia de un instrumento a otro entra
por sus parámetros, cuyo valor por defecto es el comportamiento de siempre (cripto 24/7 con
volumen real). Aquí se construye, para un instrumento concreto, la versión con los supuestos
correctos. **Un perpetuo 24/7 con volumen real (BTC, ETH, el resto del universo de Binance)
recibe el mismo objeto, sin copiar ni tocar nada**: así sus resultados no pueden cambiar.

Qué se adapta fuera de ese caso (cambios mínimos y parametrizados):

- `vwap`: anclas en la zona del calendario (la NYSE corta el día en Nueva York), el ancla que
  no aplica al marco se declara (con velas de 1 d, la diaria) y el volumen de ticks degrada;
  sin volumen no calcula nada.
- `seasonality`: el mes termina en su última sesión (viernes 28 + fin de semana o festivo).
- `technical`: sin volumen, fuera las familias de volumen y flujo (con aviso); sin
  `taker_buy_v`, el flujo es capacidad ausente (no degrada ni cuenta en la cobertura).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from eim.core import Agent
from eim.instruments.calendar_specs import CalendarUnavailable
from eim.instruments.calendars import spec
from eim.instruments.models import DataCapability, Instrument, SessionKind

if TYPE_CHECKING:
    from eim.agents.eligibility import DataCoverage

VolumeKind = Literal["real", "tick", "none"]
#: Días sin sesión que puede haber entre la última vela de un mes y el día 1 (fin de semana y
#: un festivo pegado): con eso la última sesión del mes «llega» a su fin.
MONTH_END_GRACE_DAYS = 4.0


def instrument_volume(inst: Instrument) -> VolumeKind:
    """Qué volumen declara el instrumento (T89): real, de ticks o ninguno."""
    if inst.has(DataCapability.REAL_VOLUME):
        return "real"
    return "tick" if inst.has(DataCapability.TICK_VOLUME) else "none"


def is_native(inst: Instrument) -> bool:
    """¿Es el caso para el que se escribieron los agentes? (24/7 con volumen real)."""
    return inst.session is SessionKind.ALWAYS and instrument_volume(inst) == "real"


def anchor_tz(inst: Instrument) -> tuple[str, str | None]:
    """(zona, nota). Zona del calendario del instrumento; UTC con nota si no está registrado."""
    try:
        return spec(inst).tz, None
    except CalendarUnavailable:
        return "UTC", f"calendario {inst.calendar_id!r} no registrado: anclas en UTC"


def notes(inst: Instrument, coverage: DataCoverage | None = None) -> list[str]:
    """Lo que la adaptación cambia, en palabras (va a la evidencia del reporte)."""
    if is_native(inst):
        return []
    tz, tz_note = anchor_tz(inst)
    vol = coverage.volume if coverage is not None else instrument_volume(inst)
    out = [f"supuestos adaptados a {inst.id}: sesión {inst.session.value}, anclas en {tz}, "
           f"volumen {vol}"]
    if tz_note:
        out.append(tz_note)
    return out


def adapt(agent: Agent, inst: Instrument, coverage: DataCoverage | None = None) -> Agent:
    """El agente con los supuestos del instrumento; el MISMO objeto si no hay nada que adaptar."""
    if is_native(inst) or agent.id not in _ADAPTERS:
        return agent
    vol: VolumeKind = coverage.volume if coverage is not None else instrument_volume(inst)
    taker = coverage.taker_flow if coverage is not None else False
    return _ADAPTERS[agent.id](agent, inst, vol, taker)


def _vwap(agent, inst: Instrument, vol: VolumeKind, taker: bool):
    from eim.agents.vwap import VWAPAgent

    tz, _ = anchor_tz(inst)
    return VWAPAgent(agent.params.model_copy(update={
        "anchor_tz": tz, "explicit_dead_anchors": True, "volume_kind": vol}))


def _seasonality(agent, inst: Instrument, vol: VolumeKind, taker: bool):
    from eim.agents.seasonality import SeasonalityAgent

    if inst.session is SessionKind.ALWAYS:
        return agent
    return SeasonalityAgent(agent.params.model_copy(
        update={"month_end_grace_days": MONTH_END_GRACE_DAYS}))


def _technical(agent, inst: Instrument, vol: VolumeKind, taker: bool):
    from eim.agents.technical import TechnicalAgent

    absent = () if taker else ("flujo",)
    return TechnicalAgent(agent.params.model_copy(update={
        "volume_kind": vol, "families_absent": absent}), rules=agent.rules)


_ADAPTERS = {"vwap": _vwap, "seasonality": _seasonality, "technical": _technical}
