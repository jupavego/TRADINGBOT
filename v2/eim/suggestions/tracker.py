"""Seguimiento de sugerencias publicadas (T51): registra, resuelve y vigila la degradación.

`record` guarda cada publicación nueva y los intervalos sin sugerencia; `refresh` resuelve lo
publicado sobre el camino de 15 m del bróker y pone «en revisión» la versión cuyo R medio de las
últimas 20 queda bajo el IC95 % de su evidencia (el publicador la excluye hasta un veredicto
nuevo de T49 con la degradación ya absorbida). Siempre Análisis/Simulado: nada se ejecuta.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence

from eim.data.suggestion_store import SuggestionStore
from eim.paper.engine import Path
from eim.paper.params import ExecParams
from eim.suggestions.publisher import NOTE, Publication, evidence_of
from eim.suggestions.tracking import (
    degradation,
    gap_summary,
    resolve,
    scorecard,
    totals,
)

GAP_JOIN_MS = 10 * 60_000          # una observación a > 10 min de la anterior abre otro intervalo
DAY_MS = 86_400_000


def sim_fill_of(outcomes: Sequence, resolved: Sequence[dict]) -> dict[str, tuple[int, int]]:
    """(llenadas, decididas) de las ideas simuladas por el bróker, por versión publicada."""
    vids = {f"{r['sid']}@{r['fingerprint']}": r["vid"] for r in resolved}
    out: dict[str, list[int]] = {}
    for o in outcomes:
        vid = vids.get(o.idea.vid)
        if vid is None or o.status == "PENDIENTE":
            continue
        a = out.setdefault(vid, [0, 0])
        a[1] += 1
        a[0] += 1 if o.fill_t is not None and o.status != "RECHAZADA" else 0
    return {k: (a[0], a[1]) for k, a in out.items()}


class Tracker:
    def __init__(self, store: SuggestionStore, ep: ExecParams | None = None) -> None:
        self.store, self.ep = store, ep or ExecParams()
        self._lock = threading.Lock()

    # --- registro ---------------------------------------------------------------------
    def record(self, symbol: str, pub: Publication, now: int, verdicts: Sequence[dict],
               verdicts_asof: int | None, criteria: str) -> int:
        """Guarda las publicaciones nuevas (idempotente) y, sin sugerencias, el intervalo."""
        by_id = {v["id"]: v for v in verdicts}
        new = 0
        with self._lock:
            for s in pub.setups:
                v = by_id[s["id"]]
                new += self.store.publish({
                    "id": f"{symbol}:{s['timeframe']}:{s['created_at']}:{s['strategy']}",
                    "symbol": symbol, "published_ms": now, "criteria": criteria,
                    "verdicts_asof": verdicts_asof, "vid": s["id"], "sid": v["sid"],
                    "strategy": s["strategy"], "timeframe": s["timeframe"], "n": v["n"],
                    "fingerprint": v["fingerprint"], "side": 1 if s["side"] == "long" else -1,
                    "kind": s["kind"], "entry": s["entry"], "sl": s["sl"], "tp": s["tp"],
                    "fill_ms": (s["valid_until"] - s["created_at"]) if s["valid_until"] else 0,
                    "hold_ms": int(s["hours"] * 3_600_000), "idea_t": s["created_at"],
                    "price": s["entry"], "reason": s["reason"], "evidence": evidence_of(v)})
            if not pub.setups:
                self.store.gap(symbol, now, pub.status, pub.message, GAP_JOIN_MS)
        return new

    def in_review(self, symbol: str) -> set[str]:
        with self._lock:
            return {r["vid"] for r in self.store.reviews(symbol, open_only=True)}

    # --- resolución y degradación -----------------------------------------------------
    def refresh(self, symbol: str, path: Path | None, verdicts: Sequence[dict],
                verdicts_asof: int | None, now: int) -> list[dict]:
        """Resuelve lo publicado y actualiza las versiones en revisión; devuelve lo resuelto."""
        with self._lock:
            resolved = resolve(self.store.published(symbol), path, self.ep)
            current = {v["id"]: evidence_of(v) for v in verdicts if v["verdict"] == "VALIDADA"
                       and v.get("retired") is None}
            valid = {v["id"] for v in verdicts if v["verdict"] == "VALIDADA"}
            open_ = {r["vid"]: r for r in self.store.reviews(symbol, open_only=True)}
            by: dict[str, list[dict]] = {}
            for r in resolved:
                by.setdefault(r["vid"], []).append(r)
            for vid, rs in by.items():
                deg = degradation(rs, current)
                flag = open_.get(vid)
                if deg and flag is None:
                    self.store.flag(symbol, vid, now, verdicts_asof, deg["mean_r"],
                                    deg["ci_low"], deg["n"])
                elif (flag is not None and not deg and vid in valid and verdicts_asof is not None
                      and (flag["verdict_asof"] or 0) < verdicts_asof):
                    self.store.release(symbol, vid, now)
        return resolved

    # --- vista ------------------------------------------------------------------------
    def history(self, symbol: str, resolved: Sequence[dict], verdicts: Sequence[dict],
                outcomes: Sequence, now: int, limit: int = 100) -> dict:
        with self._lock:
            reviews = self.store.reviews(symbol)
            gaps = self.store.gaps(symbol)
        current = {v["id"]: evidence_of(v) for v in verdicts if v["verdict"] == "VALIDADA"
                   and v.get("retired") is None}
        review = {r["vid"] for r in reviews if r["released"] is None}
        sim = sim_fill_of(outcomes, resolved)
        return {"mode": "ANALISIS", "symbol": symbol, "now": now, "note": NOTE,
                "totals": totals(resolved),
                "scorecard": scorecard(resolved, current, review, sim),
                "published": sorted(resolved, key=lambda r: -r["published_ms"])[:limit],
                "gaps": gaps[-limit:], "gap_summary": gap_summary(gaps, now, 7 * DAY_MS),
                "in_review": [r for r in reviews if r["released"] is None],
                "released": [r for r in reviews if r["released"] is not None]}

