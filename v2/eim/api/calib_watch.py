"""Vigía de calibración en el proceso de la API (T184): control y retroalimentación automáticos.

Corre como gancho del bróker simulado (`paper.hooks`, hilo propio en prioridad baja): cada 6 h
evalúa los pronósticos persistidos de cada símbolo del foco y cada marco, juzga con las reglas
de `eim/forecast/calib_watch.py`, mide en sombra las recalibraciones de T160 y guarda cada
revisión en `data/calibration/watch.jsonl` (solo añadir: el historial es la memoria de la mejora
continua). Late en el mapa como `forecast.calibration`; con alerta sostenida, en ámbar.

No toca el pronóstico, la síntesis ni el bróker: lo que cambia es que ya nadie tiene que abrir la
pestaña para enterarse de que las bandas o las probabilidades se desviaron.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from eim.api.calibration import outcomes
from eim.api.forecast import Forecaster
from eim.core import Mode
from eim.data.store import Store
from eim.data.timeframes import FOCUS, TF_MS, tf_ms
from eim.forecast.calib_watch import (
    SUSTAINED,
    WatchParams,
    assess,
    shadow,
    shadow_streak,
    to_obs,
)
from eim.forecast.calibration import summarize
from eim.observability import hooks_service

COMPONENT = "forecast.calibration"
log = logging.getLogger(__name__)
_KEEP = ("n_evaluated", "n_effective", "n_pending", "brier", "brier_rw", "brier_skill",
         "pinball_skill", "ece", "top_hit", "mean_prob", "realized_freq")


def _now() -> int:
    return int(time.time() * 1000)


class CalibWatch:
    def __init__(self, store: Store, forecaster: Forecaster, data_dir: Path,
                 symbols: Sequence[str] = FOCUS, tfs: Sequence[str] = tuple(TF_MS),
                 params: WatchParams | None = None, clock: Callable[[], int] = _now) -> None:
        self.store, self.forecaster = store, forecaster
        self.symbols, self.tfs = tuple(symbols), tuple(tfs)
        self.p = params or WatchParams()
        self.clock = clock
        self.path = Path(data_dir) / "calibration" / "watch.jsonl"
        self.history: list[dict] = self._load()
        self.last_run: int | None = None
        self.error = ""
        self._lock = threading.Lock()

    # --- persistencia ---------------------------------------------------------------
    def _load(self, keep: int = 500) -> list[dict]:
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
        del self.history[:-500]

    def _prev(self, symbol: str, tf: str) -> list[dict]:
        return [h for h in self.history if h.get("symbol") == symbol and h.get("timeframe") == tf]

    # --- revisión -------------------------------------------------------------------
    def due(self, now: int) -> bool:
        return self.last_run is None or now - self.last_run >= self.p.interval_ms

    def review(self, symbol: str, tf: str, now: int) -> dict:
        h = self.p.horizon
        outs, pending, _ = outcomes(self.store, self.forecaster, symbol, tf, h)
        rep = summarize(outs, h, pending)
        prev = self._prev(symbol, tf)
        verdict = assess(rep, self.p, prev[-1]["state"] if prev else None)
        sh = shadow(to_obs(outs, h, tf_ms(tf)), h, self.p)
        sh["streak"] = shadow_streak(prev, sh)
        cov = {k: c.get("terminal") for k, c in (rep.get("coverage") or {}).items()}
        return {"at": now, "symbol": symbol, "timeframe": tf, "horizon": h,
                "state": verdict["state"], "level": verdict["level"],
                "reasons": verdict["reasons"], "coverage": cov,
                **{k: rep.get(k) for k in _KEEP}, "verdict": rep.get("verdict", []),
                "shadow": sh, "source": "pronósticos persistidos vs velas del almacén"}

    def run(self, now: int) -> list[dict]:
        done = []
        with self._lock:
            for sym in self.symbols:
                for tf in self.tfs:
                    entry = self.review(sym, tf, now)
                    self._append(entry)
                    done.append(entry)
        return done

    def maybe_run(self) -> bool:
        """Gancho del bróker: True si revisó y nada está en alerta sostenida (el gancho late
        «ok»); con alerta sostenida late él mismo en ámbar y devuelve False."""
        now = self.clock()
        if not self.due(now):
            return False
        self.last_run = now
        try:
            done = self.run(now)
            self.error = ""
        except Exception as exc:  # noqa: BLE001 - un fallo del vigía nunca tumba al bróker
            self.error = f"{type(exc).__name__}: {exc}"
            log.warning("vigía de calibración: %s", self.error)
            return False
        bad = [f"{e['symbol']} {e['timeframe']}" for e in done if e["state"] == SUSTAINED]
        if bad:
            hooks_service.beat(COMPONENT, status="degraded", mode=Mode.SIMULADO,
                               detail={"hook": "calibracion", "alerta_sostenida": bad})
            return False
        return True

    # --- API ------------------------------------------------------------------------
    def latest(self) -> list[dict]:
        last: dict[tuple[str, str], dict] = {}
        for h in self.history:
            last[(h.get("symbol"), h.get("timeframe"))] = h
        return sorted(last.values(), key=lambda e: (e["symbol"], TF_MS.get(e["timeframe"], 0)))

    def payload(self, symbol: str | None, tf: str | None, limit: int) -> dict:
        sel = [h for h in self.history if (symbol is None or h.get("symbol") == symbol)
               and (tf is None or h.get("timeframe") == tf)]
        latest = [e for e in self.latest() if (symbol is None or e["symbol"] == symbol)
                  and (tf is None or e["timeframe"] == tf)]
        nxt = None if self.last_run is None else self.last_run + self.p.interval_ms
        return {"enabled": True, "latest": latest, "history": sel[-limit:],
                "last_run": self.last_run, "next_run": nxt, "error": self.error,
                "params": self.p.model_dump(), "symbols": list(self.symbols),
                "timeframes": list(self.tfs)}
