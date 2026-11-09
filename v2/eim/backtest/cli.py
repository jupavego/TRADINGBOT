"""CLI: backtest walk-forward desde el almacén local → `reports/backtest/`.

    python -m eim.backtest.cli --store data --symbol ETHUSDT --tf 1h --train 2000 --test 1000

Se calcula sobre una instantánea congelada de la serie (T124) y el resultado queda registrado:
`python -m eim.repro repetir <result_id>` lo recalcula y dice qué cambió si no coincide.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from eim.backtest.params import BacktestParams
from eim.backtest.report import DEFAULT_DIR, build_report, figures, write_report
from eim.backtest.strategy import PlanStrategy
from eim.backtest.walkforward import walk_forward
from eim.data.results import ResultStore
from eim.data.snapshots import SnapshotStore
from eim.data.store import Store
from eim.repro.code import fingerprint
from eim.repro.stamp import stamp


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
    ap.add_argument("--root", default=None,
                    help="carpeta de instantáneas y resultados (T124); por defecto, --store")
    a = ap.parse_args(argv)
    root = a.root or a.store
    snap = SnapshotStore(root).create(Store(a.store), a.symbol, a.tf, origin="backtest.cli")
    view = snap.view()                       # se mide sobre la instantánea, no sobre el almacén
    candles = view.read_candles(a.symbol, a.tf)
    funding = view.read_series("funding", a.symbol) or None
    source = view.source("candles", a.symbol, a.tf) or "?"
    params = BacktestParams(eval_step=a.eval_step)
    wins = walk_forward(candles, funding, lambda _train: PlanStrategy(), params, a.train,
                        a.test, symbol=a.symbol, timeframe=a.tf, sources={"candles": source})
    rep = build_report(wins, params, candles, funding,
                       {"symbol": a.symbol, "timeframe": a.tf, "strategy": "PlanStrategy",
                        "source": source})
    name = a.name or f"{a.symbol}_{a.tf}"
    rec = ResultStore(root).register(
        "backtest", f"backtest {name}", [snap.info.id],
        {"symbol": a.symbol, "timeframe": a.tf, "train": a.train, "test": a.test,
         "backtest": params.model_dump()}, fingerprint(), figures(wins, params),
        str(Path(a.out) / f"{name}.json"))
    rep["meta"]["reproducibility"] = stamp([snap.info], rec.id)
    pj, pm = write_report(rep, name, a.out)
    print(pj, pm, rec.id)


if __name__ == "__main__":
    main()
