"""Panel de decisiones (T43): en cada hora de decisión el motor T38 valora y selecciona
sobre la fotografía reproducida; cada oportunidad seleccionable se simula hasta su salida
para comparar lo ESTIMADO (lo que vio el selector) con lo REALIZADO. La política (una
posición a la vez por estrategia y activo) y la calibración salen de este panel.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from eim.arbitrage.basis import scan_basis
from eim.arbitrage.funding_carry import scan_funding_carry
from eim.arbitrage.params import ArbParams
from eim.arbitrage.related_perps import scan_related_perps
from eim.arbitrage.selector import score, select
from eim.arbitrage.sim.depth import DepthModel
from eim.arbitrage.sim.frame import H_MS, ArbHistory
from eim.arbitrage.sim.params import SimParams
from eim.arbitrage.sim.realize import Realizer
from eim.arbitrage.sim.replay import Replayer
from eim.arbitrage.sim.trade import Executor, SimTrade
from eim.core import ArbMarket, ArbScan, CostModel

Scanner = Callable[[ArbMarket, CostModel, ArbParams], ArbScan]
SCANNERS: dict[str, Scanner] = {"funding_carry": scan_funding_carry, "basis": scan_basis,
                                 "related_perps": scan_related_perps}
WARMUP_H = 8 * 22  # 21 liquidaciones realizadas + margen antes de la primera decisión


@dataclass
class PanelRow:
    t: int
    strategy: str
    asset: str
    variant: str
    instrument: str
    est_net_bps: float
    est_score: float
    est_annualized: float | None
    horizon_h: float
    selected: bool
    reject_code: str | None
    trade: SimTrade | None
    skip: str | None = None  # por qué no se pudo simular


@dataclass
class Panel:
    rows: list[PanelRow]
    times: list[int]
    missing: Counter = field(default_factory=Counter)  # (estrategia, faltante) → veces
    skips: Counter = field(default_factory=Counter)

    def of(self, strategy: str) -> list[PanelRow]:
        return [r for r in self.rows if r.strategy == strategy]


def decision_times(hist: ArbHistory, p: ArbParams, sp: SimParams) -> list[int]:
    """Rejilla cada `decision_every_h`, `decision_offset_h` antes de las liquidaciones de
    00/08/16 UTC, dentro del tramo con velas spot y del perpetuo de todos los activos."""
    lo, hi = [], []
    for a in p.assets:
        h = hist.assets.get(a)
        for bars in (h.spot, h.perp) if h else ():
            if bars is not None and len(bars):
                lo.append(int(bars.t[0]))
                hi.append(int(bars.t[-1]))
    if not lo:
        return []
    start, end = max(lo) + WARMUP_H * H_MS, min(hi)
    grid = 8 * H_MS
    t = (start // grid + 1) * grid - sp.decision_offset_h * H_MS
    step = sp.decision_every_h * H_MS
    out = []
    while t <= end:
        out.append(t)
        t += step
    return out


def instrument_of(o) -> str:  # noqa: ANN001 — Opportunity
    syms = list(dict.fromkeys(lg.symbol for lg in o.legs))
    return "/".join(syms)


def build_panel(hist: ArbHistory, cm: CostModel, p: ArbParams, sp: SimParams, *,
                strategies: tuple[str, ...] = tuple(SCANNERS), times: list[int] | None = None,
                progress: Callable[[int, int], None] | None = None) -> Panel:
    dm = DepthModel(hist.depth, ref_notional=p.notional_usd)
    rp = Replayer(hist, dm, sp, p)
    rz = Realizer(rp, Executor(cm, dm, sp))
    times = decision_times(hist, p, sp) if times is None else times
    panel = Panel(rows=[], times=times)
    for k, t in enumerate(times):
        mkt = rp.market_at(t)
        opps = []
        for s in strategies:
            scan = SCANNERS[s](mkt, cm, p)
            opps += scan.opportunities
            for m in scan.missing:
                panel.missing[(s, m.split(" (")[0])] += 1
        sel = select(opps, p, now=t)
        chosen = {id(r.opportunity) for r in sel.selected}
        codes = {id(r.opportunity): r.code for r in sel.rejected}
        for o in opps:
            tr, why = rz.run(o, t)
            if why:
                panel.skips[(o.strategy, why)] += 1
            panel.rows.append(PanelRow(
                t=t, strategy=o.strategy, asset=o.asset, variant=o.variant,
                instrument=instrument_of(o), est_net_bps=o.net_bps, est_score=score(o, p),
                est_annualized=o.annualized, horizon_h=o.horizon_h,
                selected=id(o) in chosen, reject_code=codes.get(id(o)), trade=tr, skip=why))
        if progress and (k % 200 == 0 or k == len(times) - 1):
            progress(k + 1, len(times))
    return panel


def policy(rows: list[PanelRow], *, only_selected: bool = True,
           min_est_bps: float | None = None) -> list[SimTrade]:
    """Una posición a la vez por activo: en cada decisión, si está plano, toma la mejor
    oportunidad seleccionada (mayor puntuación) y queda ocupado hasta su salida.
    `min_est_bps` sustituye el filtro del selector por un umbral de neto estimado."""
    out: list[SimTrade] = []
    by_asset: dict[str, list[PanelRow]] = {}
    for r in rows:
        by_asset.setdefault(r.asset, []).append(r)
    for rs in by_asset.values():
        busy = -1
        by_t: dict[int, list[PanelRow]] = {}
        for r in rs:
            by_t.setdefault(r.t, []).append(r)
        for t in sorted(by_t):
            if t < busy:
                continue
            cand = [r for r in by_t[t] if r.trade is not None and _passes(r, only_selected,
                                                                         min_est_bps)]
            if not cand:
                continue
            best = max(cand, key=lambda r: r.est_score)
            assert best.trade is not None
            out.append(best.trade)
            busy = best.trade.exit_t
    return sorted(out, key=lambda tr: tr.entry_t)


def _passes(r: PanelRow, only_selected: bool, min_est_bps: float | None) -> bool:
    if min_est_bps is not None:
        return r.reject_code in (None, "below_min") and r.est_net_bps >= min_est_bps
    return r.selected or not only_selected
