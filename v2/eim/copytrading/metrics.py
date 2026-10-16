"""Métricas de una muestra de operaciones cerradas (puro). Importes en USD (USDC)."""

from __future__ import annotations

from collections import defaultdict
from statistics import median

from eim.copytrading import stats as S
from eim.copytrading.params import ScoreParams
from eim.copytrading.trades import Trip
from eim.core.market import Frozen

DAY_MS = 86_400_000


class TradeStats(Frozen):
    n: int = 0  # operaciones cerradas y completas (de plano a plano)
    n_open: int = 0
    n_partial: int = 0  # abiertas antes del historial o cortadas por un hueco: no cuentan
    wins: int = 0
    losses: int = 0
    win_rate: float | None = None
    net: float = 0.0  # PnL − comisiones + funding
    pnl: float = 0.0
    fees: float = 0.0
    funding: float = 0.0
    ret: float | None = None  # neto / valor de la cuenta
    profit_factor: float | None = None  # None sin pérdidas (∞) o sin operaciones
    avg_win: float | None = None
    avg_loss: float | None = None
    payoff: float | None = None  # ganancia media / |pérdida media|
    max_dd: float | None = None  # sobre el neto acumulado por operación / cuenta
    mean: float | None = None  # neto medio por operación
    mean_ci: tuple[float, float] | None = None
    mean_bps: float | None = None  # Σ neto / Σ nocional máximo
    sharpe: float | None = None  # por operación
    sharpe_ci: tuple[float, float] | None = None
    dsr: float | None = None
    sr0: float | None = None
    skew: float | None = None
    kurt: float | None = None
    first_t: int | None = None
    last_t: int | None = None
    days: float = 0.0
    hold_ms: float | None = None  # mediana
    n_assets: int = 0
    assets: dict[str, float] = {}  # fracción del nocional por moneda
    top_asset: str | None = None
    top_asset_share: float | None = None
    lev_median: float | None = None
    lev_max: float | None = None
    avg_down_share: float | None = None
    martingale: float | None = None  # tamaño tras pérdida / tras ganancia
    best_trade_share: float | None = None  # mejor operación / neto (≥ 1: sin ella no gana)
    best_day_share: float | None = None
    best_asset_share: float | None = None
    best_asset: str | None = None  # moneda con más neto
    windows: int = 0
    windows_pos: int = 0
    worst_window: float | None = None
    taker_share: float | None = None
    liquidations: int = 0


def _martingale(closed: list[Trip], min_n: int) -> float | None:
    """Tamaño medio de la operación siguiente a una pérdida vs a una ganancia."""
    by_close = sorted(closed, key=lambda t: t.t_close or 0)
    after: dict[bool, list[float]] = {True: [], False: []}
    j, last = 0, None
    for tr in sorted(closed, key=lambda t: t.t_open):
        while j < len(by_close) and (by_close[j].t_close or 0) <= tr.t_open:
            last = by_close[j]
            j += 1
        if last is not None:
            after[last.net < 0].append(tr.notional_max)
    lost, won = after[True], after[False]
    if len(lost) < min_n or len(won) < min_n:
        return None
    mw = sum(won) / len(won)
    return (sum(lost) / len(lost)) / mw if mw > 0 else None


def _share(best: float, net: float) -> float | None:
    return best / net if net > 0 else None


def trade_stats(trips: list[Trip], account_value: float | None, n_trials: int,
                p: ScoreParams) -> TradeStats:
    closed = [t for t in trips if t.closed and t.complete]
    n_open = sum(not t.closed for t in trips)
    out = {"n": len(closed), "n_open": n_open, "n_partial": sum(not t.complete for t in trips),
           "liquidations": sum(t.liquidated for t in trips)}
    if not closed:
        return TradeStats(**out)
    xs = [t.net for t in closed]
    wins, losses = [x for x in xs if x > 0], [x for x in xs if x < 0]
    net = sum(xs)
    av = account_value if account_value and account_value >= p.min_account_usd else None
    m, _, skew, kurt = S.moments(xs)
    dsr = S.deflated(xs, n_trials)
    notional = sum(t.notional_max for t in closed)
    by_asset: dict[str, float] = defaultdict(float)
    asset_net: dict[str, float] = defaultdict(float)
    for t in closed:
        by_asset[t.symbol] += t.notional_max
        asset_net[t.symbol] += t.net
    assets = {k: v / notional for k, v in by_asset.items()} if notional else {}
    top = max(assets, key=assets.__getitem__) if assets else None
    win_net: dict[int, float] = defaultdict(float)
    for t in closed:
        win_net[(t.t_close or 0) // p.window_ms] += t.net
    levs = [t.leverage_max for t in closed if t.leverage_max is not None]
    first, last = min(t.t_open for t in closed), max(t.t_close or 0 for t in closed)
    out |= {
        "wins": len(wins), "losses": len(losses), "win_rate": len(wins) / len(xs),
        "net": net, "pnl": sum(t.pnl for t in closed), "fees": sum(t.fees for t in closed),
        "funding": sum(t.funding for t in closed), "ret": net / av if av else None,
        "profit_factor": sum(wins) / -sum(losses) if losses else None,
        "avg_win": sum(wins) / len(wins) if wins else None,
        "avg_loss": sum(losses) / len(losses) if losses else None,
        "max_dd": S.max_drawdown([t.net for t in sorted(closed, key=lambda t: t.t_close or 0)],
                                 av),
        "mean": m, "mean_ci": S.mean_ci(xs, p.ci_level, n_trials),
        "mean_bps": net / notional * 1e4 if notional else None,
        "sharpe": S.sharpe(xs), "sharpe_ci": S.sharpe_ci(xs, p.ci_level, n_trials),
        "dsr": dsr[0] if dsr else None, "sr0": dsr[1] if dsr else None,
        "skew": skew if len(xs) >= 3 else None, "kurt": kurt if len(xs) >= 3 else None,
        "first_t": first, "last_t": last, "days": (last - first) / DAY_MS,
        "hold_ms": median([t.hold_ms or 0 for t in closed]),
        "n_assets": len(assets), "assets": assets, "top_asset": top,
        "top_asset_share": assets[top] if top else None,
        "lev_median": median(levs) if levs else None, "lev_max": max(levs) if levs else None,
        "avg_down_share": sum(t.avg_downs > 0 for t in closed) / len(closed),
        "martingale": _martingale(closed, p.martingale_min_n),
        "best_trade_share": _share(max(xs), net),
        "best_day_share": _share(max(win_net.values()), net),
        "best_asset_share": _share(max(asset_net.values()), net) if len(asset_net) > 1 else None,
        "best_asset": max(asset_net, key=asset_net.__getitem__),
        "windows": len(win_net), "windows_pos": sum(v > 0 for v in win_net.values()),
        "worst_window": min(win_net.values()),
        "taker_share": sum(t.taker_share for t in closed) / len(closed),
    }
    if out["avg_win"] is not None and out["avg_loss"]:
        out["payoff"] = out["avg_win"] / -out["avg_loss"]
    return TradeStats(**out)
