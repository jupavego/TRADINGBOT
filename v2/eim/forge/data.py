"""Datos de la forja (T208): velas de 5 m de la historia del banco de T131, y su funding.

El 5 m no existe como serie capturada: se **agrega** del 1 m (solo grupos completos de 5 velas),
igual que hace `eim.data.aggregate` para el almacén vivo. El banco de T131
(`v2/backups/t131_banco/`) es una copia inmutable con 1 m desde 2022-12-31, 0 huecos y cobertura
100 %; aquí nunca se escribe en él.

    python -m eim.forge build-data --bank <banco T131> --out <banco de la forja>
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SYMBOL = "BTCUSDT"
TF_MS = 300_000
COLS = ("t", "o", "h", "l", "c", "v", "taker_buy_v", "trades")


@dataclass(frozen=True)
class Series:
    """Serie de 5 m como arreglos, más la tasa de funding que se liquida en cada vela (0 si no)."""

    t: np.ndarray
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray  # noqa: E741 - el nombre del campo de la vela en todo el proyecto
    c: np.ndarray
    v: np.ndarray
    taker_buy_v: np.ndarray
    trades: np.ndarray
    funding: np.ndarray

    def __len__(self) -> int:
        return len(self.t)


def _glob(bank: Path, kind: str, tf: str) -> str:
    pat = bank / kind / f"symbol={SYMBOL}" / f"timeframe={tf}" / "*.parquet"
    if not list(pat.parent.glob("*.parquet")):
        raise FileNotFoundError(f"el banco no tiene {kind} {tf}: {pat}")
    return str(pat).replace("\\", "/")


def build(bank: Path, out: Path) -> dict:
    """Agrega el 1 m del banco a 5 m en `out`. Devuelve la cobertura; no toca `bank`."""
    import duckdb

    dst = out / "candles" / f"symbol={SYMBOL}" / "timeframe=5m"
    dst.mkdir(parents=True, exist_ok=True)
    src = _glob(bank, "candles", "1m")
    con = duckdb.connect()
    con.execute(f"""
        CREATE VIEW agg AS
        SELECT t // {TF_MS} * {TF_MS} AS t, arg_min(o, t) AS o, max(h) AS h, min(l) AS l,
               arg_max(c, t) AS c, sum(v) AS v, sum(taker_buy_v) AS taker_buy_v,
               sum(trades) AS trades
        FROM read_parquet('{src}') GROUP BY 1 HAVING count(*) = 5 ORDER BY 1""")
    con.execute(f"COPY agg TO '{(dst / 'data.parquet').as_posix()}' (FORMAT PARQUET)")
    n, a, b = con.execute("SELECT count(*), min(t), max(t) FROM agg").fetchone()
    gaps = con.execute(
        "SELECT count(*) FROM (SELECT t - lag(t) OVER (ORDER BY t) AS d FROM agg) "
        f"WHERE d IS NOT NULL AND d <> {TF_MS}").fetchone()[0]
    cov = {"symbol": SYMBOL, "timeframe": "5m", "candles": int(n), "t0": int(a), "t1": int(b),
           "gaps": int(gaps), "source": f"agregado de 1m del banco {bank.name}",
           "complete_groups_only": True}
    (out / "cobertura_5m.json").write_text(json.dumps(cov, indent=1), encoding="utf-8")
    return cov


def load(forge_bank: Path, bank: Path | None = None, end: int | None = None) -> Series:
    """Carga el 5 m de la forja (y el funding del banco de T131) como arreglos."""
    import duckdb

    con = duckdb.connect()
    where = "" if end is None else f"WHERE t < {int(end)}"
    a = con.execute(f"SELECT {', '.join(COLS)} FROM read_parquet("
                    f"'{_glob(forge_bank, 'candles', '5m')}') {where} ORDER BY t").fetchnumpy()
    t = np.asarray(a["t"], dtype=np.int64)
    cols = {k: np.asarray(a[k], dtype=float) for k in COLS[1:]}
    fund = np.zeros(len(t), dtype=float)
    if bank is not None:
        f = con.execute(f"SELECT t, x FROM read_parquet('{_glob(bank, 'funding', '-')}') "
                        "ORDER BY t").fetchnumpy()
        ft, fx = np.asarray(f["t"], np.int64), np.asarray(f["x"], float)
        # la tasa se liquida en la vela que contiene su instante
        idx = np.searchsorted(t, ft, "right") - 1
        ok = (idx >= 0) & (idx < len(t)) & np.isfinite(fx)
        np.add.at(fund, idx[ok], fx[ok])
    return Series(t=t, funding=fund, **cols)
