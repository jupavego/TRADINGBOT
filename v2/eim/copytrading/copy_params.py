"""Parámetros de la copia simulada (T42) y mínimos del exchange. Nada mágico en la lógica.

Una subcuenta virtual por líder (saldo propio, `Mode.SIMULADO`). La proporción de capital se
fija al abrir cada viaje del líder: saldo asignado / valor de la cuenta del líder. Costos de
perpetuos con el modelo de T25 (`CostParams`) a la tarifa base de Hyperliquid, donde opera
el líder y de donde salen los precios grabados del seguidor (T41).
"""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict

from eim.backtest.params import CostParams
from eim.core.market import Frozen

# Hyperliquid, nivel base (2026-10): tomador 4,5 pb, creador 1,5 pb; funding cada hora.
HL_COSTS = CostParams(taker_fee=0.00045, maker_fee=0.00015, funding_interval_ms=3_600_000)
HL_MIN_NOTIONAL = 10.0  # valor mínimo de una orden (USDC), documentación de Hyperliquid


class ExchangeSpec(Frozen):
    """Mínimos por moneda: paso de cantidad (`szDecimals` de `meta`) y valor mínimo."""

    venue: str = "hyperliquid"
    sz_decimals: dict[str, int] = {}
    min_notional: float = HL_MIN_NOTIONAL
    source: str = "supuesto"

    @classmethod
    def from_meta(cls, meta: dict, source: str = "hyperliquid:info.meta") -> ExchangeSpec:
        dec = {str(u["name"]): int(u["szDecimals"]) for u in meta.get("universe") or []
               if "name" in u and "szDecimals" in u}
        return cls(sz_decimals=dec, source=source)

    def step(self, coin: str) -> float | None:
        d = self.sz_decimals.get(coin)
        return None if d is None else 10.0 ** -d

    def round_down(self, coin: str, qty: float) -> float:
        """Cantidad ≥ 0 redondeada hacia cero al paso de la moneda (0 si no hay paso)."""
        d = self.sz_decimals.get(coin)
        if d is None or qty <= 0:
            return 0.0
        k = 10 ** d
        return math.floor(qty * k + 1e-9) / k


class CopyParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    # --- Subcuenta y proporción ---------------------------------------------------------------
    initial_equity: float = 10_000.0  # saldo virtual por líder (USDC)
    alloc_frac: float = 1.0  # parte del saldo asignada al líder (el asignador es T46)
    copy_existing: bool = False  # copiar posiciones abiertas antes de seguirlo (decisión explícita)

    # --- Topes (fracción del capital de la subcuenta) -----------------------------------------
    max_asset_frac: float = 0.4  # nocional por moneda ≤ capital × esto
    max_leader_frac: float = 1.5  # nocional total copiado del líder ≤ capital × esto
    max_slippage: float = 0.005  # no abrir/aumentar > 0,5 % peor que la entrada del líder

    # --- Protección (la exige el motor de riesgo: el líder no declara stop) -------------------
    stop_frac: float = 0.05  # stop de protección a 5 % de la entrada media propia

    # --- Ejecución y costos -------------------------------------------------------------------
    exec_delay_ms: int = 300  # la orden llega 300 ms después de ver la ejecución del líder (T41)
    half_spread: float = 0.0002  # sin libro (`allMids`, marca): medio diferencial supuesto
    quote_timeout_ms: int = 15_000  # cotización más vieja que esto no vale
    pending_timeout_ms: int = 5_000  # señal en vivo sin cotización: se ejecuta a la marca actual
    close_below_min: bool = True  # el cierre total (reduce-only) no exige el mínimo (supuesto)
    costs: CostParams = HL_COSTS

    # --- Riesgo (motor T29, carril propio) ----------------------------------------------------
    risk_version: str = "risk_copy_v1"
    risk_bar_ms: int = 60_000  # «vela» del carril: vigencia de señal y frescura del flujo

    # --- Reconciliación -----------------------------------------------------------------------
    recon_tol_frac: float = 0.02  # diferencia tolerada además de un paso y del mínimo
    recon_confirm: int = 2  # comprobaciones seguidas antes de declarar divergencia
    recon_gap_ms: int = 300_000  # sin confirmar el flujo más que esto = hueco de captura conocido

    @property
    def taker_fee(self) -> float:
        return self.costs.taker_fee

    def summary(self) -> dict[str, float | int | bool | str]:
        keys = ("initial_equity", "alloc_frac", "copy_existing", "max_asset_frac",
                "max_leader_frac", "max_slippage", "stop_frac", "exec_delay_ms", "half_spread",
                "risk_version", "recon_tol_frac", "recon_confirm")
        return {k: getattr(self, k) for k in keys} | {"taker_fee": self.taker_fee}
