"""Capacidades declaradas de cada agente (T91): a qué instrumentos, marcos y datos aplica.

**Datos, no lógica.** Aquí no se decide nada: `eim/agents/eligibility.py` lee esta tabla y la
cruza con el instrumento (T89) y con lo que el snapshot trae de verdad. El `Protocol` `Agent`
no se toca (lo cumplen los 20 agentes tal cual): la ficha vive al lado, por id.

Qué declara cada ficha y por qué (lo que T87 midió que faltaba además de `requires`):

- `asset_classes`: clases donde el concepto del agente tiene sentido (las de `candles` no
  cubren renta fija ni opciones, que son solo viabilidad: T87 ◆4 y T100).
- `requires` / `requires_any`: lo mismo que `agent.requires`, partido en «todos» y «al menos
  uno» (`liquidations` trabaja con el flujo en vivo **o** con el histórico). Un test exige que
  su unión sea exactamente `agent.requires`.
- `timeframes`: marcos admitidos; `None` = cualquiera.
- `min_bars` y `min_history_days`: velas mínimas (las mismas que el `min_bars` del agente, que
  un test compara) e historia mínima en días cuando el agente mide en meses o en días.
- `session_models`: 24/7, 24/5 o sesión de bolsa (`SessionKind` de T89).
- `needs_real_volume`: `ninguno` (no mira el volumen) · `opcional` (sin volumen pierde la
  parte que lo usa, con aviso) · `preferible` (con volumen de ticks corre degradado; sin
  volumen no corre) · `obligatorio` (sin volumen real no corre).
- `time_anchor`: con qué reloj razona (velas, día UTC, sesión, mes calendario).
- `horizon`: horizonte que publica, en palabras.
- `cost_ms`: mediana medida en T87 (1 h, BTCUSDT, 500 velas; `reports/t87_agents_cost.md`).

Un agente nuevo añade aquí su ficha (lo comprueba `tests/agents/test_capabilities.py`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from eim.instruments.models import AssetClass as A
from eim.instruments.models import SessionKind as S


class VolumeNeed(StrEnum):
    NONE = "ninguno"           # no mira el volumen
    OPTIONAL = "opcional"      # sin volumen pierde la parte que lo usa (y lo dice)
    PREFERRED = "preferible"   # necesita volumen: con ticks corre degradado; sin volumen, no corre
    REQUIRED = "obligatorio"   # solo volumen negociado real


class TimeAnchor(StrEnum):
    BARS = "velas"                 # cuenta velas; no sabe de días ni de sesiones
    UTC_DAY = "dia_utc"            # ancla en el día UTC (por defecto; en sesión: `anchor_tz`)
    SESSION = "sesion"             # ancla en la sesión del calendario del instrumento
    CALENDAR_MONTH = "mes"         # meses calendario completos
    WALL_CLOCK = "reloj"           # ventanas de horas o días de reloj (eventos, titulares)


class CostClass(StrEnum):
    CHEAP = "barato"               # ≤ 20 ms: la etapa barata del embudo de T93
    MEDIUM = "medio"               # ≤ 200 ms
    EXPENSIVE = "caro"             # > 200 ms
    UNMEASURED = "sin_medir"


CHEAP_MS = 20.0
MEDIUM_MS = 200.0

#: Clases con precio negociado o calculado sobre el que razonan los agentes de velas.
PRICED = frozenset({A.CRYPTO, A.EQUITY, A.ETF, A.INDEX, A.FX, A.COMMODITY, A.FUTURE})
#: Todas: los agentes de riesgo y contexto (calendario macro, titulares) no dependen de la clase.
ANY_CLASS = frozenset(A)
ANY_SESSION = frozenset(S)
#: Lo que solo existe en un perpetuo 24/7 (funding, recolectores de Binance, líderes, bots).
PERP_ONLY = frozenset({S.ALWAYS})
INTRADAY = frozenset({"1m", "5m", "15m", "1h", "4h"})


@dataclass(frozen=True)
class AgentCapabilities:
    """Ficha de capacidades de un agente (inmutable)."""

    agent_id: str
    asset_classes: frozenset[A]
    requires: frozenset[str]
    min_bars: int
    session_models: frozenset[S]
    needs_real_volume: VolumeNeed
    time_anchor: TimeAnchor
    horizon: str
    cost_ms: float | None
    requires_any: frozenset[str] = frozenset()
    timeframes: frozenset[str] | None = None
    min_history_days: float = 0.0
    notes: str = ""

    @property
    def all_requires(self) -> frozenset[str]:
        """Lo que el agente declara en `requires` (unión de «todos» y «al menos uno»)."""
        return self.requires | self.requires_any

    @property
    def cost_class(self) -> CostClass:
        if self.cost_ms is None:
            return CostClass.UNMEASURED
        if self.cost_ms <= CHEAP_MS:
            return CostClass.CHEAP
        return CostClass.MEDIUM if self.cost_ms <= MEDIUM_MS else CostClass.EXPENSIVE


def _candles(agent_id: str, min_bars: int, horizon: str, cost_ms: float, *,
             volume: VolumeNeed = VolumeNeed.NONE, anchor: TimeAnchor = TimeAnchor.BARS,
             min_history_days: float = 0.0, notes: str = "") -> AgentCapabilities:
    """Agente portable por dato: solo pide velas y vale para cualquier clase con precio."""
    return AgentCapabilities(
        agent_id=agent_id, asset_classes=PRICED, requires=frozenset({"candles"}),
        min_bars=min_bars, session_models=ANY_SESSION, needs_real_volume=volume,
        time_anchor=anchor, horizon=horizon, cost_ms=cost_ms,
        min_history_days=min_history_days, notes=notes)


_ALL: tuple[AgentCapabilities, ...] = (
    # --- los 11 de `candles` (portables por dato, con supuestos declarados) -----------------
    _candles("structure", 60, "12 velas", 87.07, volume=VolumeNeed.PREFERRED,
             notes="EMA-200: con menos de 400 velas avisa de calentamiento incompleto; la "
                   "coherencia y la fricción usan la razón de volumen (F-008): sin volumen "
                   "salen NaN (medido en T91), así que sin volumen no corre"),
    _candles("ema", 30, "12 velas", 54.78, notes="EMA-200 estable desde 200 velas"),
    _candles("vwap", 24, "24 velas", 48.03, volume=VolumeNeed.PREFERRED,
             anchor=TimeAnchor.UTC_DAY,
             notes="anclas diaria/semanal/quincenal/mensual; en sesión de bolsa ancla por la "
                   "zona del calendario (`anchor_tz`); con velas de 1 d el ancla diaria no aplica"
                   " y se declara"),
    _candles("price_action", 20, "12 velas", 106.46),
    _candles("elliott", 30, "12 velas", 0.23),
    _candles("seasonality", 0, "30 velas", 0.88, anchor=TimeAnchor.CALENDAR_MONTH,
             min_history_days=62.0,
             notes="mide en meses calendario completos (min_months=2); en bolsa el último mes "
                   "cierra en su última sesión, no a medianoche del día 1"),
    _candles("levels", 60, "24 velas", 2.06, notes="ATR en unidades de precio, por vela"),
    _candles("regime", 120, "24 velas", 113.08,
             notes="BOCPD por vela: un fin de semana es un retorno más, no un hueco"),
    _candles("technical", 120, "12 velas", 85.00, volume=VolumeNeed.OPTIONAL,
             notes="familia «volumen» con volumen real; «flujo» necesita taker_buy_v (solo "
                   "Binance): sin él es capacidad ausente, no degradación"),
    _candles("literature", 60, "12 velas", 6.82,
             notes="las fichas declaran su propio supuesto de clase (futuros, 24/7)"),
    _candles("plan", 120, "24 velas", 1414.23, volume=VolumeNeed.PREFERRED,
             notes="el más caro del ciclo (73 % en T87): queda fuera de la etapa barata; "
                   "envuelve a `structure`, así que hereda su necesidad de volumen"),
    # --- genéricos por otra vía ---------------------------------------------------------------
    AgentCapabilities(
        agent_id="calendar", asset_classes=ANY_CLASS, requires=frozenset({"events"}),
        min_bars=0, session_models=ANY_SESSION, needs_real_volume=VolumeNeed.NONE,
        time_anchor=TimeAnchor.WALL_CLOCK, horizon="0 velas (riesgo de evento, no dirección)",
        cost_ms=0.06),
    AgentCapabilities(
        agent_id="context", asset_classes=ANY_CLASS, requires=frozenset({"headlines"}),
        min_bars=0, session_models=ANY_SESSION, needs_real_volume=VolumeNeed.NONE,
        time_anchor=TimeAnchor.WALL_CLOCK, horizon="titulares de las últimas 48 h",
        cost_ms=0.01, notes="costo medido sin LLM; el real es la llamada al modelo"),
    AgentCapabilities(
        agent_id="intermarket", asset_classes=PRICED, requires=frozenset({"intermarket"}),
        min_bars=0, session_models=ANY_SESSION, needs_real_volume=VolumeNeed.NONE,
        time_anchor=TimeAnchor.SESSION, horizon="5 días de sesión", cost_ms=1.93,
        notes="velas DIARIAS cerradas de otros mercados (T183); el mínimo de sesiones comunes "
              "(min_common) lo comprueba el agente sobre esas series, no sobre las del marco"),
    AgentCapabilities(
        agent_id="vol_surface", asset_classes=frozenset({A.CRYPTO}),
        requires=frozenset({"option_chain"}), min_bars=0, session_models=PERP_ONLY,
        needs_real_volume=VolumeNeed.NONE, time_anchor=TimeAnchor.WALL_CLOCK,
        horizon="0 velas (volatilidad implícita, no dirección)", cost_ms=4.70,
        notes="T214: cadena de opciones de Deribit de la moneda base (hoy BTC; ◆ de T213, nivel "
              "1, solo uso personal); las velas solo sirven para la prima de varianza y su falta "
              "se avisa. Realiza para BTC el contrato hermano `options_iv` de T100, que sigue "
              "abierto para opciones de acciones e índices. Costo medido en la nube con una toma "
              "real (956 opciones), no en la portátil como T87"),
    # --- específicos de perpetuos y de Binance --------------------------------------------------
    AgentCapabilities(
        agent_id="derivatives", asset_classes=PRICED,
        requires=frozenset({"candles", "funding", "open_interest"}), min_bars=13,
        session_models=PERP_ONLY, needs_real_volume=VolumeNeed.NONE,
        time_anchor=TimeAnchor.BARS, horizon="12 velas", cost_ms=2.25,
        notes="cualquier perpetuo con funding e interés abierto (también los TradFi); "
              "`min_bars` = change_bars + 1"),
    AgentCapabilities(
        agent_id="microstructure", asset_classes=frozenset({A.CRYPTO, A.COMMODITY, A.EQUITY,
                                                           A.ETF, A.FUTURE}),
        requires=frozenset({"candles", "micro"}), min_bars=24, timeframes=INTRADAY,
        session_models=PERP_ONLY, needs_real_volume=VolumeNeed.REQUIRED,
        time_anchor=TimeAnchor.BARS, horizon="3 velas", cost_ms=1.62,
        notes="recolector L2 de Binance (T23); `min_bars` = velas con recolección"),
    AgentCapabilities(
        agent_id="liquidations", asset_classes=frozenset({A.CRYPTO}), requires=frozenset(),
        requires_any=frozenset({"liq_flow", "liquidations"}), min_bars=0,
        session_models=PERP_ONLY, needs_real_volume=VolumeNeed.NONE,
        time_anchor=TimeAnchor.BARS, horizon="24 velas (6 con flujo en vivo)", cost_ms=0.82,
        notes="flujo en vivo multi-bolsa o histórico coin-margined (retirado en 2024)"),
    AgentCapabilities(
        agent_id="arbitrage", asset_classes=frozenset({A.CRYPTO}), requires=frozenset({"arb"}),
        min_bars=0, session_models=PERP_ONLY, needs_real_volume=VolumeNeed.NONE,
        time_anchor=TimeAnchor.WALL_CLOCK, horizon="0 velas (neutral al mercado)", cost_ms=2.03),
    AgentCapabilities(
        agent_id="smart_money", asset_classes=frozenset({A.CRYPTO}),
        requires=frozenset({"leaders"}), min_bars=0, session_models=PERP_ONLY,
        needs_real_volume=VolumeNeed.NONE, time_anchor=TimeAnchor.WALL_CLOCK,
        horizon="mediana de permanencia de los líderes", cost_ms=0.01),
    AgentCapabilities(
        agent_id="bots", asset_classes=frozenset({A.CRYPTO}), requires=frozenset({"bot_signals"}),
        min_bars=0, session_models=PERP_ONLY, needs_real_volume=VolumeNeed.NONE,
        time_anchor=TimeAnchor.BARS, horizon="mediana de los bots que votan", cost_ms=0.01),
)

CAPABILITIES: dict[str, AgentCapabilities] = {c.agent_id: c for c in _ALL}


@dataclass(frozen=True)
class SiblingContract:
    """Contrato `requires` de un agente hermano que aún no existe (se construye en su clase)."""

    agent_id: str
    task: str
    asset_classes: frozenset[A]
    requires: frozenset[str]
    description: str
    data_notes: tuple[str, ...] = field(default_factory=tuple)


#: Agentes hermanos pendientes (punto 4 de T91): solo el contrato, ninguno se construye aquí.
SIBLINGS: tuple[SiblingContract, ...] = (
    SiblingContract(
        "yield_curve", "T100", frozenset({A.BOND}), frozenset({"curve"}),
        "curva de rendimiento y carry de renta fija (pendiente, roll-down)",
        ("serie `curve` de T90: un plazo por serie, point-in-time",)),
    SiblingContract(
        "futures_basis", "T99", frozenset({A.FUTURE, A.COMMODITY}),
        frozenset({"candles", "term_structure"}),
        "basis de futuros y estructura temporal (contango/backwardation, roll yield)",
        ("`term_structure` = precios por vencimiento a `asof`; el continuo, con empalme "
         "declarado",)),
    SiblingContract(
        "options_iv", "T100", frozenset({A.OPTION, A.CRYPTO, A.EQUITY, A.INDEX}),
        frozenset({"option_chain"}),
        "volatilidad implícita, sesgo y estructura de plazos de la cadena de opciones",
        ("`option_chain` (DataCapability.OPTION_CHAIN); DVOL de T164 como precedente",)),
    SiblingContract(
        "fx_carry", "T98", frozenset({A.FX}), frozenset({"candles", "rates"}),
        "carry de divisas: diferencial de tipos a corto entre las dos monedas",
        ("`rates` = tipo a corto por moneda (BCE/FRED, ◆ de T88)",)),
)
