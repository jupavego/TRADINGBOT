"""Servicio de puntuación del escuadrón (T59): lee lo guardado, puntúa, persiste y se recalcula.

I/O de `scorecard.score`: posturas (`bot_signals`), velas y funding del almacén, régimen de los
contextos del bróker y fichas del catálogo. Se recalcula al cierre de cada vela de 4 h (gancho del
bróker, como la puerta de T49). El aporte marginal es caro (reconstruye el panel de agentes): lo
mide el CLI (`scorecard_cli --marginal`) y el recálculo periódico reutiliza la última medición
mientras la versión del bot no cambie. Siempre SIMULADO: no publica ni opera nada.
"""

from __future__ import annotations

import logging
import threading
from bisect import bisect_right
from collections.abc import Callable

from eim.bots.card import BotCard, default_cards
from eim.bots.marginal import Marginal
from eim.bots.scorecard import score
from eim.data.bots.scorestore import ScoreStore
from eim.data.bots.simstore import SimRunStore
from eim.data.bots.store import BotSignalStore
from eim.data.paper_store import PaperStore
from eim.data.store import Store
from eim.data.timeframes import tf_ms
from eim.paper.engine import Path
from eim.paper.generate import now_ms
from eim.validation.criteria import Criteria, load_criteria

log = logging.getLogger("eim.bots")
FOUR_H = 4 * 3_600_000
FUNDING_MS = 8 * 3_600_000
TF = "1h"                       # marco del núcleo: panel de agentes y régimen
TFS = ("1h", "5m")              # marcos en que hay bots (5m: NFI)
PATH_TF = {"1h": "15m", "5m": "5m"}   # velas con que se resuelve cada operación sombra


def regime_lookup(pstore: PaperStore, symbol: str, tf: str = TF) -> Callable[[int], str | None]:
    """Régimen vigente al cierre `asof` (el contexto más reciente ≤ asof): sin futuro."""
    ctxs = [(int(c["t"]), c.get("regime")) for c in pstore.load(symbol, tf)]
    ts = [t for t, _ in ctxs]

    def at(asof: int) -> str | None:
        i = bisect_right(ts, asof) - 1
        return ctxs[i][1] if i >= 0 else None
    return at


class BotScorer:
    def __init__(self, signals: BotSignalStore, scores: ScoreStore, store: Store,
                 pstore: PaperStore, sims: SimRunStore | None = None,
                 cards: dict[str, BotCard] | None = None, crit: Criteria | None = None,
                 symbols: tuple[str, ...] = ("BTCUSDT",)) -> None:
        self.signals, self.scores, self.store, self.pstore = signals, scores, store, pstore
        self.sims, self.crit = sims, crit or load_criteria()
        self.cards = cards if cards is not None else default_cards()
        self.symbols = symbols
        self.last_run: int | None = None
        self.error = ""
        self.on_scored: list[Callable[[dict], None]] = []   # T60: política del escuadrón
        self._lock = threading.Lock()

    def compute(self, symbol: str, now: int | None = None,
                marginals: dict[str, Marginal] | None = None) -> dict:
        with self._lock:
            return self._compute(symbol, now or now_ms(), marginals)

    def _compute(self, symbol: str, now: int, marginals: dict[str, Marginal] | None) -> dict:
        rows = self.rows(symbol, now)
        if not rows:
            return {"mode": "SIMULADO", "symbol": symbol, "bots": [], "attempts": [],
                    "summary": {"states": {}, "votan": [], "informan": [], "publicables": [],
                                "modulan_confianza": []},
                    "error": "sin posturas guardadas de bots"}
        t0 = min(s.asof for s, _ in rows)
        tfs = sorted({s.timeframe for s, _ in rows})
        candles = {tf: self.store.read_candles(symbol, tf, start=t0 - 600 * tf_ms(tf), end=now)
                   for tf in tfs}
        funding = self.store.read_series("funding", symbol, start=t0 - FUNDING_MS)
        path = {tf: Path(self.store.read_candles(symbol, PATH_TF[tf], start=t0 - tf_ms("4h")),
                         funding, tf_ms(PATH_TF[tf])) for tf in tfs}
        ends = [p.end for p in path.values() if p.end]
        asof = min(now, *ends) if ends else now
        marginals = marginals if marginals is not None else self._previous_marginals(symbol)
        sims = self.sims.query(symbol=symbol) if self.sims is not None else []
        out = score(rows, candles, path, symbol, self.crit, self.cards, asof,
                    regime_lookup(self.pstore, symbol), marginals, sim_runs=sims)
        self.scores.save(out, now)
        for fn in self.on_scored:
            fn(out)
        return {**out, "computed": now}

    def rows(self, symbol: str, end: int | None = None) -> list:
        """Posturas guardadas de todos los marcos con bots, por `asof`."""
        out = [r for tf in TFS for r in self.signals.query_all(symbol, tf, end)]
        return sorted(out, key=lambda r: r[0].asof)

    def _previous_marginals(self, symbol: str) -> dict[str, Marginal]:
        """Última medición marginal, válida solo para la misma versión del bot."""
        prev = self.scores.latest(symbol, self.crit.version)
        out: dict[str, Marginal] = {}
        for b in (prev or {}).get("bots", []):
            m = b.get("marginal")
            if m:
                out[b["id"]] = Marginal(m["contributes"], m["weight"], m["reason"], m["rho_max"],
                                        m["deltas"], m["moderator"], m["modulates"])
        return out

    def latest(self, symbol: str) -> dict:
        got = self.scores.latest(symbol, self.crit.version)
        return got if got is not None else self.compute(symbol)

    def due(self, now: int) -> bool:
        return self.last_run is None or self.last_run < now - now % FOUR_H

    def maybe_run(self) -> None:
        """Gancho del bróker: recalcula al pasar cada cierre de vela de 4 h; nunca lo tumba."""
        now = now_ms()
        if not self.due(now):
            return
        try:
            for sym in self.symbols:
                self.compute(sym, now)
            self.error = ""
        except Exception as exc:  # noqa: BLE001
            self.error = f"{type(exc).__name__}: {exc}"
            log.warning("puntuación de bots: %s", self.error)
        self.last_run = now
