"""Parámetros del backtest de perpetuos (costos y mecánica; sin números mágicos en la lógica)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CostParams(BaseModel):
    """Costos de un perpetuo lineal USDT-M. Valores por defecto: tarifa regular de Binance."""

    model_config = ConfigDict(frozen=True)

    taker_fee: float = 0.0005        # 5 pb: entrada a mercado, SL, salida por tiempo
    maker_fee: float = 0.0002        # 2 pb: TP como orden límite
    slip_base_bps: float = 1.0       # deslizamiento mínimo (spread/2)
    slip_vol_k: float = 0.10         # × rango relativo de la vela de ejecución (h−l)/o
    slip_impact_k: float = 5.0       # × (notional / notional negociado en la vela)
    slip_cap_bps: float = 100.0      # tope de seguridad
    # Entradas a mercado del bróker simulado (calibración con el libro real, 2026-10-20: llenar
    # 1,5–150 k USDT en BTCUSDT cuesta ≈ 0,01 pb): deslizamiento propio, sin el término de
    # volatilidad que se conserva en las salidas por SL/BE/tiempo (reports/slippage_calibracion.md)
    slip_entry_base_bps: float = 0.1
    slip_entry_vol_k: float = 0.0
    funding_interval_ms: int = 8 * 3_600_000
    mmr: float = 0.005               # tasa de margen de mantenimiento (tramo bajo)


class BacktestParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    initial_equity: float = 10_000.0
    leverage: float = 5.0            # margen aislado; fija el precio de liquidación
    risk_frac: float = 0.01          # fracción del capital arriesgada hasta el SL
    lookback: int = 500              # velas que ve la estrategia en cada decisión
    eval_step: int = 1               # cada cuántas velas se consulta a la estrategia (plana)
    max_hold_bars: int = 96          # salida a mercado si no toca SL/TP (0 = sin límite)
    bars_per_year: float = 8766.0    # 1 h; ajustar con otros marcos
    costs: CostParams = CostParams()


ZERO_COSTS = CostParams(taker_fee=0.0, maker_fee=0.0, slip_base_bps=0.0, slip_vol_k=0.0,
                        slip_impact_k=0.0, slip_entry_base_bps=0.0, slip_entry_vol_k=0.0)
