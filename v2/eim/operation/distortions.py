"""Distorsiones conocidas de los libros que mide T31, para que el informe no las oculte.

El informe semanal cuenta lo que pasó, pero no sabe cuándo un fallo propio alteró lo medido. Lo que
se haya diagnosticado y medido se apunta aquí, con su evidencia, y sale en cada informe cuyo periodo
se solape. Se añade a mano y no se borra: es parte de la lectura de la corrida.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Distortion:
    t0: int                   # desde cuándo afecta a los libros (ms UTC)
    t1: int | None            # hasta cuándo; None = aún sin resolver
    title: str
    detail: str
    ref: str                  # dónde está la evidencia


KNOWN: tuple[Distortion, ...] = (
    Distortion(
        t0=1_793_751_120_000,        # 2026-11-04 00:32 UTC, la primera congelada
        t1=None,
        title="5 posiciones fantasma en Agresivo, Moderado y PPP (T142)",
        detail=("Congeladas por un escalón guardado antes de tener las velas de 1 min, siguieron "
                "abiertas en los libros aunque el recálculo las ve cerradas. Medido hasta "
                "2026-11-06 00:00 UTC, frente a los mismos libros sin congelar: Moderado +17,30 "
                "USDT (7 entradas no tomadas), Agresivo −171,26 (5) y PPP −13,14 (4); en total "
                "−167,10 USDT. Sus 5 cierres (+22,22 USDT) ya están en el libro fijo: lo que le "
                "falta son las 16 entradas no tomadas (−189,33 USDT, incluido el efecto en el "
                "tamaño de las demás). Hasta reconciliarlas, Agresivo y PPP salen mejor y Moderado "
                "peor de lo que habrían salido. Es una medida sobre el recálculo, no un resultado "
                "operado, y crece mientras sigan congeladas."),
        ref="PLAN/notas/T142_posiciones_fantasma.md"),
)


def overlapping(t0: int, t1: int, known: tuple[Distortion, ...] = KNOWN) -> list[dict]:
    """Las que afectan al periodo [t0, t1), para el informe."""
    return [{"from": d.t0, "to": d.t1, "title": d.title, "detail": d.detail, "ref": d.ref}
            for d in known if d.t0 < t1 and (d.t1 is None or d.t1 > t0)]
