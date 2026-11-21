"""Motor de la forja (T208): de una señal a operaciones, con las normas del usuario y los costos.

Normas (§5 de `PLAN/notas/T208_forja_5m.md`): cuenta de 10 000 $ **sin interés compuesto** (el
tamaño se calcula siempre sobre 10 000, nunca sobre el capital corriente), riesgo del 1 % por
operación (R = 100 $), apalancamiento máximo 1:10 (nocional ≤ 100 000 $; si el stop es tan estrecho
que lo pasaría, se recorta el tamaño y la operación arriesga **menos** del 1 %), entrada a mercado
en la apertura de la **vela siguiente** a la señal y cierre forzoso al cierre de la sesión.

Costos: la tarifa única del proyecto (`eim/core/fees.py`: taker 5 pb, maker 2 pb) y el
deslizamiento de `CostParams` (entrada a mercado 0,1 pb, calibrado con el libro real; salidas a
mercado 1 pb + volatilidad + impacto). Dentro de una vela, si caben stop y objetivo, **se asume el
stop primero**; un hueco más allá del nivel se ejecuta a la apertura, nunca a un precio mejor.

Todo es vectorizado: las barreras se buscan en una ventana de hasta `HMAX` velas por candidata.
`tests/forge/test_motor.py` lo compara con un bucle lento de referencia, operación por operación.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from eim.backtest.params import CostParams
from eim.forge.data import Series
from eim.forge.session import Sessions
from eim.forge.space import Exit

HMAX = 80            # velas de 5 m que puede durar una posición (una sesión son 78)
BIG = HMAX + 1
EXIT_KINDS = ("stop", "objetivo", "senal", "cierre")


@dataclass(frozen=True)
class Rules:
    """Las normas de la cuenta. Cambiarlas es otra familia."""

    equity: float = 10_000.0
    risk_frac: float = 0.01
    max_leverage: float = 10.0
    costs: CostParams = CostParams()

    @property
    def r_dollar(self) -> float:
        return self.equity * self.risk_frac

    @property
    def max_notional(self) -> float:
        return self.equity * self.max_leverage


@dataclass
class Trades:
    """Operaciones de una receta: día de sesión, R neto, costo en R, motivo y velas de la vida."""

    day: np.ndarray
    r: np.ndarray
    cost_r: np.ndarray
    kind: np.ndarray
    entry: np.ndarray
    exit: np.ndarray
    capped: int = 0

    def __len__(self) -> int:
        return len(self.r)

    @staticmethod
    def empty() -> Trades:
        z = np.empty(0)
        return Trades(np.empty(0, np.int32), z, z.copy(), np.empty(0, np.int8),
                      np.empty(0, np.int64), np.empty(0, np.int64))


class Market:
    """Ventanas de la serie precalculadas una sola vez (vistas, sin copiar la serie)."""

    def __init__(self, s: Series, ss: Sessions, atr: np.ndarray, vwap: np.ndarray) -> None:
        self.n = len(s)
        self.ss, self.atr, self.vwap = ss, atr, vwap
        pad = np.full(HMAX, np.nan)
        self.o, self.h, self.l, self.c, self.v = s.o, s.h, s.l, s.c, s.v
        self.wo = sliding_window_view(np.r_[s.o, pad], HMAX)
        self.wh = sliding_window_view(np.r_[s.h, pad], HMAX)
        self.wl = sliding_window_view(np.r_[s.l, pad], HMAX)
        self.wc = sliding_window_view(np.r_[s.c, pad], HMAX)
        self.wv = sliding_window_view(np.r_[s.v, pad], HMAX)
        self.cum_fund = np.r_[0.0, np.cumsum(s.funding)]

    def windows(self, e: np.ndarray) -> dict[str, np.ndarray]:
        return {k: getattr(self, f"w{k}")[e].astype(float) for k in "ohlcv"}


def _first(mask: np.ndarray) -> np.ndarray:
    """Primera columna verdadera de cada fila (BIG si ninguna)."""
    any_ = mask.any(axis=1)
    return np.where(any_, mask.argmax(axis=1), BIG)


def simulate(mk: Market, sig: np.ndarray, ex: Exit, rules: Rules,
             cost_mult: float = 1.0, flip: np.ndarray | None = None) -> Trades:
    """Operaciones de una señal con una salida, sin solapamiento (una posición a la vez).

    `flip` es la serie que usa la salida por giro: el disparador **crudo**, sin la dirección ni el
    filtro de entrada (si no, en `largo` o `corto` nunca habría señal contraria que mirar).
    """
    idx = np.flatnonzero(sig)
    idx = idx[idx + 1 < mk.n]            # la última vela no puede señalar: no hay vela siguiente
    if not len(idx):
        return Trades.empty()
    e = idx + 1                                    # entrada: la vela SIGUIENTE a la señal
    side = sig[idx].astype(float)
    atr = mk.atr[idx]                              # ATR de la vela de la señal (causal)
    d = ex.atr_k * atr
    p_raw = mk.o[e]
    ok = np.isfinite(d) & (d > 0) & np.isfinite(p_raw) & (mk.ss.last[e] > e)
    if not ok.any():
        return Trades.empty()
    idx, e, side, d, p_raw = idx[ok], e[ok], side[ok], d[ok], p_raw[ok]
    cp = rules.costs
    slip_in = cost_mult * cp.slip_entry_base_bps / 1e4
    p_e = p_raw * (1 + side * slip_in)
    q = np.minimum(rules.r_dollar / d, rules.max_notional / p_e)
    capped = int(np.sum(rules.r_dollar / d > rules.max_notional / p_e))

    hz = np.minimum(mk.ss.last[e] - e, HMAX - 1).astype(np.int64)
    if ex.bars is not None:
        hz = np.minimum(hz, ex.bars)
    w = mk.windows(e)
    cols = np.arange(HMAX)[None, :]
    valid = cols <= hz[:, None]
    sd = side[:, None]
    fav = np.where(sd > 0, w["h"], w["l"])         # extremo a favor de la vela
    adv = np.where(sd > 0, w["l"], w["h"])         # extremo en contra

    sl0 = p_e - side * d
    if ex.kind == "trailing":
        run = np.maximum.accumulate(np.where(np.isnan(fav), -np.inf, sd * fav), axis=1)
        lvl = sd * (run - d[:, None])
        lvl = np.c_[sl0[:, None], lvl[:, :-1]]     # el nivel nuevo rige desde la vela siguiente
    else:
        lvl = np.broadcast_to(sl0[:, None], (len(e), HMAX))
    j_adv = _first((sd * (adv - lvl) <= 0) & valid)

    j_fav = np.full(len(e), BIG)
    tp = np.full(len(e), np.nan)
    if ex.kind == "objetivo":
        tp = p_e + side * (ex.tp_r or 0.0) * d
        j_fav = _first((sd * (fav - tp[:, None]) >= 0) & valid)
    elif ex.kind == "nivel":                       # objetivo = VWAP de sesión en la señal
        tp = mk.vwap[idx]
        good = np.isfinite(tp) & (side * (tp - p_e) > 0)
        j_fav = np.where(good, _first((sd * (fav - tp[:, None]) >= 0) & valid), BIG)

    j_oth = np.full(len(e), BIG)
    if ex.kind == "giro":
        fsig = sig if flip is None else flip
        ws = sliding_window_view(np.r_[fsig, np.zeros(HMAX, np.int8)], HMAX)[e]
        j_oth = _first((ws == -side[:, None].astype(np.int8)) & valid)

    j = np.minimum(np.minimum(j_adv, j_fav), np.minimum(j_oth, hz))
    is_adv = j_adv == j
    is_fav = (~is_adv) & (j_fav == j)
    is_oth = (~is_adv) & (~is_fav) & (j_oth == j)
    rows = np.arange(len(e))
    px_o, px_c = w["o"][rows, j], w["c"][rows, j]
    lvl_j = lvl[rows, j]
    # stop: el nivel, o la apertura si la vela abrió más allá (hueco). Objetivo: el nivel (límite).
    px = np.where(is_adv, np.where(side * (px_o - lvl_j) <= 0, px_o, lvl_j),
                  np.where(is_fav, tp, px_c))
    # deslizamiento: solo en las salidas a mercado (stop, señal, cierre); el objetivo es límite
    rng = np.where(w["o"][rows, j] > 0, (w["h"][rows, j] - w["l"][rows, j]) / w["o"][rows, j], 0.0)
    traded = w["v"][rows, j] * w["o"][rows, j]
    impact = np.where(traded > 0, q * p_e / np.maximum(traded, 1e-9), 1.0)
    slip_out = np.clip(cp.slip_base_bps / 1e4 + cp.slip_vol_k * rng
                       + cp.slip_impact_k * impact / 1e4, 0.0, cp.slip_cap_bps / 1e4) * cost_mult
    slip_out = np.where(is_fav, 0.0, slip_out)
    px_fill = px * (1 - side * slip_out)

    fee_rate = np.where(is_fav, cp.maker_fee, cp.taker_fee) * cost_mult
    fee = (cp.taker_fee * cost_mult * q * p_e) + fee_rate * q * np.abs(px_fill)
    fund = side * (mk.cum_fund[e + j + 1] - mk.cum_fund[e]) * q * p_e
    slip_cost = q * (np.abs(p_e - p_raw) + np.abs(px_fill - px))
    pnl = side * (px_fill - p_e) * q - fee - fund
    r = pnl / rules.r_dollar
    cost_r = (fee + slip_cost + np.maximum(fund, 0.0)) / rules.r_dollar
    kind = np.where(is_adv, 0, np.where(is_fav, 1, np.where(is_oth, 2, 3))).astype(np.int8)

    keep = _no_overlap(e, j)
    day = mk.ss.day[e[keep]].astype(np.int32)
    return Trades(day, r[keep], cost_r[keep], kind[keep], e[keep], e[keep] + j[keep], capped)


def _no_overlap(e: np.ndarray, j: np.ndarray) -> np.ndarray:
    """Índices de las operaciones que de verdad se harían: una posición a la vez, en orden."""
    out: list[int] = []
    k, n = 0, len(e)
    while k < n:
        out.append(k)
        k = int(np.searchsorted(e, e[k] + j[k] + 1, "left"))
    return np.asarray(out, dtype=np.int64)
