"""Cómo se recalcula cada tipo de resultado (T124): datos ya leídos + parámetros → cifras.

Cada tipo declara `recompute(instantáneas, parámetros) -> cifras` (con el código de hoy) y
`current(parámetros grabados) -> parámetros vigentes` (los que el productor usaría hoy). Los tipos
sin `recompute` solo admiten la comprobación de datos: la calibración (horas de búsqueda) y la
puntuación de bots (lee posturas y contextos de bases que la API tiene abiertas).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from eim.data.snapshots import Snapshot


@dataclass(frozen=True)
class Kind:
    name: str
    title: str
    recompute: Callable[[list[Snapshot], dict], dict] | None
    current: Callable[[dict], dict]
    why_not: str = ""        # por qué no se recalcula (si `recompute` es None)


def _series(snap: Snapshot, lookback: int):
    from eim.calibration.evaluate import Series
    from eim.calibration.inputs import InputCache

    i = snap.info
    return Series(i.symbol, i.timeframe, snap.candles, snap.funding or None,
                  InputCache(snap.candles, i.symbol, i.timeframe, lookback), i.source)


def edge_window(snaps: list[Snapshot], params: dict) -> dict:
    """Una ventana de la puerta de edge (T27): mismo contexto previo, misma estrategia."""
    from eim.backtest.params import BacktestParams
    from eim.calibration.gate_cli import plan_strategy, run, window_figures

    bt = BacktestParams(**params["backtest"])
    s = _series(snaps[0], bt.lookback)
    idx = {c.t: k for k, c in enumerate(s.candles)}
    if params["from_t"] not in idx or params["to_t"] not in idx:
        raise ValueError("la instantánea no contiene la ventana")
    w = (idx[params["from_t"]], idx[params["to_t"]] + 1)
    return window_figures(s, w, run(s, w, plan_strategy(s, params["values"]), bt), bt)


def edge_current(params: dict) -> dict:
    from eim.calibration.gate_cli import gate_backtest
    from eim.calibration.space import defaults

    return {**params, "values": defaults(), "backtest": gate_backtest().model_dump()}


def backtest(snaps: list[Snapshot], params: dict) -> dict:
    """Walk-forward de `python -m eim.backtest.cli` (estrategia completa de agentes)."""
    from eim.backtest.params import BacktestParams
    from eim.backtest.report import figures
    from eim.backtest.strategy import PlanStrategy
    from eim.backtest.walkforward import walk_forward

    bt, i = BacktestParams(**params["backtest"]), snaps[0].info
    wins = walk_forward(snaps[0].candles, snaps[0].funding or None, lambda _t: PlanStrategy(), bt,
                        params["train"], params["test"], symbol=i.symbol, timeframe=i.timeframe,
                        sources={"candles": i.source})
    return figures(wins, bt)


def backtest_current(params: dict) -> dict:
    from eim.backtest.params import BacktestParams

    return {**params,
            "backtest": BacktestParams(eval_step=params["backtest"]["eval_step"]).model_dump()}


def _same(params: dict) -> dict:
    return params


KINDS: dict[str, Kind] = {
    "edge_window": Kind("edge_window", "ventana de la puerta de edge (T27)", edge_window,
                        edge_current),
    "backtest": Kind("backtest", "backtest walk-forward", backtest, backtest_current),
    "calibration": Kind("calibration", "calibración walk-forward anidada (T26)", None, _same,
                        "la búsqueda dura horas: solo se comprueban los datos (BACKLOG T124)"),
    "bot_scorecard": Kind("bot_scorecard", "puntuación del escuadrón de bots (T59)", None, _same,
                          "lee posturas y contextos de bases abiertas por la API: solo se "
                          "comprueban los datos (BACKLOG T124)"),
}


def same(a, b) -> bool:
    """Igualdad exacta de una cifra (None con None, NaN con NaN, 28 con 28.0)."""
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, int | float) and isinstance(b, int | float):
        fa, fb = float(a), float(b)
        return fa == fb or (fa != fa and fb != fb)
    return a == b


def compare(recorded: dict, got: dict) -> list[dict]:
    """Cifras grabadas que no se obtienen igual (solo las que el resultado grabó)."""
    return [{"figure": k, "recorded": v, "now": got.get(k)}
            for k, v in recorded.items() if not same(v, got.get(k))]


def changed_keys(a: dict, b: dict, prefix: str = "") -> list[str]:
    """Claves (con ruta) cuyo valor difiere entre dos juegos de parámetros."""
    out = []
    for k in sorted(set(a) | set(b)):
        x, y = a.get(k), b.get(k)
        if isinstance(x, dict) and isinstance(y, dict):
            out += changed_keys(x, y, f"{prefix}{k}.")
        elif not same(x, y):
            out.append(f"{prefix}{k}")
    return out
