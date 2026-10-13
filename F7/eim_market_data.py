"""
EIM-F7 | Módulo 11: Datos Multi-Activo
=========================================
Fuente unificada de OHLCV para el visor de velas multi-activo — un visor de
precio "tal como aparece en el exchange", sin pasar por el pipeline de
diagnóstico FRM/BRM/IRM (ese sigue siendo exclusivo de los símbolos que EIM
efectivamente modela, ver F0-F6).

Fuentes reales por activo — ninguna es sintética ni derivada:
  - Cripto (ETHUSDT, BTCUSDT, ...) y Oro (XAUUSDT) → Binance Futuros, el
    mismo EIMDataFeed que ya usa el motor de diagnóstico. XAUUSDT es el
    futuro perpetuo de oro liquidado en USDT que Binance lanzó el 5 de
    enero de 2026 (contrato "TradFi Perpetual") — el futuro de oro que
    Binance mismo opera, no un proxy externo ni un ETF.
  - S&P 500 (^GSPC) y Nasdaq Composite (^IXIC) → Yahoo Finance (yfinance),
    porque Binance todavía no lista futuros de índices bursátiles (solo
    materias primas — oro/plata — y acciones individuales a la fecha).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

from eim_data import EIMDataFeed


@dataclass(frozen=True)
class AssetSpec:
    label:     str
    source:    str        # "binance" | "yahoo"
    ticker:    str         # símbolo real en la fuente
    intervals: tuple        # timeframes soportados para este activo en esta fuente


# Nota sobre timeframes: Yahoo Finance no tiene barras de 4h nativas (solo
# intradía de 1m/5m/15m/30m/60m/90m limitado a ~730 días, y 1d/1wk/1mo sin
# límite) — por eso los índices ofrecen 1d/1wk/1mo en vez de 1h/4h/1d como
# cripto, en vez de fabricar una vela de 4h por resampleo que Yahoo no mide.
SUPPORTED_ASSETS: dict[str, AssetSpec] = {
    "ETHUSDT": AssetSpec("Ethereum (ETHUSDT)",              "binance", "ETHUSDT", ("1h", "4h", "1d")),
    "BTCUSDT": AssetSpec("Bitcoin (BTCUSDT)",                "binance", "BTCUSDT", ("1h", "4h", "1d")),
    "XAUUSDT": AssetSpec("Oro (XAUUSDT — futuro Binance)",   "binance", "XAUUSDT", ("1h", "4h", "1d")),
    "SP500":   AssetSpec("S&P 500 (^GSPC, Yahoo Finance)",   "yahoo",   "^GSPC",   ("1d", "1wk", "1mo")),
    "NASDAQ":  AssetSpec("Nasdaq Composite (^IXIC, Yahoo Finance)", "yahoo", "^IXIC", ("1d", "1wk", "1mo")),
}

_YAHOO_LOOKBACK_DAYS = {
    "1d":  lambda candles: int(candles * 1.6) + 15,   # ~5 días hábiles / 7 calendario
    "1wk": lambda candles: candles * 7 + 30,
    "1mo": lambda candles: candles * 31 + 60,
}


class EIMMultiAssetFeed:
    """Envoltura delgada que normaliza OHLCV de Binance y Yahoo Finance al mismo esquema."""

    def __init__(self, binance_feed: EIMDataFeed | None = None):
        # Perezoso a propósito: pedir S&P 500/Nasdaq (Yahoo) no debe requerir
        # una conexión a Binance funcionando — EIMDataFeed() valida la
        # conexión en su constructor (futures_ping), así que instanciarla
        # aquí de entrada rompería activos que no la necesitan para nada.
        self._binance_feed = binance_feed
        self._binance_explicit = binance_feed is not None

    @property
    def _binance(self) -> EIMDataFeed:
        if self._binance_feed is None:
            self._binance_feed = EIMDataFeed()
        return self._binance_feed

    @property
    def binance_feed_if_ready(self) -> "EIMDataFeed | None":
        """
        La instancia de EIMDataFeed SOLO si ya se creó (por una petición
        cripto/oro anterior) — nunca la fuerza. Para pasarla a otros
        módulos (ej. eim_seasonality) reutilizando la conexión cuando ya
        existe, sin obligar a los activos Yahoo-only a depender de Binance.
        """
        return self._binance_feed

    @staticmethod
    def list_assets() -> list[dict]:
        return [
            {"key": k, "label": s.label, "source": s.source, "intervals": list(s.intervals)}
            for k, s in SUPPORTED_ASSETS.items()
        ]

    def get_asset_ohlcv(self, asset_key: str, timeframe: str, candles: int = 300) -> pd.DataFrame:
        asset_key = asset_key.upper()
        if asset_key not in SUPPORTED_ASSETS:
            raise ValueError(
                f"Activo '{asset_key}' no soportado. Disponibles: "
                f"{', '.join(SUPPORTED_ASSETS)}"
            )
        spec = SUPPORTED_ASSETS[asset_key]
        if timeframe not in spec.intervals:
            raise ValueError(
                f"Timeframe '{timeframe}' no disponible para {asset_key} — "
                f"usar uno de: {', '.join(spec.intervals)}"
            )

        if spec.source == "binance":
            df = self._binance.get_historical(spec.ticker, timeframe, candles)
            df["asset_key"] = asset_key
            df["asset_label"] = spec.label
            return df
        return self._fetch_yahoo(asset_key, spec, timeframe, candles)

    def _fetch_yahoo(self, asset_key: str, spec: AssetSpec, timeframe: str, candles: int) -> pd.DataFrame:
        lookback_days = _YAHOO_LOOKBACK_DAYS[timeframe](candles)
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=lookback_days)

        ticker = yf.Ticker(spec.ticker)
        hist = ticker.history(start=start, end=end, interval=timeframe, auto_adjust=False)

        if hist.empty:
            raise ValueError(
                f"Yahoo Finance no devolvió datos para {spec.ticker} — puede ser un "
                f"problema temporal de red, o el símbolo dejó de estar disponible."
            )

        hist = hist.reset_index()
        time_col = "Date" if "Date" in hist.columns else "Datetime"
        out = pd.DataFrame({
            "timestamp": pd.to_datetime(hist[time_col], utc=True),
            "symbol":    spec.ticker,
            "timeframe": timeframe,
            "open":      hist["Open"].astype(float),
            "high":      hist["High"].astype(float),
            "low":       hist["Low"].astype(float),
            "close":     hist["Close"].astype(float),
            "volume":    hist["Volume"].astype(float),
        })
        # La sesión del día en curso suele venir con OHLC en NaN hasta que
        # cierra — se descarta esa fila en vez de graficar una vela vacía o
        # rellenarla con el último precio conocido.
        out = out.dropna(subset=["open", "high", "low", "close"])

        out["asset_key"] = asset_key
        out["asset_label"] = spec.label
        # Yahoo puede devolver más de lo pedido si `lookback_days` sobreestimó
        # — se recorta a las últimas `candles` reales, nunca se rellena si
        # devolvió menos (fines de semana, feriados bursátiles, IPO reciente).
        return out.tail(candles).reset_index(drop=True)
