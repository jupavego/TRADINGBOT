"""Objetivo de selección pre-registrado (E2 de §8 de `PLAN/notas/T129_sl_dinamico.md`).

§5.3 decía «los parámetros se eligen solo en el tramo de ajuste», pero no QUÉ se maximiza, y lo que
se optimiza es lo que se obtiene (Sutton y Barto §17.4). Aquí queda fijado:

1. **Factible:** dentro del tramo de ajuste, el CVaR 95 % y el drawdown máximo no son peores que
   los de la base (M0) en ESE mismo tramo. Una variante que mejora la esperanza empeorando la cola
   no entra, por buena que parezca su media.
2. **Objetivo:** entre las factibles, el E[R] **neto de costos**.
3. **Centro de la meseta, no el pico:** una variante es candidata si (a) sus vecinos a ±1 paso
   conservan al menos `plateau_keep` (0,7) de su valor y (b) ella misma conserva al menos
   `plateau_keep` del mejor valor factible del tramo. Entre las candidatas gana la que maximiza el
   **mínimo** de su entorno (ella y sus vecinos). (a) descarta el pico aislado; (b) descarta el
   punto malo que solo cumple (a) porque su vecino es bueno —sin (b) la regla elegiría justo la
   peor variante de la rejilla—; y el maximin prefiere la meseta ancha al filo.

Puro: sin red y sin disco. No decide nada por sí mismo; T134 es quien decide.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

PLATEAU_KEEP = 0.7


@dataclass(frozen=True)
class Score:
    """Lo que el objetivo de selección mira de una variante en un tramo de ajuste."""

    variant: str
    expectancy_r: float | None
    cvar95_r: float | None
    max_dd_r: float | None
    n: int
    feasible: bool
    why: str

    def to_json(self) -> dict:
        return {"variant": self.variant, "expectancy_r": self.expectancy_r,
                "cvar95_r": self.cvar95_r, "max_dd_r": self.max_dd_r, "n": self.n,
                "feasible": self.feasible, "why": self.why}


def score_of(variant: str, m: Mapping, base: Mapping, min_trades: int = 1) -> Score:
    """Puntúa una variante con las métricas de su tramo de ajuste frente a la base del tramo."""
    n = int(m.get("n") or 0)
    exp, cvar, dd = m.get("expectancy_r"), m.get("cvar95_r"), m.get("max_dd_r")
    b_cvar, b_dd = base.get("cvar95_r"), base.get("max_dd_r")
    if n < min_trades or exp is None:
        return Score(variant, exp, cvar, dd, n, False, f"muestra insuficiente ({n})")
    bad = []
    if cvar is not None and b_cvar is not None and cvar < b_cvar:
        bad.append(f"CVaR 95 % {cvar:+.3f} peor que la base {b_cvar:+.3f}")
    if dd is not None and b_dd is not None and dd > b_dd:
        bad.append(f"DD máximo {dd:.3f} R peor que la base {b_dd:.3f} R")
    return Score(variant, exp, cvar, dd, n, not bad,
                 "; ".join(bad) if bad else "cumple las restricciones del tramo")


def plateau_ok(scores: Mapping[str, Score], neighbours: Mapping[str, Sequence[str]],
               keep: float = PLATEAU_KEEP) -> dict[str, bool]:
    """¿Los vecinos a ±1 paso conservan ≥ `keep` del valor? Sin vecinos declarados: no es meseta."""
    out = {}
    for k, s in scores.items():
        ns = [scores[x].expectancy_r for x in neighbours.get(k, ())
              if x in scores and scores[x].expectancy_r is not None]
        out[k] = bool(ns) and s.expectancy_r is not None and s.expectancy_r > 0 and all(
            v >= keep * s.expectancy_r for v in ns)
    return out


def choose(scores: Mapping[str, Score], neighbours: Mapping[str, Sequence[str]],
           keep: float = PLATEAU_KEEP) -> dict:
    """Variante elegida en el tramo de ajuste, con el motivo. `winner` es None si ninguna cumple."""
    feasible = {k: s for k, s in scores.items() if s.feasible}
    plat = plateau_ok(feasible, neighbours, keep)
    best = max((s.expectancy_r for s in feasible.values() if s.expectancy_r is not None),
               default=None)
    ok = [k for k, v in plat.items() if v and best is not None
          and (feasible[k].expectancy_r or -1e9) >= keep * best]
    if not ok:
        return {"winner": None, "reason": "ninguna variante factible forma meseta competitiva",
                "feasible": sorted(feasible), "plateau": plat,
                "best_unconstrained": max(scores, key=lambda k: scores[k].expectancy_r or -1e9,
                                          default=None)}
    def worst(k: str) -> float:
        vals = [feasible[k].expectancy_r] + [feasible[x].expectancy_r for x in neighbours.get(k, ())
                                             if x in feasible]
        return min(v for v in vals if v is not None)

    winner = max(ok, key=lambda k: (worst(k), feasible[k].expectancy_r or -1e9, k))
    return {"winner": winner, "reason": "centro de la meseta (máximo del mínimo de su entorno)",
            "neighbourhood_min": worst(winner), "expectancy_r": feasible[winner].expectancy_r,
            "feasible": sorted(feasible), "plateau": plat}


def neighbours_of(values: Sequence[float], name: str = "{v:g}") -> dict[str, list[str]]:
    """Vecinos a ±1 paso de una rejilla de un solo parámetro ordenada (el caso de M0 y M8)."""
    keys = [name.format(v=v) for v in values]
    out: dict[str, list[str]] = {}
    for i, k in enumerate(keys):
        out[k] = [keys[j] for j in (i - 1, i + 1) if 0 <= j < len(keys)]
    return out
