"""Medición estable para las pruebas `perf` (T116): mismos umbrales, mejor medidos.

Las pruebas que miden tiempo de reloj comparan contra umbrales fijados por su tarea
(`eim/observability/thresholds.py`, presupuesto de T77…) y esos umbrales no se tocan aquí. Lo que
se cuida es la medida: llamadas de calentamiento descartadas y ≥ 100 muestras (con 20, el p95
interpolado era casi la máxima y una sola llamada lenta decidía). Se mide en condiciones reales
(recolector de basura encendido) y con el mismo índice de percentil que usaban las pruebas.
`describe()` da la cifra medida para el mensaje del fallo.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

MIN_SAMPLES = 100


@dataclass(frozen=True)
class Timing:
    """Duraciones medidas, en segundos y ordenadas."""

    samples: tuple[float, ...]

    def pct(self, q: float) -> float:
        """Percentil `q` (0..1) sin interpolar: el valor en la posición `int(q·n)` (con 100
        muestras, p95 = la 96.ª; ni la máxima ni más laxo que antes)."""
        s = self.samples
        return s[min(len(s) - 1, int(q * len(s)))]

    def ms(self, q: float) -> float:
        return self.pct(q) * 1e3

    def us(self, q: float) -> float:
        return self.pct(q) * 1e6

    def describe(self, unit: str = "ms") -> str:
        k = {"ms": 1e3, "us": 1e6, "s": 1.0}[unit]
        return (f"p50 {self.pct(0.5) * k:.1f} · p95 {self.pct(0.95) * k:.1f} · "
                f"p99 {self.pct(0.99) * k:.1f} · máx {self.samples[-1] * k:.1f} {unit} "
                f"(n={len(self.samples)})")


def measure(fn: Callable[[], object], samples: int = MIN_SAMPLES, warmup: int = 1) -> Timing:
    """Llama `fn` `warmup` veces sin medir y luego `samples` veces midiendo cada llamada."""
    if samples < MIN_SAMPLES:
        raise ValueError(f"un percentil estable pide ≥ {MIN_SAMPLES} muestras, no {samples}")
    for _ in range(warmup):
        fn()
    out = []
    for _ in range(samples):
        t = time.perf_counter()
        fn()
        out.append(time.perf_counter() - t)
    return Timing(tuple(sorted(out)))
