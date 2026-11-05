"""Estadística del banco de salidas (T131): bootstrap por días, Romano-Wolf y PBO por CSCV.

Pura, vectorizada y reproducible con semilla. Tres piezas que el código del proyecto no tenía:

- **Bootstrap por bloques de día** sobre las diferencias EMPAREJADAS (misma entrada, dos salidas).
  Las operaciones de un mismo día comparten el movimiento del día: se remuestrean días completos,
  nunca operaciones sueltas.
- **Romano-Wolf** (E3 de §8): corrección por pasos con el MISMO remuestreo para todas las
  variantes, así que aprovecha que están muy correlacionadas (mismas entradas, parámetros
  vecinos) y pierde menos potencia que Holm, que se informa como referencia conservadora.
  El estadístico se estudentiza con un error estándar **agrupado por día** calculado una vez sobre
  la muestra original (escala fija): es lo que hace comparable el máximo entre variantes.
- **PBO por CSCV** (Bailey, Borwein, López de Prado y Zhu): parte el periodo en S tramos, prueba
  todas las mitades posibles como ajuste y mide con qué frecuencia la variante que gana dentro de
  muestra cae en la mitad mala fuera. PBO ≥ 0,2 = la rejilla está sobreajustada (§5.3).

Convenio de signo: todas las pruebas son **unilaterales** con H1 «la variante mejora a la base»
(ΔE[R] > 0) y usan la corrección +1, así que un p nunca sale 0.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from itertools import combinations

import numpy as np

from eim.backtest.edge import holm

CHUNK = 500               # réplicas por bloque (acota la memoria)
MAX_SPLITS = 2_000        # tope de combinaciones de CSCV
DEGENERATE = 1e-9         # por debajo de esto el error estándar es ruido de coma flotante


def _by_day(days: np.ndarray, values: np.ndarray,
            keys: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(suma, cuenta) de `values` por cada día de `keys` (0 donde la variante no tiene datos)."""
    idx = np.searchsorted(keys, days)
    ok = (idx < len(keys)) & (keys[np.minimum(idx, len(keys) - 1)] == days)
    sums = np.bincount(idx[ok], weights=values[ok], minlength=len(keys))
    cnts = np.bincount(idx[ok], minlength=len(keys)).astype(float)
    return sums[:len(keys)], cnts[:len(keys)]


def cluster_se(days: np.ndarray, d: np.ndarray) -> float:
    """Error estándar de la media agrupado por día: raíz de Σ_día (Σ residuos)² entre n."""
    n = len(d)
    if n < 2:
        return math.nan
    mu = float(d.mean())
    keys = np.unique(days)
    u, _ = _by_day(days, d - mu, keys)
    return float(math.sqrt(float((u**2).sum())) / n)


def resample_means(sums: np.ndarray, cnts: np.ndarray, reps: int,
                   rng: np.random.Generator) -> np.ndarray:
    """Medias de `reps` remuestreos de días completos (con reemplazo)."""
    g = len(sums)
    out = []
    for a in range(0, reps, CHUNK):
        idx = rng.integers(0, g, size=(min(CHUNK, reps - a), g))
        num, den = sums[idx].sum(axis=1), cnts[idx].sum(axis=1)
        out.append(np.where(den > 0, num / np.where(den > 0, den, 1.0), np.nan))
    return np.concatenate(out) if out else np.array([], dtype=float)


def day_block_means(days: np.ndarray, values: np.ndarray, reps: int,
                    rng: np.random.Generator) -> np.ndarray:
    """Medias de `reps` remuestreos de días completos de `values` (bloques de día).

    Es la pieza que comparten el IC emparejado, Romano-Wolf y la comprobación del ES de T136:
    cualquier estadístico que sea la MEDIA de una serie por operación se remuestrea con esto.
    """
    keys = np.unique(days)
    sums, cnts = _by_day(days, values, keys)
    return resample_means(sums, cnts, reps, rng)


def paired_ci(diffs: Sequence[tuple[int, float]], reps: int, level: float,
              rng: np.random.Generator) -> tuple[float, float]:
    """IC del ΔE[R] medio emparejado por bootstrap de bloques de día (percentiles)."""
    if len(diffs) < 2:
        return math.nan, math.nan
    days = np.array([x[0] for x in diffs], dtype=np.int64)
    d = np.array([x[1] for x in diffs], dtype=float)
    keys = np.unique(days)
    sums, cnts = _by_day(days, d, keys)
    means = resample_means(sums, cnts, reps, rng)
    means = means[np.isfinite(means)]
    if not len(means):
        return math.nan, math.nan
    q = (1 - level) / 2
    return float(np.quantile(means, q)), float(np.quantile(means, 1 - q))


def _one_sided_p(obs: float, null: np.ndarray) -> float:
    return float((1 + int(np.sum(null >= obs))) / (1 + len(null)))


def romano_wolf(diffs: dict[str, Sequence[tuple[int, float]]], reps: int,
                rng: np.random.Generator) -> dict:
    """p ajustados por Romano-Wolf (y los brutos y los de Holm) de cada variante frente a la base.

    `diffs`: variante → [(día, ΔR)] de las filas emparejadas. El remuestreo de días es el MISMO
    para todas las variantes (se sortea una vez), que es lo que respeta su dependencia.
    """
    names = [k for k, v in diffs.items() if len(v) >= 2]
    if not names:
        return {"p_raw": {}, "p_rw": {}, "p_holm": {}, "reps": 0, "skipped": list(diffs)}
    keys = np.unique(np.concatenate([[x[0] for x in diffs[k]] for k in names]).astype(np.int64))
    stat, se_of, sums, cnts = {}, {}, {}, {}
    for k in names:
        days = np.array([x[0] for x in diffs[k]], dtype=np.int64)
        d = np.array([x[1] for x in diffs[k]], dtype=float)
        mu, se = float(d.mean()), cluster_se(days, d)
        # Varianza degenerada (todas las diferencias iguales): no hay estadístico que
        # estudentizar y un `se` de 1e-18 daría una t absurda. Se informa como saltada.
        if not math.isfinite(se) or se <= DEGENERATE * max(abs(mu), 1.0):
            continue
        stat[k], se_of[k] = mu / se, se
        sums[k], cnts[k] = _by_day(days, d, keys)
        sums[k] = sums[k] - cnts[k] * float(d.mean())      # centrado: nulo de «sin efecto»
    live = [k for k in names if k in stat]
    if not live:
        return {"p_raw": {}, "p_rw": {}, "p_holm": {}, "reps": 0, "skipped": names}
    g = len(keys)
    boots = {k: [] for k in live}
    for a in range(0, reps, CHUNK):
        idx = rng.integers(0, g, size=(min(CHUNK, reps - a), g))
        for k in live:
            num, den = sums[k][idx].sum(axis=1), cnts[k][idx].sum(axis=1)
            m = np.where(den > 0, num / np.where(den > 0, den, 1.0), 0.0)
            boots[k].append(m / se_of[k])
    t_null = {k: np.concatenate(v) for k, v in boots.items()}
    p_raw = {k: _one_sided_p(stat[k], t_null[k]) for k in live}
    order = sorted(live, key=lambda k: -stat[k])
    p_rw, run = {}, 0.0
    for s, k in enumerate(order):
        rest = order[s:]
        mx = np.max(np.stack([t_null[x] for x in rest]), axis=0)
        run = max(run, _one_sided_p(stat[k], mx))
        p_rw[k] = min(1.0, run)
    return {"p_raw": p_raw, "p_rw": p_rw, "p_holm": holm(p_raw), "reps": reps,
            "t": {k: stat[k] for k in live}, "days": int(g),
            "skipped": [k for k in diffs if k not in live]}


def pbo(matrix: dict[str, Sequence[float]], splits: int = 8) -> dict:
    """PBO por CSCV: `matrix` = variante → rendimiento en cada tramo (misma longitud y orden).

    Parte los tramos en todas las mitades posibles; en cada una se elige la variante que gana
    DENTRO de muestra y se mira su posición FUERA. PBO = fracción de veces que cae en la mitad
    mala (logit ≤ 0). Devuelve también la mediana del logit y la degradación media.
    """
    names = sorted(matrix)
    if len(names) < 2:
        return {"pbo": None, "reason": "hacen falta ≥ 2 variantes", "variants": len(names)}
    m = np.array([list(matrix[k]) for k in names], dtype=float)
    s = m.shape[1]
    if splits % 2 or splits < 4 or s < splits:
        return {"pbo": None, "reason": f"hacen falta ≥ {splits} tramos con S par ≥ 4 (hay {s})",
                "slices": s}
    groups = np.array_split(np.arange(s), splits)
    combos = list(combinations(range(splits), splits // 2))[:MAX_SPLITS]
    n = len(names)
    logits, drops = [], []
    for c in combos:
        fit = np.concatenate([groups[i] for i in c])
        test = np.concatenate([groups[i] for i in range(splits) if i not in c])
        in_s, out_s = m[:, fit].mean(axis=1), m[:, test].mean(axis=1)
        best = int(np.argmax(in_s))
        rank = float(np.sum(out_s <= out_s[best]))        # 1 = la peor, n = la mejor
        w = rank / (n + 1)
        w = min(max(w, 1 / (n + 1)), n / (n + 1))
        logits.append(math.log(w / (1 - w)))
        drops.append(float(in_s[best] - out_s[best]))
    lg = np.array(logits, dtype=float)
    return {"pbo": float((lg <= 0).mean()), "splits": splits, "combinations": len(combos),
            "variants": n, "logit_median": float(np.median(lg)),
            "degradation_mean": float(np.mean(drops))}


def plateau(scores: dict[str, float], neighbours: dict[str, Sequence[str]],
            keep: float = 0.7) -> dict[str, bool]:
    """¿Es meseta y no pico? (§5.3) Los vecinos a ±1 paso conservan ≥ `keep` de la mejora."""
    out = {}
    for k, v in scores.items():
        ns = [scores[x] for x in neighbours.get(k, ()) if x in scores]
        out[k] = bool(ns) and v > 0 and all(x >= keep * v for x in ns)
    return out
