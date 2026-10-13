"""OHLCV multi-activo para el visor y la estacionalidad (todo el I/O; migrado de F7).

Fuentes reales, nada sintético: cripto y oro (XAUUSDT, perpetuo TradFi de Binance) vía Binance
Futuros; S&P 500 y Nasdaq Composite vía Yahoo Finance (`yfinance`, importado solo si se pide).
Yahoo no tiene velas de 4 h, por eso los índices ofrecen 1d/1wk/1mo y no se fabrica ninguna.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from eim.core import Candle
from eim.data.providers.binance import BinanceFutures

BINANCE_STEP_MS = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
_BINANCE_SRC = "binance futures (fapi/v1/klines)"
_YAHOO_SRC = "yahoo finance (yfinance)"
_YAHOO_LOOKBACK_DAYS = {
    "1d": lambda n: int(n * 1.6) + 15,
    "1wk": lambda n: n * 7 + 30,
    "1mo": lambda n: n * 31 + 60,
}


@dataclass(frozen=True)
class AssetSpec:
    label: str
    source: str  # "binance" | "yahoo"
    ticker: str
    intervals: tuple[str, ...]


ASSETS: dict[str, AssetSpec] = {
    "ETHUSDT": AssetSpec("Ethereum (ETHUSDT)", "binance", "ETHUSDT", ("1h", "4h", "1d")),
    "BTCUSDT": AssetSpec("Bitcoin (BTCUSDT)", "binance", "BTCUSDT", ("1h", "4h", "1d")),
    "XAUUSDT": AssetSpec("Oro (XAUUSDT — futuro Binance)", "binance", "XAUUSDT",
                         ("1h", "4h", "1d")),
    "SP500": AssetSpec("S&P 500 (^GSPC, Yahoo Finance)", "yahoo", "^GSPC", ("1d", "1wk", "1mo")),
    "NASDAQ": AssetSpec("Nasdaq Composite (^IXIC, Yahoo Finance)", "yahoo", "^IXIC",
                        ("1d", "1wk", "1mo")),
}


def list_assets() -> list[dict]:
    return [{"key": k, "label": s.label, "source": s.source, "intervals": list(s.intervals)}
            for k, s in ASSETS.items()]


def spec_of(asset_key: str) -> AssetSpec:
    try:
        return ASSETS[asset_key.upper()]
    except KeyError:
        raise ValueError(
            f"Activo '{asset_key}' no soportado. Disponibles: {', '.join(ASSETS)}") from None


def _binance_klines(client: BinanceFutures, symbol: str, interval: str, *, start: int | None,
                    limit: int) -> list[Candle]:
    """Velas CERRADAS (la vela en formación se descarta) para cualquier intervalo Binance."""
    params: dict = {"symbol": symbol, "interval": interval, "limit": limit}
    if start is not None:
        params["startTime"] = start
    rows = client._get("/fapi/v1/klines", params)  # noqa: SLF001 — reutiliza reintentos y tasa
    now = int(time.time() * 1000)
    step = BINANCE_STEP_MS.get(interval)
    out = []
    for r in rows:
        t = int(r[0])
        if step is not None and t + step > now:
            continue
        out.append(Candle(t=t, o=float(r[1]), h=float(r[2]), l=float(r[3]), c=float(r[4]),
                          v=float(r[5])))
    return out


def _yahoo_history(ticker: str, interval: str, start: datetime, end: datetime | None = None):
    import yfinance as yf  # perezoso: Binance no debe depender de Yahoo

    hist = yf.Ticker(ticker).history(start=start, end=end, interval=interval, auto_adjust=False)
    if hist.empty:
        raise ValueError(f"Yahoo Finance no devolvió datos para {ticker} (¿red o símbolo?).")
    return hist.reset_index().dropna(subset=["Open", "High", "Low", "Close"])


def _to_candles(hist) -> list[Candle]:
    col = "Date" if "Date" in hist.columns else "Datetime"
    return [Candle(t=int(row[col].timestamp() * 1000), o=float(row["Open"]), h=float(row["High"]),
                   l=float(row["Low"]), c=float(row["Close"]), v=float(row["Volume"]))
            for _, row in hist.iterrows()]


def fetch_ohlcv(asset_key: str, timeframe: str, candles: int = 300,
                client: BinanceFutures | None = None) -> tuple[list[Candle], str]:
    """(velas cerradas, fuente) de un activo soportado."""
    spec = spec_of(asset_key)
    if timeframe not in spec.intervals:
        raise ValueError(f"Timeframe '{timeframe}' no disponible para {asset_key.upper()} — "
                         f"usar uno de: {', '.join(spec.intervals)}")
    if spec.source == "binance":
        got = _binance_klines(client or BinanceFutures(), spec.ticker, timeframe, start=None,
                              limit=min(candles + 1, 1500))
        return got[-candles:], _BINANCE_SRC
    end = datetime.now(UTC)
    hist = _yahoo_history(spec.ticker, timeframe,
                          end - timedelta(days=_YAHOO_LOOKBACK_DAYS[timeframe](candles)), end)
    return _to_candles(hist)[-candles:], _YAHOO_SRC


def fetch_monthly(asset_key: str, start_year: int,
                  client: BinanceFutures | None = None) -> tuple[list[Candle], str]:
    """Velas MENSUALES reales desde `start_year` (el mes en curso lo filtra `monthly_closes`)."""
    spec = spec_of(asset_key)
    start = datetime(start_year, 1, 1, tzinfo=UTC)
    if spec.source == "binance":
        got = _binance_klines(client or BinanceFutures(), spec.ticker, "1M",
                              start=int(start.timestamp() * 1000), limit=1000)
        if not got:
            raise ValueError(f"Binance no devolvió velas mensuales para {spec.ticker}.")
        return got, _BINANCE_SRC
    return _to_candles(_yahoo_history(spec.ticker, "1mo", start)), _YAHOO_SRC
