"""Piezas comunes: patas contra el libro, montaje de la oportunidad y cierre del escaneo."""

from __future__ import annotations

from eim.arbitrage.params import ArbParams
from eim.core import ArbMarket, ArbScan, Book, CostModel, Costs, Leg, Opportunity, Risk
from eim.core.arbitrage import MarketKind, Side, StrategyId


def mid(book: Book) -> float | None:
    if not book.bids or not book.asks:
        return None
    return (book.bids[0][0] + book.asks[0][0]) / 2


def leg(cm: CostModel, market: MarketKind, symbol: str, book: Book, side: Side, qty: float,
        *, action: str = "open", usd: float = 1.0) -> Leg:
    """Ejecuta `qty` base recorriendo el lado que corresponde (compra → asks, venta → bids).

    `usd` convierte la moneda cotizada a USD (1 para USDT; USDCUSDT para USDC-M).
    """
    fill = cm.fill(book.asks if side == "buy" else book.bids, base=qty)
    m = mid(book) or fill.best
    rate = cm.fee_rate(market)
    return Leg(market=market, symbol=symbol, side=side, action=action, qty=qty,
               filled=fill.base, vwap=fill.vwap or m, mid=m, best=fill.best or m,
               fee_rate=rate, fee=rate * fill.quote * usd,
               slippage=abs((fill.vwap or m) - m) * fill.base * usd, levels=fill.levels)


def settle_leg(cm: CostModel, symbol: str, side: Side, qty: float, price: float) -> Leg:
    """Liquidación de un trimestral al vencimiento: sin libro (precio de liquidación =
    índice ≈ spot) y con la tasa de liquidación del modelo de costos."""
    rate = cm.settle_rate()
    return Leg(market="usdm", symbol=symbol, side=side, action="close", qty=qty, filled=qty,
               vwap=price, mid=price, best=price, fee_rate=rate, fee=rate * qty * price,
               slippage=0.0, levels=0)


def flip(side: Side) -> Side:
    return "sell" if side == "buy" else "buy"


def coverage_of(mkt: ArbMarket, keys: list[str]) -> tuple[str, dict[str, tuple[int, int]]]:
    cov = {k: mkt.coverage[k] for k in keys if k in mkt.coverage}
    srcs = sorted({mkt.sources[k] for k in keys if k in mkt.sources})
    return "+".join(srcs) or "desconocida", cov


def assemble(
    strategy: StrategyId, variant: str, asset: str, legs: list[Leg], gross: float, *,
    mkt: ArbMarket, keys: list[str], capital: float, horizon_h: float, risk: Risk,
    p: ArbParams, funding: float = 0.0, borrow: float = 0.0, annualize: bool = True,
    slippage: float | None = None,
    valid_until: int | None = None, details: dict | None = None,
    warnings: list[str] | None = None,
) -> Opportunity:
    """Suma comisiones y deslizamiento de todas las patas y fija `net = gross − costos`.

    `slippage` explícito sustituye la suma por pata (triangular: residuo compuesto real)."""
    slip = sum(lg.slippage for lg in legs) if slippage is None else slippage
    costs = Costs(fees=sum(lg.fee for lg in legs), slippage=slip, funding=funding,
                  borrow=borrow)
    net = gross - costs.total
    ann = net / capital * 8760.0 / horizon_h if annualize and horizon_h > 0 else None
    source, cov = coverage_of(mkt, keys)
    until = mkt.asof + p.quote_ttl_s * 1000
    if valid_until is not None and valid_until > mkt.asof:
        until = min(until, valid_until)
    warns = list(warnings or [])
    incomplete = [lg for lg in legs if not lg.complete]
    for lg in incomplete:
        warns.append(f"pata incompleta {lg.symbol} ({lg.side}): el libro visible cubre "
                     f"{lg.filled:.6g} de {lg.qty:.6g}")
    return Opportunity(strategy=strategy, variant=variant, asset=asset, legs=legs,
                       gross_edge=gross, costs=costs, net_edge=net, capital_required=capital,
                       annualized=ann, horizon_h=horizon_h, risk=risk, asof=mkt.asof,
                       valid_until=until, source=source, coverage=cov,
                       executable=not incomplete, details=details or {}, warnings=warns)


def missing_book(mkt: ArbMarket, key: str, label: str) -> str:
    why = mkt.errors.get(key)
    return f"{label}" + (f" ({why})" if why else "")


def finish(strategy: StrategyId, mkt: ArbMarket, opps: list[Opportunity], missing: list[str],
           warnings: list[str], *, degraded: bool = False) -> ArbScan:
    """`no_data` si no hubo con qué valorar nada; `degraded` si faltó una parte."""
    missing, warnings = list(dict.fromkeys(missing)), list(dict.fromkeys(warnings))
    if missing and not opps:
        status = "no_data"
    elif missing or degraded:
        status = "degraded"
    else:
        status = "ok"
    return ArbScan(strategy=strategy, status=status, asof=mkt.asof, opportunities=opps,
                   missing=missing, warnings=warnings)
