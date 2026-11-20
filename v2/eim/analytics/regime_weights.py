"""Pesos por régimen (T197): ¿cambia el régimen **qué agente acierta**?

Mide, sobre el panel histórico de T44 (`agent_panel`) y con el pre-registro
`PLAN/notas/T197_preregistro.md`, si modular el peso de cada agente por el régimen que etiqueta
`regime` (T22) mejora la señal de la síntesis fuera de muestra, después de costos.

Dos cosas que esta medición respeta y que son el motivo de la tarea:
- **la potencia va primero**: si la mejora mínima detectable no baja de la puerta, la mitad de
  prueba NO se mira (es lo que hicieron T133 en su cota del oráculo y T166 con su MDE de QLIKE);
- **la escalera de multiplicadores está declarada** antes de ver ninguna celda: umbral ±0,02 de IC,
  mínimo 200 muestras, tres niveles (0,5 / 1,0 / 1,5).

Puro: numpy/pandas y la propia síntesis; sin red ni disco (el panel, las velas y el funding los
trae quien llama). El resultado es un diccionario; quien informa es `regime_weights_report`.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np
import pandas as pd

from eim.analytics.agents_marginal import (
    BT,
    N_BOOT,
    PANEL_STEP,
    Q_SIGNAL,
    backtest,
    forward_returns,
    reports_by_asof,
    split_at,
)
from eim.analytics.technical_ic import spearman
from eim.backtest.metrics import compute_metrics
from eim.core import AgentReport, Candle
from eim.synthesis import SynthesisParams, synthesize
from eim.synthesis.params import NON_DIRECTIONAL, role_of
from eim.validation.power import mde

# --- Pre-registro (§4 y §5). Nada de esto se toca después de ver cifras. -----------------
# El agente `regime` guarda la etiqueta en `metrics["regime"]` con estas claves; los nombres en
# castellano son los suyos (`eim/agents/regime/agent.py`) y solo se usan para informar.
REGIMES: tuple[str, ...] = ("trend_up", "trend_down", "range", "volatile")
NAMES = {"trend_up": "tendencial alcista", "trend_down": "tendencial bajista",
         "range": "rango", "volatile": "alta volatilidad"}
H_PRIMARY, H_SECONDARY = 4, 24      # velas de 1 h; el panel da un instante cada PANEL_STEP
MIN_N = 200                         # muestras mínimas por agente y régimen (descubrimiento)
THR_IC = 0.02                       # |IC[a,g] − IC[a]| que mueve el multiplicador
M_UP, M_DOWN, M_FLAT = 1.5, 0.5, 1.0
BLOCK_DAYS = 30                     # bloques del bootstrap emparejado
GATE_MDE = 0.01                     # puerta 1: sin esto, SIN POTENCIA
GATE_DELTA = 0.01                   # puerta 2: ΔIC fuera de muestra, con IC95 que excluya 0
MIN_LABELLED = 0.8                  # §6: menos etiqueta que esto y no hay pregunta
SEED = 197
DAY_MS = 86_400_000


def voters(df: pd.DataFrame) -> list[str]:
    """Agentes del panel que votan hoy con peso > 0 (los únicos que un multiplicador movería)."""
    base = SynthesisParams()
    return [a for a in sorted(set(df.agent))
            if a not in NON_DIRECTIONAL and a not in base.excluded
            and role_of(a, base) == "direccional" and base.weights.get(a, 1.0) > 0]


def regime_by_asof(df: pd.DataFrame) -> dict[int, str | None]:
    """Etiqueta de régimen por instante (columna `regime` del panel; None si `regime` no dio)."""
    g = df[["asof", "regime"]].drop_duplicates("asof")
    return {int(a): (None if r is None or pd.isna(r) else str(r))
            for a, r in g.itertuples(index=False)}


def agent_ic(df: pd.DataFrame, candles: list[Candle], agents: list[str],
             h: int = H_PRIMARY) -> dict:
    """IC de Spearman de `sesgo × confianza` de cada agente: global y por régimen, en este tramo."""
    reg = regime_by_asof(df)
    live = df[df.status == "ok"]
    out: dict = {}
    for a in agents:
        rows = live[live.agent == a]
        if rows.empty:
            out[a] = {"ic": float("nan"), "n": 0, "p": float("nan"),
                      "by_regime": {g: {"ic": float("nan"), "n": 0} for g in REGIMES}}
            continue
        asofs = rows["asof"].to_numpy()
        x = rows["bias"].to_numpy(float) * rows["conf"].to_numpy(float)
        y = forward_returns(candles, asofs, h)
        ic, n, p = spearman(x, y)
        labels = np.array([reg.get(int(t)) for t in asofs], dtype=object)
        per = {}
        for g in REGIMES:
            m = labels == g
            icg, ng, _ = spearman(x[m], y[m]) if m.any() else (float("nan"), 0, float("nan"))
            per[g] = {"ic": icg, "n": ng}
        out[a] = {"ic": ic, "n": n, "p": p, "by_regime": per}
    return out


def multipliers(detail: dict) -> tuple[dict[str, dict[str, float]], list[dict]]:
    """Escalera de §4 del pre-registro → (`regime_weights` candidato, detalle celda a celda)."""
    out: dict[str, dict[str, float]] = {}
    table: list[dict] = []
    for a, d in sorted(detail.items()):
        ic_a = d["ic"]
        for g in REGIMES:
            icg, ng = d["by_regime"][g]["ic"], d["by_regime"][g]["n"]
            if ng < MIN_N:
                m, why = M_FLAT, f"n = {ng} < {MIN_N}"
            elif not (math.isfinite(icg) and math.isfinite(ic_a)):
                m, why = M_FLAT, "IC no definido (sin varianza)"
            else:
                diff = icg - ic_a
                m = M_UP if diff >= THR_IC else M_DOWN if diff <= -THR_IC else M_FLAT
                why = f"dIC {diff:+.4f}"
            table.append({"agent": a, "regime": g, "n": int(ng), "ic": icg, "ic_all": ic_a,
                          "m": m, "why": why})
            if m != M_FLAT:
                out.setdefault(g, {})[a] = m
    return out, table


def synth_signal(by_asof: dict[int, list[AgentReport]], p: SynthesisParams, expected: list[str],
                 reg: dict[int, str | None], use_regime: bool) -> pd.Series:
    """`sesgo × confianza` de la síntesis por instante; `use_regime` pasa la etiqueta a la síntesis.

    Ningún sitio de producción pasa hoy `regime=` a `synthesize` (solo lo hace su prueba unitaria):
    adoptar los multiplicadores exigiría, además del diccionario, cablear la etiqueta en esas
    llamadas. Aquí se pasa a mano para poder medir qué daría.
    """
    vals: dict[int, float] = {}
    for a, reps in by_asof.items():
        s = synthesize(reps, p, regime=reg.get(a) if use_regime else None, expected=expected)
        vals[a] = 0.0 if s is None else s.bias * s.confidence
    return pd.Series(vals).sort_index()


def _blocks(t: np.ndarray, block_days: int) -> list[np.ndarray]:
    blk = ((t - t.min()) // (block_days * DAY_MS)).astype(int)
    return [np.flatnonzero(blk == b) for b in np.unique(blk)]


def block_delta(x: np.ndarray, x0: np.ndarray, y: np.ndarray, t: np.ndarray,
                n_boot: int = N_BOOT, block_days: int = BLOCK_DAYS, seed: int = SEED) -> dict:
    """ΔIC (régimen − plana) y su IC95 por bootstrap emparejado en bloques de `block_days` días."""
    ok = ~(np.isnan(y) | np.isnan(x) | np.isnan(x0))
    x, x0, y, t = x[ok], x0[ok], y[ok], t[ok]
    ic, n, _ = spearman(x, y)
    ic0 = spearman(x0, y)[0]
    groups = _blocks(t, block_days)
    rng = np.random.default_rng(seed)
    d: list[float] = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(groups), len(groups))
        idx = np.concatenate([groups[i] for i in pick])
        v = spearman(x[idx], y[idx])[0] - spearman(x0[idx], y[idx])[0]
        if math.isfinite(v):
            d.append(v)
    arr = np.array(d) if d else np.array([float("nan")])
    delta = ic - ic0 if math.isfinite(ic) and math.isfinite(ic0) else float("nan")
    return {"n": int(n), "blocks": len(groups), "ic": ic, "ic_flat": ic0, "delta": delta,
            "se": float(np.std(arr, ddof=1)) if len(arr) > 1 else float("nan"),
            "ci95": ([float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))]
                     if d else None)}


def ic_pair(sig: pd.Series, flat: pd.Series, candles: list[Candle], h: int,
            stride: int, **kw) -> dict:
    """ΔIC a horizonte `h` tomando una muestra cada `stride` instantes (sin solape)."""
    t = sig.index.to_numpy()[::stride]
    y = forward_returns(candles, t, h)
    out = block_delta(sig.to_numpy()[::stride], flat.to_numpy()[::stride], y, t, **kw)
    return {"h": h, "stride": stride, **out}


def _bt_row(candles: list[Candle], funding, sig: pd.Series, cut: int, symbol: str) -> dict:
    """Backtest T25 de la regla fija de T44 con el umbral de SU propia variante."""
    thr = float(np.quantile(np.abs(sig[sig.index < cut].to_numpy()), Q_SIGNAL))
    wins, pooled = backtest(candles, funding, sig[sig.index >= cut], thr, cut, symbol)
    m = compute_metrics(pooled, BT.initial_equity, BT.bars_per_year, n_boot=0)
    return {"thr": thr, "windows": len(wins),
            **{k: m[k] for k in ("n_trades", "sharpe", "expectancy_r", "max_drawdown")}}


def evaluate(df: pd.DataFrame, candles: list[Candle], funding, symbol: str,
             log: Callable[[str], None] = print) -> dict:
    """Medición completa de T197. Si no hay potencia, no se calcula nada sobre la prueba."""
    asofs = sorted(int(a) for a in df["asof"].unique())
    cut = split_at(asofs)
    disc, test = df[df["asof"] < cut], df[df["asof"] >= cut]
    agents = voters(df)
    reg = regime_by_asof(df)
    labelled = sum(1 for a in asofs if reg.get(a))
    cover = {a: df[df.agent == a].status.value_counts(normalize=True).round(4).to_dict()
             for a in sorted(set(df.agent))}
    out: dict = {
        "symbol": symbol, "timeframe": "1h", "asofs": len(asofs), "from": asofs[0],
        "to": asofs[-1], "cut": cut, "panel_step": PANEL_STEP, "voters": agents,
        "regime_labelled": labelled, "regime_share": round(labelled / len(asofs), 4),
        "regime_counts": {g: sum(1 for a in asofs if reg.get(a) == g) for g in REGIMES},
        "coverage": cover, "gate": {"mde": GATE_MDE, "delta": GATE_DELTA},
    }
    if labelled < MIN_LABELLED * len(asofs):
        out["verdict"] = "NO MEDIBLE"
        out["why"] = (f"`regime` etiqueta {labelled}/{len(asofs)} instantes "
                      f"({out['regime_share']:.1%} < 80 %, §6 del pre-registro)")
        return out

    # --- Descubrimiento: multiplicadores y potencia. La prueba no se mira todavía.
    detail = agent_ic(disc, candles, agents, H_PRIMARY)
    mult, table = multipliers(detail)
    out["ic_discovery"] = detail
    out["cells"] = table
    out["multipliers"] = mult
    moved = sum(1 for r in table if r["m"] != M_FLAT)
    log(f"descubrimiento: {len(table)} celdas, {moved} fuera de 1,0")
    if not mult:
        out["verdict"] = "NO SE ADOPTA"
        out["why"] = ("ninguna celda cruza ±0,02 de IC con n >= 200: la variante por régimen es "
                      "idéntica a la plana por construcción, no hay nada que medir en la prueba")
        return out

    p_flat, p_reg = SynthesisParams(), SynthesisParams(regime_weights=mult)
    by_disc, by_test = reports_by_asof(disc), reports_by_asof(test)
    s_flat_d = synth_signal(by_disc, p_flat, agents, reg, False)
    s_reg_d = synth_signal(by_disc, p_reg, agents, reg, True)
    d_disc = ic_pair(s_reg_d, s_flat_d, candles, H_PRIMARY, 1)
    n_test = len(test["asof"].unique())
    se_obs = d_disc["se"] * math.sqrt(max(d_disc["n"], 1))      # SE -> sd por observación
    out["power"] = {"delta_discovery": d_disc["delta"], "se_discovery": d_disc["se"],
                    "n_discovery": d_disc["n"], "n_test": n_test,
                    "mde": mde(se_obs, n_test)}
    log(f"potencia: MDE {out['power']['mde']:.4f} frente a la puerta {GATE_MDE}")
    if out["power"]["mde"] > GATE_MDE:
        out["verdict"] = "SIN POTENCIA"
        out["why"] = (f"la mejora mínima detectable de IC es {out['power']['mde']:.4f}, por encima"
                      f" de la puerta pre-registrada de {GATE_MDE}: la prueba no se mira")
        return out

    # --- Prueba (solo con potencia): primaria, secundaria y costos.
    s_flat = synth_signal(by_test, p_flat, agents, reg, False)
    s_reg = synth_signal(by_test, p_reg, agents, reg, True)
    primary = ic_pair(s_reg, s_flat, candles, H_PRIMARY, 1)
    secondary = ic_pair(s_reg, s_flat, candles, H_SECONDARY, H_SECONDARY // PANEL_STEP)
    flat_bt = _bt_row(candles, funding, pd.concat([s_flat_d, s_flat]), cut, symbol)
    reg_bt = _bt_row(candles, funding, pd.concat([s_reg_d, s_reg]), cut, symbol)
    d_exp = (reg_bt["expectancy_r"] or 0.0) - (flat_bt["expectancy_r"] or 0.0)
    out["test"] = {"primary": primary, "secondary": secondary,
                   "backtest": {"flat": flat_bt, "regime": reg_bt},
                   "delta_expectancy_r": d_exp,
                   "delta_sharpe": (reg_bt["sharpe"] or 0.0) - (flat_bt["sharpe"] or 0.0)}
    ci = primary["ci95"]
    ok_delta = primary["delta"] >= GATE_DELTA and ci is not None and ci[0] > 0
    out["verdict"] = "SE ADOPTA" if ok_delta and d_exp >= 0 else "NO SE ADOPTA"
    out["why"] = (f"dIC {primary['delta']:+.4f} (IC95 {ci}) frente a la puerta +{GATE_DELTA}; "
                  f"dE[R] {d_exp:+.4f}")
    log(f"prueba: {out['verdict']} - {out['why']}")
    return out
