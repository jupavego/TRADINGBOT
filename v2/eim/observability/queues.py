"""Fronteras de la tubería (T123): tope, política y contadores declarados en un solo sitio.

Cada cola entre dos etapas tiene un tamaño máximo y una política escrita para cuando se llena:
`descartar_viejo` (datos de mercado: lo reciente vale más), `descartar_nuevo` o
`frenar_productor`. El inventario con su justificación está en `PLAN/notas/T123_colas.md`, y
`tests/observability/test_queues_bounded.py` recorre el código y falla si aparece una cola sin tope.

Cada proceso cuenta, por frontera, descartes, esperas del productor, ocupación máxima y última
causa (`gauge(id)`). Un hilo daemon los emite al observatorio (T72) como `heartbeat` de la pieza
`observability.queues` con `detail.queue`, para no maquillar el latido de la pieza dueña: cada
`REPORT_EVERY_S` si algo cambió y, sin cambios, cada `KEEPALIVE_S` (así se distingue «sin
descartes» de «proceso parado» sin llenar el observatorio). `GET /v2/obs/queues` los sirve a la
interfaz. Contar nunca lanza ni bloquea; con `EIM_OBS=off` se cuenta y no se emite.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from eim.observability import emit as _emit

Policy = Literal["descartar_viejo", "descartar_nuevo", "frenar_productor"]
POLICY_ES: dict[str, str] = {"descartar_viejo": "descarta lo más viejo",
                             "descartar_nuevo": "descarta lo nuevo",
                             "frenar_productor": "frena al productor"}
COMPONENT = "observability.queues"   # pieza del catálogo que emite los informes
REPORT_EVERY_S = 60.0
KEEPALIVE_S = 600.0
WS_MAX_QUEUE = 16          # tramas por conexión de `websockets` (su valor por defecto, declarado)


@dataclass(frozen=True)
class Frontier:
    id: str
    component_id: str          # pieza del catálogo que la posee (T72)
    process: str
    capacity: int
    unit: str
    policy: Policy
    title_es: str
    why_es: str
    per_key: bool = False      # el tope es por canal/agente, no global
    measured: bool = True      # False: la librería no expone su ocupación (no se emite contador)


def _f(*a, **k) -> Frontier:
    return Frontier(*a, **k)


FRONTIERS: tuple[Frontier, ...] = (
    _f("red.websocket", "data.hft_collector", "todos los que escuchan a un exchange", WS_MAX_QUEUE,
       "tramas por conexión", "frenar_productor", "Red → recepción",
       "Es la red: solo se puede dejar de leer. El corte que llega después ya queda como hueco.",
       per_key=True, measured=False),
    _f("hft.recepcion", "data.hft_collector", "hft_collector", 50_000, "mensajes",
       "descartar_nuevo", "Recepción → proceso de la captura",
       "El libro es una secuencia: descartar lo nuevo deja un solo tramo contiguo, marcado como "
       "cola llena; descartar lo viejo la partiría dos veces."),
    _f("hft.escritor", "data.hft_collector", "hft_collector", 200_000, "filas sin escribir",
       "frenar_productor", "Proceso → disco de la captura",
       "≈ 4 min de disco parado sin perder nada (≈ 70 MB). Después el proceso espera y la "
       "recepción sigue: lo que no quepa lo descarta ella, con marca; la pérdida, en un sitio."),
    _f("micro.escritor", "data.micro_collector", "hft_collector, liq_collector, collector", 5_000,
       "filas por volcado", "frenar_productor", "Proceso → disco (microestructura y liquidaciones)",
       "La escritura es síncrona: el bucle espera al disco. Se cuentan las filas que un fallo de "
       "escritura deja fuera."),
    _f("api.cierres", "api.hub", "api", 1, "vela por canal", "descartar_viejo",
       "Cierre de vela → análisis",
       "Si cierra otra vela mientras se analiza la anterior, se analiza la más reciente. La vela "
       "se guarda igual en el almacén.", per_key=True),
    _f("api.clientes", "api.hub", "api", 256, "mensajes por cliente", "descartar_viejo",
       "Difusor → cada pantalla abierta",
       "Una pantalla lenta pierde lo más viejo y nunca frena al difusor ni a las demás.",
       per_key=True),
    _f("agentes.hilos", "api.hub", "api, operation", 1, "hilo colgado por agente y canal",
       "descartar_nuevo", "Instantánea → agentes",
       "Plazo común desde el envío. Mientras un agente siga colgado de una vela anterior sale "
       "degradado sin lanzar otro hilo.", per_key=True),
    _f("pronostico.hilos", "forecast.engine", "api, operation", 1, "hilo colgado por canal",
       "descartar_nuevo", "Análisis → pronóstico",
       "El pronóstico que no llega a tiempo se salta y se cuenta; la decisión sigue sin él.",
       per_key=True),
    _f("obs.emisor", "observability.indexer", "todos", 10_000, "eventos", "descartar_nuevo",
       "Proceso → observatorio",
       "Observar nunca frena lo observado: con la cola llena el evento se descarta y se cuenta."),
)
BY_ID: dict[str, Frontier] = {f.id: f for f in FRONTIERS}


def capacity(fid: str) -> int:
    return BY_ID[fid].capacity


class Gauge:
    """Contadores de una frontera en este proceso (exactos desde `since_ms`)."""

    def __init__(self, frontier: Frontier, probe: Callable[[], int] | None = None) -> None:
        self.f, self.probe = frontier, probe
        self._lock = threading.Lock()
        self.since_ms = int(time.time() * 1000)
        self.occupancy = self.max_occupancy = 0
        self.dropped = self.held = 0
        self.held_s = 0.0
        self.last_cause, self.last_ms = "", None
        self._rep_dropped = self._rep_held = 0
        self._sig: tuple = ()
        self._rep_at = 0.0

    def due(self, now: float) -> bool:
        """¿Toca informar? Si cambió algo desde el último informe o pasó `KEEPALIVE_S`."""
        sig = (self.dropped, self.held, self.max_occupancy)
        return sig != self._sig or now - self._rep_at >= KEEPALIVE_S

    def seen(self, occupancy: int) -> None:
        self.occupancy = occupancy
        if occupancy > self.max_occupancy:
            self.max_occupancy = occupancy

    def drop(self, n: int = 1, cause: str = "") -> None:
        with self._lock:
            self.dropped += n
            self.last_cause, self.last_ms = cause[:160], int(time.time() * 1000)

    def hold(self, seconds: float, cause: str = "") -> None:
        """El productor esperó `seconds` (política `frenar_productor`)."""
        with self._lock:
            self.held += 1
            self.held_s += seconds
            self.last_cause, self.last_ms = cause[:160], int(time.time() * 1000)

    def detail(self) -> dict:
        with self._lock:
            if self.probe is not None:
                try:
                    self.seen(int(self.probe()))
                except Exception:  # noqa: BLE001, S110 - medir nunca rompe
                    pass
            new_d, new_h = self.dropped - self._rep_dropped, self.held - self._rep_held
            self._rep_dropped, self._rep_held = self.dropped, self.held
            self._sig = (self.dropped, self.held, self.max_occupancy)
            self._rep_at = time.monotonic()
            return {"queue": self.f.id, "capacity": self.f.capacity, "policy": self.f.policy,
                    "occupancy": self.occupancy, "max_occupancy": self.max_occupancy,
                    "dropped": self.dropped, "dropped_new": new_d, "held": self.held,
                    "held_new": new_h, "held_s": round(self.held_s, 1),
                    "last_cause": self.last_cause, "last_ms": self.last_ms,
                    "since_ms": self.since_ms, "pid": os.getpid()}


_GAUGES: dict[str, Gauge] = {}
_LOCK = threading.Lock()
_reporter: tuple[int, threading.Thread] | None = None
_emitter_seen: dict = {"dropped": 0, "sig": (), "at": 0.0}   # lo ya informado del emisor


def gauge(fid: str, probe: Callable[[], int] | None = None) -> Gauge:
    """El contador de `fid` en este proceso (lo crea, y arranca el emisor periódico)."""
    global _reporter
    with _LOCK:
        g = _GAUGES.get(fid)
        if g is None:
            g = _GAUGES[fid] = Gauge(BY_ID[fid], probe)
        elif probe is not None:
            g.probe = probe
        if _reporter is None or _reporter[0] != os.getpid() or not _reporter[1].is_alive():
            t = threading.Thread(target=_loop, name="eim-queues", daemon=True)
            _reporter = (os.getpid(), t)
            t.start()
    return g


def _emitter_detail(force: bool) -> dict | None:
    s, seen, now = _emit.stats(), _emitter_seen, time.monotonic()
    sig = (s["dropped"], s["max_queued"])
    if not force and sig == seen["sig"] and now - seen["at"] < KEEPALIVE_S:
        return None
    new = max(0, s["dropped"] - seen["dropped"])   # 0 si el emisor se reconfiguró
    seen.update(dropped=s["dropped"], sig=sig, at=now)
    return {"queue": "obs.emisor", "capacity": s["capacity"], "policy": "descartar_nuevo",
            "occupancy": s["queued"], "max_occupancy": s["max_queued"], "dropped": s["dropped"],
            "dropped_new": new,
            "last_cause": s["last_cause"][:160], "since_ms": s["since_ms"], "pid": os.getpid()}


def report(force: bool = True) -> int:
    """Emite el estado de las fronteras contadas en este proceso (con `force=False`, solo las que
    cambiaron o llevan `KEEPALIVE_S` sin informar). Devuelve cuántas; nunca lanza."""
    n = 0
    try:
        process, now = _emit.stats()["process"], time.monotonic()
        with _LOCK:
            gauges = list(_GAUGES.values())
        rows = [g.detail() for g in gauges if force or g.due(now)]
        if (em := _emitter_detail(force)) is not None:
            rows.append(em)
        for d in rows:
            bad = d.get("dropped_new", 0) or d.get("held_new", 0)
            n += bool(_emit.emit("heartbeat", COMPONENT, status="degraded" if bad else "ok",
                                 detail=d, coverage=1.0,
                                 source=f"contador en memoria del proceso {process}"))
    except Exception:  # noqa: BLE001, S110 - informar nunca tumba al proceso
        pass
    return n


def _loop() -> None:
    while True:
        time.sleep(REPORT_EVERY_S)
        report(force=False)
