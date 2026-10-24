"""Cota analítica de costos HFT (T77): |Δmid| a 1–60 s frente a la ida y vuelta de comisiones.

Uso (desde `v2/`): python scripts/hft_cost_bound.py [--root data] [--symbol BTCUSDT]
Lee lo que guarda el recolector de T23 (`<root>/micro/{trades,top}/symbol=…`): la serie
principal es una rejilla de 1 s con el último precio negociado (con spread de ≈ 1 tick aproxima
el mid y permite el horizonte de 1 s); el mid del top del libro (≈ 1/s) sirve de contraste y da
el spread. Escribe `reports/hft_cost_bound.md` y `.json`. Orientativo: la cota definitiva es T80.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb  # noqa: E402
import numpy as np  # noqa: E402

from eim.hft.cost_bound import asof_grid, bound_table, spread_summary  # noqa: E402

OUT = ROOT / "reports" / "hft_cost_bound"


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).isoformat(timespec="minutes")


def _f(v: float, nd: int = 2) -> str:
    return f"{v:,.{nd}f}".replace(",", " ").replace(".", ",")


def _read(root: Path, kind: str, symbol: str, cols: str, where: str) -> dict:
    base = root / "micro" / kind / f"symbol={symbol}"
    g = (base / "date=*" / "hour=*" / "part-*.parquet").as_posix().replace("'", "''")
    return duckdb.connect().execute(
        f"SELECT {cols} FROM read_parquet('{g}', hive_partitioning=false) "
        f"WHERE {where} ORDER BY t").fetchnumpy()


def render(res: dict) -> str:
    c = res["costs_bps"]
    lines = ["# Cota analítica de costos HFT (T77)", "",
             f"{res['symbol']} perpetuo, datos del recolector T23: rejilla de 1 s con el último "
             f"precio negociado ({_f(res['trades'], 0)} operaciones `aggTrade`, "
             f"{_f(res['points'], 0)} puntos, {_f(res['hours'], 1)} h: "
             f"{res['from']} → {res['to']} UTC). "
             "Generado por `python scripts/hft_cost_bound.py`. **Orientativo**: un solo tramo "
             "de mercado, ventanas solapadas (los percentiles valen; los errores estándar no). "
             "La cota definitiva con features y validación es T80.", "",
             f"Ida y vuelta con `CostParams` (taker 5 pb, maker 2 pb): **taker {_f(c['taker'], 0)}"
             f" pb · mixto {_f(c['mixto'], 0)} pb · maker-maker {_f(c['maker'], 0)} pb**. "
             f"Spread p50/p95/p99: {' / '.join(_f(v, 4) for v in res['spread_bps'].values())} pb"
             " (≈ 1 tick: cruzarlo no cambia la cuenta).", "",
             "| Horizonte | Ventanas | E\\|Δmid\\| (pb) | p50 | p90 | p95 | p99 | "
             "P(>10 pb) | P(>7 pb) | P(>4 pb) | Techo taker | Techo mixto | Techo maker |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for h, r in res["horizons"].items():
        if not r.get("n"):
            lines.append(f"| {h} s | 0 | — |" + " — |" * 10)
            continue
        lines.append(
            f"| {h} s | {_f(r['n'], 0)} | {_f(r['mean'])} | {_f(r['p50'])} | {_f(r['p90'])} | "
            f"{_f(r['p95'])} | {_f(r['p99'])} | {_f(100 * r['frac_gt_taker'], 2)} % | "
            f"{_f(100 * r['frac_gt_mixto'], 2)} % | {_f(100 * r['frac_gt_maker'], 2)} % | "
            f"{_f(r['ceiling_taker'], 3)} | {_f(r['ceiling_mixto'], 3)} | "
            f"{_f(r['ceiling_maker'], 3)} |")
    lines += ["", "**Techo** = E[max(|Δmid| − costo, 0)] por ventana, en pb: lo que ganaría un "
              "oráculo que sabe la dirección y solo opera cuando el movimiento paga la comisión, "
              "sin selección adversa, sin cola y con llenado seguro. Ninguna estrategia real lo "
              "supera; si es ≈ 0 en un horizonte, ese horizonte queda descartado para ese esquema "
              "de comisiones.", "",
              "Contraste con el mid del top del libro (instantáneas ≈ 1/s, sin horizonte de 1 s "
              "porque dos instantáneas distan ≥ 1 s): p50 / p99 de |Δmid| en pb.", "",
              "| Horizonte | Rejilla de operaciones | Top del libro |", "|---|---|---|"]
    for h, r in res["horizons"].items():
        c2 = res["top_check"]["horizons"].get(h, {})
        top = f"{_f(c2['p50'])} / {_f(c2['p99'])}" if c2.get("n") else "—"
        grid = f"{_f(r['p50'])} / {_f(r['p99'])}" if r.get("n") else "—"
        lines.append(f"| {h} s | {grid} | {top} |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=ROOT / "data")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()
    trades = _read(a.root, "trades", a.symbol, "t, p", "p > 0")
    top = _read(a.root, "top", a.symbol, "t, bid_p, ask_p", "bid_p > 0 AND ask_p > bid_p")
    gt, gp = asof_grid(trades["t"], trades["p"], step_ms=1_000)
    tt = np.asarray(top["t"], dtype=np.int64)
    res = {"symbol": a.symbol, "from": _iso(int(gt[0])), "to": _iso(int(gt[-1])),
           "trades": int(len(trades["t"])), **bound_table(gt, gp),
           "spread_bps": spread_summary(top["bid_p"], top["ask_p"]),
           "top_check": bound_table(tt, (top["bid_p"] + top["ask_p"]) / 2)}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    a.out.with_suffix(".md").write_text(render(res), encoding="utf-8")
    print(a.out.with_suffix(".md"))


if __name__ == "__main__":
    main()
