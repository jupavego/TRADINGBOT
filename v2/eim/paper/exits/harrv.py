"""HAR-RV sobre las velas de 1 min (Corsi, 2009), el patrón de referencia para BTC intradía.

La volatilidad realizada de un día es la suma de los log-retornos al cuadrado de sus velas de
1 min. HAR la pronostica con tres componentes —el día anterior, la semana (5 días) y el mes
(22 días)— por mínimos cuadrados:

    RV_{t+1} = c + β_d·RV_t + β_w·RV_t^{(5)} + β_m·RV_t^{(22)}

Dos reglas que hacen esto usable en el banco, y que son la diferencia entre medir y engañarse:

- **Sin fuga:** el pronóstico del día `t+1` se ajusta **solo con días ≤ t**. Se recalcula día a día
  en una sola pasada acumulativa, así que cuesta lo mismo que hacerlo una vez.
- **Sin dato no aprieta:** mientras no hay `min_days` días para ajustar, el pronóstico es `nan` y la
  política usa su valor base. Nunca se devuelve 0, que pondría el stop encima del precio.

Unidad: σ **relativo por vela del camino**, igual que `sigma.py`, para que las políticas puedan
intercambiar estimadores sin tocar nada. El σ diario pronosticado se reparte entre las velas del
día (√tiempo): σ_vela = σ_día / √(velas por día).

Puro: numpy, sin dependencias nuevas (◆5 de T129).
"""

from __future__ import annotations

import numpy as np

DAY_MS = 86_400_000
LAGS = (1, 5, 22)            # día, semana, mes (Corsi)
MIN_DAYS = 60                # mínimo para ajustar; por debajo, `nan`
EPS = 1e-12


def daily_rv(t: np.ndarray, c: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(día UTC, volatilidad realizada) de cada día con velas finas.

    RV del día = Σ (ln c_i − ln c_{i−1})² dentro del día. El primer retorno de cada día usa el
    cierre anterior del MISMO día, así que el salto entre días no entra (lo recoge Yang–Zhang).
    """
    if len(c) < 2:
        return np.array([], dtype=np.int64), np.array([], dtype=float)
    ok = (c > 0) & np.isfinite(c)
    lc = np.where(ok, np.log(np.where(ok, c, 1.0)), np.nan)
    day = (np.asarray(t) // DAY_MS).astype(np.int64)
    r2 = np.full(len(c), np.nan)
    same = day[1:] == day[:-1]
    diff = lc[1:] - lc[:-1]
    r2[1:] = np.where(same, diff**2, np.nan)
    keys, inv = np.unique(day, return_inverse=True)
    good = np.isfinite(r2)
    rv = np.bincount(inv[good], weights=r2[good], minlength=len(keys))
    cnt = np.bincount(inv[good], minlength=len(keys))
    rv = np.where(cnt > 0, rv, np.nan)
    return keys, rv


def _design(rv: np.ndarray, k: int) -> np.ndarray | None:
    """Regresores del día `k`: medias de los `LAGS` días anteriores. None si falta alguno."""
    row = [1.0]
    for n in LAGS:
        if k - n < 0:
            return None
        w = rv[k - n:k]
        if not np.isfinite(w).all():
            return None
        row.append(float(w.mean()))
    return np.array(row, dtype=float)


def forecast_by_day(keys: np.ndarray, rv: np.ndarray,
                    min_days: int = MIN_DAYS) -> dict[int, float]:
    """{día: RV pronosticada para ese día} ajustando SOLO con los días anteriores.

    Para cada día `k` se arman las filas (regresores del día i, objetivo RV del día i) de todos los
    `i < k` con ventana completa, se resuelve por mínimos cuadrados y se aplica a los regresores
    del propio `k`. Si no hay `min_days` filas o la fila de `k` está incompleta, no hay pronóstico.
    """
    out: dict[int, float] = {}
    rows: list[np.ndarray] = []
    targets: list[float] = []
    for k in range(len(rv)):
        xk = _design(rv, k)
        if xk is not None and len(rows) >= min_days:
            a = np.vstack(rows)
            beta, *_ = np.linalg.lstsq(a, np.array(targets, dtype=float), rcond=None)
            pred = float(xk @ beta)
            if np.isfinite(pred) and pred > EPS:
                out[int(keys[k])] = pred
        if xk is not None and np.isfinite(rv[k]):
            rows.append(xk)
            targets.append(float(rv[k]))
    return out


def sigma_by_bar(path_t: np.ndarray, fine_t: np.ndarray, fine_c: np.ndarray,
                 bars_per_day: float, min_days: int = MIN_DAYS) -> np.ndarray:
    """σ relativo por vela del camino, del HAR-RV ajustado con las velas finas.

    `path_t` son los instantes del camino (15 m); `fine_t`/`fine_c`, las velas de 1 min. El valor
    de cada vela del camino usa el pronóstico de SU día, que se ajustó con días anteriores: no hay
    anticipación dentro del día porque la RV del propio día no entra en su pronóstico.
    """
    out = np.full(len(path_t), np.nan)
    if not len(path_t) or not len(fine_c) or bars_per_day <= 0:
        return out
    keys, rv = daily_rv(fine_t, fine_c)
    if not len(keys):
        return out
    pred = forecast_by_day(keys, rv, min_days)
    if not pred:
        return out
    days = (np.asarray(path_t) // DAY_MS).astype(np.int64)
    scale = np.sqrt(bars_per_day)
    for j, d in enumerate(days):
        v = pred.get(int(d))
        if v is not None:
            out[j] = float(np.sqrt(v)) / scale
    return out
