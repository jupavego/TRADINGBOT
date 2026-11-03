"""Métricas del banco de salidas (§5.3 de `PLAN/notas/T129_sl_dinamico.md`). Puras y vectorizadas.

Todo sale de lo REGISTRADO por el banco (operaciones cerradas al tamaño fijo): nada se estima.
Además de las de siempre (acierto, PF, expectativa, drawdown y costos) están las que T129 pide por
lo visto en el libro real:

- **Devolución desde el MFE** (`giveback_r`): lo que el precio llegó a dar y la salida no cobró.
  Es la medida directa del defecto H1 (la escalera cierra a +0,1 R lo que llegó a +1 R).
- **Ganadoras que acaban en pérdida** (`mfe1r_to_loss`): fracción de operaciones con MFE ≥ 1 R que
  cierran perdiendo.
- **CVaR 95 %**: media del 5 % peor de los R. Mide la cola, que el drawdown medio esconde.
- **Riesgo de ruina**: probabilidad de caer al 50 % del capital en N operaciones con el `risk_pct`
  del perfil, por bootstrap de bloques de día (las operaciones del mismo día no son independientes).
- **Sharpe y Sortino diarios** (√365): sobre el R sumado por día UTC de cierre, no por operación.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from eim.paper.exits.bench import BenchTrade

DAY_MS = 86_400_000
YEAR_DAYS = 365.0
CVAR_LEVEL = 0.95
RUIN_FLOOR = 0.5          # «ruina» = capital en la mitad del inicial o menos


def _f(x: float | None) -> float | None:
    return None if x is None or not math.isfinite(x) else float(x)


def daily_r(trades: Sequence[BenchTrade]) -> tuple[np.ndarray, np.ndarray]:
    """(días UTC de cierre, R sumado ese día). La serie de Sharpe y Sortino."""
    if not trades:
        return np.array([], dtype=np.int64), np.array([], dtype=float)
    d = np.array([t.exit_t // DAY_MS for t in trades], dtype=np.int64)
    r = np.array([t.r for t in trades], dtype=float)
    days, inv = np.unique(d, return_inverse=True)
    return days, np.bincount(inv, weights=r, minlength=len(days))


def sharpe_sortino(trades: Sequence[BenchTrade]) -> tuple[float | None, float | None]:
    """Sharpe y Sortino anualizados (√365) del R diario; los días sin operaciones no cuentan."""
    _, r = daily_r(trades)
    if len(r) < 2:
        return None, None
    mu, sd = float(r.mean()), float(r.std(ddof=1))
    down = r[r < 0]
    dsd = float(np.sqrt((down**2).mean())) if len(down) else 0.0
    k = math.sqrt(YEAR_DAYS)
    return (_f(mu / sd * k) if sd > 0 else None, _f(mu / dsd * k) if dsd > 0 else None)


def max_dd(values: np.ndarray) -> float:
    """Mayor caída pico a valle del acumulado (en las unidades de `values`)."""
    if not len(values):
        return 0.0
    cum = np.concatenate(([0.0], np.cumsum(values)))
    return float((np.maximum.accumulate(cum) - cum).max())


def cvar(r: np.ndarray, level: float = CVAR_LEVEL) -> float | None:
    """Media del (1 − level) peor de la muestra (CVaR/ES del R por operación)."""
    if len(r) == 0:
        return None
    k = max(1, int(math.floor(len(r) * (1 - level))))
    return float(np.sort(r)[:k].mean())


def ruin_risk(trades: Sequence[BenchTrade], risk_pct: float, n_trades: int, reps: int,
              rng: np.random.Generator, floor: float = RUIN_FLOOR) -> float | None:
    """Probabilidad de caer a `floor` del capital en `n_trades` operaciones.

    Remuestrea **días completos** con reemplazo (las operaciones de un día están correlacionadas)
    hasta juntar `n_trades`, compone capital × (1 + risk_pct·R) y mira si el mínimo baja del suelo.
    """
    if not trades or risk_pct <= 0 or n_trades < 1 or reps < 1:
        return None
    order = sorted(trades, key=lambda x: (x.exit_t, x.id))
    days = np.array([t.exit_t // DAY_MS for t in order], dtype=np.int64)
    r = np.array([t.r for t in order], dtype=float)
    keys, start = np.unique(days, return_index=True)
    ends = np.append(start[1:], len(days))
    blocks = [r[a:b] for a, b in zip(start, ends, strict=True)]
    per_day = max(1, len(r) // max(1, len(keys)))
    draws = int(math.ceil(n_trades / per_day)) + 1
    ruined = 0
    for _ in range(reps):
        pick = rng.integers(0, len(blocks), size=draws)
        seq = np.concatenate([blocks[i] for i in pick])[:n_trades]
        eq = np.cumprod(np.maximum(1 + risk_pct * seq, 0.0))
        if float(eq.min()) <= floor:
            ruined += 1
    return ruined / reps


def summary(trades: Sequence[BenchTrade], risk_pct: float = 0.01, ruin_trades: int = 200,
            ruin_reps: int = 0, rng: np.random.Generator | None = None) -> dict:
    """Todas las métricas de §5.3 de una política. `ruin_reps = 0` salta el riesgo de ruina."""
    n = len(trades)
    if n == 0:
        return {"n": 0}
    r = np.array([t.r for t in trades], dtype=float)
    gross = np.array([t.gross_r for t in trades], dtype=float)
    cost = np.array([t.cost_r for t in trades], dtype=float)
    mfe = np.array([t.mfe_r for t in trades], dtype=float)
    mae = np.array([t.mae_r for t in trades], dtype=float)
    pnl = np.array([t.pnl_usd for t in trades], dtype=float)
    order = np.array(sorted(range(n), key=lambda i: (trades[i].exit_t, trades[i].id)), dtype=int)
    wins, losses = r > 0, r <= 0
    won, lost = float(r[wins].sum()), float(-r[losses].sum())
    net = float(r.sum())
    dd_r = max_dd(r[order])
    sharpe, sortino = sharpe_sortino(trades)
    hot = mfe >= 1.0
    out = {
        "n": n, "wins": int(wins.sum()), "losses": int(losses.sum()),
        "win_rate": _f(float(wins.mean())),
        "avg_win_r": _f(float(r[wins].mean())) if wins.any() else None,
        "avg_loss_r": _f(float(r[losses].mean())) if losses.any() else None,
        "win_loss_ratio": _f(float(r[wins].mean() / -r[losses].mean()))
        if wins.any() and losses.any() and r[losses].mean() < 0 else None,
        "net_r": _f(net), "won_r": _f(won), "lost_r": _f(-lost),
        "pf": _f(won / lost) if lost > 0 else None,
        "expectancy_r": _f(float(r.mean())), "expectancy_gross_r": _f(float(gross.mean())),
        "cost_r": _f(float(cost.mean())),
        "net_usd": _f(float(pnl.sum())), "expectancy_usd": _f(float(pnl.mean())),
        "max_dd_r": _f(dd_r), "max_dd_usd": _f(max_dd(pnl[order])),
        "recovery_factor": _f(net / dd_r) if dd_r > 0 else None,
        "sharpe_daily": sharpe, "sortino_daily": sortino,
        "cvar95_r": _f(cvar(r)),
        "mfe_r": _f(float(mfe.mean())), "mae_r": _f(float(mae.mean())),
        "mae_over_mfe": _f(float(mae.mean() / mfe.mean())) if mfe.mean() > 0 else None,
        "giveback_r": _f(float((mfe - r).mean())),
        "giveback_winners_r": _f(float((mfe - r)[wins].mean())) if wins.any() else None,
        "mfe1r_n": int(hot.sum()),
        "mfe1r_to_loss": _f(float((r[hot] <= 0).mean())) if hot.any() else None,
        "hours_mean": _f(float(np.mean([t.elapsed_ms for t in trades]) / 3_600_000)),
        "hours_winners": _f(float(np.mean([t.elapsed_ms for t, w in zip(trades, wins, strict=True)
                                           if w]) / 3_600_000)) if wins.any() else None,
        "hours_losers": _f(float(np.mean([t.elapsed_ms for t, lo in zip(trades, losses,
                                                                       strict=True)
                                          if lo]) / 3_600_000)) if losses.any() else None,
        "exits": {k: int(sum(1 for t in trades if t.reason == k))
                  for k in sorted({t.reason for t in trades})},
        "span": [int(min(t.t for t in trades)), int(max(t.exit_t for t in trades))],
    }
    if ruin_reps and rng is not None:
        out["ruin_risk"] = ruin_risk(trades, risk_pct, ruin_trades, ruin_reps, rng)
        out["ruin_params"] = {"risk_pct": risk_pct, "trades": ruin_trades, "reps": ruin_reps,
                              "floor": RUIN_FLOOR}
    return out


def by_group(trades: Sequence[BenchTrade], key: str) -> dict[str, dict]:
    """Métricas por régimen, marco, familia (`sid`) o lado: los cortes de §5.3."""
    groups: dict[str, list[BenchTrade]] = {}
    for t in trades:
        k = {"regime": t.regime, "timeframe": t.timeframe, "sid": t.sid,
             "side": "largo" if t.side > 0 else "corto"}[key]
        groups.setdefault(k, []).append(t)
    return {k: summary(v) for k, v in sorted(groups.items())}
