"""
EIM-F7 | Módulo 10: Mapa de Liquidaciones
============================================
Datos REALES de liquidaciones forzadas de Binance Futuros, tomados del
archivo histórico diario oficial que publica Binance en data.binance.vision
(dataset "liquidationSnapshot") — mismo enfoque validado en el repo de
referencia `liquidations-chart` (github.com/StephanAkkerman/liquidations-chart,
perfilado en repos/repo_profiles_master.md), pero conservando el precio de
cada evento para construir un mapa por nivel de precio, no solo un total
diario como hace ese repo.

DOS hallazgos importantes verificados en vivo contra el bucket real de
Binance (no supuestos, no heredados sin más del repo de referencia):

1. Binance NO publica liquidationSnapshot para el mercado USDⓈ-M ("um" —
   donde vive ETHUSDT/BTCUSDT, el mismo que usa EIMDataFeed). El dataset
   solo existe para el mercado COIN-margined ("cm") — contratos inversos
   liquidados en la propia moneda. Por eso `resolve_liquidation_symbol()`
   traduce ETHUSDT→ETHUSD_PERP y BTCUSDT→BTCUSD_PERP: es el instrumento
   real más cercano con datos reales, pero es un contrato DISTINTO
   (correlacionado, no idéntico) — se expone así en cada respuesta
   (`requested_symbol` vs `liquidation_symbol`), nunca disfrazado.

2. Binance dejó de publicar archivos nuevos de este dataset desde octubre
   de 2024 (verificado: el archivo más reciente listado es del
   2024-10-14, tanto para ETHUSD_PERP como BTCUSD_PERP). Es decir, este
   módulo da un mapa de liquidaciones REAL pero HISTÓRICO — útil para
   estudiar 2023-06 a 2024-10, NO representa el mercado actual. El
   resultado marca `stale: true` y lo dice explícitamente en `source`
   cuando la fecha más reciente disponible supera STALE_THRESHOLD_DAYS.
   Un mapa de liquidaciones verdaderamente actual solo sería posible con
   el stream en vivo (WebSocket `forceOrder`), que requeriría un proceso
   24/7 acumulando datos en una base — fuera del alcance de esta
   arquitectura de servidor que responde bajo demanda.

Por qué esta fuente y no una sintética (investigado antes de implementar —
ver también repos/py-liquidation-map y repos/-Cryptocurrency-Liquidation-Heatmap,
y los repos externos btc-liquidation-heatmap / crypto-liquidations-mcp
encontrados en la misma ronda de investigación): no es una estimación —
varias alternativas comunes sí lo son (fórmulas de apalancamiento teórico
sobre trades grandes, o proxies de Open Interest, ninguna mide una
liquidación real). Este dataset es el registro real de órdenes de
liquidación forzada que Binance efectivamente ejecutó, aunque hoy solo
cubra un período histórico específico.

Columnas reales del CSV (confirmadas contra el código fuente de
liquidations-chart y contra un archivo real descargado, no adivinadas):
time (ms epoch), symbol, side (BUY = liquidación de posición CORTA,
SELL = liquidación de posición LARGA — es el lado de la orden de
liquidación, opuesto al lado de la posición), order_type, time_in_force,
original_quantity, price, average_price, order_status,
order_last_filled_quantity, order_filled_accumulated_quantity, order_trade_time.

Días sin archivo publicado simplemente no aportan filas — nunca se
rellenan con ceros ni se estima nada en su lugar.
"""

import io
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
import pandas as pd
import requests

BASE_URL = "https://data.binance.vision"
LISTING_URL = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"

# IMPORTANTE — verificado contra el bucket real, no supuesto: Binance NO
# publica liquidationSnapshot para el mercado USDⓈ-M ("um", donde vive
# ETHUSDT/BTCUSDT — el mismo que usa EIMDataFeed). El dataset solo existe
# para el mercado COIN-margined ("cm") — contratos inversos liquidados en
# la propia moneda (ETHUSD_PERP, BTCUSD_PERP), no en USDT. Es un
# instrumento relacionado pero DISTINTO al que EIM diagnostica — precio y
# dinámica de liquidación correlacionados con ETHUSDT, no idénticos. Se
# expone así, sin disfrazarlo, en cada respuesta (`liquidation_symbol` vs
# `requested_symbol`).
MARKET = "cm"
LIQUIDATION_SYMBOL_MAP = {
    "ETHUSDT": "ETHUSD_PERP",
    "BTCUSDT": "BTCUSD_PERP",
}
CACHE_DIR = Path(__file__).parent / "cache" / "liquidations"


def resolve_liquidation_symbol(requested_symbol: str) -> str:
    """
    Traduce un símbolo USDⓈ-M de EIM (ETHUSDT) al símbolo coin-margined
    real que sí tiene liquidationSnapshot (ETHUSD_PERP). Si ya se pasa un
    símbolo _PERP/cm directamente, se usa tal cual.
    """
    requested_symbol = requested_symbol.upper()
    if requested_symbol in LIQUIDATION_SYMBOL_MAP:
        return LIQUIDATION_SYMBOL_MAP[requested_symbol]
    if requested_symbol.endswith("_PERP") or "_" in requested_symbol:
        return requested_symbol
    raise ValueError(
        f"No hay mapeo conocido de '{requested_symbol}' a un símbolo coin-margined "
        f"con datos reales de liquidación. Disponibles: {', '.join(LIQUIDATION_SYMBOL_MAP)}."
    )


# ─── Descubrimiento y descarga ─────────────────────────────────────
def _listing_prefix(symbol: str) -> str:
    return f"data/futures/{MARKET}/daily/liquidationSnapshot/{symbol.upper()}/"


def list_available_dates(symbol: str, timeout: int = 30) -> list[str]:
    """Consulta el listado REAL de archivos publicados por Binance para `symbol`."""
    resp = requests.get(
        LISTING_URL,
        params={"delimiter": "/", "prefix": _listing_prefix(symbol)},
        timeout=timeout,
    )
    resp.raise_for_status()
    tree = ElementTree.fromstring(resp.content)
    ns = "{http://s3.amazonaws.com/doc/2006-03-01/}"
    dates = []
    for content in tree.findall(f"{ns}Contents"):
        key = content.find(f"{ns}Key").text
        if key.endswith(".zip"):
            dates.append(key.split("liquidationSnapshot-")[-1].split(".")[0])
    return sorted(dates)


def _cache_path(symbol: str, date_str: str) -> Path:
    d = CACHE_DIR / symbol.upper()
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{symbol.upper()}-liquidationSnapshot-{date_str}.csv"


def _download_day(symbol: str, date_str: str, timeout: int = 30) -> pd.DataFrame | None:
    """
    Descarga (o lee de caché local en disco) un día de liquidaciones reales.
    Devuelve None si Binance no publicó archivo ese día — nunca se inventa
    un DataFrame vacío ni con ceros para rellenar el hueco.
    """
    cache_file = _cache_path(symbol, date_str)
    if cache_file.exists():
        return pd.read_csv(cache_file)

    url = (
        f"{BASE_URL}/data/futures/{MARKET}/daily/liquidationSnapshot/"
        f"{symbol.upper()}/{symbol.upper()}-liquidationSnapshot-{date_str}.zip"
    )
    resp = requests.get(url, timeout=timeout)
    if resp.status_code != 200:
        return None

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
        if not names:
            return None
        with zf.open(names[0]) as f:
            df = pd.read_csv(f)

    if df.empty:
        return None

    df.to_csv(cache_file, index=False)
    return df


STALE_THRESHOLD_DAYS = 30  # más de esto sin publicar nuevo archivo = probable dataset descontinuado


def fetch_liquidations(requested_symbol: str, days: int = 30, timeout: int = 30) -> pd.DataFrame:
    """
    Descarga (o toma de caché) los últimos `days` días CON DATOS REALES
    publicados para `requested_symbol` (traducido primero al símbolo coin-
    margined real vía resolve_liquidation_symbol).

    A propósito NO camina "desde ayer hacia atrás" asumiendo que el dataset
    está siempre al día — primero consulta el listado REAL del bucket
    (list_available_dates) y toma las últimas `days` fechas que de verdad
    tienen archivo. Esto evita interpretar "Binance descontinuó el dataset
    hace meses" como si fuera simplemente "no hubo liquidaciones esos días".
    Si la fecha más reciente real es más vieja que STALE_THRESHOLD_DAYS,
    `out.attrs["stale"]` queda en True para que el consumidor lo muestre.

    Raises:
        ValueError: si el símbolo no tiene NINGÚN archivo publicado nunca —
        nunca se devuelve un resultado vacío disfrazado de "sin liquidaciones
        ese periodo" cuando en realidad es "no hay dato real disponible".
    """
    liquidation_symbol = resolve_liquidation_symbol(requested_symbol)

    all_dates = list_available_dates(liquidation_symbol, timeout=timeout)
    if not all_dates:
        raise ValueError(
            f"Binance no tiene (o ya no tiene) datos de liquidationSnapshot "
            f"publicados para {liquidation_symbol} — verificado contra el "
            f"listado real del bucket, no es un problema de red."
        )

    target_dates = all_dates[-days:]
    frames = [df for d in target_dates if (df := _download_day(liquidation_symbol, d, timeout=timeout)) is not None]

    if not frames:
        raise ValueError(
            f"El listado de {liquidation_symbol} reporta fechas con archivo, "
            f"pero no se pudo descargar ninguna — probable problema de red."
        )

    out = pd.concat(frames, ignore_index=True).drop_duplicates()
    out["datetime"] = pd.to_datetime(out["time"], unit="ms", utc=True)

    most_recent = datetime.strptime(all_dates[-1], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - most_recent).days

    out.attrs["requested_symbol"]   = requested_symbol.upper()
    out.attrs["liquidation_symbol"] = liquidation_symbol
    out.attrs["days_with_data"]     = len(frames)
    out.attrs["most_recent_date"]   = all_dates[-1]
    out.attrs["stale"]              = age_days > STALE_THRESHOLD_DAYS
    out.attrs["stale_age_days"]     = age_days
    return out


# ─── Agregación en mapa de liquidaciones ───────────────────────────
class EIMLiquidationMap:
    """
    Construye un mapa de liquidaciones REALES por nivel de precio y tiempo,
    a partir del DataFrame crudo que devuelve fetch_liquidations().
    """

    def __init__(self, raw: pd.DataFrame):
        if raw.empty:
            raise ValueError("No hay filas de liquidaciones para procesar.")
        self.raw = raw.copy()
        # `side` es el lado de la ORDEN de liquidación, no de la posición:
        # BUY cierra (liquida) una posición corta; SELL cierra una larga.
        self.raw["position_side"] = self.raw["side"].map({"BUY": "SHORT", "SELL": "LONG"})
        self.raw["notional_usd"] = self.raw["original_quantity"] * self.raw["average_price"]

    def price_time_heatmap(self, price_bins: int = 40, time_bucket: str = "1D") -> dict:
        """
        Matriz precio × tiempo de notional liquidado (USD), separada por
        lado de la posición liquidada (LONG/SHORT). El rango de precio de
        los bins se toma del mínimo/máximo REAL observado en los datos, no
        de un rango supuesto alrededor del precio actual.
        """
        df = self.raw
        pmin, pmax = float(df["average_price"].min()), float(df["average_price"].max())
        if pmin == pmax:
            pmin, pmax = pmin * 0.99, pmax * 1.01
        edges = np.linspace(pmin, pmax, price_bins + 1)

        df = df.copy()
        df["price_bin_idx"] = pd.cut(
            df["average_price"], edges, include_lowest=True, labels=False
        )
        df["time_bin"] = df["datetime"].dt.floor(time_bucket)

        time_bins = sorted(df["time_bin"].unique())
        time_index = {t: i for i, t in enumerate(time_bins)}
        bin_centers = [(edges[i] + edges[i + 1]) / 2 for i in range(price_bins)]

        matrix_long = np.zeros((price_bins, len(time_bins)))
        matrix_short = np.zeros((price_bins, len(time_bins)))

        grouped = df.dropna(subset=["price_bin_idx"]).groupby(
            ["price_bin_idx", "time_bin", "position_side"], observed=True
        )["notional_usd"].sum()

        for (price_idx, t_bin, side), notional in grouped.items():
            row = matrix_long if side == "LONG" else matrix_short
            row[int(price_idx), time_index[t_bin]] += notional

        return {
            "price_levels": [round(c, 2) for c in bin_centers],
            "timestamps": [t.isoformat() for t in time_bins],
            "long_liquidations_usd": matrix_long.round(2).tolist(),
            "short_liquidations_usd": matrix_short.round(2).tolist(),
            "total_long_usd": round(float(matrix_long.sum()), 2),
            "total_short_usd": round(float(matrix_short.sum()), 2),
        }

    def daily_totals(self) -> pd.DataFrame:
        """
        Totales diarios long/short + precio promedio ponderado por notional
        — la vista simple tipo barras (referencia: liquidations-chart).
        """
        df = self.raw.copy()
        df["date"] = df["datetime"].dt.floor("1D")
        g = (
            df.groupby(["date", "position_side"])
            .agg(notional_usd=("notional_usd", "sum"), qty=("original_quantity", "sum"))
            .reset_index()
        )
        g["vwap_price"] = g["notional_usd"] / g["qty"]

        pivot_notional = g.pivot(index="date", columns="position_side", values="notional_usd").fillna(0)
        pivot_notional = pivot_notional.rename(columns={"LONG": "longs_usd", "SHORT": "shorts_usd"})
        for col in ("longs_usd", "shorts_usd"):
            if col not in pivot_notional.columns:
                pivot_notional[col] = 0.0

        pivot_price = g.pivot(index="date", columns="position_side", values="vwap_price")
        pivot_notional["price"] = (
            pivot_price.get("LONG", 0).fillna(0) * pivot_notional["longs_usd"]
            + pivot_price.get("SHORT", 0).fillna(0) * pivot_notional["shorts_usd"]
        ) / (pivot_notional["longs_usd"] + pivot_notional["shorts_usd"]).replace(0, np.nan)

        return pivot_notional.reset_index()

    def run_all(self, price_bins: int = 40, time_bucket: str = "1D") -> dict:
        heatmap = self.price_time_heatmap(price_bins=price_bins, time_bucket=time_bucket)
        daily = self.daily_totals()
        daily_out = daily.copy()
        daily_out["date"] = daily_out["date"].astype(str)

        requested = self.raw.attrs.get("requested_symbol")
        liq_symbol = self.raw.attrs.get("liquidation_symbol")
        stale = self.raw.attrs.get("stale", False)

        source_note = (
            f"Binance liquidationSnapshot (futures/cm, data.binance.vision) — datos reales de "
            f"{liq_symbol} (contrato coin-margined, liquidado en la propia moneda), "
            f"usado como proxy real de {requested} (USDⓈ-M, liquidado en USDT) porque Binance "
            f"no publica este dataset para el mercado USDⓈ-M."
        )
        if stale:
            source_note += (
                f" AVISO: el archivo más reciente disponible es del "
                f"{self.raw.attrs.get('most_recent_date')} ({self.raw.attrs.get('stale_age_days')} días de "
                f"antigüedad) — Binance parece haber descontinuado la publicación de este dataset; "
                f"esto NO es un mapa de liquidaciones actual/en vivo."
            )

        return {
            "heatmap": heatmap,
            "daily_totals": daily_out.round(2).to_dict(orient="records"),
            "source": source_note,
            "requested_symbol": requested,
            "liquidation_symbol": liq_symbol,
            "days_with_data": self.raw.attrs.get("days_with_data"),
            "most_recent_date": self.raw.attrs.get("most_recent_date"),
            "stale": stale,
            "stale_age_days": self.raw.attrs.get("stale_age_days"),
        }
