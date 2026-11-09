"""Registro de revisiones del almacén (T124): una fila ya guardada que cambia queda anotada.

`capture` lo llama `Store` antes de escribir: compara las filas nuevas con las guardadas del mismo
`t` (los dos tramos) y anota cada diferencia, con antes, después, momento y fuente, en
`snapshots/revisions/AAAAMMDD.<pid>.jsonl` (uno por día UTC y proceso: solo se añade y dos
procesos nunca escriben el mismo archivo). Rellenar un hueco no es una revisión: no había fila.
Volver a escribir los mismos valores tampoco. Nunca hace fallar la escritura: si no puede
anotar, lo dice en el registro.

`affected` cruza una revisión con `data_snapshots`: quedan afectadas las instantáneas de esa
serie creadas ANTES de la revisión cuyo rango contiene la fila (las posteriores ya la vieron).
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from eim.data.snapshots import DIR, SnapshotInfo
from eim.data.timeframes import tf_ms

log = logging.getLogger("eim.data")
SUB = "revisions"


def _dir(root: Path | str) -> Path:
    return Path(root) / DIR / SUB


def capture(store, con, kind: str, symbol: str, timeframe: str, cols: str,
            table: str = "new", source: str = "") -> int:
    """Anota las filas de `table` (en `con`) que cambian una fila ya guardada. Devuelve cuántas."""
    try:
        lo, hi = con.execute(f"SELECT min(t), max(t) FROM {table}").fetchone()
        src = None if lo is None else store.sql_source(kind, symbol, timeframe, lo, hi + 1)
        if src is None:
            return 0
        names = [c.strip() for c in cols.split(",")]
        diff = " OR ".join(f"o.{c} IS DISTINCT FROM n.{c}" for c in names[1:])
        rows = con.execute(
            f"SELECT {', '.join('o.' + c for c in names)}, "
            f"{', '.join('n.' + c for c in names[1:])} FROM {table} n "
            f"JOIN {src} o ON o.t = n.t WHERE {diff} ORDER BY n.t").fetchall()
        if not rows:
            return 0
        now, before_src = int(time.time() * 1000), store.source(kind, symbol, timeframe) or ""
        k = len(names)
        recs = [{"detected_ms": now, "kind": kind, "symbol": symbol, "timeframe": timeframe,
                 "t": int(r[0]), "before": dict(zip(names[1:], r[1:k], strict=True)),
                 "after": dict(zip(names[1:], r[k:], strict=True)),
                 "source_before": before_src, "source_after": source, "pid": os.getpid()}
                for r in rows]
        write(store.root, recs)
        log.warning("revisión del almacén: %d filas de %s %s %s cambiaron (T124)", len(recs),
                    kind, symbol, timeframe)
        return len(recs)
    except Exception as exc:  # noqa: BLE001 - anotar nunca tumba una escritura del almacén
        log.warning("no se pudo anotar la revisión de %s %s %s: %s", kind, symbol, timeframe, exc)
        return 0


def write(root: Path | str, recs: list[dict]) -> Path:
    d = _dir(root)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{datetime.now(UTC):%Y%m%d}.{os.getpid()}.jsonl"
    with open(p, "a", encoding="utf-8") as f:
        f.write("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in recs))
    return p


def read(root: Path | str, since_ms: int | None = None, symbol: str | None = None) -> list[dict]:
    """Revisiones anotadas (más antiguas primero)."""
    out = []
    for p in sorted(_dir(root).glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if (since_ms is None or r["detected_ms"] >= since_ms) and \
                    (symbol is None or r["symbol"] == symbol):
                out.append(r)
    return sorted(out, key=lambda r: (r["detected_ms"], r["t"]))


def touches(rev: dict, s: SnapshotInfo) -> bool:
    """¿La revisión cae dentro de la instantánea `s` y es posterior a su creación?"""
    if rev["symbol"] != s.symbol or rev["detected_ms"] <= s.created_ms:
        return False
    if rev["kind"] == "funding":
        return bool(s.n_funding or s.funding_source) and s.start_ms <= rev["t"] < s.end_ms
    return (rev["kind"], rev["timeframe"]) == (s.kind, s.timeframe) and \
        s.start_ms <= rev["t"] and rev["t"] + tf_ms(s.timeframe) <= s.end_ms


def affected(revs: list[dict], snaps: list[SnapshotInfo]) -> dict[str, list[dict]]:
    """id de instantánea → revisiones que la tocan (solo las afectadas)."""
    out: dict[str, list[dict]] = {}
    for s in snaps:
        hit = [r for r in revs if touches(r, s)]
        if hit:
            out[s.id] = hit
    return out
