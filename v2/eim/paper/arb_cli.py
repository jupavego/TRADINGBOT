"""Pruebas del arbitraje en el bróker simulado (T45), desde `v2/`:

    python -m eim.paper.arb_cli [--hold 48] [--notional 1000]

Lee velas de 1 h y funding del almacén local (`EIM_DATA_DIR`, por defecto `data`), corre los
tres escenarios de `arb_tests` en modo SIMULADO y guarda el informe en `data/paper/arb_tests.json`
(lo muestra el Bróker simulado → «Arbitraje»). Sin cuenta de Binance.
"""

from __future__ import annotations

import argparse
import os
import sys

from eim.data.arb_sim_data import load_sim_series, save_report
from eim.data.store import Store
from eim.paper.arb_tests import run_all


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")      # consola sin UTF-8
    ap = argparse.ArgumentParser(description="Pruebas del arbitraje en el bróker simulado")
    ap.add_argument("--hold", type=int, default=48, help="horas con el carry abierto")
    ap.add_argument("--notional", type=float, default=1000.0)
    a = ap.parse_args()
    root = os.environ.get("EIM_DATA_DIR", "data")
    series = load_sim_series(Store(root), hours=a.hold + 8)
    if series is None:
        raise SystemExit("✖ faltan velas de 1 h de spot y perpetuo en el almacén")
    rep = run_all(series, a.hold, a.notional)
    path = save_report(root, rep)
    for sc in rep["scenarios"]:
        print(f"{'✔' if sc['ok'] else '✖'} {sc['title']}")
        for c in sc["checks"]:
            print(f"   {'✔' if c['ok'] else '✖'} {c['label']} — {c['detail']}")
    print(f"informe: {path}")
    raise SystemExit(0 if rep["ok"] else 1)


if __name__ == "__main__":
    main()
