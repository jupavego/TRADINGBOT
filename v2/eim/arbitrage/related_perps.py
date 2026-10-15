"""Perpetuos relacionados: mismo activo en USDⓈ-M (USDT) y USDC-M (USDC).

Se compara en USDT (precio USDC-M × USDCUSDT spot). Largo el barato + corto el caro;
bruto = diferencia a precio medio × cantidad SI se cierra durante la tenencia (no hay
convergencia forzada: riesgo de base ≥ 0.5). Cada pata paga o cobra su propio funding.
"""

from __future__ import annotations

from eim.arbitrage import risk
from eim.arbitrage.common import assemble, finish, flip, leg, mid, missing_book
from eim.arbitrage.funding import expected_path, realized, settlements
from eim.arbitrage.params import ArbParams
from eim.core import ArbMarket, ArbScan, CostModel, Opportunity, PremiumInfo

CONV = "USDCUSDT"


def _funding(mkt: ArbMarket, p: ArbParams, prem: PremiumInfo, h: float) -> tuple[float, int]:
    """Suma de tasas esperadas en la tenencia y nº de tasas realizadas usadas."""
    r_mean, r_n = realized(mkt.funding_hist.get(prem.symbol), mkt.asof, p.funding_realized_n)
    sched = settlements(prem, mkt.asof, h)
    return sum(expected_path(prem, len(sched), r_mean)), r_n


def scan_related_perps(mkt: ArbMarket, cm: CostModel, p: ArbParams) -> ArbScan:
    opps: list[Opportunity] = []
    missing: list[str] = []
    conv = mkt.spot_books.get(CONV)
    r = mid(conv) if conv else None
    if r is None:
        missing.append(missing_book(mkt, f"book:spot:{CONV}", f"libro spot {CONV} "
                                    "(conversión USDC→USDT)"))
        return finish("related_perps", mkt, [], missing, [])
    degraded = False
    h = p.related_horizon_h
    for asset in p.assets:
        pt, pc = mkt.perpetual(asset, "USDT"), mkt.perpetual(asset, "USDC")
        if pt is None or pc is None:
            missing.append(f"perpetuo {asset} {'USDⓈ-M' if pt is None else 'USDC-M'} "
                           "no disponible")
            continue
        tbook, cbook = mkt.futures_books.get(pt.symbol), mkt.futures_books.get(pc.symbol)
        ft, fc = mkt.premium.get(pt.symbol), mkt.premium.get(pc.symbol)
        lacks = [missing_book(mkt, k, label) for k, label, ok in (
            (f"book:usdm:{pt.symbol}", f"libro {pt.symbol}", tbook and mid(tbook)),
            (f"book:usdcm:{pc.symbol}", f"libro {pc.symbol}", cbook and mid(cbook)),
            (f"premium:{pt.symbol}", f"funding previsto {pt.symbol}", ft is not None),
            (f"premium:{pc.symbol}", f"funding previsto {pc.symbol}", fc is not None),
        ) if not ok]
        if lacks:
            missing += lacks
            continue
        assert tbook is not None and cbook is not None and ft is not None and fc is not None
        t_mid, c_usd = mid(tbook) or 0.0, (mid(cbook) or 0.0) * r
        spread = c_usd - t_mid
        sign = 1 if spread >= 0 else -1  # +1: USDC-M caro → corto USDC-M / largo USDT-M
        qty = p.notional_usd / t_mid
        t_side = "buy" if sign > 0 else "sell"
        c_side = flip(t_side)
        legs = [leg(cm, "usdm", pt.symbol, tbook, t_side, qty),
                leg(cm, "usdcm", pc.symbol, cbook, c_side, qty, usd=r),
                leg(cm, "usdm", pt.symbol, tbook, c_side, qty, action="close"),
                leg(cm, "usdcm", pc.symbol, cbook, t_side, qty, action="close", usd=r)]
        sum_t, n_t = _funding(mkt, p, ft, h)
        sum_c, n_c = _funding(mkt, p, fc, h)
        degraded |= n_t == 0 or n_c == 0
        long_t = 1 if t_side == "buy" else -1  # el largo paga funding positivo
        funding = long_t * (sum_t * qty * ft.mark - sum_c * qty * fc.mark * r)
        gross = abs(spread) * qty
        capital = qty * (legs[0].vwap + legs[1].vwap * r) / p.perp_leverage
        shock = max(abs(spread) / t_mid, p.basis_floor_bps / 1e4) * qty * t_mid
        rk = risk.build(
            risk.legging(legs, sequential=False),
            risk.basis(shock, gross, "sin convergencia forzada entre USDT-M y USDC-M; la "
                       "pata USDC añade riesgo de paridad USDC/USDT", floor=0.5),
            risk.liquidation(p, h, leveraged=True),
            risk.liquidity([(legs[0], tbook), (legs[1], cbook)]),
        )
        variant = ("largo USDT-M / corto USDC-M" if sign > 0 else "corto USDT-M / largo USDC-M")
        details = {"spread_bps": spread / t_mid * 1e4, "usdc_usdt": r,
                   "funding_usdt_pred": ft.funding_rate, "funding_usdc_pred": fc.funding_rate,
                   "funding_realized_n_usdt": n_t, "funding_realized_n_usdc": n_c}
        keys = [f"book:usdm:{pt.symbol}", f"book:usdcm:{pc.symbol}", f"book:spot:{CONV}",
                f"premium:{pt.symbol}", f"premium:{pc.symbol}", f"funding:{pt.symbol}",
                f"funding:{pc.symbol}"]
        opps.append(assemble(
            "related_perps", variant, asset, legs, gross, mkt=mkt, keys=keys, capital=capital,
            horizon_h=h, risk=rk, p=p, funding=funding, details=details,
            warnings=["el bruto supone que la diferencia se cierra en la tenencia; salida "
                      "estimada con el libro actual"]))
    return finish("related_perps", mkt, opps, missing, [], degraded=degraded)
