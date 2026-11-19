"""Vigía de asimetría (T187–T189) en el proceso de la API: control, validación y mejora continua.

Corre como gancho del bróker simulado (`paper.hooks`, hilo propio en prioridad baja) una vez por
hora. Lee el libro fijo y la vista de la mesa principal, compara cada operación viva con lo que
habría dejado con cada regla del pre-registro `t187_asimetria_v1` y guarda la revisión en
`data/paper/asym/reviews.jsonl`. **Solo decide en las tres fechas fijas** (con los datos
anteriores a cada una, una sola vez por fecha, en `looks.json`); el primer veredicto queda en
`verdicts.json` y no se revisa. Lo de costo y riesgo que PASA entra solo en `adopted.json`, que la
mesa principal aplica desde su instante (`EIM_ASYM_ADOPT=0` lo impide). Late en el mapa como
`paper.asymmetry`.

No cambia nada de la corrida de T31: mide en sombra, y lo que adopta solo vale para decisiones
posteriores al cierre de T31.
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, Query

from eim.paper import ledger, universe
from eim.paper.asym import adoption
from eim.paper.asym import prereg as P
from eim.paper.asym.loss_side import Pair, capped_loss, capped_weight, measured, one_bet
from eim.paper.asym.maker_live import (
    MakerPair,
    halves_same_sign,
    live_market_ideas,
    pair_ideas,
    summary,
)
from eim.paper.asym.runner import runner_pairs
from eim.paper.asym.verdict import RUNNING, due_look, judge_book, judge_maker
from eim.paper.params import PROFILES, ProfileParams

COMPONENT = "paper.asymmetry"
EVERY_MS = 3_600_000
log = logging.getLogger(__name__)


def _now() -> int:
    return int(time.time() * 1000)


def _book_pairs(ps: list[Pair], before_day: int | None = None) -> list[tuple[int, float]]:
    return [(p.day, p.delta) for p in ps if before_day is None or p.day < before_day]


def clean(x):
    """JSON estricto: sin infinitos ni NaN (un IC sin muestra sale con ±inf)."""
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [clean(v) for v in x]
    return x


def _usd(ps: list[Pair]) -> dict:
    return {"real": round(sum(p.usd_actual for p in ps), 2),
            "con_regla": round(sum(p.usd_cf for p in ps), 2),
            "cambiadas": sum(1 for p in ps if p.changed)}


class AsymWatch:
    def __init__(self, desk, data_dir: Path, *, adopt: bool = True,
                 profiles: tuple[ProfileParams, ...] = PROFILES,
                 clock: Callable[[], int] = _now) -> None:
        self.desk, self.adopt_on, self.clock = desk, adopt, clock
        self.by_id = {p.id: p for p in profiles}
        self.dir = Path(data_dir) / "paper" / "asym"
        self.adopted_path = self.dir / "adopted.json"
        self.maker: dict[str, MakerPair] = {}     # ideas ya resueltas en los dos brazos
        self.last: dict = {}
        self.last_run: int | None = None
        self.error = ""
        self._lock = threading.Lock()

    # --- medición ---------------------------------------------------------------------
    def _rows(self) -> tuple[list[dict], list[dict]]:
        rows = ledger.query(self.desk.pstore, None, "perfil", None, 1_000_000)
        counted = [dict(r) for r in universe.result_rows(rows)]
        return counted, measured(counted)

    def _maker_pairs(self) -> None:
        for sym in self.desk.symbols:
            v = self.desk.cached_view(sym)
            if v is None or v.path is None:
                continue
            ideas = live_market_ideas(v.outcomes, set(self.maker))
            for mp in pair_ideas(ideas, v.path, self.desk.ep):
                self.maker[mp.idea_id] = mp

    def measure(self) -> dict:
        counted, meas = self._rows()

        def est(pid: str) -> float:
            return self.by_id[pid].est_cost_frac if pid in self.by_id else 0.0016

        def fb(pid: str):
            return (self.by_id.get(pid) or PROFILES[0]).feedback
        paths = {}
        for sym in self.desk.symbols:
            v = self.desk.cached_view(sym)
            if v is not None and v.path is not None:
                paths[sym] = v.path
        run, pending = runner_pairs(meas, paths)
        self._maker_pairs()
        return {"n_rows": len(meas), "t187a": capped_loss(meas, est), "t187b": one_bet(meas),
                "t187c": capped_weight(meas, counted, fb), "t188": run,
                "t188_pending": pending, "maker": list(self.maker.values())}

    @staticmethod
    def judge(m: dict, look: int | None, before_day: int | None = None) -> dict:
        out = {r: judge_book(_book_pairs(m[r], before_day), look, r)
               for r in ("t187b", "t187c", "t188")}
        for tf in P.MAKER_TIMEFRAMES:
            mp = [p for p in m["maker"] if p.timeframe == tf
                  and (before_day is None or p.day < before_day)]
            s = summary(mp)
            rule = f"t189_{tf}"
            out[rule] = judge_maker([(p.day, p.delta) for p in mp], s["costo_baja_r"],
                                    halves_same_sign(mp), look, rule)
        return out

    # --- miradas, veredictos y adopción ----------------------------------------------
    def _looks(self, m: dict, now: int) -> dict:
        path = self.dir / "looks.json"
        looks = adoption.read_json(path)
        look = due_look(now)
        if look is not None and str(look) not in looks:
            cut = P.checkpoints_ms()[look] // P.DAY_MS
            looks[str(look)] = clean({"at": now, "results": self.judge(m, look, cut)})
            adoption.write_json(path, looks)
        return looks

    def run(self, now: int) -> dict:
        with self._lock:
            m = self.measure()
            looks = self._looks(m, now)
            decided: dict[str, dict] = {}
            for k in sorted(looks, key=int):
                for rule, v in looks[k]["results"].items():
                    if rule not in decided and v.get("state") != RUNNING:
                        decided[rule] = v
            verdicts = adoption.settle(self.dir / "verdicts.json", decided, now)
            adopted = adoption.adopt(self.adopted_path, verdicts, self.adopt_on)
            entry = clean(self._entry(m, now, verdicts, adopted))
            self.dir.mkdir(parents=True, exist_ok=True)
            with (self.dir / "reviews.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self.last = entry
            return entry

    def _entry(self, m: dict, now: int, verdicts: dict, adopted: dict) -> dict:
        prov = self.judge(m, None)
        rules = {}
        for r in ("t187b", "t187c", "t188"):
            rules[r] = {**prov[r], "usdt": _usd(m[r])}
        a = m["t187a"]
        rules["t187a"] = {"n": len(a), "delta": (sum(p.delta for p in a) / len(a)) if a else 0.0,
                          "usdt": _usd(a), "state": "ADOPTADA POR DECISIÓN",
                          "why": "se enciende sola al cerrar T31 (fase 2); aquí solo se informa"}
        rules["t188"]["pendientes"] = m["t188_pending"]
        for tf in P.MAKER_TIMEFRAMES:
            mp = [p for p in m["maker"] if p.timeframe == tf]
            rules[f"t189_{tf}"] = {**prov[f"t189_{tf}"], "brazos": summary(mp)}
        nxt = [t for t in P.checkpoints_ms() if t > now]
        return {"at": now, "mode": "SIMULADO", "prereg": P.VERSION,
                "fingerprint": P.fingerprint(), "start": P.START_ISO,
                "next_look": nxt[0] if nxt else None, "operaciones_medidas": m["n_rows"],
                "rules": rules, "verdicts": verdicts, "adopted": adopted,
                "adopt_enabled": self.adopt_on,
                "source": "libro fijo (universo oficial de T144) y vista de la mesa principal"}

    def maybe_run(self) -> bool:
        """Gancho del bróker: True si revisó (el gancho late «ok» con su componente)."""
        now = self.clock()
        if self.last_run is not None and now - self.last_run < EVERY_MS:
            return False
        self.last_run = now
        try:
            self.run(now)
            self.error = ""
        except Exception as exc:  # noqa: BLE001 - un fallo del vigía nunca tumba al bróker
            self.error = f"{type(exc).__name__}: {exc}"
            log.warning("vigía de asimetría: %s", self.error)
            return False
        return True

    def payload(self) -> dict:
        return {**self.last, "last_run": self.last_run, "error": self.error,
                "checkpoints": list(P.checkpoints_ms()), "rules_auto": list(P.AUTO_RULES),
                "rules_user": list(P.USER_RULES)}


def build_asym_router(get_watch: Callable[[], AsymWatch | None]) -> APIRouter:
    router = APIRouter(prefix="/v2/paper", tags=["paper"])

    @router.get("/asymmetry")
    def asymmetry(history: int = Query(0, ge=0, le=500)) -> dict:
        """T187–T189: la asimetría medida en sombra, los veredictos y lo adoptado (solo lectura)."""
        w = get_watch()
        if w is None:
            return {"mode": "SIMULADO", "enabled": False,
                    "why": "sin bróker en vivo (pruebas o EIM_PAPER=0)"}
        out = {"mode": "SIMULADO", "enabled": True, **w.payload()}
        if history:
            p = w.dir / "reviews.jsonl"
            lines = p.read_text(encoding="utf-8").splitlines()[-history:] if p.exists() else []
            out["history"] = [json.loads(x) for x in lines if x.strip()]
        return out

    return router
