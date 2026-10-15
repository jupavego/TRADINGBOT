"""Motor de oportunidades de arbitraje dentro de Binance (T38): funciones puras sobre
`ArbMarket` ya cargado (I/O en `eim/data/arb_market.py`). Sin ejecución (T45)."""

from eim.arbitrage.basis import scan_basis
from eim.arbitrage.funding_carry import scan_funding_carry
from eim.arbitrage.params import DEFAULT_PARAMS, ArbParams
from eim.arbitrage.related_perps import scan_related_perps
from eim.arbitrage.scan import ArbResult, scan_all
from eim.arbitrage.selector import Ranked, Rejected, Selection, select
from eim.arbitrage.triangular import scan_triangular

__all__ = [
    "DEFAULT_PARAMS",
    "ArbParams",
    "ArbResult",
    "Ranked",
    "Rejected",
    "Selection",
    "scan_all",
    "scan_basis",
    "scan_funding_carry",
    "scan_related_perps",
    "scan_triangular",
    "select",
]
