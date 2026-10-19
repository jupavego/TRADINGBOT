"""Servicio de validación (T49): une el bróker simulado con la puerta pura y persiste.

En cada cálculo: registra la versión vigente de cada estrategia@marco (huella del código y de la
mecánica; alta con su declaración de `lineage.json` o automática), toma las operaciones sombra
CERRADAS de esa versión (`Idea.version`), simula el lado contrario de las que quedan fuera de
muestra (réplica de V3), ajusta por Holm con todos los intentos registrados y guarda los
veredictos. El bróker lo llama tras cada ciclo y recalcula al cierre de cada vela de 4 h.
Siempre SIMULADO: no publica ni opera nada.
"""

from __future__ import annotations

import threading
from collections import Counter
from pathlib import Path

import numpy as np

from eim.core import Mode
from eim.data.validation_store import ValidationStore
from eim.paper.catalog import CATALOG
from eim.paper.desk import PaperDesk
from eim.paper.engine import Outcome, simulate
from eim.paper.engine import Path as PricePath
from eim.paper.generate import now_ms
from eim.validation.criteria import Criteria, load_criteria
from eim.validation.evidence import flip_idea, trade_of
from eim.validation.gate import NAMES, VALIDADA, measure, validate_all
from eim.validation.lineage import (
    LINEAGE_FILE,
    Version,
    load_declarations,
    out_of_sample,
    tuning_windows,
)

FOUR_H = 4 * 3_600_000


def _ref_price(o: Outcome, path: PricePath) -> float:
    """Precio de la decisión: la entrada a mercado o la apertura de 15 m en `t`."""
    i = o.idea
    if i.kind == "market":
        return i.entry
    j = int(np.searchsorted(path.t, i.t))
    return float(path.o[min(j, len(path.o) - 1)])


def summarize(verdicts: list[dict]) -> dict:
    counts = Counter(v["verdict"] for v in verdicts)
    fails = Counter(c["id"] for v in verdicts for c in v["checks"] if c["ok"] is False)
    return {"counts": dict(counts), "validated": [v["id"] for v in verdicts
                                                  if v["verdict"] == VALIDADA],
            "most_failed": [{"id": k, "name": NAMES[k], "n": n} for k, n in fails.most_common()]}


class Validator:
    def __init__(self, desk: PaperDesk, vstore: ValidationStore, crit: Criteria | None = None,
                 lineage: Path = LINEAGE_FILE) -> None:
        self.desk, self.vstore = desk, vstore
        self.crit = crit or load_criteria()
        self.lineage = lineage
        self.last_run: int | None = None
        self.error = ""
        self._cov: dict[str, dict | None] = {}     # cobertura del último cálculo por símbolo
        self._lock = threading.Lock()

    # --- versiones --------------------------------------------------------------------
    def current_versions(self, now: int) -> dict[str, Version]:
        """Registra (si hace falta) y devuelve la versión vigente de cada estrategia@marco."""
        decls = load_declarations(self.lineage)
        out = {}
        for tf in self.desk.tfs:
            for info in CATALOG.values():
                sid = f"{info.id}@{tf}"
                out[sid] = self.vstore.ensure(sid, info.id, tf, info.version(tf, self.desk.ep),
                                              now, decls)
        return out

    # --- cálculo ----------------------------------------------------------------------
    def compute(self, symbol: str, now: int | None = None) -> dict:
        with self._lock:
            return self._compute(symbol, now or now_ms())

    def _compute(self, symbol: str, now: int) -> dict:
        view = self.desk.view(symbol)
        current = self.current_versions(now)
        allv = self.vstore.versions()
        path = view.path
        asof = path.end if path is not None and path.end else now
        prior = {f"{s}|{sid}@v{n}": p
                 for (s, sid, n), p in self.vstore.last_pvalues(self.crit.version).items()}
        for v in allv:
            prior.setdefault(f"{symbol}|{v.label}", None)
        attempts = len(prior)
        closed: dict[str, list[Outcome]] = {}
        for o in view.outcomes:
            v = current.get(o.idea.sid)
            if v is not None and o.idea.version == v.fingerprint and o.status == "CERRADA":
                closed.setdefault(v.sid, []).append(o)
        prices = (path.t, path.c) if path is not None else None
        items = []
        for sid, v in sorted(current.items()):
            wins = tuning_windows(v, [x for x in allv if x.sid == sid])
            trades = []
            for o in closed.get(sid, []):
                oos = (o.exit_t or 0) <= asof and out_of_sample(o.idea.t, symbol, wins)
                flip = (simulate(flip_idea(o.idea, _ref_price(o, path)), path, self.desk.ep)
                        if oos and path is not None else None)
                t = trade_of(o, flip)
                if t is not None:
                    trades.append(t)
            m = measure(f"{symbol}|{v.label}", trades, wins, symbol, asof, self.crit, attempts,
                        prices)
            items.append((v, m, wins))
        verdicts = [x.to_json() for x in validate_all(items, prior, self.crit)]
        self.vstore.save_verdicts(self.crit.version, symbol, asof, now, verdicts)
        self._cov[symbol] = view.summary.get("coverage")
        return self.payload(symbol, asof, now, verdicts, self._cov[symbol])

    def payload(self, symbol: str, asof: int | None, computed: int | None, verdicts: list[dict],
                coverage: dict | None = None) -> dict:
        allv = self.vstore.versions()
        return {
            "mode": Mode.SIMULADO.value, "symbol": symbol, "asof": asof, "computed": computed,
            "criteria": self.crit.to_json(), "attempts": len(allv), "summary": summarize(verdicts),
            "verdicts": verdicts, "versions": [v.to_json() for v in allv],
            "coverage": coverage, "error": self.error,
            "provenance": self.vstore.provenance(),
        }

    def latest(self, symbol: str) -> dict:
        """Veredictos vigentes guardados (sin recalcular el bróker); si aún no hay ninguno,
        los calcula una vez."""
        asof, computed, rows = self.vstore.latest(self.crit.version, symbol)
        if not rows:
            return self.compute(symbol)
        return self.payload(symbol, asof, computed, rows, self._cov.get(symbol))

    # --- periódico --------------------------------------------------------------------
    def due(self, now: int) -> bool:
        return self.last_run is None or self.last_run < now - now % FOUR_H

    def maybe_run(self) -> None:
        """Gancho del servicio del bróker: recalcula al pasar cada cierre de vela de 4 h."""
        now = now_ms()
        if not self.due(now):
            return
        try:
            for sym in self.desk.symbols:
                self.compute(sym, now)
            self.error = ""
        except Exception as exc:  # nunca tumba el ciclo del bróker
            self.error = f"{type(exc).__name__}: {exc}"
        self.last_run = now
