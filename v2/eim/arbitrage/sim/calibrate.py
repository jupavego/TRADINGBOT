"""Calibración del selector T38 con la evidencia simulada (T43).

1. Umbral de neto estimado: para cada umbral θ, lo REALIZADO de las decisiones cuyo neto
   estimado por el motor fue ≥ θ (todas las que pasan los demás filtros del selector;
   solapadas → bootstrap por bloques del largo de la tenencia).
2. Riesgos heurísticos de `ArbParams` medidos en el histórico: movimiento diario
   plausible (p90 |rend. 24 h|), cambio de base perpetuo−spot en la tenencia del carry
   (p90) y desvío del funding extrapolado frente al realizado (p90 por liquidación).
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np

from eim.arbitrage.params import ArbParams
from eim.arbitrage.sim.frame import ArbHistory, Funding
from eim.arbitrage.sim.panel import PanelRow
from eim.arbitrage.sim.stats import block_bootstrap

THRESHOLDS = (-1e9, 0.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0)


def threshold_sweep(rows: list[PanelRow], every_h: int, seed: int = 0,
                    policy_stats: Callable[[float], dict] | None = None) -> list[dict]:
    """Por umbral θ: lo realizado de TODAS las decisiones con neto estimado ≥ θ (solapadas)
    y, con `policy_stats`, la política de una posición a la vez con ese umbral."""
    pool = sorted((r for r in rows if r.trade is not None
                   and r.reject_code in (None, "below_min")), key=lambda r: r.t)
    out = []
    for th in THRESHOLDS:
        sub = [r for r in pool if r.est_net_bps >= th]
        if not sub:
            out.append({"theta": th, "n": 0})
            continue
        real = np.array([r.trade.net_bps for r in sub if r.trade is not None])
        est = np.array([r.est_net_bps for r in sub])
        hold = float(np.median([r.trade.hold_h for r in sub if r.trade is not None]))
        lo, hi, p0 = block_bootstrap(real, max(1, math.ceil(hold / every_h)), seed=seed)
        row = {"theta": th, "n": len(sub), "est_mean_bps": float(est.mean()),
               "real_mean_bps": float(real.mean()), "ci95": [lo, hi], "p_le0": p0,
               "share_pos": float((real > 0).mean()), "gap_bps": float((real - est).mean())}
        if policy_stats is not None:
            st = policy_stats(th)
            row["policy_n"], row["policy_apr"] = st.get("n", 0), st.get("apr_period")
            m, ci = st.get("mean_bps"), st.get("ci95_mean_bps")
            if m and m > 0 and ci and ci[0] == ci[0]:  # semiancho del IC de la anual
                row["policy_apr_half"] = abs(st["apr_period"]) * (ci[1] - ci[0]) / 2 / m
        out.append(row)
    return out


def pick_threshold(sweep: list[dict], current: float) -> float | None:
    """Umbral respaldado por la evidencia (None si ningún θ ≥ 0 da realizado significativo).

    Candidatos: θ ≥ 0 con realizado de IC95 % inferior > 0 (n ≥ 30) cuya política rinde
    dentro del ruido de la mejor (semiancho del IC de su anual). Si el umbral actual está
    entre ellos se mantiene (la evidencia no lo distingue); si no, el menor candidato."""
    ok = [r for r in sweep if r["theta"] >= 0 and r.get("n", 0) >= 30 and r["ci95"][0] > 0]
    if not ok:
        return None
    best = max(ok, key=lambda r: r.get("policy_apr") or 0.0)
    floor = (best.get("policy_apr") or 0.0) - best.get("policy_apr_half", 0.0)
    cand = [r for r in ok if (r.get("policy_apr") or 0.0) >= floor]
    if any(abs(r["theta"] - current) < 1e-9 for r in cand):
        return float(current)
    return float(min(r["theta"] for r in cand))


def _p(x: np.ndarray, q: float) -> float:
    return float(np.percentile(x, q)) if len(x) else float("nan")


def daily_move(hist: ArbHistory) -> dict[str, dict[str, float]]:
    out = {}
    for a, h in hist.assets.items():
        if h.perp is None or len(h.perp) < 48:
            continue
        lc = np.log(h.perp.c)
        r = np.abs(lc[24:] - lc[:-24])
        out[a] = {"p50": _p(r, 50), "p90": _p(r, 90), "p99": _p(r, 99)}
    return out


def basis_change(hist: ArbHistory, horizon_h: float) -> dict[str, dict[str, float]]:
    """|Δ(perpetuo − spot)| en pb durante `horizon_h` (cierres 1 h alineados)."""
    out = {}
    k = max(1, int(horizon_h))
    for a, h in hist.assets.items():
        if h.perp is None or h.spot is None:
            continue
        _, ip, is_ = np.intersect1d(h.perp.t, h.spot.t, assume_unique=True,
                                    return_indices=True)
        b = (h.perp.c[ip] - h.spot.c[is_]) / h.spot.c[is_] * 1e4
        if len(b) <= k:
            continue
        d = np.abs(b[k:] - b[:-k])
        out[a] = {"p50": _p(d, 50), "p90": _p(d, 90), "p99": _p(d, 99),
                  "level_p50": _p(b, 50)}
    return out


def funding_shock(hist: ArbHistory, n_past: int, ahead: int = 90) -> dict[str, dict]:
    """|media realizada de las próximas `ahead` − media de las últimas `n_past`| por
    liquidación (lo que el motor extrapola frente a lo que luego pasó)."""
    out = {}
    for a, h in hist.assets.items():
        f = Funding.of(h.funding)
        r = f.rate
        if len(r) < n_past + ahead:
            continue
        cs = np.concatenate(([0.0], np.cumsum(r)))
        i = np.arange(n_past, len(r) - ahead + 1)
        past = (cs[i] - cs[i - n_past]) / n_past
        fut = (cs[i + ahead] - cs[i]) / ahead
        d = np.abs(fut - past)
        out[a] = {"p50": _p(d, 50), "p90": _p(d, 90), "p99": _p(d, 99), "ahead": ahead,
                  "mean_rate": float(r.mean()), "share_negative": float((r < 0).mean())}
    return out


def measured(hist: ArbHistory, carry_h: float, n_past: int) -> dict:
    dm, bc, fs = daily_move(hist), basis_change(hist, carry_h), funding_shock(hist, n_past)
    pick = {}
    if dm:
        pick["daily_move"] = round(max(v["p90"] for v in dm.values()), 4)
    if bc:
        pick["basis_floor_bps"] = round(max(v["p90"] for v in bc.values()), 1)
    if fs:
        pick["funding_shock_rate"] = round(max(v["p90"] for v in fs.values()), 6)
    return {"daily_move": dm, "basis_change": bc, "funding_shock": fs, "pick": pick,
            "carry_h": carry_h}


def recommend(res: dict, p: ArbParams) -> list[dict]:
    """Parámetros del selector T38 que respalda la evidencia: (parámetro, antes, después,
    evidencia). Solo se cambia lo que se midió; lo demás queda declarado sin calibrar."""
    out: list[dict] = []

    def put(name: str, after: object, why: str) -> None:
        out.append({"param": name, "before": getattr(p, name), "after": after, "why": why})

    v = res["verdicts"]
    keep = tuple(s for s in p.selectable if v.get(s, ("No viable",))[0] != "No viable")
    put("selectable", keep, "se desactiva toda estrategia con veredicto No viable")
    put("carry_horizon_h", res["best_carry_h"], "tenencia del carry con mayor rentabilidad "
        "anual sobre el período (tabla de horizontes)")
    best = [h for h in res.get("carry_horizons", []) if h["horizon_h"] == res["best_carry_h"]]
    blocks = {**res["strategies"], **({"funding_carry": best[0]} if best else {})}
    picks = [blocks[s]["pick_theta"] for s in keep if s in blocks]
    picks = [x for x in picks if x is not None]
    if picks:
        put("min_net_bps", max(picks), "umbral con realizado significativo (IC95 % > 0, ≥ 30 "
            "decisiones) y rentabilidad de la política dentro del ruido de la mejor; se "
            "mantiene si la evidencia no lo distingue; el más exigente entre las seleccionables")
    else:
        put("min_net_bps", p.min_net_bps, "ningún umbral da realizado significativo > 0: se "
            "mantiene (las estrategias quedan fuera por `selectable`)")
    lev = res.get("sensitivity", {}).get("leverage", {})
    ok = {lv: sum((row.get(s) or {}).get("apr_period") or 0.0 for s in keep)
          for lv, row in lev.items()
          if all(not (row.get(s) or {}).get("liquidations") for s in keep)}
    if keep and ok:
        put("perp_leverage", max(ok, key=lambda k: ok[k]), "apalancamiento de las patas de "
            "futuros con mayor rentabilidad anual sin liquidaciones (sensibilidad)")
    dis = res["strategies"].get("basis", {}).get("disabled_variants", [])
    put("disabled_variants", tuple(dis), "variantes con veredicto No viable en el backtest "
        "(neto medio ≤ 0) aunque su estrategia siga activa")
    for name, val in res["calibration"]["pick"].items():
        put(name, val, "p90 medido en el histórico (ver «Calibración de riesgos»)")
    return out
