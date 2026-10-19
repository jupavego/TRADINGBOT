"""CLI de la puerta de validación (desde `v2/`).

    python -m eim.validation [informe] [--symbol BTCUSDT] [--nota "…"]
    python -m eim.validation declarar --origin optuna --desde 2026-01-01T00:00Z \
        --hasta 2026-03-01T00:00Z --nota "…" [--sid estrategia@marco …]
    python -m eim.validation versiones

`informe` escribe `reports/validation/validation_v1_<fecha>.md` + `.json`. DuckDB admite un
solo proceso escritor: si la API está en marcha, lee de ella (`GET /v2/validation`); si no,
calcula en este proceso. `declarar` añade a `eim/validation/lineage.json` las ventanas de ajuste
de las huellas ACTUALES del código (antes de que el servicio las dé de alta en automático).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from eim.data.local_api import DEFAULT_API
from eim.data.timeframes import SYMBOLS


def _fetch(api: str, symbol: str) -> dict:
    with urllib.request.urlopen(f"{api}/v2/validation?symbol={symbol}",  # noqa: S310
                                timeout=1800) as r:
        return json.loads(r.read())


def _local(data: str, symbol: str) -> dict:
    from eim.data.paper_store import PaperStore
    from eim.data.store import Store
    from eim.data.validation_store import ValidationStore
    from eim.paper.desk import PaperDesk
    from eim.validation.service import Validator

    ps = PaperStore(Path(data) / "paper.duckdb")
    try:
        desk = PaperDesk(Store(data), ps)
        return Validator(desk, ValidationStore(ps)).compute(symbol)
    finally:
        ps.close()


def _payload(a: argparse.Namespace) -> dict:
    if not a.local:
        try:
            return _fetch(a.api, a.symbol)
        except (urllib.error.URLError, OSError):
            print("API no disponible: se calcula en este proceso", flush=True)
    return _local(a.data, a.symbol)


def _informe(a: argparse.Namespace) -> int:
    from eim.validation.report import write

    p = _payload(a)
    md, js = write(p, Path(a.out), a.nota, a.commit)
    s = p["summary"]
    print(f"{p['criteria']['version']}: {s['counts']} · validadas: {s['validated'] or 'ninguna'}")
    print(f"informe: {md}\ndatos:   {js}")
    return 0


def _declarar(a: argparse.Namespace) -> int:
    from eim.paper.catalog import CATALOG
    from eim.paper.params import ExecParams
    from eim.validation.lineage import (
        LINEAGE_FILE,
        Window,
        declare,
        find_declaration,
        iso_ms,
        load_declarations,
    )

    ep = ExecParams()
    fps = {f"{i.id}@{tf}": i.version(tf, ep) for tf in ep.timeframes for i in CATALOG.values()
           if i.runs_in(tf)}
    unknown = sorted(set(a.sid or ()) - set(fps))
    if unknown:
        print(f"estrategia@marco desconocidas: {unknown}", file=sys.stderr)
        return 2
    decls = load_declarations()
    sel = {sid: fp for sid, fp in fps.items()
           if (sid in a.sid if a.sid else find_declaration(decls, sid, fp) is None)}
    if not sel:
        print("todas las huellas actuales ya están declaradas; nada que añadir")
        return 0
    w = Window(iso_ms(a.desde), iso_ms(a.hasta), a.symbol_window, a.nota_ventana or "")
    if w.to_ms <= w.from_ms:
        print("--hasta debe ser posterior a --desde", file=sys.stderr)
        return 2
    declare(LINEAGE_FILE, a.origin, a.nota, [w], sel, datetime.now(UTC).strftime("%Y-%m-%d"))
    print(f"declaradas {len(sel)} versiones con origen {a.origin} en {LINEAGE_FILE}")
    return 0


def _versiones(a: argparse.Namespace) -> int:
    for v in _payload(a)["versions"]:
        state = "vigente" if v["retired"] is None else "retirada"
        print(f"{v['id']:<36} {v['fingerprint']}  {v['origin']:<8} {state}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eim.validation")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("informe", "versiones"):
        sp = sub.add_parser(name)
        sp.add_argument("--symbol", default="BTCUSDT", choices=SYMBOLS)
        sp.add_argument("--api", default=DEFAULT_API)
        sp.add_argument("--local", action="store_true", help="no leer de la API")
        sp.add_argument("--data", default="data")
        if name == "informe":
            sp.add_argument("--out", default="reports/validation")
            sp.add_argument("--nota", action="append", help="nota o riesgo para el informe")
            sp.add_argument("--commit", default="", help="commit que fijó los criterios")
    dc = sub.add_parser("declarar", help="ventanas de ajuste de las huellas actuales")
    dc.add_argument("--origin", required=True, help="manual, T48b, optuna, …")
    dc.add_argument("--desde", required=True, help="ISO UTC, p. ej. 2026-08-16T00:00Z")
    dc.add_argument("--hasta", required=True)
    dc.add_argument("--nota", required=True, help="qué datos se miraron y para qué")
    dc.add_argument("--nota-ventana", default="")
    dc.add_argument("--symbol-window", default=None, help="símbolo de la ventana (todos)")
    dc.add_argument("--sid", action="append", help="estrategia@marco (por defecto: todas las "
                                                   "huellas aún no declaradas)")
    a = ap.parse_args(argv)
    if a.cmd in (None, "informe"):
        if a.cmd is None:
            a = ap.parse_args(["informe", *(argv or sys.argv[1:])])
        return _informe(a)
    return _declarar(a) if a.cmd == "declarar" else _versiones(a)


if __name__ == "__main__":
    raise SystemExit(main())
