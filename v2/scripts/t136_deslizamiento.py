"""T136 (6), E4b — deslizamiento del stop medido contra el libro capturado (T78).

    python scripts/t136_deslizamiento.py --api http://127.0.0.1:8000 --root data

Toma los stops que el bróker simulado disparó (los lee del libro por la API local, en **solo
lectura**: `GET /v2/paper/trades`), se queda con los que caen en horas con captura HFT y, para
cada uno, busca en el `bbo` guardado el primer instante de su vela en que la punta del libro
alcanzó el nivel del stop. Compara el deslizamiento que supuso el modelo de costos con el que
daba el libro en ese instante.

Es prospectivo: solo mide stops posteriores al inicio de la captura. No escribe nada en `data/`,
no cambia ningún parámetro y, si el modelo se queda corto, lo que propone es una **versión nueva**
del modelo de costos (◆ del usuario), nunca un ajuste automático.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.request
from pathlib import Path

import duckdb

from eim.data.collectors.hft_read import hour_label, hours_with_data
from eim.data.collectors.hft_writer import hour_dir
from eim.data.timeframes import tf_ms
from eim.paper import slip_check as sc

HOUR_MS = 3_600_000
COLS = "e_ms, t_ms, bid_p, bid_q, ask_p, ask_q"


def fetch(api: str, symbol: str, limit: int) -> list[dict]:
    """Libro de operaciones cerradas del bróker simulado, por la API local (solo lectura)."""
    url = f"{api.rstrip('/')}/v2/paper/trades?symbol={symbol}&limit={limit}"
    with urllib.request.urlopen(url, timeout=120) as r:      # noqa: S310  (solo 127.0.0.1)
        return json.loads(r.read().decode("utf-8")).get("trades", [])


def as_fill(t: dict) -> sc.StopFill | None:
    if t.get("reason") not in sc.STOP_REASONS or not t.get("exit") or not t.get("exit_t"):
        return None
    return sc.StopFill(id=f"{t['profile']}:{t['id']}", profile=t["profile"], side=int(t["side"]),
                       qty=float(t["qty"]), stop=float(t["exit"]),
                       notional=float(t.get("notional") or 0.0),
                       slip_usd=float(t.get("slip") or 0.0), exit_t=int(t["exit_t"]))


def connect() -> duckdb.DuckDBPyConnection:
    """Una sola conexión, con memoria y hilos **acotados**.

    Sin tope, una consulta sobre una hora de `bbo` de BTCUSDT (millones de filas) se come toda la
    RAM del equipo y degrada la captura, que es justo lo que T127 intenta evitar. Con tope, DuckDB
    vuelca a disco o falla, pero no se lleva por delante a los servicios.
    """
    con = duckdb.connect()
    con.execute("SET memory_limit = '512MB'")
    con.execute("SET threads = 1")
    con.execute("SET preserve_insertion_order = false")
    return con


def parts_for(root: Path, symbol: str, t0: int, t1: int) -> list[Path]:
    out: list[Path] = []
    for h in range(t0 // HOUR_MS, t1 // HOUR_MS + 1):
        d = hour_dir(root, "bbo", symbol, h)
        out += sorted(d.glob("part-*.parquet")) if d.exists() else []
    return out


def first_crossing(con: duckdb.DuckDBPyConnection, root: Path, symbol: str, f: sc.StopFill,
                   bar_ms: int) -> tuple[sc.Touch | None, int]:
    """Primer instante de la vela del stop en que la punta del libro alcanzó su nivel.

    La condición va **dentro de la consulta**, con `LIMIT 1`: una vela de 15 m de `bbo` de BTCUSDT
    son entre 0,8 y 2 millones de mensajes, así que traerla a Python para buscar la primera fila
    es lo que hace falta NO hacer (la primera versión de esto se comió 10 GB de RAM).

    Devuelve también cuántas puntas había en la ventana, para saber si hubo cobertura real.
    """
    t0, t1 = f.exit_t, f.exit_t + bar_ms
    parts = parts_for(root, symbol, t0, t1)
    if not parts:
        return None, 0
    lst = "[" + ", ".join("'" + p.as_posix().replace("'", "''") + "'" for p in parts) + "]"
    src = f"read_parquet({lst})"
    n = con.execute(f"SELECT count(*) FROM {src} WHERE e_ms >= ? AND e_ms < ?",
                    [t0, t1]).fetchone()[0]
    if not n:
        return None, 0
    side = "bid_p <= ?" if f.side > 0 else "ask_p >= ?"
    row = con.execute(f"SELECT {COLS} FROM {src} WHERE e_ms >= ? AND e_ms < ? AND {side} "
                      "ORDER BY e_ms LIMIT 1", [t0, t1, f.stop]).fetchone()
    if row is None:
        return None, int(n)
    return sc.Touch(t_ms=int(row[0]), bid_p=float(row[2] or 0.0), bid_q=float(row[3] or 0.0),
                    ask_p=float(row[4] or 0.0), ask_q=float(row[5] or 0.0)), int(n)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--root", default="data", help="raíz de los datos con la captura HFT")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--tf", default="15m", help="marco del camino: define la ventana de la vela")
    ap.add_argument("--limit", type=int, default=5000)
    ap.add_argument("--max-stops", type=int, default=0,
                    help="mide solo los N stops mas recientes (0 = todos)")
    ap.add_argument("--out", default="reports/t136_deslizamiento")
    a = ap.parse_args()
    root, t0 = Path(a.root), time.perf_counter()

    hours = set(hours_with_data(root, a.symbol, ("bbo",)))
    if not hours:
        print(f"sin captura de bbo en {root}: nada que medir (es prospectivo)")
        return 1
    trades = fetch(a.api, a.symbol, a.limit)
    fills = [f for f in (as_fill(t) for t in trades) if f is not None]
    covered = [f for f in fills if f.exit_t // HOUR_MS in hours]
    print(f"libro: {len(trades)} cerradas, {len(fills)} por stop, {len(covered)} en horas con "
          f"captura ({hour_label(min(hours))} -> {hour_label(max(hours))})", flush=True)

    if a.max_stops and len(covered) > a.max_stops:
        covered = covered[:a.max_stops]       # para medir el costo antes de lanzarlo entero
        print(f"solo los {len(covered)} mas recientes (--max-stops)", flush=True)
    bar = tf_ms(a.tf)
    con = connect()
    try:
        found = {}
        for n, f in enumerate(covered, 1):
            found[f.id] = first_crossing(con, root, a.symbol, f, bar)
            if n % 25 == 0:
                print(f"  {n}/{len(covered)} ({time.perf_counter() - t0:.0f} s)", flush=True)
    finally:
        con.close()
    rows = sc.rows_found(covered, found)
    res = {
        "meta": {"api": a.api, "root": str(root), "symbol": a.symbol, "path_tf": a.tf,
                 "commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                          capture_output=True, text=True,
                                          check=False).stdout.strip(),
                 "built_ms": int(time.time() * 1000),
                 "seconds": round(time.perf_counter() - t0, 1)},
        "coverage": {"hft_from": hour_label(min(hours)), "hft_to": hour_label(max(hours)),
                     "hft_hours": len(hours), "closed": len(trades), "stops": len(fills),
                     "stops_in_coverage": len(covered)},
        "summary": sc.summary(rows), "rows": rows,
    }
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1,
                                                   default=str), encoding="utf-8")
    s = res["summary"]
    print(f"\nmedidos {s['n_measured']} de {s['n_stops']}: {s.get('verdict')}")
    if s.get("real_bps"):
        print(f"  real mediana {s['real_bps']['median']:.2f} pb frente a modelo "
              f"{s['model_bps']['median']:.2f} pb (diferencia {s['diff_bps_median']:+.2f} pb)")
        print(f"  el modelo se queda corto en {s['model_short_share']:.0%} de los stops")
    print(f"  estados: {s['states']}")
    print(f"\ndatos en {out.with_suffix('.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
