"""Rasgos del día, estados causales de los tres modelos y condicionamiento — T166.

Todo lo que hay aquí es **causal**: el estado del día `d` y el pronóstico para el día `d+1` solo
usan días `≤ d`. Los rasgos se estandarizan con media y desviación expansivas (nunca con la
muestra entera) y los modelos se reajustan cada `refit_every` días con los días anteriores,
asignando en línea los días intermedios.

Los cuatro rasgos declarados en `PLAN/notas/T166_preregistro.md` son los del día que usa el banco
de T133 (`paper/ab_conditions.day_features`) más el objetivo de volatilidad de T162: retorno
diario, log de la RV5, eficiencia direccional de Kaufman y rango relativo.

Puro: solo numpy y los módulos puros del agente; sin red, sin disco y sin estado global.
"""

from __future__ import annotations

import numpy as np

from eim.agents.regime import hmm, jump
from eim.agents.regime.bocpd import bocpd, change_points, standardize
from eim.agents.regime.labeling import LABELS, label_bars, segment_starts
from eim.agents.regime.params import RegimeParams

DAY_MS = 86_400_000
FEATURES = ("ret", "ln_rv", "er", "rng")
MIN_Z_DAYS = 20          # días previos mínimos para estandarizar un rasgo
MIN_STATE_DAYS = 20      # días previos mínimos de un estado para usar su media (si no, el suelo)


def day_extras(t: np.ndarray, o: np.ndarray, high: np.ndarray, low: np.ndarray, c: np.ndarray
               ) -> dict[str, np.ndarray]:
    """Por día UTC: eficiencia direccional de Kaufman y rango relativo, desde velas de 1 min.

    Mismas definiciones que `paper/ab_conditions.day_features`, que es lo que etiqueta el banco
    de T133; aquí se calculan sobre las velas de 1 min que ya se leen para la RV.
    """
    t = np.asarray(t, dtype=np.int64)
    day = t // DAY_MS
    keys, start, count = np.unique(day, return_index=True, return_counts=True)
    er = np.full(len(keys), np.nan)
    rng = np.full(len(keys), np.nan)
    for i, (s, n) in enumerate(zip(start, count, strict=True)):
        oo, cc = float(o[s]), c[s:s + n]
        steps = float(np.abs(np.diff(np.concatenate(([oo], cc)))).sum())
        if oo > 0 and steps > 0:
            er[i] = abs(float(cc[-1]) - oo) / steps
            rng[i] = (float(high[s:s + n].max()) - float(low[s:s + n].min())) / oo
    return {"day": keys, "er": er, "rng": rng}


def expanding_z(x: np.ndarray, min_days: int = MIN_Z_DAYS) -> np.ndarray:
    """Estandarización causal: cada fila usa la media y la desviación de las filas `≤` ella.

    Incluir el día propio es causal (sus rasgos se conocen a su cierre) y evita perder días. Las
    primeras `min_days` filas quedan `nan` porque su escala todavía no significa nada.
    """
    x = np.asarray(x, float)
    n = len(x)
    cnt = np.arange(1, n + 1, dtype=float)[:, None]
    m = np.cumsum(x, axis=0) / cnt
    var = np.maximum(np.cumsum(x * x, axis=0) / cnt - m * m, 0.0)
    sd = np.sqrt(var)
    out = np.where(sd > 0, (x - m) / np.where(sd > 0, sd, 1.0), 0.0)
    out[:min_days] = np.nan
    return out


def _refits(n: int, first: int, every: int) -> list[tuple[int, int, int]]:
    """(fin del ajuste, inicio del bloque, fin del bloque) de cada reajuste."""
    return [(r, r, min(r + every, n)) for r in range(first, n, every)]


def jump_states(z: np.ndarray, first_fit: int, k: int, c: float, every: int = 20) -> np.ndarray:
    """Estados del modelo de saltos, reajustando cada `every` días y filtrando hacia delante.

    `c` es la penalización en unidades de los datos (`jump.fit_scaled`). El filtro se rearranca
    con todo el histórico hasta el bloque y se recorta a él, igual que el del HMM: así el estado
    del primer día del bloque no depende de una memoria heredada de otros centroides.
    """
    out = np.full(len(z), -1, dtype=np.int16)
    for end, lo, hi in _refits(len(z), first_fit, every):
        model = jump.fit_scaled(z[:end], k, c)
        out[lo:hi] = jump.assign_filtered(z[:hi], model)[lo:hi]
    return out


def hmm_states(z: np.ndarray, first_fit: int, k: int, every: int = 20) -> np.ndarray:
    """Estados del HMM gaussiano, reajustando cada `every` días y filtrando hacia delante.

    El filtro se rearranca con todo el histórico hasta el bloque y se recorta a él, para que el
    estado del primer día del bloque no dependa de una posterior inicial arbitraria.
    """
    out = np.full(len(z), -1, dtype=np.int16)
    for end, lo, hi in _refits(len(z), first_fit, every):
        model = hmm.fit(z[:end], k)
        out[lo:hi] = hmm.filter_states(z[:hi], model)[lo:hi]
    return out


def bocpd_states(ret: np.ndarray, p: RegimeParams | None = None, min_bars: int | None = None
                 ) -> np.ndarray:
    """Estados del BOCPD **tal como lo corre el agente hoy**, día a día y sin mirar al futuro.

    Para cada día se repite el `run()` del agente sobre la historia hasta ese día (BOCPD sobre el
    retorno y sobre log|retorno|, unión de cambios, `label_bars`) y se toma la etiqueta del último
    día. Es exactamente la secuencia que vería el agente en producción; recalcularlo cada día, en
    vez de cada 20, solo favorece a la referencia.

    Devuelve el índice de la etiqueta en `labeling.LABELS` (−1 mientras no hay suficientes días).
    """
    p = p or RegimeParams()
    ret = np.asarray(ret, float)
    need = p.min_bars if min_bars is None else min_bars
    code = {name: i for i, name in enumerate(LABELS)}
    out = np.full(len(ret), -1, dtype=np.int16)
    for i in range(need, len(ret)):
        r = ret[: i + 1]
        v = np.log(np.abs(r) + 1e-8)
        _, run_r = bocpd(standardize(r), p.hazard, p.max_run, p.short_run)
        _, run_v = bocpd(standardize(v), p.hazard, p.max_run, p.short_run)
        found = sorted(change_points(run_r, p.min_drop, p.min_gap)
                       + change_points(run_v, p.min_drop, p.min_gap))
        cps: list[int] = []
        for loc, _det in found:
            if not cps or loc - cps[-1] >= p.min_gap:
                cps.append(loc)
        starts = segment_starts(len(r), cps)
        out[i] = code[label_bars(r, starts, p.min_seg, p.trend_t, p.vol_ratio)[-1]]
    return out


def forecast_next(states: np.ndarray, ln_rv: np.ndarray, min_days: int = MIN_STATE_DAYS
                  ) -> np.ndarray:
    """Pronóstico de la varianza del día `i` con el estado del día `i−1` y solo días anteriores.

    ĥ_i = exp(m_s + v_s/2) con `m_s`, `v_s` la media y la varianza de ln RV de los días `< i` con
    el mismo estado que el día `i−1`. Si ese estado no llega a `min_days` días, se usa el
    estimador incondicional: así un modelo no cobra nada por inventarse estados casi vacíos.
    """
    states = np.asarray(states, dtype=np.int64)
    ln_rv = np.asarray(ln_rv, float)
    n = len(ln_rv)
    out = np.full(n, np.nan)
    ks = int(states.max()) + 1 if (states >= 0).any() else 1
    cnt = np.zeros(ks)
    s1 = np.zeros(ks)
    s2 = np.zeros(ks)
    g_cnt = g1 = g2 = 0.0
    for i in range(n):
        if i > 0 and g_cnt >= 2:
            gm = g1 / g_cnt
            gv = max(g2 / g_cnt - gm * gm, 0.0)
            s = int(states[i - 1])
            if 0 <= s < ks and cnt[s] >= min_days:
                m = s1[s] / cnt[s]
                v = max(s2[s] / cnt[s] - m * m, 0.0)
                out[i] = float(np.exp(m + v / 2))
            else:
                out[i] = float(np.exp(gm + gv / 2))
        y = ln_rv[i]
        if np.isfinite(y):
            g_cnt, g1, g2 = g_cnt + 1, g1 + y, g2 + y * y
            s = int(states[i])
            if 0 <= s < ks:
                cnt[s] += 1
                s1[s] += y
                s2[s] += y * y
    return out


def persistence(states: np.ndarray) -> dict:
    """Permanencia media, número de cambios, entropía normalizada y ocupación por estado."""
    s = np.asarray(states, dtype=np.int64)
    s = s[s >= 0]
    if len(s) < 2:
        return {"n": int(len(s)), "dwell_mean": None, "n_switches": None, "entropy": None,
                "occupancy": {}}
    ks = int(s.max()) + 1
    counts = np.zeros((ks, ks))
    for a, b in zip(s[:-1], s[1:], strict=True):
        counts[a, b] += 1
    rows = counts.sum(axis=1)
    trans = np.divide(counts, rows[:, None], out=np.zeros_like(counts), where=rows[:, None] > 0)
    occ = rows / rows.sum() if rows.sum() > 0 else rows
    safe = np.where(trans > 0, trans, 1.0)
    h = float(np.sum(occ * -np.sum(trans * np.log(safe), axis=1)) / np.log(ks)) if ks > 1 else 0.0
    switches = int(np.sum(s[1:] != s[:-1]))
    return {"n": int(len(s)), "dwell_mean": float(len(s) / (switches + 1)),
            "n_switches": switches, "entropy": h,
            "occupancy": {int(i): float(x) for i, x in enumerate(occ)},
            "transition": trans.round(4).tolist()}
