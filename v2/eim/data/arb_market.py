"""Carga la fotografía `ArbMarket` (T38): todo el I/O del motor de arbitraje vive aquí.

Cada pieza que falla queda fuera con su motivo en `errors` (nunca se rellena con supuestos);
las estrategias responden `no_data` o `degraded` según lo que falte.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from eim.core import ArbMarket, Book, FuturesContract, PremiumInfo, SpotPair
from eim.data.providers.binance_arb import FUTURES_SOURCE, SPOT_SOURCE, BinanceArbData

T = TypeVar("T")
DAY_MS = 86_400_000
TRI_ASSETS = ("USDT", "BTC", "ETH", "BNB", "SOL", "XRP")


def load_arb_market(
    prov: BinanceArbData,
    *,
    assets: Iterable[str] = ("BTC", "ETH"),
    tri_assets: Iterable[str] = TRI_ASSETS,
    depth: int = 100,
    funding_days: int = 7,
    max_quarterlies: int = 2,
    borrow_apr: dict[str, float] | None = None,
    borrow_source: str = "manual (configuración del usuario)",
    workers: int = 8,
) -> ArbMarket:
    """Lee libros, contratos, funding previsto y realizado de Binance para `assets` y los
    pares spot entre `tri_assets` (ciclos triangulares).

    Libros y funding realizado se piden en paralelo (`workers` hilos, T39): la fotografía
    tarda ~1 s en vez de ~8 s y las patas quedan casi simultáneas frente a la vigencia de 15 s.
    """
    now = prov.clock()
    assets, tri = list(assets), set(tri_assets)
    errors: dict[str, str] = {}
    sources: dict[str, str] = {}
    coverage: dict[str, tuple[int, int]] = {}

    def guard(key: str, fn: Callable[[], T]) -> T | None:
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — se registra y la estrategia lo declara
            errors[key] = f"{type(exc).__name__}: {exc}"[:240]
            return None

    pairs: list[SpotPair] = guard("spot_pairs", prov.spot_pairs) or []
    contracts: list[FuturesContract] = guard("contracts", prov.futures_contracts) or []
    premium_all: dict[str, PremiumInfo] = guard("premium", prov.premium_index) or {}
    if pairs:
        sources["spot_pairs"] = SPOT_SOURCE
    if contracts:
        sources["contracts"] = FUTURES_SOURCE

    contracts = [c for c in contracts if c.base in assets]
    quarterly: list[FuturesContract] = []
    for base in assets:
        q = sorted((c for c in contracts if c.base == base and c.kind == "quarterly"
                    and c.margin == "USDT" and (c.delivery_t or 0) > now),
                   key=lambda c: c.delivery_t or 0)
        quarterly += q[:max_quarterlies]
    perps = [c for c in contracts if c.kind == "perpetual"]
    contracts = perps + quarterly

    premium: dict[str, PremiumInfo] = {}
    for c in perps:
        info = premium_all.get(c.symbol)
        key = f"premium:{c.symbol}"
        if info is None:
            errors.setdefault(key, errors.get("premium", "sin premiumIndex para el símbolo"))
            continue
        premium[c.symbol] = info
        sources[key] = FUTURES_SOURCE
        coverage[key] = (info.t, info.t)

    wanted_spot = {p.symbol for p in pairs if (p.base in assets and p.quote == "USDT")
                   or (p.base in tri and p.quote in tri) or p.symbol == "USDCUSDT"}
    spot_syms = sorted(wanted_spot)
    jobs: list[tuple[str, Callable[[], object]]] = (
        [(f"book:spot:{s}", lambda s=s: prov.spot_book(s, depth)) for s in spot_syms]
        + [(f"book:{c.market}:{c.symbol}", lambda s=c.symbol: prov.futures_book(s, depth))
           for c in contracts]
        + [(f"funding:{c.symbol}", lambda s=c.symbol: prov.funding_history(
            s, now - funding_days * DAY_MS, now + 1)) for c in perps])
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        got_all = dict(zip([k for k, _ in jobs], ex.map(lambda j: guard(*j), jobs),
                           strict=True))

    spot_books: dict[str, Book] = {}
    for sym in spot_syms:
        key = f"book:spot:{sym}"
        got = got_all[key]
        if got:
            spot_books[sym], t = got
            sources[key], coverage[key] = SPOT_SOURCE, (t, t)

    futures_books: dict[str, Book] = {}
    for c in contracts:
        key = f"book:{c.market}:{c.symbol}"
        got = got_all[key]
        if got:
            futures_books[c.symbol], t = got
            sources[key], coverage[key] = FUTURES_SOURCE, (t, t)

    funding_hist: dict[str, list[tuple[int, float]]] = {}
    for c in perps:
        key = f"funding:{c.symbol}"
        rows = got_all[key]
        if rows:
            funding_hist[c.symbol] = rows
            sources[key], coverage[key] = FUTURES_SOURCE, (rows[0][0], rows[-1][0])
        elif rows is not None:
            errors[key] = f"sin liquidaciones de funding en {funding_days} días"

    borrow = dict(borrow_apr or {})
    for asset in borrow:
        sources[f"borrow:{asset}"] = borrow_source
        coverage[f"borrow:{asset}"] = (now, now)

    pairs = [p for p in pairs if p.symbol in wanted_spot]
    return ArbMarket(asof=now, spot_pairs=pairs, contracts=contracts, spot_books=spot_books,
                     futures_books=futures_books, premium=premium, funding_hist=funding_hist,
                     borrow_apr=borrow, sources=sources, coverage=coverage, errors=errors)
