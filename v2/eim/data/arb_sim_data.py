"""Datos reales para las pruebas del arbitraje en el bróker simulado (T45): velas de 1 h de spot
y del perpetuo (`Store`, kinds `spot_candles` y `candles`) y funding realizado; informe en JSON.

Solo lectura del almacén local: no consulta Binance ni usa ninguna cuenta.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eim.data.store import Store

H_MS = 3_600_000
REPORT = Path("paper") / "arb_tests.json"


@dataclass(frozen=True)
class SimSeries:
    symbol: str
    t: list[int]                       # aperturas de vela 1 h comunes a spot y perpetuo
    spot: list[float]                  # cierre spot
    fut: list[float]                   # cierre del perpetuo
    funding: list[tuple[int, float]]   # liquidaciones dentro de la ventana
    funding_hist: list[float]          # últimas tasas antes de la ventana (funding esperado)
    sources: dict[str, str]


def load_sim_series(store: Store, symbol: str = "BTCUSDT", hours: int = 60,
                    hist_n: int = 21) -> SimSeries | None:
    """Últimas `hours` velas de 1 h presentes en spot Y en el perpetuo (None si no alcanzan)."""
    spot = {c.t: c.c for c in store.read_candles(symbol, "1h", last=hours + 48,
                                                 kind="spot_candles")}
    fut = {c.t: c.c for c in store.read_candles(symbol, "1h", last=hours + 48)}
    ts = sorted(set(spot) & set(fut))[-hours:]
    if len(ts) < hours:
        return None
    rows = store.read_series("funding", symbol)
    fund = [(t, r) for t, r in rows if ts[0] < t <= ts[-1] + H_MS]
    hist = [r for t, r in rows if t <= ts[0]][-hist_n:]
    return SimSeries(
        symbol=symbol, t=ts, spot=[spot[t] for t in ts], fut=[fut[t] for t in ts],
        funding=fund, funding_hist=hist,
        sources={"spot": store.source("spot_candles", symbol, "1h") or "desconocida",
                 "futuros": store.source("candles", symbol, "1h") or "desconocida",
                 "funding": store.source("funding", symbol) or "desconocida"})


def save_report(root: Path | str, report: dict[str, Any]) -> Path:
    p = Path(root) / REPORT
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, p)
    return p


def load_report(root: Path | str) -> dict[str, Any] | None:
    try:
        return json.loads((Path(root) / REPORT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
