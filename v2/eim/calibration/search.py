"""Búsqueda con optuna (solo ventanas de entrenamiento) y selección por estabilidad ±10 %."""

from __future__ import annotations

from dataclasses import dataclass

from eim.backtest.params import BacktestParams
from eim.calibration.evaluate import DEFAULT_OBJECTIVE, ObjectiveParams, Series, evaluate
from eim.calibration.space import perturbations, suggest


@dataclass
class Stability:
    score: float                 # objetivo sin perturbar
    worst: float                 # peor objetivo con un parámetro a ±10 %
    worst_label: str
    drops: dict[str, float]      # caída del objetivo por perturbación
    peaked: bool                 # "picuda": alguna perturbación cae más de `max_drop`


def stability(series: Series, values: dict, windows: list[tuple[int, int]],
              bt: BacktestParams, base: dict, op: ObjectiveParams, max_drop: float = 0.5,
              score: float | None = None) -> Stability:
    """Sensibilidad del objetivo a mover cada parámetro ±10 %."""
    s0 = score if score is not None else evaluate(series, values, windows, bt, base, op).score
    drops: dict[str, float] = {}
    for label, v in perturbations(values):
        drops[label] = s0 - evaluate(series, v, windows, bt, base, op).score
    worst_label = max(drops, key=drops.get) if drops else ""
    worst = s0 - drops[worst_label] if drops else s0
    return Stability(score=s0, worst=worst, worst_label=worst_label, drops=drops,
                     peaked=bool(drops) and drops[worst_label] > max_drop)


@dataclass
class SearchResult:
    values: dict                 # elegido (vigente si nada lo supera de forma estable)
    train_score: float
    default_score: float
    stability: Stability | None
    n_trials: int
    candidates: list[dict]       # top-k evaluados por estabilidad
    kept_default: bool


def optimize(series: Series, windows: list[tuple[int, int]], bt: BacktestParams, base: dict,
             op: ObjectiveParams = DEFAULT_OBJECTIVE, n_trials: int = 40, top_k: int = 3,
             seed: int = 0, max_drop: float = 0.5) -> SearchResult:
    """TPE con semilla; el vigente entra como primer trial. Entre los `top_k` mejores se elige
    el de mejor objetivo en el PEOR caso de ±10 % (descarta soluciones picudas). Si ninguno
    supera al vigente en ese peor caso, se conserva el vigente."""
    import optuna  # dependencia opcional: solo para calibrar

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="maximize",
                                sampler=optuna.samplers.TPESampler(seed=seed))
    study.enqueue_trial(dict(base))

    def objective(trial) -> float:
        return evaluate(series, suggest(trial), windows, bt, base, op).score

    study.optimize(objective, n_trials=n_trials)
    done = [t for t in study.trials if t.value is not None]
    default_score = done[0].value
    ranked = sorted(done[1:], key=lambda t: -t.value)
    seen: list[dict] = []
    cands = []
    for t in ranked:
        if len(cands) >= top_k or t.value <= default_score:
            break
        if t.params in seen:
            continue
        seen.append(t.params)
        st = stability(series, dict(t.params), windows, bt, base, op, max_drop, t.value)
        cands.append({"values": dict(t.params), "score": t.value, "worst": st.worst,
                      "worst_label": st.worst_label, "peaked": st.peaked, "_st": st})
    ok = [c for c in cands if not c["peaked"] and c["worst"] > default_score]
    best = max(ok, key=lambda c: c["worst"]) if ok else None
    pub = [{k: v for k, v in c.items() if k != "_st"} for c in cands]
    if best is None:
        return SearchResult(dict(base), default_score, default_score, None, len(done), pub, True)
    return SearchResult(best["values"], best["score"], default_score, best["_st"], len(done),
                        pub, False)
