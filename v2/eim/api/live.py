"""Hub de difusión: un canal por (símbolo, marco) que ejecuta los agentes al cierre de vela.

Fronteras (T123, `eim.observability.queues`): el difusor (`_pump`) nunca espera al análisis.
Guarda la vela cerrada y la deja en un buzón de 1 por canal (`api.cierres`, gana la más reciente);
un analizador por canal lo vacía. Cada pantalla tiene su cola de 256 (`api.clientes`, descarta lo
más viejo). El pronóstico tiene plazo (`pronostico.hilos`). Todo descarte se cuenta.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass, field

from eim.agents.registry import AgentRegistry
from eim.agents.runner import call_with_deadline, run_agents
from eim.api.reports_db import ReportStore
from eim.api.sources import LiveSource
from eim.core import AgentReport, Candle
from eim.data.snapshot import build_snapshot
from eim.data.store import Store
from eim.data.timeframes import tf_ms
from eim.observability import hooks, hooks_service, queues
from eim.observability.emit import span
from eim.observability.events import trace_for
from eim.synthesis import synthesize


def synthesis_of(reports: list[AgentReport], expected: list[str] | None = None) -> dict | None:
    syn = synthesize(reports, expected=expected)
    return syn.model_dump() if syn else None


def overlays_of(reports: list[AgentReport]) -> list[dict]:
    return [o.model_dump() for r in reports for o in r.overlays]


@dataclass
class Channel:
    symbol: str
    timeframe: str
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    task: asyncio.Task | None = None
    last_tick: dict | None = None
    status: dict = field(default_factory=lambda: {"type": "status", "state": "connecting"})
    pending: Candle | None = None              # buzón del análisis: tope 1, gana la más reciente
    wake: asyncio.Event = field(default_factory=asyncio.Event)
    analyzer: asyncio.Task | None = None


class Hub:
    def __init__(
        self,
        source: LiveSource,
        store: Store,
        reports: ReportStore,
        registry: AgentRegistry,
        snapshot_bars: int = 500,
        agent_timeout_s: float = 30.0,
        forecaster=None,
        history=None,
        bots=None,
        forecast_timeout_s: float = 60.0,
    ) -> None:
        self._source, self._store, self._reports = source, store, reports
        self._registry, self._bars, self._timeout = registry, snapshot_bars, agent_timeout_s
        self._forecaster = forecaster
        self._history = history
        self._bots = bots  # servicio de bots (T57): produce `snapshot.bot_signals`
        self._channels: dict[tuple[str, str], Channel] = {}
        self._forecast_timeout = forecast_timeout_s
        self._closes, self._clients = queues.gauge("api.cierres"), queues.gauge("api.clientes")

    def subscribe(self, symbol: str, timeframe: str) -> tuple[Channel, asyncio.Queue]:
        ch = self._channels.setdefault((symbol, timeframe), Channel(symbol, timeframe))
        q: asyncio.Queue = asyncio.Queue(maxsize=queues.capacity("api.clientes"))
        ch.subscribers.add(q)
        if ch.task is None or ch.task.done():
            ch.task = asyncio.create_task(self._pump(ch))
        return ch, q

    def unsubscribe(self, ch: Channel, q: asyncio.Queue) -> None:
        ch.subscribers.discard(q)

    async def close(self) -> None:
        for ch in self._channels.values():
            for t in (ch.task, ch.analyzer):
                if t:
                    t.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await t

    def broadcast_all(self, msg: dict) -> None:
        """Mensaje independiente del par/marco (p. ej. escáner de arbitraje, T39)."""
        for ch in list(self._channels.values()):
            self._broadcast(ch, msg)

    def _broadcast(self, ch: Channel, msg: dict) -> None:
        for q in list(ch.subscribers):
            if q.full():  # cliente lento: se descarta lo más viejo, nunca se bloquea el hub
                with contextlib.suppress(asyncio.QueueEmpty):
                    q.get_nowait()
                    self._clients.drop(1, f"{ch.symbol} {ch.timeframe}: pantalla lenta, se "
                                          "descarta lo más viejo")
            q.put_nowait(msg)
            self._clients.seen(q.qsize())

    async def _bootstrap(self, ch: Channel) -> None:
        """Análisis inicial sobre la última vela cerrada del almacén, para ver los agentes en
        cualquier marco sin esperar al próximo cierre. No hace nada si ya hay reportes al día."""
        if self._history is not None:  # marco sin historia: se descarga antes de analizar
            await asyncio.to_thread(self._history.ensure, ch.symbol, ch.timeframe)
        step = tf_ms(ch.timeframe)
        now = int(time.time() * 1000)
        last = await asyncio.to_thread(
            self._store.read_candles, ch.symbol, ch.timeframe, None, now - step + 1, 1)
        if not last:
            return
        stored = await asyncio.to_thread(self._reports.latest, ch.symbol, ch.timeframe)
        done = {r.asof for r in stored}
        if last[0].t + step in done:
            return
        await self._on_close(ch, last[0], persist_candle=False)

    async def _pump(self, ch: Channel) -> None:
        with contextlib.suppress(Exception):   # una sola vez, antes de abrir el flujo
            await self._bootstrap(ch)
        if ch.analyzer is None or ch.analyzer.done():
            ch.analyzer = asyncio.create_task(self._analyzer(ch))
        async for ev in self._source.stream(ch.symbol, ch.timeframe):
            if ev["type"] == "status":
                ch.status = {
                    "type": "status", "state": ev["state"], "detail": ev.get("detail", ""),
                    "source": self._source.name,
                }
                self._broadcast(ch, ch.status)
                continue
            candle: Candle = ev["candle"]
            ch.last_tick = {
                "type": "tick", "symbol": ch.symbol, "timeframe": ch.timeframe,
                "candle": candle.model_dump(), "closed": ev["closed"],
                "source": self._source.name,
            }
            self._broadcast(ch, ch.last_tick)
            if ev["closed"]:
                await self._enqueue_close(ch, candle)

    async def _enqueue_close(self, ch: Channel, candle: Candle) -> None:
        """Guarda la vela y la deja en el buzón del análisis; el difusor no espera al análisis."""
        try:
            await asyncio.to_thread(self._store.upsert_candles, ch.symbol, ch.timeframe,
                                    [candle], self._source.name)
        except Exception as exc:
            self._broadcast(ch, {"type": "error", "detail": f"{type(exc).__name__}: {exc}"})
            return
        if ch.pending is not None:
            self._closes.drop(1, f"{ch.symbol} {ch.timeframe}: vela {ch.pending.t} sin analizar, "
                                 f"se analiza la {candle.t}")
        ch.pending = candle
        self._closes.seen(1)
        ch.wake.set()

    async def _analyzer(self, ch: Channel) -> None:
        """Vacía el buzón del canal: analiza la última vela cerrada que haya."""
        while True:
            await ch.wake.wait()
            ch.wake.clear()
            candle, ch.pending = ch.pending, None
            self._closes.seen(0)
            if candle is None:
                continue
            try:
                await self._on_close(ch, candle, persist_candle=False)
            except Exception as exc:  # noqa: BLE001 - el analizador del canal no se muere
                self._broadcast(ch, {"type": "error", "detail": f"{type(exc).__name__}: {exc}"})

    async def _on_close(self, ch: Channel, candle: Candle, persist_candle: bool = True) -> None:
        try:
            reports = await asyncio.to_thread(self._analyze, ch, candle, persist_candle)
        except Exception as exc:
            self._broadcast(ch, {"type": "error", "detail": f"{type(exc).__name__}: {exc}"})
            return
        self._broadcast(ch, {
            "type": "reports", "symbol": ch.symbol, "timeframe": ch.timeframe,
            "asof": candle.t + tf_ms(ch.timeframe),
            "reports": [r.model_dump() for r in reports], "overlays": overlays_of(reports),
            "synthesis": synthesis_of(reports, [a.id for a in self._registry.latest()]),
        })
        await self._emit_forecast(ch, candle.t + tf_ms(ch.timeframe))
        hooks_service.beat("api.hub", detail={"symbol": ch.symbol, "tf": ch.timeframe})

    async def _emit_forecast(self, ch: Channel, asof: int | None = None) -> None:
        """Pronóstico al cierre de vela; si faltan datos o falla, no interrumpe el flujo."""
        if self._forecaster is None:
            return
        trace = trace_for(ch.symbol, ch.timeframe, asof) if asof else None
        try:
            with span("api.hub", trace_id=trace, detail={"phase": "forecast"}):
                st, fs = await asyncio.to_thread(
                    call_with_deadline, ("forecast", ch.symbol, ch.timeframe),
                    lambda: self._forecaster.run(ch.symbol, ch.timeframe), self._forecast_timeout)
            if st != "ok":   # timeout o aún colgado del cierre anterior: se salta
                raise TimeoutError(f"pronóstico sin respuesta ({st}, plazo "
                                   f"{self._forecast_timeout:g} s)")
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            hooks_service.service_error("forecast.engine", exc)
            self._broadcast(ch, {"type": "forecast_error", "detail": detail})
            return
        self._broadcast(ch, {"type": "forecast", "forecast": fs.model_dump()})

    def _analyze(
        self, ch: Channel, candle: Candle, persist_candle: bool = True
    ) -> list[AgentReport]:
        if persist_candle:
            self._store.upsert_candles(ch.symbol, ch.timeframe, [candle], self._source.name)
        asof = candle.t + tf_ms(ch.timeframe)
        with span("api.hub", trace_id=trace_for(ch.symbol, ch.timeframe, asof),
                  detail={"phase": "analyze", "symbol": ch.symbol, "tf": ch.timeframe,
                          "asof": asof}):
            snap = build_snapshot(self._store, ch.symbol, ch.timeframe, self._bars, asof=asof)
            hooks.snapshot_fetches(snap, self._bars)
            if self._bots is not None:
                snap = self._bots.attach(snap)
            reports = run_agents(self._registry.latest(), snap, timeout=self._timeout)
            self._reports.save(ch.symbol, ch.timeframe, reports)
        return reports
