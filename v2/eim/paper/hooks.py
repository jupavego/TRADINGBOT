"""Ganchos del bróker simulado fuera de su ciclo (T128, entregable 3).

Antes el ciclo del bróker esperaba a sus ganchos (validación de 4 h, libro fijo, puntuación de
bots, setups) y callaba mientras corrían: al cierre de cada vela de 4 h, entre 100 y 230 s sin
latir. Lo caro no son los ganchos (2 s la validación, 2 s la puntuación, 0,3 s los setups) sino
la vista del bróker que rehacen cuando hay contextos nuevos (~30 s de CPU).

Ahora el ciclo solo avisa (`kick`) y sigue: los ganchos corren en orden en su propio hilo, con
la prioridad del nivel `batch` (`priority.lower_thread`), y laten por su cuenta. `paper.hooks`
late tras cada pasada (muestreado), con lo que tardó cada gancho y sus errores. Un gancho que
devuelve True hizo trabajo de verdad (p. ej. la validación al cierre de 4 h) y, si tiene
componente, late también con el suyo. Un aviso mientras corre una pasada deja otra pendiente,
nunca una cola. Ningún gancho tumba al resto ni al servicio.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from eim.core import Mode
from eim.observability import hooks_service
from eim.operation.priority import lower_thread

COMPONENT = "paper.hooks"
BEAT_EVERY_S = 240.0            # un latido cada ~4 min aunque las pasadas sean cada minuto
ERROR_EVERY_S = 900.0           # el mismo error, como mucho un aviso cada 15 min


@dataclass
class Hook:
    name: str
    fn: Callable[[], object]
    component: str | None = None    # latido propio cuando hace trabajo de verdad


class HookRunner:
    def __init__(self, beat_every_s: float = BEAT_EVERY_S) -> None:
        self.hooks: list[Hook] = []
        self.beat_every_s = beat_every_s
        self.passes = 0
        self.running = False
        self.last_pass: int | None = None
        self.last: dict[str, dict] = {}         # por gancho: ms, si trabajó y su error
        self._kick = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def add(self, name: str, fn: Callable[[], object], component: str | None = None) -> None:
        self.hooks.append(Hook(name, fn, component))

    # --- hilo -------------------------------------------------------------------------
    def start(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="eim-paper-hooks",
                                            daemon=True)
            self._thread.start()

    def kick(self) -> None:
        """Lo llama el ciclo del bróker tras cada vuelta; nunca espera."""
        self._kick.set()

    def stop(self) -> None:
        self._stop.set()
        self._kick.set()

    def _loop(self) -> None:
        lower_thread()
        while True:
            self._kick.wait()
            if self._stop.is_set():
                return
            self._kick.clear()
            self.run_once()

    # --- una pasada -------------------------------------------------------------------
    def run_once(self) -> dict:
        self.running = True
        t0 = time.perf_counter()
        ms, ran, errors = {}, [], {}
        try:
            for h in self.hooks:
                s = time.perf_counter()
                did, err = False, ""
                try:
                    did = h.fn() is True
                except Exception as exc:  # noqa: BLE001 - un gancho nunca tumba a los demás
                    err = f"{type(exc).__name__}: {exc}"
                    hooks_service.service_error(COMPONENT, exc, detail={"hook": h.name},
                                                mode=Mode.SIMULADO, min_interval_s=ERROR_EVERY_S)
                ms[h.name] = round((time.perf_counter() - s) * 1000)
                self.last[h.name] = {"ms": ms[h.name], "ran": did, "error": err,
                                     "at": int(time.time() * 1000)}
                if err:
                    errors[h.name] = err[:120]
                if did:
                    ran.append(h.name)
                    if h.component:
                        hooks_service.beat(h.component, mode=Mode.SIMULADO,
                                           duration_ms=ms[h.name], detail={"hook": h.name})
        finally:
            self.running = False
        total = round((time.perf_counter() - t0) * 1000)
        self.passes += 1
        self.last_pass = int(time.time() * 1000)
        hooks_service.beat(COMPONENT, mode=Mode.SIMULADO, duration_ms=total,
                           status="degraded" if errors else "ok",
                           detail={"ms": ms, "ran": ran, "errors": errors},
                           min_interval_s=self.beat_every_s)
        return {"ms": ms, "ran": ran, "errors": errors, "total_ms": total}

    def status(self) -> dict:
        return {"passes": self.passes, "running": self.running, "last_pass": self.last_pass,
                "hooks": {h.name: self.last.get(h.name) for h in self.hooks}}
