"""Piezas comunes del modelo de costos por clase (T92): tipo de contrato, deslizamiento,
margen y la regla «cada parámetro con su fuente o marcado supuesto».

Por qué existe: hasta T92 `CostParams` **era** un perpetuo lineal (comisión sobre nocional,
funding cada 8 h, margen aislado). Una acción, un par de divisas o un futuro tradicional se
cobran de otra forma y deciden si una «oportunidad» sobrevive a los costos. Cada clase tiene
ahora su modelo (`equity.py`, `fx.py`, `futures.py`) y el perpetuo de siempre queda envuelto
sin cambios (`perpetual.py`).

Contrato común (lo que el motor por instrumento usa, ver `eim/backtest/class_engine.py`):
todo importe sale en la **moneda de cotización** del instrumento y el motor lo convierte a la
de la cuenta. `+` es siempre un costo pagado.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import ClassVar, NamedTuple

from pydantic import BaseModel, ConfigDict, Field

from eim.core import Candle

DAY_MS = 86_400_000
SUPUESTO = "supuesto"


class ContractKind(StrEnum):
    """Cómo se cobra el contrato (no qué subyacente tiene: un perpetuo de Binance sobre una
    acción es un perpetuo, con funding y liquidación, aunque su clase sea `equity`)."""

    PERPETUAL = "perpetual"
    EQUITY = "equity"          # acción o ETF al contado
    FX = "fx"                  # divisa al contado (o CFD sobre ella)
    FUTURE = "future"          # futuro con vencimiento


class NotTradable(ValueError):
    """El instrumento no se negocia como tal (un índice se calcula) o su clase queda fuera de
    T92 (opciones, bonos: T100)."""


class MarginReq(NamedTuple):
    """Margen inicial y de mantenimiento, en moneda de cotización."""

    initial: float
    maintenance: float


class Sourced(BaseModel):
    """Base de los modelos: inmutable, versionado y con la fuente de cada parámetro.

    `SOURCES` asigna a cada campo su procedencia; los que empiezan por «supuesto» son valores
    razonables sin verificar en la fuente (regla de CLAUDE.md: nunca presentar un supuesto
    como real). Una prueba exige que ningún campo quede sin entrada.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    SOURCES: ClassVar[dict[str, str]] = {}

    def assumptions(self) -> dict[str, str]:
        """Campos marcados «supuesto», con su explicación (para el informe)."""
        out: dict[str, str] = {}
        for name, value in self:
            if isinstance(value, Sourced):
                out.update({f"{name}.{k}": v for k, v in value.assumptions().items()})
            elif self.SOURCES.get(name, "").startswith(SUPUESTO):
                out[name] = self.SOURCES[name]
        return out

    def fingerprint(self) -> str:
        """Huella del modelo (versión + valores): va en cada informe."""
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()[:16]


class SlippageParams(Sourced):
    """Deslizamiento como en T25: medio diferencial + k·rango relativo de la vela + k·tamaño
    frente a lo negociado en la vela. Sin volumen real (FX, ticks) se usa `liquidity_notional`.
    """

    spread_bps: float = Field(ge=0)                 # diferencial completo; se paga la mitad
    vol_k: float = Field(default=0.10, ge=0)
    impact_k: float = Field(default=5.0, ge=0)
    cap_bps: float = Field(default=100.0, gt=0)
    liquidity_notional: float = Field(default=1e8, gt=0)

    SOURCES: ClassVar[dict[str, str]] = {
        "spread_bps": "supuesto: diferencial típico de un instrumento líquido de la clase; "
                      "sustituir por el medido (T97/T98/T99)",
        "vol_k": "T25: mismo coeficiente de volatilidad que el perpetuo (supuesto conservador "
                 "fuera de cripto)",
        "impact_k": "T25: mismo coeficiente de impacto que el perpetuo",
        "cap_bps": "T25: tope de seguridad",
        "liquidity_notional": "supuesto: nocional negociado por vela cuando la fuente no "
                              "declara volumen real (FX, índices)",
    }


def slippage(sp: SlippageParams, c: Candle, notional: float, traded: float | None,
             spread_bps: float | None = None) -> float:
    """Deslizamiento relativo de un llenado a mercado en la vela `c` (siempre perjudica).

    `traded` = nocional negociado en la vela; None o ≤ 0 = sin volumen real → la liquidez
    supuesta del modelo. `spread_bps` sustituye al del modelo (FX por sesión, futuros por tick).
    """
    rng = (c.h - c.l) / c.o if c.o > 0 else 0.0
    liq = traded if traded is not None and traded > 0 else sp.liquidity_notional
    half = (sp.spread_bps if spread_bps is None else spread_bps) / 2
    frac = half / 1e4 + sp.vol_k * rng + sp.impact_k * (notional / liq) / 1e4
    return min(max(frac, 0.0), sp.cap_bps / 1e4)
