"""Micro-prueba del diseño del observatorio (T72): «los procesos escriben archivos, uno indexa».

Mide (desde `v2/`: `python scripts/obs_bench.py [--seconds 10] [--rate 1000]`):
  1. dos procesos emitiendo a `--rate` eventos/s cada uno, a la vez, sin líneas corruptas;
  2. un único proceso que indexa los JSONL en DuckDB (tiempo y filas);
  3. que escribir directo en la base desde varios procesos FALLA (por eso no se hace);
  4. coste de `emit()` en el hilo que lo llama (p50/p95/p99) y frente a un ciclo real de agentes.
Escribe el resultado en JSON (por defecto, a stdout).
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _producer(spool: str, name: str, rate: int, seconds: float, shared: bool) -> None:
    import eim.observability.emit as E
    E.configure(process="shared" if shared else name, spool_dir=spool)
    n = int(rate * seconds)
    t0 = time.perf_counter()
    for i in range(n):
        E.emit("signal", "agent.structure", detail={"i": i, "p": name},
               source="bench", coverage=1.0)
        due = t0 + (i + 1) / rate
        slack = due - time.perf_counter()
        if slack > 0:
            time.sleep(slack)
    E.flush(10.0)
    print(json.dumps({"proc": name, "stats": E.stats(),
                      "elapsed_s": round(time.perf_counter() - t0, 2)}), flush=True)


def _write_db(db: str, tag: str, q) -> None:
    import duckdb
    try:
        con = duckdb.connect(db)
        con.execute("CREATE TABLE IF NOT EXISTS t(x INT)")
        time.sleep(1.5)
        con.close()
        q.put((tag, "ok"))
    except Exception as exc:
        q.put((tag, f"{type(exc).__name__}: {str(exc)[:90]}"))


def check_lines(spool: Path) -> dict:
    total = bad = 0
    ids: set[str] = set()
    for f in spool.glob("*.jsonl"):
        for line in f.read_bytes().split(b"\n"):
            if not line:
                continue
            total += 1
            try:
                ids.add(json.loads(line)["event_id"])
            except Exception:
                bad += 1
    return {"lines": total, "corrupt": bad, "unique_ids": len(ids)}


def index(spool: Path, db: Path) -> dict:
    import duckdb
    t0 = time.perf_counter()
    con = duckdb.connect(str(db))
    con.execute(f"""CREATE TABLE events AS SELECT * FROM read_json_auto(
        '{(spool / '*.jsonl').as_posix()}', format='newline_delimited',
        columns={{'event_id':'VARCHAR','ts_utc':'BIGINT','process':'VARCHAR',
        'component_id':'VARCHAR','kind':'VARCHAR','status':'VARCHAR','run_id':'VARCHAR',
        'trace_id':'VARCHAR','duration_ms':'DOUBLE','mode':'VARCHAR','source':'VARCHAR',
        'coverage':'DOUBLE','detail':'JSON'}})""")
    n = con.execute("SELECT count(*) FROM events").fetchone()[0]
    con.close()
    return {"rows": n, "index_s": round(time.perf_counter() - t0, 3)}


def concurrent_db_write(tmp: Path) -> dict:
    q = mp.Queue()
    db = str(tmp / "direct.duckdb")
    ps = [mp.Process(target=_write_db, args=(db, t, q)) for t in ("A", "B")]
    for p in ps:
        p.start()
    for p in ps:
        p.join()
    return dict(q.get() for _ in ps)


def emit_cost(spool: str, n: int = 20_000) -> dict:
    import eim.observability.emit as E
    E.configure(process="cost", spool_dir=spool)
    lat = []
    for i in range(n):
        t = time.perf_counter()
        E.emit("signal", "agent.structure", detail={"i": i, "bias": 0.3},
               source="bench", coverage=1.0)
        lat.append((time.perf_counter() - t) * 1e6)
    lat.sort()
    E.flush(10.0)
    st = E.stats()
    E.close()
    return {"n": n, "p50_us": round(lat[n // 2], 1), "p95_us": round(lat[int(n * .95)], 1),
            "p99_us": round(lat[int(n * .99)], 1), "mean_us": round(statistics.fmean(lat), 1),
            "stats": st}


def cycle_cost() -> dict:
    from eim.agents.registry import default_registry
    from eim.agents.runner import run_agents
    from tests.agents.conftest import make_snapshot
    snap = make_snapshot()
    agents = [a for a in default_registry().latest()
              if a.id not in ("arbitrage", "context", "smart_money", "calendar")]
    t = time.perf_counter()
    run_agents(agents, snap)
    return {"agents": len(agents), "run_agents_s": round(time.perf_counter() - t, 3)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--rate", type=int, default=1000)
    ap.add_argument("--shared", action="store_true", help="ambos procesos al MISMO archivo")
    a = ap.parse_args()
    out: dict = {"seconds": a.seconds, "rate_per_proc": a.rate, "shared_file": a.shared}
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        tmp = Path(td)
        spool = tmp / "spool"
        spool.mkdir()
        ps = [mp.Process(target=_producer, args=(str(spool), n, a.rate, a.seconds, a.shared))
              for n in ("p1", "p2")]
        t0 = time.perf_counter()
        for p in ps:
            p.start()
        for p in ps:
            p.join()
        out["producers_wall_s"] = round(time.perf_counter() - t0, 2)
        out["lines"] = check_lines(spool)
        out["expected"] = 2 * int(a.rate * a.seconds)
        out["spool_kb"] = round(sum(f.stat().st_size for f in spool.glob("*.jsonl")) / 1024)
        out["index"] = index(spool, tmp / "obs.duckdb")
        out["direct_db_two_writers"] = concurrent_db_write(tmp)
        cost_spool = tmp / "cost"
        out["emit_cost"] = emit_cost(str(cost_spool))
    out["cycle"] = cycle_cost()
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
