"""Espacio de búsqueda acotado y justificado, y construcción de parámetros desde un trial.

Correspondencia con EIM-VRM-001 cap. 4 (el VRM se escribió para el BRM/IRM legado):
- C-1 (umbrales θ) → umbrales de decisión del plan: sesgo y confianza mínimos, R:R mínimo,
  distancias de SL en ATR.
- C-2 (pesos W, suma 1, cada peso ≥ 0.05) → peso relativo structure/levels en la síntesis
  (con dos agentes votantes es un solo grado de libertad) y penalización por desacuerdo.
- C-3 (modificadores de confianza, isotónica) → NO se calibra aquí: el plan no usa la confianza
  como probabilidad; queda en BACKLOG.

Rangos: centrados en el valor vigente, sin salir de lo que la especificación del plan admite
(R:R ≥ 1, SL tras el nivel estructural con colchón positivo, umbrales en 0..1).
"""

from __future__ import annotations

from dataclasses import dataclass

from eim.agents.plan import PlanParams
from eim.synthesis import SynthesisParams


@dataclass(frozen=True)
class Dim:
    name: str             # "plan.<campo>" | "synth.<campo>" | "strategy.tp_index"
    low: float
    high: float
    kind: str = "float"   # float | int | cat
    why: str = ""


SPACE: list[Dim] = [
    Dim("plan.min_abs_bias", 0.05, 0.40, why="θ: sesgo combinado mínimo (0.15 vigente)"),
    Dim("plan.min_confidence", 0.15, 0.50, why="θ: confianza mínima (0.30 vigente)"),
    Dim("plan.min_rr", 1.0, 3.0, why="θ: R:R mínimo a TP1; <1 contradice el plan"),
    Dim("plan.sl_buffer_atr", 0.2, 1.0, why="colchón del SL tras el nivel (0.5 ATR vigente)"),
    Dim("plan.max_sl_atr", 2.5, 8.0, why="SL más lejano admitido (5 ATR vigente)"),
    Dim("plan.expiry_bars", 24, 96, "int", why="vigencia del plan: 1–4 días en 1h"),
    Dim("synth.w_structure", 0.5, 2.0, why="W: peso structure/levels (1 vigente; ≥0.05 VRM)"),
    Dim("synth.disagree_penalty", 0.3, 0.8, why="factor de confianza ante desacuerdo (0.5)"),
    Dim("strategy.tp_index", 0, 1, "cat", why="salida en TP1 o TP2"),
]


def defaults() -> dict[str, float]:
    """Valores vigentes (los de `params.py`) en el mismo espacio."""
    pp, sp = PlanParams(), SynthesisParams()
    out: dict[str, float] = {}
    for d in SPACE:
        grp, key = d.name.split(".", 1)
        if grp == "plan":
            out[d.name] = getattr(pp, key)
        elif key == "w_structure":
            out[d.name] = sp.weights.get("structure", 1.0)
        elif grp == "synth":
            out[d.name] = getattr(sp, key)
        else:
            out[d.name] = 0
    return out


def suggest(trial) -> dict[str, float]:
    """Valores de un trial de optuna dentro de `SPACE`."""
    out: dict[str, float] = {}
    for d in SPACE:
        if d.kind == "int":
            out[d.name] = trial.suggest_int(d.name, int(d.low), int(d.high))
        elif d.kind == "cat":
            out[d.name] = trial.suggest_categorical(d.name, list(range(int(d.low),
                                                                       int(d.high) + 1)))
        else:
            out[d.name] = trial.suggest_float(d.name, d.low, d.high)
    return out


def build(values: dict[str, float]) -> tuple[PlanParams, SynthesisParams, int]:
    """(PlanParams, SynthesisParams, tp_index) a partir de valores del espacio."""
    plan: dict = {}
    synth: dict = {}
    tp_index = 0
    for name, v in values.items():
        grp, key = name.split(".", 1)
        if grp == "plan":
            plan[key] = int(round(v)) if isinstance(PlanParams.model_fields[key].default,
                                                    int) else float(v)
        elif key == "w_structure":
            synth["weights"] = {"structure": float(v), "levels": 1.0}
        elif grp == "synth":
            synth[key] = float(v)
        else:
            tp_index = int(v)
    return PlanParams(**plan), SynthesisParams(**synth), tp_index


def n_changed(values: dict[str, float], base: dict[str, float], tol: float = 0.10) -> int:
    """Parámetros que se apartan del vigente más de `tol` (relativo; categóricos: distinto)."""
    k = 0
    for d in SPACE:
        a, b = values[d.name], base[d.name]
        if d.kind == "cat":
            k += a != b
        else:
            k += abs(a - b) > tol * max(abs(b), 1e-9) + 1e-12
    return k


def perturbations(values: dict[str, float], rel: float = 0.10) -> list[tuple[str, dict]]:
    """Copias con cada parámetro numérico a ±`rel` (recortado al rango). Categóricos no."""
    out = []
    for d in SPACE:
        if d.kind == "cat":
            continue
        for sgn in (-1, 1):
            v = values[d.name] * (1 + sgn * rel)
            v = min(d.high, max(d.low, v))
            if d.kind == "int":
                v = int(round(v))
            if v != values[d.name]:
                out.append((f"{d.name}{'+' if sgn > 0 else '−'}{int(rel * 100)}%",
                            {**values, d.name: v}))
    return out
