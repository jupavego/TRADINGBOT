"""Elección de fotogramas candidatos (T66), pura: escenas + muestreo mínimo + duplicados + tope.

Entrada: muestras `(t, hash, rejilla)` de un video recorrido a `sample_every_s`. Un candidato
nace en cada corte de escena (Hamming del dHash ≥ `cut_hash_bits` o diferencia de rejilla ≥
`cut_grid_mad` frente a la muestra anterior) y, sin cortes, cada `min_every_s`. Se descartan los
casi idénticos a uno ya elegido (Hamming ≤ `dup_hash_bits`) y, si pasan del tope de T62, quedan
los de mayor cambio, en orden temporal.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from eim.video.visual.imageops import grid_mad, hamming
from eim.video.visual.params import DEFAULT, VisualParams


@dataclass(frozen=True)
class Sample:
    t: float
    hash: int
    grid: np.ndarray


@dataclass(frozen=True)
class Candidate:
    t: float
    hash: int
    reason: str        # inicio | corte | muestreo
    change: float      # magnitud del cambio que lo hizo candidato (0..1)


@dataclass(frozen=True)
class Selection:
    chosen: list[Candidate]
    n_samples: int
    n_candidates: int
    n_duplicates: int
    n_over_cap: int
    cap: int


def candidates(samples: list[Sample], p: VisualParams = DEFAULT) -> list[Candidate]:
    out: list[Candidate] = []
    prev: Sample | None = None
    last_t = -1e18
    bits = p.hash_size * p.hash_size
    for s in samples:
        if prev is None:
            out.append(Candidate(s.t, s.hash, "inicio", 1.0))
            last_t = s.t
        else:
            dh = hamming(s.hash, prev.hash)
            dg = grid_mad(s.grid, prev.grid)
            if dh >= p.cut_hash_bits or dg >= p.cut_grid_mad:
                out.append(Candidate(s.t, s.hash, "corte", max(dh / bits, min(1.0, dg * 4))))
                last_t = s.t
            elif s.t - last_t >= p.min_every_s:
                out.append(Candidate(s.t, s.hash, "muestreo", 0.0))
                last_t = s.t
        prev = s
    return out


def select(samples: list[Sample], duration_s: float, p: VisualParams = DEFAULT) -> Selection:
    cands = candidates(samples, p)
    kept: list[Candidate] = []
    dups = 0
    for c in cands:
        if any(hamming(c.hash, k.hash) <= p.dup_hash_bits for k in kept):
            dups += 1
            continue
        kept.append(c)
    cap = p.frame_cap(duration_s)
    over = max(0, len(kept) - cap)
    if over:
        best = sorted(kept, key=lambda c: (-(c.reason == "inicio"), -c.change, c.t))[:cap]
        kept = sorted(best, key=lambda c: c.t)
    return Selection(kept, len(samples), len(cands), dups, over, cap)
