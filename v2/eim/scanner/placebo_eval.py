"""Evaluación del placebo y umbral vigente del panel (T95, entregable 4). Ver `placebo.py`.

`evaluate` compara el escaneo real con las réplicas sin estructura: umbral = cuantil (1 − α) del
máximo de prioridad por réplica (con él, en el (1 − α) de los universos sin estructura el panel no
mostraría nada), hallazgos reales por encima, falsos esperados por pasada (estimación de la tasa
de falsos descubrimientos) y p global de «el mejor hallazgo real supera al mejor del azar».
`write_threshold`/`load_threshold` guardan y leen `data/scanner/placebo.json`; el umbral solo
vale para las mismas versiones (agentes, pesos, ranking, etapa profunda y etapa 3): si cambia
alguna, queda desactualizado y ninguna candidata se marca por encima del azar.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

from eim.core.opportunity import stable_hash
from eim.scanner import rank, screen

PLACEBO_VERSION = "1.0.0"
THRESHOLD_FILE = "placebo.json"


def evaluate(real: Mapping, nulls: Sequence[Mapping], alpha: float = 0.05) -> dict:
    maxima = [m["max"] if m["max"] is not None else -math.inf for m in nulls]
    finite = [x for x in maxima if math.isfinite(x)]
    if finite:
        thr = float(np.quantile(np.array([x if math.isfinite(x) else -1.0 for x in maxima]),
                                1 - alpha, method="higher"))
        thr = max(thr, 0.0)
    else:
        thr = 0.0
    above = [sum(p >= thr for p in m["priorities"]) for m in nulls]
    pooled = [p for m in nulls for p in m["priorities"]]
    real_pr = list(real["priorities"])
    real_above = sum(p >= thr for p in real_pr)
    false_per_pass = float(np.mean(above)) if above else None
    real_max = real.get("max")
    beats = sum(x >= real_max for x in maxima) if real_max is not None else len(maxima)
    p_global = (1 + beats) / (1 + len(maxima)) if maxima else None
    fdr = (min(1.0, false_per_pass / real_above) if real_above and false_per_pass is not None
           else None)
    return {
        "alpha": alpha, "replicas": len(nulls), "threshold": round(thr, 6),
        "threshold_rule": f"cuantil {1 - alpha:.0%} (método «higher») del máximo por réplica",
        "null_max": [None if not math.isfinite(x) else round(x, 6) for x in maxima],
        "null_candidates_mean": float(np.mean([m["n_candidates"] for m in nulls])) if nulls
        else None,
        "null_rate_per_candidate": (round(float(np.mean([p >= thr for p in pooled])), 6)
                                    if pooled else None),
        "false_per_pass": None if false_per_pass is None else round(false_per_pass, 4),
        "real_candidates": real["n_candidates"], "real_max": real_max,
        "real_above": int(real_above), "fdr_estimate": None if fdr is None else round(fdr, 4),
        "p_global": None if p_global is None else round(p_global, 6),
        "beats_chance": bool(real_above > 0 and p_global is not None and p_global < alpha),
    }


def fingerprint(weights: rank.Weights, agents_fp: str, deep_versions: Mapping[str, str]) -> str:
    """Huella de todo lo que mueve la prioridad: si cambia, el umbral queda desactualizado."""
    return stable_hash({"placebo": PLACEBO_VERSION, "rank": rank.RANK_VERSION,
                        "weights": weights.fingerprint, "agents": agents_fp,
                        "deep": dict(deep_versions), "screen": screen.SCREEN_VERSION}, size=8)


def threshold_path(data_dir: str | Path) -> Path:
    return Path(data_dir) / "scanner" / THRESHOLD_FILE


def write_threshold(data_dir: str | Path, ev: Mapping, fp: str, meta: Mapping) -> Path:
    f = threshold_path(data_dir)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps({"fingerprint": fp, **meta, "evaluation": dict(ev)},
                              ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    tmp.replace(f)
    return f


def load_threshold(data_dir: str | Path | None, fp: str) -> dict:
    """Umbral vigente; si falta o es de otra versión, no marca nada por encima (conservador)."""
    try:
        raw = json.loads(threshold_path(data_dir).read_text(encoding="utf-8")) \
            if data_dir is not None else None
    except (OSError, ValueError):
        raw = None
    if not raw:
        return {"status": "sin_placebo", "value": None,
                "reason": "aún no se corrió `scripts/scanner_placebo.py`: ninguna candidata se "
                          "marca por encima del azar"}
    ev = raw.get("evaluation") or {}
    base = {"value": ev.get("threshold"), "replicas": ev.get("replicas"),
            "alpha": ev.get("alpha"), "fdr_estimate": ev.get("fdr_estimate"),
            "false_per_pass": ev.get("false_per_pass"), "p_global": ev.get("p_global"),
            "kind": raw.get("kind"), "computed_at": raw.get("computed_at")}
    if raw.get("fingerprint") != fp:
        return base | {"status": "desactualizado", "value": None,
                       "reason": "el placebo se midió con otras versiones (agentes, pesos o "
                                 "ranking): ninguna candidata se marca hasta repetirlo"}
    return base | {"status": "vigente", "reason": ""}
