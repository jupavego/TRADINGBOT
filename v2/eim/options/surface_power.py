"""Potencia a priori de T214: cuántos días de tomas hacen falta antes de evaluar (puro).

Método de T163/T165 (`validation/power.n_needed`): para detectar con un contraste unilateral
una mejora media de QLIKE `δ` cuando la diferencia diaria de pérdidas tiene desviación `s`,

    n = κ · ((z_{1−α/m} + z_{potencia}) · s / δ)²

con `m` el tamaño de la familia de Holm (el primer rechazo de Holm exige p < α/m) y `κ ≥ 1` la
inflación por dependencia serie (Newey-West con el bloque de Politis-White, como T163). Antes
de evaluar hay `warmup` días válidos de calentamiento de las regresiones, que no puntúan.

Todo es aritmética anterior a cualquier resultado: `s` sale de cifras ya publicadas (T165) o,
en la revisión de potencia, solo de la dispersión del tramo de calentamiento, nunca de su media.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import NormalDist

from eim.validation.power import n_needed

ALPHA, POWER = 0.05, 0.80
WARMUP_DAYS = 250                 # calentamiento de las regresiones (el de T165)
A2_QLIKE_T165 = 0.29450           # QLIKE de A2 en 2022-2026 (reports/t165_dvol.md)
DELTA_REL = 0.05                  # mejora mínima que se quiere poder detectar: 5 % de A2
#: s de la diferencia diaria de QLIKE publicadas en T165 (modelo anidado frente a su base).
S_PRIOR = {"A1 vs M1 (un regresor más)": 0.2731, "A2 vs M1 (dos regresores más)": 0.2405,
           "A3 vs M1 (combinación anidada)": 0.1242}
S_CENTRAL = 0.2405
FAMILY_T95 = 1138                 # familia del escáner al 2026-11-26 (841 de T49 + 297)
N_ATTEMPTS = 3                    # C1 estructura temporal, C2 sesgo 25Δ, C3 prima por plazo
START = date(2026, 11, 28)        # primer día con toma de las 23 h UTC del día anterior
CAP = date(2029, 11, 27)          # tope: 3 años de tomas; más allá, SIN POTENCIA


def delta_min(rel: float = DELTA_REL, base: float = A2_QLIKE_T165) -> float:
    return rel * base


def days_needed(s: float, delta: float, family: int, kappa: float = 1.0,
                alpha: float = ALPHA, power: float = POWER) -> float:
    """Días válidos puntuados para detectar `delta` con Holm sobre una familia de `family`."""
    return kappa * n_needed(delta, s, alpha / family, power)


def z_holm(family: int, alpha: float = ALPHA, power: float = POWER) -> float:
    return NormalDist().inv_cdf(1 - alpha / family) + NormalDist().inv_cdf(power)


def first_evaluation(n_scored: float, start: date = START, warmup: int = WARMUP_DAYS,
                     valid_rate: float = 1.0) -> date | None:
    """Fecha estimada en que se cumplen `warmup + n_scored` días válidos (None si infinito)."""
    if not math.isfinite(n_scored) or valid_rate <= 0:
        return None
    return start + timedelta(days=math.ceil((warmup + n_scored) / valid_rate))


def max_s_for_cap(delta: float, family: int, kappa: float = 1.0, start: date = START,
                  cap: date = CAP, warmup: int = WARMUP_DAYS) -> float:
    """La mayor `s` con la que la evaluación cabe antes del tope (todos los días válidos)."""
    scored = (cap - start).days - warmup
    return 0.0 if scored <= 0 else delta * math.sqrt(scored / kappa) / z_holm(family)


@dataclass(frozen=True)
class PowerCase:
    label: str
    s: float
    family: int
    rel: float
    days: float
    first_eval: date | None

    @property
    def before_cap(self) -> bool:
        return self.first_eval is not None and self.first_eval <= CAP

    def to_json(self) -> dict:
        return {"label": self.label, "s": self.s, "family": self.family, "delta_rel": self.rel,
                "delta": round(delta_min(self.rel), 5), "days_scored": math.ceil(self.days),
                "first_evaluation": self.first_eval.isoformat() if self.first_eval else None,
                "before_cap": self.before_cap}


def power_table(families: tuple[int, ...] = (N_ATTEMPTS, FAMILY_T95 + N_ATTEMPTS),
                rels: tuple[float, ...] = (0.03, DELTA_REL, 0.10)) -> list[PowerCase]:
    """Curva a priori: cada `s` de T165 × tamaño de familia × mejora relativa."""
    out = []
    for label, s in S_PRIOR.items():
        for fam in families:
            for rel in rels:
                n = days_needed(s, delta_min(rel), fam)
                out.append(PowerCase(label, s, fam, rel, n, first_evaluation(n)))
    return out
