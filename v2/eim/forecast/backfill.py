"""Backfill walk-forward: pronósticos retroactivos sobre historia para tener muestra desde el día 1.

Cada origen `i` solo ve `candles[:i]` (sin mirar el futuro). No hay plan ni derivados históricos,
así que no se aplican SL del plan ni deriva externa: se evalúa el motor tal cual (línea base).
Uso: `python -m eim.forecast.backfill --symbol BTCUSDT --timeframe 1h --data-dir data`
"""

from __future__ import annotations

import argparse
from collections.abc import Iterator

from eim.core import Candle, ForecastSet, MarketSnapshot
from eim.forecast.base_engine import BaseEngine
from eim.forecast.engine import Engine
from eim.forecast.scenarios import build_forecast

NOTE = "backfill walk-forward (sin plan ni derivados)"


def backfill(
    engine: Engine,
    candles: list[Candle],
    *,
    symbol: str,
    timeframe: str,
    horizon: int = 25,
    n: int = 200,
    start: int = 150,
    stride: int = 1,
    context: int = 1500,
    max_origins: int | None = None,
) -> Iterator[ForecastSet]:
    """Genera un `ForecastSet` por origen con horizonte completo observable en `candles`."""
    last = len(candles) - horizon
    origins = list(range(max(start, 100), last + 1, stride))
    if max_origins:
        origins = origins[-max_origins:]
    for i in origins:
        snap = MarketSnapshot(
            symbol=symbol, timeframe=timeframe, candles=candles[max(0, i - context) : i],
            asof=candles[i].t, sources={}, coverage={})
        fs = build_forecast(snap, horizon, n, engine=engine)
        yield fs.model_copy(update={"warnings": [*fs.warnings, NOTE]})


def main() -> None:  # pragma: no cover - uso manual con datos reales
    from eim.api.forecast_db import ForecastStore
    from eim.api.reports_db import ReportStore
    from eim.data.store import Store

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--timeframe", default="1h")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--reports", default="data/reports.duckdb")
    ap.add_argument("--horizon", type=int, default=25)
    ap.add_argument("--max-origins", type=int, default=800)
    a = ap.parse_args()
    candles = Store(a.data_dir).read_candles(a.symbol, a.timeframe)
    db = ForecastStore(*ReportStore(a.reports).connection)
    k = 0
    for fs in backfill(BaseEngine(), candles, symbol=a.symbol, timeframe=a.timeframe,
                       horizon=a.horizon, max_origins=a.max_origins):
        db.save(fs)
        k += 1
    print(f"{k} pronósticos de backfill guardados")


if __name__ == "__main__":  # pragma: no cover
    main()
