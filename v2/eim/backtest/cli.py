"""CLI: backtest walk-forward desde el almacén local → `reports/backtest/`.

    python -m eim.backtest.cli --store data --symbol ETHUSDT --tf 1h --train 2000 --test 1000
"""

from __future__ import annotations

import argparse

from eim.backtest.params import BacktestParams
from eim.backtest.report import DEFAULT_DIR, build_report, write_report
from eim.backtest.strategy import PlanStrategy
from eim.backtest.walkforward import walk_forward
from eim.data.store import Store


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", required=True)
    ap.add_argument("--symbol", default="ETHUSDT")
    ap.add_argument("--tf", default="1h")
    ap.add_argument("--train", type=int, default=2000)
    ap.add_argument("--test", type=int, default=1000)
    ap.add_argument("--eval-step", type=int, default=1)
    ap.add_argument("--name", default=None)
    ap.add_argument("--out", default=str(DEFAULT_DIR))
    a = ap.parse_args(argv)
    store = Store(a.store)
    candles = store.read_candles(a.symbol, a.tf)
    funding = store.read_series("funding", a.symbol) or None
    params = BacktestParams(eval_step=a.eval_step)
    wins = walk_forward(candles, funding, lambda _train: PlanStrategy(), params, a.train,
                        a.test, symbol=a.symbol, timeframe=a.tf,
                        sources={"candles": store.source("candles", a.symbol, a.tf) or "?"})
    rep = build_report(wins, params, candles, funding,
                       {"symbol": a.symbol, "timeframe": a.tf, "strategy": "PlanStrategy",
                        "source": store.source("candles", a.symbol, a.tf)})
    pj, pm = write_report(rep, a.name or f"{a.symbol}_{a.tf}", a.out)
    print(pj, pm)


if __name__ == "__main__":
    main()
