"""CLI del bróker simulado (desde `v2/`).

    python -m eim.paper backtest --symbol BTCUSDT --days 30 [--step 1]
    python -m eim.paper resumen --symbol BTCUSDT

DuckDB admite un solo proceso escritor: si la API está en marcha (tiene `data/paper.duckdb`
abierta), `backtest` le pide el trabajo a ella (`POST /v2/paper/backtest`).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from eim.data.local_api import DEFAULT_API, post_local
from eim.data.timeframes import SYMBOLS


def _backtest_local(a: argparse.Namespace) -> int:
    from eim.data.paper_store import PaperStore
    from eim.data.store import Store
    from eim.paper.generate import CtxGenerator, closed_asofs, default_workers

    store = Store(a.data)
    ps = PaperStore(Path(a.data) / "paper.duckdb")
    for tf in a.tf.split(","):
        gen = CtxGenerator(store, timeframe=tf)
        b = store.bounds(a.symbol, tf)
        if b is None:
            print(f"sin velas de {a.symbol} {tf} en {a.data}", file=sys.stderr)
            continue
        n = int(a.days * 24 * 3_600_000 / gen.bar / a.step)
        asofs = closed_asofs(b[1], gen.bar, n, a.step)

        def progress(k: int, total: int, tf: str = tf) -> None:
            if k == total or k % 50 == 0:
                print(f"  {tf}: {k}/{total} velas", flush=True)

        saved = gen.run(ps, a.symbol, asofs, lambda _t: "backtest", progress=progress,
                        workers=a.workers or default_workers())
        print(f"contextos guardados: {saved} ({a.symbol} {tf}, {a.days} días, cada {a.step})")
    ps.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eim.paper")
    sub = ap.add_subparsers(dest="cmd", required=True)
    bt = sub.add_parser("backtest", help="reconstruye contextos de los últimos N días")
    bt.add_argument("--symbol", default="BTCUSDT", choices=SYMBOLS)
    bt.add_argument("--days", type=float, default=30)
    bt.add_argument("--step", type=int, default=1, help="cada cuántas velas del marco")
    bt.add_argument("--tf", default="15m,1h,4h", help="marcos separados por coma")
    bt.add_argument("--data", default="data")
    bt.add_argument("--api", default=DEFAULT_API)
    bt.add_argument("--local", action="store_true", help="no delegar en la API")
    bt.add_argument("--workers", type=int, default=0, help="procesos (0 = núcleos − 2)")
    rs = sub.add_parser("resumen", help="resumen de perfiles y estrategias (vía la API)")
    rs.add_argument("--symbol", default="BTCUSDT", choices=SYMBOLS)
    rs.add_argument("--api", default=DEFAULT_API)
    a = ap.parse_args(argv)
    if a.cmd == "backtest":
        if not a.local:
            try:
                r = post_local(a.api, f"/v2/paper/backtest?symbol={a.symbol}&days={a.days}"
                                      f"&step={a.step}&tf={a.tf}", "paper-backtest")
                print(json.dumps(r, ensure_ascii=False, indent=1))
                return 0
            except (urllib.error.URLError, OSError):
                print("API no disponible: se calcula en este proceso", flush=True)
        return _backtest_local(a)
    with urllib.request.urlopen(f"{a.api}/v2/paper?symbol={a.symbol}", timeout=120) as r:  # noqa: S310
        v = json.loads(r.read())
    for p in v.get("profiles", []):
        print(f"{p['name']:<12} capital {p['equity']:>12,.2f}  rent. {p['return_pct']:+.2%}  "
              f"ops {p['n_closed']}  acierto {p['win_rate'] or 0:.0%}")
    for line in v.get("insights", []):
        print("·", line["text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
