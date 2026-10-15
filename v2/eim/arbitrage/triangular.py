"""Triangular spot: ciclos USDT→A→B→USDT con precio efectivo por profundidad y comisión
por pata (cobrada en el activo recibido, como Binance sin BNB).

Bruto = nocional × (Π tipos a precio medio − 1). Neto = USDT final real recorriendo los tres
libros con comisiones − nocional (lo no ejecutado se valora a precio medio). Deslizamiento =
bruto − comisiones − neto (incluye el efecto compuesto). Con comisiones realistas casi
siempre es ≤ 0: se informa igual (T33: no entra en el selector).
"""

from __future__ import annotations

from itertools import combinations

from eim.arbitrage import risk
from eim.arbitrage.common import assemble, finish, mid
from eim.arbitrage.params import ArbParams
from eim.core import ArbMarket, ArbScan, Book, CostModel, Leg, Opportunity, SpotPair

START = "USDT"


def scan_triangular(mkt: ArbMarket, cm: CostModel, p: ArbParams) -> ArbScan:
    live = {pr.symbol: pr for pr in mkt.spot_pairs
            if pr.symbol in mkt.spot_books and mid(mkt.spot_books[pr.symbol]) is not None}
    missing = [f"libro spot {pr.symbol}" + (f" ({mkt.errors[k]})" if (k := f"book:spot:"
               f"{pr.symbol}") in mkt.errors else "") for pr in mkt.spot_pairs
               if pr.symbol not in live]
    if not mkt.spot_pairs:
        missing.append("pares spot (exchangeInfo)" + (
            f" ({mkt.errors['spot_pairs']})" if "spot_pairs" in mkt.errors else ""))
    edges: dict[frozenset[str], SpotPair] = {frozenset((pr.base, pr.quote)): pr
                                              for pr in live.values()}
    usd = {START: 1.0} | {pr.base: mid(mkt.spot_books[s]) or 0.0
                          for s, pr in live.items() if pr.quote == START}
    nodes = sorted({a for pr in live.values() for a in (pr.base, pr.quote)} - {START})
    opps: list[Opportunity] = []
    for a, b in combinations(nodes, 2):
        path = [frozenset((START, a)), frozenset((a, b)), frozenset((b, START))]
        if not all(e in edges for e in path) or a not in usd or b not in usd:
            continue
        for cycle in ([START, a, b, START], [START, b, a, START]):
            opps.append(_cycle(mkt, cm, p, cycle, edges, usd))
    return finish("triangular", mkt, opps, missing, [])


def _step(cm: CostModel, pr: SpotPair, book: Book, frm: str, to: str, amount: float,
          usd: dict[str, float]) -> tuple[float, float, float, Leg]:
    """Convierte `amount` de `frm` en `to`. Devuelve (recibido neto, sobrante sin ejecutar
    en `frm`, tipo a precio medio, pata)."""
    m = mid(book) or 0.0
    if pr.base == to:  # compra base gastando la cotizada
        fill = cm.fill(book.asks, quote=amount)
        side, got, spent, rate = "buy", fill.base, fill.quote, 1.0 / m
        qty = fill.base * amount / fill.quote if fill.quote else amount / m
    else:  # vende base por la cotizada
        fill = cm.fill(book.bids, base=amount)
        side, got, spent, rate, qty = "sell", fill.quote, fill.base, m, amount
    fee_rate = cm.fee_rate("spot")
    fee = got * fee_rate
    lg = Leg(market="spot", symbol=pr.symbol, side=side, qty=qty, filled=fill.base,
             vwap=fill.vwap or m, mid=m, best=fill.best or m, fee_rate=fee_rate,
             fee=fee * usd[to], slippage=abs((fill.vwap or m) - m) * fill.base * usd[pr.quote],
             levels=fill.levels)
    return got - fee, amount - spent, rate, lg


def _cycle(mkt: ArbMarket, cm: CostModel, p: ArbParams, cycle: list[str],
           edges: dict[frozenset[str], SpotPair], usd: dict[str, float]) -> Opportunity:
    n = p.notional_usd
    amount, leftover_usd, mid_prod = n, 0.0, 1.0
    legs: list[Leg] = []
    used: list[tuple[Leg, Book]] = []
    for frm, to in zip(cycle, cycle[1:], strict=False):
        pr = edges[frozenset((frm, to))]
        book = mkt.spot_books[pr.symbol]
        amount, left, rate, lg = _step(cm, pr, book, frm, to, amount, usd)
        leftover_usd += left * usd[frm]
        mid_prod *= rate
        legs.append(lg)
        used.append((lg, book))
    net = amount + leftover_usd - n
    gross = n * (mid_prod - 1.0)
    fees = sum(lg.fee for lg in legs)
    rk = risk.build(
        risk.legging(legs, sequential=True),
        (0.0, "misma plataforma y ejecución inmediata: sin riesgo de base"),
        risk.liquidation(p, 0.0, leveraged=False),
        risk.liquidity(used),
    )
    route = "→".join(cycle)
    details = {"mid_product": mid_prod, "gross_bps": (mid_prod - 1) * 1e4,
               "fee_bps": fees / n * 1e4, "slippage_legs_sum": sum(lg.slippage for lg in legs),
               "leftover_usd": leftover_usd}
    keys = [f"book:spot:{lg.symbol}" for lg in legs]
    return assemble("triangular", route, route, legs, gross, mkt=mkt, keys=keys, capital=n,
                    horizon_h=0.0, risk=rk, p=p, annualize=False,
                    slippage=gross - fees - net, details=details,
                    warnings=["informativa: el triangular está fuera del alcance aprobado (T33)"])
