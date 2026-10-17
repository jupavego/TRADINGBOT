"""Libros y fotografías sintéticas para los tests de arbitraje (sin red)."""

from __future__ import annotations

from eim.core import ArbMarket, Book, FuturesContract, PremiumInfo, SpotPair

# Supuestos de T38 con los que se escribieron los tests de mecánica del motor (T43 cambió
# los valores por defecto con evidencia; estos tests prueban la mecánica, no la calibración).
T38 = {"carry_horizon_h": 24.0, "perp_leverage": 2.0, "daily_move": 0.04,
       "basis_floor_bps": 5.0, "funding_shock_rate": 0.0001,
       "selectable": ("funding_carry", "basis", "related_perps"), "disabled_variants": ()}
ASOF = 1_760_000_000_000 - 1_760_000_000_000 % 3_600_000 + 1_800_000  # hh:30 UTC
H = 3_600_000
DAY = 24 * H


def book(mid: float, *, spread_bps: float = 1.0, levels: int = 20, qty: float = 5.0,
         step_bps: float = 0.5, source: str = "test") -> Book:
    """Libro simétrico: mejor bid/ask a ±spread/2 y `levels` niveles de `qty` cada uno."""
    half = mid * spread_bps / 2e4
    step = mid * step_bps / 1e4
    bids = [(mid - half - i * step, qty) for i in range(levels)]
    asks = [(mid + half + i * step, qty) for i in range(levels)]
    return Book(bids=bids, asks=asks, source=source)


def premium(symbol: str, rate: float, *, mark: float, index: float | None = None,
            next_in_min: float = 90, interval_h: float = 8.0) -> PremiumInfo:
    return PremiumInfo(symbol=symbol, mark=mark, index=index or mark, funding_rate=rate,
                       next_funding_t=ASOF + int(next_in_min * 60_000), interval_h=interval_h,
                       t=ASOF)


def history(rate: float, n: int = 21, interval_h: float = 8.0) -> list[tuple[int, float]]:
    return [(ASOF - (n - i) * int(interval_h * H), rate) for i in range(n)]


def market(*, spot: dict[str, Book] | None = None, futures: dict[str, Book] | None = None,
           prem: dict[str, PremiumInfo] | None = None,
           hist: dict[str, list[tuple[int, float]]] | None = None,
           pairs: list[SpotPair] | None = None, contracts: list[FuturesContract] | None = None,
           borrow: dict[str, float] | None = None, errors: dict[str, str] | None = None,
           ) -> ArbMarket:
    spot, futures, prem, hist = spot or {}, futures or {}, prem or {}, hist or {}
    if pairs is None:
        pairs = [SpotPair(symbol=s, base=s.removesuffix("USDT"), quote="USDT") for s in spot]
    sources = {f"book:spot:{s}": "binance-spot" for s in spot}
    cov = {f"book:spot:{s}": (ASOF, ASOF) for s in spot}
    for c in contracts or []:
        if c.symbol in futures:
            sources[f"book:{c.market}:{c.symbol}"] = "binance-futures"
            cov[f"book:{c.market}:{c.symbol}"] = (ASOF, ASOF)
    for s in prem:
        sources[f"premium:{s}"], cov[f"premium:{s}"] = "binance-futures", (ASOF, ASOF)
    for s, rows in hist.items():
        sources[f"funding:{s}"], cov[f"funding:{s}"] = "binance-futures", (rows[0][0], rows[-1][0])
    return ArbMarket(asof=ASOF, spot_pairs=pairs, contracts=contracts or [], spot_books=spot,
                     futures_books=futures, premium=prem, funding_hist=hist,
                     borrow_apr=borrow or {}, sources=sources, coverage=cov,
                     errors=errors or {})


def perp(base: str, margin: str = "USDT") -> FuturesContract:
    return FuturesContract(symbol=f"{base}{margin}", base=base, margin=margin, kind="perpetual")


def quarterly(base: str, days: float) -> FuturesContract:
    return FuturesContract(symbol=f"{base}USDT_Q", base=base, margin="USDT", kind="quarterly",
                           delivery_t=ASOF + int(days * DAY))


def carry_market(rate: float, *, realized: float | None = None, spot_mid: float = 60_000.0,
                 perp_mid: float | None = None, qty: float = 5.0, **kw) -> ArbMarket:
    """BTC: spot + perpetuo USDT con funding previsto `rate` y realizado `realized`."""
    pm = perp_mid or spot_mid
    hist = {"BTCUSDT": history(realized)} if realized is not None else {}
    return market(spot={"BTCUSDT": book(spot_mid, qty=qty)},
                  futures={"BTCUSDT": book(pm, qty=qty)},
                  prem={"BTCUSDT": premium("BTCUSDT", rate, mark=pm, index=spot_mid)},
                  hist=hist, contracts=[perp("BTC")], **kw)
