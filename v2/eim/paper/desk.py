"""Mesa del bróker simulado: une contextos guardados (15 m, 1 h y 4 h), estrategias, motor,
retroalimentación y perfiles; el servicio en vivo y el backtest están en `service.py` y el diario
de la protección (T110) en `protection_desk.py`. Siempre SIMULADO."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from eim.agents.registry import AgentRegistry
from eim.core import Mode
from eim.data.paper_store import PaperStore
from eim.data.providers.base import Provider
from eim.data.store import Store
from eim.data.timeframes import FOCUS, tf_ms
from eim.paper import ledger
from eim.paper.balance import balance
from eim.paper.book import ProfileState, run_profile
from eim.paper.catalog import CATALOG, generate_ideas
from eim.paper.engine import CAUSES, Outcome, Path, run_shadow
from eim.paper.feedback import Learner, family_stats, strategy_stats, timeframe_stats
from eim.paper.generate import CtxGenerator, now_ms
from eim.paper.insights import insights
from eim.paper.ladder_book import LadderSim
from eim.paper.params import (
    FAMILIES,
    PROFILES,
    ExecParams,
    ProfileParams,
    check_profiles,
)
from eim.paper.protection_desk import DeskProtection
from eim.paper.service import WARMUP_BARS, DeskService, Job
from eim.paper.summary import profile_summary
from eim.paper.trend import HtfTrend

MMR = {"BTCUSDT": 0.004, "ETHUSDT": 0.005}     # tramo bajo de Binance (supuesto, = simulador)
FUNDING_MS = 8 * 3_600_000
BUSY_REFRESH_MS = 10 * 60_000   # con un backtest en curso la vista se rehace como mucho cada 10 min
LEDGER_EVERY_MS = 3_600_000     # el libro fijo se pone al día cada hora aunque nadie mire


@dataclass
class View:
    symbol: str
    stamp: tuple
    computed: int = 0               # cuándo se calculó (la API avisa si está desfasada)
    outcomes: list[Outcome] = field(default_factory=list)
    books: dict[str, ProfileState] = field(default_factory=dict)
    summary: dict = field(default_factory=dict)
    live_ctx: list[tuple[str, int]] = field(default_factory=list)   # velas decididas en vivo
    path: Path | None = None        # camino de 15 m usado en la sombra (T49: réplica contraria)
    protection: dict = field(default_factory=dict)   # pasada del diario de la protección (T110)


def strategy_infos(tfs: tuple[str, ...]) -> list[dict]:
    """Ficha de cada estrategia en cada marco (`id` = estrategia@marco)."""
    return [{**s.to_json(), "id": f"{s.id}@{tf}", "base": s.id, "timeframe": tf,
             "name": f"{s.name} · {tf}"} for tf in tfs for s in CATALOG.values()
            if s.runs_in(tf)]


class PaperDesk(DeskService, DeskProtection):
    def __init__(self, store: Store, pstore: PaperStore, registry: AgentRegistry | None = None,
                 exec_params: ExecParams | None = None,
                 profiles: tuple[ProfileParams, ...] = PROFILES, provider: Provider | None = None,
                 symbols: tuple[str, ...] = FOCUS, poll_s: float = 60.0) -> None:
        self.store, self.pstore = store, pstore
        self.ep = exec_params or ExecParams()
        self.tfs = self.ep.timeframes
        self.profiles, self.provider = profiles, provider
        self.symbols, self.poll_s = symbols, poll_s
        check_profiles(self.profiles, self.symbols)   # T108: configuración inválida = no arranca
        self.gens = {tf: CtxGenerator(store, registry, tf) for tf in self.tfs}
        self.job = Job()
        self.live_error = ""
        self.last_tick: int | None = None
        self.loop_started: int | None = None    # el servicio arrancó (aunque falte el 1er ciclo)
        self.after_tick: list = []              # ganchos tras cada ciclo (T49: validación)
        self._cache: dict[str, View] = {}
        self._lock = threading.Lock()
        self._busy: dict[str, threading.Event] = {}    # recálculos en segundo plano en curso
        self._busy_lock = threading.Lock()
        self.view_error = ""
        self.ledger_error = ""
        self._ledger_at = 0
        ledger.ensure(pstore)
        self._protection_init()

    def live_status(self) -> dict:
        return {"last_tick": self.last_tick, "started": self.loop_started, "error": self.live_error}

    # --- cálculo ----------------------------------------------------------------------
    def _stamp(self, symbol: str) -> tuple:
        b = self.store.bounds(symbol, self.ep.path_tf)
        f = self.store.read_series("funding", symbol, last=1)
        return (tuple(self.pstore.stamp(symbol, tf) for tf in self.tfs), b,
                f[-1][0] if f else None)

    def view(self, symbol: str) -> View:
        """Vista al día; si hay datos nuevos la recalcula y espera (la usa la validación)."""
        stamp = self._stamp(symbol)
        with self._lock:
            v = self._cache.get(symbol)
            if v is None or v.stamp != stamp:
                v = self._compute(symbol, stamp)
                self._cache[symbol] = v
            return v

    def cached_view(self, symbol: str, wait_s: float = 0.0) -> View | None:
        """Vista para la API sin quedarse colgada: con datos nuevos lanza el recálculo en segundo
        plano y espera hasta `wait_s`; si no termina, entrega la última calculada (desfasada) o
        None si aún no hay ninguna. Con un backtest en curso cada contexto nuevo cambia los datos:
        la vista se rehace como mucho cada `BUSY_REFRESH_MS`."""
        v = self._cache.get(symbol)
        if v is not None and (v.stamp == self._stamp(symbol) or self._throttled(v)):
            return v
        done = self._refresh(symbol)
        done.wait(wait_s)
        return self._cache.get(symbol)

    def view_state(self, v: View) -> dict:
        """Frescura de la vista entregada: cuándo se calculó, si ya hay datos más nuevos y si se
        está rehaciendo."""
        return {"computed": v.computed, "stale": v.stamp != self._stamp(v.symbol),
                "refreshing": v.symbol in self._busy, "error": self.view_error}

    def _throttled(self, v: View) -> bool:
        return self.job.state == "corriendo" and now_ms() - v.computed < BUSY_REFRESH_MS

    def _refresh(self, symbol: str) -> threading.Event:
        """Un solo recálculo en segundo plano por símbolo; devuelve su señal de fin."""
        with self._busy_lock:
            ev = self._busy.get(symbol)
            if ev is not None:
                return ev
            ev = self._busy[symbol] = threading.Event()

        def work() -> None:
            try:
                self.view(symbol)
                self.view_error = ""
            except Exception as exc:  # el hilo nunca tumba la API: la vista lo muestra
                self.view_error = f"{type(exc).__name__}: {exc}"
            finally:
                with self._busy_lock:
                    self._busy.pop(symbol, None)
                ev.set()

        threading.Thread(target=work, name=f"eim-paper-view-{symbol}", daemon=True).start()
        return ev

    def _compute(self, symbol: str, stamp: tuple) -> View:
        by_tf = {tf: self.pstore.load(symbol, tf) for tf in self.tfs}
        v = View(symbol, stamp, computed=now_ms())
        v.live_ctx = [(tf, int(c["t"])) for tf, cs in by_tf.items() for c in cs
                      if c.get("origin") == "vivo"]
        infos = strategy_infos(self.tfs)
        firsts = [c[0]["t"] for c in by_tf.values() if c]
        if not firsts:
            v.summary = self._payload(v, by_tf, infos, Learner([]), None, None)
            return v
        ideas = []
        for tf, ctxs in by_tf.items():
            if not ctxs:
                continue
            bar = tf_ms(tf)
            candles = self.store.read_candles(symbol, tf, start=ctxs[0]["t"] - WARMUP_BARS * bar)
            ideas += generate_ideas(ctxs, candles, symbol, bar, timeframe=tf,
                                    htf=self._htf(symbol, tf, ctxs[0]["t"]),
                                    exec_params=self.ep)
        t0 = min(firsts)
        pc = self.store.read_candles(symbol, self.ep.path_tf, start=t0 - tf_ms("4h"))
        funding = self.store.read_series("funding", symbol, start=t0 - FUNDING_MS)
        path = v.path = Path(pc, funding, tf_ms(self.ep.path_tf))
        v.outcomes = run_shadow(ideas, path, self.ep)
        learner = Learner(v.outcomes)
        mmr = MMR.get(symbol, 0.005)
        sim = LadderSim(path, self.ep, self._fine(symbol, t0), guards=self._guards(symbol))
        v.books = {p.id: run_profile(p, v.outcomes, learner, mmr, sim) for p in self.profiles}
        self._record_ledger(v)
        self._sync_protection(v)
        v.summary = self._payload(v, by_tf, infos, learner, path.end or None,
                                  pc[-1].c if pc else None, n_ideas=len(ideas))
        return v

    def _record_ledger(self, v: View) -> None:
        """Escribe en el libro fijo lo que se cerró en vivo (solo añade; nunca falla la vista)."""
        try:
            n = ledger.record(self.pstore, ledger.rows_from_view(
                v.symbol, v.outcomes, v.books, self.ep, now_ms()))
            self.ledger_error = ""
            if n:
                self.ledger_added = getattr(self, "ledger_added", 0) + n
        except Exception as exc:  # noqa: BLE001 - el registro nunca tumba el cálculo de la vista
            self.ledger_error = f"{type(exc).__name__}: {exc}"

    def ledger_tick(self) -> None:
        """Gancho tras cada ciclo: pone al día el libro fijo una vez por hora (calcula la vista
        solo si hay contextos nuevos; si alguien la consultó antes, ya está calculada)."""
        if now_ms() - self._ledger_at < LEDGER_EVERY_MS:
            return
        self._ledger_at = now_ms()
        for sym in self.symbols:
            self.view(sym)

    def _fine(self, symbol: str, t0: int) -> Path | None:
        """Velas finas (1 min) para resolver el orden dentro de las velas de 15 m ambiguas del
        perfil de escalera; None si ningún perfil las usa o el almacén no las tiene."""
        tfs = {p.ladder.fine_tf for p in self.profiles if p.ladder and symbol in (p.symbols or (
            symbol,))}
        if not tfs:
            return None
        tf = sorted(tfs)[0]
        if self.store.bounds(symbol, tf) is None:
            return None
        # millones de filas en 1 min (historia desde 2023): arreglos, no un objeto por vela
        return Path.from_arrays(self.store.read_arrays(symbol, tf, start=t0 - tf_ms("4h")),
                                tf_ms(tf))

    def _htf(self, symbol: str, tf: str, t0: int):
        """Tendencia del marco mayor para las ideas de `tf` (None si no está configurada)."""
        spec = self.ep.htf.get(tf)
        if not spec:
            return None
        htf, fast, slow = spec
        bar = tf_ms(htf)
        cs = self.store.read_candles(symbol, htf, start=t0 - 4 * slow * bar)
        return HtfTrend(cs, bar, fast, slow).at

    def _coverage(self, symbol: str, by_tf: dict[str, list[dict]], n_ideas: int,
                  n_sim: int) -> dict:
        tfs = {}
        for tf, ctxs in by_tf.items():
            tfs[tf] = {"contexts": len(ctxs), "from": ctxs[0]["t"] if ctxs else None,
                       "to": ctxs[-1]["t"] if ctxs else None,
                       "origins": self.pstore.counts(symbol, tf)}
        froms = [x["from"] for x in tfs.values() if x["from"]]
        tos = [x["to"] for x in tfs.values() if x["to"]]
        origins: dict[str, int] = {}
        for x in tfs.values():
            for k, n in x["origins"].items():
                origins[k] = origins.get(k, 0) + n
        return {"from": min(froms) if froms else None, "to": max(tos) if tos else None,
                "contexts": sum(x["contexts"] for x in tfs.values()), "origins": origins,
                "ideas": n_ideas, "simulated": n_sim, "timeframes": tfs}

    def _payload(self, v: View, by_tf: dict[str, list[dict]], infos: list[dict],
                 learner: Learner, now: int | None, mark: float | None, n_ideas: int = 0) -> dict:
        mmr = MMR.get(v.symbol, 0.005)
        now = now or now_ms()
        ids = [i["id"] for i in infos]
        profiles = [profile_summary(v.books[p.id], learner, ids, now, mmr)
                    for p in self.profiles if p.id in v.books]
        self.annotate_protection(v, profiles)
        rows = strategy_stats(v.outcomes, infos)
        fams = family_stats(rows)
        cov = self._coverage(v.symbol, by_tf, n_ideas, len(v.outcomes))
        fund = self.store.read_series("funding", v.symbol, last=1)
        return {
            "mode": Mode.SIMULADO.value, "symbol": v.symbol, "timeframes": list(self.tfs),
            "path_tf": self.ep.path_tf, "now": now, "mark": mark, "coverage": cov,
            "sources": {"candles": self.store.source("candles", v.symbol, self.ep.path_tf),
                        "funding": self.store.source("funding", v.symbol) or "sin datos",
                        "funding_last": fund[-1][0] if fund else None,
                        "costs": "tarifa regular Binance (supuesto: taker 0,05 %, maker 0,02 %)"},
            "families": FAMILIES, "causes": CAUSES, "profiles": profiles, "strategies": rows,
            "family_stats": fams, "tf_stats": timeframe_stats(v.outcomes),
            "insights": insights(rows, fams, profiles, cov["origins"]),
            "balance": balance({pid: b.trades for pid, b in v.books.items()},
                               {i["id"]: i["name"] for i in infos}, now, self.tfs),
            "job": self.job.to_json(), "live": self.live_status(), "protection": v.protection,
        }
