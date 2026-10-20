"""Prueba marginal de un bot en el núcleo (T59): ¿aporta información que el núcleo no tiene?

Mismo método que T44 (`eim.analytics.agents_marginal`, con el bot como un agente más del panel):
ΔSharpe, ΔE[R] e ΔIC a 24 velas fuera de muestra de la síntesis CON el bot frente a SIN él, y la
correlación del bot con `ema`/`structure`/`technical`. La regla se fija aquí, antes de calcular:

- **aporta** ⇔ `agents_marginal.passes` (Sharpe, E[R] e IC mejoran a la vez y el Sharpe mejora en
  ≥ 60 % de las ventanas) **y** no duplica al núcleo (|ρ| máx < `DUP_RHO`).
  Añadido tras la primera corrida real (2026-10-20), declarado: con una sola ventana de prueba el
  criterio «mejora en ≥ 60 % de las ventanas» se cumple trivialmente (1/1), así que se exige
  ≥ `MIN_WINDOWS` ventanas; sin ellas el aporte queda «no medible».
- **peso inicial medido** = `MODERATE_WEIGHT·(1 − ρ⁺ máx)` si aporta, 0 si no. Nunca se decreta.
- **modera** ⇔ el acuerdo del bot con el núcleo predice un acierto mayor del núcleo (IC95 de la
  diferencia de aciertos por encima de 0, ≥ `MOD_MIN_N` por grupo). Modula la confianza; no vota.
Un bot que no rinde solo puede aportar información distinta; uno que rinde pero repite al núcleo no.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from eim.analytics import agents_marginal as am
from eim.core import BotSignal
from eim.synthesis.params import MODERATE_WEIGHT

PEERS = ("ema", "structure", "technical")
DUP_RHO = 0.9          # |ρ| ≥ 0,9 con algún agente del núcleo = lo repite
MIN_WINDOWS = 2        # con < 2 ventanas de prueba «mejora en el 100 %» no es evidencia
MOD_MIN_N = 30
MOD_H = 24             # velas de 1 h
N_BOOT = 1000
STANCE_MIN = 0.2


@dataclass(frozen=True)
class Marginal:
    contributes: bool
    weight: float
    reason: str
    rho_max: float | None = None
    deltas: dict | None = None
    moderator: dict | None = None
    modulates: bool = False

    def to_json(self) -> dict:
        return {"contributes": self.contributes, "weight": self.weight, "reason": self.reason,
                "rho_max": self.rho_max, "deltas": self.deltas, "moderator": self.moderator,
                "modulates": self.modulates, "rule": am.RULE}


def agent_name(label: str) -> str:
    return "bot:" + label


def panel_rows(name: str, rows: list[BotSignal], asofs: set[int]) -> pd.DataFrame:
    """Postura del bot como reporte de agente en los instantes del panel (confianza 1 si no da)."""
    out = [(s.asof, name, float(s.stance), float(s.confidence if s.confidence is not None else 1.0),
            s.status, None) for s in rows if s.asof in asofs]
    return pd.DataFrame(out, columns=["asof", "agent", "bias", "conf", "status", "regime"])


def rho_max(res: dict, name: str) -> float | None:
    vals = [res["corr_disc"].get(f"{name}~{p}", {}).get("pearson") for p in PEERS]
    vals = [abs(v) for v in vals if v is not None]
    return max(vals) if vals else None


def measured_weight(rho: float | None) -> float:
    pen = max(0.0, rho) if rho is not None else 0.0
    return round(MODERATE_WEIGHT * (1.0 - pen), 2)


def decide(res: dict, name: str, moderator: dict | None = None) -> Marginal:
    """Aplica la regla a un resultado de `agents_marginal.evaluate` (un activo)."""
    rho = rho_max(res, name)
    ok, why = am.passes(res, name)
    row = res["variants"].get(f"+{name}")
    base = res["variants"]["base"]
    deltas = None
    if row is not None:
        deltas = {"sharpe": (row["metrics"]["sharpe"] or 0) - (base["metrics"]["sharpe"] or 0),
                  "expectancy_r": (row["metrics"]["expectancy_r"] or 0)
                  - (base["metrics"]["expectancy_r"] or 0),
                  "ic24": row["ic"][1]["delta"]}
    n_win = len(row["windows"]) if row is not None and "windows" in row else MIN_WINDOWS
    if ok and n_win < MIN_WINDOWS:
        return Marginal(False, 0.0, f"no medible: solo {n_win} ventana(s) de prueba "
                        f"(< {MIN_WINDOWS}); regla T44 sola: {why}", rho, deltas, moderator,
                        bool((moderator or {}).get("modulates")))
    mod = moderator or {}
    modulates = bool(mod.get("modulates"))
    if ok and rho is not None and rho >= DUP_RHO:
        return Marginal(False, 0.0, f"repite al núcleo (|ρ| {rho:.2f} ≥ {DUP_RHO}); {why}", rho,
                        deltas, moderator, modulates)
    if ok:
        return Marginal(True, measured_weight(rho), f"aporta: {why}", rho, deltas, moderator,
                        modulates)
    return Marginal(False, 0.0, f"no aporta: {why}", rho, deltas, moderator, modulates)


def moderator_effect(core: pd.Series, stance: dict[int, float], candles, cut: int,
                     seed: int = 0) -> dict:
    """¿Predice mejor el núcleo cuando el bot coincide con él? (solo mitad de prueba)."""
    s = core[core.index >= cut]
    asofs = s.index.to_numpy()[::max(1, MOD_H // am.PANEL_STEP)]
    sig = s.reindex(asofs).to_numpy()
    y = am.forward_returns(candles, asofs, MOD_H)
    b = np.array([stance.get(int(a), 0.0) for a in asofs])
    ok = (~np.isnan(y)) & (np.abs(sig) > 0) & (np.abs(b) >= STANCE_MIN)
    hit = (np.sign(sig) == np.sign(y))[ok]
    agree = (np.sign(sig) == np.sign(b))[ok]
    na, nd = int(agree.sum()), int((~agree).sum())
    out = {"h": MOD_H, "n_agree": na, "n_disagree": nd,
           "hit_agree": float(hit[agree].mean()) if na else None,
           "hit_disagree": float(hit[~agree].mean()) if nd else None,
           "diff": None, "ci95": None, "modulates": False}
    if na < MOD_MIN_N or nd < MOD_MIN_N:
        out["note"] = f"muestra insuficiente (< {MOD_MIN_N} por grupo)"
        return out
    rng = np.random.default_rng(seed)
    ha, hd = hit[agree], hit[~agree]
    d = [rng.choice(ha, na).mean() - rng.choice(hd, nd).mean() for _ in range(N_BOOT)]
    ci = [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]
    out.update(diff=float(ha.mean() - hd.mean()), ci95=ci, modulates=bool(ci[0] > 0))
    return out


def evaluate_bot(panel: pd.DataFrame, name: str, rows: list[BotSignal], candles, funding,
                 symbol: str, log=lambda _m: None) -> Marginal:
    """Estudio completo de un bot en un activo (el panel trae solo agentes del núcleo)."""
    asofs = set(panel["asof"].unique().tolist())
    df = pd.concat([panel, panel_rows(name, rows, asofs)], ignore_index=True)
    df = df.sort_values(["asof", "agent"], ignore_index=True)
    if not (df.agent == name).any():
        return Marginal(False, 0.0, "sin posturas del bot en el panel: no medible")
    res = am.evaluate(df, candles, funding, symbol, log, new=(name,), peers=PEERS)
    agents = sorted(set(df.agent) - am.NON_DIRECTIONAL - {"regime"})
    sy = am.variants(res["corr_disc"], (name,), PEERS)["base"]
    core = am.synth_series(am.reports_by_asof(df), sy, agents)
    stance = {int(s.asof): s.stance for s in rows if s.status == "ok"}
    mod = moderator_effect(core, stance, candles, res["cut"])
    m = decide(res, name, mod)
    if not math.isfinite(m.weight):
        return Marginal(False, 0.0, "peso no finito", m.rho_max)
    return m
