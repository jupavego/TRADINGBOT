"""Mantenimiento de posiciones cubiertas sobre el histórico (T43): margen, funding,
rebalanceo, liquidación y salida. Vela a vela por segmentos con numpy.

- `spot_short`: largo spot + corto futuro (perpetuo o trimestral). El spot está en la
  billetera spot: el futuro corto tiene margen aislado propio. Si su capital cae a
  `rebalance_frac` del objetivo (cierre de vela) se vende spot, se transfiere y se recompra
  futuro (ambas patas bajan: cuesta comisiones y realiza el cambio de base de esa parte).
  Liquidación si el máximo de la vela alcanza el precio de liquidación (antes que el cierre).
- `futures_pair`: dos futuros en margen cruzado (las pérdidas de una pata las cubre la
  otra): sin rebalanceo; liquidación solo si el diferencial agota el margen.
Las comisiones no se descuentan del margen (aproximación: son ≪ margen).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from eim.arbitrage.params import ArbParams
from eim.arbitrage.sim.frame import H_MS, Bars, Funding, bar_of
from eim.arbitrage.sim.params import SimParams
from eim.arbitrage.sim.trade import Executor, LegSpec, SimTrade
from eim.core.arbitrage import MarketKind


@dataclass(frozen=True)
class Side_:
    """Una pata: sus velas, clave de profundidad, mercado y volumen de referencia."""

    bars: Bars
    key: str
    market: MarketKind
    ref_vq: float | None = None
    usd: Bars | None = None  # conversión de la cotizada a USD (USDC-M: USDCUSDT)

    def scale(self, i: int, sp: SimParams) -> float:
        return self.bars.vol_scale(i, self.ref_vq, sp.vol_scale_min)

    def usd_at(self, t: int) -> float:
        if self.usd is None:
            return 1.0
        i = self.usd.at(t)
        i = i if i is not None else self.usd.before(t)
        return float(self.usd.o[i]) if i is not None else 1.0


@lru_cache(maxsize=64)
def _common(a: Bars, b: Bars) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return np.intersect1d(a.t, b.t, assume_unique=True, return_indices=True)


def align(a: Bars, b: Bars, t0: int, t1: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Velas comunes a `a` y `b` con t0 ≤ t < t1: (t, índices en a, índices en b)."""
    ts, ia, ib = _common(a, b)
    i, j = np.searchsorted(ts, t0), np.searchsorted(ts, t1)
    return ts[i:j], ia[i:j], ib[i:j]


def _first(mask: np.ndarray) -> int | None:
    idx = np.flatnonzero(mask)
    return int(idx[0]) if idx.size else None


def _mark(bars: Bars, t_event: int) -> float | None:
    i = bars.at(bar_of(t_event))
    i = i if i is not None else bars.before(t_event)
    return float(bars.o[i]) if i is not None else None


def spot_short(tr: SimTrade, ex: Executor, sp: SimParams, p: ArbParams, spot: Side_,
               fut: Side_, *, q: float, exit_t: int, funding: Funding | None = None,
               settle: float | None = None) -> SimTrade | None:
    """Largo spot / corto futuro desde `tr.entry_t` hasta `exit_t` (apertura de esa vela;
    con `settle` el futuro liquida a ese precio en `exit_t` y el spot se vende entonces)."""
    ts, si, fi = align(spot.bars, fut.bars, tr.entry_t, exit_t)
    if not len(ts) or ts[0] != tr.entry_t:
        return None
    L, mmr = p.perp_leverage, p.mmr
    s0, pe = float(spot.bars.o[si[0]]), float(fut.bars.o[fi[0]])
    ex.pair(tr, LegSpec(spot.key, "spot", "buy", q * s0, spot.scale(si[0], sp)),
            LegSpec(fut.key, fut.market, "sell", q * pe, fut.scale(fi[0], sp)))
    W = q * pe / L
    s_c, f_c, f_h, f_o = spot.bars.c[si], fut.bars.c[fi], fut.bars.h[fi], fut.bars.o[fi]
    events: list[tuple[int, float, float]] = []
    if funding is not None:
        for t_ev, rate in zip(*funding.between(tr.entry_t, exit_t), strict=True):
            k = int(np.searchsorted(ts, bar_of(int(t_ev))))
            mark = _mark(fut.bars, int(t_ev))
            if 0 < k < len(ts) and mark is not None:
                events.append((k, float(rate), mark))
    pos, n = 0, len(ts)
    for b, rate, mark in [*events, (n, 0.0, 0.0)]:
        while pos < b:
            thr_liq = (W + q * pe) / (q * (1 + mmr))
            thr_reb = (W + q * pe) / (q * (1 + sp.rebalance_frac / L))
            jl = _first(f_h[pos:b] >= thr_liq)
            jr = _first(f_c[pos:b] >= thr_reb)
            if jl is None and jr is None:
                pos = b
                break
            if jl is not None and (jr is None or jl <= jr):
                j = pos + jl
                p_liq = max(thr_liq, float(f_o[j]))
                fut_pnl = max(q * (pe - p_liq), -W)  # nunca más que el margen (fondo de seguro)
                tr.price_pnl += fut_pnl + q * (float(s_c[j]) - s0)
                tr.liq_loss += W + fut_pnl  # lo que quedaba de margen se pierde
                ex.leg(tr, LegSpec(spot.key, "spot", "sell", q * float(s_c[j]),
                                   spot.scale(int(si[j]), sp)))
                tr.exit_t, tr.exit_reason = int(ts[j]) + H_MS, "liq"
                return tr
            j = pos + jr
            sc_, fc_ = float(s_c[j]), float(f_c[j])
            q_new = (q * sc_ + W + q * (pe - fc_)) / (sc_ + fc_ / L)
            d = q - q_new
            if d > 0:
                ex.pair(tr, LegSpec(spot.key, "spot", "sell", d * sc_, spot.scale(int(si[j]), sp)),
                        LegSpec(fut.key, fut.market, "buy", d * fc_, fut.scale(int(fi[j]), sp)))
                tr.price_pnl += d * (sc_ - s0) + d * (pe - fc_)
                W += d * sc_ + d * (pe - fc_)
                q = q_new
                tr.rebalances += 1
            pos = j + 1
        if b < n:  # el corto cobra el funding positivo
            tr.funding += rate * q * mark
            W += rate * q * mark
            tr.settlements += 1
    return _exit_spot_short(tr, ex, sp, spot, fut, q=q, s0=s0, pe=pe, exit_t=exit_t,
                            settle=settle, last=(int(si[-1]), int(fi[-1])))


def _exit_spot_short(tr: SimTrade, ex: Executor, sp: SimParams, spot: Side_, fut: Side_, *,
                     q: float, s0: float, pe: float, exit_t: int, settle: float | None,
                     last: tuple[int, int]) -> SimTrade:
    i_s = spot.bars.at(exit_t)
    s_exit = float(spot.bars.o[i_s]) if i_s is not None else float(spot.bars.c[last[0]])
    sc_s = spot.scale(i_s if i_s is not None else last[0], sp)
    if settle is not None:
        ex.leg(tr, LegSpec(spot.key, "spot", "sell", q * s_exit, sc_s))
        tr.fees += ex.cm.settle_rate() * q * settle
        tr.price_pnl += q * (s_exit - s0) + q * (pe - settle)
        tr.exit_reason = "settle"
    else:
        i_f = fut.bars.at(exit_t)
        f_exit = float(fut.bars.o[i_f]) if i_f is not None else float(fut.bars.c[last[1]])
        ex.pair(tr, LegSpec(spot.key, "spot", "sell", q * s_exit, sc_s),
                LegSpec(fut.key, fut.market, "buy", q * f_exit,
                        fut.scale(i_f if i_f is not None else last[1], sp)))
        tr.price_pnl += q * (s_exit - s0) + q * (pe - f_exit)
    tr.exit_t = exit_t
    return tr


def futures_pair(tr: SimTrade, ex: Executor, sp: SimParams, p: ArbParams, long: Side_,
                 short: Side_, *, q: float, exit_t: int, first_long: bool = False,
                 funding: dict[str, Funding] | None = None, settle: float | None = None,
                 settle_long: bool = False, stop: np.ndarray | None = None) -> SimTrade | None:
    """Largo `long` / corto `short` (futuros, margen cruzado). `first_long`: la pata larga
    es la menos líquida (se ejecuta primero). `funding` por clave de pata (perpetuos).
    `settle`: un trimestral (corto, o largo con `settle_long`) liquida a ese precio en
    `exit_t`. `stop[j]` (línea de tiempo alineada) = salir en la apertura siguiente."""
    ts, li, si = align(long.bars, short.bars, tr.entry_t, exit_t)
    if not len(ts) or ts[0] != tr.entry_t:
        return None
    u0l, u0s = long.usd_at(tr.entry_t), short.usd_at(tr.entry_t)
    l0, s0 = float(long.bars.o[li[0]]), float(short.bars.o[si[0]])
    a = LegSpec(long.key, long.market, "buy", q * l0 * u0l, long.scale(li[0], sp))
    b = LegSpec(short.key, short.market, "sell", q * s0 * u0s, short.scale(si[0], sp))
    ex.pair(tr, *((a, b) if first_long else (b, a)))
    w0 = q * (l0 * u0l + s0 * u0s) / p.perp_leverage
    n = len(ts)
    hit = _first(stop[:n - 1]) if stop is not None else None
    end = n if hit is None else hit + 1
    t_exit = int(ts[end]) if end < n else exit_t
    fcum = np.zeros(n)
    for side, sgn in ((long, -1.0), (short, 1.0)):  # el largo paga funding positivo
        fs = (funding or {}).get(side.key)
        if fs is None:
            continue
        for t_ev, rate in zip(*fs.between(tr.entry_t, t_exit), strict=True):
            mark = _mark(side.bars, int(t_ev))
            k = int(np.searchsorted(ts, bar_of(int(t_ev))))
            if mark is None or not 0 < k < n:
                continue
            amt = sgn * float(rate) * q * mark * side.usd_at(int(t_ev))
            fcum[k:] += amt
            tr.funding += amt
            tr.settlements += 1
    lc, sc = long.bars.c[li], short.bars.c[si]
    pnl = q * ((lc - l0) * u0l - (sc - s0) * u0s)
    mm = p.mmr * q * (lc * u0l + sc * u0s)
    j = _first((w0 + fcum + pnl <= mm)[:end])
    if j is not None:  # se agota el margen cruzado: se pierde lo que queda, nunca más
        tr.funding -= float(fcum[-1] - fcum[j])
        lost = max(float(pnl[j]), -float(w0 + fcum[j]))
        tr.price_pnl += lost
        tr.liq_loss += float(w0 + fcum[j]) + lost
        tr.exit_t, tr.exit_reason = int(ts[j]) + H_MS, "liq"
        return tr
    settling = settle is not None and end == n
    orders: list[LegSpec] = []
    for side, idx, p0, sgn, is_long in ((long, li, l0, 1.0, True), (short, si, s0, -1.0, False)):
        u1 = side.usd_at(t_exit)
        if settling and settle_long == is_long:
            assert settle is not None
            tr.fees += ex.cm.settle_rate() * q * settle * u1
            tr.price_pnl += sgn * q * (settle - p0) * u1
            continue
        i = side.bars.at(t_exit)
        px = float(side.bars.o[i]) if i is not None else float(side.bars.c[idx[end - 1]])
        tr.price_pnl += sgn * q * (px - p0) * u1
        orders.append(LegSpec(side.key, side.market, "sell" if is_long else "buy",
                              q * px * u1, side.scale(i if i is not None else int(idx[end - 1]),
                                                      sp)))
    if len(orders) == 2:
        ex.pair(tr, *(orders if first_long else orders[::-1]))
    else:
        ex.leg(tr, orders[0])
    tr.exit_reason = "settle" if settling else ("converged" if end < n else "time")
    tr.exit_t = t_exit
    return tr
