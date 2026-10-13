"""
EIM-F7 | Módulo 12: Estacionalidad — Matriz de Retornos Mensuales
=====================================================================
Tabla Año (filas) × Mes (columnas) de variación % de cierre a cierre —
el formato clásico de "mapa de estacionalidad" que se ve en mesas de
trading. Construida sobre cierres mensuales REALES; nunca se extiende la
tabla a años sin datos reales del activo — un año sin cobertura real
simplemente no aparece como fila (no se rellena con ceros ni se interpola).

Cobertura real por fuente — no es igual para todos los activos, y hay que
decirlo explícitamente en vez de mostrar una tabla 2015-2026 uniforme que
sugiera falsamente que todos los activos tienen esa historia:
  - Binance Futuros (ETHUSDT, BTCUSDT, XAUUSDT, ...) vía kline nativo
    mensual (interval "1M"): la cobertura depende de cuándo se listó el
    contrato. Los perpetuos ETHUSDT/BTCUSDT no llegan a 2015 (Binance
    Futures USDⓈ-M arrancó en 2019); XAUUSDT solo existe desde el 5 de
    enero de 2026 (ver eim_market_data.py).
  - Yahoo Finance (S&P 500 ^GSPC, Nasdaq Composite ^IXIC): historia mensual
    de varias décadas — cubre 2015-2026 sin problema.

El resultado siempre incluye `real_data_range` para que quien lo consuma
sepa, sin ambigüedad, desde cuándo hay datos reales — igual que
`leverage_source`/`capital_source` en la bitácora.
"""

from datetime import datetime, timezone

import pandas as pd
from binance.client import Client

from eim_data import EIMDataFeed
from eim_market_data import SUPPORTED_ASSETS

MONTH_NAMES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


# ─── Cierres mensuales reales por fuente ───────────────────────────
def _monthly_closes_binance(feed: EIMDataFeed, ticker: str, start_year: int) -> pd.DataFrame:
    """
    Cierres mensuales reales vía kline nativo 1M de Binance Futuros (no
    resampleado desde velas diarias — Binance ya agrega el mes real).
    """
    start_ms = int(datetime(start_year, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    raw = feed.client.futures_klines(
        symbol=ticker.upper(),
        interval=Client.KLINE_INTERVAL_1MONTH,
        startTime=start_ms,
        limit=1500,   # 125 años de velas mensuales — más que suficiente en una sola llamada
    )
    if not raw:
        raise ValueError(f"Binance no devolvió velas mensuales para {ticker}.")
    df = EIMDataFeed._parse_klines(raw, ticker, "1mo")
    return df[["timestamp", "close"]]


def _monthly_closes_yahoo(ticker: str, start_year: int) -> pd.DataFrame:
    import yfinance as yf

    start = datetime(start_year, 1, 1, tzinfo=timezone.utc)
    hist = yf.Ticker(ticker).history(start=start, interval="1mo", auto_adjust=False)
    if hist.empty:
        raise ValueError(f"Yahoo Finance no devolvió velas mensuales para {ticker}.")

    hist = hist.reset_index()
    time_col = "Date" if "Date" in hist.columns else "Datetime"
    out = pd.DataFrame({
        "timestamp": pd.to_datetime(hist[time_col], utc=True),
        "close":     hist["Close"].astype(float),
    })
    return out.dropna(subset=["close"])


# ─── Construcción de la matriz ─────────────────────────────────────
class EIMSeasonality:
    """Construye la matriz Año × Mes de retornos % a partir de cierres mensuales reales."""

    def __init__(self, monthly_closes: pd.DataFrame):
        """monthly_closes: columnas [timestamp, close] — un cierre por mes."""
        if monthly_closes.empty:
            raise ValueError("No hay cierres mensuales para construir la matriz.")
        df = monthly_closes.sort_values("timestamp").reset_index(drop=True)
        df["year"]  = df["timestamp"].dt.year
        df["month"] = df["timestamp"].dt.month
        # Retorno del mes = variación del cierre respecto al cierre del mes
        # anterior REAL en la serie — si falta un mes intermedio (símbolo
        # nuevo, gap de datos), ese retorno queda NaN, no se aproxima.
        df["return_pct"] = df["close"].pct_change() * 100
        self.df = df

    def matrix(self, start_year: int | None = None, end_year: int | None = None) -> dict:
        df = self.df.dropna(subset=["return_pct"]).copy()
        if start_year is not None:
            df = df[df["year"] >= start_year]
        if end_year is not None:
            df = df[df["year"] <= end_year]

        if df.empty:
            raise ValueError(
                "No hay retornos mensuales reales en el rango de años pedido — "
                "prueba un rango más amplio o revisa `real_data_range`."
            )

        pivot = df.pivot_table(index="year", columns="month", values="return_pct", aggfunc="first")
        pivot = pivot.reindex(columns=range(1, 13))

        rows = []
        for y in sorted(pivot.index.tolist()):
            row = {"year": int(y)}
            for m in range(1, 13):
                v = pivot.loc[y, m] if m in pivot.columns else None
                row[MONTH_NAMES[m - 1]] = round(float(v), 2) if pd.notna(v) else None
            rows.append(row)

        monthly_avg = {}
        for m in range(1, 13):
            col = pivot[m] if m in pivot.columns else pd.Series(dtype=float)
            monthly_avg[MONTH_NAMES[m - 1]] = round(float(col.mean()), 2) if col.notna().any() else None

        return {
            "rows": rows,
            "months": MONTH_NAMES,
            "monthly_average_pct": monthly_avg,
            "real_data_range": {
                "start": self.df["timestamp"].min().strftime("%Y-%m"),
                "end":   self.df["timestamp"].max().strftime("%Y-%m"),
            },
        }


def build_seasonality_matrix(
    asset_key: str,
    start_year: int = 2015,
    end_year: int | None = None,
    binance_feed: EIMDataFeed | None = None,
) -> dict:
    """Punto de entrada único: activo soportado → matriz año×mes con cierres reales."""
    asset_key = asset_key.upper()
    if asset_key not in SUPPORTED_ASSETS:
        raise ValueError(
            f"Activo '{asset_key}' no soportado. Disponibles: {', '.join(SUPPORTED_ASSETS)}"
        )
    spec = SUPPORTED_ASSETS[asset_key]

    if spec.source == "binance":
        feed = binance_feed or EIMDataFeed()
        monthly = _monthly_closes_binance(feed, spec.ticker, start_year)
    else:
        monthly = _monthly_closes_yahoo(spec.ticker, start_year)

    result = EIMSeasonality(monthly).matrix(start_year=start_year, end_year=end_year)
    result["asset_key"] = asset_key
    result["asset_label"] = spec.label
    result["requested_range"] = {
        "start_year": start_year,
        "end_year": end_year or datetime.now(timezone.utc).year,
    }
    return result
