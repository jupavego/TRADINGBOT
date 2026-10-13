"""Métricas del backtest con intervalos por bootstrap (puras, reproducibles con semilla)."""

from __future__ import annotations

import math

import numpy as np

from eim.backtest.engine import BacktestResult

N_BOOT = 1000
CI = (2.5, 97.5)


def _sharpe(r: np.ndarray, ppy: float) -> float:
    sd = r.std(ddof=1) if len(r) > 1 else 0.0
    return float(r.mean() / sd * math.sqrt(ppy)) if sd > 0 else 0.0


def _sortino(r: np.ndarray, ppy: float) -> float:
    dd = math.sqrt(float(np.mean(np.minimum(r, 0.0) ** 2))) if len(r) else 0.0
    return float(r.mean() / dd * math.sqrt(ppy)) if dd > 0 else 0.0


def max_drawdown(eq: np.ndarray) -> float:
    """Caída máxima desde un máximo (fracción positiva)."""
    if len(eq) == 0:
        return 0.0
    peak = np.maximum.accumulate(eq)
    return float(np.max((peak - eq) / np.where(peak > 0, peak, 1.0)))


def profit_factor(pnl: np.ndarray) -> float | None:
    """Ganancias brutas / pérdidas brutas; None si no hay pérdidas (indefinido)."""
    loss = -pnl[pnl < 0].sum()
    return float(pnl[pnl > 0].sum() / loss) if loss > 0 else None


def _block_idx(rng: np.random.Generator, n: int, block: int) -> np.ndarray:
    """Índices de bootstrap por bloques circulares (conserva la autocorrelación)."""
    k = math.ceil(n / block)
    starts = rng.integers(0, n, size=k)
    return ((starts[:, None] + np.arange(block)[None, :]) % n).ravel()[:n]


def _ci(vals: list[float]) -> list[float] | None:
    v = [x for x in vals if x is not None and math.isfinite(x)]
    return [float(np.percentile(v, CI[0])), float(np.percentile(v, CI[1]))] if v else None


def compute_metrics(res: BacktestResult, initial_equity: float, bars_per_year: float,
                    seed: int = 0, n_boot: int = N_BOOT) -> dict:
    """Retorno, Sharpe/Sortino, drawdown, R esperado, acierto, factor de beneficio, exposición,
    nº de operaciones; con IC95% por bootstrap (operaciones remuestreadas; barras por bloques)."""
    rng = np.random.default_rng(seed)
    eq = np.array(res.equity, dtype=float)
    r = np.diff(eq) / eq[:-1] if len(eq) > 1 else np.array([])
    pnl = np.array([t.net_pnl for t in res.trades])
    rr = np.array([t.r_multiple for t in res.trades])
    n_tr, n_bars = len(pnl), len(eq)
    out: dict = {
        "n_trades": n_tr, "n_bars": n_bars, "initial_equity": initial_equity,
        "final_equity": float(eq[-1]) if n_bars else initial_equity,
        "total_return": float(eq[-1] / initial_equity - 1) if n_bars else 0.0,
        "sharpe": _sharpe(r, bars_per_year), "sortino": _sortino(r, bars_per_year),
        "max_drawdown": max_drawdown(eq),
        "expectancy_r": float(rr.mean()) if n_tr else None,
        "win_rate": float((pnl > 0).mean()) if n_tr else None,
        "profit_factor": profit_factor(pnl) if n_tr else None,
        "exposure": res.stats.get("bars_in_position", 0) / n_bars if n_bars else 0.0,
        "ci95": {},
    }
    if n_tr >= 2:
        pf, wr, ex = [], [], []
        for _ in range(n_boot):
            idx = rng.integers(0, n_tr, size=n_tr)
            pf.append(profit_factor(pnl[idx]))
            wr.append(float((pnl[idx] > 0).mean()))
            ex.append(float(rr[idx].mean()))
        out["ci95"].update(expectancy_r=_ci(ex), win_rate=_ci(wr), profit_factor=_ci(pf))
    if len(r) >= 10:
        block = max(2, int(math.sqrt(len(r))))
        sh = []
        for _ in range(n_boot):
            rs = r[_block_idx(rng, len(r), block)]
            sh.append(_sharpe(rs, bars_per_year))
        out["ci95"]["sharpe"] = _ci(sh)
    else:
        out["warning_few_bars"] = "menos de 10 barras: sin IC de Sharpe"
    if n_tr < 30:
        out["warning_few_trades"] = f"{n_tr} operaciones: los intervalos son muy anchos"
    return out


def cost_breakdown(res: BacktestResult) -> dict:
    """Desglose exacto: bruto − comisiones − deslizamiento − funding − liquidación = neto."""
    ts = res.trades
    gross = sum(t.gross_pnl for t in ts)
    d = {"gross_pnl": gross, "fees": sum(t.fees for t in ts),
         "slippage": sum(t.slippage for t in ts), "funding": sum(t.funding for t in ts),
         "liquidation_fees": sum(t.liq_fee for t in ts), "net_pnl": sum(t.net_pnl for t in ts)}
    d["total_costs"] = d["fees"] + d["slippage"] + d["funding"] + d["liquidation_fees"]
    exp, obs = res.stats.get("funding_expected", 0), res.stats.get("funding_observed", 0)
    d["funding_settlements"] = {"expected": exp, "observed": obs}
    if obs < exp:
        d["warning_funding"] = (f"faltan {exp - obs} de {exp} liquidaciones de funding en los datos"
                                " (se asumen 0: el funding real puede cambiar el resultado)")
    return d
