"""Importa historia de velas al TRAMO HISTÓRICO del almacén (BACKLOG T111 (1)).

    python -m eim.data.import_history --from <carpeta de datos con la historia> \\
        [--data data] [--symbol BTCUSDT] [--tf 1m]

Copia con SQL (sin un objeto por vela) las velas que el almacén de origen tiene ANTES de la
primera vela viva del destino. Solo escribe `history.parquet`; el `data.parquet` que reescribe el
servicio en curso no se toca, así que puede correr con la API encendida. Volver a correrlo no
duplica nada (las velas se identifican por `t`).
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from eim.data.store import Store


def _iso(t: int | None) -> str:
    return "—" if t is None else datetime.fromtimestamp(t / 1000, UTC).strftime("%Y-%m-%d %H:%M")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eim.data.import_history")
    ap.add_argument("--from", dest="src", required=True)
    ap.add_argument("--data", default="data")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--tf", default="1m")
    ap.add_argument("--source", default="binance-futures")
    a = ap.parse_args(argv)
    src, dst = Store(a.src), Store(a.data)
    if src.bounds(a.symbol, a.tf) is None:
        print(f"el origen no tiene velas de {a.symbol} {a.tf}")
        return 1
    n = dst.add_history(a.symbol, a.tf, src, a.source)
    b = dst.bounds(a.symbol, a.tf)
    print(f"{a.symbol} {a.tf}: tramo histórico con {n} velas; serie {_iso(b[0] if b else None)} → "
          f"{_iso(b[1] if b else None)} UTC, {dst.count(a.symbol, a.tf)} velas, "
          f"{len(dst.find_gaps(a.symbol, a.tf))} huecos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
