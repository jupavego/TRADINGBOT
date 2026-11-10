"""Gestor de recursos de los motores locales (T63).

- **Un modelo cargado a la vez**: una sola llamada corre en cada momento (cola con prioridad:
  menor número = antes; empate = orden de llegada) y, si la siguiente usa otro modelo, el
  anterior se descarga antes (`unload`).
- **RAM**: antes de cargar se comprueba que la RAM libre cubra el pico medido del modelo
  (`catalog.need_mb`, de T62) más el margen; si no, la etapa se **aplaza** (`Deferred`), el
  servicio sigue. Durante la llamada se mide la RAM consumida en el pico.
- **Tiempo**: tope por llamada (la llamada corre en un hilo; si se pasa, se devuelve
  `timeout` y la cola sigue ocupada hasta que el hilo termine: nunca hay dos modelos a la vez) y
  presupuesto de cómputo por día UTC (`ComputeGuard`, el `CostGuard` del tiempo de CPU).
"""

from __future__ import annotations

import ctypes
import heapq
import itertools
import os
import threading
import time
from collections.abc import Callable
from typing import Any

from eim.localai.engines import Backend

MB = 1024 * 1024


class Deferred(Exception):
    """No hay recursos ahora (RAM, cola o presupuesto): la etapa se aplaza, no falla."""


class CallTimeout(Exception):
    """La llamada pasó su tiempo máximo."""


def free_ram_mb() -> float | None:
    """RAM física libre del sistema (MB), o None si no se puede leer."""
    if os.name == "nt":
        class _Mem(ctypes.Structure):
            _fields_ = [("len", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                (n, ctypes.c_uint64) for n in ("tot", "avail", "tpf", "apf", "tv", "av", "ae")]
        st = _Mem()
        st.len = ctypes.sizeof(_Mem)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return st.avail / MB
        return None
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        return None
    return None


class ComputeGuard:
    """Presupuesto de segundos de cómputo por día UTC (0 = sin tope). Igual que `CostGuard`:
    `allows()` antes de llamar, `add()` después; se reinicia solo al cambiar el día."""

    def __init__(self, max_s_per_day: float = 0.0, clock: Callable[[], float] = time.time):
        self.max_s, self._clock = max_s_per_day, clock
        self.spent, self._day = 0.0, int(clock() // 86_400)

    def _roll(self) -> None:
        day = int(self._clock() // 86_400)
        if day != self._day:
            self._day, self.spent = day, 0.0

    def allows(self) -> bool:
        self._roll()
        return self.max_s <= 0 or self.spent < self.max_s

    def add(self, seconds: float) -> None:
        self._roll()
        self.spent += max(0.0, seconds)


class _Sampler:
    """Mide en segundo plano la RAM libre mínima durante una llamada."""

    def __init__(self, probe: Callable[[], float | None], every_s: float = 0.25) -> None:
        self.probe, self.every = probe, every_s
        self.start = probe()
        self.low = self.start
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True, name="localai-ram")

    def _run(self) -> None:
        while not self._stop.wait(self.every):
            v = self.probe()
            if v is not None and (self.low is None or v < self.low):
                self.low = v

    def __enter__(self) -> _Sampler:
        self._t.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        v = self.probe()
        if v is not None and (self.low is None or v < self.low):
            self.low = v

    def peak_mb(self) -> float | None:
        return None if self.start is None or self.low is None else round(
            max(0.0, self.start - self.low), 1)


class ResourceManager:
    def __init__(self, ram_margin_mb: float = 1024.0, wait_s: float = 1800.0,
                 guard: ComputeGuard | None = None,
                 ram_probe: Callable[[], float | None] = free_ram_mb,
                 sample_every_s: float = 0.25) -> None:
        self.margin, self.wait_s = ram_margin_mb, wait_s
        self.guard = guard or ComputeGuard()
        self.probe, self.every = ram_probe, sample_every_s
        self._cv = threading.Condition()
        self._heap: list[tuple[int, int]] = []
        self._seq = itertools.count()
        self._busy = False
        self.loaded: Backend | None = None

    # --- cola ------------------------------------------------------------------------------
    def _acquire(self, priority: int) -> None:
        with self._cv:
            ticket = (priority, next(self._seq))
            heapq.heappush(self._heap, ticket)
            deadline = time.monotonic() + self.wait_s
            while self._busy or self._heap[0] != ticket:
                left = deadline - time.monotonic()
                if left <= 0 or not self._cv.wait(left):
                    if self._busy or self._heap[0] != ticket:
                        self._heap.remove(ticket)
                        heapq.heapify(self._heap)
                        self._cv.notify_all()
                        raise Deferred(f"cola ocupada más de {self.wait_s:.0f} s")
            heapq.heappop(self._heap)
            self._busy = True

    def _release(self) -> None:
        with self._cv:
            self._busy = False
            self._cv.notify_all()

    # --- carga y descarga ------------------------------------------------------------------
    def _switch(self, backend: Backend) -> None:
        if self.loaded is not None and self.loaded is not backend:
            self.unload()

    def unload(self) -> None:
        """Descarga explícita del modelo cargado (al cambiar de modelo o al terminar)."""
        b, self.loaded = self.loaded, None
        if b is not None:
            try:
                b.unload()
            except Exception:  # noqa: BLE001 — descargar nunca tumba al llamador
                pass

    def check_ram(self, need_mb: float) -> None:
        free = self.probe()
        if free is not None and free < need_mb + self.margin:
            raise Deferred(f"RAM libre {free:.0f} MB < {need_mb:.0f} MB del modelo + "
                           f"{self.margin:.0f} MB de margen: la etapa se aplaza")

    # --- llamada ---------------------------------------------------------------------------
    def run(self, backend: Backend, need_mb: float, fn: Callable[[], Any], timeout_s: float,
            priority: int = 5) -> tuple[Any, float | None, float]:
        """Ejecuta `fn` con el modelo de `backend` cargado. Devuelve (salida, RAM pico, s).
        Lanza `Deferred`, `CallTimeout` o la excepción del backend."""
        if not self.guard.allows():
            raise Deferred(f"presupuesto de cómputo del día agotado ({self.guard.max_s:.0f} s)")
        self._acquire(priority)
        released = False
        try:
            self._switch(backend)
            if self.loaded is None:
                self.check_ram(need_mb)
            self.loaded = backend
            box: dict[str, Any] = {}
            lock = threading.Lock()

            def work() -> None:
                try:
                    box["out"] = fn()
                except BaseException as e:  # noqa: BLE001 — se re-lanza en el hilo llamador
                    box["err"] = e
                finally:
                    with lock:
                        box["done"] = True
                        orphan = box.get("orphan", False)
                    if orphan:   # el llamador ya se fue por tiempo agotado: libera aquí
                        self.unload()
                        self._release()

            t0 = time.monotonic()
            with _Sampler(self.probe, self.every) as s:
                th = threading.Thread(target=work, daemon=True, name="localai-call")
                th.start()
                th.join(timeout_s)
            elapsed = time.monotonic() - t0
            self.guard.add(elapsed)
            with lock:
                if not box.get("done"):
                    box["orphan"] = released = True   # el hilo libera la cola al terminar
            if released:
                raise CallTimeout(f"sin respuesta en {timeout_s:.0f} s")
            if "err" in box:
                raise box["err"]
            return box.get("out"), s.peak_mb(), elapsed
        finally:
            if not released:
                self._release()
