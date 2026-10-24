"""Reloj local de recepción de la captura HFT (T78).

En Windows `time.time_ns()` avanza a saltos de ~1–16 ms y `time.monotonic()` (GetTickCount64) de
16 ms; `perf_counter_ns()` (QueryPerformanceCounter) resuelve 100 ns. Por eso cada mensaje lleva
`mono_ns` = `perf_counter_ns()` y `recv_ns` = `mono_ns` + desfase, un UTC de alta resolución anclado
al reloj de pared en el instante en que este cambia de valor.

`check()` (cada `CHECK_S`) compara con el reloj de pared, cuyas lecturas solo pueden ir atrasadas
(por su granularidad): una desviación ≥ `JUMP_MS` es un **salto** (NTP, cambio manual) y se
re-ancla en el acto; si no, el máximo de la ventana (la lectura menos atrasada) mide la deriva y,
si supera `SLEW_MS`, se re-ancla como **ajuste**. Ambos quedan registrados (tabla `clock`); el
`mono_ns` nunca salta, así que los intervalos entre mensajes siguen siendo exactos.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

CHECK_S = 10.0
JUMP_MS = 100.0
SLEW_MS = 5.0
WINDOW = 6
_SPIN_MAX = 200_000            # lecturas como máximo esperando a que cambie el reloj de pared


class RecvClock:
    def __init__(self, wall: Callable[[], int] = time.time_ns,
                 mono: Callable[[], int] = time.perf_counter_ns) -> None:
        self._wall, self._mono = wall, mono
        self._devs: deque[int] = deque(maxlen=WINDOW)
        self.offset = self._anchor()

    def _anchor(self) -> int:
        """Desfase pared − monotónico medido justo cuando la lectura de pared cambia."""
        w0 = w = self._wall()
        for _ in range(_SPIN_MAX):
            w = self._wall()
            if w != w0:
                break
        return w - self._mono()

    def now(self) -> tuple[int, int]:
        """(recv_ns UTC, mono_ns)."""
        m = self._mono()
        return m + self.offset, m

    def check(self) -> tuple[str, int, int] | None:
        """(«salto»|«ajuste», ns corregidos, hora de pared) si hubo que re-anclar; si no, None."""
        utc, _ = self.now()
        wall = self._wall()
        dev = wall - utc
        if abs(dev) >= JUMP_MS * 1e6:
            self._devs.clear()
            self.offset = self._anchor()
            return "salto", dev, wall
        self._devs.append(dev)
        if len(self._devs) == WINDOW:
            est = max(self._devs)
            if abs(est) >= SLEW_MS * 1e6:
                self._devs.clear()
                self.offset += est
                return "ajuste", est, wall
        return None
