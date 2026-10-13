"""Walk-forward con ventanas de prueba disjuntas y (opcional) ajuste solo con datos previos."""

from __future__ import annotations

from collections.abc import Callable

from eim.backtest.engine import BacktestResult, run_backtest
from eim.backtest.params import BacktestParams
from eim.backtest.strategy import Strategy
from eim.core import Candle


def make_windows(n: int, train: int, test: int, warmup: int = 0) -> list[dict]:
    """Ventanas `[train | test]` que avanzan `test` velas: las pruebas no se solapan jamás.

    Índices sobre la serie completa; `ctx_from` = inicio del contexto/calentamiento que la
    estrategia puede VER (anterior a `test_from`, nunca posterior a su inicio).
    """
    out, s = [], 0
    while s + train + test <= n:
        a = s + train
        out.append({"train_from": s, "test_from": a, "test_to": a + test,
                    "ctx_from": max(0, a - warmup)})
        s += test
    return out


def walk_forward(
    candles: list[Candle],
    funding: list[tuple[int, float]] | None,
    make_strategy: Callable[[list[Candle] | None], Strategy],
    params: BacktestParams,
    train: int,
    test: int,
    warmup: int = 200,
    fit: bool = False,
    **kw,
) -> list[tuple[dict, BacktestResult]]:
    """Corre cada ventana de prueba con capital inicial propio y una estrategia NUEVA.

    `make_strategy(train_candles)` recibe las velas de entrenamiento si `fit=True` (para
    calibrar solo con el pasado; T26) y `None` si no. Devuelve [(ventana, resultado)].
    """
    results = []
    for w in make_windows(len(candles), train, test, warmup):
        strat = make_strategy(candles[w["train_from"]:w["test_from"]] if fit else None)
        seg = candles[w["ctx_from"]:w["test_to"]]
        res = run_backtest(seg, funding, strat, params, trade_from=w["test_from"] - w["ctx_from"],
                           **kw)
        results.append((w, res))
    return results
