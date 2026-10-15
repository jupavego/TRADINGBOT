"""Estrategias de agentes individuales e indicadores técnicos (catálogo T34).

Los indicadores se calculan una vez sobre toda la serie de 1 h (son causales: el valor en `i`
solo usa velas ≤ `i`) y cada estrategia mira el índice de la última vela cerrada del contexto.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from eim.core import Candle
from eim.indicators._core import rolling_max, rolling_min, shift
from eim.indicators.momentum import macd, rsi
from eim.indicators.registry import candle_arrays
from eim.indicators.trend import dmi, ema_lines, supertrend
from eim.indicators.volatility import boll
from eim.paper.ideas import Draft, StrategyInfo, atr_draft, finite, sign

AGENT_BIAS = 0.3
AGENT_CONF = 0.2
DONCHIAN_N = 20
ADX_MIN = 25.0


class Ind:
    """Indicadores precalculados de la serie de decisión."""

    def __init__(self, candles: Sequence[Candle]) -> None:
        a = candle_arrays(candles)
        self.t = a["t"]
        c, h, lo = a["close"], a["high"], a["low"]
        self.c, self.h, self.l = c, h, lo
        n = len(c)
        nan = np.full(n, np.nan)
        e = ema_lines(c, (7, 25, 99)) if n else {"ema7": nan, "ema25": nan, "ema99": nan}
        self.ema7, self.ema25, self.ema99 = e["ema7"], e["ema25"], e["ema99"]
        self.rsi = rsi(c, 14) if n > 15 else nan
        b = boll(c, 20, 2.0) if n > 20 else {"up": nan, "mb": nan, "dn": nan}
        self.bb_up, self.bb_mb, self.bb_dn = b["up"], b["mb"], b["dn"]
        self.hist = macd(c)["hist"] if n else nan
        st = supertrend(h, lo, c) if n > 11 else {"st": nan, "dir": nan}
        self.st, self.st_dir = st["st"], st["dir"]
        d = dmi(h, lo, c) if n > 30 else {"pdi": nan, "mdi": nan, "adx": nan}
        self.pdi, self.mdi, self.adx = d["pdi"], d["mdi"], d["adx"]
        self.dc_hi = shift(rolling_max(h, DONCHIAN_N), 1) if n > DONCHIAN_N else nan
        self.dc_lo = shift(rolling_min(lo, DONCHIAN_N), 1) if n > DONCHIAN_N else nan

    def index(self, t_last: int) -> int:
        """Índice de la vela que abrió en `t_last` (−1 si no está)."""
        i = int(np.searchsorted(self.t, t_last))
        return i if i < len(self.t) and self.t[i] == t_last else -1


def _cross(a: np.ndarray, b: np.ndarray, i: int) -> int:
    """+1 si `a` cruza `b` hacia arriba en `i`, −1 hacia abajo, 0 si no."""
    if i < 1 or not finite(a[i], b[i], a[i - 1], b[i - 1]):
        return 0
    if a[i - 1] <= b[i - 1] and a[i] > b[i]:
        return 1
    if a[i - 1] >= b[i - 1] and a[i] < b[i]:
        return -1
    return 0


def _agent(aid: str):
    def fn(ctx: dict, _x: object, _i: int) -> Draft | None:
        row = (ctx.get("agents") or {}).get(aid)
        if not row or row[2] != "ok" or abs(row[0]) < AGENT_BIAS or row[1] < AGENT_CONF:
            return None
        return atr_draft(sign(row[0]), ctx, 1.5, 2.5, row[1],
                         (f"Agente {aid}: sesgo {row[0]:+.2f}, confianza {row[1]:.0%}",))
    return fn


def ema_cross(ctx: dict, x: Ind, i: int) -> Draft | None:
    side = _cross(x.ema7, x.ema25, i)
    if not side or not finite(x.ema99[i]) or (x.c[i] - x.ema99[i]) * side <= 0:
        return None
    return atr_draft(side, ctx, 1.5, 3.0, 0.5, ("EMA 7 cruza la EMA 25 a favor de la EMA 99",),
                     hold_h=48)


def rsi_reversion(ctx: dict, x: Ind, i: int) -> Draft | None:
    if i < 1 or not finite(x.rsi[i], x.rsi[i - 1]):
        return None
    side = 1 if x.rsi[i - 1] < 30 <= x.rsi[i] else -1 if x.rsi[i - 1] > 70 >= x.rsi[i] else 0
    return atr_draft(side, ctx, 1.2, 1.8, 0.4,
                     (f"RSI 14 sale de {'sobreventa' if side > 0 else 'sobrecompra'} "
                      f"({x.rsi[i]:.0f})",)) if side else None


def bb_breakout(ctx: dict, x: Ind, i: int) -> Draft | None:
    up, dn = _cross(x.c, x.bb_up, i), _cross(x.c, x.bb_dn, i)
    side = 1 if up > 0 else -1 if dn < 0 else 0
    return atr_draft(side, ctx, 1.5, 2.5, 0.4,
                     ("Cierre fuera de la banda de Bollinger (20, 2): ruptura",)) if side else None


def bb_reversion(ctx: dict, x: Ind, i: int) -> Draft | None:
    """Vuelve dentro de la banda: TP en la media, SL tras el extremo de las 2 últimas velas."""
    side = 1 if _cross(x.c, x.bb_dn, i) > 0 else -1 if _cross(x.c, x.bb_up, i) < 0 else 0
    if not side or not finite(x.bb_mb[i], ctx.get("atr")):
        return None
    ext = min(x.l[i - 1], x.l[i]) if side > 0 else max(x.h[i - 1], x.h[i])
    sl = ext - side * 0.25 * ctx["atr"]
    return Draft(side=side, sl=sl, tp=float(x.bb_mb[i]), conf=0.4, entry=ctx["close"],
                 why=("Cierre de vuelta dentro de la banda de Bollinger: reversión a la media",))


def donchian(ctx: dict, x: Ind, i: int) -> Draft | None:
    if not finite(x.dc_hi[i], x.dc_lo[i]):
        return None
    side = 1 if x.c[i] > x.dc_hi[i] else -1 if x.c[i] < x.dc_lo[i] else 0
    return atr_draft(side, ctx, 2.0, 4.0, 0.4,
                     (f"Ruptura del canal de Donchian de {DONCHIAN_N} velas",),
                     hold_h=72) if side else None


def macd_trend(ctx: dict, x: Ind, i: int) -> Draft | None:
    if i < 1 or not finite(x.hist[i], x.hist[i - 1], x.ema99[i]):
        return None
    side = 1 if x.hist[i - 1] <= 0 < x.hist[i] else -1 if x.hist[i - 1] >= 0 > x.hist[i] else 0
    if not side or (x.c[i] - x.ema99[i]) * side <= 0:
        return None
    return atr_draft(side, ctx, 1.5, 2.5, 0.45,
                     ("Histograma MACD cambia de signo a favor de la EMA 99",), hold_h=36)


def supertrend_flip(ctx: dict, x: Ind, i: int) -> Draft | None:
    if i < 1 or not finite(x.st_dir[i], x.st_dir[i - 1], x.st[i], ctx.get("atr")):
        return None
    if x.st_dir[i] == x.st_dir[i - 1]:
        return None
    side, c, a = int(x.st_dir[i]), ctx["close"], ctx["atr"]
    risk = (c - x.st[i]) * side
    sl = float(x.st[i]) if 0.5 * a <= risk <= 3 * a else c - side * 1.5 * a
    return Draft(side=side, sl=sl, tp=c + side * 2 * abs(c - sl), conf=0.45, entry=c,
                 hold_h=48, why=("SuperTrend (10, 3) cambia de dirección; SL en su línea, TP 2 R",))


def adx_trend(ctx: dict, x: Ind, i: int) -> Draft | None:
    side = _cross(x.pdi, x.mdi, i)
    if not side or not finite(x.adx[i]) or x.adx[i] < ADX_MIN:
        return None
    return atr_draft(side, ctx, 1.5, 3.0, min(1.0, x.adx[i] / 50),
                     (f"+DI/−DI se cruzan con ADX {x.adx[i]:.0f} (tendencia)",), hold_h=48)


_AGENTS = (("structure", "Estructura"), ("levels", "Niveles S/R"),
           ("price_action", "Price action"), ("vwap", "VWAP"), ("ema", "EMAs (FRM)"),
           ("elliott", "Elliott"), ("technical", "Técnico multi-marco"),
           ("derivatives", "Derivados"))

IND: tuple[StrategyInfo, ...] = tuple(
    StrategyInfo(f"agente_{aid}", f"Agente {name}", "agentes",
                 f"Sigue al agente {aid} solo si |sesgo| ≥ {AGENT_BIAS} y confianza ≥ "
                 f"{AGENT_CONF:.0%}; SL 1,5 ATR, TP 2,5 ATR.", _agent(aid))
    for aid, name in _AGENTS) + (
    StrategyInfo("ind_cruce_ema", "Cruce de EMAs", "indicadores",
                 "EMA 7 cruza EMA 25 a favor de la EMA 99; SL 1,5 ATR, TP 3 ATR.", ema_cross),
    StrategyInfo("ind_rsi", "Reversión RSI", "indicadores",
                 "RSI 14 sale de < 30 o > 70; SL 1,2 ATR, TP 1,8 ATR.", rsi_reversion),
    StrategyInfo("ind_bb_ruptura", "Ruptura Bollinger", "indicadores",
                 "El cierre sale de la banda (20, 2): sigue el movimiento.", bb_breakout),
    StrategyInfo("ind_bb_reversion", "Reversión Bollinger", "indicadores",
                 "El cierre vuelve dentro de la banda: TP en la media.", bb_reversion),
    StrategyInfo("ind_donchian", "Ruptura Donchian", "indicadores",
                 f"Cierre fuera del rango de {DONCHIAN_N} velas (tortuga); SL 2 ATR, TP 4 ATR.",
                 donchian),
    StrategyInfo("ind_macd", "MACD con tendencia", "indicadores",
                 "El histograma MACD cambia de signo a favor de la EMA 99.", macd_trend),
    StrategyInfo("ind_supertrend", "Giro SuperTrend", "indicadores",
                 "SuperTrend (10, 3) cambia de dirección; SL en su línea, TP 2 R.",
                 supertrend_flip),
    StrategyInfo("ind_adx", "Tendencia ADX", "indicadores",
                 f"+DI cruza −DI con ADX ≥ {ADX_MIN:.0f}; SL 1,5 ATR, TP 3 ATR.", adx_trend),
)
