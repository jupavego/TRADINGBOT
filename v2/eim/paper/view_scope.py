"""Alcance de una vista del bróker simulado (T118): qué tramo ve, su techo y qué deja fuera.

La vista se rehace desde los contextos que hay HOY en este almacén. Eso no es «toda la historia»
cuando el libro fijo guarda operaciones en vivo que la vista ya no reproduce (u otro PnL para las
mismas), o cuando una instantánea anterior contaba más operaciones de un perfil. Cada caso es un
hueco con su porqué; sin huecos la vista es `complete`. Funciones puras sobre el resumen.
"""

from __future__ import annotations

from datetime import UTC, datetime

LEDGER_WHY = ("la vista se recalcula con las reglas, el capital y los contextos de ahora; el libro "
              "fijo conserva cada operación en vivo tal como se cerró")
CEILING_WHY = ("cada idea que la sombra no rechazó da como mucho una operación por perfil: ningún "
               "recuento de esta vista puede pasar de ahí")


def _day(t: int | None) -> str:
    return datetime.fromtimestamp(t / 1000, UTC).strftime("%Y-%m-%d") if t else "—"


def prior_why(body: dict | None, pid: str, coverage: dict, versions: dict) -> str:
    """Por qué una instantánea anterior contaba más operaciones que esta vista."""
    if body is None:
        return "esa instantánea ya no se puede leer en este almacén"
    why = []
    c0 = body.get("coverage") or {}
    if (c0.get("contexts"), c0.get("from"), c0.get("to")) != (
            coverage.get("contexts"), coverage.get("from"), coverage.get("to")):
        why.append(f"el almacén tenía {c0.get('contexts')} contextos ({_day(c0.get('from'))} → "
                   f"{_day(c0.get('to'))}) y hoy tiene {coverage.get('contexts')} "
                   f"({_day(coverage.get('from'))} → {_day(coverage.get('to'))})")
    v0 = body.get("versions") or {}
    if (v0.get("profiles") or {}).get(pid) != versions["profiles"].get(pid):
        why.append("cambiaron los parámetros del perfil")
    if any(v0.get(k) != versions.get(k) for k in ("exec", "policy", "code")):
        why.append("cambió la mecánica, la política o el código")
    return "; ".join(why) or ("mismo almacén y mismas versiones: el recálculo no debería contar "
                              "menos (revisar)")


def scope_of(payload: dict, ceiling: int, prior: dict[str, dict], bodies: dict[str, dict],
             versions: dict) -> dict:
    """Alcance declarado de la vista: tramo, techo, huecos con su porqué y si abarca todo.

    `prior` = por perfil, la instantánea anterior que más contaba (`snapshot.largest`); `bodies`
    = el contenido de esas instantáneas (solo de las que contaban más que ahora)."""
    cov, gaps = payload["coverage"], []
    for p in payload["profiles"]:
        led = p["counts"].get("ledger")
        if led and not led["match"]:
            gaps.append({"kind": "libro_fijo", "profile": p["id"], "name": p["name"],
                         "rows": led["rows"], "view_live": led["view_live"],
                         "outside": led["outside"], "differ": led["differ"],
                         "from": led["outside_from"], "to": led["outside_to"],
                         "why": LEDGER_WHY})
        pr = prior.get(p["id"])
        if pr and pr["n"] > p["n_closed"]:
            gaps.append({"kind": "instantanea", "profile": p["id"], "name": p["name"],
                         "n": pr["n"], "now": p["n_closed"], "id": pr["id"],
                         "computed": pr["computed"],
                         "why": prior_why(bodies.get(pr["id"]), p["id"], cov, versions)})
    froms = [p["counts"]["from"] for p in payload["profiles"] if p["counts"]["from"]]
    tos = [p["counts"]["to"] for p in payload["profiles"] if p["counts"]["to"]]
    return {"kind": "almacen", "from": cov["from"], "to": cov["to"],
            "closes_from": min(froms, default=None), "closes_to": max(tos, default=None),
            "contexts": cov["contexts"], "origins": cov["origins"],
            "ceiling": ceiling, "ceiling_why": CEILING_WHY,
            "complete": not gaps, "gaps": gaps}
