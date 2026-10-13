"""Matriz Año×Mes de retornos mensuales a partir de cierres reales (puro; equivale a F7)."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from eim.core import Candle

MONTH_NAMES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def _next_month_start(year: int, month: int) -> int:
    y, m = (year + 1, 1) if month == 12 else (year, month + 1)
    return int(datetime(y, m, 1, tzinfo=UTC).timestamp() * 1000)


def monthly_closes(candles: list[Candle], timeframe: str, asof: int) -> pd.DataFrame:
    """Cierre de cada mes CALENDARIO COMPLETO presente en las velas (columnas timestamp, close).

    `timestamp` = inicio del mes (UTC). Un mes cuenta como completo si la serie continúa en un
    mes posterior, o si las velas llegan hasta su fin y `asof` ya pasó el cambio de mes. El mes
    en curso nunca entra: no se inventa un cierre que todavía no existe.
    """
    if not candles:
        return pd.DataFrame({"timestamp": pd.to_datetime([], utc=True), "close": []})
    diffs = [b.t - a.t for a, b in zip(candles, candles[1:], strict=False)]
    step = min(diffs) if diffs and timeframe != "1M" else None
    by_month: dict[tuple[int, int], Candle] = {}
    for c in candles:
        d = datetime.fromtimestamp(c.t / 1000, tz=UTC)
        by_month[(d.year, d.month)] = c  # la última vela del mes fija el cierre
    last_key = max(by_month)
    rows = []
    for (y, m), c in sorted(by_month.items()):
        nxt = _next_month_start(y, m)
        if (y, m) == last_key:
            reaches_end = timeframe == "1M" or (step is not None and c.t + step >= nxt)
            if not (asof >= nxt and reaches_end):
                continue
        rows.append((pd.Timestamp(datetime(y, m, 1, tzinfo=UTC)), c.c))
    return pd.DataFrame(rows, columns=["timestamp", "close"])


def build_matrix(
    monthly: pd.DataFrame,
    start_year: int | None = None,
    end_year: int | None = None,
    *,
    strict_gaps: bool = True,
) -> dict:
    """Tabla año×mes de variación % cierre a cierre.

    `strict_gaps=True`: si falta un mes intermedio su retorno y el del mes siguiente quedan NaN
    (no se compara contra un cierre de hace dos meses). `False` reproduce el legado F7, que
    calcula `pct_change` entre filas consecutivas aunque haya hueco.
    """
    if monthly.empty:
        raise ValueError("No hay cierres mensuales para construir la matriz.")
    df = monthly.sort_values("timestamp").reset_index(drop=True)
    df["year"] = df["timestamp"].dt.year
    df["month"] = df["timestamp"].dt.month
    df["return_pct"] = df["close"].pct_change() * 100
    if strict_gaps:
        idx = df["year"] * 12 + df["month"]
        df.loc[idx.diff() != 1, "return_pct"] = float("nan")
    d = df.dropna(subset=["return_pct"])
    if start_year is not None:
        d = d[d["year"] >= start_year]
    if end_year is not None:
        d = d[d["year"] <= end_year]
    if d.empty:
        raise ValueError("No hay retornos mensuales reales en el rango de años pedido.")
    pivot = d.pivot_table(index="year", columns="month", values="return_pct", aggfunc="first")
    pivot = pivot.reindex(columns=range(1, 13))
    rows = []
    for y in sorted(pivot.index.tolist()):
        row: dict = {"year": int(y)}
        for m in range(1, 13):
            v = pivot.loc[y, m]
            row[MONTH_NAMES[m - 1]] = round(float(v), 2) if pd.notna(v) else None
        rows.append(row)
    avg = {
        MONTH_NAMES[m - 1]: round(float(pivot[m].mean()), 2) if pivot[m].notna().any() else None
        for m in range(1, 13)
    }
    return {
        "rows": rows, "months": MONTH_NAMES, "monthly_average_pct": avg,
        "real_data_range": {"start": df["timestamp"].min().strftime("%Y-%m"),
                            "end": df["timestamp"].max().strftime("%Y-%m")},
    }
