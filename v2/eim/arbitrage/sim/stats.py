"""Estadística de las operaciones simuladas (T43).

Rentabilidad neta anualizada (mientras invierte y sobre todo el período, con el capital
ocioso), distribución por operación, peor caso, caída máxima, IC95 % de la media y valor p
(bootstrap por bloques: los regímenes de funding persisten) y la distribución de pérdida por
pata incompleta según la latencia asumida (escalado browniano de rendimientos reales de
15 min: conserva las colas, pero bajo el segundo la microestructura domina — supuesto).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np

from eim.arbitrage.sim.params import SimParams
from eim.arbitrage.sim.trade import SimTrade
from eim.backtest.metrics import max_drawdown

YEAR_H = 8766.0
PCTS = (1, 5, 10, 25, 50, 75, 90, 95, 99)
BAR_15M_MS = 900_000


def latency_returns(rets_15m: np.ndarray | None, latency_ms: float) -> np.ndarray | None:
    """Rendimientos durante `latency_ms` (escalado √t de los de 15 min)."""
    if rets_15m is None or len(rets_15m) < 10:
        return None
    r = rets_15m[np.isfinite(rets_15m)]
    return r * math.sqrt(latency_ms / BAR_15M_MS)


def incident_losses(undo_frac: float, r_lat: np.ndarray | None, n: int,
                    rng: np.random.Generator) -> np.ndarray:
    """Pérdida (fracción del nocional, + = pierde) de `n` incidentes de pata incompleta:
    deshacer la pata ejecutada más el movimiento mientras queda sin cubrir (signo al azar)."""
    if r_lat is None:
        return np.full(n, undo_frac)
    s = rng.choice((-1.0, 1.0), size=n)
    return undo_frac - s * rng.choice(r_lat, size=n)


def legging_table(rets_15m: np.ndarray | None, latencies: tuple[float, ...], undo_frac: float,
                  p_fail: float, n: int = 100_000, seed: int = 0) -> list[dict]:
    rng = np.random.default_rng(seed)
    out = []
    for lat in latencies:
        r = latency_returns(rets_15m, lat)
        loss = incident_losses(undo_frac, r, n, rng) * 1e4
        out.append({"latency_ms": lat, "mean_bps": float(loss.mean()),
                    "p95_bps": float(np.percentile(loss, 95)),
                    "p99_bps": float(np.percentile(loss, 99)), "max_bps": float(loss.max()),
                    "expected_per_event_bps": float(p_fail * loss.mean()),
                    "drift_std_bps": float(r.std() * 1e4) if r is not None else 0.0})
    return out


def mc_nets(trades: list[SimTrade], rets: dict[str, np.ndarray | None], sp: SimParams,
            latency_ms: float | None = None) -> np.ndarray:
    """Neto por operación (USD) con incidentes de pata incompleta sorteados en cada
    ejecución de dos patas: (operaciones × `mc_paths`). Sin incidente queda el
    deslizamiento por latencia de la segunda pata (media 0)."""
    rng = np.random.default_rng(sp.seed)
    lat = latency_ms or sp.latency_ms
    out = np.zeros((len(trades), sp.mc_paths))
    for k, tr in enumerate(trades):
        r = latency_returns(rets.get(tr.asset), lat)
        base = tr.net + tr.legging  # se reemplaza el valor esperado por sorteos
        loss = np.zeros(sp.mc_paths)
        for notional, undo in tr.events:
            fail = rng.random(sp.mc_paths) < sp.p_fail
            move = 0.0 if r is None else -rng.choice((-1.0, 1.0), sp.mc_paths) * rng.choice(
                r, sp.mc_paths) * notional
            loss += np.where(fail, undo, 0.0) + move
        out[k] = base - loss
    return out


def block_bootstrap(x: np.ndarray, block: int, n_boot: int = 2000,
                    seed: int = 0) -> tuple[float, float, float]:
    """(IC95 inferior, IC95 superior, P(media ≤ 0)) de la media por bloques circulares."""
    n = len(x)
    if n < 2:
        return (float("nan"), float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    block = max(1, min(block, n))
    k = math.ceil(n / block)
    starts = rng.integers(0, n, size=(n_boot, k))
    idx = ((starts[:, :, None] + np.arange(block)[None, None, :]) % n).reshape(n_boot, -1)[:, :n]
    means = x[idx].mean(axis=1)
    return (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)),
            float((means <= 0).mean()))


def trade_stats(trades: list[SimTrade], *, period_ms: int, n_assets: int, sp: SimParams,
                rets: dict[str, np.ndarray | None]) -> dict:
    years = max(period_ms / (YEAR_H * 3_600_000), 1e-9)
    if not trades:
        return {"n": 0, "years": years, "apr_period": 0.0, "apr_invested": None,
                "mean_bps": None, "note": "el selector no tomó ninguna operación"}
    net = np.array([t.net for t in trades])
    bps = np.array([t.net_bps for t in trades])
    cap = np.array([t.capital for t in trades])
    hold = np.array([t.hold_h for t in trades])
    cap_ref = float(cap.mean())
    equity = cap_ref * n_assets + np.concatenate(([0.0], np.cumsum(net)))
    lo, hi, p_le0 = block_bootstrap(bps, max(1, int(math.sqrt(len(bps)))), seed=sp.seed)
    mc = mc_nets(trades, rets, sp) / cap[:, None] * 1e4
    sums = {k: float(sum(getattr(t, k) for t in trades))
            for k in ("price_pnl", "funding", "fees", "slippage", "legging", "liq_loss")}
    years_tab: dict[int, dict] = {}
    for t in trades:
        y = datetime.fromtimestamp(t.entry_t / 1000, UTC).year
        d = years_tab.setdefault(y, {"n": 0, "net_usd": 0.0, "hold_h": 0.0})
        d["n"] += 1
        d["net_usd"] += t.net
        d["hold_h"] += t.hold_h
    return {
        "n": len(trades), "years": years, "net_usd": float(net.sum()),
        "capital_ref": cap_ref, "invested_frac": float(hold.sum() / (years * YEAR_H * n_assets)),
        "apr_period": float(net.sum() / (cap_ref * n_assets) / years),
        "apr_invested": float(net.sum() / float((cap * hold / YEAR_H).sum()))
        if hold.sum() > 0 else None,
        "mean_bps": float(bps.mean()), "median_bps": float(np.median(bps)),
        "std_bps": float(bps.std(ddof=1)) if len(bps) > 1 else 0.0,
        "pcts_bps": {p: float(np.percentile(bps, p)) for p in PCTS},
        "worst_bps": float(bps.min()), "best_bps": float(bps.max()),
        "win_rate": float((net > 0).mean()), "mean_hold_h": float(hold.mean()),
        "max_dd": max_drawdown(equity), "ci95_mean_bps": [lo, hi], "p_value": p_le0,
        "mc_pcts_bps": {p: float(np.percentile(mc, p)) for p in (1, 5, 50)},
        "mc_worst_bps": float(mc.min()), "costs": sums,
        "rebalances": int(sum(t.rebalances for t in trades)),
        "liquidations": int(sum(t.exit_reason == "liq" for t in trades)),
        "incomplete": int(sum(t.incomplete for t in trades)),
        "missing_depth": sorted({k for t in trades for k in t.missing_depth}),
        "by_year": {y: {**d, "apr": d["net_usd"] / (cap_ref * n_assets)
                        / _year_frac(y, trades)} for y, d in sorted(years_tab.items())},
        **_last_year(trades, cap_ref * n_assets),
    }


def _last_year(trades: list[SimTrade], capital: float) -> dict:
    """Rentabilidad de los últimos 365 días con datos (régimen actual): el neto de cada
    operación se reparte en proporción al tiempo que cae dentro de la ventana."""
    end = max(t.exit_t for t in trades)
    start = end - int(365 * 24 * 3_600_000)
    net = 0.0
    for t in trades:
        span = max(t.exit_t - t.entry_t, 1)
        net += t.net * max(0, min(t.exit_t, end) - max(t.entry_t, start)) / span
    return {"last_year_apr": net / capital, "last_year": [start, end]}


def _year_frac(year: int, trades: list[SimTrade]) -> float:
    """Fracción del año cubierta por el período simulado (primer/último año parciales)."""
    a = max(datetime(year, 1, 1, tzinfo=UTC).timestamp() * 1000, min(t.entry_t for t in trades))
    b = min(datetime(year + 1, 1, 1, tzinfo=UTC).timestamp() * 1000,
            max(t.exit_t for t in trades))
    return max((b - a) / (YEAR_H * 3_600_000), 1 / 365)
