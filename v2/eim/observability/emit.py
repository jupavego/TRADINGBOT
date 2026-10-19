"""Emisor de eventos del observatorio (T72): observa sin poder romper lo observado.

Contrato: `emit()` y `span()` NUNCA lanzan ni bloquean. Cada evento va a una cola acotada y un
hilo escritor lo añade como una línea JSON a `data/obs/spool/<proceso>.<AAAAMMDD>.<pid>.jsonl`
(un archivo por proceso y día: sin cerrojo entre procesos; un solo indexador los carga en la
base, T73). Cola llena, disco lleno, permiso denegado o evento inválido → se descarta y se
cuenta (`stats()["dropped"]`). `EIM_OBS=off` lo apaga por completo.
"""

from __future__ import annotations

import atexit
import contextlib
import contextvars
import os
import queue
import re
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from eim.core.mode import Mode
from eim.observability.events import (
    EventKind,
    ObsEvent,
    Ref,
    Status,
    new_event_id,
    new_run_id,
)
from eim.observability.redact import redact, redact_text
from eim.observability.thresholds import QUEUE_MAX as DEFAULT_QUEUE

_BATCH = 500
_SAFE = re.compile(r"[^A-Za-z0-9_-]")


def default_spool_dir() -> Path:
    return Path(os.environ.get("EIM_DATA_DIR", "data")) / "obs" / "spool"


class _Emitter:
    def __init__(self, process: str, mode: Mode, spool: Path, enabled: bool, qsize: int) -> None:
        self.process = _SAFE.sub("_", process)[:40] or "eim"
        self.mode = mode
        self.spool = spool
        self.enabled = enabled
        self.q: queue.Queue[tuple[int, str]] = queue.Queue(maxsize=qsize)
        self.pid = os.getpid()
        self.emitted = self.written = self.dropped = self.errors = 0
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._busy = False
        self._fh = None
        self._fh_path: Path | None = None

    def _count(self, field: str, n: int = 1) -> None:
        with self._lock:
            setattr(self, field, getattr(self, field) + n)

    def start(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, name="eim-obs-writer", daemon=True)
            self._thread.start()

    def put(self, ts: int, line: str) -> bool:
        self.start()
        try:
            self.q.put_nowait((ts, line))
            return True
        except queue.Full:
            self._count("dropped")
            return False

    def _path_for(self, ts_ms: int) -> Path:
        day = time.strftime("%Y%m%d", time.gmtime(ts_ms / 1000))
        return self.spool / f"{self.process}.{day}.{self.pid}.jsonl"

    def _write(self, batch: list[tuple[int, str]]) -> None:
        groups: dict[Path, list[str]] = {}
        for ts, line in batch:
            groups.setdefault(self._path_for(ts), []).append(line)
        for path, lines in groups.items():
            try:
                if self._fh is None or self._fh_path != path:
                    self._close()
                    path.parent.mkdir(parents=True, exist_ok=True)
                    self._fh = path.open("ab")
                    self._fh_path = path
                self._fh.write(("\n".join(lines) + "\n").encode("utf-8"))
                self._fh.flush()
                self._count("written", len(lines))
            except Exception:  # disco lleno, permiso denegado, ruta inválida…
                self._close()
                self._count("dropped", len(lines))
                self._count("errors")

    def _close(self) -> None:
        if self._fh is not None:
            with contextlib.suppress(Exception):
                self._fh.close()
        self._fh = None
        self._fh_path = None

    def _run(self) -> None:
        while True:
            try:
                first = self.q.get(timeout=0.25)
            except queue.Empty:
                continue
            self._busy = True
            batch = [first]
            while len(batch) < _BATCH:
                try:
                    batch.append(self.q.get_nowait())
                except queue.Empty:
                    break
            try:
                self._write(batch)
            finally:
                for _ in batch:
                    self.q.task_done()
                self._busy = False

    def flush(self, timeout: float) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.q.unfinished_tasks == 0:
                return True
            time.sleep(0.005)
        return self.q.unfinished_tasks == 0


_EM: _Emitter | None = None
_EM_LOCK = threading.Lock()


def configure(*, process: str | None = None, mode: Mode | None = None,
              spool_dir: Path | str | None = None, enabled: bool | None = None,
              queue_size: int | None = None) -> None:
    """Fija proceso lógico, modo y destino. Llamarlo una vez al arrancar cada proceso; si no,
    se usan los valores por defecto (`eim`, ANALISIS, `EIM_DATA_DIR/obs/spool`)."""
    global _EM
    with _EM_LOCK:
        old = _EM
        if old is not None:
            old.flush(1.0)
            old._close()
        spool = Path(spool_dir) if spool_dir is not None else (
            old.spool if old else default_spool_dir())
        _EM = _Emitter(
            process or (old.process if old else "eim"),
            mode or (old.mode if old else Mode.ANALISIS),
            spool,
            enabled if enabled is not None else _env_enabled(),
            queue_size or DEFAULT_QUEUE,
        )


def _env_enabled() -> bool:
    return os.environ.get("EIM_OBS", "on").strip().lower() not in ("off", "0", "false", "no")


def _em() -> _Emitter:
    global _EM
    em = _EM
    if em is None or em.pid != os.getpid():  # primer uso, o hijo de un fork: hilo propio
        configure()
        em = _EM
    assert em is not None
    return em


def stats() -> dict[str, Any]:
    em = _em()
    return {"enabled": em.enabled, "emitted": em.emitted, "written": em.written,
            "dropped": em.dropped, "errors": em.errors, "queued": em.q.qsize(),
            "process": em.process, "spool": str(em.spool)}


def flush(timeout: float = 2.0) -> bool:
    """Espera a que el hilo escritor vacíe la cola (tests y apagado). Nunca lanza."""
    try:
        return _em().flush(timeout)
    except Exception:
        return False


def close(timeout: float = 2.0) -> None:
    """Vacía la cola y suelta el archivo (Windows no deja borrar un JSONL abierto)."""
    with contextlib.suppress(Exception):
        em = _em()
        em.flush(timeout)
        em._close()


atexit.register(lambda: flush(1.0))

_CUR: contextvars.ContextVar[tuple[str, str | None] | None] = contextvars.ContextVar(
    "eim_obs_span", default=None)  # (run_id, trace_id) del tramo en curso


def current() -> tuple[str, str | None] | None:
    """(run_id, trace_id) del tramo en curso en este contexto, o None fuera de un `span`."""
    return _CUR.get()


def emit(kind: EventKind, component_id: str, *, status: Status = "ok",
         run_id: str | None = None, parent_run_id: str | None = None,
         trace_id: str | None = None, duration_ms: float | None = None,
         inputs: tuple[Ref, ...] | list[Ref] = (), outputs: tuple[Ref, ...] | list[Ref] = (),
         detail: dict[str, Any] | None = None, mode: Mode | None = None,
         source: str | None = None, coverage: float | None = None,
         ts_utc: int | None = None) -> bool:
    """Registra un evento. Devuelve True si quedó en cola; **nunca lanza ni bloquea**."""
    try:
        em = _em()
        if not em.enabled:
            return False
        ts = int(ts_utc if ts_utc is not None else time.time() * 1000)
        cur = _CUR.get()
        ev = ObsEvent(
            event_id=new_event_id(ts), ts_utc=ts, process=em.process, component_id=component_id,
            kind=kind, status=status, run_id=run_id or (cur[0] if cur else new_run_id()),
            parent_run_id=parent_run_id, trace_id=trace_id or (cur[1] if cur else None),
            duration_ms=duration_ms, inputs=tuple(inputs), outputs=tuple(outputs),
            detail=redact(detail or {}), mode=mode or em.mode,
            source=redact_text(source) if source else None, coverage=coverage,
        )
        em._count("emitted")
        return em.put(ts, ev.model_dump_json())
    except Exception:  # evento inválido u otro fallo: se descarta y se cuenta
        with contextlib.suppress(Exception):
            _em()._count("dropped")
        return False


class Span:
    """Tramo en curso: acumula estado/salidas/detalle que se publican en `run_end`."""

    def __init__(self, run_id: str, trace_id: str | None) -> None:
        self.run_id = run_id
        self.trace_id = trace_id
        self.status: Status = "ok"
        self.outputs: list[Ref] = []
        self.detail: dict[str, Any] = {}

    def set(self, *, status: Status | None = None, detail: dict[str, Any] | None = None,
            output: Ref | None = None) -> None:
        if status is not None:
            self.status = status
        if detail:
            self.detail.update(detail)
        if output is not None:
            self.outputs.append(output)


@contextmanager
def span(component_id: str, *, trace_id: str | None = None,
         inputs: tuple[Ref, ...] | list[Ref] = (), detail: dict[str, Any] | None = None,
         mode: Mode | None = None) -> Iterator[Span]:
    """`run_start` al entrar y `run_end` (con duración y estado) al salir. Una excepción del
    cuerpo se registra como `error` y se PROPAGA intacta; el propio `span` nunca lanza."""
    parent = None
    sp = Span(new_run_id(), trace_id)
    token = None
    t0 = time.perf_counter()
    try:
        cur = _CUR.get()
        parent = cur[0] if cur else None
        sp.trace_id = trace_id or (cur[1] if cur else None)
        token = _CUR.set((sp.run_id, sp.trace_id))
        emit("run_start", component_id, run_id=sp.run_id, parent_run_id=parent,
             trace_id=sp.trace_id, inputs=inputs, detail=detail, mode=mode)
    except Exception:
        pass
    try:
        yield sp
    except BaseException as exc:
        sp.status = "error"
        sp.detail.setdefault("error", f"{type(exc).__name__}: {exc}")
        raise
    finally:
        if token is not None:
            with contextlib.suppress(Exception):
                _CUR.reset(token)
        with contextlib.suppress(Exception):
            emit("run_end", component_id, status=sp.status, run_id=sp.run_id,
                 parent_run_id=parent, trace_id=sp.trace_id,
                 duration_ms=(time.perf_counter() - t0) * 1000, outputs=sp.outputs,
                 detail=sp.detail, mode=mode)
