"""Filas serializables del escáner: oportunidades con su desglose, funding, base y descartes.

Las comparten el agente (`metrics`, versión compacta) y la API (tabla completa de la UI).
Los importes salen tal cual del motor T38: aquí no se recalcula ningún costo.
"""

from __future__ import annotations

from collections import Counter

from eim.arbitrage.alerts import opp_key
from eim.arbitrage.common import mid
from eim.arbitrage.funding import realized
from eim.arbitrage.scan import ArbResult
from eim.arbitrage.selector import Ranked, Rejected
from eim.core import ArbMarket, Leg, Opportunity

DAY_MS = 86_400_000
SIDE = {"buy": "compra", "sell": "venta"}
MARKET = {"spot": "spot", "usdm": "USDⓈ-M", "usdcm": "USDC-M"}
STRATEGY = {"funding_carry": "Carry de funding", "basis": "Base / cash-and-carry",
            "triangular": "Triangular spot", "related_perps": "USDT-M vs USDC-M"}
REJECT = {"informative": "informativa (fuera de alcance, T33)",
          "incomplete": "pata incompleta en el libro visible", "stale": "precio caducado",
          "below_min": "neto bajo el mínimo", "illiquid": "liquidez insuficiente"}


def _r(x: float | None, nd: int) -> float | None:
    return None if x is None else round(x, nd)


def leg_text(lg: Leg) -> str:
    out = f"{SIDE[lg.side]} {MARKET[lg.market]} {lg.symbol}"
    if lg.action == "open":
        return out
    # trimestral liquidado contra el índice: sin libro (`settle_leg` de T38)
    settles = lg.levels == 0 and lg.filled > 0 and lg.slippage == 0
    return out + (" (liquidación al vencimiento)" if settles else " (salida)")


def leg_row(lg: Leg) -> dict:
    return {"text": leg_text(lg), "market": lg.market, "symbol": lg.symbol, "side": lg.side,
            "action": lg.action, "qty": lg.qty, "filled": lg.filled, "vwap": lg.vwap,
            "mid": lg.mid, "fee_rate": lg.fee_rate, "fee": lg.fee, "slippage": lg.slippage,
            "levels": lg.levels, "complete": lg.complete}


def opportunity_row(o: Opportunity, *, full: bool, score: float | None = None,
                    code: str | None = None, reason: str | None = None) -> dict:
    """`full` = cifras exactas del motor, patas con precios, notas de riesgo, detalles y
    avisos (tabla de la UI); compacta = redondeada para `metrics` (se guarda por reporte)."""
    c, r = o.costs, o.risk
    usd, bps, frac = (None, None, None) if full else (2, 2, 6)

    def k(x: float | None, nd: int | None) -> float | None:
        return x if nd is None else _r(x, nd)

    risk = {n: k(getattr(r, n), frac) for n in ("legging", "basis", "liquidation", "liquidity")}
    row = {
        "id": opp_key(o), "strategy": o.strategy, "variant": o.variant, "asset": o.asset,
        "legs": [leg_row(lg) for lg in o.legs] if full else [leg_text(lg) for lg in o.legs],
        "gross": k(o.gross_edge, usd),
        "costs": {"fees": k(c.fees, usd), "slippage": k(c.slippage, usd),
                  "funding": k(c.funding, usd), "borrow": k(c.borrow, usd),
                  "total": k(c.total, usd)},
        "net": k(o.net_edge, usd), "net_bps": k(o.net_bps, bps),
        "annualized": k(o.annualized, frac), "capital": k(o.capital_required, usd),
        "horizon_h": k(o.horizon_h, bps), "risk": risk,
        "valid_until": o.valid_until, "executable": o.executable, "source": o.source,
        "selected": code is None, "score": k(score, bps), "reject_code": code,
        "reason": reason,
    }
    if full:
        row["risk_notes"] = dict(r.notes)
        row["details"] = dict(o.details)
        row["warnings"] = list(o.warnings)
        row["coverage"] = dict(o.coverage)
    return row


def ranked_row(r: Ranked, *, full: bool) -> dict:
    return opportunity_row(r.opportunity, full=full, score=r.score)


def rejected_row(r: Rejected, *, full: bool) -> dict:
    return opportunity_row(r.opportunity, full=full, code=r.code, reason=r.reason)


def all_rows(res: ArbResult) -> list[dict]:
    """Tabla completa: seleccionadas (por puntuación) y luego descartadas (por neto)."""
    sel = res.selection
    return ([ranked_row(r, full=True) for r in sel.selected]
            + [rejected_row(r, full=True) for r in sel.rejected])


def rejected_summary(res: ArbResult) -> tuple[dict[str, int], list[dict]]:
    """Recuento por motivo y lista compacta (por qué se descartó cada una)."""
    rej = res.selection.rejected
    counts = dict(Counter(r.code for r in rej))
    items = [{"id": opp_key(r.opportunity), "strategy": r.opportunity.strategy,
              "asset": r.opportunity.asset, "variant": r.opportunity.variant,
              "net_bps": _r(r.opportunity.net_bps, 2), "code": r.code, "reason": r.reason}
             for r in rej]
    return counts, items


def funding_table(mkt: ArbMarket, n: int) -> dict[str, dict]:
    """Funding actual/próximo por perpetuo, realizado medio y su histórico corto."""
    out: dict[str, dict] = {}
    for c in mkt.contracts:
        if c.kind != "perpetual":
            continue
        prem = mkt.premium.get(c.symbol)
        hist = [(t, r) for t, r in mkt.funding_hist.get(c.symbol, []) if t <= mkt.asof][-n:]
        r_mean, r_n = realized(hist, mkt.asof, n)
        row: dict = {"symbol": c.symbol, "margin": c.margin, "history": [list(h) for h in hist],
                     "realized_mean": _r(r_mean, 10), "realized_n": r_n,
                     "coverage": mkt.coverage.get(f"funding:{c.symbol}"),
                     "source": mkt.sources.get(f"premium:{c.symbol}")}
        if prem is None:
            row |= {"predicted": None,
                    "error": mkt.errors.get(f"premium:{c.symbol}", "sin premiumIndex")}
        else:
            per_year = 8760.0 / prem.interval_h
            row |= {"predicted": prem.funding_rate,
                    "predicted_annual": _r(prem.funding_rate * per_year, 6),
                    "realized_annual": _r(r_mean * per_year, 6) if r_mean is not None else None,
                    "next_funding_t": prem.next_funding_t, "interval_h": prem.interval_h,
                    "mark": prem.mark, "index": prem.index,
                    "premium_bps": _r((prem.mark - prem.index) / prem.index * 1e4, 3)}
        out[c.symbol] = row
    return out


def basis_table(mkt: ArbMarket, assets: tuple[str, ...]) -> list[dict]:
    """Base de cada trimestral USDⓈ-M y del perpetuo frente al spot (precios medios);
    anualizada solo la del trimestral (converge al vencimiento)."""
    rows: list[dict] = []
    for asset in assets:
        spot_sym = mkt.spot_symbol(asset, "USDT")
        s_mid = mid(mkt.spot_books[spot_sym]) if spot_sym in mkt.spot_books else None
        if s_mid is None:
            rows.append({"asset": asset, "contract": None, "vs": spot_sym,
                         "error": "sin libro spot: base no calculable"})
            continue
        perp = mkt.perpetual(asset, "USDT")
        targets = ([(perp.symbol, None)] if perp else []) + [
            (q.symbol, q.delivery_t) for q in mkt.quarterlies(asset, "USDT")]
        for sym, delivery in targets:
            book = mkt.futures_books.get(sym)
            f_mid = mid(book) if book is not None else None
            if f_mid is None:
                rows.append({"asset": asset, "contract": sym, "vs": spot_sym,
                             "error": "sin libro del contrato"})
                continue
            b = (f_mid - s_mid) / s_mid
            days = (delivery - mkt.asof) / DAY_MS if delivery else None
            rows.append({"asset": asset, "contract": sym, "vs": spot_sym, "kind":
                         "quarterly" if delivery else "perpetual", "delivery_t": delivery,
                         "days": _r(days, 3), "basis_bps": round(b * 1e4, 3),
                         "annualized": _r(b * 365 / days, 6) if days and days > 0 else None})
    return rows


def scans_summary(res: ArbResult) -> list[dict]:
    return [{"strategy": s.strategy, "label": STRATEGY[s.strategy], "status": s.status,
             "valued": len(s.opportunities), "missing": s.missing, "warnings": s.warnings}
            for s in res.scans]
