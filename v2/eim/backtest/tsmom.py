"""Cartera continua de tendencia lenta con volatilidad objetivo (T163), funciones puras.

Esto **no** es el motor de entradas de `engine.py`: aquí no hay señal, ni stop, ni salida. Hay una
posición que siempre existe y cuyo tamaño cambia cada semana. Es la forma en la que la literatura
mide el momento de series temporales (cartera siempre posicionada, dimensionada por volatilidad,
rotación baja), y la que T139 no probó.

Los costos son los de T25: comisión taker, `perp.slippage_frac` sobre la vela de ejecución y
funding cada 8 h con el signo del motor (`side·qty·precio·tasa`, + = pagado).

Especificación y tramos: `PLAN/notas/T163_potencia.md`. Sin red, sin disco, sin estado global; el
I/O vive en `scripts/t163_tsmom.py`.
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, ConfigDict

from eim.backtest.params import CostParams
from eim.backtest.perp import slippage_frac
from eim.core import Candle

DAY_MS = 86_400_000
# 1970-01-01 fue jueves (lunes = 0 → 3): el día de la semana del día epoch `d` es (d + 3) % 7
_MONDAY_OFFSET = 3


class TsmomParams(BaseModel):
    """Especificación única de T163, declarada antes de cualquier cifra."""

    model_config = ConfigDict(frozen=True)

    lookbacks: tuple[int, ...] = (20, 60, 120)   # días del signo de la tendencia
    vol_window: int = 60                         # días de la σ realizada
    vol_target: float = 0.30                     # volatilidad objetivo anual
    max_leverage: float = 3.0                    # tope de |peso|
    year_days: float = 365.0                     # días por año (cripto opera todos los días)
    rebalance_weekday: int = 0                   # 0 = lunes, en UTC
    initial_equity: float = 10_000.0


def weekday(day: np.ndarray) -> np.ndarray:
    """Día de la semana (lunes = 0) de días epoch UTC."""
    return (np.asarray(day, np.int64) + _MONDAY_OFFSET) % 7


def trend_signal(close: np.ndarray, lookbacks: tuple[int, ...] = (20, 60, 120)) -> np.ndarray:
    """Promedio de los signos de ln(C_d / C_{d−L}) en los `lookbacks`; nan antes del calentamiento.

    `close` son cierres diarios consecutivos. El valor del día `d` solo usa cierres ≤ `d`.
    """
    c = np.asarray(close, float)
    out = np.zeros(len(c))
    for lb in lookbacks:
        s = np.full(len(c), np.nan)
        if len(c) > lb:
            s[lb:] = np.sign(np.log(c[lb:] / c[:-lb]))
        out = out + s
    return out / len(lookbacks)


def realized_vol(ret: np.ndarray, window: int = 60, year_days: float = 365.0) -> np.ndarray:
    """σ anualizada de los últimos `window` retornos diarios (solo días ≤ d); nan si no llega."""
    r = np.asarray(ret, float)
    out = np.full(len(r), np.nan)
    for i in range(len(r)):
        lo = i - window + 1
        if lo < 0:
            continue
        w = r[lo:i + 1]
        if np.all(np.isfinite(w)):
            out[i] = float(np.std(w, ddof=1)) * np.sqrt(year_days)
    return out


def target_weight(signal: np.ndarray, vol: np.ndarray, p: TsmomParams) -> np.ndarray:
    """Peso objetivo w = recorte(señal · σ_objetivo/σ̂, ±tope); nan si falta señal o σ̂."""
    s, v = np.asarray(signal, float), np.asarray(vol, float)
    ok = np.isfinite(s) & np.isfinite(v) & (v > 0)
    w = np.full(len(s), np.nan)
    w[ok] = np.clip(s[ok] * p.vol_target / v[ok], -p.max_leverage, p.max_leverage)
    return w


def buy_and_hold_weight(w: np.ndarray) -> np.ndarray:
    """Comprar y mantener: peso 1 en los mismos días en que la cartera tiene peso definido."""
    out = np.where(np.isfinite(np.asarray(w, float)), 1.0, np.nan)
    return out


def no_vol_target_weight(signal: np.ndarray, vol: np.ndarray) -> np.ndarray:
    """La misma señal **sin** volatilidad objetivo: w = señal (|w| ≤ 1), con el mismo calendario."""
    s, v = np.asarray(signal, float), np.asarray(vol, float)
    return np.where(np.isfinite(s) & np.isfinite(v) & (v > 0), s, np.nan)


def _fund_by_day(day: np.ndarray, f_t: np.ndarray) -> list[np.ndarray]:
    """Índices de los puntos de funding que caen dentro de cada día."""
    d = np.asarray(day, np.int64)
    lo = np.searchsorted(f_t, d * DAY_MS)
    hi = np.searchsorted(f_t, (d + 1) * DAY_MS)
    return [np.arange(a, b) for a, b in zip(lo, hi, strict=True)]


def run_portfolio(day: np.ndarray, open_: np.ndarray, close: np.ndarray, w: np.ndarray,
                  exec_bar: list[Candle | None], funding: np.ndarray, fund_price: np.ndarray,
                  p: TsmomParams | None = None, cp: CostParams | None = None,
                  start: int = 0) -> dict:
    """Simula la cartera continua día a día desde el índice `start`.

    Convención, sin mirar al futuro: el peso `w[d−1]` (cierre del día anterior) se ejecuta a la
    **apertura** del día `d` cuando `d` es día de rebalanceo; entre rebalanceos la **cantidad** en
    BTC se mantiene fija, así que la exposición deriva con el precio. El P&L del día `d` es
    `qty_{d−1}·(O_d − C_{d−1}) + qty_d·(C_d − O_d)`.

    `exec_bar[d]` es la vela de 1 h de la hora de ejecución (00:00 UTC) para el deslizamiento;
    `funding` es (n, 2) con (t_ms, tasa) y `fund_price` el precio en cada punto.

    Devuelve el capital, el retorno diario neto y el desglose de costos.
    """
    p, cp = p or TsmomParams(), cp or CostParams()
    d = np.asarray(day, np.int64)
    o, c, wt = (np.asarray(x, float) for x in (open_, close, w))
    f_t = np.asarray(funding[:, 0], np.int64) if len(funding) else np.zeros(0, np.int64)
    f_r = np.asarray(funding[:, 1], float) if len(funding) else np.zeros(0)
    idx = _fund_by_day(d, f_t)
    is_reb = weekday(d) == p.rebalance_weekday

    n = len(d)
    equity = np.full(n, np.nan)
    ret = np.full(n, np.nan)
    qty = np.zeros(n)
    traded = np.zeros(n)        # nocional negociado
    fees = np.zeros(n)
    slip = np.zeros(n)
    fund = np.zeros(n)
    eq, held, ruined = p.initial_equity, 0.0, False
    for i in range(start, n):
        prev_eq = eq
        if i > start:
            eq += held * (o[i] - c[i - 1])             # del cierre anterior a la apertura
        target = held
        if (i == start or is_reb[i]) and np.isfinite(wt[i - 1] if i > 0 else np.nan):
            target = wt[i - 1] * eq / o[i]
        dq = target - held
        if dq != 0.0 and o[i] > 0:
            notional = abs(dq) * o[i]
            bar = exec_bar[i]
            frac = slippage_frac(bar, notional, cp) if bar is not None else cp.slip_base_bps / 1e4
            fees[i] = notional * cp.taker_fee
            slip[i] = notional * frac
            traded[i] = notional
            eq -= fees[i] + slip[i]
            held = target
        qty[i] = held
        eq += held * (c[i] - o[i])                              # resto del día
        for k in idx[i]:
            fund[i] += held * fund_price[k] * f_r[k]
        eq -= fund[i]
        if eq <= abs(held) * c[i] * cp.mmr:                     # margen de mantenimiento agotado
            ruined = True
            eq, held = max(eq, 0.0), 0.0
        equity[i] = eq
        if i > start and prev_eq > 0:
            ret[i] = eq / prev_eq - 1.0
        if ruined:
            break
    return {"day": d, "equity": equity, "ret": ret, "qty": qty, "traded": traded,
            "fees": fees, "slip": slip, "funding": fund, "weight": wt, "ruined": ruined,
            "rebalance": is_reb}
