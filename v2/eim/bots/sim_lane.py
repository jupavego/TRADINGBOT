"""Carril de simulación desde la línea de comandos (T58): `python -m eim.bots.sim_lane`.

Lee velas de 1 min del almacén local (`data/candles`), corre cada estrategia de Passivbot en su
entorno aparte y guarda la `SimRun` en `bot_sim_runs` (`reports.duckdb`). No necesita la API.

    python -m eim.bots.sim_lane run --symbol BTCUSDT --since 2026-03-01 [--until 2026-10-19]
    python -m eim.bots.sim_lane list

Variables: `EIM_BOT_PASSIVBOT_PY` (intérprete del entorno de Passivbot) y `EIM_BOT_PASSIVBOT_DIR`
(checkout en el SHA de la ficha). Sin ellas no corre (ver `docs/BOTS.md`).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from eim.api.reports_db import ReportStore
from eim.bots.pb_adapter import MINUTE, PassivbotSimAdapter, run_hash
from eim.data.bots.simstore import SimRunStore
from eim.data.store import Store

PY_ENV, DIR_ENV = "EIM_BOT_PASSIVBOT_PY", "EIM_BOT_PASSIVBOT_DIR"


def _ms(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp() * 1000)


def build_adapter() -> PassivbotSimAdapter | None:
    py, checkout = os.environ.get(PY_ENV), os.environ.get(DIR_ENV)
    if not py or not checkout or not Path(checkout).exists():
        return None
    return PassivbotSimAdapter(Path(py), Path(checkout))


def run(args: argparse.Namespace) -> int:
    ad = build_adapter()
    if ad is None:
        print(f"falta {PY_ENV}/{DIR_ENV}: ver docs/BOTS.md", file=sys.stderr)
        return 2
    data = Path(args.data_dir)
    start = _ms(args.since)
    end = _ms(args.until) if args.until else int(time.time() * 1000) // MINUTE * MINUTE
    candles = Store(data).read_candles(args.symbol, "1m", start=start, end=end)
    print(f"{len(candles)} velas de 1 min de {args.symbol} [{args.since}, {args.until or 'ahora'})")
    reports = ReportStore(data / "reports.duckdb")
    store = SimRunStore(*reports.connection)
    for strategy in args.strategy or ad.strategies:
        t0 = time.monotonic()
        sim = ad.simulate(args.symbol, candles, strategy, balance=args.balance)
        saved = store.append(sim, int(time.time() * 1000)) if sim.status == "ok" else False
        print(f"{strategy}: {sim.status}, {len(sim.fills)} fills simulados, huella "
              f"{run_hash(sim)}, {time.monotonic() - t0:.0f}s, guardada={saved}; "
              f"{'; '.join(sim.evidence)}")
    return 0


def listing(args: argparse.Namespace) -> int:
    reports = ReportStore(Path(args.data_dir) / "reports.duckdb")
    for r in SimRunStore(*reports.connection).query(limit=50):
        print(r.bot_id, r.strategy, r.symbol, r.start, r.end, r.status, len(r.fills), "simulado")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="eim.bots.sim_lane", description=__doc__)
    p.add_argument("--data-dir", default=os.environ.get("EIM_DATA_DIR", "data"))
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--symbol", default="BTCUSDT")
    r.add_argument("--since", required=True)
    r.add_argument("--until")
    r.add_argument("--balance", type=float, default=10_000.0)
    r.add_argument("--strategy", action="append")
    r.set_defaults(fn=run)
    sub.add_parser("list").set_defaults(fn=listing)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
