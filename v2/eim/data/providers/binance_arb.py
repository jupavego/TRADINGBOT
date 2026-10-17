"""Proveedor de arbitraje Binance por REST público (sin claves): spot y futuros USDⓈ-M/USDC-M.

Libros (`depth`), contratos (`exchangeInfo`: perpetuos y trimestrales), `premiumIndex`
(funding previsto y próxima liquidación) con el intervalo real de `fundingInfo`, e
histórico de funding realizado. El préstamo spot no tiene endpoint público sin clave.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from eim.core import Book, Candle, FuturesContract, PremiumInfo, SpotPair
from eim.data.providers.binance import BinanceFutures

SPOT_URL = "https://api.binance.com"
SPOT_SOURCE = "binance-spot"
FUTURES_SOURCE = "binance-futures"
_QUARTERLY = {"CURRENT_QUARTER", "NEXT_QUARTER"}
_MARGINS = {"USDT", "USDC"}


def _levels(rows: list) -> list[tuple[float, float]]:
    return [(float(p), float(q)) for p, q, *_ in rows]


class BinanceArbData:
    """Lecturas públicas para el motor de arbitraje; reintentos vía `BinanceFutures.request`."""

    def __init__(
        self,
        spot: BinanceFutures | None = None,
        futures: BinanceFutures | None = None,
        *,
        clock: Callable[[], int] = lambda: int(time.time() * 1000),
    ) -> None:
        self.spot = spot or BinanceFutures(base_url=SPOT_URL)
        self.futures = futures or BinanceFutures()
        self.clock = clock

    # --- Contratos --------------------------------------------------------
    def spot_pairs(self) -> list[SpotPair]:
        data = self.spot.request("/api/v3/exchangeInfo")
        return [SpotPair(symbol=s["symbol"], base=s["baseAsset"], quote=s["quoteAsset"])
                for s in data.get("symbols", []) if s.get("status") == "TRADING"]

    def futures_contracts(self) -> list[FuturesContract]:
        data = self.futures.request("/fapi/v1/exchangeInfo")
        out: list[FuturesContract] = []
        for s in data.get("symbols", []):
            ctype, margin = s.get("contractType"), s.get("marginAsset")
            if s.get("status") != "TRADING" or margin not in _MARGINS:
                continue
            if ctype == "PERPETUAL":
                out.append(FuturesContract(symbol=s["symbol"], base=s["baseAsset"],
                                           margin=margin, kind="perpetual"))
            elif ctype in _QUARTERLY:
                out.append(FuturesContract(symbol=s["symbol"], base=s["baseAsset"],
                                           margin=margin, kind="quarterly",
                                           delivery_t=int(s["deliveryDate"])))
        return out

    # --- Libros -----------------------------------------------------------
    def spot_book(self, symbol: str, limit: int = 100) -> tuple[Book, int]:
        """Libro spot y hora de la consulta (spot no devuelve hora de transacción)."""
        data = self.spot.request("/api/v3/depth", {"symbol": symbol, "limit": limit})
        book = Book(bids=_levels(data["bids"]), asks=_levels(data["asks"]), source=SPOT_SOURCE)
        return book, self.clock()

    def futures_book(self, symbol: str, limit: int = 100) -> tuple[Book, int]:
        """Libro de futuros y su hora de transacción `T`."""
        data = self.futures.request("/fapi/v1/depth", {"symbol": symbol, "limit": limit})
        book = Book(bids=_levels(data["bids"]), asks=_levels(data["asks"]),
                    source=FUTURES_SOURCE)
        return book, int(data.get("T") or data.get("E") or self.clock())

    # --- Funding ----------------------------------------------------------
    def funding_intervals(self) -> dict[str, float]:
        """Horas entre liquidaciones de los símbolos ajustados (el resto: 8 h)."""
        rows = self.futures.request("/fapi/v1/fundingInfo")
        return {r["symbol"]: float(r["fundingIntervalHours"]) for r in rows
                if r.get("fundingIntervalHours")}

    def premium_index(self) -> dict[str, PremiumInfo]:
        """Perpetuos con funding previsto (los trimestrales vienen sin funding y se omiten)."""
        intervals = self.funding_intervals()
        out: dict[str, PremiumInfo] = {}
        for r in self.futures.request("/fapi/v1/premiumIndex"):
            rate, nxt = r.get("lastFundingRate"), int(r.get("nextFundingTime") or 0)
            if rate in (None, "") or nxt <= 0:
                continue
            sym = r["symbol"]
            out[sym] = PremiumInfo(symbol=sym, mark=float(r["markPrice"]),
                                   index=float(r["indexPrice"]), funding_rate=float(rate),
                                   next_funding_t=nxt, interval_h=intervals.get(sym, 8.0),
                                   t=int(r["time"]))
        return out

    def funding_history(self, symbol: str, start: int, end: int) -> list[tuple[int, float]]:
        return self.futures.funding_rates(symbol, start, end)

    # --- Histórico (T43) ----------------------------------------------------
    def spot_klines(self, symbol: str, timeframe: str, start: int, end: int) -> list[Candle]:
        return self.spot.klines(symbol, timeframe, start, end, path="/api/v3/klines",
                                limit=1000)

    def symbol_filters(self, symbols: set[str]) -> dict[str, dict[str, float | str]]:
        """Mínimos de orden por símbolo (`exchangeInfo`): paso de cantidad, cantidad mínima y
        nocional mínimo; `market` = spot/futures. Clave `spot:SÍMBOLO` o `futures:SÍMBOLO`."""
        out: dict[str, dict[str, float | str]] = {}
        for market, client, path in (("spot", self.spot, "/api/v3/exchangeInfo"),
                                     ("futures", self.futures, "/fapi/v1/exchangeInfo")):
            for s in client.request(path).get("symbols", []):
                if s.get("symbol") not in symbols:
                    continue
                f = {x.get("filterType"): x for x in s.get("filters", [])}
                lot = f.get("LOT_SIZE", {})
                notional = f.get("MIN_NOTIONAL") or f.get("NOTIONAL") or {}
                min_n = notional.get("notional") or notional.get("minNotional") or 0
                out[f"{market}:{s['symbol']}"] = {
                    "step": float(lot.get("stepSize") or 0),
                    "min_qty": float(lot.get("minQty") or 0), "min_notional": float(min_n),
                    "source": SPOT_SOURCE if market == "spot" else FUTURES_SOURCE}
        return out


class SpotKlines:
    """Adaptador spot para `sync_candles` (misma interfaz `name`/`klines` que el de futuros)."""

    name = SPOT_SOURCE

    def __init__(self, data: BinanceArbData) -> None:
        self.data = data

    def klines(self, symbol: str, timeframe: str, start: int, end: int) -> list[Candle]:
        return self.data.spot_klines(symbol, timeframe, start, end)
