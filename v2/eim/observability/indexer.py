"""Indexador único del observatorio (T73): JSONL del spool → `obs.duckdb`.

Corre DENTRO del proceso de la API (un solo escritor de la base; los demás procesos solo
añaden líneas a sus archivos). Garantías:
- Reanuda por *offset*: cada archivo guarda hasta dónde se indexó; datos y offset se confirman
  en la MISMA transacción, así que una caída no duplica ni pierde.
- Idempotente por `event_id`: indexar dos veces lo mismo deja una sola copia.
- Tolera líneas corruptas o truncadas: las cuenta y sigue. Una línea sin salto final se espera
  (el escritor puede estar a medias) hasta `TRUNCATED_LINE_GRACE_S`; pasado ese plazo sin crecer
  se da por truncada.
- No borra un JSONL hasta que está indexado y pasada la retención del spool.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from eim.observability import thresholds as T
from eim.observability.derive import fold_decision, fold_run
from eim.observability.events import ObsEvent
from eim.observability.store import (
    DECISION_COLS,
    EVENT_COLS,
    RUN_COLS,
    ObsStore,
)

log = logging.getLogger(__name__)
DAY_MS = 86_400_000
READ_CHUNK = 8 * 2**20          # bytes leídos por vuelta (acota la memoria de una pasada)
REF_COLS = ("event_id", "direction", "ordinal", "type", "id", "hash", "params_version")
FILE_COLS = ("file", "byte_offset", "size", "lines", "corrupt", "updated_ms")

# Un puente devuelve (eventos, marca de agua nueva) a partir de la marca anterior.
Bridge = Callable[[int], tuple[list[ObsEvent], int]]


def _event_row(e: ObsEvent, now: int) -> tuple:
    return (e.event_id, e.ts_utc, e.process, e.component_id, e.kind, e.status, e.run_id,
            e.parent_run_id, e.trace_id, e.duration_ms, e.mode.value, e.source, e.coverage,
            json.dumps(e.detail, ensure_ascii=False, sort_keys=True), now)


def _ref_rows(e: ObsEvent) -> list[tuple]:
    return [(e.event_id, d, i, r.type, r.id, r.hash, r.params_version)
            for d, refs in (("in", e.inputs), ("out", e.outputs)) for i, r in enumerate(refs)]


class Indexer:
    def __init__(self, store: ObsStore, spool_dir: str | Path, *,
                 clock: Callable[[], float] = time.time,
                 bridges: Iterable[tuple[str, Bridge]] = ()) -> None:
        self.store = store
        self.spool = Path(spool_dir)
        self.clock = clock
        self.bridges = list(bridges)
        self.last_pass_ms: int | None = None
        self.last_error: str | None = None
        self.passes = 0
        self._last_purge_ms = 0

    def now_ms(self) -> int:
        return int(self.clock() * 1000)

    # --- núcleo transaccional ------------------------------------------------------------
    def index_events(self, events: Iterable[ObsEvent],
                     file_state: tuple[str, int, int, int, int] | None = None) -> int:
        """Inserta los eventos NUEVOS y pliega `runs`/`decisions`; devuelve cuántos eran nuevos.
        `file_state` = (archivo, offset, tamaño, líneas, corruptas) se confirma en la misma
        transacción."""
        now = self.now_ms()
        batch = {e.event_id: e for e in events}
        st = self.store
        with st.lock:
            st.begin()
            try:
                known = st.existing("events", "event_id", list(batch))
                new = sorted((e for i, e in batch.items() if i not in known),
                             key=lambda e: (e.ts_utc, e.kind != "run_start", e.event_id))
                st.insert("events", EVENT_COLS, [_event_row(e, now) for e in new])
                st.insert("refs", REF_COLS, [r for e in new for r in _ref_rows(e)])
                self._fold(new)
                if file_state is not None:
                    name, off, size, lines, bad = file_state
                    prev = st.rows("spool_files", FILE_COLS, "file", [name]).get(name)
                    st.insert("spool_files", FILE_COLS, [(
                        name, off, size, (prev["lines"] if prev else 0) + lines,
                        (prev["corrupt"] if prev else 0) + bad, now)], replace=True)
                st.commit()
            except BaseException:
                st.rollback()
                raise
        return len(new)

    def _fold(self, new: list[ObsEvent]) -> None:
        st = self.store
        run_ids = list({e.run_id for e in new if e.kind in ("run_start", "run_end")})
        runs = st.rows("runs", RUN_COLS, "run_id", run_ids)
        for e in new:
            if e.kind in ("run_start", "run_end"):
                runs[e.run_id] = fold_run(runs.get(e.run_id), e)
        traces = list({e.trace_id for e in new if e.trace_id})
        decs = st.rows("decisions", DECISION_COLS, "trace_id", traces)
        for e in new:
            if e.trace_id:
                decs[e.trace_id] = fold_decision(decs.get(e.trace_id), e)
        st.insert("runs", RUN_COLS, [tuple(runs[k][c] for c in RUN_COLS) for k in run_ids],
                  replace=True)
        st.insert("decisions", DECISION_COLS, [tuple(decs[k][c] for c in DECISION_COLS)
                                               for k in traces], replace=True)

    # --- lectura del spool ---------------------------------------------------------------
    def _index_file(self, path: Path) -> tuple[int, int]:
        """Indexa lo pendiente de un archivo. Devuelve (eventos nuevos, líneas corruptas)."""
        name = path.name
        with self.store.lock:
            prev = self.store.rows("spool_files", FILE_COLS, "file", [name]).get(name)
        offset = prev["byte_offset"] if prev else 0
        total_new = total_bad = 0
        while True:
            st = path.stat()
            if st.st_size < offset:          # archivo reemplazado o truncado: se relee entero
                offset = 0
            if st.st_size == offset:
                break
            with path.open("rb") as f:
                f.seek(offset)
                data = f.read(READ_CHUNK)
            end = data.rfind(b"\n") + 1
            at_eof = offset + len(data) >= st.st_size
            tail = data[end:]
            stale = self.clock() - st.st_mtime > T.TRUNCATED_LINE_GRACE_S
            if tail and at_eof and stale:    # resto sin salto final que ya no crece
                end = len(data)
            if end == 0 and len(data) == READ_CHUNK:   # «línea» gigante sin salto: corrupta
                end = len(data)
                events, bad, lines = [], 1, 1
                offset += end
                self.index_events(events, (name, offset, st.st_size, lines, bad))
                total_bad += bad
                continue
            if end == 0:
                break
            events, bad, lines = [], 0, 0
            for raw in data[:end].split(b"\n"):
                raw = raw.strip()
                if not raw:
                    continue
                lines += 1
                try:
                    events.append(ObsEvent.model_validate_json(raw))
                except Exception:           # JSON roto, truncado o fuera de contrato
                    bad += 1
            offset += end
            total_new += self.index_events(events, (name, offset, st.st_size, lines, bad))
            total_bad += bad
        return total_new, total_bad

    def run_once(self) -> dict[str, Any]:
        """Una pasada: spool + puentes. Nunca lanza; deja el último error en `status()`."""
        out = {"new": 0, "corrupt": 0, "files": 0, "bridge": 0}
        try:
            self.store.sync_catalog(self.now_ms())
            for path in sorted(self.spool.glob("*.jsonl")) if self.spool.exists() else []:
                try:
                    n, bad = self._index_file(path)
                except OSError as e:         # archivo en uso o borrado entre medias
                    log.warning("observatorio: %s: %s", path.name, e)
                    continue
                out["new"] += n
                out["corrupt"] += bad
                out["files"] += 1
            for name, bridge in self.bridges:
                out["bridge"] += self._run_bridge(name, bridge)
            self.last_error = None
        except Exception as e:  # noqa: BLE001 - el observatorio no puede tumbar a la API
            self.last_error = f"{type(e).__name__}: {e}"
            log.exception("observatorio: pasada fallida")
        self.last_pass_ms = self.now_ms()
        self.passes += 1
        if self.last_pass_ms - self._last_purge_ms > 3_600_000:
            try:
                self.purge()
            except Exception as e:  # noqa: BLE001
                self.last_error = f"purga: {type(e).__name__}: {e}"
            self._last_purge_ms = self.last_pass_ms
        return out

    def _run_bridge(self, name: str, bridge: Bridge) -> int:
        mark = self.store.scalar("SELECT watermark FROM bridge_state WHERE source = ?", [name])
        events, new_mark = bridge(int(mark or 0))
        n = self.index_events(events)
        with self.store.lock:
            self.store.insert("bridge_state", ("source", "watermark"), [(name, new_mark)],
                              replace=True)
        return n

    async def loop(self) -> None:
        while True:
            await asyncio.to_thread(self.run_once)
            await asyncio.sleep(T.INDEX_INTERVAL_S)

    # --- retención -----------------------------------------------------------------------
    def purge(self) -> dict[str, int]:
        """Eventos crudos > 30 d y JSONL ya indexados > 7 d; `runs`/`decisions` > 180 d."""
        now = self.now_ms()
        ev_cut = now - T.EVENT_RETENTION_DAYS * DAY_MS
        run_cut = now - T.RUN_RETENTION_DAYS * DAY_MS
        st, out = self.store, {}
        with st.lock:
            st.begin()
            try:
                old = "SELECT event_id FROM events WHERE ts_utc < ?"
                out["refs"] = self._delete(f"refs WHERE event_id IN ({old})", ev_cut)
                out["events"] = self._delete("events WHERE ts_utc < ?", ev_cut)
                out["runs"] = self._delete(
                    "runs WHERE coalesce(ended_ms, started_ms, 0) < ?", run_cut)
                out["decisions"] = self._delete("decisions WHERE last_ms < ?", run_cut)
                st.commit()
            except BaseException:
                st.rollback()
                raise
        out["files"] = self._purge_spool(now)
        return out

    def _delete(self, target: str, cutoff: int) -> int:
        return len(self.store.con.execute(f"DELETE FROM {target} RETURNING 1",
                                          [cutoff]).fetchall())

    def _purge_spool(self, now_ms: int) -> int:
        if not self.spool.exists():
            return 0
        cut = now_ms / 1000 - T.SPOOL_RETENTION_DAYS * 86400
        removed = 0
        for path in self.spool.glob("*.jsonl"):
            try:
                size, mtime = path.stat().st_size, path.stat().st_mtime
            except OSError:
                continue
            if mtime >= cut:
                continue
            with self.store.lock:
                prev = self.store.rows("spool_files", FILE_COLS, "file", [path.name]).get(
                    path.name)
            if prev is None or prev["byte_offset"] < size:
                continue                    # sin indexar del todo: no se borra
            try:
                path.unlink()
            except OSError:                 # Windows: archivo aún abierto por su escritor
                continue
            with self.store.lock:
                self.store.con.execute("DELETE FROM spool_files WHERE file = ?", [path.name])
            removed += 1
        return removed

    # --- estado --------------------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        now = self.now_ms()
        files = {r["file"]: r for r in self.store.query("SELECT * FROM spool_files")}
        pending = unindexed_old = 0
        total = 0
        cut = now / 1000 - T.SPOOL_RETENTION_DAYS * 86400
        for p in self.spool.glob("*.jsonl") if self.spool.exists() else []:
            try:
                s = p.stat()
            except OSError:
                continue
            total += s.st_size
            behind = s.st_size - (files[p.name]["byte_offset"] if p.name in files else 0)
            pending += max(behind, 0)
            if behind > 0 and s.st_mtime < cut:
                unindexed_old += 1
        last_ev = self.store.scalar("SELECT max(ts_utc) FROM events")
        lag = None if self.last_pass_ms is None else round((now - self.last_pass_ms) / 1000, 1)
        spool_mb = round(total / 2**20, 2)
        problems = []
        if self.last_error:
            problems.append(self.last_error)
        if lag is not None and lag > T.INDEX_LAG_S_MAX:
            problems.append(f"el indexador lleva {lag:.0f} s sin pasar (máx {T.INDEX_LAG_S_MAX})")
        if spool_mb > T.SPOOL_ALERT_MB:
            problems.append(f"spool de {spool_mb} MB (alerta a {T.SPOOL_ALERT_MB})")
        if unindexed_old:
            problems.append(f"{unindexed_old} archivos con más de {T.SPOOL_RETENTION_DAYS} días "
                            "sin indexar del todo")
        return {
            "ok": not problems, "problems": problems, "passes": self.passes,
            "last_pass_ms": self.last_pass_ms, "index_lag_s": lag,
            "last_event_ms": last_ev, "last_event_age_s": (
                None if last_ev is None else round((now - last_ev) / 1000, 1)),
            "pending_bytes": pending, "spool_mb": spool_mb,
            "corrupt_lines": int(self.store.scalar(
                "SELECT coalesce(sum(corrupt), 0) FROM spool_files") or 0),
            "counts": self.store.counts(),
        }
