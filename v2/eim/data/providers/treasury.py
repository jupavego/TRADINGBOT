"""Curva par diaria del Tesoro de EE. UU. (T100). Todo el I/O de esa fuente vive aquí.

Fuente aprobada en la ◆ de T88 §2.1 (nivel 2): «offered free, without restriction»; no nombra
licencia (se anota como reutilización declarada) ni publica límites. CSV sin clave, un archivo
por año, filas de la más reciente a la más antigua, fechas `MM/DD/YYYY`, rendimientos en % y
celdas vacías cuando un plazo no existía (el de 1,5 meses empieza en 2025; el de 4 meses en
2022). Se actualiza hacia las 15:30 ET.

`parse_par_csv` es puro y lo prueban los fixtures; `TreasuryPar` solo descarga.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime

import httpx

from eim.data.providers.meta import US_TREASURY

BASE = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
        "daily-treasury-rates.csv/{year}/all")
#: Cabecera del CSV → plazo en años.
TENORS: dict[str, float] = {
    "1 Mo": 1 / 12, "1.5 Month": 1.5 / 12, "2 Mo": 2 / 12, "3 Mo": 3 / 12, "4 Mo": 4 / 12,
    "6 Mo": 0.5, "1 Yr": 1.0, "2 Yr": 2.0, "3 Yr": 3.0, "5 Yr": 5.0, "7 Yr": 7.0,
    "10 Yr": 10.0, "20 Yr": 20.0, "30 Yr": 30.0,
}


@dataclass(frozen=True)
class ParCurve:
    """Una curva par del día: plazos en años y rendimientos equivalentes de bono en %."""

    date: str                         # ISO AAAA-MM-DD
    tenors: tuple[float, ...]
    yields_pct: tuple[float, ...]
    source: str = US_TREASURY.name

    def get(self, tenor: float) -> float | None:
        for t, y in zip(self.tenors, self.yields_pct, strict=True):
            if abs(t - tenor) < 1e-9:
                return y
        return None


def parse_par_csv(text: str) -> list[ParCurve]:
    """Curvas del CSV, ordenadas de la más antigua a la más reciente. Las columnas que no son
    plazos conocidos se ignoran; una celda vacía o no numérica deja fuera ese plazo ese día."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if not reader.fieldnames or "Date" not in reader.fieldnames:
        raise ValueError("CSV del Tesoro sin columna Date")
    cols = [c for c in reader.fieldnames if c in TENORS]
    if not cols:
        raise ValueError("CSV del Tesoro sin columnas de plazo reconocibles")
    out: dict[str, ParCurve] = {}
    for row in reader:
        try:
            day = datetime.strptime(row["Date"].strip(), "%m/%d/%Y").date().isoformat()
        except (ValueError, AttributeError):
            continue
        pts = []
        for c in cols:
            try:
                pts.append((TENORS[c], float(row[c])))
            except (TypeError, ValueError):
                continue
        if pts:
            pts.sort()
            out[day] = ParCurve(day, tuple(t for t, _ in pts), tuple(y for _, y in pts))
    return [out[d] for d in sorted(out)]


class TreasuryPar:
    """Descarga la curva par de un año (sin clave). Lanza `httpx.HTTPError` si falla la red."""

    name = US_TREASURY.name
    meta = US_TREASURY

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=30.0, follow_redirects=True)

    def year(self, year: int) -> list[ParCurve]:
        r = self._client.get(BASE.format(year=year), params={
            "type": "daily_treasury_yield_curve", "field_tdr_date_value": str(year),
            "page": "", "_format": "csv"})
        r.raise_for_status()
        return parse_par_csv(r.text)
