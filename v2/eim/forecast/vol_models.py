"""Pronósticos de la varianza del día siguiente para el cono (T162).

El cono proyecta 20–30 velas de 1 h: su horizonte natural es el día. Aquí se comparan cuatro
fuentes de σ² diaria, todas **sin fuga** (el pronóstico del día `d` solo usa datos anteriores
a su comienzo, 00:00 UTC):

- `m0_fixed_garch`: el GARCH(1,1) fijo de `base_engine.py` agregado a 24 h (la referencia).
- `m1_log_har`: Log-HAR-RV (Corsi 2009, en logaritmos) con reajuste diario por mínimos cuadrados.
- `m2_gjr_garch`: GJR-GARCH(1,1) con t de Student sobre retornos diarios, con `arch` (extra
  `stats`, licencia NCSA); se importa al llamar.
- La combinación M3 es la media de M1 y M2 (la hace quien llama).

T165 añade sobre el mismo banco la volatilidad implícita de Deribit: `daily_implied_var` lleva el
DVOL horario a la IV² del día sin fuga y `log_har_x` admite regresores extra (el HAR-IV y su
pendiente). La ingesta del DVOL es I/O y vive en `eim/data/dvol.py`.

Pre-registro: `PLAN/notas/T162_preregistro.md` y `PLAN/notas/T165_preregistro.md`.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from eim.forecast.base_engine import BaseParams

DAY_MS = 86_400_000
HOUR_MS = 3_600_000
LAGS = (1, 5, 22)


def daily_series(t: np.ndarray, c: np.ndarray, step: int = 5, min_cov: float = 0.90
                 ) -> dict[str, np.ndarray]:
    """Por día UTC: RV con retornos de `step` min, retorno diario, cobertura y si cuenta.

    `t`, `c` son las velas de 1 min. El retorno del día es el log del último cierre del día sobre
    el último del día anterior (nan si falta el anterior).
    """
    t = np.asarray(t, dtype=np.int64)
    c = np.asarray(c, dtype=float)
    day = t // DAY_MS
    keys, start, count = np.unique(day, return_index=True, return_counts=True)
    rv = np.full(len(keys), np.nan)
    last = np.full(len(keys), np.nan)
    for k, (s, n) in enumerate(zip(start, count, strict=True)):
        cc = c[s:s + n]
        last[k] = cc[-1]
        sub = cc[::step]
        if len(sub) >= 2:
            lr = np.diff(np.log(sub))
            rv[k] = float(np.sum(lr * lr))
    cov = count / 1440.0
    ret = np.full(len(keys), np.nan)
    consecutive = np.diff(keys) == 1
    ret[1:] = np.where(consecutive, np.log(last[1:] / last[:-1]), np.nan)
    ok = (cov >= min_cov) & np.isfinite(rv) & (rv > 0)
    return {"day": keys, "rv": np.where(ok, rv, np.nan), "ret": ret, "cov": cov, "ok": ok}


def m0_fixed_garch(hour_t: np.ndarray, hour_c: np.ndarray, days: np.ndarray,
                   p: BaseParams | None = None, steps: int = 24) -> np.ndarray:
    """Σ_{k=1..steps} E[σ²_{t+k}] con la recursión fija del motor base, desde las 00:00 UTC.

    Igual que `BaseEngine.sample`: σ² de arranque por EWMA (λ) sobre las últimas `lookback`
    velas de 1 h, varianza de largo plazo = varianza muestral de esos retornos y persistencia
    α + β. La expectativa a k pasos es V + (α+β)^{k−1}·(σ²₁ − V).
    """
    p = p or BaseParams()
    ht = np.asarray(hour_t, dtype=np.int64)
    lr = np.diff(np.log(np.asarray(hour_c, dtype=float)))
    rt = ht[1:]                                   # instante de apertura de la vela del retorno
    phi = p.garch_alpha + p.garch_beta
    weights = phi ** np.arange(steps)
    out = np.full(len(days), np.nan)
    for i, d in enumerate(np.asarray(days, dtype=np.int64)):
        j = int(np.searchsorted(rt, d * DAY_MS))  # retornos cerrados antes de las 00:00
        r = lr[max(0, j - p.lookback):j]
        if len(r) < p.min_candles:
            continue
        var = float(np.var(r[: min(len(r), 50)])) or 1e-8
        for x in r:
            var = p.ewma_lambda * var + (1 - p.ewma_lambda) * x * x
        v = float(np.var(r))
        out[i] = float(np.sum(v + weights * (var - v)))
    return out


def m1_log_har(rv: np.ndarray, min_rows: int = 250) -> np.ndarray:
    """Log-HAR-RV de T162: el caso sin regresores extra de `log_har_x`."""
    return log_har_x(rv, None, min_rows)


def log_har_x(rv: np.ndarray, extras: Sequence[np.ndarray] | None = None,
              min_rows: int = 250) -> np.ndarray:
    """Pronóstico de RV de cada día con Log-HAR (+ regresores extra) ajustado solo con el pasado.

    Ecuaciones normales acumuladas: cada día cuesta O(1). El pronóstico en niveles es
    exp(ŷ + s²/2), con s² la varianza residual del ajuste (corrección lognormal).

    Cada arreglo de `extras` debe estar **alineado con el día que se pronostica** y contener solo
    información anterior a su comienzo (T165 usa IV² leída a las 00:00 UTC de ese día). Un día con
    algún extra no finito no se pronostica ni entra en el ajuste.
    """
    rv = np.asarray(rv, dtype=float)
    n = len(rv)
    ex = None if not extras else np.column_stack([np.asarray(e, float) for e in extras])
    k_cols = 4 + (0 if ex is None else ex.shape[1])
    out = np.full(n, np.nan)
    xtx = np.zeros((k_cols, k_cols))
    xty = np.zeros(k_cols)
    yty, rows = 0.0, 0
    lrv = np.log(np.where(rv > 0, rv, np.nan))
    for k in range(n):
        x = har_row(rv, k)
        if x is not None and ex is not None:
            x = np.concatenate([x, ex[k]]) if np.isfinite(ex[k]).all() else None
        if x is not None and rows >= min_rows:
            try:
                beta = np.linalg.solve(xtx, xty)
            except np.linalg.LinAlgError:
                beta = None
            if beta is not None:
                ssr = max(yty - float(beta @ xty), 0.0)
                s2 = ssr / max(rows - k_cols, 1)
                out[k] = float(np.exp(x @ beta + s2 / 2))
        if x is not None and np.isfinite(lrv[k]):
            xtx += np.outer(x, x)
            xty += x * lrv[k]
            yty += lrv[k] ** 2
            rows += 1
    return out


def har_row(rv: np.ndarray, k: int) -> np.ndarray | None:
    """Fila HAR del día `k` —[1, ln RV_{k−1}, ln RV̄^(5), ln RV̄^(22)]— o None si falta historia.

    Solo usa días estrictamente anteriores a `k`: es la que garantiza que no hay fuga.
    """
    row = [1.0]
    for n in LAGS:
        if k - n < 0:
            return None
        w = rv[k - n:k]
        if not np.isfinite(w).all():
            return None
        row.append(float(np.log(w.mean())))
    return np.array(row)


def daily_implied_var(hour_t: np.ndarray, hour_c: np.ndarray, days: np.ndarray,
                      ann_days: float = 365.0, max_stale_ms: int = DAY_MS) -> np.ndarray:
    """IV² diaria del DVOL para cada día, **sin fuga** (T165).

    Para el día `d` toma el cierre de la última vela horaria de DVOL cerrada a más tardar a las
    00:00 UTC de `d` (la de las 23:00 del día anterior) y lo convierte de σ anualizada en % a
    varianza del día: (DVOL/100)² / `ann_days`. Si esa vela es más vieja que `max_stale_ms` o no
    existe, el día queda en nan.
    """
    ht = np.asarray(hour_t, dtype=np.int64)
    hc = np.asarray(hour_c, dtype=float)
    starts = np.asarray(days, dtype=np.int64) * DAY_MS
    if not len(ht):
        return np.full(len(starts), np.nan)
    j = np.searchsorted(ht, starts - HOUR_MS, side="right") - 1
    jj = np.clip(j, 0, len(ht) - 1)
    iv = hc[jj] / 100.0
    ok = (j >= 0) & (starts - (ht[jj] + HOUR_MS) <= max_stale_ms) & np.isfinite(iv) & (iv > 0)
    return np.where(ok, iv * iv / ann_days, np.nan)


def log_slope(x: np.ndarray, lag: int = 5) -> np.ndarray:
    """ln x_t − ln x_{t−lag} por posición; nan donde no hay historia o el valor no es positivo."""
    lx = np.log(np.where(np.asarray(x, float) > 0, x, np.nan))
    out = np.full(len(lx), np.nan)
    if lag < len(lx):
        out[lag:] = lx[lag:] - lx[:-lag]
    return out


def m2_gjr_garch(ret: np.ndarray, first: int, refit: int = 20, min_obs: int = 400
                 ) -> np.ndarray:
    """σ² del día con GJR-GARCH(1,1)-t; parámetros reajustados cada `refit` días con el pasado.

    `first` es el primer índice que se pronostica. Los retornos ausentes se tratan como 0 para
    el filtro (no aportan información de varianza) y su día no se evalúa (lo decide quien llama).
    """
    from arch import arch_model

    r = np.nan_to_num(np.asarray(ret, dtype=float), nan=0.0) * 100.0
    n = len(r)
    out = np.full(n, np.nan)
    start = max(first, min_obs)
    for s in range(start, n, refit):
        e = min(s + refit, n)
        fit = arch_model(r[:s], mean="Zero", vol="GARCH", p=1, o=1, q=1,
                         dist="t").fit(disp="off", show_warning=False)
        fixed = arch_model(r[:e], mean="Zero", vol="GARCH", p=1, o=1, q=1,
                           dist="t").fix(fit.params)
        f = fixed.forecast(horizon=1, start=s - 1, reindex=False)
        v = np.asarray(f.variance.iloc[:, 0], dtype=float)[: e - s]
        out[s:s + len(v)] = v / 1e4
    return out
