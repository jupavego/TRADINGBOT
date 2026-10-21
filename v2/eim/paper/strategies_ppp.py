"""Entrada propia del perfil PPP (familia `ppp`): continuación de tendencia con confluencia.

La escalera solo gana si el precio sigue en la dirección elegida (sin TP, un SL a favor que sube
tras +10 USDT): sin deriva a favor, su esperanza es −costos. Por eso esta entrada pide que TODO
coincida y se abstiene si algo falta (calidad antes que frecuencia):

1. tendencia del marco mayor a favor (`htf_dir`),
2. síntesis de los agentes en el mismo sentido: |sesgo| ≥ 0,25, confianza ≥ 0,3, acuerdo ≥ 0,5,
3. fuerza de la tendencia: ADX ≥ 25 con +DI/−DI a favor,
4. RSI sin agotamiento (largo 50–72, corto 28–50).

Son confirmaciones de naturaleza distinta (marco mayor, agentes, fuerza y momentum). Se evitó
apilar SuperTrend, EMA y MACD: miden lo mismo que +DI/−DI (tendencia del propio precio) y
contarían como confirmaciones independientes lo que son copias (la primera versión las pedía y
casi nunca se activaba: 5 ideas en 40 días).

SL a 2,2 ATR (más ancho que el ruido de la vela y con un costo relativo ≤ 0,15 R en 1 h/4 h); el
TP a 4 ATR solo ESTIMA si el primer escalón es alcanzable (la salida real la decide la escalera).
Son umbrales fijados a priori, no ajustados a un periodo; su valor se mide con la puerta T49.
"""

from __future__ import annotations

from eim.paper.ideas import Draft, StrategyInfo, atr_draft, finite, sign
from eim.paper.strategies_ind import Ind

SYN_BIAS = 0.25
SYN_CONF = 0.3
SYN_AGREE = 0.5
ADX_MIN = 25.0
RSI_LONG = (50.0, 72.0)
RSI_SHORT = (28.0, 50.0)
SL_ATR = 2.2
TP_ATR = 4.0


def ppp_tendencia(ctx: dict, x: Ind, i: int) -> Draft | None:
    s = ctx.get("syn")
    side = int(ctx.get("htf_dir") or 0)
    if not s or not side or sign(s["bias"]) != side or abs(s["bias"]) < SYN_BIAS:
        return None
    if s["conf"] < SYN_CONF or s["agree"] < SYN_AGREE or i < 1:
        return None
    if not finite(x.adx[i], x.pdi[i], x.mdi[i], x.rsi[i]):
        return None
    if x.adx[i] < ADX_MIN or (x.pdi[i] - x.mdi[i]) * side <= 0:
        return None
    lo, hi = RSI_LONG if side > 0 else RSI_SHORT
    if not lo <= x.rsi[i] <= hi:
        return None
    return atr_draft(side, ctx, SL_ATR, TP_ATR, min(1.0, s["conf"] * 1.5),
                     (f"Tendencia mayor y síntesis {s['bias']:+.2f} a favor",
                      f"ADX {x.adx[i]:.0f} con DI a favor · RSI {x.rsi[i]:.0f}"),
                     key="")


PPP: tuple[StrategyInfo, ...] = (
    StrategyInfo("ppp_tendencia", "PPP: continuación de tendencia", "ppp",
                 "Entrada propia de la escalera: marco mayor, síntesis, ADX/DI y RSI sin "
                 "agotamiento, todo a favor; SL 2,2 ATR (el TP 4 ATR solo estima).",
                 ppp_tendencia, timeframes=("1h", "4h")),
)
