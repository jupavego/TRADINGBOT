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


def compact_dir(d: Path) -> tuple[int, int] | None:
    """Une los `part-*.parquet` de `d`; (archivos antes, filas) o None si no hacía falta."""
    parts = sorted(d.glob("part-*.parquet"))
    if len(parts) < 2:
        return None
    lst = "[" + ", ".join(_q(p) for p in parts) + "]"
    tmp = d / f"compact-{time.time_ns()}.tmp"
    con = duckdb.connect()
    con.execute("SET threads = 1")                 # el equipo anda corto de memoria
    con.execute("SET memory_limit = '300MB'")
    con.execute(f"SET temp_directory = {_q(d / '.duck_tmp')}")
    try:
        n0, s0 = con.execute(f"SELECT COUNT(*), COALESCE(SUM(t), 0) FROM read_parquet({lst})"
                             ).fetchone()
        con.execute(f"COPY (SELECT * FROM read_parquet({lst}) ORDER BY t) TO {_q(tmp)} "
                    "(FORMAT parquet)")
        n1, s1 = con.execute(f"SELECT COUNT(*), COALESCE(SUM(t), 0) FROM read_parquet({_q(tmp)})"
                             ).fetchone()
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
