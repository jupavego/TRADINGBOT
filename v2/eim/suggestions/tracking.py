"""Seguimiento puro de lo publicado (T51): resolución, señal contra resultado y degradación.

Resolver = simular lo publicado con el mismo motor del bróker (`paper/engine.simulate`) sobre las
velas de 15 m POSTERIORES a la publicación (la vela en curso al publicar no cuenta: sin
anticipación). Nada se marca nunca como ejecutado: toda fila conserva `state` de sugerida.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from statistics import fmean

from eim.paper.engine import Outcome, Path, simulate
from eim.paper.ideas import Idea
from eim.paper.params import ExecParams
from eim.suggestions.publisher import STATE

KEYS = ("id", "vid", "sid", "fingerprint", "strategy", "timeframe", "n", "side", "kind", "entry",
        "sl", "tp", "price", "reason", "published_ms", "idea_t", "evidence")
LAST_N = 20           # operaciones publicadas que miden la degradación
MIN_CLOSED = 5        # cerradas mínimas para opinar de «dentro / fuera» del IC95 %


def idea_of(row: dict) -> Idea:
    """La idea publicada, tal como se decidió (para volver a simularla)."""
    return Idea(id=row["id"], strategy=row["strategy"], family="", symbol=row["symbol"],
                t=int(row["idea_t"]), side=int(row["side"]), kind=row["kind"],
                entry=row["entry"], sl=row["sl"], tp=row["tp"], fill_ms=int(row["fill_ms"]),
                hold_ms=int(row["hold_ms"]), conf=0.0, why=(), timeframe=row["timeframe"],
                version=row["fingerprint"])


def after_publication(idea: Idea, published_ms: int, step_ms: int) -> Idea:
    """Idea desplazada a la primera vela que ABRE después de publicarla; una orden límite
    conserva su vencimiento original."""
    t0 = -(-published_ms // step_ms) * step_ms
    if t0 <= idea.t:
        return idea
    end = idea.t + idea.fill_ms
    return replace(idea, t=t0, fill_ms=max(0, end - t0) if idea.kind == "limit" else 0)


def _state(o: Outcome) -> str:
    if o.status == "PENDIENTE":
        return "pendiente"
    if o.status == "CANCELADA":
        return "no_llenada"
    if o.status == "RECHAZADA":
        return "rechazada"
    return "cerrada" if o.status == "CERRADA" else "abierta"


def resolve(rows: Sequence[dict], path: Path | None, ep: ExecParams) -> list[dict]:
    """Cada publicación con su resolución (misma lista y orden que `rows`)."""
    out = []
    for row in rows:
        base = {**{k: row[k] for k in KEYS}, "state": STATE, "executed": False}
        if path is None or not len(path.t):
            out.append({**base, "resolution": {"state": "sin_datos"}})
            continue
        o = simulate(after_publication(idea_of(row), int(row["published_ms"]), path.step),
                     path, ep)
        res = {"state": _state(o), "status": o.status, "reason": o.reason, "fill_t": o.fill_t,
               "fill": o.fill, "exit_t": o.exit_t, "exit": o.exit, "r": o.r, "mfe_r": o.mfe_r,
               "mae_r": o.mae_r, "cause": o.cause, "mark": o.mark}
        out.append({**base, "resolution": res})
    return out


def _closed(rs: Sequence[dict]) -> list[dict]:
    return [r for r in rs if r["resolution"]["state"] == "cerrada"
            and r["resolution"]["r"] is not None]


def _expected(rs: Sequence[dict], current: Mapping[str, dict]) -> dict:
    """Evidencia fuera de muestra: la del veredicto vigente si existe; si no, la última mostrada."""
    vid = rs[-1]["vid"]
    ev = current.get(vid) or rs[-1]["evidence"]
    ci = ev.get("ci95") or [None, None]
    return {"mean_r": ev.get("mean_r"), "ci95": ci, "n_oos": ev.get("n_oos"),
            "current": vid in current}


def verdict_against(realized: float | None, n: int, ci: Sequence[float | None]) -> str:
    if realized is None or n < MIN_CLOSED or ci[0] is None or ci[1] is None:
        return "sin_muestra"
    return "debajo" if realized < ci[0] else "encima" if realized > ci[1] else "dentro"


def degradation(rs: Sequence[dict], current: Mapping[str, dict]) -> dict | None:
    """Media de las últimas `LAST_N` cerradas por debajo del límite inferior del IC95 % de su
    evidencia → datos de la degradación; None si no hay `LAST_N` o no cae por debajo."""
    last = sorted(_closed(rs), key=lambda r: r["published_ms"])[-LAST_N:]
    lo = _expected(rs, current)["ci95"][0]
    if len(last) < LAST_N or lo is None:
        return None
    mean = fmean(r["resolution"]["r"] for r in last)
    return {"mean_r": mean, "ci_low": lo, "n": len(last)} if mean < lo else None


def scorecard(resolved: Sequence[dict], current: Mapping[str, dict], review: set[str],
              sim_fill: Mapping[str, tuple[int, int]]) -> list[dict]:
    """Señal contra resultado por `estrategia@marco@versión`.

    `current`: evidencia vigente por id de versión; `review`: ids en revisión; `sim_fill`:
    (llenadas, decididas) de las ideas simuladas por el bróker, por `vid`.
    """
    by: dict[str, list[dict]] = {}
    for r in sorted(resolved, key=lambda x: x["published_ms"]):
        by.setdefault(r["vid"], []).append(r)
    out = []
    for vid, rs in by.items():
        states = [r["resolution"]["state"] for r in rs]
        cl = _closed(rs)
        rr = [r["resolution"]["r"] for r in cl]
        filled = len(cl) + states.count("abierta")
        decided = filled + states.count("no_llenada")
        exp = _expected(rs, current)
        real = fmean(rr) if rr else None
        sf, sd = sim_fill.get(vid, (0, 0))
        last = rr[-LAST_N:]
        out.append({
            "vid": vid, "strategy": rs[0]["strategy"], "timeframe": rs[0]["timeframe"],
            "published": len(rs), "closed": len(cl), "open": states.count("abierta"),
            "pending": states.count("pendiente"), "not_filled": states.count("no_llenada"),
            "rejected": states.count("rechazada"), "realized_mean_r": real,
            "cum_r": sum(rr), "hit_rate": (sum(1 for x in rr if x > 0) / len(rr)) if rr else None,
            "last_n": len(last), "last_mean_r": fmean(last) if last else None,
            "expected": exp, "against": verdict_against(real, len(rr), exp["ci95"]),
            "fill_real": filled / decided if decided else None,
            "fill_sim": sf / sd if sd else None, "fill_n": [decided, sd],
            "in_review": vid in review})
    return sorted(out, key=lambda x: x["vid"])


def totals(resolved: Sequence[dict]) -> dict:
    rr = [r["resolution"]["r"] for r in _closed(resolved)]
    return {"published": len(resolved), "closed": len(rr), "cum_r": sum(rr),
            "hit_rate": (sum(1 for x in rr if x > 0) / len(rr)) if rr else None,
            "mean_r": fmean(rr) if rr else None}


def gap_summary(gaps: Sequence[dict], now: int, window_ms: int) -> dict:
    """Tiempo observado sin sugerencia por estado dentro de la ventana [now−window, now]."""
    lo, by = now - window_ms, {}
    for g in gaps:
        ms = max(0, min(g["to"], now) - max(g["from"], lo))
        by[g["status"]] = by.get(g["status"], 0) + ms
    return {"window_ms": window_ms, "ms_by_status": by, "ms_total": sum(by.values()),
            "intervals": len(gaps)}
