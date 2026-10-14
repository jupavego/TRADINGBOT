"""CLI de la operación continua (desde `v2/`).

- `python -m eim.operation run [--execution paper|testnet] [--port 8000]`: lanza la API con el
  servicio de operación bajo el vigilante (reinicio automático). Nunca dinero real.
- `python -m eim.operation report [--from AAAA-MM-DD] [--to AAAA-MM-DD]`: pide a la API en
  marcha el informe del periodo (por defecto, la semana en curso). La base DuckDB la tiene
  abierta el servicio, por eso el informe se genera dentro de ese proceso.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from eim.operation.notify import JsonLog
from eim.operation.watchdog import Watchdog


def _ms(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp() * 1000)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="eim.operation")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="API + servicio de operación bajo el vigilante")
    r.add_argument("--execution", choices=["paper", "testnet"], default="paper")
    r.add_argument("--port", type=int, default=8000)
    r.add_argument("--tf", default="1h")
    r.add_argument("--poll", type=float, default=60.0)
    r.add_argument("--data-dir", default=os.environ.get("EIM_DATA_DIR", "data"))
    p = sub.add_parser("report", help="informe del periodo (vía la API en marcha)")
    p.add_argument("--from", dest="start")
    p.add_argument("--to", dest="end")
    p.add_argument("--api", default="http://127.0.0.1:8000")
    a = ap.parse_args(argv)

    if a.cmd == "run":
        env = {**os.environ, "EIM_OPERATE": "1", "EIM_EXECUTION": a.execution,
               "EIM_OPERATE_TF": a.tf, "EIM_OPERATE_POLL_S": str(a.poll),
               "EIM_DATA_DIR": a.data_dir}
        cmd = [sys.executable, "-m", "uvicorn", "eim.api.main:app", "--host", "127.0.0.1",
               "--port", str(a.port)]
        root = Path(a.data_dir) / "operation"
        Watchdog(cmd, env, root / "heartbeat.json", JsonLog(root / "logs", echo=True)).run()
        return 0

    q = []
    if a.start:
        q.append(f"start={_ms(a.start)}")
    if a.end:
        q.append(f"end={_ms(a.end)}")
    req = urllib.request.Request(f"{a.api}/v2/operation/report?{'&'.join(q)}", method="POST",
                                 headers={"X-EIM-Confirm": "report"})
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 - URL local del usuario
        print(json.dumps(json.loads(resp.read()), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
