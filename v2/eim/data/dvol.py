"""Ingesta y cobertura del índice DVOL de Deribit en el almacén del proyecto (T165).

Todo el I/O de la volatilidad implícita vive aquí: los modelos y los agentes siguen siendo puros.
La serie se guarda como velas con `kind="dvol"`, símbolo `BTC`/`ETH` y marco `1h`, así que se lee
con el mismo `Store` que el resto y la medición se repite **sin red**.

No arranca ningún servicio nuevo: se refresca a mano o desde la tarea programada,

    python -m eim.data.dvol --data v2/data --currency BTC,ETH

y cada corrida solo pide lo que falta desde la última vela guardada.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from eim.data.providers.deribit import HISTORY_START_MS, SOURCE, DeribitPublic
from eim.data.store import Store
from eim.validation.lineage import iso_ms, ms_iso

KIND = "dvol"
TIMEFRAME = "1h"
STEP_MS = 3_600_000


def sync(store: Store, currency: str, start: int | None = None, end: int | None = None,
         provider: DeribitPublic | None = None, overlap: int = 24) -> dict:
    """Descarga lo que falta y lo guarda. Devuelve qué se trajo y la cobertura resultante.

    Por defecto arranca en la última vela guardada menos `overlap` horas (para rehacer el borde) o,
    si la serie está vacía, en el comienzo de la historia pública.
    """
    cur = currency.upper()
    p = provider or DeribitPublic()
    if start is None:
        bounds = store.bounds(cur, TIMEFRAME, kind=KIND)
        start = HISTORY_START_MS if bounds is None else int(bounds[1]) - overlap * STEP_MS
    if end is None:
        end = p.now()
    candles = p.volatility_index(cur, max(start, HISTORY_START_MS), end)
    rows = store.upsert_candles(cur, TIMEFRAME, candles, SOURCE, kind=KIND) if candles else 0
    out = {"currency": cur, "fetched": len(candles), "rows": rows or store.count(
        cur, TIMEFRAME, kind=KIND)}
    out.update(coverage(store, cur))
    return out


def coverage(store: Store, currency: str) -> dict:
    """Primera y última vela guardadas, filas y cobertura real frente a las horas del tramo."""
    cur = currency.upper()
    bounds = store.bounds(cur, TIMEFRAME, kind=KIND)
    rows = store.count(cur, TIMEFRAME, kind=KIND)
    if bounds is None or not rows:
        return {"source": SOURCE, "first": None, "last": None, "rows": 0, "coverage": None}
    first, last = int(bounds[0]), int(bounds[1])
    expected = (last - first) // STEP_MS + 1
    return {"source": SOURCE, "first": ms_iso(first), "last": ms_iso(last), "rows": rows,
            "expected": expected, "coverage": round(rows / expected, 6) if expected else None}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True, help="raíz del almacén (p. ej. v2/data)")
    ap.add_argument("--currency", default="BTC", help="BTC, ETH o una lista separada por comas")
    ap.add_argument("--from", dest="start", default=None, help="ISO UTC; por defecto, lo que falta")
    ap.add_argument("--to", dest="end", default=None, help="ISO UTC; por defecto, ahora")
    a = ap.parse_args(argv)
    store = Store(Path(a.data))
    out = [sync(store, c.strip(), iso_ms(a.start) if a.start else None,
                iso_ms(a.end) if a.end else None)
           for c in a.currency.split(",") if c.strip()]
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
