"""Estadística de la familia de la forja (T208), a escala de miles de recetas.

Las piezas son las de T131 —bloques de un día, Romano-Wolf estudentizado con error estándar
agrupado, PBO por CSCV y Sharpe deflactado—, pero reescritas en forma **matricial**: con 18 000
recetas, el remuestreo receta por receta de `eim/paper/exits/stats.py` sería inviable.

El truco es que remuestrear días con reemplazo equivale a multiplicar por un vector de **cuentas**
multinomiales: con las sumas por día en una matriz `S` (recetas × días), las medias de todas las
recetas en todas las réplicas salen de dos productos de matrices. Es exactamente el mismo
remuestreo —los mismos días para todas las recetas, que es lo que respeta su dependencia—, solo
escrito de otra forma.

Convenio: todas las pruebas son unilaterales con H1 «E[R] > 0» y usan la corrección +1, así que
ningún p sale 0.
"""

from __future__ import annotations

import numpy as np
from scipy.special import ndtr

from eim.backtest.edge import holm
from eim.copytrading.stats import expected_max_z

CHUNK = 200               # réplicas por bloque (acota la memoria del producto)


def moments(n: np.ndarray, s1: np.ndarray, s2: np.ndarray, s3: np.ndarray,
            s4: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(media, desviación muestral, asimetría, curtosis) por receta, desde las sumas de potencias.

    Idéntico al convenio de `eim/copytrading/stats.moments`: desviación muestral (ddof 1),
    asimetría y curtosis con momentos poblacionales y curtosis **no** en exceso (normal = 3).
    """
    nn = np.maximum(n, 1).astype(float)
    m1 = s1 / nn
    pop = np.maximum(s2 / nn - m1 ** 2, 0.0)
    var = np.where(n > 1, (s2 - nn * m1 ** 2) / np.maximum(nn - 1, 1), 0.0)
    m3 = s3 / nn - 3 * m1 * s2 / nn + 2 * m1 ** 3
    m4 = s4 / nn - 4 * m1 * s3 / nn + 6 * m1 ** 2 * s2 / nn - 3 * m1 ** 4
    ok = pop > 0
    skew = np.where(ok, m3 / np.where(ok, pop, 1.0) ** 1.5, 0.0)
    kurt = np.where(ok, m4 / np.where(ok, pop, 1.0) ** 2, 3.0)
    return m1, np.sqrt(np.maximum(var, 0.0)), skew, kurt


def dsr(n: np.ndarray, s1: np.ndarray, s2: np.ndarray, s3: np.ndarray, s4: np.ndarray,
        trials: int) -> tuple[np.ndarray, float]:
    """Sharpe deflactado por receta (Bailey y López de Prado) con `trials` intentos exactos."""
    m1, sd, skew, kurt = moments(n, s1, s2, s3, s4)
    sr = np.where(sd > 0, m1 / np.where(sd > 0, sd, 1.0), np.nan)
    sr0 = expected_max_z(trials) / np.sqrt(np.maximum(n - 1, 1))
    v = 1 - skew * sr + (kurt - 1) / 4 * sr ** 2
    se = np.sqrt(np.maximum(v, 1e-12) / np.maximum(n - 1, 1))
    out = np.where((n >= 3) & (sd > 0), ndtr((sr - sr0) / se), np.nan)
    return out, float(expected_max_z(trials))


def _cluster_se(s: np.ndarray, c: np.ndarray, mean: np.ndarray,
                total: np.ndarray) -> np.ndarray:
    """Error estándar agrupado por día, por receta (igual que `exits/stats.cluster_se`)."""
    u = s - c * mean[:, None]
    return np.sqrt((u ** 2).sum(axis=1)) / np.maximum(total, 1)


def stepm(s: np.ndarray, c: np.ndarray, names: list[str], reps: int, seed: int,
          min_trades: int = 1) -> dict:
    """Romano-Wolf (StepM) de «E[R] > 0» para todas las recetas a la vez.

    `s` y `c`: sumas y cuentas de R por día (recetas × días). Devuelve t, p brutos, p de
    Romano-Wolf y p de Holm (de referencia), y el t del máximo nulo (lo que daría la mejor de
    `len(names)` recetas por puro azar).
    """
    total = c.sum(axis=1)
    mean = np.where(total > 0, s.sum(axis=1) / np.maximum(total, 1), np.nan)
    se = _cluster_se(s, c, np.nan_to_num(mean), total)
    live = np.flatnonzero((total >= min_trades) & np.isfinite(mean) & (se > 0))
    if not len(live):
        return {"p_raw": {}, "p_rw": {}, "p_holm": {}, "t": {}, "reps": 0, "live": 0}
    sl, cl = s[live].astype(np.float32), c[live].astype(np.float32)
    ml, sel = mean[live], se[live]
    t_obs = ml / sel
    centered = (sl - cl * ml[:, None].astype(np.float32)).astype(np.float32)
    rng = np.random.default_rng(seed)
    d = s.shape[1]
    ge = np.zeros(len(live), dtype=np.int64)
    maxes: list[np.ndarray] = []
    order = np.argsort(-t_obs)
    for a in range(0, reps, CHUNK):
        k = min(CHUNK, reps - a)
        w = rng.multinomial(d, np.full(d, 1 / d), size=k).astype(np.float32).T   # días × réplicas
        num, den = centered @ w, cl @ w
        tb = np.where(den > 0, num / np.where(den > 0, den, 1.0), 0.0) / sel[:, None]
        ge += (tb >= t_obs[:, None]).sum(axis=1)
        # máximo acumulado desde la receta peor hacia la mejor, en el orden observado
        maxes.append(np.maximum.accumulate(tb[order][::-1], axis=0)[::-1])
    suf = np.concatenate(maxes, axis=1)
    p_raw = (1 + ge) / (1 + reps)
    p_step = (1 + (suf >= t_obs[order][:, None]).sum(axis=1)) / (1 + reps)
    p_rw = np.maximum.accumulate(p_step)        # por pasos: monótona de la mejor a la peor
    nm = [names[i] for i in live]
    raw = {nm[i]: float(p_raw[i]) for i in range(len(live))}
    rw = {nm[order[j]]: float(min(1.0, p_rw[j])) for j in range(len(live))}
    return {"p_raw": raw, "p_rw": rw,
            "p_holm": holm(raw), "t": {nm[i]: float(t_obs[i]) for i in range(len(live))},
            "reps": reps, "live": int(len(live)),
            "t_null_max_mean": float(np.mean(suf[0])), "days": int(d)}


def slice_means(s: np.ndarray, c: np.ndarray, splits: int = 8) -> np.ndarray:
    """R medio de cada receta en cada uno de los `splits` tramos de días consecutivos."""
    parts = np.array_split(np.arange(s.shape[1]), splits)
    out = np.empty((s.shape[0], splits), dtype=float)
    for j, p in enumerate(parts):
        num, den = s[:, p].sum(axis=1), c[:, p].sum(axis=1)
        out[:, j] = np.where(den > 0, num / np.maximum(den, 1), np.nan)
    return out
