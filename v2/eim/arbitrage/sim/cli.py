"""Simulación del arbitraje (T43), modo ANÁLISIS (no envía órdenes):

    python -m eim.arbitrage.sim sync   # descarga el histórico y captura libros (REST público)
    python -m eim.arbitrage.sim run    # escribe reports/arbitrage_edge.md y .json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from eim.arbitrage.params import ArbParams
from eim.arbitrage.sim.evaluate import Evaluator
from eim.arbitrage.sim.params import SimParams
from eim.arbitrage.sim.report import render
from eim.core import CostModel
from eim.data.arb_history import load_history
from eim.data.arb_history_sync import sync_history
from eim.data.providers.binance_arb import BinanceArbData
from eim.data.store import Store


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("sync", "run"))
    ap.add_argument("--data", default="data")
    ap.add_argument("--assets", nargs="+", default=["BTC", "ETH"])
    ap.add_argument("--tri-days", type=int, default=30)
    ap.add_argument("--snapshots", type=int, default=4)
    ap.add_argument("--out", default="reports/arbitrage_edge.md")
    ap.add_argument("--no-sensitivity", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # consola de Windows (cp1252)
    root, store = Path(a.data), Store(a.data)
    assets = tuple(x.upper() for x in a.assets)
    if a.cmd == "sync":
        out = sync_history(store, BinanceArbData(), root, assets=assets, tri_days=a.tri_days,
                           snapshots=a.snapshots, log=_log)
        _log(f"errores: {json.dumps(out['errors'], ensure_ascii=False)}")
        return
    hist = load_history(store, root, assets=assets)
    _log(f"histórico cargado; faltantes: {json.dumps(hist.missing, ensure_ascii=False)}")
    cm, p, sp = CostModel(), ArbParams(assets=assets), SimParams()
    res = Evaluator(hist, cm, p, sp, log=_log).run(sensitivities=not a.no_sensitivity)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(res, hist, cm, p, sp, int(time.time() * 1000)), encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1,
                                                   default=str), encoding="utf-8")
    _log(f"informe en {out} (+ .json)")
    for s, (label, why) in res["verdicts"].items():
        _log(f"{s}: {label} — {'; '.join(why)}")
