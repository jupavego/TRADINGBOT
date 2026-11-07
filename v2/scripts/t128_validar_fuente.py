"""T128 ◆: compara los trades por vela del recolector viejo (`micro/`, T23) y de la captura HFT
(`micro_hft/`, la fuente que lee hoy el agente microstructure) en el tramo en que corrieron los dos.

Solo lectura. Uso (desde v2/, en prioridad batch):
  python -m eim.operation.priority run batch -- python -I scripts/t128_validar_fuente.py data 60
Resultado del 2026-11-07 en `PLAN/notas/T128_validacion_fuente.md`.
"""
import sys
import time
from pathlib import Path

import duckdb

PARTS = ("symbol=BTCUSDT", "date=*", "hour=*", "part-*.parquet")
GAP_SQL = "stream IN ('depth', 'trades') AND cause <> 'silencio'"  # como eim/data/micro.py


def glob(root: Path, *kind: str) -> str:
    return root.joinpath(*kind, *PARTS).as_posix()


def fmt(ms: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(ms / 1000))


def rel(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1e-9)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    root, step = Path(sys.argv[1]), int(sys.argv[2]) * 60_000
    con = duckdb.connect(config={"memory_limit": "700MB", "threads": "2"})
    old_src = f"read_parquet('{glob(root, 'micro', 'trades')}', hive_partitioning=false)"
    new_raw = (f"read_parquet('{glob(root, 'micro_hft', 'trades')}', union_by_name=true, "
               "hive_partitioning=false)")
    o0, o1 = con.execute(f"SELECT min(t), max(t) FROM {old_src}").fetchone()
    n0, n1 = con.execute(f"SELECT min(t_ms), max(t_ms) FROM {new_raw}").fetchone()
    t0, t1 = (max(o0, n0) // step + 1) * step, (min(o1, n1) // step) * step
    print(f"viejo {fmt(o0)} → {fmt(o1)} · captura {fmt(n0)} → {fmt(n1)}")
    print(f"tramo común {fmt(t0)} → {fmt(t1)}")

    agg = ("SELECT CAST(floor((t - {t0}) / {s}) AS BIGINT) i, "
           "SUM(CASE WHEN maker THEN 0 ELSE q END), SUM(CASE WHEN maker THEN q ELSE 0 END), "
           "COUNT(*) FROM {src} WHERE t >= {t0} AND t < {t1} GROUP BY 1")
    # en la captura, un agg_id repetido tras reconectar cuenta una vez (como eim/data/micro.py)
    new_src = (f"(SELECT DISTINCT ON (agg_id) t_ms AS t, q, maker FROM {new_raw} "
               f"WHERE t_ms >= {t0} AND t_ms < {t1})")
    def bars(src: str) -> dict[int, tuple]:
        rows = con.execute(agg.format(t0=t0, t1=t1, s=step, src=src)).fetchall()
        return {r[0]: r[1:] for r in rows}

    old, new = bars(old_src), bars(new_src)
    n = (t1 - t0) // step
    bad: set[int] = set()
    try:  # instantes de hueco del recolector viejo
        q = (f"SELECT t FROM read_parquet('{glob(root, 'micro', 'gaps')}', "
             f"hive_partitioning=false) WHERE t >= {t0} AND t < {t1}")
        bad |= {int((t - t0) // step) for (t,) in con.execute(q).fetchall()}
    except duckdb.Error:
        pass
    q = (f"SELECT start_ns // 1000000, end_ns // 1000000 FROM read_parquet("
         f"'{glob(root, 'micro_hft', 'gaps')}', union_by_name=true, hive_partitioning=false) "
         f"WHERE {GAP_SQL} AND end_ns >= {t0} * 1000000 AND start_ns < {t1} * 1000000")
    for a, b in con.execute(q).fetchall():  # tramos de hueco de la captura
        bad |= set(range(max(0, (a - t0) // step), min(n - 1, (b - t0) // step) + 1))

    clean = [i for i in range(n) if i not in bad and i in old and i in new]
    holed = len(bad & set(range(n)))
    print(f"velas de {step // 60000} min: {n} · con hueco en alguna fuente: {holed}"
          f" · comparables: {len(clean)}")
    if not clean:
        return
    worst = sorted(((max(rel(old[i][0], new[i][0]), rel(old[i][1], new[i][1])), i) for i in clean),
                   reverse=True)
    exact = sum(1 for w, _ in worst if w < 1e-9)
    delta = {i: (old[i][0] - old[i][1], new[i][0] - new[i][1]) for i in clean}
    same = sum(1 for a, b in delta.values() if a * b > 0 or abs(a) < 1e-9)
    print(f"compra y venta idénticas (< 1e-9 relativo): {exact} de {len(clean)}")
    print(f"delta con el mismo signo: {same} de {len(clean)}")
    print(f"trades sumados viejo / captura: {sum(old[i][2] for i in clean)} / "
          f"{sum(new[i][2] for i in clean)}")
    for _w, i in worst[:5]:
        print(f"  {fmt(t0 + i * step)}  viejo {old[i][0]:.4f} / {old[i][1]:.4f}"
              f" · captura {new[i][0]:.4f} / {new[i][1]:.4f} (compra / venta, BTC)")


if __name__ == "__main__":
    main()
