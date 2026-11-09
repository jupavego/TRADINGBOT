"""Orden de consola de la reproducibilidad (T124). Desde `v2/`:

    python -m eim.repro instantanea --symbol BTCUSDT --tf 1h [--desde 2023-01-01] [--ligera]
    python -m eim.repro instantaneas [--symbol BTCUSDT]
    python -m eim.repro revisiones [--dias 30]     # qué cambió en el almacén y a quién afecta
    python -m eim.repro resultados [--tipo edge_window]
    python -m eim.repro repetir <id de resultado> [--store data] [--json]
    python -m eim.repro adoptar-t27 --store backups/t131_banco [--asset BTCUSDT] [--ventana 1]

`--root` (por defecto `data`) es donde viven `snapshots/snapshots.duckdb` y las copias. `repetir`
sale con 0 si se repite (o, sin recálculo, si los datos siguen intactos), 1 si no y 2 si falla.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from eim.data import revisions
from eim.data.results import ResultStore
from eim.data.snapshots import SnapshotStore
from eim.data.store import Store
from eim.repro.text import ts


def _ms(day: str | None) -> int | None:
    if not day:
        return None
    return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp() * 1000)


def _snap_line(i) -> str:
    cov = i.coverage()
    return (f"{i.id}  {'congelada' if i.frozen else 'ligera   '}  {i.symbol} {i.timeframe}  "
            f"{ts(i.start_ms)} → {ts(i.end_ms)}  {i.n_candles} velas/{cov['expected']}  "
            f"{i.gaps} huecos  {i.n_funding} funding  {i.source}  {i.origin}")


def cmd_instantanea(a) -> int:
    s = SnapshotStore(a.root).create(Store(a.store or a.root), a.symbol, a.tf, _ms(a.desde),
                                     _ms(a.hasta), freeze=not a.ligera, origin="consola")
    print(_snap_line(s.info))
    return 0


def cmd_instantaneas(a) -> int:
    for i in SnapshotStore(a.root).list(a.symbol, a.limit):
        print(_snap_line(i))
    return 0


def cmd_revisiones(a) -> int:
    since = int(time.time() * 1000) - a.dias * 86_400_000
    revs = revisions.read(a.root, since, a.symbol)
    if not revs:
        print(f"Sin revisiones anotadas en los últimos {a.dias} días.")
        return 0
    for r in revs:
        moved = {k: (r["before"][k], r["after"][k]) for k in r["after"]
                 if r["before"][k] != r["after"][k]}
        print(f"{ts(r['detected_ms'])}  {r['kind']} {r['symbol']} {r['timeframe']}  "
              f"fila {ts(r['t'])}  {moved}  ({r['source_before']} → {r['source_after']})")
    hit = revisions.affected(revs, SnapshotStore(a.root).list(limit=100_000))
    print(f"\nInstantáneas afectadas: {len(hit)}")
    for sid, rs in hit.items():
        print(f"  {sid}: {len(rs)} filas revisadas después de crearla")
    for rec in ResultStore(a.root).using(set(hit)):
        print(f"  resultado {rec.id} ({rec.name}) usa datos revisados: "
              f"python -m eim.repro repetir {rec.id}")
    return 0


def cmd_resultados(a) -> int:
    rs = ResultStore(a.root)
    for r in rs.list(a.tipo, a.limit):
        last = rs.checks(r.id, 1)
        chk = (f"último repetir {ts(last[0]['checked_ms'])}: {last[0]['verdict']}"
               + (f" ({', '.join(last[0]['causes'])})" if last[0]["causes"] else "")
               if last else "sin repetir")
        print(f"{r.id}  {r.kind:13s}  {r.name}  · {len(r.snapshots)} instantáneas · {chk}")
    return 0


def cmd_repetir(a) -> int:
    from eim.repro.replay import repetir

    try:
        chk = repetir(a.root, a.id, Store(a.store) if a.store else None)
    except (KeyError, ValueError) as exc:
        print(f"no se puede repetir: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"verdict": chk.verdict, "causes": chk.causes, **chk.detail}, default=str,
                     indent=1) if a.json else "\n".join(chk.lines))
    return chk.exit_code


def cmd_adoptar(a) -> int:
    from eim.repro.adopt import DEFAULT_EDGE, adopt_t27

    got = adopt_t27(a.root, Store(a.store or a.root), Path(a.edge or DEFAULT_EDGE), a.asset,
                    a.ventana)
    print(f"{len(got)} ventanas adoptadas; compruébalas con `python -m eim.repro repetir <id>`.")
    return 0 if got else 1


def main(argv: list[str] | None = None) -> int:
    for f in (sys.stdout, sys.stderr):
        if hasattr(f, "reconfigure"):
            f.reconfigure(encoding="utf-8")       # consola de Windows (cp1252)
    ap = argparse.ArgumentParser(prog="python -m eim.repro", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default="data", help="carpeta con snapshots/ (por defecto data)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("instantanea", help="fija una serie del almacén")
    p.add_argument("--symbol", required=True)
    p.add_argument("--tf", required=True)
    p.add_argument("--desde")
    p.add_argument("--hasta")
    p.add_argument("--ligera", action="store_true", help="sin copia (solo identidad y hash)")
    p.add_argument("--store", help="almacén del que leer (por defecto --root)")
    p.set_defaults(fn=cmd_instantanea)
    p = sub.add_parser("instantaneas", help="lista las instantáneas")
    p.add_argument("--symbol")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(fn=cmd_instantaneas)
    p = sub.add_parser("revisiones", help="velas guardadas que cambiaron y a quién afectan")
    p.add_argument("--dias", type=int, default=30)
    p.add_argument("--symbol")
    p.set_defaults(fn=cmd_revisiones)
    p = sub.add_parser("resultados", help="resultados registrados y su último repetir")
    p.add_argument("--tipo")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(fn=cmd_resultados)
    p = sub.add_parser("repetir", help="recalcula un resultado contra su instantánea")
    p.add_argument("id")
    p.add_argument("--store", help="almacén con que comparar (por defecto, el de la instantánea)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_repetir)
    p = sub.add_parser("adoptar-t27", help="instantánea a posteriori de ventanas de T27")
    p.add_argument("--edge")
    p.add_argument("--store", help="almacén con la historia (p. ej. backups/t131_banco)")
    p.add_argument("--asset", nargs="+")
    p.add_argument("--ventana", type=int, nargs="+", help="índices desde 1")
    p.set_defaults(fn=cmd_adoptar)
    a = ap.parse_args(argv)
    return a.fn(a)
