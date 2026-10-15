"""Mesa del bróker simulado: une contextos guardados, estrategias, motor, retroalimentación y
perfiles; mantiene el servicio en vivo y el backtest en segundo plano. Siempre SIMULADO."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field

from eim.agents.registry import AgentRegistry
from eim.core import Mode
from eim.data.paper_store import PaperStore
from eim.data.providers.base import Provider
from eim.data.store import Store
from eim.data.sync import sync_candles
from eim.data.timeframes import FOCUS, tf_ms
from eim.paper.balance import balance
from eim.paper.book import ProfileState, run_profile
from eim.paper.catalog import CATALOG, generate_ideas
from eim.paper.engine import Outcome, Path, run_shadow
from eim.paper.feedback import Learner, family_stats, strategy_stats
from eim.paper.generate import CtxGenerator, closed_asofs, default_workers, now_ms
from eim.paper.insights import insights
from eim.paper.params import FAMILIES, PROFILES, ExecParams, ProfileParams
from eim.paper.summary import profile_summary

MMR = {"BTCUSDT": 0.004, "ETHUSDT": 0.005}     # tramo bajo de Binance (supuesto, = simulador)
WARMUP_BARS = 400                               # velas previas para los indicadores
LIVE_BARS = 48                                  # el servicio rellena como mucho 2 días
FUNDING_MS = 8 * 3_600_000


@dataclass
class View:
    symbol: str
    stamp: tuple
    outcomes: list[Outcome] = field(default_factory=list)
    books: dict[str, ProfileState] = field(default_factory=dict)
    summary: dict = field(default_factory=dict)


@dataclass
class Job:
    state: str = "inactivo"     # inactivo | corriendo | terminado | cancelado | error
    symbol: str = ""
    done: int = 0
    total: int = 0
    saved: int = 0
    error: str = ""
    started: int | None = None
    finished: int | None = None
    stop: threading.Event = field(default_factory=threading.Event)

    def to_json(self) -> dict:
        return {k: getattr(self, k) for k in ("state", "symbol", "done", "total", "saved",
                                                "error", "started", "finished")}


class PaperDesk:
    def __init__(self, store: Store, pstore: PaperStore, registry: AgentRegistry | None = None,
                 exec_params: ExecParams | None = None,
                 profiles: tuple[ProfileParams, ...] = PROFILES, provider: Provider | None = None,
                 symbols: tuple[str, ...] = FOCUS, poll_s: float = 60.0) -> None:
        self.store, self.pstore = store, pstore
        self.ep = exec_params or ExecParams()
        self.tf, self.bar = self.ep.timeframe, tf_ms(self.ep.timeframe)
        self.profiles, self.provider = profiles, provider
        self.symbols, self.poll_s = symbols, poll_s
        self.gen = CtxGenerator(store, registry, self.tf)
        self.job = Job()
        self.live_error = ""
        self.last_tick: int | None = None
        self._cache: dict[str, View] = {}
        self._lock = threading.Lock()

    # --- cálculo ----------------------------------------------------------------------
    def view(self, symbol: str) -> View:
        b = self.store.bounds(symbol, self.ep.path_tf)
        f = self.store.read_series("funding", symbol, last=1)
        stamp = (self.pstore.stamp(symbol, self.tf), b, f[-1][0] if f else None)
        with self._lock:
            v = self._cache.get(symbol)
            if v is None or v.stamp != stamp:
                v = self._compute(symbol, stamp)
                self._cache[symbol] = v
            return v

    def _compute(self, symbol: str, stamp: tuple) -> View:
        ctxs = self.pstore.load(symbol, self.tf)
        v = View(symbol, stamp)
        infos = [s.to_json() for s in CATALOG.values()]
        if not ctxs:
            v.summary = self._payload(v, [], infos, Learner([]), None, None)
            return v
        t0 = ctxs[0]["t"]
        candles = self.store.read_candles(symbol, self.tf, start=t0 - WARMUP_BARS * self.bar)
        pc = self.store.read_candles(symbol, self.ep.path_tf, start=t0 - self.bar)
        funding = self.store.read_series("funding", symbol, start=t0 - FUNDING_MS)
        ideas = generate_ideas(ctxs, candles, symbol, self.bar)
        path = Path(pc, funding, tf_ms(self.ep.path_tf))
        v.outcomes = run_shadow(ideas, path, self.ep)
        learner = Learner(v.outcomes)
        mmr = MMR.get(symbol, 0.005)
        v.books = {p.id: run_profile(p, v.outcomes, learner, mmr) for p in self.profiles}
        last = pc[-1] if pc else None
        v.summary = self._payload(v, ctxs, infos, learner, path.end or None,
                                  last.c if last else None, n_ideas=len(ideas))
        return v

    def _payload(self, v: View, ctxs: list[dict], infos: list[dict], learner: Learner,
                 now: int | None, mark: float | None, n_ideas: int = 0) -> dict:
        mmr = MMR.get(v.symbol, 0.005)
        now = now or now_ms()
        ids = [i["id"] for i in infos]
        profiles = [profile_summary(v.books[p.id], learner, ids, now, mmr)
                    for p in self.profiles if p.id in v.books]
        rows = strategy_stats(v.outcomes, infos)
        fams = family_stats(rows)
        counts = self.pstore.counts(v.symbol, self.tf)
        fund = self.store.read_series("funding", v.symbol, last=1)
        return {
            "mode": Mode.SIMULADO.value, "symbol": v.symbol, "timeframe": self.tf,
            "path_tf": self.ep.path_tf, "now": now, "mark": mark,
            "coverage": {"from": ctxs[0]["t"] if ctxs else None,
                         "to": ctxs[-1]["t"] if ctxs else None, "contexts": len(ctxs),
                         "origins": counts, "ideas": n_ideas, "simulated": len(v.outcomes)},
            "sources": {"candles": self.store.source("candles", v.symbol, self.ep.path_tf),
                        "funding": self.store.source("funding", v.symbol) or "sin datos",
                        "funding_last": fund[-1][0] if fund else None,
                        "costs": "tarifa regular Binance (supuesto: taker 0,05 %, maker 0,02 %)"},
            "families": FAMILIES, "profiles": profiles, "strategies": rows,
            "family_stats": fams,
            "insights": insights(rows, fams, profiles, counts),
            "balance": balance({pid: b.trades for pid, b in v.books.items()},
                               {i["id"]: i["name"] for i in infos}, now),
            "job": self.job.to_json(), "live": {"last_tick": self.last_tick,
                                                "error": self.live_error},
        }

    # --- backtest ---------------------------------------------------------------------
    def start_backtest(self, symbol: str, days: float, step: int = 1) -> dict:
        if self.job.state == "corriendo":
            return self.job.to_json()
        b = self.store.bounds(symbol, self.tf)
        if b is None:
            raise LookupError(f"sin velas de {symbol} {self.tf}")
        n = max(1, int(days * 24 * 3_600_000 / self.bar / step))
        asofs = closed_asofs(b[1], self.bar, n, step)
        self.job = Job(state="corriendo", symbol=symbol, started=now_ms())
        job = self.job

        def work() -> None:
            def prog(k: int, total: int) -> None:
                job.done, job.total = k, total
            try:
                job.saved = self.gen.run(self.pstore, symbol, asofs, self._origin, job.stop, prog,
                                         workers=default_workers())
                job.state = "cancelado" if job.stop.is_set() else "terminado"
            except Exception as exc:  # el hilo nunca tumba la API
                job.state, job.error = "error", f"{type(exc).__name__}: {exc}"
            job.finished = now_ms()

        threading.Thread(target=work, name="eim-paper-backtest", daemon=True).start()
        return job.to_json()

    def stop_backtest(self) -> dict:
        self.job.stop.set()
        return self.job.to_json()

    def _origin(self, asof: int) -> str:
        """`vivo` solo si se decide a lo sumo una vela después de su cierre."""
        return "vivo" if now_ms() - asof <= 2 * self.bar else "backtest"

    # --- servicio en vivo -------------------------------------------------------------
    def tick(self) -> int:
        """Trae velas y funding nuevos (si hay proveedor) y genera los contextos que falten."""
        saved = 0
        for sym in self.symbols:
            if self.provider is not None:
                self._sync(sym)
            b = self.store.bounds(sym, self.tf)
            if b is None or not self.pstore.asofs(sym, self.tf) and sym != self.symbols[0]:
                continue                     # otros símbolos: solo si ya tienen historial
            saved += self.gen.run(self.pstore, sym, closed_asofs(b[1], self.bar, LIVE_BARS),
                                  self._origin)
        self.last_tick, self.live_error = now_ms(), ""
        return saved

    def _sync(self, sym: str) -> None:
        now = now_ms()
        for tf in (self.tf, self.ep.path_tf):
            b = self.store.bounds(sym, tf)
            start = b[1] if b else now - (WARMUP_BARS + LIVE_BARS) * self.bar
            sync_candles(self.store, self.provider, sym, tf, start, now)
        f = self.store.read_series("funding", sym, last=1)
        rates = self.provider.funding_rates(sym, f[-1][0] + 1 if f else now - 30 * 86_400_000,
                                            now)
        if rates:
            self.store.upsert_series("funding", sym, "-", rates, self.provider.name)

    async def loop(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self.tick)
            except Exception as exc:  # red caída: se reintenta en el siguiente ciclo
                self.live_error = f"{type(exc).__name__}: {exc}"
            await asyncio.sleep(self.poll_s)
