"""Constructores sintéticos para los tests del banco de salidas (T131). Sin red y sin disco."""

from __future__ import annotations

import numpy as np

from eim.backtest.params import ZERO_COSTS
from eim.paper.engine import Path
from eim.paper.exits.bench import BenchTrade
from eim.paper.exits.policy import ExitContext, LadderExit, ShadowExit
from eim.paper.ideas import Idea
from eim.paper.params import ExecParams, LadderParams, spec_for
from tests.paper.helpers import H1, M15, T0, bar

SPEC = spec_for("BTCUSDT")
ZERO = ExecParams(costs=ZERO_COSTS, funding_8h_assumed=0.0)
COSTED = ExecParams(funding_8h_assumed=0.0)
LADDER = LadderParams(basis="r", first_r=0.1, step_r=0.05, be_with_ladder=True)
M0 = LadderExit(LADDER)
M1 = ShadowExit()
DAY_MS = 86_400_000


def ctx(path: Path, ep: ExecParams = ZERO, fine: Path | None = None) -> ExitContext:
    return ExitContext(path=path, ep=ep, spec=SPEC, fine=fine)


def walk_path(n: int, seed: int, px0: float = 70_000.0, sigma: float = 0.0015,
              t0: int = T0, step: int = M15) -> Path:
    """Paseo aleatorio de `n` velas de 15 m sin deriva: la referencia honesta de E[R] ≈ 0."""
    rng = np.random.default_rng(seed)
    r = rng.normal(0.0, sigma, n)
    c = px0 * np.exp(np.cumsum(r))
    o = np.concatenate(([px0], c[:-1]))
    wick = np.abs(rng.normal(0.0, sigma / 2, n)) * c
    cs = [bar(t0 + i * step, float(o[i]), float(max(o[i], c[i]) + wick[i]),
              float(min(o[i], c[i]) - wick[i]), float(c[i])) for i in range(n)]
    return Path(cs)


def random_ideas(path: Path, n: int, seed: int, risk_frac: float = 0.01,
                 rr: float = 2.0, strategy: str = "control_aleatorio") -> list[Idea]:
    """`n` entradas a mercado con lado al azar y la misma geometría relativa (el control de §5.3).

    El SL y el TP se ponen a una distancia FIJA del cierre de la vela de decisión, así que ninguna
    idea sabe nada del futuro: es la línea base «entrada al azar con el mismo riesgo» de T27.
    """
    rng = np.random.default_rng(seed)
    last = len(path.t) - 2
    picks = sorted(rng.choice(np.arange(1, max(2, last)), size=min(n, max(1, last - 1)),
                              replace=False))
    out = []
    for k, j in enumerate(picks):
        side = 1 if rng.random() < 0.5 else -1
        px = float(path.c[j])
        d = px * risk_frac
        out.append(Idea(id=f"R{k}", strategy=strategy, family="control", symbol="BTCUSDT",
                        t=int(path.t[j]) + path.step, side=side, kind="market", entry=px,
                        sl=px - side * d, tp=px + side * rr * d, fill_ms=0,
                        hold_ms=int(48 * H1), conf=0.5, why=("control",), timeframe="1h"))
    return out


def trade(r: float, day: int = 0, tid: str = "t", policy: str = "M0", mfe: float = 0.0,
          mae: float = 0.0, cost_r: float = 0.0, hours: float = 1.0,
          regime: str = "range", side: int = 1, risk_usd: float = 100.0) -> BenchTrade:
    """Operación del banco hecha a mano (para las métricas y los pliegues)."""
    t = T0 + day * DAY_MS
    el = int(hours * H1)
    return BenchTrade(id=tid, policy=policy, t=t, fill_t=t, exit_t=t + el, side=side,
                      sid="s@1h", timeframe="1h", regime=regime, origin="backtest", reason="SL",
                      qty=1.0, risk_usd=risk_usd, pnl_usd=r * risk_usd,
                      gross_usd=(r + cost_r) * risk_usd, cost_usd=cost_r * risk_usd, r=r,
                      gross_r=r + cost_r, cost_r=cost_r, mfe_r=mfe, mae_r=mae, elapsed_ms=el)


def series(rs: list[float], policy: str = "M0", day0: int = 0,
           per_day: int = 1, **kw) -> list[BenchTrade]:
    """Serie de operaciones, `per_day` por día UTC."""
    return [trade(r, day=day0 + i // per_day, tid=f"{policy}-{i}", policy=policy, **kw)
            for i, r in enumerate(rs)]
