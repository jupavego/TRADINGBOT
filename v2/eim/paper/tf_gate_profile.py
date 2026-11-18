"""Puerta de costo por perfil y marco (T179, ◆ del usuario 2026-11-17). Puro salvo `load`/`save`.

La puerta de T143 (3) cierra un marco **entero** con un solo costo, medido en la sombra que
algún perfil aceptaría. Los perfiles tienen vetos de costo distintos (conservador 0,12 R,
moderado y PPP 0,15, agresivo 0,20), así que en 15 m el agresivo pagaba 0,180 R vividos y el
moderado 0,140, y la puerta, con un número, no podía decidir por los dos. Aquí cada perfil se
juzga con la sombra que **él** aceptaría, corregida con su propio libro (`tf_calib`, aditiva).

**Un marco cerrado no abre posiciones nuevas; no reescribe lo vivido.** La puerta de T143 filtra
toda la sombra, así que al cerrarse un marco el libro recalculado perdería también lo ya cerrado
y lo que está abierto. Aquí, cuando un perfil@marco se cierra, se anota desde qué instante
(`[desde, hasta]`, `hasta` None mientras siga cerrado). Solo se bloquean las ideas de ese tramo:
lo anterior queda como se vivió y lo posterior a la reapertura vuelve a entrar. Los tramos se
guardan en disco (`data/paper/tf_gate_<variante>.json`) para que un reinicio no los olvide.

Con menos de `tf_cost_min_n` operaciones de sombra del perfil en el marco se usa la línea base de
T136 (que ya es costo vivido, del banco), como en la puerta de T143.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from eim.paper import tf_calib, tf_gate
from eim.paper.engine import Outcome


def decide(tfs: Sequence[str], outcomes: Sequence[Outcome], ep, profiles: Sequence,
           cor: Mapping[str, dict]) -> list[dict]:
    """Una fila por perfil y marco: costo calibrado, de dónde sale y si el perfil opera ahí."""
    rows = []
    for p in profiles:
        meas = tf_gate.cost_by_tf(tf_gate.takeable(outcomes, [p]))
        for tf in tfs:
            c, n = meas.get(tf, (None, 0))
            d, dsrc = tf_calib.correction_for(cor, p.id, tf)
            if c is not None and n >= ep.tf_cost_min_n:
                cost, src = c + d, f"sombra de {p.id} ({n} operaciones) {d:+.3f} R ({dsrc})"
            else:
                cost = tf_gate.BASELINE_COST_R.get(tf)
                src = f"T136 (banco de T131); la sombra de {p.id} lleva {n} de {ep.tf_cost_min_n}"
            ok = ep.tf_max_cost_r is None or cost is None or cost < ep.tf_max_cost_r
            rows.append({"profile": p.id, "timeframe": tf,
                         "cost_r": None if cost is None else round(cost, 4),
                         "shadow_cost_r": None if c is None else round(c, 4), "correction_r": d,
                         "source": src, "max_cost_r": ep.tf_max_cost_r, "admitted": ok})
    return rows


def key(symbol: str, profile: str, tf: str) -> str:
    return f"{symbol}|{profile}@{tf}"


def update(closed: Mapping[str, list], rows: Iterable[Mapping], symbol: str,
           at: int) -> dict[str, list[list]]:
    """Abre un tramo cerrado al cerrarse un perfil@marco y lo termina al reabrirse, en `at`."""
    out = {k: [list(x) for x in v] for k, v in closed.items()}
    for r in rows:
        iv = out.setdefault(key(symbol, r["profile"], r["timeframe"]), [])
        is_open = bool(iv) and iv[-1][1] is None
        if not r["admitted"] and not is_open:
            iv.append([at, None])
        elif r["admitted"] and is_open:
            iv[-1][1] = at
    return {k: v for k, v in out.items() if v}


def blocked(closed: Mapping[str, list], symbol: str, profile: str, o: Outcome) -> bool:
    """¿La idea cae en un tramo en que su perfil@marco estaba cerrado?"""
    for a, b in closed.get(key(symbol, profile, o.idea.timeframe), ()):
        if o.idea.t >= a and (b is None or o.idea.t < b):
            return True
    return False


def tradable(closed: Mapping[str, list], symbol: str, profiles: Sequence,
             outcomes: Sequence[Outcome]) -> dict[str, list[Outcome]]:
    """Lo que cada perfil puede tomar. La sombra no se filtra nunca (la miden todos)."""
    return {p.id: [o for o in outcomes if not blocked(closed, symbol, p.id, o)] for p in profiles}


def load(path: Path) -> dict[str, list]:
    """Tramos guardados; un archivo que falta o no se lee es «nada cerrado», nunca un error."""
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): [list(x) for x in v] for k, v in d.items() if isinstance(v, list)}


def save(path: Path, closed: Mapping[str, list]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(closed, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp.replace(p)
