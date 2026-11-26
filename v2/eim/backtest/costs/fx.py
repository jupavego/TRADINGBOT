"""Divisas al contado (T92): diferencial por sesión, swap/rollover y apalancamiento por
regulación configurable.

- Diferencial: depende de la hora (Asia, Londres, solape Londres-Nueva York, Nueva York y la
  hora del rollover, la más cara). Sin volumen real (el FX no lo tiene centralizado), el
  impacto usa la liquidez supuesta del modelo.
- Swap: cada rollover (17:00 de Nueva York) que la posición atraviesa cobra un día de
  diferencial de tipos más el margen del intermediario; el del miércoles cuenta triple
  (liquidación T+2 sobre el fin de semana). El largo paga `tipo_cotizada − tipo_base`.
- Apalancamiento: el máximo de la regulación elegida, distinto para pares mayores y el resto;
  mantenimiento = la regla de cierre al 50 % del margen.

Los tipos de interés por defecto son 0 y están marcados «supuesto»: los reales (BCE, FRED)
son trabajo de T98, que los tendrá como serie y no como constante.
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from typing import ClassVar, Literal

from pydantic import Field

from eim.backtest.costs.base import ContractKind, MarginReq, SlippageParams, Sourced, slippage
from eim.core import Candle

HOUR_MS = 3_600_000
MAJORS = frozenset({"EURUSD", "USDJPY", "GBPUSD", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"})
#: Apalancamiento máximo (mayores, resto) por régimen. ESMA: intervención de producto de 2018
#: sobre CFD a minoristas; NFA: regla de margen de divisas de EE. UU. No verificadas en la
#: fuente en T92: cuando haya intermediario (T103) se fija el suyo.
LEVERAGE_BY_REGULATION: dict[str, tuple[float, float]] = {
    "esma_retail": (30.0, 20.0),
    "nfa": (50.0, 20.0),
    "professional": (100.0, 50.0),
    "none": (1.0, 1.0),
}
_FX_SLIP = SlippageParams(spread_bps=0.8, vol_k=0.05, liquidity_notional=5e8)


def _ny_rollover_utc_hour(day: dt.date) -> int:
    """Hora UTC de las 17:00 de Nueva York ese día (21 en verano, 22 en invierno)."""
    try:
        from zoneinfo import ZoneInfo
        ny = dt.datetime(day.year, day.month, day.day, 17, tzinfo=ZoneInfo("America/New_York"))
        return ny.astimezone(dt.UTC).hour
    except Exception:  # sin base de zonas: el horario de invierno, el más común
        return 22


@lru_cache(maxsize=4096)
def _rollover_ms(day_ordinal: int) -> int:
    day = dt.date.fromordinal(day_ordinal)
    hour = _ny_rollover_utc_hour(day)
    return int(dt.datetime(day.year, day.month, day.day, hour, tzinfo=dt.UTC).timestamp() * 1000)


def rollovers(t0: int, t1: int) -> list[tuple[int, int]]:
    """Rollovers en (t0, t1]: (instante ms UTC, días que cobra). Lunes a viernes; el del
    miércoles cobra 3 días (convención T+2 del contado sobre el fin de semana)."""
    if t1 <= t0:
        return []
    d = dt.datetime.fromtimestamp(t0 / 1000, dt.UTC).date() - dt.timedelta(days=1)
    end = dt.datetime.fromtimestamp(t1 / 1000, dt.UTC).date() + dt.timedelta(days=1)
    out: list[tuple[int, int]] = []
    while d <= end:
        if d.weekday() < 5:
            t = _rollover_ms(d.toordinal())
            if t0 < t <= t1:
                out.append((t, 3 if d.weekday() == 2 else 1))
        d += dt.timedelta(days=1)
    return out


class FxCostModel(Sourced):
    version: str = "fx_v1"
    pair: str = "EURUSD"
    regulation: Literal["esma_retail", "nfa", "professional", "none"] = "esma_retail"
    commission_per_million: float = Field(default=0.0, ge=0)
    slippage: SlippageParams = _FX_SLIP
    spread_bps_by_session: dict[str, float] = Field(default_factory=lambda: {
        "asia": 1.2, "london": 0.6, "overlap": 0.5, "new_york": 0.7, "rollover": 3.0})
    rate_base_annual: float = 0.0
    rate_quote_annual: float = 0.0
    swap_markup_annual: float = Field(default=0.005, ge=0)
    swap_day_count: float = Field(default=365.0, gt=0)
    stop_out_frac: float = Field(default=0.5, gt=0, le=1)

    kind: ClassVar[ContractKind] = ContractKind.FX
    uses_perp_engine: ClassVar[bool] = False
    SOURCES: ClassVar[dict[str, str]] = {
        "version": "T92",
        "pair": "instrumento (para saber si es par mayor)",
        "regulation": "supuesto: régimen minorista europeo (ESMA) hasta elegir intermediario",
        "commission_per_million": "supuesto: cuenta de solo diferencial, sin comisión aparte",
        "slippage": "supuesto: diferencial de referencia e impacto con liquidez supuesta (el FX "
                    "no publica volumen centralizado)",
        "spread_bps_by_session": "supuesto: diferencial de un par mayor por franja (UTC); el "
                                 "rollover es la hora más cara",
        "rate_base_annual": "supuesto: 0; el tipo real de la divisa base viene de T98 (BCE/FRED)",
        "rate_quote_annual": "supuesto: 0; el tipo real de la divisa cotizada viene de T98",
        "swap_markup_annual": "supuesto: margen del intermediario sobre el diferencial (0,5 %)",
        "swap_day_count": "supuesto: base 365",
        "stop_out_frac": "ESMA 2018: cierre cuando el capital cae al 50 % del margen exigido "
                         "(no verificada en la fuente en T92)",
    }

    @property
    def max_leverage(self) -> float:
        major, other = LEVERAGE_BY_REGULATION[self.regulation]
        return major if self.pair.upper() in MAJORS else other

    def session_of(self, t: int) -> str:
        """Franja (UTC) de un instante: decide el diferencial."""
        h = (t // HOUR_MS) % 24
        if h == 21:
            return "rollover"
        if 12 <= h < 16:
            return "overlap"
        if 7 <= h < 12:
            return "london"
        if 16 <= h < 21:
            return "new_york"
        return "asia"

    def commission(self, qty: float, price: float, multiplier: float = 1.0, *,
                   maker: bool = False) -> float:
        return qty * price * multiplier * self.commission_per_million / 1e6

    def slippage_frac(self, c: Candle, notional: float, traded: float | None = None, *,
                      entry: bool = False, tick: float | None = None, t: int | None = None
                      ) -> float:
        spread = self.spread_bps_by_session.get(self.session_of(c.t if t is None else t))
        return slippage(self.slippage, c, notional, None, spread)

    def swap_rate(self, side: int) -> float:
        """Costo anual del swap para el lado (+ = paga): el largo financia la cotizada y
        presta la base; el intermediario cobra su margen a los dos lados."""
        diff = self.rate_quote_annual - self.rate_base_annual
        return (diff if side > 0 else -diff) + self.swap_markup_annual

    def financing(self, side: int, notional: float, t0: int, t1: int) -> float:
        days = sum(n for _, n in rollovers(t0, t1))
        return abs(notional) * self.swap_rate(side) * days / self.swap_day_count

    def margin(self, side: int, notional: float) -> MarginReq:
        initial = notional / self.max_leverage
        return MarginReq(initial, initial * self.stop_out_frac)
