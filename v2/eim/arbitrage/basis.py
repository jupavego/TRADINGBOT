"""Base / cash-and-carry hasta el vencimiento del trimestral USDⓈ-M.

- spot vs trimestral: largo spot + corto trimestral si cotiza con prima (contango); la
  inversa exige préstamo spot. Al vencer, el trimestral liquida contra el índice.
- perpetuo vs trimestral: largo el barato + corto el caro; el perpetuo paga/cobra funding
  hasta el vencimiento (costo `funding`, prevista + media realizada extrapolada).
Bruto = diferencia a precio medio × cantidad (converge por liquidación del trimestral).
"""

from __future__ import annotations

from eim.arbitrage import risk
from eim.arbitrage.common import assemble, finish, flip, leg, mid, missing_book, settle_leg
from eim.arbitrage.funding import expected_path, realized, settlements
from eim.arbitrage.params import ArbParams
from eim.core import ArbMarket, ArbScan, CostModel, FuturesContract, Opportunity

DAY_MS = 86_400_000


def scan_basis(mkt: ArbMarket, cm: CostModel, p: ArbParams) -> ArbScan:
    opps: list[Opportunity] = []
    missing: list[str] = []
    warns: list[str] = []
    for asset in p.assets:
        qs = mkt.quarterlies(asset, "USDT")
        if not qs:
            missing.append(f"trimestral {asset}USDT no disponible")
            continue
        for q in qs:
            k_q = f"book:usdm:{q.symbol}"
            qbook = mkt.futures_books.get(q.symbol)
            if qbook is None or mid(qbook) is None:
                missing.append(missing_book(mkt, k_q, f"libro trimestral {q.symbol}"))
                continue
            opps += _spot_vs_quarterly(mkt, cm, p, asset, q, missing, warns)
            opps += _perp_vs_quarterly(mkt, cm, p, asset, q, missing, warns)
    return finish("basis", mkt, opps, missing, warns)


def _horizon(mkt: ArbMarket, q: FuturesContract) -> float:
    return ((q.delivery_t or mkt.asof) - mkt.asof) / 3_600_000


def _spot_vs_quarterly(mkt: ArbMarket, cm: CostModel, p: ArbParams, asset: str,
                       q: FuturesContract, missing: list[str],
                       warns: list[str]) -> list[Opportunity]:
    spot_sym = mkt.spot_symbol(asset, "USDT")
    sbook = mkt.spot_books.get(spot_sym or "")
    if spot_sym is None or sbook is None or mid(sbook) is None:
        missing.append(missing_book(mkt, f"book:spot:{spot_sym}", f"libro spot {asset}USDT"))
        return []
    qbook = mkt.futures_books[q.symbol]
    s_mid, f_mid = mid(sbook) or 0.0, mid(qbook) or 0.0
    qty = p.notional_usd / s_mid
    h = _horizon(mkt, q)
    sign = 1 if f_mid >= s_mid else -1  # +1: largo spot / corto trimestral
    apr = mkt.borrow_apr.get(asset)
    if sign < 0 and apr is None:
        warns.append(f"{q.symbol} en descuento: la inversa (corto spot) no se evalúa sin tasa "
                     "de préstamo")
        return []
    s_side = "buy" if sign > 0 else "sell"
    legs = [leg(cm, "spot", spot_sym, sbook, s_side, qty),
            leg(cm, "usdm", q.symbol, qbook, flip(s_side), qty),
            leg(cm, "spot", spot_sym, sbook, flip(s_side), qty, action="close"),
            settle_leg(cm, q.symbol, s_side, qty, s_mid)]
    gross = sign * (f_mid - s_mid) * qty
    borrow = qty * s_mid * apr * h / 8760.0 if sign < 0 and apr is not None else 0.0
    capital = qty * legs[0].vwap + qty * legs[1].vwap / p.perp_leverage
    perp = mkt.perpetual(asset, "USDT")
    prem = mkt.premium.get(perp.symbol) if perp else None
    idx_gap = abs(prem.index - s_mid) / s_mid if prem else 0.0
    shock = max(idx_gap, p.basis_floor_bps / 1e4) * qty * s_mid
    rk = risk.build(
        risk.legging(legs, sequential=False),
        risk.basis(shock, gross, "converge al vencimiento (liquida contra el índice); queda la "
                   "diferencia índice–spot de Binance y el riesgo de salir antes"),
        risk.liquidation(p, h, leveraged=True),
        risk.liquidity([(legs[0], sbook), (legs[1], qbook)]),
    )
    variant = ("largo spot / corto trimestral" if sign > 0
               else "corto spot (préstamo) / largo trimestral")
    details = {"delivery_t": q.delivery_t, "days_to_expiry": round(h / 24, 2),
               "basis_bps": (f_mid - s_mid) / s_mid * 1e4, "borrow_apr": apr if sign < 0 else None}
    return [assemble("basis", variant, asset, legs, gross, mkt=mkt,
                     keys=[f"book:spot:{spot_sym}", f"book:usdm:{q.symbol}"], capital=capital,
                     horizon_h=h, risk=rk, p=p, borrow=borrow, details=details,
                     warnings=["salida del spot estimada con el libro actual"])]


def _perp_vs_quarterly(mkt: ArbMarket, cm: CostModel, p: ArbParams, asset: str,
                       q: FuturesContract, missing: list[str],
                       warns: list[str]) -> list[Opportunity]:
    perp = mkt.perpetual(asset, "USDT")
    pbook = mkt.futures_books.get(perp.symbol) if perp else None
    prem = mkt.premium.get(perp.symbol) if perp else None
    if perp is None or pbook is None or mid(pbook) is None or prem is None:
        sym = perp.symbol if perp else f"{asset}USDT"
        what = "libro" if prem is not None else "libro o funding previsto"
        missing.append(missing_book(mkt, f"book:usdm:{sym}", f"{what} del perpetuo {sym}"))
        return []
    qbook = mkt.futures_books[q.symbol]
    p_mid, f_mid = mid(pbook) or 0.0, mid(qbook) or 0.0
    qty = p.notional_usd / p_mid
    h = _horizon(mkt, q)
    sign = 1 if f_mid >= p_mid else -1  # +1: largo perpetuo / corto trimestral
    p_side = "buy" if sign > 0 else "sell"
    legs = [leg(cm, "usdm", perp.symbol, pbook, p_side, qty),
            leg(cm, "usdm", q.symbol, qbook, flip(p_side), qty),
            leg(cm, "usdm", perp.symbol, pbook, flip(p_side), qty, action="close"),
            settle_leg(cm, q.symbol, p_side, qty, prem.index)]
    r_mean, r_n = realized(mkt.funding_hist.get(perp.symbol), mkt.asof, p.funding_realized_n)
    sched = settlements(prem, mkt.asof, h)
    rates = expected_path(prem, len(sched), r_mean)
    funding = sign * sum(rates) * qty * prem.mark  # el largo paga funding positivo
    gross = sign * (f_mid - p_mid) * qty
    capital = qty * (legs[0].vwap + legs[1].vwap) / p.perp_leverage
    gap = abs(prem.mark - prem.index) / prem.index
    f_shock = len(sched) * p.funding_shock_rate
    shock = (max(gap, p.basis_floor_bps / 1e4) + f_shock) * qty * p_mid
    rk = risk.build(
        risk.legging(legs, sequential=False),
        risk.basis(shock, gross, "el trimestral converge al índice, el perpetuo no: queda su "
                   f"prima al vencimiento y un desvío de funding de {f_shock:.2%} del nocional "
                   f"({len(sched)} liquidaciones × {p.funding_shock_rate:.2%})"),
        risk.liquidation(p, h, leveraged=True),
        risk.liquidity([(legs[0], pbook), (legs[1], qbook)]),
    )
    w = [f"funding de {len(sched)} liquidaciones extrapolado (prevista + media realizada "
         f"de {r_n})"] if r_mean is not None else [
        "sin funding realizado: se extrapola la tasa prevista hasta el vencimiento"]
    variant = ("largo perpetuo / corto trimestral" if sign > 0
               else "corto perpetuo / largo trimestral")
    details = {"delivery_t": q.delivery_t, "days_to_expiry": round(h / 24, 2),
               "spread_bps": (f_mid - p_mid) / p_mid * 1e4, "settlements": len(sched),
               "funding_predicted": prem.funding_rate, "funding_realized_mean": r_mean}
    return [assemble("basis", variant, asset, legs, gross, mkt=mkt,
                     keys=[f"book:usdm:{perp.symbol}", f"book:usdm:{q.symbol}",
                           f"premium:{perp.symbol}", f"funding:{perp.symbol}"],
                     capital=capital, horizon_h=h, risk=rk, p=p, funding=funding,
                     details=details, warnings=w)]
