"""Pronósticos de la varianza del día siguiente para el cono (T162).

El cono proyecta 20–30 velas de 1 h: su horizonte natural es el día. Aquí se comparan cuatro
fuentes de σ² diaria, todas **sin fuga** (el pronóstico del día `d` solo usa datos anteriores
a su comienzo, 00:00 UTC):

- `m0_fixed_garch`: el GARCH(1,1) fijo de `base_engine.py` agregado a 24 h (la referencia).
- `m1_log_har`: Log-HAR-RV (Corsi 2009, en logaritmos) con reajuste diario por mínimos cuadrados.
- `m2_gjr_garch`: GJR-GARCH(1,1) con t de Student sobre retornos diarios, con `arch` (extra
  `stats`, licencia NCSA); se importa al llamar.
- La combinación M3 es la media de M1 y M2 (la hace quien llama).

Pre-registro: `PLAN/notas/T162_preregistro.md`.
"""

from __future__ import annotations

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
    """Pronóstico de RV de cada día con Log-HAR ajustado solo con días anteriores.

    Ecuaciones normales acumuladas: cada día cuesta O(1). El pronóstico en niveles es
    exp(ŷ + s²/2), con s² la varianza residual del ajuste (corrección lognormal).
    """
    rv = np.asarray(rv, dtype=float)
    n = len(rv)
    out = np.full(n, np.nan)
    xtx = np.zeros((4, 4))
    xty = np.zeros(4)
    yty, rows = 0.0, 0
    lrv = np.log(np.where(rv > 0, rv, np.nan))
    for k in range(n):
        x = _row(rv, k)
        if x is not None and rows >= min_rows:
            beta = np.linalg.solve(xtx, xty)
            ssr = max(yty - float(beta @ xty), 0.0)
            s2 = ssr / max(rows - 4, 1)
            out[k] = float(np.exp(x @ beta + s2 / 2))
        if x is not None and np.isfinite(lrv[k]):
            xtx += np.outer(x, x)
            xty += x * lrv[k]
            yty += lrv[k] ** 2
            rows += 1
    return out


def _row(rv: np.ndarray, k: int) -> np.ndarray | None:
    row = [1.0]
    for n in LAGS:
        if k - n < 0:
            return None
        w = rv[k - n:k]
        if not np.isfinite(w).all():
            return None
        row.append(float(np.log(w.mean())))
    return np.array(row)


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
