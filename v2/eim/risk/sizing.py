"""Tamaño por riesgo fijo con tope de apalancamiento y distancia mínima a liquidación."""

from __future__ import annotations

import math
from dataclasses import dataclass

from eim.backtest.perp import liquidation_price
from eim.risk.config import RiskConfig


@dataclass(frozen=True)
class Sizing:
    size: float
    notional: float
    leverage: float
    margin: float
    risk_amount: float
    liquidation_price: float
    notes: tuple[str, ...]


def max_safe_leverage(sl_frac: float, cfg: RiskConfig) -> float:
    """Apalancamiento entero máximo con dist(liquidación) ≥ k·dist(SL) (margen aislado).

    dist_liq = 1/L − mmr ≥ k·sl_frac  ⇒  L ≤ 1 / (k·sl_frac + mmr).
    """
    cap = 1.0 / (cfg.min_liq_sl_ratio * sl_frac + cfg.mmr)
    return float(math.floor(min(cfg.max_leverage, cap) + 1e-9))


def size_position(side: int, entry: float, sl: float, equity: float,
                  cfg: RiskConfig, scale: float = 1.0, why: str = "") -> Sizing | str:
    """Tamaño o motivo (str) de veto. Supone `side`, `entry`, `sl` ya validados.

    `scale` (≤ 1) reduce el riesgo por operación (T44: ventana de evento; `why` = motivo)."""
    sl_dist = abs(entry - sl)
    sl_frac = sl_dist / entry
    lev = max_safe_leverage(sl_frac, cfg)
    if lev < 1:
        return f"SL a {sl_frac:.2%}: ningún apalancamiento ≥1× deja la liquidación a ≥" \
               f"{cfg.min_liq_sl_ratio:.1f}× la distancia del SL"
    notes: list[str] = []
    if scale < 1:
        notes.append(f"tamaño ×{scale:.2f} ({cfg.risk_per_trade * scale:.2%} de riesgo) por "
                     f"{why or 'ventana de evento'}")
    notional = equity * cfg.risk_per_trade * scale / sl_frac
    cap = min(equity * cfg.max_notional_frac, equity * lev)   # margen ≤ capital
    if notional > cap:
        notes.append(f"tamaño recortado por tope de nocional/apalancamiento "
                     f"({notional:,.0f} → {cap:,.0f})")
        notional = cap
    size = notional / entry
    liq = liquidation_price(side, entry, lev, cfg.mmr)
    if (sl - liq) * side <= 0 or abs(entry - liq) < cfg.min_liq_sl_ratio * sl_dist * (1 - 1e-9):
        return f"liquidación {liq:,.2f} demasiado cerca del SL {sl:,.2f}"
    return Sizing(size=size, notional=notional, leverage=lev, margin=notional / lev,
                  risk_amount=size * sl_dist, liquidation_price=liq, notes=tuple(notes))
