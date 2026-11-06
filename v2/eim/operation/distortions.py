"""Distorsiones conocidas de los libros que mide T31, para que el informe no las oculte.

El informe semanal cuenta lo que pasó, pero no sabe cuándo un fallo propio alteró lo medido. Lo que
se haya diagnosticado y medido se apunta aquí, con su evidencia, y sale en cada informe cuyo periodo
se solape. Se añade a mano y no se borra: es parte de la lectura de la corrida. Al resolverse se
pone `t1`. Cada equipo lleva su propia corrida y este archivo llega a todos con `main`: cada
distorsión dice de qué equipo se midió y solo sale en los informes de ese equipo.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Distortion:
    machine: str              # equipo cuyos libros se midieron (`data/machine_id`)
    t0: int                   # desde cuándo afecta a los libros (ms UTC)
    t1: int | None            # hasta cuándo; None = aún sin resolver
    title: str
    detail: str
    ref: str                  # dónde está la evidencia


KNOWN: tuple[Distortion, ...] = (
    Distortion(
        machine="juanpablo-cpu",
        t0=1_793_752_329_000,        # 2026-11-04 00:32:09 UTC, la primera fila «inconsistente»
        t1=1_793_995_705_000,        # 2026-11-06 20:08:25 UTC, la pasada tras reconciliar
        title="5 posiciones fantasma en Agresivo, Moderado y PPP (T142)",
        detail=("Congeladas por un escalón guardado antes de tener las velas de 1 min, siguieron "
                "abiertas en los libros aunque el recálculo las veía cerradas. Al reconciliarlas, "
                "el capital realizado cambió: Moderado +17,79 USDT, Agresivo −147,51 y PPP −13,14; "
                "en total −142,86. De ello, +22,22 son sus 5 cierres y −164,53 son 18 entradas "
                "que no se tomaron mientras duró. Esas 18 están en el libro fijo marcadas `retro`: "
                "se decidieron al recalcular y no son operaciones vividas en su momento. Es una "
                "medida sobre el recálculo, no un resultado operado."),
        ref="PLAN/notas/T142_posiciones_fantasma.md"),
)


def overlapping(t0: int, t1: int, machine: str | None,
                known: tuple[Distortion, ...] = KNOWN) -> list[dict]:
    """Las de este equipo que afectan al periodo [t0, t1), para el informe."""
    return [{"from": d.t0, "to": d.t1, "title": d.title, "detail": d.detail, "ref": d.ref}
            for d in known
            if d.machine == machine and d.t0 < t1 and (d.t1 is None or d.t1 > t0)]
