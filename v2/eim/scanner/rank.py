"""Ranking global comparable del escáner (T95, 1/3). Puro: sin E/S salvo leer/guardar los pesos.

Hace comparables oportunidades de instrumentos, horizontes y clases distintos:

- **Unidades comparables.** La ventaja esperada se mide en múltiplos de la **σ de su propio
  horizonte** (σ por vela de las últimas `SIGMA_BARS` velas × √horizonte) y en múltiplos de **R**
  (distancia a la invalidación del escenario a favor, que es el SL del plan cuando lo hay; si no,
  R = 1 σ del horizonte y se dice). Es **neta del costo de ida y vuelta de su clase** (T92, el que
  ya trae la oportunidad). Al ser fracciones del precio, no dependen de la escala ni de la divisa.
  La **incertidumbre** es la dispersión de los tres escenarios alrededor de la esperanza, también
  en σ del horizonte. Ningún horizonte se compara sin normalizar: todo va en σ de su horizonte.
- **Cuatro puntuaciones separadas** (0–1, más alto = más favorable): calidad de la señal,
  viabilidad y riesgo/costos (las de T94, sin tocarlas) y ventaja (Φ de la ventaja neta en σ).
- **La prioridad** (la única combinación) solo se calcula al final, con pesos versionados. Los de
  partida son **iguales y sin calibrar** (pre-registro `PLAN/notas/T95_preregistro.md`); `calibrate`
  los ajusta **fuera de muestra** con resultados hacia adelante ya maduros y solo los adopta si
  mejoran a los iguales en la mitad posterior (nunca se fijan para maximizar el pasado).

Una oportunidad sin costo de su clase o sin σ medible queda **no comparable** (sin prioridad) y
se dice por qué: no se inventa un número para poder ordenarla.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import NormalDist

import numpy as np

RANK_VERSION = "1.0.0"
SIGMA_BARS = 60
MIN_SIGMA_RETURNS = 20
SCORE_KEYS = ("quality", "viability", "risk", "edge")
WEIGHTS_FILE = "rank_weights.json"
#: Calibración: rejilla del símplex, mínimo de resultados por mitad.
GRID_STEP = 0.25
MIN_FIT, MIN_HOLDOUT = 100, 100
_N = NormalDist()


@dataclass(frozen=True)
class Weights:
    values: dict[str, float]
    calibrated: bool = False
    source: str = "iguales (0,25 cada una), sin calibrar: pre-registro T95"

    @property
    def fingerprint(self) -> str:
        raw = json.dumps({k: round(float(self.values[k]), 6) for k in SCORE_KEYS}, sort_keys=True)
        return hashlib.blake2b(raw.encode(), digest_size=6).hexdigest()

    def as_json(self) -> dict:
        return {"values": {k: round(float(self.values[k]), 6) for k in SCORE_KEYS},
                "calibrated": self.calibrated, "source": self.source,
                "fingerprint": self.fingerprint}


DEFAULT_WEIGHTS = Weights(dict.fromkeys(SCORE_KEYS, 0.25))


def _clean(values: Mapping) -> dict[str, float] | None:
    try:
        v = {k: float(values[k]) for k in SCORE_KEYS}
    except (KeyError, TypeError, ValueError):
        return None
    total = sum(v.values())
    if any(x < 0 or not math.isfinite(x) for x in v.values()) or total <= 0:
        return None
    return {k: x / total for k, x in v.items()}


def weights_path(data_dir: str | Path) -> Path:
    return Path(data_dir) / "scanner" / WEIGHTS_FILE


def load_weights(data_dir: str | Path | None) -> Weights:
    """Pesos adoptados por `calibrate` (si los hay y son válidos); si no, los iguales."""
    if data_dir is None:
        return DEFAULT_WEIGHTS
    try:
        raw = json.loads(weights_path(data_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return DEFAULT_WEIGHTS
    v = _clean(raw.get("values") or {})
    if v is None:
        return DEFAULT_WEIGHTS
    return Weights(v, bool(raw.get("calibrated")), str(raw.get("source") or "archivo"))


def save_weights(data_dir: str | Path, w: Weights, calibration: Mapping) -> Path:
    f = weights_path(data_dir)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(w.as_json() | {"calibration": dict(calibration)},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(f)
    return f


def bar_sigma(closes: Sequence[float]) -> float | None:
    """σ de los rendimientos logarítmicos por vela de las últimas `SIGMA_BARS` velas."""
    c = np.asarray(closes, dtype=float)[-(SIGMA_BARS + 1):]
    c = c[np.isfinite(c) & (c > 0)]
    if len(c) < MIN_SIGMA_RETURNS + 1:
        return None
    s = float(np.std(np.diff(np.log(c)), ddof=1))
    return s if s > 0 and math.isfinite(s) else None


@dataclass(frozen=True)
class Normalized:
    opportunity_id: str
    instrument_id: str
    symbol: str
    side: str
    horizon_bars: int
    horizon_ms: int
    sigma_bar: float | None
    sigma_h: float | None
    gross: float | None              # esperanza bruta del lado, fracción del precio
    cost: float | None               # ida y vuelta de su clase, fracción del precio
    net: float | None
    edge_sigma: float | None         # ventaja neta en σ de su horizonte
    edge_r: float | None             # ventaja neta en R
    r_unit: float | None             # R como fracción del precio
    r_source: str
    uncertainty_sigma: float | None  # dispersión de los escenarios, en σ del horizonte
    scores: dict[str, float | None]
    comparable: bool
    notes: tuple[str, ...] = ()

    def as_json(self) -> dict:
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, float):
                d[k] = round(v, 6)
        d["scores"] = {k: None if v is None else round(v, 6) for k, v in self.scores.items()}
        d["notes"] = list(self.notes)
        return d


def _f(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def normalize(opp: Mapping, closes: Sequence[float]) -> Normalized:
    """La oportunidad en unidades comparables (fracciones del precio, σ y R de su horizonte)."""
    side = 1 if opp["side"] == "largo" else -1
    h = int(opp["horizon_bars"])
    sc = opp["forecast"]["scenarios"]
    notes: list[str] = []
    last = _f(closes[-1]) if len(closes) else None
    sb = bar_sigma(closes)
    sh = sb * math.sqrt(h) if sb is not None else None
    if sh is None:
        notes.append(f"σ sin medir (< {MIN_SIGMA_RETURNS + 1} cierres válidos)")
    gross = disp = None
    if last and last > 0:
        ps = np.array([max(0.0, _f(sc[k]["p"]) or 0.0) for k in ("bull", "neutral", "bear")])
        rs = np.array([(_f(sc[k]["median_end"]) or last) / last - 1
                       for k in ("bull", "neutral", "bear")])
        if ps.sum() > 0:
            ps = ps / ps.sum()
            gross = float(side * (ps * rs).sum())
            disp = float(math.sqrt((ps * (side * rs - gross) ** 2).sum()))
    s = opp["scores"]
    cost = _f(s.get("components", {}).get("round_trip_cost"))
    if cost is None:
        notes.append("sin costo de ida y vuelta de su clase: no comparable")
    net = None if gross is None or cost is None else gross - cost
    fav = "bull" if side > 0 else "bear"
    inv = _f(sc[fav].get("invalidation"))
    if last and inv and inv > 0 and abs(last - inv) > 0:
        r_unit, r_source = abs(last - inv) / last, "invalidación del escenario a favor (SL)"
    else:
        r_unit, r_source = sh, "sin invalidación: R = 1 σ del horizonte (supuesto)"
    edge_sigma = None if net is None or not sh else net / sh
    edge_r = None if net is None or not r_unit else net / r_unit
    unc = None if disp is None or not sh else disp / sh
    scores = {"quality": _f(s.get("signal_quality")), "viability": _f(s.get("viability")),
              "risk": _f(s.get("risk_cost")),
              "edge": None if edge_sigma is None else _N.cdf(edge_sigma)}
    comparable = all(v is not None for v in scores.values())
    return Normalized(
        opportunity_id=opp["opportunity_id"], instrument_id=opp["instrument_id"],
        symbol=opp.get("symbol", ""), side=opp["side"], horizon_bars=h,
        horizon_ms=int(opp["horizon_ms"]), sigma_bar=sb, sigma_h=sh, gross=gross, cost=cost,
        net=net, edge_sigma=edge_sigma, edge_r=edge_r, r_unit=r_unit, r_source=r_source,
        uncertainty_sigma=unc, scores=scores, comparable=comparable, notes=tuple(notes))


def priority(n: Normalized | Mapping, w: Weights = DEFAULT_WEIGHTS) -> float | None:
    """La única combinación: Σ peso × puntuación, solo si las cuatro existen."""
    scores = n.scores if isinstance(n, Normalized) else n
    if any(scores.get(k) is None for k in SCORE_KEYS):
        return None
    return float(sum(w.values[k] * float(scores[k]) for k in SCORE_KEYS))


def rank(opps: Sequence[Mapping], closes: Mapping[str, Sequence[float]],
         w: Weights = DEFAULT_WEIGHTS) -> list[dict]:
    """Oportunidades por prioridad descendente (empates por id; las no comparables, al final)."""
    rows = []
    for o in opps:
        n = normalize(o, closes.get(o["instrument_id"], ()))
        rows.append({"opportunity_id": o["opportunity_id"], "instrument_id": o["instrument_id"],
                     "symbol": o.get("symbol", ""), "side": o["side"], "priority": priority(n, w),
                     "normalized": n.as_json()})
    rows.sort(key=lambda r: (r["priority"] is None, -(r["priority"] or 0.0),
                             r["opportunity_id"]))
    k = 0
    for r in rows:
        if r["priority"] is not None:
            k += 1
            r["priority"] = round(r["priority"], 6)
        r["position"] = k if r["priority"] is not None else None
    return rows


# --- calibración fuera de muestra ------------------------------------------------------------
def simplex(step: float = GRID_STEP) -> list[dict[str, float]]:
    n = round(1 / step)
    out = []
    for combo in itertools.product(range(n + 1), repeat=len(SCORE_KEYS)):
        if sum(combo) == n:
            out.append({k: c / n for k, c in zip(SCORE_KEYS, combo, strict=True)})
    return out


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3 or np.all(x == x[0]) or np.all(y == y[0]):
        return -math.inf
    from scipy.stats import spearmanr

    r = float(spearmanr(x, y).statistic)
    return r if math.isfinite(r) else -math.inf


def _r(x: float) -> float | None:
    return round(x, 6) if math.isfinite(x) else None


def _corr(rows: Sequence[Mapping], w: Mapping[str, float]) -> float:
    pr = np.array([sum(w[k] * r["scores"][k] for k in SCORE_KEYS) for r in rows])
    return _spearman(pr, np.array([r["outcome"] for r in rows], dtype=float))


def calibrate(rows: Sequence[Mapping], step: float = GRID_STEP, min_fit: int = MIN_FIT,
              min_holdout: int = MIN_HOLDOUT) -> dict:
    """Ajusta los pesos con resultados maduros (`t`, `scores`, `outcome` en σ) fuera de muestra.

    Mitad anterior en el tiempo: se elige la combinación del símplex con mayor correlación de
    rangos entre prioridad y resultado. Mitad posterior: se adopta solo si supera a los pesos
    iguales y es positiva. Si no hay muestra suficiente, se dice y no se adopta nada.
    """
    ok = sorted((r for r in rows if all(r["scores"].get(k) is not None for k in SCORE_KEYS)
                 and _f(r.get("outcome")) is not None), key=lambda r: r["t"])
    out = {"version": RANK_VERSION, "n": len(ok), "adopted": False, "step": step,
           "min_fit": min_fit, "min_holdout": min_holdout}
    if len(ok) < min_fit + min_holdout:
        return out | {"reason": f"muestra insuficiente: {len(ok)} resultados maduros < "
                                f"{min_fit + min_holdout}; siguen los pesos iguales"}
    cut = ok[len(ok) // 2]["t"]
    fit = [r for r in ok if r["t"] < cut]
    hold = [r for r in ok if r["t"] >= cut]
    if len(fit) < min_fit or len(hold) < min_holdout:
        return out | {"reason": "las dos mitades no llegan al mínimo (empates de fecha)"}
    best = max(simplex(step), key=lambda w: (_corr(fit, w), -max(w.values())))
    base = DEFAULT_WEIGHTS.values
    h_best, h_base = _corr(hold, best), _corr(hold, base)
    adopted = h_best > h_base and h_best > 0
    return out | {"adopted": adopted, "weights": best, "n_fit": len(fit), "n_holdout": len(hold),
                  "fit_corr": _r(_corr(fit, best)), "holdout_corr": _r(h_best),
                  "holdout_default_corr": _r(h_base),
                  "reason": ("mejora a los pesos iguales fuera de muestra" if adopted else
                             "no mejora a los pesos iguales fuera de muestra: siguen los iguales")}
