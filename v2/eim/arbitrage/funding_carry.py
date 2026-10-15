"""Carry de funding: largo spot + corto perpetuo USDⓈ-M (y la inversa si hay préstamo).

Bruto = funding esperado en las liquidaciones que cruza la tenencia (prevista para la
próxima, media realizada para las demás) sobre el nocional a precio de marca. Costos =
comisiones y deslizamiento de entrada y de salida estimada con el libro actual, más el
interés del préstamo en la inversa. La base no se suma al bruto: es riesgo declarado.
"""

from __future__ import annotations

from eim.arbitrage import risk
from eim.arbitrage.common import assemble, finish, flip, leg, mid, missing_book
from eim.arbitrage.funding import comparison, expected_path, realized, settlements
from eim.arbitrage.params import ArbParams
from eim.core import ArbMarket, ArbScan, Book, CostModel, Opportunity, PremiumInfo

H_MS = 3_600_000


def scan_funding_carry(mkt: ArbMarket, cm: CostModel, p: ArbParams) -> ArbScan:
    opps: list[Opportunity] = []
    missing: list[str] = []
    warns: list[str] = []
    degraded = False
    for asset in p.assets:
        perp, spot_sym = mkt.perpetual(asset, "USDT"), mkt.spot_symbol(asset, "USDT")
        if perp is None or spot_sym is None:
            what = f"perpetuo {asset}USDT" if perp is None else f"par spot {asset}USDT"
            missing.append(f"{what} no disponible" + (
                f" ({mkt.errors['contracts']})" if "contracts" in mkt.errors else ""))
            continue
        k_s, k_p = f"book:spot:{spot_sym}", f"book:usdm:{perp.symbol}"
        k_prem, k_f = f"premium:{perp.symbol}", f"funding:{perp.symbol}"
        sbook, pbook = mkt.spot_books.get(spot_sym), mkt.futures_books.get(perp.symbol)
        prem = mkt.premium.get(perp.symbol)
        lacks = [missing_book(mkt, k, label) for k, label, ok in (
            (k_s, f"libro spot {spot_sym}", sbook is not None and mid(sbook) is not None),
            (k_p, f"libro perpetuo {perp.symbol}", pbook is not None and mid(pbook) is not None),
            (k_prem, f"funding previsto (premiumIndex) {perp.symbol}", prem is not None),
        ) if not ok]
        if lacks:
            missing += lacks
            continue
        assert sbook is not None and pbook is not None and prem is not None
        r_mean, r_n = realized(mkt.funding_hist.get(perp.symbol), mkt.asof, p.funding_realized_n)
        degraded |= r_mean is None
        sched = settlements(prem, mkt.asof, p.carry_horizon_h)
        rates = expected_path(prem, len(sched), r_mean)
        s_mid = mid(sbook) or 0.0
        qty = p.notional_usd / s_mid
        base_warns = comparison(prem, r_mean, r_n)
        nxt = sched[0] if sched else prem.next_funding_t
        if not sched:
            base_warns.append(f"la tenencia de {p.carry_horizon_h:g} h no cruza ninguna "
                              f"liquidación (próxima en {(nxt - mkt.asof) / 60_000:.0f} min)")
        realized_rate = prem.funding_rate if r_mean is None else r_mean
        details = {
            "settlements": len(sched), "interval_h": prem.interval_h, "next_funding_t": nxt,
            "minutes_to_next": round((nxt - mkt.asof) / 60_000, 1),
            "funding_predicted": prem.funding_rate, "funding_realized_mean": r_mean,
            "funding_realized_n": r_n,
            "gross_if_realized": realized_rate * len(sched) * qty * prem.mark,
            "entry_basis_bps": ((mid(pbook) or s_mid) - s_mid) / s_mid * 1e4,
        }
        keys = [k_s, k_p, k_prem, k_f]
        common = dict(mkt=mkt, cm=cm, p=p, asset=asset, spot_sym=spot_sym, perp_sym=perp.symbol,
                      sbook=sbook, pbook=pbook, prem=prem, qty=qty, rates=rates, keys=keys,
                      until=sched[0] if sched else None)
        opps.append(_variant(**common, sign=1, apr=None, details=details, warns=base_warns))
        apr = mkt.borrow_apr.get(asset)
        if apr is None:
            warns.append(f"{asset}: carry inverso (corto spot + largo perpetuo) no evaluado: "
                         "sin tasa de préstamo (no hay API pública sin clave; configurarla)")
        else:
            opps.append(_variant(**common, sign=-1, apr=apr, details={**details,
                                 "borrow_apr": apr}, warns=base_warns + [
                "préstamo spot: tasa configurada a mano, puede cambiar cada hora"]))
    return finish("funding_carry", mkt, opps, missing, warns, degraded=degraded)


def _variant(*, mkt: ArbMarket, cm: CostModel, p: ArbParams, asset: str, spot_sym: str,
             perp_sym: str, sbook: Book, pbook: Book, prem: PremiumInfo, qty: float,
             rates: list[float], keys: list[str], until: int | None, sign: int,
             apr: float | None, details: dict, warns: list[str]) -> Opportunity:
    """sign=+1: largo spot / corto perpetuo (cobra funding positivo); −1: la inversa."""
    s_side = "buy" if sign > 0 else "sell"
    p_side = flip(s_side)
    legs = [leg(cm, "spot", spot_sym, sbook, s_side, qty),
            leg(cm, "usdm", perp_sym, pbook, p_side, qty),
            leg(cm, "spot", spot_sym, sbook, flip(s_side), qty, action="close"),
            leg(cm, "usdm", perp_sym, pbook, flip(p_side), qty, action="close")]
    h = p.carry_horizon_h
    gross = sign * sum(rates) * qty * prem.mark
    s_mid = legs[0].mid
    borrow = qty * s_mid * apr * h / 8760.0 if apr is not None else 0.0
    capital = qty * legs[0].vwap + qty * legs[1].vwap / p.perp_leverage
    entry_basis = abs(legs[1].mid - s_mid) / s_mid
    shock_bps = max(entry_basis * 1e4, p.basis_floor_bps)
    shock = shock_bps / 1e4 * qty * s_mid
    rk = risk.build(
        risk.legging(legs, sequential=False),
        risk.basis(shock, gross, f"un cambio de base de {shock_bps:.1f} pb al salir equivale a "
                   "esa fracción del bruto (no converge por contrato)"),
        risk.liquidation(p, h, leveraged=True),
        risk.liquidity([(legs[0], sbook), (legs[1], pbook)]),
    )
    variant = ("largo spot / corto perpetuo" if sign > 0
               else "corto spot (préstamo) / largo perpetuo")
    return assemble("funding_carry", variant, asset, legs, gross, mkt=mkt, keys=keys,
                    capital=capital, horizon_h=h, risk=rk, p=p, borrow=borrow,
                    valid_until=until, details=details, warnings=warns)
