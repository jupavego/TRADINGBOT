"""Medición en el banco de T131 de lo que T136 cambia: costos, tope, frenos y tamaño.

Cuatro cosas, todas sobre las operaciones del banco (mismas entradas, misma salida vigente):

1. **El costo que el riesgo no incluye** (entregable 1): distribución del costo en R y cuánto se
   pasa hoy del riesgo declarado, en total y por marco.
2. **El tope de costo en R** (entregable 2): qué deja fuera y qué E[R] queda con cada valor de la
   rejilla, medido con el costo **ex ante**, que es el que decide el veto, no con el realizado.
3. **Los frenos** (entregable 4): se simula el capital del perfil operación a operación con los
   MISMOS `caps` que corren en el libro (`caps.Brake`, `caps.dd_scale`, `caps.cvar_scale`), así
   que lo medido es el freno de verdad y no una reimplementación.
4. **El tamaño por volatilidad objetivo** (entregable 3, opcional) con la σ versionada de T132.

El Kelly (entregable 5) y la comprobación del ES (E12) viven en `eim/paper/kelly.py` y
`eim/paper/exits/es_check.py`; aquí solo se les da la evidencia.

Puro: sin red y sin disco. Las cifras salen de `BenchTrade`, que ya es neto de costos.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from eim.paper import kelly
from eim.paper.caps import Brake, CapParams
from eim.paper.exits.bench import BenchTrade
from eim.paper.exits.metrics import cvar
from eim.paper.exits.stats import cluster_se

CVAR_MIN_N = 30          # muestra mínima para informar un CVaR


def _q(xs: Sequence[float], p: float) -> float:
    return float(np.quantile(np.asarray(xs, dtype=float), p)) if len(xs) else math.nan


def _pf(rs: Sequence[float]) -> float | None:
    """Factor de beneficio: ganado entre perdido. La misma cuenta que `metrics.summary`."""
    r = np.asarray(rs, dtype=float)
    won, lost = float(r[r > 0].sum()), float(-r[r <= 0].sum())
    return won / lost if lost > 0 else None


def cost_profile(ts: Sequence[BenchTrade], ex_ante: dict[str, float]) -> dict:
    """Lo que cuesta el viaje completo, en R, y cuánto se pasa el riesgo de lo declarado.

    `ex_ante` es el costo en R que el perfil estima AL DECIDIR (`risk_budget.cost_r`), que es con
    el que dimensiona y con el que veta; el realizado sale de la operación cerrada.
    """
    real = [t.cost_r for t in ts]
    est = [ex_ante[t.id] for t in ts if t.id in ex_ante]
    by_tf: dict[str, dict] = {}
    for tf in sorted({t.timeframe for t in ts}):
        g = [t for t in ts if t.timeframe == tf]
        e = [ex_ante[t.id] for t in g if t.id in ex_ante]
        by_tf[tf] = {"n": len(g), "cost_r_real_mean": float(np.mean([t.cost_r for t in g])),
                     "cost_r_ex_ante_mean": float(np.mean(e)) if e else None,
                     "overrun_pct": 100 * float(np.mean(e)) if e else None}
    return {
        "n": len(ts),
        "cost_r_real": {"mean": float(np.mean(real)) if real else math.nan,
                        "median": _q(real, 0.5), "p90": _q(real, 0.9)},
        "cost_r_ex_ante": {"mean": float(np.mean(est)) if est else math.nan,
                           "median": _q(est, 0.5), "p90": _q(est, 0.9), "n": len(est)},
        # lo que de verdad se arriesga al saltar el SL inicial, en unidades del riesgo declarado
        "risk_overrun": float(1 + np.mean(est)) if est else math.nan,
        "qty_ratio_with_costs": float(1 / (1 + np.mean(est))) if est else math.nan,
        "by_timeframe": by_tf,
    }


def cost_cap_grid(ts: Sequence[BenchTrade], ex_ante: dict[str, float],
                  caps: Sequence[float]) -> list[dict]:
    """Para cada tope de costo: qué se queda fuera y con qué E[R] se opera lo que entra."""
    out = []
    have = [t for t in ts if t.id in ex_ante]
    for cap in caps:
        keep = [t for t in have if ex_ante[t.id] <= cap]
        rs = [t.r for t in keep]
        out.append({
            "cap_r": cap, "n": len(keep), "share": len(keep) / len(have) if have else math.nan,
            "expectancy_r": float(np.mean(rs)) if rs else None,
            "win_rate": float(np.mean([r > 0 for r in rs])) if rs else None,
            "pf": _pf(rs) if rs else None,
            "cvar95_r": cvar(rs) if rs else None,
        })
    return out


def equity_run(ts: Sequence[BenchTrade], risk_pct: float, caps: CapParams,
               initial: float = 10_000.0) -> dict:
    """Capital del perfil operación a operación con `caps`, en orden de cierre.

    Usa `caps.Brake` tal cual corre en el libro: el freno todo o nada pausa entradas, el gradual y
    el límite de CVaR recortan el tamaño. Devuelve el capital final, el drawdown máximo, el CVaR
    de los resultados por operación y cuántas entradas se frenaron o se recortaron.

    **Es una aproximación secuencial**: una operación detrás de otra, en orden de cierre, sin
    posiciones solapadas ni margen. El libro de verdad tiene varias abiertas a la vez, así que el
    capital va con retraso respecto a esto. Sirve para comparar frenos entre sí —todos sufren la
    misma aproximación—, no para pronosticar la curva de un perfil.
    """
    order = sorted(ts, key=lambda t: (t.exit_t, t.id))
    eq, peak, maxdd = initial, initial, 0.0
    b = Brake(peak=initial)
    halted = cut = 0
    rs: list[float] = []
    for t in order:
        if b.veto(t.t):
            halted += 1
            continue
        scale, _ = b.scale(caps, eq)
        if scale <= 0:
            halted += 1
            continue
        cut += scale < 1.0
        risk = eq * risk_pct * scale
        eq += risk * t.r
        rs.append(t.r * scale)
        peak = max(peak, eq)
        maxdd = max(maxdd, 1 - eq / peak if peak > 0 else 0.0)
        b.closed(caps, eq, initial, t.exit_t, t.r)
        if eq <= 0:
            break
    return {"n_taken": len(rs), "halted": halted, "cut": cut, "equity_final": eq,
            "return_pct": 100 * (eq / initial - 1), "max_dd_pct": 100 * maxdd,
            # con cuatro operaciones un CVaR no significa nada: antes de 30 no se informa
            "cvar95_r": cvar(rs) if len(rs) >= CVAR_MIN_N else None,
            "ruined": eq <= initial * 0.01}


def cases(dd_brakes: Sequence[float], cvar_limits: Sequence[float],
          cut: float = 0.5) -> list[tuple[str, CapParams]]:
    """Los casos de la rejilla pre-registrada de S3, más el de hoy.

    El freno gradual no tiene rejilla propia en el pre-registro, así que se **construye** desde la
    que hay, sin inventar parámetros: el último tramo es el `dd_brake` pre-registrado y el
    intermedio es la mitad de ese valor con el riesgo a la mitad.
    """
    out: list[tuple[str, CapParams]] = [("hoy (sin frenos)", CapParams())]
    for dd in dd_brakes:
        out.append((f"todo o nada dd={dd:.0%}", CapParams(dd_brake=dd)))
        out.append((f"gradual dd={dd:.0%}", CapParams(dd_steps=((dd / 2, cut), (dd, 0.0)))))
    for lim in cvar_limits:
        out.append((f"CVaR ≥ {-lim:.2f} R", CapParams(cvar_limit_r=-lim)))
    return out


def brake_grid(ts: Sequence[BenchTrade], risk_pct: float, dd_brakes: Sequence[float],
               cvar_limits: Sequence[float], cut: float = 0.5) -> list[dict]:
    """La rejilla de S3 sobre toda la ventana, de corrido (el horizonte largo)."""
    return [{"caso": name, **equity_run(ts, risk_pct, caps)}
            for name, caps in cases(dd_brakes, cvar_limits, cut)]


def brake_grid_by_fold(folds: Sequence[Sequence[BenchTrade]], risk_pct: float,
                       dd_brakes: Sequence[float], cvar_limits: Sequence[float],
                       cut: float = 0.5) -> list[dict]:
    """La misma rejilla pliegue a pliegue, cada uno con su capital inicial.

    Hace falta porque de corrido, 3,5 años de un sistema con E[R] < 0 arruinan la cuenta en
    cualquier configuración y la tabla no distingue nada. Por pliegue (tres meses) sí se ve qué
    hace cada freno.
    """
    out = []
    for name, caps in cases(dd_brakes, cvar_limits, cut):
        runs = [equity_run(ts, risk_pct, caps) for ts in folds if ts]
        if not runs:
            continue
        rets = [r["return_pct"] for r in runs]
        out.append({"caso": name, "folds": len(runs),
                    "return_median_pct": float(np.median(rets)),
                    "return_worst_pct": float(np.min(rets)),
                    "dd_median_pct": float(np.median([r["max_dd_pct"] for r in runs])),
                    "taken_median": float(np.median([r["n_taken"] for r in runs])),
                    "ruined_folds": sum(r["ruined"] for r in runs)})
    return out


def kelly_view(ts: Sequence[BenchTrade], k: kelly.KellyParams,
               profile_risk_pct: dict[str, float]) -> dict:
    """La evidencia que ve Kelly y el tamaño que saldría para cada perfil."""
    rs = np.array([t.r for t in ts], dtype=float)
    days = np.array([t.day for t in ts], dtype=np.int64)
    se = cluster_se(days, rs) if len(rs) > 1 else math.nan
    e = kelly.Edge.of(rs.tolist(), se_r=None if math.isnan(se) else se)
    return {"n": e.n, "mean_r": e.mean_r, "se_r": e.se_r, "m2_r": e.m2_r,
            "lower_r": kelly.lower_bound(e, k.z), "z": k.z, "frac": k.frac,
            "fraction": kelly.fraction(e, k),
            "risk_pct": {pid: kelly.risk_pct(e, k, v) for pid, v in profile_risk_pct.items()}}


W_MIN, W_MAX = 0.25, 4.0     # el multiplicador del tamaño nunca sale de aquí


def vol_target_view(ts: Sequence[BenchTrade], sigma_of: dict[str, float],
                    targets: Sequence[float]) -> dict:
    """Tamaño por volatilidad objetivo con la σ versionada de T132 (entregable 3, opcional).

    El multiplicador es `objetivo / σ` acotado a [0,25; 4], y lo que se mide es si **reduce la
    dispersión** del resultado por operación sin empeorar la esperanza.

    Cuidado con las unidades: la σ versionada es **relativa por vela** (fracción del precio,
    mediana ≈ 0,0025), así que un `objetivo` de 0,5 o 1,0 no está en sus unidades y satura el
    tope. Se informa `saturated` de cada objetivo para que se vea, y además se mide el único
    objetivo **sin parámetro libre**: la σ mediana de la propia muestra, con la etiqueta
    `mediana`. Adoptarlo exigiría una versión nueva del pre-registro, no un ajuste aquí.
    """
    have = [t for t in ts if sigma_of.get(t.id, 0.0) > 0]
    base = np.array([t.r for t in have], dtype=float)
    sig = np.array([sigma_of[t.id] for t in have], dtype=float)
    med = float(np.median(sig)) if len(sig) else math.nan
    out = {"n": len(have), "sigma_median": med, "w_min": W_MIN, "w_max": W_MAX,
           "base": {"expectancy_r": float(base.mean()) if len(base) else None,
                    "sd_r": float(base.std(ddof=1)) if len(base) > 1 else None,
                    "cvar95_r": cvar(base.tolist()) if len(base) else None}, "targets": []}
    for label, tgt in [*((f"{t:g}", t) for t in targets), ("mediana", med)]:
        if not len(sig) or not math.isfinite(tgt):
            continue
        raw = tgt / sig
        w = np.clip(raw, W_MIN, W_MAX)
        r = base * w
        out["targets"].append({
            "label": label, "target": tgt,
            "saturated": float(np.mean((raw <= W_MIN) | (raw >= W_MAX))),
            "weight_median": float(np.median(w)),
            "expectancy_r": float(r.mean()),
            "sd_r": float(r.std(ddof=1)) if len(r) > 1 else None,
            "cvar95_r": cvar(r.tolist())})
    return out
