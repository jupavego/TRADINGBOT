"""Lo realizado de cada oportunidad del motor T38 sobre el histórico (T43).

Entrada en la apertura de la vela de decisión con la cantidad que propuso el motor; luego
cada estrategia sigue su regla de salida:
- carry de funding: largo spot / corto perpetuo durante `carry_horizon_h`;
- base spot/trimestral: hasta el vencimiento (liquida al precio real de liquidación);
- base perpetuo/trimestral: hasta el vencimiento; el perpetuo paga o cobra funding;
- perpetuos relacionados: hasta que la diferencia cierra o `related_horizon_h`.
Las variantes con préstamo spot no se simulan (no hay histórico de tasas de préstamo).
"""

from __future__ import annotations

import numpy as np

from eim.arbitrage.sim.frame import H_MS, AssetHistory, Bars, Quarterly
from eim.arbitrage.sim.hedge import Side_, align, futures_pair, spot_short
from eim.arbitrage.sim.replay import Replayer, quarter_key, spot_key
from eim.arbitrage.sim.trade import Executor, SimTrade
from eim.core import Opportunity
from eim.core.arbitrage import MarketKind


class Realizer:
    def __init__(self, rp: Replayer, ex: Executor) -> None:
        self.rp, self.ex = rp, ex
        self.hist, self.sp, self.p = rp.hist, rp.sp, rp.p

    def _side(self, bars: Bars, key: str, market: MarketKind,
              usd: Bars | None = None) -> Side_:
        return Side_(bars=bars, key=key, market=market,
                     ref_vq=self.hist.depth_ref_vq.get(key), usd=usd)

    def _trade(self, o: Opportunity, t: int, instrument: str) -> SimTrade:
        lg = o.legs[0]
        return SimTrade(strategy=o.strategy, variant=o.variant, asset=o.asset,
                        instrument=instrument, entry_t=t, capital=o.capital_required,
                        notional=lg.qty * lg.mid)

    def run(self, o: Opportunity, t: int) -> tuple[SimTrade | None, str | None]:
        """(operación, motivo si no se pudo simular)."""
        h = self.hist.assets.get(o.asset)
        if h is None:
            return None, "sin histórico del activo"
        if "préstamo" in o.variant:
            return None, "variante con préstamo spot: sin histórico de tasas"
        if o.strategy == "funding_carry":
            return self._carry(o, t, h)
        if o.strategy == "basis":
            return self._basis(o, t, h)
        if o.strategy == "related_perps":
            return self._related(o, t, h)
        return None, f"estrategia {o.strategy} sin simulador de tenencia"

    def _carry(self, o: Opportunity, t: int, h: AssetHistory):
        if h.spot is None or h.perp is None:
            return None, "faltan velas spot o del perpetuo"
        exit_t = t + int(self.p.carry_horizon_h * H_MS)
        if h.perp.at(exit_t) is None or h.spot.at(exit_t) is None:
            return None, "la tenencia sale del histórico"
        sym = f"{o.asset}USDT"
        tr = spot_short(self._trade(o, t, sym), self.ex, self.sp, self.p,
                        self._side(h.spot, spot_key(sym), "spot"),
                        self._side(h.perp, f"usdm:{sym}", "usdm"), q=o.legs[0].qty,
                        exit_t=exit_t, funding=self.rp.funding[o.asset])
        return tr, None if tr is not None else "velas desalineadas en la entrada"

    def _quarter(self, o: Opportunity, h: AssetHistory) -> tuple[Quarterly | None, int]:
        sym = o.legs[1].symbol
        alive = sorted((q for q in h.quarterlies if q.delivery_t > o.asof),
                       key=lambda q: q.delivery_t)
        for rank, q in enumerate(alive, start=1):
            if q.symbol == sym:
                return q, rank
        return None, 0

    def _basis(self, o: Opportunity, t: int, h: AssetHistory):
        q, rank = self._quarter(o, h)
        if q is None:
            return None, "trimestral no encontrado"
        if q.settle is None:
            return None, f"{q.symbol}: sin precio de liquidación (aún no vence o falta)"
        if (q.delivery_t - t) / (24 * H_MS) < self.sp.min_days_to_expiry:
            return None, "a menos de los días mínimos del vencimiento"
        qside = self._side(q.bars, quarter_key(o.asset, rank), "usdm")
        qty = o.legs[0].qty
        if o.variant.startswith("largo spot"):
            if h.spot is None:
                return None, "faltan velas spot"
            sym = f"{o.asset}USDT"
            tr = spot_short(self._trade(o, t, q.symbol), self.ex, self.sp, self.p,
                            self._side(h.spot, spot_key(sym), "spot"), qside, q=qty,
                            exit_t=q.delivery_t, settle=q.settle)
        else:
            if h.perp is None:
                return None, "faltan velas del perpetuo"
            sym = f"{o.asset}USDT"
            perp = self._side(h.perp, f"usdm:{sym}", "usdm")
            long_perp = o.variant.startswith("largo perpetuo")
            tr = futures_pair(self._trade(o, t, q.symbol), self.ex, self.sp, self.p,
                              perp if long_perp else qside, qside if long_perp else perp,
                              q=qty, exit_t=q.delivery_t, first_long=not long_perp,
                              funding={perp.key: self.rp.funding[o.asset]}, settle=q.settle,
                              settle_long=not long_perp)
        return tr, None if tr is not None else "velas desalineadas en la entrada"

    def _related(self, o: Opportunity, t: int, h: AssetHistory):
        conv = self.hist.usdcusdt
        if h.perp is None or h.usdc_perp is None or conv is None:
            return None, "faltan velas USDT-M, USDC-M o USDCUSDT"
        exit_t = t + int(self.p.related_horizon_h * H_MS)
        if h.perp.at(exit_t) is None or h.usdc_perp.at(exit_t) is None:
            return None, "la tenencia sale del histórico"
        a = o.asset
        usdt = self._side(h.perp, f"usdm:{a}USDT", "usdm")
        usdc = self._side(h.usdc_perp, f"usdcm:{a}USDC", "usdcm", usd=conv)
        long_usdt = o.variant.startswith("largo USDT")
        long, short = (usdt, usdc) if long_usdt else (usdc, usdt)
        ts, li, si = align(long.bars, short.bars, t, exit_t)
        stop = None
        if len(ts):
            r = np.array([usdc.usd_at(int(x)) for x in ts])
            c_usdc = (long if not long_usdt else short).bars.c[si if long_usdt else li]
            p_usdt = (long if long_usdt else short).bars.c[li if long_usdt else si]
            spread_bps = (c_usdc * r - p_usdt) / p_usdt * 1e4
            sgn = 1.0 if long_usdt else -1.0  # +1: USDC-M caro → gana si la diferencia baja
            stop = sgn * spread_bps <= self.sp.related_exit_bps
        fund = {usdt.key: self.rp.funding[a], usdc.key: self.rp.usdc_funding[a]}
        tr = futures_pair(self._trade(o, t, f"{a}USDT/{a}USDC"), self.ex, self.sp, self.p,
                          long, short, q=o.legs[0].qty, exit_t=exit_t,
                          first_long=not long_usdt, funding=fund, stop=stop)
        return tr, None if tr is not None else "velas desalineadas en la entrada"

