"""Series sustitutas para el nulo del control aleatorio (criterio 6, redefinido en la v3).

El nulo de la v1 y la v2 estaba mal especificado para una salida dependiente del camino: pedía que
el R **bruto** de unas entradas al azar contuviera el 0, y eso solo se cumple si la serie es una
martingala. El BTC no lo es a 15 min, y un stop de arrastre es **precisamente** una apuesta a esa
dependencia (Kaminski y Lo; Lo y Remorov). Medido en T131: la escalera ajustada daba +0,025 R de
bruto con el 0 fuera del intervalo, sin que hubiera ninguna anticipación —sobre paseos aleatorios
independientes y sin costos da 0—. Con ese nulo, el criterio rechazaba por una propiedad del
mercado, no por un defecto del código.

El nulo correcto conserva **la distribución de los retornos** y destruye **la dependencia**:

1. Se toman los log-retornos de las velas de 1 min reales.
2. Se barajan (bloques de `block` minutos; con `block=1` queda iid).
3. Se rehace el camino de 1 min acumulándolos desde el mismo precio inicial, y el de 15 min
   **agregando** desde él, para que el máximo y el mínimo de cada vela gruesa correspondan de
   verdad al recorrido fino (si no, un arrastre que ancla en el extremo sale sesgado: medido en
   T132, −0,11 R con mechas inventadas frente a 0,00 con el camino coherente).
4. Las entradas al azar se generan sobre ESE camino, con la misma geometría relativa y los mismos
   costos.

Así la única diferencia con la serie real es la dependencia serial, que es justo lo que se quiere
contrastar.

Puro: numpy, sin red y sin disco.
"""

from __future__ import annotations

import numpy as np

from eim.core import Candle
from eim.paper.engine import Path

MIN_MS = 60_000
EPS = 1e-12


def log_returns(c: np.ndarray) -> np.ndarray:
    """Log-retornos de los cierres, saltando los valores no válidos."""
    c = np.asarray(c, dtype=float)
    ok = (c > 0) & np.isfinite(c)
    out = np.full(len(c) - 1, np.nan)
    good = ok[1:] & ok[:-1]
    out[good] = np.log(c[1:][good]) - np.log(c[:-1][good])
    return out[np.isfinite(out)]


def shuffled(returns: np.ndarray, rng: np.random.Generator, block: int = 1) -> np.ndarray:
    """Los mismos retornos en otro orden: bloques de `block` barajados (con `block=1`, iid)."""
    r = np.asarray(returns, dtype=float)
    if block <= 1:
        return rng.permutation(r)
    n = (len(r) // block) * block
    blocks = r[:n].reshape(-1, block)
    return blocks[rng.permutation(len(blocks))].ravel()


def rebuild(returns: np.ndarray, px0: float, t0: int, bars: int,
            per_bar: int = 15) -> tuple[Path, Path]:
    """(camino de 15 m, velas de 1 min) coherentes a partir de una secuencia de retornos.

    El grueso se **agrega** del fino, así que su máximo y su mínimo son los del recorrido real de
    la serie sustituta, no mechas inventadas.
    """
    need = bars * per_bar
    r = np.asarray(returns, dtype=float)[:need]
    if len(r) < per_bar or px0 <= 0:
        return Path([]), Path([], (), MIN_MS)
    usable = (len(r) // per_bar) * per_bar
    r = r[:usable]
    c = px0 * np.exp(np.cumsum(r))
    o = np.concatenate(([px0], c[:-1]))
    fine = [Candle(t=t0 + k * MIN_MS, o=float(o[k]), h=float(max(o[k], c[k])),
                   l=float(min(o[k], c[k])), c=float(c[k]), v=1000.0)
            for k in range(usable)]
    fp = Path(fine, (), MIN_MS)
    step = per_bar * MIN_MS
    coarse = []
    for j in range(usable // per_bar):
        a, b = j * per_bar, (j + 1) * per_bar
        coarse.append(Candle(t=t0 + j * step, o=float(o[a]), h=float(np.max(fp.h[a:b])),
                             l=float(np.min(fp.l[a:b])), c=float(c[b - 1]), v=1000.0))
    return Path(coarse, (), step), fp


def surrogate_of(fine_c: np.ndarray, rng: np.random.Generator, *, bars: int, px0: float,
                 t0: int, block: int = 1, per_bar: int = 15) -> tuple[Path, Path]:
    """Una serie sustituta de `bars` velas de 15 m con los retornos reales en otro orden."""
    return rebuild(shuffled(log_returns(fine_c), rng, block), px0, t0, bars, per_bar)


def one_sided_p(observed: float, null: list[float] | np.ndarray) -> float:
    """p de una cola con corrección +1: ¿el observado supera al nulo más de lo que toca?"""
    a = np.asarray(null, dtype=float)
    a = a[np.isfinite(a)]
    if not len(a):
        return float("nan")
    return float((1 + int(np.sum(a >= observed))) / (1 + len(a)))


def verdict(observed: float, null: list[float] | np.ndarray, alpha: float) -> dict:
    """Veredicto del criterio 6: se RECHAZA si el bruto observado destaca sobre el nulo."""
    a = np.asarray([x for x in null if np.isfinite(x)], dtype=float)
    p = one_sided_p(observed, a)
    return {
        "observed_gross_r": None if not np.isfinite(observed) else float(observed),
        "surrogates": int(len(a)),
        "null_mean": float(a.mean()) if len(a) else None,
        "null_sd": float(a.std(ddof=1)) if len(a) > 1 else None,
        "null_p95": float(np.quantile(a, 0.95)) if len(a) else None,
        "p_one_sided": None if not np.isfinite(p) else p,
        "alpha": alpha,
        "ok": None if not np.isfinite(p) else bool(p >= alpha),
        "reason": ("sin sustitutas suficientes" if not len(a) else
                   f"bruto {observed:+.4f} frente a un nulo de media "
                   f"{a.mean():+.4f} (p95 {np.quantile(a, 0.95):+.4f}): p={p:.3f}"),
    }
