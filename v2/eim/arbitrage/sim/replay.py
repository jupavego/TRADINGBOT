"""Reproducción del motor T38 sobre el histórico (T43).

En cada decisión `t` se arma la fotografía `ArbMarket` que el escáner habría visto y se
valoran las estrategias con el MISMO código de T38 (`scan_*` + `select`):
- libros = perfil real capturado (`DepthModel.rep`) centrado en el cierre de la vela previa
  y adelgazado por el volumen de entonces;
- funding previsto = última tasa realizada (proxy sin mirar al futuro; el `premiumIndex`
  histórico no existe) y media de las realizadas para el resto, como en vivo;
- índice ≈ cierre spot; trimestrales vivos en `t` (máx. 2, como `load_arb_market`).
Así lo que se calibra es el selector tal como opera, no una versión paralela.
"""

from __future__ import annotations

from eim.arbitrage.params import ArbParams
from eim.arbitrage.sim.depth import DepthModel
from eim.arbitrage.sim.frame import H_MS, ArbHistory, Bars, Funding
from eim.arbitrage.sim.params import SimParams
from eim.core import ArbMarket, Book, FuturesContract, PremiumInfo, SpotPair

CONV = "USDCUSDT"


def spot_key(symbol: str) -> str:
    return f"spot:{symbol}"


def quarter_key(asset: str, rank: int) -> str:
    """Perfil del trimestral por posición: Q1 = el más cercano al vencimiento."""
    return f"usdm:{asset}USDT_Q{rank}"


class Replayer:
    def __init__(self, hist: ArbHistory, dm: DepthModel, sp: SimParams, p: ArbParams) -> None:
        self.hist, self.dm, self.sp, self.p = hist, dm, sp, p
        self.funding = {a: Funding.of(h.funding) for a, h in hist.assets.items()}
        self.usdc_funding = {a: Funding.of(h.usdc_funding) for a, h in hist.assets.items()}

    def scale(self, bars: Bars, i: int, key: str) -> float:
        """Adelgazamiento en la vela `i` (la que abre en la decisión)."""
        return bars.vol_scale(i, self.hist.depth_ref_vq.get(key), self.sp.vol_scale_min)

    def market_at(self, t: int) -> ArbMarket:
        st = _State(self, t)
        for asset in self.p.assets:
            h = self.hist.assets.get(asset)
            if h is None:
                st.errors[f"asset:{asset}"] = "sin histórico"
                continue
            spot_sym, perp_sym = f"{asset}USDT", f"{asset}USDT"
            if st.book(spot_key(spot_sym), h.spot, spot=True):
                st.pairs.append(SpotPair(symbol=spot_sym, base=asset, quote="USDT"))
            if st.book(f"usdm:{perp_sym}", h.perp):
                st.contracts.append(FuturesContract(symbol=perp_sym, base=asset, margin="USDT",
                                                    kind="perpetual"))
                st.premium(perp_sym, h.perp, h.spot, self.funding[asset])
            alive = sorted((q for q in h.quarterlies if q.delivery_t > t
                            and q.bars.at(t - H_MS) is not None), key=lambda q: q.delivery_t)
            for rank, q in enumerate(alive[:2], start=1):
                if st.book(quarter_key(asset, rank), q.bars, symbol=q.symbol):
                    st.contracts.append(FuturesContract(
                        symbol=q.symbol, base=asset, margin="USDT", kind="quarterly",
                        delivery_t=q.delivery_t))
            usdc_sym = f"{asset}USDC"
            if h.usdc_perp is not None and st.book(f"usdcm:{usdc_sym}", h.usdc_perp):
                st.contracts.append(FuturesContract(symbol=usdc_sym, base=asset, margin="USDC",
                                                    kind="perpetual"))
                st.premium(usdc_sym, h.usdc_perp, h.spot, self.usdc_funding[asset])
        if st.book(spot_key(CONV), self.hist.usdcusdt, spot=True):
            st.pairs.append(SpotPair(symbol=CONV, base="USDC", quote="USDT"))
        return ArbMarket.model_construct(
            asof=t, spot_pairs=st.pairs, contracts=st.contracts, spot_books=st.spot_books,
            futures_books=st.fut_books, premium=st.prem, funding_hist=st.fhist, borrow_apr={},
            sources=st.sources, coverage=st.coverage, errors=st.errors)


class _State:
    """Acumulador de una fotografía (libros, contratos, funding, fuentes y faltantes)."""

    def __init__(self, rp: Replayer, t: int) -> None:
        self.rp, self.t = rp, t
        self.pairs: list[SpotPair] = []
        self.contracts: list[FuturesContract] = []
        self.spot_books: dict[str, Book] = {}
        self.fut_books: dict[str, Book] = {}
        self.prem: dict[str, PremiumInfo] = {}
        self.fhist: dict[str, list[tuple[int, float]]] = {}
        self.sources: dict[str, str] = {}
        self.coverage: dict[str, tuple[int, int]] = {}
        self.errors: dict[str, str] = {}

    def book(self, key: str, bars: Bars | None, *, spot: bool = False,
             symbol: str | None = None) -> bool:
        """Libro sintético en la clave del motor T38 (`book:<mercado>:<símbolo>`)."""
        market, _, sym = key.partition(":")
        sym = symbol or sym
        bkey = f"book:{market}:{sym}"
        prof = self.rp.dm.rep(key)
        i = bars.at(self.t - H_MS) if bars is not None else None
        if bars is None or i is None:
            self.errors[bkey] = "sin vela cerrada en la hora previa"
            return False
        if prof is None:
            self.errors[bkey] = "sin perfil de profundidad capturado"
            return False
        scale = self.rp.scale(bars, i + 1, key) * self.rp.sp.depth_scale
        book = prof.to_book(float(bars.c[i]), scale)
        (self.spot_books if spot else self.fut_books)[sym] = book
        self.sources[bkey] = f"{bars.source} 1h + {prof.source} (perfil)"
        self.coverage[bkey] = (int(bars.t[i]), int(bars.t[i]))
        return True

    def premium(self, sym: str, perp: Bars, spot: Bars | None, fs: Funding) -> None:
        """Funding previsto = última realizada (proxy); marca = cierre; índice ≈ spot."""
        i = perp.at(self.t - H_MS)
        nxt = fs.next_after(self.t)
        past = fs.before(self.t, self.rp.p.funding_realized_n)
        if i is None or nxt is None or not past:
            self.errors[f"premium:{sym}"] = "sin funding realizado o calendario"
            return
        j = spot.at(self.t - H_MS) if spot is not None else None
        index = float(spot.c[j]) if spot is not None and j is not None else float(perp.c[i])
        self.prem[sym] = PremiumInfo(symbol=sym, mark=float(perp.c[i]), index=index,
                                     funding_rate=past[-1][1], next_funding_t=nxt,
                                     interval_h=fs.interval_h(self.t), t=self.t)
        self.fhist[sym] = past
        self.sources[f"premium:{sym}"] = "proxy: última tasa realizada (histórico)"
        self.sources[f"funding:{sym}"] = perp.source
        self.coverage[f"premium:{sym}"] = (self.t, self.t)
        self.coverage[f"funding:{sym}"] = (past[0][0], past[-1][0])
