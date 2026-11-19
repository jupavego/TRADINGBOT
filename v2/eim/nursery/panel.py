"""Vista del panel «Cantera» (T171): escalafón por agente, honesto con la muestra. Puro. SIMULADO.

Diseño: `PLAN/notas/T167_cantera.md` §3 y §7, y la nota §10 (rec. 8, 15, 17 y 20). No decide nada:
describe a cada prospecto en su etapa y, sobre todo, **cuánto le falta** para que su cifra
signifique algo. El orden es por agente y etapa, nunca por rendimiento.

Por prospecto: rentabilidad neta acumulada, saldo, drawdown, n, acierto, costo; comparación con su
hermano simple, con sus gemelos al azar, con comprar y mantener (en R y con desglose largo/corto) y
con el `agente_{id}` genérico; régimen; **R neto encogido junto al bruto** (`themes.shrink`, hacia
su tema); volatilidad y drawdown frente a su tope como señal temprana, y **días estimados hasta
veredicto**: MinTRL (T161, `validation/power.py`) de la hipótesis primaria con la confianza
corregida por la familia, α = 0,05 / m (z ≈ 3,09 con m = 50).

La contabilidad de la cantera es **aparte**: libro `data/paper_cantera.duckdb` (T168), que no se
suma nunca a los cuatro perfiles ni a la contabilidad oficial de T144 (`eim/paper/universe.py`).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from statistics import NormalDist

import numpy as np

from eim.copytrading.stats import moments
from eim.nursery import themes
from eim.nursery.book import Book
from eim.nursery.ladder import Standing
from eim.nursery.ladder_stats import DAY_MS, AccountData, observations
from eim.nursery.prereg import Prereg
from eim.validation.power import min_track_record

SOURCE = "data/paper_cantera.duckdb · libro de la cantera (T168) · pre-registro cantera_v1 (T170)"
ACCOUNTING = ("El P&L, el saldo, el drawdown y las operaciones de la cantera "
              "son un libro propio (data/paper_cantera.duckdb) y no se suman nunca a los cuatro "
              "perfiles principales ni a la contabilidad oficial del bróker simulado (T144).")
BANDS = (("scalping", "Scalping", "operaciones"), ("intradia", "Intradía", "operaciones"),
         ("tres_dias", "Tres días", "operaciones"), ("semanal", "Semanal", "días"))
STAGE_ORDER = ("primer_equipo", "promesa", "cantera", "guarderia", "baja")
FAMILY_ALPHA = 0.05            # MinTRL corregido por la familia: α / m, unilateral
MIN_OBS_ESTIMATE = 5           # menos que esto: sin estimación de MinTRL (la muestra no da)


def _f(x: float | None, d: int = 4) -> float | None:
    return None if x is None or not math.isfinite(x) else round(float(x), d)


def _i(x: float | None) -> int | None:
    return None if x is None else int(x)


def family_z(m: int, alpha: float = FAMILY_ALPHA) -> float:
    return NormalDist().inv_cdf(1 - alpha / max(m, 1))


def verdict_eta(obs: Sequence[float], clip_r: float, m: int, since_ms: int, now_ms: int,
                deadline_ms: int, alpha: float = FAMILY_ALPHA) -> dict:
    """Días estimados hasta un veredicto a favor (MinTRL corregido por la familia).

    Con la ventaja observada de la hipótesis primaria (d̃ recortado), cuántas observaciones
    harían falta para rechazar «d̃ ≤ 0» con confianza 1 − α/m, cuántas faltan y, al ritmo de
    observaciones de la cuenta, en cuántos días. Si d̃ ≤ 0 no hay veredicto a favor que esperar.
    """
    z = family_z(m, alpha)
    x = np.clip(np.asarray(obs, float), -clip_r, clip_r)
    days_left = max(0.0, (deadline_ms - now_ms) / DAY_MS)
    base = {"z": round(z, 3), "alpha": round(alpha / max(m, 1), 6), "obs": len(x),
            "deadline_days": round(days_left, 1)}
    if len(x) < MIN_OBS_ESTIMATE:
        return {**base, "state": "sin_muestra", "mintrl": None, "remaining": None, "days": None,
                "motivo": f"{len(x)} observaciones: hacen falta al menos {MIN_OBS_ESTIMATE} para "
                          "estimar el MinTRL"}
    mean, sd, skew, kurt = moments(x.tolist())
    if sd <= 0 or mean <= 0:
        return {**base, "state": "sin_ventaja", "mintrl": None, "remaining": None, "days": None,
                "motivo": f"d̃ medio {mean:+.3f} R ≤ 0: con esta muestra no apunta a un veredicto "
                          "a favor"}
    need = min_track_record(mean / sd, 0.0, skew, kurt, alpha / max(m, 1))
    remaining = max(0, math.ceil(need) - len(x))
    elapsed = max((now_ms - since_ms) / DAY_MS, 1e-9)
    rate = len(x) / elapsed
    days = remaining / rate if rate > 0 else math.inf
    return {**base, "state": "estimable", "mintrl": _f(need, 1), "remaining": remaining,
            "rate_per_day": _f(rate, 3), "days": _f(days, 1),
            "beyond_deadline": bool(days > days_left),
            "motivo": f"MinTRL {need:.0f} observaciones con z = {z:.2f} (familia de {m}); "
                      f"faltan {remaining} a {rate:.2f} por día"}


def _rows(summary: Mapping) -> dict[str, dict]:
    return {r["account"]: r for r in summary.get("accounts", [])}


def _vs_return(own: dict | None, other: dict | None, label: str | None) -> dict | None:
    if label is None:
        return None
    if other is None:
        return {"id": label, "net_return_pct": None, "diff_pct": None}
    a, b = (own or {}).get("net_return_pct"), other.get("net_return_pct")
    return {"id": label, "net_return_pct": b, "n": other.get("n"),
            "diff_pct": None if a is None or b is None else round(a - b, 3)}


def _side_r(book: Book, account: str) -> dict:
    out = {"largo": [0, 0.0], "corto": [0, 0.0]}
    for e in book.of(account):
        if e.booked and e.trade.status == "CERRADA" and e.trade.r is not None:
            k = out["largo" if e.side > 0 else "corto"]
            k[0] += 1
            k[1] += float(e.trade.r)
    return {k: {"n": n, "r_sum": round(r, 3)} for k, (n, r) in out.items()}


def _regime(acc: AccountData) -> dict:
    by: dict[str, list[float]] = {}
    for c in acc.closed:
        by.setdefault(c.regime or "sin_etiqueta", []).append(c.d)
    rows = {k: {"n": len(v), "d_mean": round(float(np.mean(v)), 4)} for k, v in sorted(by.items())}
    dom = max(rows, key=lambda k: rows[k]["n"]) if rows else None
    return {"dominant": dom, "by": rows}


def _random(row: dict, initial: float, k: int) -> dict:
    twins = sum(v[1] for v in (row.get("daily") or {}).values())
    own = row.get("net_return_pct")
    tw = round(twins / initial * 100, 3)
    d = row.get("d_vs_twins") or {}
    return {"twins_return_pct": tw, "diff_pct": None if own is None else round(own - tw, 3),
            "d_mean_r": d.get("mean"), "d_lo": d.get("lo"), "d_hi": d.get("hi"), "k": k}


def prospect_view(mb, row: dict, st: Standing | None, acc: AccountData, pr: Prereg,
                  rows_by_pid: Mapping[str, dict], rows: Mapping[str, dict], book: Book,
                  shrunk: Mapping[str, dict], since_ms: int, now_ms: int, deadline_ms: int
                  ) -> dict:
    rules = pr.ladder
    band = (st.band if st and st.band else mb.band)
    unit = "días" if band in rules.primary.day_unit_bands else "operaciones"
    obs = observations(acc, band, rules)
    rs = [c.r for c in acc.closed if c.r is not None]
    dd, cap = row.get("max_drawdown_pct"), rules.drawdown.caps_pct.get(mb.id)
    sh = shrunk.get(mb.id) or {}
    bh = dict(row.get("_bh") or {})
    min_n = rules.nursery_exit.min_trades
    spec = next((x for x in pr.family.members if x.id == mb.id), None)
    return {
        "id": mb.id, "agent_id": mb.agent_id, "timeframe": mb.timeframe, "band": band,
        "unit": unit, "theme": mb.theme, "role": spec.role if spec else None,
        "n_params": mb.n_params, "sibling": mb.sibling, "generic": mb.generic,
        "account": row.get("account"), "name": (row.get("prospect") or {}).get("name"),
        "stage": st.stage if st else "guarderia",
        "stage_since_ms": st.since_ms if st else since_ms,
        "exit": st.exit if st else None, "reviews": st.reviews if st else 0,
        "criteria": st.criteria if st else [],
        "net_return_pct": row.get("net_return_pct"), "balance": row.get("balance"),
        "max_drawdown_pct": dd, "n": row.get("n", 0), "open": row.get("open", 0),
        "hit_rate": row.get("hit_rate"), "cost_paid_usd": row.get("cost_paid_usd"),
        "sample": {"obs": len(obs), "min": min_n, "unit": unit, "ok": len(obs) >= min_n,
                   "label": None if len(obs) >= min_n else "muestra insuficiente"},
        "vs": {
            "sibling": _vs_return(row, rows_by_pid.get(mb.sibling or ""), mb.sibling),
            "random": _random(row, book.params.initial_equity, book.params.twins_k),
            "buy_hold": None if not bh else {**bh, "own_by_side": _side_r(book, row["account"])
                                             if row.get("account") else None},
            "generic": _vs_return(row, rows.get(mb.generic or ""), mb.generic),
        },
        "regime": _regime(acc),
        "r_net": {"gross_r": _f(float(np.mean(rs))) if rs else None,
                  "d_raw": sh.get("raw"), "d_shrunk": sh.get("shrunk"),
                  "shrink_weight": sh.get("weight"), "theme": mb.theme},
        "early": {"vol_r": _f(float(np.std(rs, ddof=1))) if len(rs) > 1 else None,
                  "max_dd_pct": dd, "dd_cap_pct": cap,
                  "dd_used": None if dd is None or not cap else round(dd / cap, 3)},
        "verdict": verdict_eta(obs, rules.primary.clip_r, pr.m, since_ms, now_ms, deadline_ms),
    }


def build_panel(book: Book, summary: Mapping, pr: Prereg, alta_ms: int,
                stand: Mapping[str, Standing], data: Mapping[str, AccountData], now_ms: int
                ) -> dict:
    """La panorámica por agente: lo primero que ve el usuario en la pestaña «Cantera»."""
    rows = _rows(summary)
    acc_of = {a.prospect.id: a.id for a in book.accounts if a.prospect is not None}
    rows_by_pid = {pid: rows[aid] for pid, aid in acc_of.items() if aid in rows}
    members = pr.members()
    reviews = [alta_ms + d * DAY_MS for d in pr.ladder.reviews_days]
    deadline = reviews[-1]
    d_by = {mb.id: [c.d for c in data.get(acc_of.get(mb.id, ""), AccountData()).closed]
            for mb in members}
    shrunk = themes.shrink(d_by, {mb.id: mb.theme for mb in members}, pr.ladder.primary.clip_r)
    bh = summary.get("buy_and_hold")
    prospects = []
    for mb in members:
        aid = acc_of.get(mb.id, "")
        row = {**(rows.get(aid) or {}), "_bh": bh}
        since = max(alta_ms, mb.registered_ms or alta_ms)      # reentrada: cuenta desde su alta
        prospects.append(prospect_view(mb, row, stand.get(mb.id), data.get(aid, AccountData()),
                                       pr, rows_by_pid, rows, book, shrunk, since, now_ms,
                                       deadline))
    order = {s: i for i, s in enumerate(STAGE_ORDER)}
    prospects.sort(key=lambda p: (p["agent_id"], order.get(p["stage"], 9), p["id"]))
    agents = []
    for aid in sorted({p["agent_id"] for p in prospects}):
        ps = [p for p in prospects if p["agent_id"] == aid]
        gen = sorted({p["generic"] for p in ps if p["generic"]})
        agents.append({"agent_id": aid, "prospects": [p["id"] for p in ps],
                       "stages": {s: sum(1 for p in ps if p["stage"] == s) for s in STAGE_ORDER
                                  if any(p["stage"] == s for p in ps)},
                       "generic": [{"account": g, "net_return_pct": (rows.get(g) or {})
                                    .get("net_return_pct"), "n": (rows.get(g) or {}).get("n")}
                                   for g in gen]})
    fp = pr.false_promises
    nxt = next((t for t in reviews if t > now_ms), None)
    last = max((int(e.trade.exit_t) for e in book.entries
                if e.booked and e.trade.exit_t is not None and e.trade.status == "CERRADA"),
               default=None)
    return {
        "source": SOURCE, "accounting": ACCOUNTING, "mode": "SIMULADO",
        "order": "por agente y etapa (nunca por rendimiento)",
        "coverage": {"from_ms": alta_ms, "to_ms": now_ms, "last_close_ms": last,
                     "days": round((now_ms - alta_ms) / DAY_MS, 2),
                     "closed": sum(p["n"] or 0 for p in prospects)},
        "header": {
            "false_promises": {"mean": fp.get("mean"), "p_at_least_one": fp.get("p_at_least_one"),
                               "sims": fp.get("sims"), "m": fp.get("m"), "q": pr.ladder.promise.q,
                               "reading": fp.get("reading")},
            "family_m": pr.m, "members": len(members), "z_family": round(family_z(pr.m), 3),
            "next_review_ms": nxt, "reviews_ms": reviews, "deadline_ms": deadline,
            "min_sample": pr.ladder.nursery_exit.min_trades,
            "stages": {s: sum(1 for p in prospects if p["stage"] == s) for s in STAGE_ORDER},
        },
        "bands": [{"id": b, "label": lab, "unit": u,
                   "count": sum(1 for p in prospects if p["band"] == b)} for b, lab, u in BANDS],
        "agents": agents, "prospects": prospects,
    }


def prospect_card(book: Book, summary: Mapping, prospect_id: str,
                  dossiers: Mapping[str, dict], max_trades: int = 500) -> dict | None:
    """Ficha del prospecto: su teoría, sus variables, sus parámetros citados, las obras que lo
    respaldan o contradicen (T157) y su curva simulada con las operaciones."""
    acc = next((a for a in book.accounts if a.prospect is not None
                and a.prospect.id == prospect_id), None)
    if acc is None:
        return None
    p = acc.prospect
    dossier = dossiers.get(p.agent_id) or {}
    raw = next((x for x in dossier.get("prospects", []) if x.get("id") == prospect_id), {})
    lit_by = {x["id"]: x for x in dossier.get("literature", []) if isinstance(x, dict)}
    works = [{"id": w, "stance": (lit_by.get(w) or {}).get("stance"),
              "concept": (lit_by.get(w) or {}).get("concept"),
              "consensus": (lit_by.get(w) or {}).get("consensus")} for w in p.literature]
    var_note = {v["name"]: v for v in dossier.get("variables", []) if isinstance(v, dict)}
    row = _rows(summary).get(acc.id) or {}
    trades = []
    for e in sorted(book.of(acc.id), key=lambda x: x.t):
        if not e.booked or e.trade.status not in ("CERRADA", "ABIERTA"):
            continue
        tr = e.trade
        trades.append({"t": int(e.t), "side": int(e.side), "status": tr.status,
                       "reason": tr.reason, "fill_t": _i(tr.fill_t), "fill": _f(tr.fill, 2),
                       "exit_t": _i(tr.exit_t), "exit": _f(tr.exit, 2), "r": _f(tr.r),
                       "pnl_usd": round(float(e.pnl_usd), 2), "d_r": _f(e.d_r),
                       "maker": bool(e.order.maker)})
    return {
        "mode": "SIMULADO", "source": SOURCE, "id": p.id, "account": acc.id,
        "agent_id": p.agent_id, "agent_version": p.agent_version, "name": p.name,
        "role": p.role, "theory": raw.get("theory") or dossier.get("theory"),
        "agent_theory": dossier.get("theory"), "rule": p.rule_text, "timeframe": p.timeframe,
        "exit_template": p.exit_template, "max_bars": p.max_bars, "horizon": p.horizon,
        "opposite_of": p.opposite_of, "fingerprint": p.fingerprint,
        "variables": [{"name": v, "source": (var_note.get(v) or {}).get("source"),
                       "note": (var_note.get(v) or {}).get("note")} for v in p.variables],
        "params": [{"name": k, "value": (v or {}).get("value"), "source": (v or {}).get("source")}
                   for k, v in (raw.get("params") or {}).items()],
        "literature": works,
        "equity_curve": row.get("equity_curve", []),
        "initial_equity": book.params.initial_equity,
        "trades": trades[-max_trades:], "trades_total": len(trades),
    }
