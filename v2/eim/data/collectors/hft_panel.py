"""Panel muestreado de la captura HFT (T80): el único I/O del marco de variables.

Reproduce el libro de la captura (T78) hora a hora y deja una fila por cubo de muestreo con:
el top-N del libro al CIERRE del cubo, el OFI multinivel acumulado dentro del cubo, el flujo
agresor del cubo y si el cubo está completo. Las variables (`eim/hft/features/`) y las etiquetas
(`eim/hft/evaluation/`) son puras y solo ven este panel, así que el disco vive aquí.

- Relojes: se muestrea por **hora de recepción** (`recv_ns`), que es lo que se pudo saber en el
  momento; el reloj del exchange se usa en el control de calidad, no aquí.
- Caché: `data/hft_panel/v1/symbol=S/step=<ms>/date=D/hour=HH/part.parquet`. Es derivado y
  regenerable (no entra en las copias, como los crudos): una hora se construye una vez.
- Cubos incompletos: los marca un tramo de hueco de `depth`/`trades` que toca el cubo, el libro
  sin sincronizar o la falta de eventos del libro en el cubo. Se marcan, no se arreglan.
"""

from __future__ import annotations

import argparse
import calendar
import json
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from eim.data.collectors import qc
from eim.data.collectors.book_fast import FastBook
from eim.data.collectors.hft_read import (
    hour_label,
    parse_hour,
    read_hour,
)
from eim.hft.features.book import ofi_event, pad_levels
from eim.hft.features.matrix import Panel, concat

AREA = "hft_panel"
VERSION = "v1"
STEP_MS = 1_000
LEVELS = 5
GAP_STREAMS = ("depth", "trades")
GAP_SKIP_CAUSE = "silencio"          # un silencio del exchange no pierde ni un dato
LEVEL_COLS = ("bp", "bq", "ap", "aq")


def panel_dir(root: str | Path, symbol: str, hour: int, step_ms: int = STEP_MS) -> Path:
    tm = time.gmtime(hour * 3600)
    return (Path(root) / AREA / VERSION / f"symbol={symbol}" / f"step={step_ms}"
            / time.strftime("date=%Y-%m-%d", tm) / f"hour={tm.tm_hour:02d}")


def panel_file(root: str | Path, symbol: str, hour: int, step_ms: int = STEP_MS) -> Path:
    return panel_dir(root, symbol, hour, step_ms) / "part.parquet"


def columns(levels: int = LEVELS) -> list[str]:
    lv = [f"{c}{k}" for c in LEVEL_COLS for k in range(levels)]
    return ["t", *lv, *[f"ofi{k}" for k in range(levels)], "buy_v", "sell_v", "n_trades",
            "complete"]


def _bad_buckets(root, symbol: str, hour: int, t0: int, step_ms: int, n: int) -> np.ndarray:
    """Cubos que toca un tramo de hueco (se lee también la hora anterior: los tramos cruzan)."""
    bad = np.zeros(n, bool)
    for h in (hour - 1, hour):
        g = read_hour(root, symbol, "gaps", h, "stream, cause, start_ns, end_ns")
        for _, r in g.iterrows():
            if r["stream"] not in GAP_STREAMS or r["cause"] == GAP_SKIP_CAUSE:
                continue
            a = int(r["start_ns"]) // 1_000_000
            b = max(int(r["end_ns"]) // 1_000_000, a)
            lo = max((a - t0) // step_ms, 0)
            hi = min((b - t0) // step_ms, n - 1)
            if hi >= 0 and lo <= n - 1:
                bad[lo:hi + 1] = True
    return bad


def _trade_buckets(root, symbol: str, hour: int, t0: int, step_ms: int, n: int):
    """(volumen comprador, vendedor, nº) por cubo; un `agg_id` repetido al reconectar cuenta una."""
    buy, sell, cnt = np.zeros(n), np.zeros(n), np.zeros(n)
    df = read_hour(root, symbol, "trades", hour, "recv_ns, agg_id, q, maker")
    if df.empty:
        return buy, sell, cnt
    df = df.drop_duplicates("agg_id")
    i = ((df["recv_ns"].to_numpy(dtype=np.int64) // 1_000_000) - t0) // step_ms
    ok = (i >= 0) & (i < n)
    i, q, maker = i[ok], df["q"].to_numpy(float)[ok], df["maker"].to_numpy(bool)[ok]
    np.add.at(sell, i[maker], q[maker])        # el comprador es maker → el agresor vende
    np.add.at(buy, i[~maker], q[~maker])
    np.add.at(cnt, i, 1.0)
    return buy, sell, cnt


def _events(book: pd.DataFrame, depth: pd.DataFrame) -> list[tuple[int, int, int, int]]:
    """(run, seq, tabla, fila) de las filas de `book` (0) y `depth` (1) en orden de proceso."""
    out = [(int(r), int(s), 0, i)
           for i, (r, s) in enumerate(zip(book["run"], book["seq"], strict=True))]
    out += [(int(r), int(s), 1, i)
            for i, (r, s) in enumerate(zip(depth["run"], depth["seq"], strict=True))]
    return sorted(out)


def build_hour(root: str | Path, symbol: str, hour: int, step_ms: int = STEP_MS,
               levels: int = LEVELS) -> pd.DataFrame:
    """Construye el panel de una hora reproduciendo el libro de la captura. Sin red."""
    t0 = hour * 3600 * 1000
    n = (3600 * 1000) // step_ms
    book = read_hour(root, symbol, "book", hour,
                     "recv_ns, run, seq, last_id, last_u, synced, bp, bq, ap, aq")
    depth = read_hour(root, symbol, "depth", hour,
                      "recv_ns, run, seq, first_id, last_id, prev_id, bp, bq, ap, aq")
    bk = {c: book[c].tolist() for c in book.columns}
    dp = {c: depth[c].tolist() for c in depth.columns}
    top = np.zeros((n, 4, levels))
    ofi = np.zeros((n, levels))
    seen = np.zeros(n, bool)
    unsynced = np.zeros(n, bool)
    lb = FastBook()
    prev = None
    for _run, _seq, tag, i in _events(book, depth):
        t = bk if tag == 0 else dp
        idx = (int(t["recv_ns"][i]) // 1_000_000 - t0) // step_ms
        if not 0 <= idx < n:
            continue
        if tag == 0:                                     # libro exacto del recolector
            lb = FastBook(bids=dict(zip(t["bp"][i], t["bq"][i], strict=True)),
                           asks=dict(zip(t["ap"][i], t["aq"][i], strict=True)),
                           last_id=int(t["last_id"][i]),
                           last_u=None if int(t["last_u"][i]) < 0 else int(t["last_u"][i]),
                           synced=bool(t["synced"][i]))
            prev = None
        else:
            res = lb.apply(int(t["first_id"][i]), int(t["last_id"][i]), int(t["prev_id"][i]),
                           list(zip(t["bp"][i], t["bq"][i], strict=True)),
                           list(zip(t["ap"][i], t["aq"][i], strict=True)))
            if res != "ok":
                unsynced[idx] = True
                prev = None
                continue
        bids, asks = lb.top(levels)
        cur = pad_levels([p for p, _ in bids], [q for _, q in bids],
                         [p for p, _ in asks], [q for _, q in asks], levels)
        if prev is not None:
            ofi[idx] += ofi_event(prev, cur, levels)
        top[idx] = np.asarray(cur)
        seen[idx] = True
        prev = cur
    buy, sell, cnt = _trade_buckets(root, symbol, hour, t0, step_ms, n)
    bad = _bad_buckets(root, symbol, hour, t0, step_ms, n) | unsynced | ~seen
    data = {"t": t0 + (np.arange(n) + 1) * step_ms}
    for c, k in enumerate(LEVEL_COLS):
        for lv in range(levels):
            data[f"{k}{lv}"] = top[:, c, lv]
    for lv in range(levels):
        data[f"ofi{lv}"] = ofi[:, lv]
    data |= {"buy_v": buy, "sell_v": sell, "n_trades": cnt, "complete": ~bad}
    return pd.DataFrame(data)[seen].reset_index(drop=True)   # un cubo sin libro no es panel


def write_hour(root: str | Path, symbol: str, hour: int, df: pd.DataFrame,
               step_ms: int = STEP_MS) -> Path:
    """Escribe el panel de una hora (atómico: .tmp → part.parquet)."""
    f = panel_file(root, symbol, hour, step_ms)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp.parquet")
    con = duckdb.connect()
    try:
        con.execute("SET threads = 1")
        con.register("df", df)
        con.execute("COPY (SELECT * FROM df) TO ? (FORMAT PARQUET, COMPRESSION zstd)",
                    [tmp.as_posix()])
    finally:
        con.close()
    tmp.replace(f)
    return f


def ensure_hour(root: str | Path, symbol: str, hour: int, step_ms: int = STEP_MS,
                levels: int = LEVELS, rebuild: bool = False) -> tuple[Path, int]:
    """(archivo, filas escritas) del panel de la hora; 0 filas = ya estaba o no hay datos."""
    f = panel_file(root, symbol, hour, step_ms)
    if f.exists() and not rebuild:
        return f, 0
    df = build_hour(root, symbol, hour, step_ms, levels)
    if df.empty:
        return f, 0
    return write_hour(root, symbol, hour, df, step_ms), len(df)


def from_frame(df: pd.DataFrame, symbol: str = "BTCUSDT", step_ms: int = STEP_MS,
               levels: int = LEVELS) -> Panel:
    """`Panel` a partir del marco leído del caché (orden de niveles conservado)."""
    def grab(k: str) -> np.ndarray:
        return np.column_stack([df[f"{k}{lv}"].to_numpy(float) for lv in range(levels)])

    return Panel(t=df["t"].to_numpy(dtype=np.int64), bid_p=grab("bp"), bid_q=grab("bq"),
                 ask_p=grab("ap"), ask_q=grab("aq"), ofi=grab("ofi"),
                 buy_v=df["buy_v"].to_numpy(float), sell_v=df["sell_v"].to_numpy(float),
                 n_trades=df["n_trades"].to_numpy(float),
                 complete=df["complete"].to_numpy(bool), step_ms=step_ms, symbol=symbol)


def read_hours(root: str | Path, symbol: str, hours: list[int], step_ms: int = STEP_MS,
               levels: int = LEVELS) -> Panel:
    """Panel de las horas pedidas (las que no tienen archivo se omiten)."""
    files = [f for h in sorted(hours) if (f := panel_file(root, symbol, h, step_ms)).exists()]
    if not files:
        raise FileNotFoundError("ninguna hora del panel construida")
    lst = "[" + ", ".join("'" + f.as_posix().replace("'", "''") + "'" for f in files) + "]"
    con = duckdb.connect()
    try:
        con.execute("SET threads = 2")
        df = con.execute(f"SELECT * FROM read_parquet({lst}) ORDER BY t").df()
    finally:
        con.close()
    return from_frame(df, symbol, step_ms, levels)


def load_panel(root: str | Path, symbol: str, hours: list[int], step_ms: int = STEP_MS,
               levels: int = LEVELS, chunk: int = 24) -> Panel:
    """Como `read_hours`, por tandas de `chunk` horas para no inflar la memoria."""
    hs = sorted(hours)
    parts = []
    for i in range(0, len(hs), chunk):
        block = [h for h in hs[i:i + chunk] if panel_file(root, symbol, h, step_ms).exists()]
        if block:
            parts.append(read_hours(root, symbol, block, step_ms, levels))
    return concat(parts)


def panel_hours(root: str | Path, symbol: str, step_ms: int = STEP_MS) -> list[int]:
    """Horas UTC absolutas con panel construido."""
    base = Path(root) / AREA / VERSION / f"symbol={symbol}" / f"step={step_ms}"
    out = []
    for d in base.glob("date=*/hour=*"):
        if (d / "part.parquet").exists():
            day = time.strptime(d.parent.name.removeprefix("date="), "%Y-%m-%d")
            out.append(calendar.timegm(day) // 3600 + int(d.name.removeprefix("hour=")))
    return sorted(out)


def hours_in_range(root: str | Path, symbol: str, first: int, last: int,
                   complete_only: bool = True) -> list[int]:
    """Horas de [first, last] con captura; con `complete_only`, solo las que el QC da por
    completas y sin huecos sin detectar (las demás ni se construyen)."""
    out = []
    for h in range(first, last + 1):
        rep = qc.load(root, symbol, h)
        if rep is None:
            continue
        if complete_only and not (rep.get("complete")
                                  and rep.get("holes", {}).get("undetected", 0) == 0):
            continue
        out.append(h)
    return out


def main(argv: list[str] | None = None) -> int:
    """`python -m eim.data.collectors.hft_panel --from 2026-11-02T00 --to 2026-11-19T23`."""
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default="data")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--from", dest="first", required=True, help="hora UTC AAAA-MM-DDTHH")
    ap.add_argument("--to", dest="last", required=True, help="hora UTC AAAA-MM-DDTHH")
    ap.add_argument("--step-ms", type=int, default=STEP_MS)
    ap.add_argument("--levels", type=int, default=LEVELS)
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--all-hours", action="store_true",
                    help="también las horas que el QC no da por completas")
    a = ap.parse_args(argv)
    hours = hours_in_range(a.root, a.symbol, parse_hour(a.first), parse_hour(a.last),
                           not a.all_hours)
    t0, rows, built = time.time(), 0, 0
    for k, h in enumerate(hours, 1):
        _f, n = ensure_hour(a.root, a.symbol, h, a.step_ms, a.levels, a.rebuild)
        rows += n
        built += 1 if n else 0
        if k % 10 == 0 or k == len(hours):
            print(f"{k}/{len(hours)} horas · {built} construidas · {rows} filas · "
                  f"{time.time() - t0:.0f} s · última {hour_label(h)}", flush=True)
    print(json.dumps({"horas": len(hours), "construidas": built, "filas": rows,
                      "segundos": round(time.time() - t0, 1)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":                                   # pragma: no cover
    raise SystemExit(main())
