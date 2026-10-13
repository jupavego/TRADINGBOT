"""Validación de techo/piso por escenario: ¿la estructura (Fibonacci/Elliott/pivotes) añade algo?

Solo se evalúan los niveles del escenario que SE CUMPLIÓ (son condicionales a él). Por nivel:
`ext` = extremo realizado en el horizonte (máx. high para techo, mín. low para piso); error = |ext −
nivel|/ATR; toque = el extremo alcanza el nivel; rechazo = tocó y ningún cierre lo superó.
Se comparan tres versiones del mismo nivel: AJUSTADO a estructura, el ESTADÍSTICO original y uno
ALEATORIO dentro de la misma ventana ±TOL_ATR (promedio de `draws`). Si lo ajustado no mejora al
aleatorio, la estructura no aporta. IC por bootstrap de bloques (bloque = horizonte, por solape).
Uso: `python -m eim.forecast.sr_eval --symbol BTCUSDT --timeframe 1h --data-dir data`
"""

from __future__ import annotations

import argparse
from collections import defaultdict

import numpy as np

from eim.agents.levels.pivots import atr
from eim.core import Candle, ForecastSet
from eim.forecast.sr import TOL_ATR


def _group(methods: list[str]) -> str:
    if len(methods) >= 2:
        return "confluencia (≥2 métodos)"
    if not methods:
        return "estadístico (sin estructura)"
    m = methods[0]
    return "Fibonacci" if m.startswith("Fib") else "Elliott" if m.startswith("Elliott") else m


def _metrics(role: str, lvl: float, hi: np.ndarray, lo: np.ndarray, cl: np.ndarray,
             a: float) -> tuple[float, float, float]:
    """(error en ATR, toque, rechazo) de un nivel frente a las velas realizadas."""
    if role == "techo":
        ext, touched, broke = hi.max(), hi.max() >= lvl, cl.max() > lvl
    else:
        ext, touched, broke = lo.min(), lo.min() <= lvl, cl.min() < lvl
    return abs(ext - lvl) / a, float(touched), float(touched and not broke)


def collect(forecasts: list[ForecastSet], candles: list[Candle], draws: int = 30,
            seed: int = 0) -> list[dict]:
    rng = np.random.default_rng(seed)
    idx = {c.t: i for i, c in enumerate(candles)}
    rows: list[dict] = []
    for fs in forecasts:
        if fs.made_at not in idx:
            continue
        i = idx[fs.made_at]
        sc = {s.id: s for s in fs.scenarios}
        times = [t for t, _ in sc["neutral"].path]
        if any(t not in idx for t in times):
            continue
        real = candles[idx[times[0]] : idx[times[-1]] + 1]
        hi = np.array([c.h for c in real])
        lo = np.array([c.l for c in real])
        cl = np.array([c.c for c in real])
        ctx = np.array([[c.h, c.l, c.c] for c in candles[max(0, i - 200) : i]])
        a = atr(ctx[:, 0], ctx[:, 1], ctx[:, 2], 14)
        inv = sc["neutral"].invalidation
        last, half = (inv["level"] + inv["level_low"]) / 2, (inv["level"] - inv["level_low"]) / 2
        d = cl[-1] - last
        realized = "neutral" if abs(d) < half else ("bull" if d > 0 else "bear")
        for lv in sc[realized].levels:
            snap = _metrics(lv["role"], lv["price"], hi, lo, cl, a)
            stat = _metrics(lv["role"], lv["stat_price"], hi, lo, cl, a)
            offs = rng.uniform(-TOL_ATR, TOL_ATR, draws) * a
            rnd = np.mean([_metrics(lv["role"], lv["stat_price"] + o, hi, lo, cl, a)
                           for o in offs], axis=0)
            rows.append({"i": i, "group": _group(lv["methods"]), "role": lv["role"],
                         "snap": snap, "stat": stat, "rand": tuple(rnd)})
    return rows


def _boot(rows: list[dict], h: int, k: int, b: int = 400, seed: int = 1) -> tuple[float, float]:
    """IC95 de la diferencia media (ajustado − aleatorio) del error, bloques de `h` orígenes."""
    rng = np.random.default_rng(seed)
    diff = np.array([r["snap"][k] - r["rand"][k] for r in rows])
    blk = np.array([r["i"] // h for r in rows])
    ids = np.unique(blk)
    means = []
    for _ in range(b):
        pick = rng.choice(ids, len(ids))
        sel = np.concatenate([diff[blk == p] for p in pick])
        means.append(sel.mean())
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def summarize(rows: list[dict], horizon: int) -> dict:
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by[r["group"]].append(r)
    by["TODOS los niveles ajustados"] = [r for r in rows if not r["group"].startswith("estad")]
    out = {}
    for g, rs in by.items():
        if not rs:
            continue
        def m(key: str, k: int, rs: list[dict] = rs) -> float:
            return float(np.mean([r[key][k] for r in rs]))

        lo, hi = _boot(rs, horizon, 0)
        out[g] = {
            "n": len(rs), "n_eff": round(len({r["i"] // horizon for r in rs}), 0),
            "touch": {v: m(v, 1) for v in ("snap", "stat", "rand")},
            "reject": {v: m(v, 2) for v in ("snap", "stat", "rand")},
            "err_atr": {v: m(v, 0) for v in ("snap", "stat", "rand")},
            "err_diff_snap_vs_rand": {"mean": m("snap", 0) - m("rand", 0), "ci95": [lo, hi]},
        }
        d = out[g]["err_diff_snap_vs_rand"]
        out[g]["verdict"] = ("mejor que aleatorio" if d["ci95"][1] < 0 else
                             "peor que aleatorio" if d["ci95"][0] > 0 else
                             "no distinguible del azar")
    return out


def format_report(rep: dict) -> str:
    L = ["grupo                          n  n_ef  toque(aj/est/alea)   rechazo(aj/alea)  "
         "err ATR(aj/est/alea)  Δerr aj−alea [IC95]   veredicto"]
    for g, r in rep.items():
        t, rj, e, d = r["touch"], r["reject"], r["err_atr"], r["err_diff_snap_vs_rand"]
        L.append(f"{g:<30}{r['n']:>4}{r['n_eff']:>5.0f}  "
                 f"{t['snap']:.2f}/{t['stat']:.2f}/{t['rand']:.2f}      "
                 f"{rj['snap']:.2f}/{rj['rand']:.2f}        "
                 f"{e['snap']:.2f}/{e['stat']:.2f}/{e['rand']:.2f}      "
                 f"{d['mean']:+.3f} [{d['ci95'][0]:+.3f},{d['ci95'][1]:+.3f}]  {r['verdict']}")
    return "\n".join(L)


def main() -> None:  # pragma: no cover - uso manual con datos reales
    from eim.data.store import Store
    from eim.forecast.backfill import backfill
    from eim.forecast.base_engine import BaseEngine

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--timeframe", default="1h")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--horizon", type=int, default=25)
    ap.add_argument("--n", type=int, default=200)
    a = ap.parse_args()
    candles = Store(a.data_dir).read_candles(a.symbol, a.timeframe)
    fcs = list(backfill(BaseEngine(), candles, symbol=a.symbol, timeframe=a.timeframe,
                        horizon=a.horizon, n=a.n))
    print(f"{len(fcs)} pronósticos walk-forward")
    print(format_report(summarize(collect(fcs, candles), a.horizon)))


if __name__ == "__main__":  # pragma: no cover
    main()
