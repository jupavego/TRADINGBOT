"""Medición estable para las pruebas `perf` (T116): mismos umbrales, mejor medidos.

Las pruebas que miden tiempo de reloj comparan contra umbrales fijados por su tarea
(`eim/observability/thresholds.py`, presupuesto de T77…) y esos umbrales no se tocan aquí. Lo que
se cuida es la medida: llamadas de calentamiento descartadas y ≥ 100 muestras (con 20, el p95
interpolado era casi la máxima y una sola llamada lenta decidía). Se mide en condiciones reales
(recolector de basura encendido) y con el mismo índice de percentil que usaban las pruebas.
`describe()` da la cifra medida para el mensaje del fallo.

Con el equipo cargado (2026-11-02, `juanpablo-cpu`): el gate corre en IDLE por la cola de T127
para no quitarle CPU a la captura, y entonces el reloj mide cuánto deja Windows esperar a un
proceso IDLE, no lo que tarda el código (p95 120 ms > 100 ms con la prueba aislada a 15 ms).
Por eso: (1) cada prueba `perf` sube el proceso a NORMAL mientras corre (`normal_priority`, un
autouse en `tests/conftest.py`), que sigue por debajo de la captura (ABOVE_NORMAL), y (2)
`measure` hace `ROUNDS` rondas y entrega la de p95 mediano («mediana de varias repeticiones»,
T116): una pausa de la cola o un pico ajeno en una ronda no decide.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

MIN_SAMPLES = 100
ROUNDS = 3
NORMAL = 0x20       # NORMAL_PRIORITY_CLASS


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


def measure(fn: Callable[[], object], samples: int = MIN_SAMPLES, warmup: int = 1,
            rounds: int = ROUNDS) -> Timing:
    """Llama `fn` `warmup` veces sin medir y luego, `rounds` veces, `samples` llamadas midiendo
    cada una; entrega la ronda de p95 mediano."""
    if samples < MIN_SAMPLES:
        raise ValueError(f"un percentil estable pide ≥ {MIN_SAMPLES} muestras, no {samples}")
    for _ in range(warmup):
        fn()
    runs = []
    for _ in range(rounds):
        out = []
        for _ in range(samples):
            t = time.perf_counter()
            fn()
            out.append(time.perf_counter() - t)
        runs.append(Timing(tuple(sorted(out))))
    return sorted(runs, key=lambda r: r.pct(0.95))[len(runs) // 2]


@contextmanager
def normal_priority() -> Iterator[None]:
    """El proceso en NORMAL mientras dura el bloque si corría por debajo (IDLE en la cola,
    BELOW_NORMAL desde la tarea programada); luego vuelve a la de antes. Solo Windows."""
    from eim.operation import priority

    prev = priority.current_class() if sys.platform == "win32" else None
    low = prev in (priority.WINDOWS_CLASS["batch"], priority.WINDOWS_CLASS["service"])
    if low:
        priority._set_class(NORMAL)
    try:
        yield
    finally:
        if low:
            priority._set_class(prev)
