"""Generación walk-forward de contextos desde el almacén (sin red y sin anticipación).

Para cada `asof` (cierre de una vela): snapshot con velas ≤ `asof` → agentes → síntesis →
sugerencias → escenarios → contexto compacto. Es el camino caro (≈1–1,5 s por vela, casi todo
el agente `plan`); el resultado se guarda y las estrategias se reevalúan gratis después.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Iterable
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait

from eim.agents.registry import AgentRegistry, default_registry
from eim.agents.runner import run_agents
from eim.data.paper_store import PaperStore
from eim.data.snapshot import build_snapshot
from eim.data.store import Store
from eim.data.timeframes import tf_ms
from eim.forecast.scenarios import build_forecast
from eim.paper.context import make_ctx, synthesis_drift

SKIP_AGENTS = frozenset({"context"})   # LLM: sin titulares en la reconstrucción
AGENT_BARS = 500                       # = Settings.snapshot_bars
FORECAST_BARS = 1000
HORIZON = 24
N_PATHS = 300


def default_workers() -> int:
    """Procesos para el backtest: todos los núcleos menos dos (la API sigue respondiendo)."""
    return max(1, (os.cpu_count() or 2) - 2)


def now_ms() -> int:
    return int(time.time() * 1000)


def closed_asofs(last_candle_t: int, bar_ms: int, n: int, step: int = 1) -> list[int]:
    """Los `n` cierres de vela más recientes (cada `step` velas) hasta la última cerrada."""
    last = last_candle_t + bar_ms
    return sorted(last - k * step * bar_ms for k in range(n))


class CtxGenerator:
    def __init__(self, store: Store, registry: AgentRegistry | None = None,
                 timeframe: str = "1h", agent_timeout_s: float = 30.0) -> None:
        self.store, self.tf = store, timeframe
        self.bar = tf_ms(timeframe)
        reg = registry or default_registry()
        self.agents = [a for a in reg.latest() if a.id not in SKIP_AGENTS]
        self.expected = [a.id for a in self.agents]
        self.timeout = agent_timeout_s
        self.lock = threading.Lock()    # un cálculo a la vez (vivo y backtest comparten CPU)

    def ctx_at(self, symbol: str, asof: int) -> dict | None:
        snap = build_snapshot(self.store, symbol, self.tf, AGENT_BARS, asof=asof)
        if len(snap.candles) < AGENT_BARS // 2 or snap.candles[-1].t + self.bar != asof:
            return None                 # sin la vela que cierra en `asof` no hay decisión
        reports = run_agents(self.agents, snap, self.timeout)
        fsnap = build_snapshot(self.store, symbol, self.tf, FORECAST_BARS, asof=asof)
        try:
            fs = build_forecast(fsnap, HORIZON, N_PATHS,
                                drift=synthesis_drift(reports, self.expected, fsnap))
        except (ValueError, LookupError):
            fs = None
        return make_ctx(snap, reports, self.expected, fs, self.bar)

    def run(self, pstore: PaperStore, symbol: str, asofs: Iterable[int],
            origin_of: Callable[[int], str], stop: threading.Event | None = None,
            progress: Callable[[int, int], None] | None = None, workers: int = 1) -> int:
        """Calcula y guarda los `asofs` que falten. Devuelve cuántos guardó.

        `workers > 1` reparte las velas entre procesos (los agentes son CPU puro y el GIL
        serializa los hilos); cada proceso abre el almacén por su cuenta, solo lectura."""
        have = pstore.asofs(symbol, self.tf)
        todo = [a for a in sorted(set(asofs)) if a not in have]
        if workers > 1 and len(todo) > workers:
            return self._run_pool(pstore, symbol, todo, origin_of, stop, progress, workers)
        saved = 0
        for k, asof in enumerate(todo):
            if stop is not None and stop.is_set():
                break
            with self.lock:
                ctx = self.ctx_at(symbol, asof)
            if ctx is not None:
                pstore.save(symbol, self.tf, ctx, origin_of(asof), now_ms())
                saved += 1
            if progress:
                progress(k + 1, len(todo))
        return saved

    def _run_pool(self, pstore: PaperStore, symbol: str, todo: list[int],
                  origin_of: Callable[[int], str], stop: threading.Event | None,
                  progress: Callable[[int, int], None] | None, workers: int) -> int:
        saved = done = 0
        with ProcessPoolExecutor(workers, initializer=_init_worker,
                                 initargs=(str(self.store.root), self.tf)) as pool:
            pending = {pool.submit(_worker_ctx, symbol, a) for a in todo}
            try:
                while pending:
                    if stop is not None and stop.is_set():
                        break
                    ready, pending = wait(pending, timeout=1.0, return_when=FIRST_COMPLETED)
                    for fut in ready:
                        ctx = fut.result()
                        done += 1
                        if ctx is not None:
                            pstore.save(symbol, self.tf, ctx, origin_of(int(ctx["t"])), now_ms())
                            saved += 1
                        if progress:
                            progress(done, len(todo))
            finally:
                for fut in pending:
                    fut.cancel()
        return saved


_WORKER: CtxGenerator | None = None


def _init_worker(data_dir: str, timeframe: str) -> None:
    global _WORKER
    _WORKER = CtxGenerator(Store(data_dir), timeframe=timeframe)


def _worker_ctx(symbol: str, asof: int) -> dict | None:
    assert _WORKER is not None
    return _WORKER.ctx_at(symbol, asof)
