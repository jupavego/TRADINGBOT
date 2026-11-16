"""Mirada final de la cantera (T170): candidatos a primer equipo, con el criterio estricto. Puro.

Solo en la última revisión (día 182) y solo para quien llega como Promesa. Es la capa que toca la
puerta hacia T49, así que **no se afloja un punto** (decisión del usuario, 2026-11-11):

- **StepM de Romano-Wolf** (2005), FWER a 0,05, sobre la serie diaria de d (suma de d de lo
  cerrado cada día, 0 sin cierre) de **toda la familia**, bajas incluidas hasta su baja; bootstrap
  estacionario con el bloque de Politis-White (`validation/spa.block_length`).
- **Sharpe deflactado** de d por operación con el **N efectivo** (grupos de prospectos con
  correlación diaria ≥ 0,7, enlace medio) ≥ 0,95; el del N nominal se declara al lado.
- d con signo positivo en ≥ 2 regímenes con ≥ 20 operaciones cada uno.
- **Persistencia del orden**: media de d > 0 y por encima de la mediana de la familia en los
  meses 1–3 y en los 4–6 (sustituye al PBO, que se informa como descriptivo en T172).
- V1 (≥ 100 operaciones, o ≥ 120 días en posición si es semanal), V4 (drawdown ≤ 25 %),
  V5 (≥ 60 % de ventanas de 30 días con R neto medio > 0, mínimo 4) y V6 (costo ≤ 0,3 R).

El usuario solo confirma o veta la salida mecánica (T172); no elige entre candidatos.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

import numpy as np

from eim.copytrading.stats import deflated
from eim.nursery.ladder import BAJA, PRIMER, PROMESA, Member, Standing, _crit, _drop, _set
from eim.nursery.ladder_rules import LadderRules
from eim.nursery.ladder_stats import DAY_MS, AccountData


def daily_d(acc: AccountData, alta: int, tau: int) -> np.ndarray:
    d0 = alta // DAY_MS
    out = np.zeros(int(tau // DAY_MS - d0 + 1))
    for c in acc.closed:
        out[int(c.exit_t // DAY_MS - d0)] += c.d
    return out


def n_effective(series: np.ndarray, corr: float) -> int:
    """Número de grupos de prospectos por correlación del P&L diario (enlace medio, 1 − ρ)."""
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform

    live = series[:, series.std(axis=0) > 0]
    k = live.shape[1]
    if k <= 1:                     # sin varianza, cada uno es su propio grupo (sí fue un intento)
        return max(1, series.shape[1])
    rho = np.nan_to_num(np.corrcoef(live, rowvar=False))
    dist = np.clip(1 - rho, 0, 2)
    np.fill_diagonal(dist, 0)
    z = linkage(squareform(dist, checks=False), method="average")
    return int(fcluster(z, t=1 - corr, criterion="distance").max()) + (series.shape[1] - k)


def stepm_superior(names: Sequence[str], series: np.ndarray, rules: LadderRules) -> set[str]:
    """Conjunto de prospectos superiores a no tener información (d = 0) según StepM."""
    import pandas as pd
    from arch.bootstrap import StepM

    from eim.validation.spa import block_length

    keep = [j for j in range(series.shape[1]) if series[:, j].std() > 0]
    if not keep or series.shape[0] < 10:
        return set()
    x = series[:, keep]
    ft = rules.first_team
    sm = StepM(np.zeros(x.shape[0]), pd.DataFrame(-x, columns=[names[j] for j in keep]),
               size=ft.stepm_size, block_size=max(1, int(round(block_length(x)))),
               reps=ft.stepm_reps, bootstrap="stationary", studentize=True,
               seed=ft.stepm_seed)
    sm.compute()
    return {str(c) for c in sm.superior_models}


def _regimes(acc: AccountData, ft) -> tuple[bool, dict]:
    by: dict[str, list[float]] = {}
    for c in acc.closed:
        if c.regime:
            by.setdefault(c.regime, []).append(c.d)
    good = {k: round(float(np.mean(v)), 4) for k, v in by.items()
            if len(v) >= ft.regime_min_trades}
    pos = sum(1 for v in good.values() if v > 0)
    return pos >= ft.regimes_min, good


def _halves(accs: Mapping[str, AccountData], cut: int, min_n: int) -> list[dict[str, float]]:
    out: list[dict[str, float]] = [{}, {}]
    for pid, acc in accs.items():
        for h, cs in enumerate(([c.d for c in acc.closed if c.exit_t <= cut],
                                [c.d for c in acc.closed if c.exit_t > cut])):
            if len(cs) >= min_n:
                out[h][pid] = float(np.mean(cs))
    return out


def _v5(acc: AccountData, alta: int, ft) -> tuple[bool, dict]:
    wins: dict[int, list[float]] = {}
    for c in acc.closed:
        if c.r is not None:
            wins.setdefault((c.exit_t - alta) // (ft.window_days * DAY_MS), []).append(c.r)
    ok_w = [float(np.mean(v)) > 0 for v in wins.values() if len(v) >= ft.window_min_trades]
    frac = sum(ok_w) / len(ok_w) if ok_w else 0.0
    return len(ok_w) >= ft.min_windows and frac >= ft.min_positive_frac, \
        {"windows": len(ok_w), "positive_frac": round(frac, 3)}


def make_first_team(rules: LadderRules, alta_ms: int, m: int, initial: float
                    ) -> Callable[[Sequence[Member], Mapping[str, AccountData],
                                   dict[str, Standing], int], None]:
    ft = rules.first_team

    def first_team(members: Sequence[Member], accounts: Mapping[str, AccountData],
                   stand: dict[str, Standing], tau: int) -> None:
        accs = {}
        for mb in members:
            s, acc = stand[mb.id], accounts.get(mb.id, AccountData())
            accs[mb.id] = acc.upto(s.exit["at_ms"] if s.stage == BAJA and s.exit else tau)
        names = [mb.id for mb in members]
        mat = np.column_stack([daily_d(accs[n], alta_ms, tau) for n in names])
        superior = stepm_superior(names, mat, rules)
        neff = n_effective(mat, ft.neff_corr)
        cut = alta_ms + rules.reviews_days[len(rules.reviews_days) // 2 - 1] * DAY_MS
        h1, h2 = _halves(accs, cut, ft.persistence_min_trades)
        med = [float(np.median(list(h.values()))) if h else 0.0 for h in (h1, h2)]
        for mb in members:
            s = stand[mb.id]
            if s.stage != PROMESA:
                continue
            acc = accs[mb.id]
            d = [c.d for c in acc.closed]
            dsr = deflated(d, max(neff, 1))
            dsr_nom = deflated(d, m)
            reg_ok, reg = _regimes(acc, ft)
            per = [h.get(mb.id) for h in (h1, h2)]
            per_ok = all(x is not None and x > 0 and x >= md
                         for x, md in zip(per, med, strict=True))
            semanal = s.band in rules.primary.day_unit_bands
            days_pos = len({day for f, e in acc.fills
                            for day in range(f // DAY_MS, (e or tau) // DAY_MS + 1)})
            v1 = days_pos >= ft.min_pos_days if semanal else len(d) >= ft.min_trades
            dd = s.metrics.get("max_dd_pct", 0.0) / 100
            v5, v5i = _v5(acc, alta_ms, ft)
            costs = [c.cost_r for c in acc.closed if c.cost_r is not None]
            cost = float(np.mean(costs)) if costs else None
            crit = [
                _crit("stepm", mb.id in superior, "StepM de Romano-Wolf (FWER "
                      f"{ft.stepm_size:g}) sobre la familia de {len(names)}"),
                _crit("dsr", dsr is not None and dsr[0] >= ft.dsr_min,
                      f"Sharpe deflactado con N efectivo {neff} (nominal {m}: "
                      f"{None if dsr_nom is None else round(dsr_nom[0], 3)})",
                      None if dsr is None else round(dsr[0], 3), ft.dsr_min),
                _crit("regimenes", reg_ok, f"d > 0 en ≥ {ft.regimes_min} regímenes", reg),
                _crit("persistencia", per_ok, "orden de los meses 1–3 frente a 4–6",
                      per, med),
                _crit("v1", v1, "suficiencia de datos", days_pos if semanal else len(d)),
                _crit("v4", dd <= ft.max_dd, "drawdown", round(dd, 4), ft.max_dd),
                _crit("v5", v5, "estabilidad por ventanas de 30 días", v5i),
                _crit("v6", cost is not None and cost <= ft.max_cost_r, "costo medio en R",
                      cost, ft.max_cost_r)]
            s.criteria.extend(crit)
            s.metrics["n_effective"] = neff
            failed = [c["id"] for c in crit if not c["ok"]]
            if failed:
                _drop(s, tau, "fecha_limite", "fecha límite: promesa que no cumple primer "
                                              f"equipo ({', '.join(failed)})")
            else:
                _set(s, PRIMER, tau)
                s.metrics["pending"] = "◆ T172: el usuario confirma o veta"

    return first_team
