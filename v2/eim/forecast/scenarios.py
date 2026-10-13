"""De trayectorias a exactamente 3 escenarios (alcista, neutral, bajista).

Cada trayectoria se clasifica por su retorno terminal: |Δ| < `neutral_atr`·ATR → neutral; el
resto por signo. Probabilidad = proporción de trayectorias del grupo (suman 1). Por grupo: mediana
por instante, banda = cuantiles 10–90 y la vela representativa es el MEDOIDE (una trayectoria real
del grupo, nunca un promedio de velas). Todas las velas son simuladas.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from eim.agents.levels.pivots import atr
from eim.core import Candle, ForecastSet, MarketSnapshot, Scenario
from eim.data.timeframes import tf_ms
from eim.forecast.base_engine import BaseEngine
from eim.forecast.engine import Engine, check_horizon

IDS = ("bull", "neutral", "bear")
LABEL = {"bull": "alcista", "neutral": "neutral", "bear": "bajista"}


@dataclass(frozen=True)
class ScenarioParams:
    neutral_atr: float = 2.0  # umbral neutral: múltiplo de ATR del retorno terminal
    band: tuple[float, float] = (0.10, 0.90)
    atr_period: int = 14
    invalidation_atr: float = 1.5  # distancia de invalidación por defecto (múltiplos de ATR)
    medoid_sample: int = 200  # máx. de trayectorias del grupo para calcular el medoide
    min_group: int = 5  # trayectorias mostradas si un grupo queda vacío
    seed: int = 0


def classify(
    paths: np.ndarray, last_close: float, atr_abs: float, neutral_atr: float
) -> np.ndarray:
    """Etiqueta por trayectoria: 0 alcista, 1 neutral, 2 bajista."""
    delta = paths[:, -1, 3] - last_close
    lab = np.where(delta > 0, 0, 2)
    lab[np.abs(delta) < neutral_atr * atr_abs] = 1
    return lab


def medoid(closes: np.ndarray, sample: int, rng: np.random.Generator) -> int:
    """Índice (en `closes`, forma (m, h)) de la trayectoria más central en log-precio."""
    m = len(closes)
    cand = np.arange(m) if m <= sample else np.sort(rng.choice(m, sample, replace=False))
    x = np.log(closes[cand])
    d = np.linalg.norm(x[:, None, :] - x[None, :, :], axis=2).sum(axis=1)
    return int(cand[int(d.argmin())])


def _tp(times: list[int], vals: np.ndarray) -> list[tuple[int, float]]:
    return [(t, float(v)) for t, v in zip(times, vals, strict=True)]


def _invalidation(sid: str, last: float, atr_abs: float, p: ScenarioParams,
                  stops: dict[str, float] | None) -> dict:
    if sid == "neutral":
        lo, hi = last - p.neutral_atr * atr_abs, last + p.neutral_atr * atr_abs
        return {"level": hi, "level_low": lo,
                "condition": f"cierre fuera de [{lo:.2f}, {hi:.2f}] (sale del rango neutral)"}
    k = p.invalidation_atr * atr_abs
    if stops and sid in stops:
        lvl, src = stops[sid], "SL del plan"
    else:
        sign = -1 if sid == "bull" else 1
        lvl, src = last + sign * k, f"último cierre {'−' if sign < 0 else '+'} ATR"
    way = "bajo" if sid == "bull" else "sobre"
    return {"level": float(lvl),
            "condition": f"cierre {way} {lvl:.2f} ({src}) anula el escenario {LABEL[sid]}"}


def build_scenarios(
    paths: np.ndarray,
    snapshot: MarketSnapshot,
    engine_name: str,
    params: ScenarioParams | None = None,
    stops: dict[str, float] | None = None,
) -> tuple[list[Scenario], list[str]]:
    p = params or ScenarioParams()
    n, h, _ = paths.shape
    cs = snapshot.candles
    a = np.array([[c.o, c.h, c.l, c.c] for c in cs[-200:]], dtype=float)
    last = float(cs[-1].c)
    atr_abs = atr(a[:, 1], a[:, 2], a[:, 3], p.atr_period)
    step = tf_ms(snapshot.timeframe)
    times = [cs[-1].t + (i + 1) * step for i in range(h)]
    lab = classify(paths, last, atr_abs, p.neutral_atr)
    rng = np.random.default_rng(p.seed)
    delta = paths[:, -1, 3] - last
    warnings: list[str] = []
    out: list[Scenario] = []
    for k, sid in enumerate(IDS):
        idx = np.flatnonzero(lab == k)
        prob = len(idx) / n
        if len(idx) == 0:  # grupo vacío: se muestran las trayectorias más cercanas, prob. 0
            key = -delta if sid == "bull" else delta if sid == "bear" else np.abs(delta)
            idx = np.argsort(key)[: min(p.min_group, n)]
            warnings.append(f"escenario {LABEL[sid]} sin trayectorias: probabilidad 0 "
                            f"(se muestran las {len(idx)} más cercanas)")
        g = paths[idx]
        closes = g[:, :, 3]
        med = g[medoid(closes, p.medoid_sample, rng) if len(idx) > 1 else 0]
        lo_q, hi_q = np.quantile(closes, p.band, axis=0)
        candles = [Candle(t=t, o=float(r[0]), h=float(r[1]), l=float(r[2]), c=float(r[3]), v=0.0)
                   for t, r in zip(times, med, strict=True)]
        narrative = (
            f"Escenario {LABEL[sid]}: {prob:.0%} de {n} trayectorias simuladas (motor "
            f"{engine_name}); mediana al final {np.median(closes[:, -1]):.2f}, banda 10–90 "
            f"[{lo_q[-1]:.2f}, {hi_q[-1]:.2f}]. Es una simulación estadística, no una predicción; "
            f"las velas mostradas son simuladas (medoide de {len(idx)} trayectorias)."
        )
        out.append(Scenario(
            id=sid, probability=prob, path=_tp(times, np.median(closes, axis=0)),
            band_low=_tp(times, lo_q), band_high=_tp(times, hi_q), candles=candles,
            invalidation=_invalidation(sid, last, atr_abs, p, stops), narrative=narrative,
            n_paths=len(idx), engine=engine_name))
    return out, warnings


QUANTILE_LEVELS = (5, 10, 25, 50, 75, 90, 95)


def _quantiles(paths: np.ndarray, snapshot: MarketSnapshot) -> dict[str, list[tuple[int, float]]]:
    """Cuantiles del cierre por instante sobre todas las trayectorias (insumo de T19)."""
    last_t = snapshot.candles[-1].t
    step = tf_ms(snapshot.timeframe)
    times = [last_t + (i + 1) * step for i in range(paths.shape[1])]
    qs = np.quantile(paths[:, :, 3], [q / 100 for q in QUANTILE_LEVELS], axis=0)
    return {str(q): _tp(times, row) for q, row in zip(QUANTILE_LEVELS, qs, strict=True)}


def _with_drift(engine: Engine, drift: float | None) -> Engine:
    params = getattr(engine, "params", None)
    if drift is None or params is None or not hasattr(params, "drift"):
        return engine
    return type(engine)(replace(params, drift=drift))


def build_forecast(
    snapshot: MarketSnapshot,
    horizon: int = 25,
    n: int = 500,
    engine: Engine | None = None,
    params: ScenarioParams | None = None,
    drift: float | None = None,
    stops: dict[str, float] | None = None,
) -> ForecastSet:
    """`ForecastSet` a partir de un snapshot. `drift` (log-retorno/vela) inclina el motor (T20)."""
    check_horizon(horizon)
    eng = _with_drift(engine or BaseEngine(), drift)
    paths = eng.sample(snapshot, horizon, n)
    scen, warns = build_scenarios(paths, snapshot, eng.name, params, stops)
    if drift:
        warns.append(f"deriva externa aplicada: {drift:+.6f} por vela")
    return ForecastSet(
        symbol=snapshot.symbol, timeframe=snapshot.timeframe, made_at=snapshot.asof,
        horizon_bars=horizon, scenarios=scen, engine=eng.name, baseline_engine="base",
        warnings=warns, quantiles=_quantiles(paths, snapshot))
