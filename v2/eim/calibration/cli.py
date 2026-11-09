"""CLI: calibración anidada desde el almacén local → `reports/calibration/` + versión de params.

    python -m eim.calibration.cli --store data --symbol BTCUSDT --control ETHUSDT --tf 1h

T124: las series se leen de instantáneas congeladas y el resultado queda registrado con sus ids
(`calibration`); `python -m eim.repro repetir <id>` comprueba que los datos sigan siendo esos.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from eim.backtest.params import BacktestParams
from eim.backtest.report import data_hash
from eim.calibration.evaluate import ObjectiveParams, Series
from eim.calibration.inputs import InputCache
from eim.calibration.nested import fidelity, run_nested
from eim.calibration.report import DEFAULT_DIR, write_report, write_version
from eim.data.results import ResultStore
from eim.data.snapshots import SnapshotStore
from eim.data.store import Store
from eim.repro.code import fingerprint
from eim.repro.stamp import stamp


def load_series(store: Store, symbol: str, tf: str, lookback: int,
                cache_dir: Path) -> tuple[Series, Path]:
    candles = store.read_candles(symbol, tf)
    cache = InputCache(candles, symbol, tf, lookback)
    path = cache_dir / f"{symbol}_{tf}_{lookback}_{data_hash(candles, None)}.pkl"
    cache.load(path)
    return Series(symbol, tf, candles, store.read_series("funding", symbol) or None, cache,
                  store.source("candles", symbol, tf) or "?"), path


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", required=True)
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--control", default="ETHUSDT")
    ap.add_argument("--tf", default="1h")
    ap.add_argument("--train", type=int, default=8760)
    ap.add_argument("--test", type=int, default=4380)
    ap.add_argument("--inner", type=int, default=3)
    ap.add_argument("--trials", type=int, default=40)
    ap.add_argument("--top-k", type=int, default=3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--fidelity-bars", type=int, default=720)
    ap.add_argument("--version", default=None)
    ap.add_argument("--out", default=str(DEFAULT_DIR))
    ap.add_argument("--root", default=None,
                    help="carpeta de instantáneas y resultados (T124); por defecto, --store")
    a = ap.parse_args(argv)
    t0 = time.time()
    bt = BacktestParams(eval_step=6)   # = replay_step del plan: decisiones alineadas al caché
    store, cdir, root = Store(a.store), Path(a.out) / "cache", a.root or a.store
    snaps = {sym: SnapshotStore(root).create(store, sym, a.tf, origin="calibration.cli")
             for sym in [a.symbol] + ([a.control] if a.control else [])}
    main_s, main_p = load_series(snaps[a.symbol].view(), a.symbol, a.tf, bt.lookback, cdir)
    ctl = (load_series(snaps[a.control].view(), a.control, a.tf, bt.lookback, cdir)
           if a.control else None)
    for s, p in [(main_s, main_p)] + ([ctl] if ctl else []):
        print(f"precalculando insumos de {s.symbol}", flush=True)
        s.cache.warm(bt.lookback, len(s.candles), 6)
        s.cache.save(p)
    op = ObjectiveParams()
    res = run_nested(main_s, ctl[0] if ctl else None, bt, train=a.train, test=a.test,
                     inner=a.inner, n_trials=a.trials, top_k=a.top_k, seed=a.seed, op=op,
                     log=lambda m: print(m, flush=True))
    last = res["folds"][-1]
    n = len(main_s.candles)
    fid = fidelity(main_s, last["values"], (n - n % 6 - a.fidelity_bars, n - n % 6), bt) \
        if a.fidelity_bars else None
    rep = {"meta": {"symbol": a.symbol, "timeframe": a.tf, "control": a.control,
                    "source": main_s.source, "n_candles": n, "first_t": main_s.candles[0].t,
                    "last_t": main_s.candles[-1].t,
                    "data_hash": data_hash(main_s.candles, main_s.funding), "mode": "SIMULADO",
                    "train": a.train, "test": a.test, "inner": a.inner, "trials": a.trials,
                    "seed": a.seed, "backtest": bt.model_dump(), "elapsed_s": time.time() - t0,
                    "objective": (f"mediana de Sharpe por subventana − {op.dd_penalty}·peor DD − "
                                  f"{op.param_penalty}·nº de parámetros movidos >10 %; "
                                  f"< {op.min_trades} operaciones → {op.few_trades_score}")},
           "result": res, "fidelity": fid,
           "notes": ["Optimización SOLO con ventanas de entrenamiento; cada prueba es posterior "
                     "y nunca vista por la búsqueda.",
                     "Los insumos structure/levels se memoizan con ventana móvil (ver fidelidad).",
                     "Costos de perpetuo de T25 (comisiones, deslizamiento, funding real).",
                     "Resultado de simulación: no garantiza edge futuro (decide T27)."]}
    name = a.version or f"calib_{a.symbol}_{a.tf}"
    oos = res["aggregate"]["oos"]
    rec = ResultStore(root).register(
        "calibration", f"calibración {name}", [x.info.id for x in snaps.values()],
        {"symbol": a.symbol, "control": a.control, "timeframe": a.tf, "train": a.train,
         "test": a.test, "inner": a.inner, "trials": a.trials, "top_k": a.top_k, "seed": a.seed,
         "backtest": bt.model_dump()}, fingerprint(),
        {"accepted": res["decision"]["accepted"], "fold_wins": res["decision"]["fold_wins"],
         "oos_calibrated_median_sharpe": oos["calibrated"]["median_window_sharpe"],
         "oos_default_median_sharpe": oos["default"]["median_window_sharpe"]},
        str(Path(a.out) / f"{name}.json"))
    rep["meta"]["reproducibility"] = stamp([x.info for x in snaps.values()], rec.id)
    print(*write_report(rep, name, a.out), write_version(rep, name), rec.id)


if __name__ == "__main__":
    main()
