"""Lo que vuelve de la cantera a la biblioteca, los agentes, la síntesis y el usuario (T172). Puro.

Por los cauces ya fijados (nota de T167 §6 y §9.4); **nada cambia solo**:

- **Biblioteca** (entregable 2, rec. 18): cada prospecto deja, por cada obra que cita, un hecho de
  aprendizaje con uno de tres veredictos: *sostenida* (el escalafón lo ascendió a Promesa por
  e-BH), *refutada* (la cota superior de futilidad de d̃ queda por debajo de μ_mín con n ≥ 30) o
  *no concluyente*, que es el veredicto por defecto. Los pesos de consenso no se tocan.
- **Agentes** (3): las bajas cuya causa es una variable sin información → línea para BACKLOG.
- **Ciclo de mejora** (3b, §9.2–9.3): por baja, diagnóstico en R (T154) y cadena resumida (T155);
  con causa nombrada, propuesta de versión nueva (◆, gasta una plaza de reserva) si su MinTRL con
  +0,25 R cabe en lo que queda de fase; el costo repetido en un marco se propone como variante
  de ejecución en mesa aparte (`EIM_PAPER_VARIANTS`), para todas las cuentas a la vez (◆).
- **Síntesis** (4): informatividad medida de cada agente por su prospecto base, para T150.
- **Graduaciones** (5) y **cierre** (6): con el recorte de Harvey-Liu y el ◆ que confirma o veta.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from eim.library.digital.learning import MIN_N
from eim.nursery.ladder import BAJA, PRIMER, PROMESA, Standing
from eim.nursery.ladder_stats import DAY_MS, AccountData
from eim.nursery.report import haircut as hl
from eim.nursery.report.rows import Snapshot
from eim.validation.power import min_track_record

SOSTENIDA, REFUTADA, NO_CONCLUYENTE = "sostenida", "refutada", "no concluyente"
CAUSES = ("variable sin información", "costo", "cadencia", "teoría contraria")
COST_VARIANT_MIN = 2           # bajas por costo en un mismo marco para proponer una variante


def verdict(s: Standing | None, rules) -> tuple[str, str]:
    """Veredicto de la teoría de un prospecto y su motivo (sin ascenso ni futilidad: no concluye)"""
    if s is None:
        return NO_CONCLUYENTE, "sin revisión todavía"
    if s.frozen_e is not None or s.stage in (PROMESA, PRIMER):
        return SOSTENIDA, f"ascendió a Promesa por e-BH (e = {s.frozen_e or 0:.2f})"
    k, fut = s.metrics, rules.futility
    ub = k.get("futility_ub")
    if ub is not None and (k.get("obs") or 0) >= fut.min_trades and ub < fut.mu_min_r:
        return REFUTADA, f"cota superior de d̃ {ub:+.3f} R < μ_mín {fut.mu_min_r:+.2f} R"
    n = k.get("obs") or 0
    return NO_CONCLUYENTE, (f"{n} observaciones; ni ascenso por e-BH ni futilidad"
                            if n else "sin operaciones cerradas en la última revisión")


def library_facts(snap: Snapshot, stand: Mapping[str, Standing],
                  literature: Mapping[str, Sequence[dict]], review: int,
                  review_ms: int | None) -> list[dict]:
    """Un hecho de aprendizaje por (prospecto, obra) en la revisión `review` (1…6)."""
    pr, out = snap.prereg, []
    for x in pr.family.members:
        s = stand.get(x.id)
        v, why = verdict(s, pr.ladder)
        k = s.metrics if s else {}
        for w in literature.get(x.id, ()):
            out.append({
                "key": f"{pr.version}|r{review}|{x.id}|{w['work']}",
                "prereg": pr.version, "review": review, "review_ms": review_ms,
                "prospect": x.id, "agent": x.agent_id, "theme": x.theme,
                "timeframe": x.timeframe, "work": w["work"], "concept": w.get("concept"),
                "work_stance": w.get("stance"), "verdict": v, "motivo": why,
                "n": k.get("obs"), "d_mean": k.get("d_mean"),
                "futility_ub": k.get("futility_ub"), "stage": s.stage if s else None,
                "scope": "BTCUSDT hacia adelante desde el alta de cantera_v1 (SIMULADO)"})
    return out


def cause_of(s: Standing, row: Mapping) -> tuple[str | None, str]:
    """Causa nombrada de una baja (§9.2), o None con su motivo («perdió dinero» no basta)."""
    reason = (s.exit or {}).get("reason")
    if reason == "fecha_limite":
        return None, "fecha límite sin veredicto: no hay causa que nombrar"
    motivo = (s.exit or {}).get("motivo", "")
    if reason == "inactividad" or (reason == "examen_fisico"
                                   and ("al mes" in motivo or "en posición" in motivo)):
        return "cadencia", motivo
    if reason == "examen_fisico" and "costo medio" in motivo:
        return "costo", motivo
    n = row.get("n") or 0
    if n < MIN_N:
        return None, f"muestra insuficiente ({n} cierres < {MIN_N}); no se concluye"
    d, gross, net = row["d"], row["r_gross"], row["r_net"]
    if d.get("hi") is not None and d["hi"] < 0:
        return "teoría contraria", (f"d {d['mean']:+.3f} R con IC por debajo de 0: el lado "
                                    "contrario rinde más que la regla")
    if gross.get("mean") is not None and gross["mean"] > 0 >= (net.get("mean") or 0):
        return "costo", (f"R bruto {gross['mean']:+.3f} positivo y neto {net['mean']:+.3f}: "
                         "el costo se come la señal")
    return "variable sin información", (f"d {d.get('mean') or 0:+.3f} R indistinguible del azar "
                                        f"con {n} cierres: su variable no aporta para decidir")


def improvement(snap: Snapshot, stand: Mapping[str, Standing], rows: Sequence[dict]) -> dict:
    """Diagnóstico por baja, propuestas de versión nueva, BACKLOG y variantes de ejecución."""
    pr = snap.prereg
    by = {r["id"]: r for r in rows}
    left = max(0.0, pr.ladder.deadline_days - (snap.asof_ms - snap.alta_ms) / DAY_MS)
    target = pr.ladder.drawdown.target_edge_r / pr.ladder.drawdown.sigma_r
    need = min_track_record(target, 0.0)
    drops, proposals, backlog, cost_tf = [], [], [], {}
    for x in pr.family.members:
        s = stand.get(x.id)
        if s is None or s.stage != BAJA:
            continue
        r = by[x.id]
        cause, why = cause_of(s, r)
        chain = {"n": r["n"], "r_net": r["r_net"]["mean"], "r_gross": r["r_gross"]["mean"],
                 "cost_r": r["cost_r"]["mean"], "hit_rate": r["hit_rate"],
                 "d": r["d"]["mean"], "d_ci": [r["d"]["lo"], r["d"]["hi"]]}
        drops.append({"id": x.id, "agent": x.agent_id, "timeframe": x.timeframe,
                      "exit": s.exit, "cause": cause, "why": why, "chain": chain})
        if cause == "costo":
            cost_tf.setdefault(x.timeframe, []).append(x.id)
        if cause == "variable sin información":
            backlog.append(f"- **T172 (cantera, {pr.version})** — mejorar el agente "
                           f"`{x.agent_id}`: el prospecto `{x.id}` ({x.timeframe}) causó baja "
                           f"({(s.exit or {}).get('reason')}) con {r['n']} cierres y d "
                           f"{r['d']['mean'] or 0:+.3f} R, indistinguible del azar. Versión "
                           "nueva del agente = prospectos nuevos que cuentan en la familia "
                           "(◆, §9.2).")
        if cause is None:
            continue
        days = need / r["per_day"] if r.get("per_day") else math.inf
        fits = days <= left
        proposals.append({"id": x.id, "cause": cause, "requires": "◆ del usuario",
                          "reserve_slot": True, "mintrl_trades": round(need, 1),
                          "mintrl_days": None if math.isinf(days) else round(days, 1),
                          "days_left": round(left, 1), "fits": fits,
                          "note": ("hipótesis escrita con su obra del catálogo antes de "
                                   "inscribirla; una sola reentrada por baja") if fits else
                                  "no cabe: su MinTRL con +0,25 R pasa de la fecha límite"})
    variants = [{"timeframe": tf, "prospects": ids, "kind": "variante de ejecución",
                 "how": "mesa aparte con EIM_PAPER_VARIANTS (maker/puerta de costo); si se "
                        "adopta, para todas las cuentas a la vez", "requires": "◆ del usuario"}
                for tf, ids in sorted(cost_tf.items()) if len(ids) >= COST_VARIANT_MIN]
    return {"drops": drops, "proposals": proposals, "backlog": backlog, "variants": variants,
            "reserve_slots": pr.family.reserve_slots}


def informativity(snap: Snapshot, rows: Sequence[dict]) -> dict:
    """Por agente, su prospecto base frente a sus gemelos al azar: la evidencia para T150."""
    out = {}
    for r in rows:
        if r["role"] != "base":
            continue
        d = r["d"]
        state = ("informativo" if d.get("lo") is not None and d["lo"] > 0 else
                 "contrario" if d.get("hi") is not None and d["hi"] < 0 else "no concluyente")
        if (d.get("n") or 0) < MIN_N:
            state = "muestra insuficiente"
        out[r["agent"]] = {"base": r["id"], "n": d["n"], "d_mean": d["mean"],
                           "lo": d["lo"], "hi": d["hi"], "r_net": r["r_net"]["mean"],
                           "state": state}
    return {"agents": out, "rule": "Lectura para T150: cambiar pesos de la síntesis exige "
                                   "pre-registro y ◆; la cantera pesa 0 en la síntesis."}


def graduations(snap: Snapshot, stand: Mapping[str, Standing],
                data: Mapping[str, AccountData]) -> list[dict]:
    """Candidatos a primer equipo con su ventaja en vivo tras el recorte de Harvey-Liu (rec. 19)."""
    acc_of = snap.account_of()
    r_by = {x.id: [c.r for c in data.get(acc_of.get(x.id, ""), AccountData()).closed
                   if c.r is not None] for x in snap.prereg.family.members}
    out = []
    for pid, s in stand.items():
        if s.stage != PRIMER:
            continue
        cut = hl.haircut(r_by[pid], hl.family_pvalues(r_by, skip=pid), snap.prereg.m)
        out.append({"id": pid, "haircut": cut,
                    "t145_trigger": bool(cut and cut["live_edge_r"] > 0),
                    "decision": "◆ del usuario: confirma o veta la salida mecánica del "
                                "escalafón (no elige entre candidatos); inscribir en T49 con su "
                                "historial hacia adelante"})
    return out


def closure(snap: Snapshot, stand: Mapping[str, Standing]) -> dict | None:
    """Cierre de la fase en la fecha límite: veredicto por prospecto, aunque nadie se gradúe."""
    deadline = snap.alta_ms + snap.prereg.ladder.deadline_days * DAY_MS
    if snap.asof_ms < deadline:
        return None
    per = {pid: {"stage": s.stage, "exit": s.exit} for pid, s in stand.items()}
    grads = [pid for pid, s in stand.items() if s.stage == PRIMER]
    return {"deadline_ms": deadline, "graduated": grads,
            "headline": ("ninguno se graduó" if not grads else
                         f"{len(grads)} candidato(s) a primer equipo, pendientes de ◆"),
            "per_prospect": per}
