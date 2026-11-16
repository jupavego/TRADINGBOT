"""Umbrales de la ficha T169, banda medida, descartes mecánicos y días hasta el veredicto. Puro.

Los umbrales son los de `PLAN/T169.md` («Entregables 3»), fijados antes de correr, **por banda de
horizonte** (nota de T167 §3, «Horizontes»): scalping ≥ 20 operaciones al mes, intradía ≥ 8, tres
días ≥ 5 y semanal en posición ≥ 30 % de los días; costo medio ≤ 0,3 R (V6 de T49, el mismo valor
que la puerta de la cantera); y sin anticipación. Nada de esto mira si el prospecto gana.

Los días hasta el veredicto usan `min_track_record` de T161 con una σ **supuesta** de 1 R por
operación (medirla exigiría calcular R en la historia), asimetría 0 y curtosis 3.
"""

from __future__ import annotations

import math
from statistics import NormalDist

from scipy.stats import chi2

from eim.nursery.params import V6_MAX_COST_R
from eim.validation.power import min_track_record

MIN_OPS_MONTH = {"scalping": 20.0, "intradia": 8.0, "tres_dias": 5.0}
MIN_POS_DAYS_FRAC = 0.30          # semanal: en posición ≥ 30 % de los días
MAX_COST_R = V6_MAX_COST_R        # 0,3 R
TERM_DAYS = 182                   # plazo de la fase: 6 meses (nota §10)
FIRST_TEAM_OPS, FIRST_TEAM_POS_DAYS = 100, 120
MIN_CLOSED_FOR_BAND = 10
SIGMA_R, SKEW, KURT = 1.0, 0.0, 3.0
MUS = (0.10, 0.25)
FAMILY = 50                       # techo de la familia: α 0,05/50 → z ≈ 3,09
ALPHAS = {"alfa_0_05": 0.05, "familia": 0.05 / FAMILY}
SCALP_MAX_H, INTRADAY_MAX_H, THREE_DAYS_MAX_H = 2.0, 24.0, 120.0
BANDS = ("scalping", "intradia", "tres_dias", "semanal")


def band_of(hold_h: float) -> str:
    """Banda por tenencia mediana: ≤ 2 h, < 24 h, ≤ 5 días, más."""
    if hold_h <= SCALP_MAX_H:
        return "scalping"
    if hold_h < INTRADAY_MAX_H:
        return "intradia"
    return "tres_dias" if hold_h <= THREE_DAYS_MAX_H else "semanal"


def poisson_ci(n: int, alpha: float = 0.05) -> tuple[float, float]:
    """IC exacto (Garwood) de un conteo de Poisson."""
    lo = 0.0 if n == 0 else float(chi2.ppf(alpha / 2, 2 * n) / 2)
    return lo, float(chi2.ppf(1 - alpha / 2, 2 * n + 2) / 2)


def z_of(alpha: float) -> float:
    return NormalDist().inv_cdf(1 - alpha)


def ops_needed(mu: float, alpha: float) -> float:
    return min_track_record(mu / SIGMA_R, 0.0, SKEW, KURT, alpha)


def _days_to_verdict(ops_per_day: float, hold_days: float | None, band: str) -> dict:
    out = {}
    for mu in MUS:
        for name, a in ALPHAS.items():
            need = ops_needed(mu, a)
            key = f"mu_{mu:.2f}".replace(".", "_") + f"_{name}"
            row = {"ops": math.ceil(need),
                   "days": round(need / ops_per_day, 1) if ops_per_day > 0 else None}
            if band == "semanal" and hold_days:
                row["pos_days"] = round(need * hold_days, 1)
            out[key] = row
    return out


def _spread_ci(rates: list[float]) -> tuple[float, float] | None:
    if len(rates) < 2:
        return None
    m = sum(rates) / len(rates)
    sd = math.sqrt(sum((x - m) ** 2 for x in rates) / (len(rates) - 1))
    half = 1.96 * sd / math.sqrt(len(rates))
    return m - half, m + half


def judge(declared: str, ph: dict, anticipation: bool) -> dict:
    """Veredicto mecánico de un prospecto con historia a partir de su física."""
    reasons: list[str] = []
    edge: list[str] = []
    hold = ph.get("hold_h_median")
    measured = band_of(hold) if hold is not None and ph["closed"] >= MIN_CLOSED_FOR_BAND \
        else None
    band = measured or declared
    days, n = ph["days"], ph["filled"]
    if band == "semanal":
        frac = ph["pos_days_frac"]
        if frac < MIN_POS_DAYS_FRAC:
            reasons.append(f"semanal en posición el {frac:.0%} de los días (< 30 %)")
        ci = _spread_ci(ph.get("pos_days_by_block") or [])
        if ci and ci[0] <= MIN_POS_DAYS_FRAC <= ci[1]:
            edge.append("días en posición")
    else:
        need = MIN_OPS_MONTH[band]
        if ph["ops_month"] < need:
            reasons.append(f"{band}: {ph['ops_month']:.1f} operaciones al mes (< {need:g})")
        lo, hi = poisson_ci(n)
        if days and lo / days * 30 <= need <= hi / days * 30:
            edge.append("cadencia")
    cost, sd, nc = ph.get("cost_r_mean"), ph.get("cost_r_sd"), ph["closed"]
    if cost is not None and cost > MAX_COST_R:
        reasons.append(f"costo medio {cost:.3f} R (> {MAX_COST_R:g} R, V6 de T49)")
    if cost is not None and sd and nc > 1 and abs(cost - MAX_COST_R) <= 1.96 * sd / math.sqrt(nc):
        edge.append("costo")
    if anticipation:
        reasons.append("anticipación: sus ideas cambian al truncar los datos")
    per_day = n / days if days else 0.0
    hold_days = hold / 24 if hold is not None else None
    if band == "semanal":
        expected = ph["pos_days_frac"] * TERM_DAYS
        no_first = expected < FIRST_TEAM_POS_DAYS
    else:
        expected = per_day * TERM_DAYS
        no_first = expected < FIRST_TEAM_OPS
    return {
        "declared_band": declared, "measured_band": measured, "band": band,
        "reassigned": measured is not None and measured != declared,
        "discarded": bool(reasons), "reasons": reasons, "borderline": edge,
        "expected_in_term": round(expected, 1),
        "no_first_team": (not reasons) and no_first,
        "days_to_verdict": None if reasons else _days_to_verdict(per_day, hold_days, band),
    }


def mintrl_table() -> list[dict]:
    """Operaciones necesarias por hipótesis (la misma para todos: σ supuesta común)."""
    return [{"mu_r": mu, "alpha": a, "z": round(z_of(a), 3), "ops": math.ceil(ops_needed(mu, a))}
            for mu in MUS for a in ALPHAS.values()]
