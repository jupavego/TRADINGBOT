"""Compactación de la microestructura: une los `part-*.parquet` de cada hora ya cerrada en uno.

Los recolectores vuelcan cada ~30 s, así que una hora deja ~100 archivos por tipo. Leer una
ventana larga abría miles de archivos (el `/v2/snapshot` tardaba 30 s y crecía cada día). Aquí se
une cada hora cerrada (más de `margin_h` horas atrás, para no tocar lo que aún se escribe) en un
solo archivo ordenado por `t`. Antes de quitar los originales se verifica el resultado
(nº de filas y suma de `t` iguales); si algo no cuadra, no se toca nada.

Uso: `python -m eim.data.collectors.compact --root data [--max-dirs N]`.
"""

from __future__ import annotations

import argparse
import calendar
import shutil
import time
from pathlib import Path

import duckdb

KINDS = ("trades", "top", "depth", "liqs", "gaps")


def _q(path: Path | str) -> str:
    return "'" + Path(path).as_posix().replace("'", "''") + "'"


def _out_of_order(con, path: Path, cols: list[str]) -> int:
    """Filas que no siguen estrictamente a la anterior según `cols` (orden lexicográfico)."""
    lag = ", ".join(f"lag({c}) OVER () AS p_{c}" for c in cols)
    cond, eq = [], []
    for i, c in enumerate(cols):
        op = "<=" if i == len(cols) - 1 else "<"
        cond.append("(" + " AND ".join([*eq, f"{c} {op} p_{c}"]) + ")")
        eq.append(f"{c} = p_{c}")
    q = (f"SELECT count(*) FROM (SELECT {', '.join(cols)}, {lag} FROM "
         f"read_parquet({_q(path)}, hive_partitioning = false)) "
         f"WHERE p_{cols[0]} IS NOT NULL AND ({' OR '.join(cond)})")
    return int(con.execute(q).fetchone()[0])


def compact_dir(d: Path, key: str = "t", order: str = "t", codec: str | None = None,
                presorted: bool = False, row_group_size: int | None = None
                ) -> tuple[int, int] | None:
    """Une los `part-*.parquet` de `d`; (archivos antes, filas) o None si no hacía falta.

    `key` se suma para verificar, `order` ordena el resultado y `codec` fija la compresión.
    `presorted` (captura HFT, T78): cada parte ya viene ordenada por `order` y las partes no se
    solapan, así que se concatenan en el orden de su primera fila sin reordenar en memoria y se
    verifica que el resultado quede en orden estricto. `row_group_size` acota la memoria del
    escritor (las filas con listas de niveles pesan KB: un grupo por defecto no cabe en 300 MB)."""
    parts = sorted(d.glob("part-*.parquet"))
    if len(parts) < 2:
        return None
    tmp = d / f"compact-{time.time_ns()}.tmp"
    con = duckdb.connect()
    con.execute("SET threads = 1")                 # el equipo anda corto de memoria
    con.execute("SET memory_limit = '300MB'")
    con.execute(f"SET temp_directory = {_q(d / '.duck_tmp')}")
    try:
        if presorted:
            parts.sort(key=lambda p: con.execute(
                f"SELECT {order} FROM read_parquet({_q(p)}, hive_partitioning = false) LIMIT 1"
            ).fetchone())
        lst = "[" + ", ".join(_q(p) for p in parts) + "]"
        src = f"read_parquet({lst}, hive_partitioning = false, union_by_name = true)"
        n0, s0 = con.execute(f"SELECT COUNT(*), COALESCE(SUM({key}), 0) FROM {src}").fetchone()
        opts = "FORMAT parquet" + (f", COMPRESSION {codec}" if codec else "") + (
            f", ROW_GROUP_SIZE {row_group_size}" if row_group_size else "")
        sel = f"SELECT * FROM {src}" + ("" if presorted else f" ORDER BY {order}")
        con.execute(f"COPY ({sel}) TO {_q(tmp)} ({opts})")
        n1, s1 = con.execute(f"SELECT COUNT(*), COALESCE(SUM({key}), 0) FROM "
                             f"read_parquet({_q(tmp)}, hive_partitioning = false)").fetchone()
        if presorted and (bad := _out_of_order(con, tmp, [c.strip() for c in order.split(",")])):
            raise RuntimeError(f"partes solapadas en {d}: {bad} filas fuera de orden; no se toca")
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    finally:
        con.close()
        shutil.rmtree(d / ".duck_tmp", ignore_errors=True)
    if (n0, s0) != (n1, s1):
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"compactación inconsistente en {d}: {n0}/{s0} → {n1}/{s1}")
    olds = [p.with_name(p.name + ".old") for p in parts]
    for p, o in zip(parts, olds, strict=True):      # ventana de milisegundos sin datos visibles
        p.rename(o)
    tmp.rename(d / f"part-compact-{time.time_ns()}.parquet")
    for o in olds:
        o.unlink(missing_ok=True)
    return len(parts), int(n1)


def compact_closed(root: str | Path, now_ms: int, margin_h: int = 2,
                   max_dirs: int | None = None) -> list[tuple[str, int, int]]:
    """Compacta las horas cerradas de `root/micro/*/symbol=*/date=*/hour=*`."""
    cutoff = now_ms // 3_600_000 - margin_h
    out: list[tuple[str, int, int]] = []
    for kind in KINDS:
        for d in sorted((Path(root) / "micro" / kind).glob("symbol=*/date=*/hour=*")):
            if max_dirs is not None and len(out) >= max_dirs:
                return out
            try:
                day = time.strptime(d.parent.name.removeprefix("date="), "%Y-%m-%d")
                hour = int(d.name.removeprefix("hour="))
            except ValueError:
                continue
            h = calendar.timegm(day) // 3600 + hour           # hora UTC absoluta
            if h >= cutoff:
                continue
            try:
                res = compact_dir(d)
            except Exception as e:  # noqa: BLE001 - una hora problemática no frena las demás
                print(f"aviso: {d}: {type(e).__name__}: {e}")
                continue
            if res:
                out.append((str(d), *res))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", required=True)
    ap.add_argument("--max-dirs", type=int, default=None)
    a = ap.parse_args()
    done = compact_closed(a.root, int(time.time() * 1000), max_dirs=a.max_dirs)
    files = sum(x[1] for x in done)
    print(f"{len(done)} horas compactadas ({files} archivos -> {len(done)}), "
          f"{sum(x[2] for x in done)} filas verificadas")


if __name__ == "__main__":
    main()
