"""Contribución marginal de los agentes nuevos en la síntesis (T44), fuera de muestra.

Sobre el panel histórico (`agent_panel`, cada 4 velas de 1 h) se reconstruye la síntesis con y
sin cada agente nuevo y se mide, SOLO en la mitad de prueba:
- IC de Spearman entre `sesgo × confianza` y el log-retorno a h velas (muestras sin solape);
- backtest T25 (`run_backtest` + `walk_forward`, costos de perpetuo) de una regla fija: opera
  la señal de la síntesis cuando |sesgo × confianza| supera el cuantil `Q_SIGNAL` de SU
  variante en la mitad de descubrimiento; SL a `SL_ATR`·ATR, TP a `RR`·riesgo.
La correlación entre reportes (que fija la penalización) también sale de la mitad de
descubrimiento. Regla de decisión fijada antes de mirar la prueba: `RULE`.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np
import pandas as pd

from eim.agents.levels.pivots import atr
from eim.analytics.technical_ic import spearman
from eim.backtest.edge import sharpe_diff_pvalue
from eim.backtest.engine import BacktestResult
from eim.backtest.metrics import compute_metrics
from eim.backtest.params import BacktestParams
from eim.backtest.report import pool
from eim.backtest.strategy import Signal
from eim.backtest.walkforward import walk_forward
from eim.core import AgentReport, Candle, MarketSnapshot
from eim.synthesis import SynthesisParams, synthesize
from eim.synthesis.params import MODERATE_WEIGHT, NON_DIRECTIONAL

NEW = ("technical", "smart_money")
PEERS = ("ema", "structure")           # existentes con los que se mide la redundancia
DISC_FRAC = 0.5                        # primera mitad: descubrimiento; segunda: prueba
Q_SIGNAL = 0.8                         # opera el 20 % de señales más fuertes de cada variante
SL_ATR, RR, ATR_N = 1.5, 2.0, 14
HORIZONS = (4, 24)                     # velas de 1 h
PANEL_STEP = 4                         # el panel tiene un instante cada 4 velas
WIN_TEST = 2160                        # ventana de prueba de 90 días (walk-forward T25)
WARMUP = 500
N_BOOT = 1000
BT = BacktestParams(max_hold_bars=48)
RULE = ("aporta ⇔ en la mitad de prueba de CADA activo, con el agente a peso moderado: "
        "Sharpe agregado, expectativa por operación (R) e IC a 24 velas mejoran a la vez "
        "frente a la síntesis sin él, y el Sharpe mejora en ≥ 60 % de las ventanas de 90 días")
WIN_SHARE = 0.6


def reports_by_asof(df: pd.DataFrame) -> dict[int, list[AgentReport]]:
    """Reportes mínimos (lo que lee la síntesis) por instante; sin validar (internos)."""
    out: dict[int, list[AgentReport]] = {}
    for a, ag, b, c, st in df[["asof", "agent", "bias", "conf", "status"]].itertuples(
            index=False):
        out.setdefault(int(a), []).append(AgentReport.model_construct(
            agent_id=ag, version="panel", asof=int(a), bias=float(b), confidence=float(c),
            horizon_bars=0, evidence=[], metrics={}, warnings=[], overlays=[], status=st))
    return out


def split_at(asofs: list[int], frac: float = DISC_FRAC) -> int:
    """Primer `asof` de la mitad de prueba."""
    return asofs[int(len(asofs) * frac)]


def correlations(df: pd.DataFrame, agents: tuple[str, ...], peers: tuple[str, ...]) -> dict:
    """ρ de Pearson (y Spearman) del sesgo entre pares, en las velas en que ambos tienen datos."""
    live = df[df.status != "no_data"].pivot_table(index="asof", columns="agent", values="bias")
    out: dict = {}
    for a in agents:
        for p in peers:
            if a not in live or p not in live:
                out[f"{a}~{p}"] = {"n": 0, "pearson": None, "spearman": None}
                continue
            pair = live[[a, p]].dropna()
            n = len(pair)
            ok = n >= 30 and pair[a].std() > 0 and pair[p].std() > 0
            out[f"{a}~{p}"] = {
                "n": n, "pearson": float(pair[a].corr(pair[p])) if ok else None,
                "spearman": spearman(pair[a].to_numpy(), pair[p].to_numpy())[0] if ok else None}
    return out


def variants(corr: dict) -> dict[str, SynthesisParams]:
    """Síntesis base (sin agentes nuevos) y con cada uno; ρ de descubrimiento para penalizar."""
    rho: dict[str, dict[str, float]] = {a: {} for a in NEW}
    for a in NEW:
        for p in PEERS:
            r = corr.get(f"{a}~{p}", {}).get("pearson")
            if r is not None:
                rho[a][p] = round(float(r), 3)
    zero = {a: 0.0 for a in NEW}

    def sp(w: dict[str, float], penal: bool = True) -> SynthesisParams:
        return SynthesisParams(weights={**zero, **w},
                               correlation={a: rho[a] for a in w if penal and rho[a]})
    out = {"base": sp({})}
    for a in NEW:
        out[f"+{a}"] = sp({a: MODERATE_WEIGHT})
        out[f"+{a} (peso 1, sin penalización)"] = sp({a: 1.0}, penal=False)
    out["+ambos"] = sp({a: MODERATE_WEIGHT for a in NEW})
    return out


def synth_series(by_asof: dict[int, list[AgentReport]], p: SynthesisParams,
                 expected: list[str]) -> pd.Series:
    """`sesgo × confianza` de la síntesis por instante (0 si no hay tesis)."""
    vals = {}
    for a, reps in by_asof.items():
        s = synthesize(reps, p, expected=expected)
        vals[a] = 0.0 if s is None else s.bias * s.confidence
    return pd.Series(vals).sort_index()


def forward_returns(candles: list[Candle], asofs: np.ndarray, h: int) -> np.ndarray:
    """Log-retorno del cierre de la vela que cierra en `asof` al de h velas después."""
    step = candles[1].t - candles[0].t
    idx = {c.t: i for i, c in enumerate(candles)}
    close = np.array([c.c for c in candles])
    out = np.full(len(asofs), np.nan)
    for k, a in enumerate(asofs):
        i = idx.get(int(a) - step)
        if i is not None and i + h < len(close):
            out[k] = math.log(close[i + h] / close[i])
    return out


def ic_test(sig: pd.Series, base: pd.Series, candles: list[Candle], h: int, stride: int,
            seed: int = 0) -> dict:
    """IC de la variante, de la base y su diferencia (bootstrap pareado, muestras sin solape)."""
    a = sig.index.to_numpy()[::stride]
    y = forward_returns(candles, a, h)
    x, x0 = sig.to_numpy()[::stride], base.to_numpy()[::stride]
    ic, n, p = spearman(x, y)
    ic0 = spearman(x0, y)[0]
    rng = np.random.default_rng(seed)
    ok = ~np.isnan(y)
    xs, x0s, ys = x[ok], x0[ok], y[ok]
    d = []
    for _ in range(N_BOOT):
        i = rng.integers(0, len(ys), len(ys))
        d.append(spearman(xs[i], ys[i])[0] - spearman(x0s[i], ys[i])[0])
    d = [v for v in d if math.isfinite(v)]
    ci = [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))] if d else None
    return {"h": h, "n": n, "ic": ic, "p": p, "ic_base": ic0,
            "delta": ic - ic0 if math.isfinite(ic) and math.isfinite(ic0) else None,
            "delta_ci95": ci}


class PanelStrategy:
    """Opera la síntesis reconstruida: señal en `asof` si |s| ≥ umbral (fijado en descubrimiento)."""

    def __init__(self, sig: dict[int, float], thr: float) -> None:
        self.sig, self.thr = sig, thr

    def on_bar(self, snap: MarketSnapshot) -> Signal | None:
        s = self.sig.get(snap.asof)
        if s is None or abs(s) < self.thr or self.thr <= 0:
            return None
        cs = snap.candles[-(ATR_N + 1):]
        a = atr(np.array([c.h for c in cs]), np.array([c.l for c in cs]),
                np.array([c.c for c in cs]), ATR_N)
        close, side = cs[-1].c, 1 if s > 0 else -1
        if a <= 0:
            return None
        risk = SL_ATR * a
        return Signal(side=side, sl=close - side * risk, tp=close + side * RR * risk,
                      tag=str(snap.asof))


def backtest(candles: list[Candle], funding, sig: pd.Series, thr: float, test_from_t: int,
             symbol: str) -> tuple[list[tuple[dict, BacktestResult]], BacktestResult]:
    """Walk-forward T25 en la mitad de prueba (ventanas de 90 días, capital propio cada una)."""
    start = next(i for i, c in enumerate(candles) if c.t >= test_from_t)
    d = {int(k): float(v) for k, v in sig.items()}
    wins = walk_forward(candles, funding, lambda _t: PanelStrategy(d, thr), BT, train=start,
                        test=WIN_TEST, warmup=WARMUP, symbol=symbol, timeframe="1h")
    return wins, pool([r for _, r in wins], BT.initial_equity)


def _returns(res: BacktestResult) -> np.ndarray:
    eq = np.array(res.equity, float)
    return np.diff(eq) / eq[:-1] if len(eq) > 1 else np.array([])


def evaluate(df: pd.DataFrame, candles: list[Candle], funding, symbol: str,
             log: Callable[[str], None] = print) -> dict:
    """Estudio completo de un activo: correlaciones, IC y backtest por variante."""
    asofs = sorted(df["asof"].unique().tolist())
    cut = split_at(asofs)
    disc, test = df[df["asof"] < cut], df[df["asof"] >= cut]
    corr_disc = correlations(disc, NEW, PEERS + ("vwap", "price_action", "levels"))
    corr_test = correlations(test, NEW, PEERS)
    agents = sorted(set(df.agent) - NON_DIRECTIONAL - {"regime"})
    cover = {a: df[df.agent == a].status.value_counts(normalize=True).round(4).to_dict()
             for a in sorted(set(df.agent))}
    by = reports_by_asof(df)
    vs = variants(corr_disc)
    sigs = {k: synth_series(by, p, agents) for k, p in vs.items()}
    out: dict = {"symbol": symbol, "asofs": len(asofs), "from": asofs[0], "to": asofs[-1],
                 "cut": cut, "coverage": cover, "corr_disc": corr_disc, "corr_test": corr_test,
                 "variants": {}}
    base_wins = base_pool = None
    for k in vs:  # "base" primero (orden de inserción)
        s = sigs[k]
        thr = float(np.quantile(np.abs(s[s.index < cut].to_numpy()), Q_SIGNAL))
        st = s[s.index >= cut]
        wins, pooled = backtest(candles, funding, st, thr, cut, symbol)
        m = compute_metrics(pooled, BT.initial_equity, BT.bars_per_year, n_boot=N_BOOT)
        per = [compute_metrics(r, BT.initial_equity, BT.bars_per_year, n_boot=0)
               for _, r in wins]
        row = {"weights": dict(vs[k].weights), "correlation": vs[k].correlation, "thr": thr,
               "metrics": {x: m[x] for x in ("n_trades", "total_return", "sharpe",
                                             "expectancy_r", "win_rate", "max_drawdown")},
               "ci95": m["ci95"], "windows": [{"from": candles[w["test_from"]].t, "sharpe": pm["sharpe"],
                                               "n": pm["n_trades"],
                                               "exp_r": pm["expectancy_r"]}
                                              for (w, _), pm in zip(wins, per, strict=True)],
               "ic": [ic_test(st, sigs["base"][sigs["base"].index >= cut], candles, h,
                              max(1, h // PANEL_STEP)) for h in HORIZONS],
               "identical_to_base": bool(np.allclose(s.to_numpy(), sigs["base"].to_numpy()))}
        if k == "base":
            base_wins, base_pool = wins, pooled
        else:
            p, ci = sharpe_diff_pvalue(_returns(pooled), _returns(base_pool), BT.bars_per_year)
            row["vs_base"] = {"sharpe_p": p, "sharpe_diff_ci95": ci,
                              "win_share": float(np.mean([
                                  a["sharpe"] > b["sharpe"] for a, b in zip(
                                      row["windows"], out["variants"]["base"]["windows"],
                                      strict=True)])) if base_wins else None}
        out["variants"][k] = row
        log(f"{symbol} {k}: Sharpe {m['sharpe']:+.2f}, ops {m['n_trades']}, "
            f"IC24 {row['ic'][1]['ic']:+.4f}")
    return out


def passes(res: dict, agent: str) -> tuple[bool, str]:
    """Aplica `RULE` a un activo; (aporta, motivo)."""
    v, b = res["variants"][f"+{agent}"], res["variants"]["base"]
    cov = res["coverage"].get(agent)
    if not cov or cov.get("no_data", 0.0) >= 1.0:
        return False, "sin datos en todo el histórico (100 % `no_data`): no medible"
    dm = {k: (v["metrics"][k] or 0) - (b["metrics"][k] or 0) for k in ("sharpe", "expectancy_r")}
    d_ic = v["ic"][1]["delta"]
    ws = v["vs_base"]["win_share"] or 0.0
    ok = dm["sharpe"] > 0 and dm["expectancy_r"] > 0 and (d_ic or 0) > 0 and ws >= WIN_SHARE
    why = (f"ΔSharpe {dm['sharpe']:+.2f}, ΔE[R] {dm['expectancy_r']:+.3f}, "
           f"ΔIC24 {d_ic if d_ic is None else round(d_ic, 4)}, gana {ws:.0%} de ventanas")
    return ok, why
