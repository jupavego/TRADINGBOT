"""Evaluación fuera de muestra: pinball loss de cuantiles y cobertura de bandas 50/80 %.

Recorre orígenes en una ventana histórica (walk-forward), proyecta N trayectorias desde cada
uno y compara los cierres proyectados con los reales. Uso:
`python -m eim.forecast.eval --symbol BTCUSDT --timeframe 1h --data-dir data`
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass

import numpy as np

from eim.core import Candle, MarketSnapshot
from eim.forecast.engine import Engine

QUANTILES = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)


@dataclass(frozen=True)
class EvalReport:
    engine: str
    origins: int
    horizon: int
    n_paths: int
    pinball: float  # media sobre cuantiles/pasos, en retorno log (menor = mejor)
    coverage_50: float
    coverage_80: float
    nominal_50: float = 0.5
    nominal_80: float = 0.8


def _pinball(y: np.ndarray, q: np.ndarray, tau: float) -> np.ndarray:
    d = y - q
    return np.maximum(tau * d, (tau - 1) * d)


def evaluate(
    engine: Engine,
    candles: list[Candle],
    *,
    symbol: str = "X",
    timeframe: str = "1h",
    horizon: int = 25,
    n: int = 200,
    window: int = 600,
    stride: int = 25,
    context: int = 1500,
) -> EvalReport:
    """Evalúa `engine` en las últimas `window` velas (orígenes cada `stride`)."""
    first = max(len(candles) - window, 150)
    losses: list[float] = []
    hit50: list[np.ndarray] = []
    hit80: list[np.ndarray] = []
    for i in range(first, len(candles) - horizon, stride):
        snap = MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles[max(0, i - context) : i],
            asof=candles[i].t,
            sources={},
            coverage={},
        )
        paths = engine.sample(snap, horizon, n)
        base = candles[i - 1].c
        real = np.log(np.array([c.c for c in candles[i : i + horizon]]) / base)
        sim = np.log(paths[:, :, 3] / base)  # (n, horizon)
        qs = np.quantile(sim, QUANTILES, axis=0)  # (nq, horizon)
        pin = [_pinball(real, qs[k], t).mean() for k, t in enumerate(QUANTILES)]
        losses.append(float(np.mean(pin)))
        q = dict(zip(QUANTILES, qs, strict=True))
        hit50.append((real >= q[0.25]) & (real <= q[0.75]))
        hit80.append((real >= q[0.1]) & (real <= q[0.9]))
    if not losses:
        raise ValueError("ventana insuficiente para evaluar")
    return EvalReport(
        engine=engine.name,
        origins=len(losses),
        horizon=horizon,
        n_paths=n,
        pinball=float(np.mean(losses)),
        coverage_50=float(np.mean(np.concatenate(hit50))),
        coverage_80=float(np.mean(np.concatenate(hit80))),
    )


def format_report(reports: list[EvalReport]) -> str:
    lines = ["motor      orígenes  pinball     cob50  cob80"]
    for r in reports:
        lines.append(
            f"{r.engine:<10} {r.origins:>8}  {r.pinball:.6f}  "
            f"{r.coverage_50:5.1%}  {r.coverage_80:5.1%}"
        )
    base = next((r for r in reports if r.engine == "base"), None)
    others = [r for r in reports if r.engine != "base"]
    if base is not None and others:
        best = min(others, key=lambda r: r.pinball)
        if best.pinball < base.pinball:
            lines.append(f"→ {best.engine} supera a la línea base (pinball menor): recomendable")
        else:
            lines.append(f"→ {best.engine} no supera a la línea base: NO se recomienda")
    return "\n".join(lines)


def main() -> None:  # pragma: no cover - uso manual con datos reales
    from eim.data.store import Store
    from eim.forecast.base_engine import BaseEngine
    from eim.forecast.kronos_engine import KronosEngine

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--timeframe", default="1h")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--window", type=int, default=600)
    ap.add_argument("--kronos", action="store_true")
    args = ap.parse_args()
    candles = Store(args.data_dir).read_candles(args.symbol, args.timeframe)
    engines: list[Engine] = [BaseEngine()]
    if args.kronos and KronosEngine.available():
        engines.append(KronosEngine())
    reports = [
        evaluate(
            e, candles, symbol=args.symbol, timeframe=args.timeframe, window=args.window,
            n=200 if e.name == "base" else 50,
        )
        for e in engines
    ]
    print(format_report(reports))
    print([asdict(r) for r in reports])


if __name__ == "__main__":  # pragma: no cover
    main()
