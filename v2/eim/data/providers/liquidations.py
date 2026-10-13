"""Liquidaciones forzadas de Binance (data.binance.vision, `liquidationSnapshot`). Todo el I/O.

Hallazgos verificados contra el bucket real (heredados de F7/eim_liquidations.py):
1. Binance NO publica el dataset para USDⓈ-M; solo existe para COIN-margined ("cm"). Por eso
   ETHUSDT→ETHUSD_PERP y BTCUSDT→BTCUSD_PERP: instrumento correlacionado, NO idéntico. Se expone
   `requested_symbol` vs `liquidation_symbol`.
2. Binance dejó de publicar archivos nuevos en octubre de 2024 (último: 2024-10-14). El resultado
   marca `stale=True` cuando el último archivo supera `STALE_THRESHOLD_DAYS`.
Los días sin archivo no aportan filas: nunca se rellenan con ceros ni se estiman.
"""

from __future__ import annotations

import csv
import io
import time
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

import httpx

from eim.core import LiquidationDay, LiquidationLevel, Liquidations

BASE_URL = "https://data.binance.vision"
LISTING_URL = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
MARKET = "cm"
LIQUIDATION_SYMBOL_MAP = {"ETHUSDT": "ETHUSD_PERP", "BTCUSDT": "BTCUSD_PERP"}
STALE_THRESHOLD_DAYS = 30
SOURCE = "binance liquidationSnapshot (futures/cm, data.binance.vision)"
_DAY_MS = 86_400_000
_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"


class LiquidationsUnavailable(RuntimeError):
    """El dataset no tiene datos publicados o no se pudo descargar nada."""


def resolve_liquidation_symbol(requested_symbol: str) -> str:
    """ETHUSDT → ETHUSD_PERP (coin-margined, único con datos); `_PERP` se usa tal cual."""
    s = requested_symbol.upper()
    if s in LIQUIDATION_SYMBOL_MAP:
        return LIQUIDATION_SYMBOL_MAP[s]
    if "_" in s:
        return s
    raise ValueError(
        f"sin mapeo de '{s}' a un símbolo coin-margined con datos de liquidación; "
        f"disponibles: {', '.join(LIQUIDATION_SYMBOL_MAP)}"
    )


def aggregate(
    rows: list[dict], *, price_bins: int = 40
) -> tuple[list[LiquidationDay], list[LiquidationLevel]]:
    """Filas crudas (time, side, original_quantity, average_price) → totales diarios y niveles.

    `side` es el lado de la ORDEN: BUY liquida una posición CORTA, SELL una LARGA. El rango de
    los bins sale del mínimo/máximo observado, no de un rango supuesto.
    """
    ev = []
    for r in rows:
        price = float(r["average_price"])
        usd = float(r["original_quantity"]) * price
        ev.append((int(r["time"]), r["side"] == "SELL", usd, price))
    days: dict[int, list[float]] = {}
    for t, is_long, usd, _ in ev:
        d = days.setdefault(t - t % _DAY_MS, [0.0, 0.0])
        d[0 if is_long else 1] += usd
    daily = [LiquidationDay(t=t, longs_usd=v[0], shorts_usd=v[1]) for t, v in sorted(days.items())]
    if not ev:
        return daily, []
    lo, hi = min(e[3] for e in ev), max(e[3] for e in ev)
    if lo == hi:
        lo, hi = lo * 0.99, hi * 1.01
    width = (hi - lo) / price_bins
    bins = [[0.0, 0.0] for _ in range(price_bins)]
    for _, is_long, usd, price in ev:
        bins[min(int((price - lo) / width), price_bins - 1)][0 if is_long else 1] += usd
    levels = [
        LiquidationLevel(price=lo + (i + 0.5) * width, longs_usd=b[0], shorts_usd=b[1])
        for i, b in enumerate(bins) if b[0] or b[1]
    ]
    return daily, levels


class BinanceLiquidations:
    """Descarga (con caché en disco opcional) los últimos días con datos reales publicados."""

    name = "binance-liquidations"

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        cache_dir: Path | None = None,
        clock: Callable[[], int] = lambda: int(time.time() * 1000),
    ) -> None:
        self._client = client or httpx.Client(timeout=30.0)
        self._cache = cache_dir
        self._clock = clock

    def list_available_dates(self, symbol: str) -> list[str]:
        """Fechas con archivo publicado, según el listado real del bucket."""
        prefix = f"data/futures/{MARKET}/daily/liquidationSnapshot/{symbol.upper()}/"
        resp = self._client.get(LISTING_URL, params={"delimiter": "/", "prefix": prefix})
        resp.raise_for_status()
        dates = []
        for c in ElementTree.fromstring(resp.content).findall(f"{_NS}Contents"):
            key = c.find(f"{_NS}Key").text or ""
            if key.endswith(".zip"):
                dates.append(key.split("liquidationSnapshot-")[-1].split(".")[0])
        return sorted(dates)

    @staticmethod
    def _read_csv(text: str) -> list[dict]:
        return list(csv.DictReader(io.StringIO(text)))

    def _download_day(self, symbol: str, date: str) -> list[dict] | None:
        cache = (
            self._cache / symbol / f"{symbol}-liquidationSnapshot-{date}.csv"
            if self._cache else None
        )
        if cache is not None and cache.exists():
            return self._read_csv(cache.read_text(encoding="utf-8"))
        url = (f"{BASE_URL}/data/futures/{MARKET}/daily/liquidationSnapshot/{symbol}/"
               f"{symbol}-liquidationSnapshot-{date}.zip")
        resp = self._client.get(url)
        if resp.status_code != 200:
            return None
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            if not zf.namelist():
                return None
            text = zf.read(zf.namelist()[0]).decode("utf-8")
        rows = self._read_csv(text)
        if not rows:
            return None
        if cache is not None:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(text, encoding="utf-8")
        return rows

    def fetch(self, requested_symbol: str, days: int = 30, price_bins: int = 40) -> Liquidations:
        """Últimos `days` días CON archivo real (no camina desde ayer asumiendo dataset al día)."""
        liq_symbol = resolve_liquidation_symbol(requested_symbol)
        all_dates = self.list_available_dates(liq_symbol)
        if not all_dates:
            raise LiquidationsUnavailable(
                f"Binance no tiene (o ya no tiene) liquidationSnapshot para {liq_symbol}"
            )
        rows: list[dict] = []
        n_days = 0
        for d in all_dates[-days:]:
            day_rows = self._download_day(liq_symbol, d)
            if day_rows is not None:
                rows += day_rows
                n_days += 1
        if not n_days:
            raise LiquidationsUnavailable(f"no se pudo descargar ningún archivo de {liq_symbol}")
        latest = datetime.strptime(all_dates[-1], "%Y-%m-%d").replace(tzinfo=UTC)
        age = (self._clock() - int(latest.timestamp() * 1000)) // _DAY_MS
        daily, levels = aggregate(rows, price_bins=price_bins)
        req = requested_symbol.upper()
        return Liquidations(
            requested_symbol=req, liquidation_symbol=liq_symbol,
            most_recent_date=all_dates[-1], stale=age > STALE_THRESHOLD_DAYS,
            stale_age_days=int(age), days_with_data=n_days, daily=daily, levels=levels,
            source=f"{SOURCE}: {liq_symbol} (coin-margined) como proxy de {req}",
        )
