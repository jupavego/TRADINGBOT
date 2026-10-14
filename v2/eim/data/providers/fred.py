"""Valores publicados (real, anterior, revisado) desde FRED/ALFRED, point-in-time. Todo el I/O.

Opcional: requiere `EIM_FRED_API_KEY` (gratuita). Sin clave o sin red → None y el evento queda
sin valores (nunca se estiman). Atribución obligatoria según los términos de FRED: ver
`ATTRIBUTION`. La consulta por *vintage* (`realtime_start = realtime_end = día`) devuelve lo que
se sabía ese día: `actual` sale de la vintage del día de publicación, `previous` de la del día
anterior y `revised` es el periodo previo tal como quedó tras la publicación (si cambió).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import httpx

API_URL = "https://api.stlouisfed.org/fred/series/observations"
ATTRIBUTION = ("This product uses the FRED® API but is not endorsed or certified by the "
               "Federal Reserve Bank of St. Louis.")
# publicación → (serie FRED, transformación, unidad)
SERIES: dict[str, tuple[str, str, str]] = {
    "Consumer Price Index": ("CPIAUCSL", "pct", "IPC general m/m %"),
    "Employment Situation": ("PAYEMS", "diff", "nóminas no agrícolas, miles (variación)"),
    "Personal Income and Outlays": ("PCEPI", "pct", "deflactor PCE m/m %"),
    "Gross Domestic Product": ("A191RL1Q225SBEA", "level", "PIB real t/t anualizado %"),
    "Producer Price Index": ("PPIFIS", "pct", "IPP demanda final m/m %"),
}


def _transform(kind: str, vals: list[float]) -> float | None:
    """`vals` del más reciente al más antiguo."""
    if kind == "level":
        return vals[0] if vals else None
    if len(vals) < 2 or (kind == "pct" and vals[1] == 0):
        return None
    if kind == "diff":
        return round(vals[0] - vals[1], 6)
    return round((vals[0] / vals[1] - 1) * 100, 6)


class FredValues:
    name = "fred"

    def __init__(self, api_key: str | None = None, client: httpx.Client | None = None) -> None:
        self.key = api_key if api_key is not None else os.environ.get("EIM_FRED_API_KEY")
        self._client = client or httpx.Client(timeout=20.0)

    @property
    def enabled(self) -> bool:
        return bool(self.key)

    def _vintage(self, series: str, day: str, limit: int) -> list[tuple[str, float]] | None:
        r = self._client.get(API_URL, params={
            "series_id": series, "api_key": self.key, "file_type": "json",
            "realtime_start": day, "realtime_end": day, "sort_order": "desc", "limit": limit})
        r.raise_for_status()
        out = []
        for o in r.json().get("observations", []):
            if o.get("value") not in (None, ".", ""):
                out.append((o["date"], float(o["value"])))
        return out

    def values(self, name: str, t_utc: int) -> dict | None:
        """{actual, previous, revised, unit} del evento publicado en `t_utc`; None si no aplica,
        no hay clave, falla la red o la vintage del día aún no trae un periodo nuevo."""
        if not self.enabled or name not in SERIES:
            return None
        series, kind, unit = SERIES[name]
        day = datetime.fromtimestamp(t_utc / 1000, tz=UTC)
        try:
            now = self._vintage(series, day.strftime("%Y-%m-%d"), 3)
            before = self._vintage(series, (day - timedelta(days=1)).strftime("%Y-%m-%d"), 3)
        except (httpx.HTTPError, ValueError, KeyError):
            return None
        if not now or not before or now[0][0] <= before[0][0]:
            return None  # la vintage del día no incluye un periodo nuevo: no publicado aún
        actual = _transform(kind, [v for _, v in now])
        previous = _transform(kind, [v for _, v in before])
        prior_now = _transform(kind, [v for _, v in now[1:]])
        revised = prior_now if prior_now is not None and prior_now != previous else None
        return {"actual": actual, "previous": previous, "revised": revised, "unit": unit}
