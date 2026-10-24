"""Ida y vuelta de la captura HFT (T78): el libro rehecho desde los eventos = el del recolector.

    python -m eim.data.collectors.hft_verify --root data [--symbol BTCUSDT]
        [--hour 2026-10-24T03 ... | --all] [--out CARPETA]

Por hora: convierte a eventos (`hft_events`), los reproduce SOLO desde el archivo y compara la
huella del libro con la que el recolector anotó en cada verificación REST (`checks.book_hash`) y
el libro final con el punto de control con que el recolector abrió la hora siguiente (misma
corrida). Con `--out` guarda además el `.npz` de cada hora (insumo del simulador, T79).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from eim.data.collectors.hft_book import book_hash
from eim.data.collectors.hft_events import convert_hour, replay, save_npz
from eim.data.collectors.hft_read import hour_label, hours_with_data, parse_hour, read_hour
from eim.data.collectors.hft_schema import HOUR_NS


def _hash_row(row) -> str:
    bp, bq, ap, aq = (np.asarray(row[c], float).tolist() for c in ("bp", "bq", "ap", "aq"))
    return book_hash(dict(zip(bp, bq, strict=True)), dict(zip(ap, aq, strict=True)))


def verify_hour(root: str | Path, symbol: str, hour: int, out_dir: str | Path | None = None
                ) -> dict:
    ev, meta = convert_hour(root, symbol, hour)
    checks = read_hour(root, symbol, "checks", hour, "run, seq, book_hash")
    want = dict(zip(checks["seq"].tolist(), checks["book_hash"].tolist(), strict=True))
    got: dict[int, str] = {}
    bids, asks = replay(ev, lambda seq, h: got.__setitem__(seq, h))
    res = {"hour": hour_label(hour), "events": len(ev), "checks": len(want),
           "checks_equal": sum(got.get(s) == h for s, h in want.items()), "final_compared": False}
    book = read_hour(root, symbol, "book", hour, "run, seq")
    nxt = read_hour(root, symbol, "book", hour + 1)
    if not book.empty and not nxt.empty:
        first = nxt.iloc[0]
        if first["purpose"] == "hora" and int(first["run"]) == int(book["run"].iloc[-1]):
            res["final_compared"] = True
            res["final_equal"] = book_hash(bids, asks) == _hash_row(first)
    if out_dir is not None:
        res["npz"] = str(save_npz(Path(out_dir) / f"{symbol}_{hour_label(hour)}.npz", ev, meta))
    res["ok"] = res["checks_equal"] == res["checks"] and res.get("final_equal", True)
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default="data")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--hour", action="append", default=[])
    ap.add_argument("--all", action="store_true", help="todas las horas cerradas con datos")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    now_h = time.time_ns() // HOUR_NS
    hours = [parse_hour(h) for h in a.hour] or (
        [h for h in hours_with_data(a.root, a.symbol) if h < now_h] if a.all else [])
    if not hours:
        ap.error("indica --hour AAAA-MM-DDTHH o --all")
    results = [verify_hour(a.root, a.symbol, h, a.out) for h in hours]
    for r in results:
        print(json.dumps(r, ensure_ascii=False))
    ok = all(r["ok"] for r in results)
    print(f"{sum(r['ok'] for r in results)}/{len(results)} horas reproducen el libro del "
          f"recolector ({sum(r['checks_equal'] for r in results)}/"
          f"{sum(r['checks'] for r in results)} huellas en verificaciones; "
          f"{sum(bool(r.get('final_equal')) for r in results)} cierres de hora comparados iguales)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
