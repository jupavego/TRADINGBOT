"""Línea de órdenes del registro de instrumentos (T89).

    python -m eim.instruments --data-dir data seed                  # la semilla
    python -m eim.instruments --data-dir data discover              # los USDⓈ-M de Binance
    python -m eim.instruments --data-dir data discover --source fx  # los pares del BCE
    python -m eim.instruments --data-dir data list --asset-class crypto
    python -m eim.instruments --data-dir data events --id crypto.binance.usdm.BTCUSDT

`discover` hace UNA llamada pública por fuente (peso 1 en Binance) y es idempotente: correrlo
dos veces no cambia nada ni duplica historia.
"""

from __future__ import annotations

import argparse
import json
import sys

from eim.data.instruments_store import open_store
from eim.instruments import discovery, registry


def main(argv: list[str] | None = None) -> int:
    # La consola de Windows es cp1252 y los detalles llevan flechas y acentos: se sustituye lo
    # que no quepa en vez de reventar a mitad de un listado.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description="Catálogo de instrumentos (T89)")
    ap.add_argument("--data-dir", default="data")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed", help="alta de la semilla (foco + los cinco del visor)")
    d = sub.add_parser("discover", help="descubre instrumentos de una fuente (1 llamada pública)")
    d.add_argument("--source", choices=("binance", "fx"), default="binance",
                   help="binance: los USDⓈ-M · fx: los pares mayores del BCE (Frankfurter)")
    d.add_argument("--all", action="store_true", help="fx: las 30 divisas, no solo las mayores")
    d.add_argument("--dry-run", action="store_true", help="no escribe: solo cuenta")
    ls = sub.add_parser("list", help="lista el catálogo")
    ls.add_argument("--asset-class")
    ls.add_argument("--status")
    ls.add_argument("--venue")
    ls.add_argument("--limit", type=int, default=20)
    ev = sub.add_parser("events", help="historia fechada")
    ev.add_argument("--id")
    ev.add_argument("--limit", type=int, default=20)
    args = ap.parse_args(argv)

    store = open_store(args.data_dir)
    if args.cmd == "seed":
        print(store.upsert(registry.SEED).as_json())
    elif args.cmd == "discover":
        if args.source == "binance":
            from eim.data.providers.binance import BinanceFutures
            payload = BinanceFutures().request("/fapi/v1/exchangeInfo")
            found = registry.curate_all(discovery.from_binance_usdm(payload))
            scope = {"venue": "binance"}
        else:
            import httpx
            cur = httpx.get("https://api.frankfurter.dev/v1/currencies", timeout=20).json()
            found = discovery.from_frankfurter(cur, majors_only=not args.all)
            scope = {"venue": "ecb"}
        if args.dry_run:
            print(json.dumps({"source": args.source, "found": len(found), "dry_run": True}))
        else:
            print(json.dumps({"source": args.source, "found": len(found),
                              **store.sync(found, scope=scope).as_json(),
                              "by_status": store.by_status()}))
    elif args.cmd == "list":
        for inst in store.list(asset_class=args.asset_class, status=args.status,
                               venue=args.venue, limit=args.limit):
            print(f"{inst.id:42} {inst.status.value:9} nivel {int(inst.tradable_level)} "
                  f"cal {inst.calendar_id:6} {inst.label}")
        print(f"— {store.count()} fichas · {store.by_status()}")
    else:
        for e in store.events(args.id, limit=args.limit):
            print(f"{e.t} {e.kind.value:16} {e.instrument_id:42} {e.detail}")
    store.close()
    return 0


if __name__ == "__main__":       # pragma: no cover
    sys.exit(main())
