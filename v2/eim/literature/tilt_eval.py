"""Evaluación del ajuste bibliográfico de escenarios (T54) sobre pronósticos ya cerrados.

Criterios fijados en `PLAN/notas/T54_preregistro.md` §B y en `forecast/versions/lit_tilt_v1.json`.
Pura salvo `run_backfill` (que recibe las velas ya leídas): para cada origen walk-forward calcula
el pronóstico base (`forecast/backfill.py`, motor base, línea de T19) y el neto del agente
`literature` con las `agent_bars` velas ANTERIORES al origen; luego compara Brier multiclase,
log-loss y calibración del base contra el ajustado, con IC95 % por bootstrap de bloques de día.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace

import numpy as np

from eim.agents.literature.agent import LiteratureAgent
from eim.core import Candle, MarketSnapshot
from eim.forecast.backfill import backfill
from eim.forecast.base_engine import BaseEngine
from eim.forecast.calibration import BANDS, IDS, Outcome, calibration_curve, evaluate_forecast
from eim.forecast.lit_tilt import TiltConfig, tilt_probs
from eim.validation.stats import day_block_ci, rng_for

LOG_FLOOR = 1e-4     # piso de la probabilidad en el log-loss (igual para base y ajustado)


@dataclass(frozen=True)
class Row:
    """Un pronóstico cerrado: el `Outcome` de T19 + el neto de `literature` en su origen."""

    out: Outcome
    net: dict[str, float]

    @property
    def active(self) -> bool:
        return any(abs(v) > 0 for v in self.net.values())


def brier(probs: dict[str, float], realized: str) -> float:
    return sum((probs[i] - (i == realized)) ** 2 for i in IDS)


def logloss(probs: dict[str, float], realized: str) -> float:
    return -math.log(max(probs[realized], LOG_FLOOR))


def literature_net(candles: Sequence[Candle], timeframe: str, asof: int, bars: int,
                   agent: LiteratureAgent | None = None, symbol: str = "BTCUSDT"
                   ) -> dict[str, float]:
    """Neto por escenario con las últimas `bars` velas (todas anteriores a `asof`)."""
    snap = MarketSnapshot(symbol=symbol, timeframe=timeframe, candles=list(candles[-bars:]),
                          asof=asof, sources={}, coverage={})
    rep = (agent or LiteratureAgent()).run(snap)
    if rep.status == "no_data":
        return {i: 0.0 for i in IDS}
    sup = rep.metrics.get("scenario_support") or {}
    return {i: float((sup.get(i) or {}).get("net") or 0.0) for i in IDS}


def run_backfill(candles: list[Candle], cfg: TiltConfig, symbol: str = "BTCUSDT",
                 max_origins: int | None = None) -> list[Row]:
    """Filas de la muestra: un pronóstico base cada `stride` velas, sin solape de horizontes."""
    s = cfg.sample
    closes = {c.t: c.c for c in candles}
    idx = {c.t: k for k, c in enumerate(candles)}
    agent, rows = LiteratureAgent(), []
    for fs in backfill(BaseEngine(), candles, symbol=symbol, timeframe=s.timeframe,
                       horizon=s.horizon, n=s.n_paths, stride=s.stride, context=s.context,
                       max_origins=max_origins):
        out = evaluate_forecast(fs, closes)
        if out is None:
            continue
        i = idx[fs.made_at]                       # el origen: solo velas ANTERIORES (candles[:i])
        rows.append(Row(out, literature_net(candles[:i], s.timeframe, fs.made_at,
                                            s.agent_bars, agent, symbol)))
    return rows


def _ece(outs: Sequence[Outcome]) -> float:
    cur = calibration_curve(list(outs))
    return sum(abs(c["p_pred"] - c["p_obs"]) * c["n"] for c in cur) / (3 * len(outs))


def _cov(outs: Sequence[Outcome]) -> dict[str, float | None]:
    w = [o for o in outs if o.in_band_terminal]
    return {k: (float(np.mean([o.in_band_terminal[k] for o in w])) if w else None)
            for k in BANDS}


def tilted(row: Row, k: float) -> Outcome:
    return replace(row.out, probs=tilt_probs(row.out.probs, row.net, k))


def _diff(rows: Sequence[Row], k: float, fn) -> np.ndarray:
    return np.array([fn(r.out.probs, r.out.realized)
                     - fn(tilt_probs(r.out.probs, r.net, k), r.out.realized) for r in rows])


def _ci(d: np.ndarray, t: np.ndarray, cfg: TiltConfig, label: str) -> tuple[float, float]:
    c = cfg.criteria
    return day_block_ci(d, t, c.boot_reps, c.level, rng_for(c.seed, f"lit_tilt|{label}"))


def evaluate_tilt(rows: Sequence[Row], cfg: TiltConfig) -> dict:
    """Métricas y veredicto del ajuste. `ACEPTA` solo si se cumplen los 6 criterios del
    preregistro; con muestra insuficiente, `SIN EVIDENCIA`; si no, `NO ACEPTA`."""
    c, k = cfg.criteria, cfg.k
    rows = sorted(rows, key=lambda r: r.out.made_at)
    n = len(rows)
    res: dict = {"version": cfg.version, "k": k, "n": n, "n_active": sum(r.active for r in rows),
                 "enabled_in_config": cfg.enabled, "log_floor": LOG_FLOOR}
    if n < 2:
        res.update(verdict="SIN EVIDENCIA", checks=[], reason="sin pronósticos cerrados")
        return res
    t = np.array([r.out.made_at for r in rows], dtype=np.int64)
    db, dl = _diff(rows, k, brier), _diff(rows, k, logloss)
    base_o, new_o = [r.out for r in rows], [tilted(r, k) for r in rows]
    half = n // 2
    ci_b, ci_l = _ci(db, t, cfg, "brier"), _ci(dl, t, cfg, "logloss")
    e0, e1, c0, c1 = _ece(base_o), _ece(new_o), _cov(base_o), _cov(new_o)
    h1, h2 = float(db[:half].mean()) if half else math.nan, float(db[half:].mean())
    res.update(
        span=[int(t.min()), int(t.max())],
        brier={"base": float(np.mean([brier(r.out.probs, r.out.realized) for r in rows])),
               "tilt": float(np.mean([brier(o.probs, o.realized) for o in new_o])),
               "gain": float(db.mean()), "ci": list(ci_b)},
        logloss={"base": float(np.mean([logloss(r.out.probs, r.out.realized) for r in rows])),
                 "tilt": float(np.mean([logloss(o.probs, o.realized) for o in new_o])),
                 "gain": float(dl.mean()), "ci": list(ci_l)},
        ece={"base": e0, "tilt": e1}, coverage={"base": c0, "tilt": c1},
        curve={"base": calibration_curve(base_o), "tilt": calibration_curve(new_o)},
        halves={"first": h1, "second": h2},
        mean_net={i: float(np.mean([r.net[i] for r in rows])) for i in IDS})
    ok = [
        ("T1", "Muestra", f"{n} pronósticos ({res['n_active']} con neto ≠ 0)",
         f"≥ {c.min_forecasts} y ≥ {c.min_active} con neto ≠ 0",
         n >= c.min_forecasts and res["n_active"] >= c.min_active),
        ("T2", "Brier", f"ganancia {db.mean():+.5f}, IC [{ci_b[0]:+.5f}, {ci_b[1]:+.5f}]",
         "ganancia > 0 y extremo inferior del IC > 0", bool(db.mean() > 0 and ci_b[0] > 0)),
        ("T3", "Log-loss", f"ganancia {dl.mean():+.5f}, IC [{ci_l[0]:+.5f}, {ci_l[1]:+.5f}]",
         "ganancia > 0 y extremo inferior del IC > 0", bool(dl.mean() > 0 and ci_l[0] > 0)),
        ("T4", "Calibración", f"ECE base {e0:.4f} → ajustado {e1:.4f}", "ECE ajustado ≤ base",
         bool(e1 <= e0)),
        ("T5", "Cobertura de bandas", "idéntica" if c0 == c1 else f"{c0} → {c1}",
         "sin empeorar (el ajuste no toca las bandas)",
         all(c1[b] is None or c0[b] is None or c1[b] >= c0[b] - 1e-12 for b in BANDS)),
        ("T6", "Consistencia", f"1.ª mitad {h1:+.5f} · 2.ª mitad {h2:+.5f}",
         "ganancia de Brier > 0 en las dos mitades", bool(h1 > 0 and h2 > 0)),
    ]
    res["checks"] = [{"id": a, "name": b, "value": v, "threshold": th, "ok": bool(o)}
                     for a, b, v, th, o in ok]
    if not ok[0][4]:
        res.update(verdict="SIN EVIDENCIA", reason="muestra insuficiente (T1): sigue apagado")
    elif all(x[4] for x in ok):
        res.update(verdict="ACEPTA", reason="cumple T1–T6: puede encenderse con un commit "
                   "(`enabled: true` en lit_tilt_state.json)")
    else:
        res.update(verdict="NO ACEPTA", reason="falla " + ", ".join(
            f"{x[0]} ({x[1]})" for x in ok if not x[4]) + ": queda apagado")
    return res
