"""Agentes de prueba de renta fija: curva y carry (T100). Modo ANÁLISIS, sin registrar.

Son la «una implementación de prueba por familia» que pedía T100, sobre la única fuente de
curva aprobada y gratuita (Tesoro de EE. UU., ◆ T88). **No están en el registro de agentes**,
no votan en la síntesis y no tocan el plan, el riesgo ni el bróker: sirven para medir si la
familia merece una clase (◆ de T100). Su especificación completa —`requires`, costos y
validación— está en `v2/reports/fixed_income_options_viability.md` §3.

- `curve_state`: nivel, pendiente y curvatura empíricas (Diebold–Li: 10 años, 10a − 3m y
  2·2a − 3m − 10a), 2s10s, inversión y la calidad del ajuste Svensson/NS que se usa para
  interpolar. Informante: sin sesgo.
- `carry_state`: carry + roll-down de 3 meses de un cupón cero a 10 años con la curva quieta,
  menos la financiación (la letra del mismo horizonte, como aproximación declarada), frente a
  la volatilidad medida del rendimiento → «Sharpe ex ante» y un sesgo sobre la **duración**.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from eim.fixed_income.carry import zero_coupon
from eim.fixed_income.curve import (
    TAU_GRID,
    fit_nelson_siegel,
    fit_svensson,
    linear,
    par_to_zero,
)

MODE = "ANÁLISIS"
MAX_FIT_RMSE_BP = 5.0          # por encima, el ajuste no describe la curva: se avisa
MIN_HISTORY = 61               # 60 variaciones diarias para la volatilidad
TRADING_DAYS_YEAR = 252


@dataclass
class ProtoReport:
    """Forma mínima de un informe de agente (como `AgentReport`, pero sin registrar)."""

    family: str
    as_of: str | None
    source: str
    status: str                                  # "ok" | "degradado" | "no_data"
    bias: float | None = None                    # −1..+1 sobre el objeto declarado
    bias_on: str = ""
    confidence: float = 0.0
    horizon: str = ""
    metrics: dict[str, float | None] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    mode: str = MODE


def _pct(x: float | None) -> float | None:
    return None if x is None else round(x, 4)


def curve_state(tenors: Sequence[float], par_pct: Sequence[float], as_of: str | None,
                source: str) -> ProtoReport:
    """Estado de la curva par de un día (plazos en años, rendimientos en %)."""
    rep = ProtoReport("curva", as_of, source, "ok", horizon="estado del día")
    if len(tenors) < 6:
        rep.status = "no_data"
        rep.warnings.append(f"solo {len(tenors)} plazos: hacen falta ≥ 6 para Svensson")
        return rep
    sv = fit_svensson(tenors, par_pct)
    ns = fit_nelson_siegel(tenors, par_pct)
    p = linear(tenors, par_pct)
    y3m, y2, y10 = p(0.25), p(2.0), p(10.0)
    # Medidas empíricas de Diebold–Li (2006): no dependen de unos β mal identificados.
    level, slope, curv = y10, y10 - y3m, 2 * y2 - y3m - y10
    rep.metrics = {
        "nivel_pct": _pct(level), "pendiente_3m10a_pb": round(slope * 100, 1),
        "curvatura_pb": round(curv * 100, 1), "pend_2s10s_pb": round((y10 - y2) * 100, 1),
        "par_3m_pct": _pct(y3m), "par_2a_pct": _pct(y2), "par_10a_pct": _pct(y10),
        "par_30a_pct": _pct(p(30.0)),
        "rmse_svensson_pb": round(sv.rmse * 100, 3), "rmse_ns_pb": round(ns.rmse * 100, 3),
        **{f"sv_{k}": round(v, 4) for k, v in sv.params.items()},
    }
    rep.evidence = [
        f"10 años {y10:.2f} % · 2 años {y2:.2f} % · 3 meses {y3m:.2f} %",
        f"pendiente 3m10a {slope * 100:+.0f} pb · 2s10s {(y10 - y2) * 100:+.0f} pb · "
        f"curvatura {curv * 100:+.0f} pb",
        f"Svensson reproduce la curva con {sv.rmse * 100:.1f} pb de error medio "
        f"(Nelson–Siegel: {ns.rmse * 100:.1f} pb)",
    ]
    inverted = [n for n, v in (("2s10s", y10 - y2), ("3m10a", slope)) if v < 0]
    if inverted:
        rep.evidence.append("curva invertida en " + " y ".join(inverted))
    if sv.rmse * 100 > MAX_FIT_RMSE_BP:
        rep.status = "degradado"
        rep.warnings.append(f"ajuste Svensson con error medio {sv.rmse * 100:.1f} pb "
                            f"> {MAX_FIT_RMSE_BP} pb")
    if max(sv.params["tau1"], sv.params["tau2"]) >= max(TAU_GRID):
        rep.warnings.append("τ de Svensson en el borde de la rejilla: sus β no se interpretan "
                            "(solo sirven para interpolar)")
    return rep


def carry_state(history: Sequence[tuple[str, Sequence[float], Sequence[float]]],
                source: str, maturity: float = 10.0, horizon: float = 0.25) -> ProtoReport:
    """Carry + roll-down de un cupón cero a `maturity` años en `horizon` años, neto de la
    financiación, en unidades de su riesgo medido. `history` = [(fecha, plazos, par %)] de la
    más antigua a la más reciente (días hábiles)."""
    rep = ProtoReport("carry", history[-1][0] if history else None, source, "ok",
                      bias_on=f"duración: largo en el cupón cero a {maturity:g} años",
                      horizon=f"{round(horizon * 12)} meses")
    series = [(d, dict(zip(t, y, strict=True))) for d, t, y in history]
    lvl = [row.get(maturity) for _, row in series]
    lvl = [x for x in lvl if x is not None]
    if len(lvl) < MIN_HISTORY:
        rep.status = "no_data"
        rep.warnings.append(f"{len(lvl)} días con el plazo de {maturity:g} años: hacen falta "
                            f"≥ {MIN_HISTORY} para medir su volatilidad")
        return rep
    d, tenors, par = history[-1]
    zt, zz = par_to_zero(tenors, [y / 100 for y in par], horizon=maturity)
    zero = linear(zt, zz)
    funding = zero(horizon)
    cr = zero_coupon(zero, maturity, horizon, funding_rate=funding)
    dy = np.diff(np.asarray(lvl[-MIN_HISTORY:], dtype=float) / 100)
    sigma_y = float(np.std(dy, ddof=1)) * math.sqrt(horizon * TRADING_DAYS_YEAR)
    sigma_ret = sigma_y * (maturity - horizon)          # duración del cupón cero al final
    ratio = cr.excess / sigma_ret if sigma_ret > 0 else math.nan
    rep.metrics = {
        "carry_pb": round(cr.carry * 1e4, 1), "rolldown_pb": round(cr.rolldown * 1e4, 1),
        "financiacion_pb": round(cr.funding * 1e4, 1), "exceso_pb": round(cr.excess * 1e4, 1),
        "vol_rend_horizonte_pb": round(sigma_y * 1e4, 1),
        "vol_precio_horizonte_pct": round(sigma_ret * 100, 2),
        "sharpe_ex_ante": None if math.isnan(ratio) else round(ratio, 3),
        "punto_muerto_pb": round(cr.breakeven_bp(maturity - horizon), 1),
        "cero_10a_pct": round(zero(maturity) * 100, 4), "financiacion_pct": round(funding * 100, 4),
    }
    rep.evidence = [
        f"carry {cr.carry * 1e4:+.0f} pb + roll-down {cr.rolldown * 1e4:+.0f} pb − "
        f"financiación {cr.funding * 1e4:.0f} pb = {cr.excess * 1e4:+.0f} pb en el horizonte",
        f"volatilidad del rendimiento en el horizonte {sigma_y * 1e4:.0f} pb "
        f"(60 días): exceso / riesgo = {ratio:+.2f}",
        f"el tipo a {maturity:g} años puede subir {cr.breakeven_bp(maturity - horizon):.0f} pb "
        "antes de perder frente a la financiación",
    ]
    if not math.isnan(ratio):
        rep.bias = round(max(-1.0, min(1.0, ratio)), 3)
        rep.confidence = 0.2           # prototipo sin validación: tope bajo y fijo
    rep.warnings.append("financiación aproximada por la letra del mismo plazo (no repo/SOFR)")
    rep.warnings.append("prototipo sin validar (T49 no lo ha evaluado): no es una señal")
    return rep
