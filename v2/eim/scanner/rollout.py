"""Despliegue gradual multiactivo (T102): alerta → simulación → papel → (ejecución limitada).

Protocolo escrito en `docs/OPERACION.md` §8; aquí, su parte automática y pura. Cada **clase** del
universo es una unidad con un nivel; cada **agente** del escáner es una unidad que solo puede
estar activa o desactivada (su nivel lo marca su clase).

- **Desactivación automática.** Una clase pasa a inactiva tras `DEACTIVATE_AFTER` revisiones
  seguidas en `error`, `sin_datos` u `obsoleto`; un agente, tras las mismas revisiones dando
  `no_data` en al menos `AGENT_BAD_SHARE` de los instrumentos donde corrió (con `AGENT_MIN_RUNS`
  como mínimo). `degradado` NO desactiva: es un peso reducido conocido (p. ej. poca historia).
- **Qué hace la desactivación.** Sus candidatas pasan a **sombra**: dejan de verse como
  candidatas y no pueden promoverse, pero el cálculo sigue. Apagar el cálculo cambiaría la huella
  de agentes y rompería el pre-registro de T95 (la revisión del 2026-12-29 cuenta resultados
  maduros por intento) y, además, impediría ver si se recupera.
- **Reactivación automática** tras `REACTIVATE_AFTER` revisiones sanas seguidas, siempre en
  `alerta`: un nivel perdido se vuelve a ganar con sus criterios.
- **Promoción.** Sube sola solo cuando todos sus criterios se cumplen (ver `blockers`); hoy ninguno
  se cumple: faltan la matriz de T101, la cartera de T96 y el adaptador de T103. La ejecución
  limitada nunca es automática.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping

from eim.scanner.health import ENABLED, ERROR, NO_DATA, STALE, WATCH

ROLLOUT_VERSION = "1"
LEVELS = ("alerta", "simulacion", "papel", "ejecucion_limitada")
LEVEL_ES = {"alerta": "Alerta", "simulacion": "Simulación", "papel": "Papel",
            "ejecucion_limitada": "Ejecución limitada"}
DEACTIVATE_AFTER = 2
REACTIVATE_AFTER = 2
AGENT_BAD_SHARE = 0.5
AGENT_MIN_RUNS = 5
PROMOTE_MIN_OK_CHECKS = 14
SIM_MIN_DAYS = 30
SIM_MIN_MATURED = 200
SHADOW_SHARE = 0.5
HISTORY_MAX = 20
DAY_MS = 86_400_000
BAD = (ERROR, NO_DATA, STALE)
NEVER_AUTO = ("nunca automática: exige la puerta de edge (T27), el cierre de T31 con su informe y "
              "tu decisión escrita")


def agent_stats(view: Mapping | None) -> dict[str, dict[str, int]]:
    """Por agente: en cuántos instrumentos corrió y en cuántos dio `no_data` (última pasada)."""
    out: dict[str, dict[str, int]] = {}
    for d in (view or {}).get("instruments", {}).values():
        for r in d.get("ran") or []:
            s = out.setdefault(r["agent_id"], {"runs": 0, "no_data": 0})
            s["runs"] += 1
            s["no_data"] += int(r.get("status") == "no_data")
    return out


def new_unit(kind: str, uid: str, now: int) -> dict:
    return {"kind": kind, "id": uid, "level": "alerta", "active": True, "bad": 0, "good": 0,
            "level_since": now, "reason": "", "history": []}


def _log(u: dict, now: int, what: str, reason: str, changes: list[dict], **kw) -> None:
    ev = {"t": now, "unit": f"{u['kind']}:{u['id']}", "what": what, "reason": reason, **kw}
    u["history"] = (u["history"] + [ev])[-HISTORY_MAX:]
    changes.append(ev)


def _observe(u: dict, bad: bool, reason: str, now: int, changes: list[dict]) -> None:
    """Cuenta revisiones sanas/malas seguidas y aplica desactivación o reactivación."""
    if bad:
        u["bad"], u["good"] = u["bad"] + 1, 0
        if u["active"] and u["bad"] >= DEACTIVATE_AFTER:
            u.update(active=False, reason=reason)
            if u["level"] != "alerta":
                _log(u, now, "bajada", reason, changes, frm=u["level"], to="alerta")
                u.update(level="alerta", level_since=now)
            _log(u, now, "desactivada", reason, changes)
    else:
        u["good"], u["bad"] = u["good"] + 1, 0
        if not u["active"] and u["good"] >= REACTIVATE_AFTER:
            u.update(active=True, reason="", level="alerta", level_since=now)
            _log(u, now, "reactivada", f"{REACTIVATE_AFTER} revisiones sanas seguidas", changes)


def blockers(u: Mapping, cls: Mapping | None, health: Mapping, gates: Mapping, now: int
             ) -> list[str]:
    """Qué impide subir esta clase al nivel siguiente (vacío = sube sola)."""
    lvl = u["level"]
    if lvl == "ejecucion_limitada":
        return ["ya está en el último nivel"]
    if lvl == "papel":
        return [NEVER_AUTO]
    out = [] if u["active"] else [f"desactivada: {u['reason']}"]
    t101 = (gates.get("t101") or {})
    cell = (t101.get("cells") or {}).get(u["id"]) if t101.get("available") else None
    if lvl == "alerta":
        if u["good"] < PROMOTE_MIN_OK_CHECKS:
            out.append(f"lleva {u['good']} de {PROMOTE_MIN_OK_CHECKS} revisiones sanas seguidas")
        rk = health["scanner"]["ranking"]
        if rk.get("threshold_status") != "vigente":
            out.append("el umbral del placebo (T95) no está vigente")
        elif not (cls or {}).get("above_threshold"):
            out.append("ninguna candidata de la clase supera el umbral del azar")
        if cell is None:
            out.append("falta su celda en la matriz agente × clase de T101")
        elif cell not in ("publicable", "en observación"):
            out.append(f"T101 la marcó «{cell}»")
        if not gates.get("t96_built"):
            out.append("la cartera multiactivo (T96) no existe todavía")
        return out
    # simulación → papel
    if cell != "publicable":
        out.append("T101 no la publicó como candidata validada")
    days = (now - int(u["level_since"])) / DAY_MS
    if days < SIM_MIN_DAYS:
        out.append(f"lleva {days:.0f} de {SIM_MIN_DAYS} días en simulación")
    matured = health["scanner"]["ranking"].get("matured") or 0
    if matured < SIM_MIN_MATURED:
        out.append(f"{matured} de {SIM_MIN_MATURED} resultados maduros hacia delante")
    if not gates.get("t103_built"):
        out.append("el adaptador de papel (T103) no existe todavía")
    return out


def evaluate(prev: Mapping | None, health: Mapping, view: Mapping | None, gates: Mapping,
             now: int) -> tuple[dict, list[dict]]:
    """Una revisión: (estado nuevo, cambios de esta vuelta). No muta `prev`."""
    st = copy.deepcopy(dict(prev)) if prev else {"version": ROLLOUT_VERSION, "units": {}}
    units: dict[str, dict] = st.setdefault("units", {})
    changes: list[dict] = []
    for c in health["classes"]:
        key = f"class:{c['asset_class']}"
        if c["plan"] not in (ENABLED, WATCH) or (key not in units and not c["n_scored"]
                                                 and not c["alerting"]):
            continue
        u = units.setdefault(key, new_unit("class", c["asset_class"], now))
        _observe(u, c["state"] in BAD, "; ".join(c["reasons"]) or c["state"], now, changes)
    for aid, s in agent_stats(view).items():
        if s["runs"] < AGENT_MIN_RUNS:
            continue
        u = units.setdefault(f"agent:{aid}", new_unit("agent", aid, now))
        share = s["no_data"] / s["runs"]
        _observe(u, share >= AGENT_BAD_SHARE,
                 f"sin datos en {s['no_data']} de {s['runs']} instrumentos", now, changes)
    by_cls = {c["asset_class"]: c for c in health["classes"]}
    for u in units.values():
        if u["kind"] != "class":
            u["next"] = ["su nivel lo marca la clase de cada instrumento"]
            continue
        u["next"] = blockers(u, by_cls.get(u["id"]), health, gates, now)
        if not u["next"] and u["level"] in ("alerta", "simulacion"):
            to = LEVELS[LEVELS.index(u["level"]) + 1]
            _log(u, now, "promovida", "cumple todos los criterios", changes, frm=u["level"], to=to)
            u.update(level=to, level_since=now, good=0)
            u["next"] = blockers(u, by_cls.get(u["id"]), health, gates, now)
    st.update(version=ROLLOUT_VERSION, updated_at=now)
    return st, changes


def shadow_reason(opp: Mapping, state: Mapping | None) -> str | None:
    """Por qué una candidata va a la sombra (None = se ve): clase inactiva o apoyada sobre todo
    (≥ `SHADOW_SHARE` del peso de su síntesis) por agentes desactivados."""
    units = (state or {}).get("units", {})
    cu = units.get(f"class:{opp['asset_class']}")
    if cu and not cu["active"]:
        return f"clase desactivada: {cu['reason']}"
    contrib = (opp.get("synthesis") or {}).get("contributions") or {}
    total = sum(abs(v) for v in contrib.values())
    off = [a for a in contrib if (units.get(f"agent:{a}") or {}).get("active") is False]
    if off and total > 0 and sum(abs(contrib[a]) for a in off) / total >= SHADOW_SHARE:
        return "apoyada sobre todo por agentes desactivados: " + ", ".join(sorted(off))
    return None


def level_of(asset_class: str, state: Mapping | None) -> dict:
    u = ((state or {}).get("units") or {}).get(f"class:{asset_class}")
    if not u:
        return {"level": "alerta", "active": True, "next": ["sin revisiones todavía"]}
    return {"level": u["level"], "active": u["active"], "reason": u["reason"],
            "next": u.get("next", [])}
