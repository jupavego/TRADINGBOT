"""Las órdenes del vigilante del conjunto (T148, T173).

Vive aparte de `fleet_watch.py` solo por tamaño: el motor (inventario, decisión y pasada) se lee
mejor sin el `argparse` en medio. La orden de siempre no cambia:

    python -m eim.operation.fleet_watch check [--data-dir data] [--dry-run]
    python -m eim.operation.fleet_watch status        # qué ve, sin tocar nada
    python -m eim.operation.fleet_watch why           # por qué relanzar no serviría (T173)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eim.operation import fleet_cause, fleet_watch


def _why(data_dir: Path) -> dict:
    """Las tres razones de T173, tal como las ve ahora mismo, sin decidir ni tocar nada."""
    import time

    now = time.time()
    seen = fleet_watch.ages(data_dir, now)
    down = fleet_watch.missing(seen)
    rows = fleet_cause.recent_ops(data_dir, now)
    return {"ages_s": seen, "missing": down,
            "red": fleet_cause.network_cause(rows, int(now * 1000)),
            "dentro_de_otro": fleet_cause.not_liftable(down, seen, fleet_watch.DOWN_S),
            "late_sin_producir": fleet_cause.not_producing(data_dir, now)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="eim.operation.fleet_watch",
                                 description=fleet_watch.__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, helptext in (("check", "una pasada: levanta el conjunto si falta algún latido"),
                           ("status", "qué latidos se ven, sin tocar nada"),
                           ("why", "por qué relanzar no serviría ahora (T173)")):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("--data-dir", default="data")
        s.add_argument("--down-s", type=float, default=fleet_watch.DOWN_S)
        if name == "check":
            s.add_argument("--dry-run", action="store_true", help="decide pero no lanza nada")
    a = ap.parse_args(argv)
    data_dir = Path(a.data_dir)
    if a.cmd == "status":
        seen = fleet_watch.ages(data_dir)
        out = {"ages_s": seen, "missing": fleet_watch.missing(seen, a.down_s),
               "state": vars(fleet_watch.State.load(
                   data_dir / "operation" / "fleet_watch.json"))}
    elif a.cmd == "why":
        out = _why(data_dir)
    else:
        out = fleet_watch.check(data_dir, down_s=a.down_s, dry_run=a.dry_run)
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    # Para `Get-ScheduledTaskInfo`: 0 = nada que arreglar, arreglado, o caído por algo que no es
    # nuestro remedio (sin red); 1 = sigue caído y hay que mirarlo. «esperar» es normal.
    bad = out.get("action") in ("rendirse", "dentro_de_otro") or out.get("rc") not in (0, None)
    return 1 if bad else 0
