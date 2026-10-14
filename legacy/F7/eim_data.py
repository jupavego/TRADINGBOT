"""
EIM-F7 | Módulo 1: Captura de Datos
====================================
Fuente: Binance API (Futuros USDT-M)
Modos : histórico + tiempo real
Ref   : EIM-VRM-001 § 1.2 — Timeframes
"""

from binance.client import Client
import pandas as pd
from datetime import datetime, timezone
from typing import Optional


# ─── Configuración ────────────────────────────────────────────────
TIMEFRAME_MAP = {
    "1h":  Client.KLINE_INTERVAL_1HOUR,
    "4h":  Client.KLINE_INTERVAL_4HOUR,
    "1d":  Client.KLINE_INTERVAL_1DAY,
}

SYMBOL_DEFAULT = "BTCUSDT"   # Par por defecto
WARMUP_CANDLES = 400         # EIM-FRM-001 § F-001 — req. mínimo EMA-200


# ─── Clase principal ──────────────────────────────────────────────
class EIMDataFeed:
    """
    Captura datos OHLCV de Binance Futuros.
    Soporta modo histórico y tiempo real.
    Sin API key → solo datos públicos (suficiente para OHLCV).
    """

    def __init__(self, api_key: str = "", api_secret: str = ""):
        self.client = Client(api_key, api_secret)
        self._validate_connection()

    def _validate_connection(self):
        """Verifica conexión con Binance al inicializar."""
        try:
            self.client.futures_ping()
        except Exception as e:
            raise ConnectionError(f"No se pudo conectar a Binance Futuros: {e}")

    # ── Modo histórico ────────────────────────────────────────────
    def get_historical(
        self,
        symbol:    str = SYMBOL_DEFAULT,
        timeframe: str = "4h",
        candles:   int = 1000,
    ) -> pd.DataFrame:
        """
        Descarga N velas históricas desde Binance Futuros.

        Args:
            symbol:    Par (ej. 'BTCUSDT', 'ETHUSDT')
            timeframe: '1h' | '4h' | '1d'
            candles:   Número de velas (mín. 400 por warmup EMA-200)

        Returns:
            DataFrame con columnas [timestamp, open, high, low, close, volume]
        """
        if timeframe not in TIMEFRAME_MAP:
            raise ValueError(f"Timeframe '{timeframe}' no válido. Usar: {list(TIMEFRAME_MAP)}")

        candles = max(candles, WARMUP_CANDLES)

        raw = self.client.futures_klines(
            symbol   = symbol.upper(),
            interval = TIMEFRAME_MAP[timeframe],
            limit    = candles,
        )

        df = self._parse_klines(raw, symbol, timeframe)
        print(f"[EIM Data] {symbol} {timeframe} — {len(df)} velas cargadas "
              f"({df['timestamp'].iloc[0].strftime('%Y-%m-%d')} → "
              f"{df['timestamp'].iloc[-1].strftime('%Y-%m-%d')})")
        return df

    # ── Modo tiempo real ─────────────────────────────────────────
    def get_current_candle(
        self,
        symbol:    str = SYMBOL_DEFAULT,
        timeframe: str = "4h",
    ) -> pd.Series:
        """
        Obtiene la vela actual (en formación) desde Binance Futuros.

        Returns:
            Series con [timestamp, open, high, low, close, volume]
        """
        if timeframe not in TIMEFRAME_MAP:
            raise ValueError(f"Timeframe '{timeframe}' no válido.")

        raw = self.client.futures_klines(
            symbol   = symbol.upper(),
            interval = TIMEFRAME_MAP[timeframe],
            limit    = 1,
        )

        df = self._parse_klines(raw, symbol, timeframe)
        return df.iloc[-1]

    def get_realtime_with_context(
        self,
        symbol:    str = SYMBOL_DEFAULT,
        timeframe: str = "4h",
        context:   int = WARMUP_CANDLES,
    ) -> pd.DataFrame:
        """
        Descarga contexto histórico + vela actual para diagnóstico en tiempo real.
        Garantiza warmup suficiente para EMA-200.

        Returns:
            DataFrame completo listo para pipeline EIM.
        """
        df = self.get_historical(symbol, timeframe, context + 1)
        print(f"[EIM Data] Modo tiempo real — vela actual: "
              f"CLOSE={df['close'].iloc[-1]:.2f} | "
              f"TS={df['timestamp'].iloc[-1].strftime('%Y-%m-%d %H:%M')}")
        return df

    # ── Parser interno ────────────────────────────────────────────
    @staticmethod
    def _parse_klines(raw: list, symbol: str, timeframe: str) -> pd.DataFrame:
        """Convierte respuesta de Binance a DataFrame normalizado."""
        df = pd.DataFrame(raw, columns=[
            "timestamp_ms", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote", "ignore"
        ])

        df["timestamp"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
        df["symbol"]    = symbol.upper()
        df["timeframe"] = timeframe

        numeric_cols = ["open", "high", "low", "close", "volume"]
        df[numeric_cols] = df[numeric_cols].astype(float)

        return df[["timestamp", "symbol", "timeframe",
                   "open", "high", "low", "close", "volume"]].reset_index(drop=True)


# ─── Ejecución standalone (prueba) ───────────────────────────────
if __name__ == "__main__":
    feed = EIMDataFeed()    # Sin API key — datos públicos

    # Prueba histórico
    for tf in ["1h", "4h", "1d"]:
        df = feed.get_historical("BTCUSDT", tf, 500)
        print(f"  Shape: {df.shape} | Última vela close: {df['close'].iloc[-1]:.2f}")
        print()

    # Prueba tiempo real
    df_rt = feed.get_realtime_with_context("BTCUSDT", "4h")
    print(f"  Listo para pipeline: {len(df_rt)} velas")
