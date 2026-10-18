"""Gestión de posiciones de arbitraje abiertas (T45): qué hacer en cada ciclo. Puro.

Reglas, en orden (la primera que aplica gana):
1. Kill-switch activo → cierre urgente de las dos patas.
2. Liquidación: si la liquidación del corto queda a ≤ `close_liq_move` → cierre urgente. Si el
   margen del corto cae a ≤ `rebalance_frac` del objetivo (T43: 50 %) → rebalanceo: primero se
   añade margen libre; si no alcanza, se reducen ambas patas en la fracción `1 − ratio`, que
   devuelve el margen al objetivo (cerrar parte realiza la pérdida de esa parte).
3. Base: cerca del vencimiento (`exit_before_delivery_ms`) → cierre; base actual ≤ costo de
   salida → cierre (convergió: rentabilidad agotada).
4. Tenencia cumplida (`horizon_h`) → cierre.
5. Carry: funding previsto < 0 durante `negative_funding_n` lecturas seguidas → cierre
   (cambió de signo: el corto pasaría a pagar).
"""

from __future__ import annotations

from typing import Literal

from eim.core.market import Frozen
from eim.risk.arb_config import ArbRiskConfig

H_MS = 3_600_000


class PositionView(Frozen):
    strategy: str
    opened_at: int
    horizon_h: float
    delivery_t: int | None = None
    qty: float                      # cantidad cubierta (base)
    leverage: int
    mark: float | None = None       # marca del futuro (testnet)
    margin_equity: float | None = None  # margen aislado + PnL no realizado del corto
    liq_move: float | None = None   # |liquidación − marca| / marca
    basis_bps: float | None = None  # base actual futuro − spot (escáner)
    exit_cost_bps: float = 0.0
    negative_funding_streak: int = 0
    kill_active: bool = False


class Action(Frozen):
    kind: Literal["hold", "rebalance", "close"]
    reason: str
    urgent: bool = False            # cierre que no se deshace si la 2.ª pata falla
    frac: float = 0.0               # rebalanceo: fracción de ambas patas a reducir
    margin_needed: float = 0.0      # rebalanceo: margen a añadir para volver al objetivo


def margin_ratio(v: PositionView) -> float | None:
    """Margen del corto / margen objetivo (`qty × marca / L`)."""
    if v.margin_equity is None or v.mark is None or v.qty <= 0:
        return None
    return v.margin_equity / (v.qty * v.mark / v.leverage)


def settlements_between(t0: int, t1: int, interval_h: float) -> int:
    """Liquidaciones de funding en (t0, t1]: Binance liquida en múltiplos del intervalo (UTC)."""
    step = int(interval_h * H_MS)
    return max(0, t1 // step - t0 // step) if step > 0 else 0


def decide(v: PositionView, cfg: ArbRiskConfig, now: int) -> Action:
    if v.kill_active:
        return Action(kind="close", reason="kill-switch activo", urgent=True)
    if v.liq_move is not None and v.liq_move <= cfg.close_liq_move:
        return Action(kind="close", urgent=True, reason=(
            f"riesgo de liquidación: a {v.liq_move:.1%} (mín. {cfg.close_liq_move:.0%})"))
    r = margin_ratio(v)
    if r is not None and r <= cfg.rebalance_frac:
        target = v.qty * (v.mark or 0.0) / v.leverage
        return Action(kind="rebalance", frac=min(max(1.0 - r, 0.0), 1.0),
                      margin_needed=max(target - (v.margin_equity or 0.0), 0.0),
                      reason=f"margen del corto al {r:.0%} del objetivo "
                             f"(rebalanceo al {cfg.rebalance_frac:.0%})")
    if v.delivery_t is not None and v.delivery_t - now <= cfg.exit_before_delivery_ms:
        return Action(kind="close", reason="vencimiento del trimestral cercano")
    if v.strategy == "basis" and v.basis_bps is not None and v.basis_bps <= v.exit_cost_bps:
        return Action(kind="close", reason=(
            f"base agotada: {v.basis_bps:.1f} pb ≤ costo de salida {v.exit_cost_bps:.1f} pb"))
    if now - v.opened_at >= v.horizon_h * H_MS:
        return Action(kind="close", reason=f"tenencia cumplida ({v.horizon_h:g} h)")
    if v.strategy == "funding_carry" and v.negative_funding_streak >= cfg.negative_funding_n:
        return Action(kind="close", reason=(
            f"funding cambió de signo: negativo en {v.negative_funding_streak} lecturas "
            "seguidas (rentabilidad agotada)"))
    return Action(kind="hold", reason="sin cambios")
