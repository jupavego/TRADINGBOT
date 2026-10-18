"""De las oportunidades vigentes del motor T38 a planes de dos patas ejecutables (T45). Puro.

Solo se ejecutan las estrategias habilitadas (Viable o Marginal en T43) con una pata spot y una
de futuros USDⓈ-M, ya seleccionadas por `select` (neto, vigencia, liquidez) y sin una posición
abierta de la misma estrategia y activo. Un carry no se abre con el funding previsto negativo
(es lo que haría cerrarlo: `manage`). Orden de envío: primero la pata menos líquida (la que
consume más fracción del libro visible); si la segunda falla, se deshace la primera.
"""

from __future__ import annotations

from eim.arbitrage.selector import Selection
from eim.core import ArbMarket, Opportunity
from eim.core.arbitrage import Leg
from eim.risk.arb_models import ArbLegPlan, ArbPlan


def arb_id(o: Opportunity) -> str:
    fut = next(lg.symbol for lg in o.legs if lg.market == "usdm")
    return f"{o.strategy}|{o.variant}|{o.asset}|{fut}|{o.asof}"


def _depth_frac(lg: Leg, mkt: ArbMarket | None) -> float:
    """Fracción del libro visible (lado que se cruza) que consume la pata."""
    if mkt is not None:
        book = (mkt.spot_books if lg.market == "spot" else mkt.futures_books).get(lg.symbol)
        if book is not None:
            side = book.asks if lg.side == "buy" else book.bids
            depth = sum(q for _, q in side)
            return lg.qty / depth if depth > 0 else 1.0
    return abs(lg.slippage) / max(lg.vwap * lg.qty, 1e-9)  # sin libro: el deslizamiento


def plan_of(o: Opportunity, score: float, mkt: ArbMarket | None, leverage: int) -> ArbPlan | None:
    """None si la oportunidad no es de dos patas spot + futuros USDⓈ-M."""
    opens = [lg for lg in o.legs if lg.action == "open"]
    if len(opens) != 2 or sorted(lg.market for lg in opens) != ["spot", "usdm"]:
        return None
    legs = sorted((ArbLegPlan(market=lg.market, symbol=lg.symbol,  # type: ignore[arg-type]
                              side=1 if lg.side == "buy" else -1, ref_price=lg.vwap or lg.mid,
                              depth_frac=_depth_frac(lg, mkt)) for lg in opens),
                  key=lambda x: x.depth_frac, reverse=True)
    spot = next(lg for lg in opens if lg.market == "spot")
    qty = spot.qty
    notional = qty * (spot.vwap or spot.mid)
    exit_cost = sum(lg.fee + max(lg.slippage, 0.0) for lg in o.legs if lg.action == "close")
    d = o.details
    n = int(d.get("settlements") or 0)
    rate = o.gross_edge / (n * notional) if o.strategy == "funding_carry" and n else None
    delivery = d.get("delivery_t")
    return ArbPlan(
        arb_id=arb_id(o), strategy=o.strategy, variant=o.variant, asset=o.asset,
        legs=(legs[0], legs[1]), qty=qty, notional=notional, leverage=leverage,
        net_edge=o.net_edge, net_bps=o.net_bps, score=score, annualized=o.annualized,
        horizon_h=o.horizon_h, funding_rate=rate,
        interval_h=float(d["interval_h"]) if d.get("interval_h") else None,
        delivery_t=int(delivery) if isinstance(delivery, int | float) else None,
        exit_cost_bps=exit_cost / notional * 1e4, asof=o.asof, valid_until=o.valid_until,
        source=o.source)


def candidates(sel: Selection, mkt: ArbMarket | None, enabled: tuple[str, ...],
               open_keys: set[str], leverage: int) -> list[ArbPlan]:
    """Planes en orden de puntuación del selector (pb/día ajustados por riesgo)."""
    out: list[ArbPlan] = []
    for r in sel.selected:
        o = r.opportunity
        if o.strategy not in enabled or f"{o.strategy}:{o.asset}" in open_keys:
            continue
        fut = next(lg.symbol for lg in o.legs if lg.market == "usdm")
        prem = mkt.premium.get(fut) if mkt is not None else None
        if o.strategy == "funding_carry" and prem is not None and prem.funding_rate < 0:
            continue
        p = plan_of(o, r.score, mkt, leverage)
        if p is not None:
            out.append(p)
    return out
