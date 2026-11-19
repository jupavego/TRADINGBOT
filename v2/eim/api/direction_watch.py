"""Vigía de dirección en el proceso de la API (T190–T193): `GET /v2/direction/watch`.

Corre como gancho del bróker simulado (`paper.hooks`, hilo propio en prioridad baja): cada 6 h
califica la dirección de cada informante guardado en `reports.duckdb` frente a las velas del
almacén (T190), juzga el marco con las reglas pre-registradas (T191), recorre las dos sombras de
la entrada (T192 abstención, T193 pesos por acierto) y guarda cada revisión en
`data/direction/watch.jsonl` (solo añadir). Late en el mapa como `validation.direction`; con la
síntesis peor que una moneda dos revisiones seguidas, en ámbar.

No toca la síntesis, el bróker ni la corrida de T31: lo que mide abre, como mucho, una ◆.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from fastapi import APIRouter, Query

from eim.core import Mode
from eim.data.timeframes import FOCUS, TF_MS, tf_ms
from eim.direction.board import SynthFn, build, default_synth
from eim.direction.params import DirectionParams
from eim.direction.score import judge, scoreboard, summary
from eim.direction.shadow import SHADOWS, compare, gate, walk
from eim.direction.watch import SUSTAINED, assess, compact, streak
from eim.observability import hooks_service

COMPONENT = "validation.direction"
PREREG_DOC = "PLAN/notas/T190_preregistro.md"
log = logging.getLogger(__name__)


def _now() -> int:
    return int(time.time() * 1000)


class DirectionWatch:
    def __init__(self, reports, store, data_dir: Path, symbols: Sequence[str] = FOCUS,
                 tfs: Sequence[str] = tuple(TF_MS), params: DirectionParams | None = None,
                 clock: Callable[[], int] = _now, synth: SynthFn | None = None) -> None:
        self.reports, self.store = reports, store
        self.symbols, self.tfs = tuple(symbols), tuple(tfs)
        self.p = params or DirectionParams()
        self.clock = clock
        self.synth = synth
        self.path = Path(data_dir) / "direction" / "watch.jsonl"
        self.history: list[dict] = self._load()
        self.last_run: int | None = None
        self.error = ""
        self._lock = threading.Lock()

    # --- persistencia ---------------------------------------------------------------
    def _load(self, keep: int = 300) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines()[-keep:]:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out

    def _append(self, entry: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self.history.append(entry)
        del self.history[:-300]

    def _prev_state(self, symbol: str, tf: str) -> str | None:
        prev = [h for h in self.history if h.get("symbol") == symbol and h.get("timeframe") == tf]
        return prev[-1]["state"] if prev else None

    # --- revisión -------------------------------------------------------------------
    def evaluate(self, symbol: str, tf: str) -> tuple[dict, dict, int, int]:
        """(boleta, sombras, instantes, votos) de un marco con lo guardado hasta ahora."""
        step = tf_ms(tf)
        hist = self.reports.history(symbol, tf, self.p.max_instants)
        arr = self.store.read_arrays(symbol, tf)
        synth = self.synth or default_synth()
        votes, instants = build(hist, arr["t"], arr["c"], step, self.p, synth)
        board = scoreboard(votes, step, self.p)
        dec = walk(instants, step, self.p)
        return board, {n: compare(dec, n, step, self.p) for n in SHADOWS}, len(instants), len(votes)

    def run(self, now: int) -> list[dict]:
        done: list[dict] = []
        with self._lock:
            got = {(s, tf): self.evaluate(s, tf) for s in self.symbols for tf in self.tfs}
            judge({f"{s}|{tf}": g[0] for (s, tf), g in got.items()}, self.p)
            shadows = {f"{s}|{tf}|{n}": r for (s, tf), g in got.items() for n, r in g[1].items()}
            gate(shadows, self.p)
            for (s, tf), (board, sh, n_inst, n_votes) in got.items():
                for n, r in sh.items():
                    r["streak"] = streak(self.history, s, tf, n, r["passes"])
                    r["sustained"] = r["streak"] >= self.p.gate_streak
                verdict = assess(board, self.p, self._prev_state(s, tf))
                entry = {"at": now, "symbol": s, "timeframe": tf, "prereg": self.p.prereg,
                         "horizon": self.p.primary, "instants": n_inst, "votes": n_votes,
                         **verdict, "summary": summary(board, self.p),
                         "board": compact(board, self.p), "shadows": sh,
                         "source": "reportes guardados en vivo vs velas del almacén"}
                self._append(entry)
                done.append(entry)
        return done

    def due(self, now: int) -> bool:
        return self.last_run is None or now - self.last_run >= self.p.interval_ms

    def maybe_run(self) -> bool:
        """Gancho del bróker: True si revisó sin alerta sostenida (late «ok» por el gancho); con
        alerta sostenida late él mismo en ámbar y devuelve False. Un fallo nunca tumba al bróker."""
        now = self.clock()
        if not self.due(now):
            return False
        self.last_run = now
        try:
            done = self.run(now)
            self.error = ""
        except Exception as exc:  # noqa: BLE001
            self.error = f"{type(exc).__name__}: {exc}"
            log.warning("vigía de dirección: %s", self.error)
            return False
        bad = [f"{e['symbol']} {e['timeframe']}" for e in done if e["state"] == SUSTAINED]
        if bad:
            hooks_service.beat(COMPONENT, status="degraded", mode=Mode.SIMULADO,
                               detail={"hook": "direccion", "alerta_sostenida": bad})
            return False
        return True

    # --- API ------------------------------------------------------------------------
    def latest(self) -> list[dict]:
        last: dict[tuple[str, str], dict] = {}
        for h in self.history:
            last[(h.get("symbol"), h.get("timeframe"))] = h
        return sorted(last.values(), key=lambda e: (e["symbol"], TF_MS.get(e["timeframe"], 0)))

    def payload(self, symbol: str | None, tf: str | None, limit: int, full: bool) -> dict:
        def ok(e: dict) -> bool:
            return (symbol is None or e.get("symbol") == symbol) and (
                tf is None or e.get("timeframe") == tf)
        light = ("board",) if not full else ()
        hist = [{k: v for k, v in h.items() if k not in ("board", "shadows")}
                for h in self.history if ok(h)][-limit:]
        nxt = None if self.last_run is None else self.last_run + self.p.interval_ms
        return {"enabled": True, "prereg": self.p.prereg, "prereg_doc": PREREG_DOC,
                "latest": [{k: v for k, v in e.items() if k not in light}
                           for e in self.latest() if ok(e)],
                "history": hist, "last_run": self.last_run, "next_run": nxt,
                "error": self.error, "params": self.p.model_dump(mode="json"),
                "symbols": list(self.symbols), "timeframes": list(self.tfs)}


def build_direction_router(watch: DirectionWatch | None) -> APIRouter:
    router = APIRouter(prefix="/v2")

    @router.get("/direction/watch")
    def direction_watch(symbol: str | None = None, tf: str | None = None,
                        limit: int = Query(40, ge=1, le=300), full: bool = False) -> dict:
        """T190–T193: última boleta de dirección por marco, sombras, historial y reglas."""
        if watch is None:
            return {"enabled": False, "latest": [], "history": [], "prereg_doc": PREREG_DOC,
                    "note": "vigía apagado: solo corre con el bróker simulado en vivo"}
        return watch.payload(symbol, tf, limit, full)

    return router
