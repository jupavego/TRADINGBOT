"""Laboratorio T28: walk-forward fuera de muestra de los ESN frente a las líneas base.

Pliegues: 1 año de entrenamiento (8.760 velas de 1h) → 6 meses de prueba, rodando cada 6 meses.
En prueba, orígenes cada `h` velas (horizontes sin solapamiento). Por pliegue y modelo se eligen
hiperparámetros (ρ, fuga, alpha) en validación interna sobre el final del entrenamiento: jamás se
mira la prueba. Uso (desde `v2/`):
`python -m lab.esn_connectome.run_lab --n 500 --seeds 5 --out reports/esn_connectome/n500.json`
"""

from __future__ import annotations

import argparse
import itertools
import json
import time
from pathlib import Path

import numpy as np

from lab.esn_connectome import connectome, features
from lab.esn_connectome.esn import VARIANTS, ESNParams, build_reservoir, run_states
from lab.esn_connectome.models import cone_quantiles, fit_select, metrics

TRAIN, TEST = 8760, 4380
RHOS, LEAKS = (0.5, 0.9, 1.2), (0.1, 0.5)
COST = 2 * (0.0005 + 0.0001)  # ida y vuelta: comisión taker 5 pb + deslizamiento 1 pb (T25)
LAGS = 24


def folds(t: int, horizon: int) -> list[tuple[np.ndarray, np.ndarray]]:
    out = []
    for start in range(TRAIN, t - horizon, TEST):
        tr = np.arange(max(start - TRAIN, 300), start - horizon)
        te = np.arange(start, min(start + TEST, t - horizon), horizon)
        if len(te) >= 20:
            out.append((tr, te))
    return out


def _base_engine_q(candles: list, te: np.ndarray, horizon: int, symbol: str) -> np.ndarray:
    """Cuantiles del retorno log terminal del motor base de T16 (GARCH + bootstrap de formas)."""
    from eim.core import MarketSnapshot
    from eim.forecast.base_engine import BaseEngine
    from lab.esn_connectome.models import QUANTILES

    eng = BaseEngine()
    out = np.empty((len(te), len(QUANTILES)))
    for k, i in enumerate(te):
        snap = MarketSnapshot(
            symbol=symbol, timeframe="1h", candles=candles[max(0, i - 1499) : i + 1],
            asof=candles[i].t, sources={}, coverage={},
        )
        paths = eng.sample(snap, horizon, 200)
        out[k] = np.quantile(np.log(paths[:, -1, 3] / candles[i].c), QUANTILES)
    return out


def _summ(m: dict[str, np.ndarray]) -> dict[str, float]:
    traded = m["pos"] != 0
    return {
        "pinball": float(m["pinball"].mean()),
        "cov50": float(m["in50"].mean()),
        "cov80": float(m["in80"].mean()),
        "hit": float(np.nanmean(m["hit"])) if traded.any() else float("nan"),
        "trades": int(traded.sum()),
        "net_bp": float(m["net"][traded].mean() * 1e4) if traded.any() else 0.0,
    }


def run_asset(symbol: str, n: int, seeds: int, horizon: int, data_dir: str) -> dict:
    from eim.data.store import Store

    candles = Store(data_dir).read_candles(symbol, "1h")
    ohlcv = np.array([[c.o, c.h, c.l, c.c, c.v] for c in candles], dtype=float)
    f = features.build(ohlcv, horizon)
    y, big_r, scale = f["y"], f["R"], f["sigma"] * np.sqrt(horizon)
    fl = folds(len(ohlcv), horizon)
    per_origin: dict[str, dict[str, list]] = {}  # modelo → métrica → valores por origen
    cells: dict[str, list[dict]] = {}

    def record(name: str, k: int, te: np.ndarray, q_log: np.ndarray, extra: dict | None = None):
        m = metrics(big_r[te], q_log, COST)
        cells.setdefault(name, []).append({"fold": k, **_summ(m), **(extra or {})})
        po = per_origin.setdefault(name, {"pinball": [], "net": [], "pos": [], "hit": []})
        for key in po:
            po[key].extend(np.nan_to_num(m[key], nan=-1.0).tolist())

    for k, (tr, te) in enumerate(fl):
        record("cone", k, te, cone_quantiles(y[tr], len(te)) * scale[te, None])
        record("base_T16", k, te, _base_engine_q(candles, te, horizon, symbol))
    xl = features.lagged(f["u"], LAGS)
    for k, (tr, te) in enumerate(fl):
        model, _ = fit_select(xl, y, tr, horizon)
        record("linear", k, te, model.predict(xl[te]) * scale[te, None])

    signed = connectome.load(n)
    for variant, seed in itertools.product(VARIANTS, range(seeds)):
        t0 = time.time()
        best: list[tuple[float, np.ndarray, dict] | None] = [None] * len(fl)
        for rho, leak in itertools.product(RHOS, LEAKS):
            # Misma W_in por semilla en las tres variantes: la comparación queda pareada.
            w = build_reservoir(variant, signed, np.random.default_rng(1000 * seed + 7))
            rng_in = np.random.default_rng(1000 * seed + 11)
            states = run_states(w, f["u"], ESNParams(rho=rho, leak=leak), rng_in)
            for k, (tr, te) in enumerate(fl):
                model, val = fit_select(states, y, tr, horizon)
                cur = best[k]
                if cur is None or val < cur[0]:
                    q = model.predict(states[te]) * scale[te, None]
                    best[k] = (val, q, {"rho": rho, "leak": leak, "alpha": model.alpha})
        for k, (_tr, te) in enumerate(fl):
            _, q, hp = best[k]  # type: ignore[misc]
            record(f"esn_{variant}_s{seed}", k, te, q, hp)
        print(f"{symbol} {variant} s{seed} N={n}: {time.time() - t0:.0f}s", flush=True)
    return {
        "symbol": symbol,
        "folds": [{"train": [int(tr[0]), int(tr[-1])], "test": [int(te[0]), int(te[-1])],
                   "origins": len(te)} for tr, te in fl],
        "cells": cells,
        "per_origin": per_origin,  # hit = −1 cuando no opera
    }


def main() -> None:  # pragma: no cover - uso manual con datos reales
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--horizon", type=int, default=25)
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    res = {
        "n": args.n, "seeds": args.seeds, "horizon": args.horizon, "cost": COST,
        "subgraph": connectome.describe(connectome.load(args.n)),
        "assets": [run_asset(s, args.n, args.seeds, args.horizon, args.data_dir)
                   for s in args.symbols.split(",")],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(res), encoding="utf-8")
    print(f"-> {args.out}")


if __name__ == "__main__":  # pragma: no cover
    main()
