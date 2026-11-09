"""Sello de reproducibilidad de un resultado (T124), igual en todos los informes.

`stamp` va en el JSON del resultado (`meta.reproducibility`); `markdown_line` lo dice en el
informe. Un resultado sin sello se declara **no reproducible**, sin excepciones: así se ve de
un vistazo qué cifras de antes de T124 no fijaron sus datos.
"""

from __future__ import annotations

from eim.data.snapshots import SnapshotInfo

WHY_NONE = "sin instantánea de datos (resultado anterior a T124 o el registro falló)"


def stamp(infos: list[SnapshotInfo], result_id: str | None, why: str = "") -> dict:
    if not infos or not result_id:
        return {"reproducible": False, "why": why or WHY_NONE, "snapshots": []}
    return {"reproducible": True, "result_id": result_id,
            "repeat": f"python -m eim.repro repetir {result_id}",
            "snapshots": [{"id": i.id, "frozen": i.frozen, "symbol": i.symbol,
                           "timeframe": i.timeframe, "start_ms": i.start_ms, "end_ms": i.end_ms,
                           "content_hash": i.content_hash, "source": i.source,
                           "coverage": i.coverage()} for i in infos]}


def markdown_line(repro: dict | None) -> str:
    if not repro or not repro.get("reproducible"):
        why = (repro or {}).get("why") or WHY_NONE
        return f"> **No reproducible** (T124): {why}."
    snaps = "; ".join(
        f"`{s['id']}` ({'congelada' if s['frozen'] else 'ligera'}, {s['symbol']} "
        f"{s['timeframe']}, {s['coverage']['candles']} velas, {s['coverage']['gaps']} huecos, "
        f"fuente {s['source']})" for s in repro["snapshots"])
    return (f"Reproducible (T124): datos fijados en {snaps}. Repetir: "
            f"`{repro['repeat']}` (resultado `{repro['result_id']}`).")
