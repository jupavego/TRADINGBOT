"""CLI del diario de la protección (T110), desde `v2/`:

    python -m eim.paper proteccion lista [--symbol BTCUSDT] [--estado inconsistente]
    python -m eim.paper proteccion historial "moderado|BTCUSDT|BTCUSDT:15m:...:estrategia"
    python -m eim.paper proteccion reconciliar "<op_id>" --decision recalculo --nota "por qué"

Con la API en marcha (tiene `data/paper.duckdb` abierta: DuckDB admite un solo escritor) todo va
por ella (`/v2/paper/protection…`); si no responde, se lee y se escribe la base directamente.
`reconciliar` solo acepta operaciones en «estado inconsistente» y exige una nota: `recalculo` deja
mandar al recálculo (la siguiente pasada reanuda el diario desde él), `descartar` deja de seguirla.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from eim.data.local_api import DEFAULT_API, post_local


def add_parser(sub) -> None:
    pp = sub.add_parser("proteccion", help="diario de la protección (T110)")
    acts = pp.add_subparsers(dest="act", required=True)
    ls = acts.add_parser("lista", help="estado vigente de cada operación con escalera")
    ls.add_argument("--symbol", default=None)
    ls.add_argument("--estado", default=None, help="abierta, protegida, inconsistente…")
    hs = acts.add_parser("historial", help="todas las filas de una operación")
    hs.add_argument("op_id")
    rc = acts.add_parser("reconciliar", help="resuelve a mano una operación inconsistente")
    rc.add_argument("op_id")
    rc.add_argument("--decision", required=True, choices=("recalculo", "descartar"))
    rc.add_argument("--nota", required=True)
    for p in (ls, hs, rc):
        p.add_argument("--api", default=DEFAULT_API)
        p.add_argument("--data", default="data")


def _get(api: str, path: str, params: dict) -> dict:
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    with urllib.request.urlopen(f"{api}{path}?{q}", timeout=60) as r:  # noqa: S310 - API local
        return json.loads(r.read())


def _local(a: argparse.Namespace):
    from eim.data.paper_store import PaperStore
    from eim.paper import protection

    ps = PaperStore(Path(a.data) / "paper.duckdb")
    protection.ensure(ps)
    return ps


def _iso(t: int | None) -> str:
    return "—" if t is None else datetime.fromtimestamp(t / 1000, UTC).strftime("%Y-%m-%d %H:%M")


def _print_rows(rows: list[dict]) -> None:
    for r in rows:
        stop = "—" if r.get("stop") is None else f"{r['stop']:g}"
        print(f"{r['op_id']:<60} {r['status']:<13} esc. {r.get('level') or 0:>2}  SL {stop:<10} "
              f"{_iso(r.get('updated_t'))}  {r['event']}"
              + (f" · {r['note']}" if r.get("note") else ""))


def run(a: argparse.Namespace) -> int:
    try:
        if a.act == "lista":
            out = _get(a.api, "/v2/paper/protection", {"symbol": a.symbol, "status": a.estado})
            print(json.dumps(out["counts"], ensure_ascii=False))
            _print_rows(out["rows"])
        elif a.act == "historial":
            _print_rows(_get(a.api, "/v2/paper/protection/history", {"op_id": a.op_id})["rows"])
        else:
            q = urllib.parse.urlencode({"op_id": a.op_id, "decision": a.decision,
                                        "note": a.nota})
            out = post_local(a.api, f"/v2/paper/protection/resolve?{q}", "paper-protection")
            _print_rows([out["row"]])
        return 0
    except urllib.error.HTTPError as exc:
        print(f"la API respondió {exc.code}: {exc.read().decode('utf-8', 'replace')}",
              file=sys.stderr)
        return 1
    except (urllib.error.URLError, OSError):
        print("API no disponible: se usa la base directamente", flush=True)
    return _run_local(a)


def _run_local(a: argparse.Namespace) -> int:
    from eim.paper import protection
    from eim.paper.generate import now_ms
    from eim.paper.protection_sync import reconcile

    try:
        ps = _local(a)
    except Exception as exc:  # noqa: BLE001 - p. ej. la API sigue en marcha y tiene la base
        print(f"no se pudo abrir {a.data}/paper.duckdb ({type(exc).__name__}: {exc}); si la API "
              "está en marcha, reinténtalo cuando responda", file=sys.stderr)
        return 1
    try:
        if a.act == "lista":
            _print_rows([r for r in protection.overview(ps, a.symbol, limit=1_000_000)
                         if a.estado is None or r["status"] == a.estado])
        elif a.act == "historial":
            _print_rows(protection.history(ps, a.op_id))
        else:
            _print_rows([reconcile(ps, a.op_id, a.decision, a.nota, now_ms())])
        return 0
    except (LookupError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        ps.close()
