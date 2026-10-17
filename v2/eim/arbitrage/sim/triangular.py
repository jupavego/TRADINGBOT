"""Triangular spot (T43).

1. Solo ticker — OPTIMISTA: no hay profundidad histórica de los pares spot (el recolector
   de T23 graba futuros); se usan cierres de velas de 1 min. Los cierres no son simultáneos
   ni ejecutables (no son bid/ask): la desviación del producto de tipos SOBREESTIMA las
   oportunidades; se resta el medio diferencial del libro capturado si existe. Cota superior.
2. Libros reales capturados (pocas fotografías): `scan_triangular` de T38 tal cual.
"""

from __future__ import annotations

from itertools import combinations

import numpy as np

from eim.arbitrage.params import ArbParams
from eim.arbitrage.sim.depth import DepthModel
from eim.arbitrage.sim.frame import ArbHistory
from eim.arbitrage.sim.replay import spot_key
from eim.arbitrage.triangular import scan_triangular
from eim.core import CostModel, SpotPair

START = "USDT"


def _cycles(pairs: dict[frozenset[str], SpotPair]) -> list[list[str]]:
    nodes = sorted({a for k in pairs for a in k} - {START})
    out = []
    for a, b in combinations(nodes, 2):
        edges = [frozenset((START, a)), frozenset((a, b)), frozenset((b, START))]
        if all(e in pairs for e in edges):
            out += [[START, a, b, START], [START, b, a, START]]
    return out


def scan_ticker(hist: ArbHistory, cms: dict[str, CostModel], notional: float) -> dict:
    """Por ciclo: minutos evaluados, bruto (pb) y cuántos minutos superan comisiones y medio
    diferencial con cada modelo de costos de `cms` (p. ej. VIP 0 y VIP 9 + BNB)."""
    pairs = {frozenset((p.base, p.quote)): p for p in hist.tri_pairs if p.symbol in hist.tri_bars}
    dm = DepthModel(hist.depth, ref_notional=notional)
    rows, no_depth = [], set()
    for cyc in _cycles(pairs):
        legs = [pairs[frozenset((f, t))] for f, t in zip(cyc, cyc[1:], strict=False)]
        bars = [hist.tri_bars[p.symbol] for p in legs]
        ts = bars[0].t
        for b in bars[1:]:
            ts = np.intersect1d(ts, b.t, assume_unique=True)
        if not len(ts):
            continue
        prod = np.ones(len(ts))
        spread_bps = 0.0
        for to, p, b in zip(cyc[1:], legs, bars, strict=True):
            c = b.c[np.searchsorted(b.t, ts)]
            buy = p.base == to
            prod *= 1.0 / c if buy else c
            got = dm.cost(spot_key(p.symbol), notional, "buy" if buy else "sell")
            if got is None:
                no_depth.add(p.symbol)
            else:
                spread_bps += got[0] / notional * 1e4
        gross = (prod - 1.0) * 1e4
        row = {"cycle": "→".join(cyc), "minutes": int(len(ts)),
               "from_t": int(ts[0]), "to_t": int(ts[-1]),
               "gross_p50_bps": float(np.median(gross)),
               "gross_p99_bps": float(np.percentile(gross, 99)),
               "gross_max_bps": float(gross.max()), "spread_bps": spread_bps, "by_cost": {}}
        for name, cm in cms.items():
            fee_bps = (1 - (1 - cm.fee_rate("spot")) ** 3) * 1e4
            net = gross - fee_bps - spread_bps
            pos = net > 0
            row["by_cost"][name] = {
                "fee_bps": fee_bps, "minutes_pos": int(pos.sum()),
                "share_pos": float(pos.mean()), "net_max_bps": float(net.max()),
                "upper_bound_usd": float(net[pos].sum() / 1e4 * notional)}
        rows.append(row)
    return {"cycles": rows, "no_depth": sorted(no_depth), "notional": notional,
            "label": "optimista (solo ticker: cierres de 1 min, sin profundidad histórica)"}


def scan_captures(hist: ArbHistory, cms: dict[str, CostModel], p: ArbParams) -> dict:
    """El motor T38 (`scan_triangular`) sobre cada fotografía real guardada."""
    caps = [m for m in hist.captures if m.spot_books]
    out: dict = {"captures": len(caps), "from_t": min((m.asof for m in caps), default=None),
                 "to_t": max((m.asof for m in caps), default=None), "by_cost": {}}
    for name, cm in cms.items():
        nets = [o.net_bps for m in caps for o in scan_triangular(m, cm, p).opportunities]
        out["by_cost"][name] = {"cycles": len(nets), "positive": sum(x > 0 for x in nets),
                                "best_bps": max(nets) if nets else None,
                                "median_bps": float(np.median(nets)) if nets else None}
    return out
