"""Escaneo completo: todas las estrategias sobre la misma fotografía + selección."""

from __future__ import annotations

from collections.abc import Callable

from eim.arbitrage.basis import scan_basis
from eim.arbitrage.funding_carry import scan_funding_carry
from eim.arbitrage.params import DEFAULT_PARAMS, ArbParams
from eim.arbitrage.related_perps import scan_related_perps
from eim.arbitrage.selector import Selection, select
from eim.arbitrage.triangular import scan_triangular
from eim.core import ArbMarket, ArbScan, CostModel
from eim.core.market import Frozen

Scanner = Callable[[ArbMarket, CostModel, ArbParams], ArbScan]
STRATEGIES: tuple[Scanner, ...] = (scan_funding_carry, scan_basis, scan_triangular,
                                   scan_related_perps)


class ArbResult(Frozen):
    asof: int
    scans: list[ArbScan]
    selection: Selection
    cost_model: CostModel


def scan_all(mkt: ArbMarket, cm: CostModel | None = None,
             p: ArbParams = DEFAULT_PARAMS) -> ArbResult:
    """Puro y determinista sobre `mkt`."""
    cm = cm or CostModel()
    scans = [fn(mkt, cm, p) for fn in STRATEGIES]
    opps = [o for s in scans for o in s.opportunities]
    return ArbResult(asof=mkt.asof, scans=scans, selection=select(opps, p), cost_model=cm)
