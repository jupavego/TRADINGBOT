"""CLI de líderes (T40), desde `v2/`: `python -m eim.leaders <orden>`.

  add 0xDIR [--label X] [--vault] [--watch]   alta manual (vault: datos de `vaultDetails`)
  add-binance ID --label X                     solo registro manual (T33: sin automatizar)
  discover [--seconds 300] [--coins BTC,ETH]   muestra el WS `trades` y registra candidatos
  list [--status S]                            líderes registrados
  watch|unwatch 0xDIR...                       empezar/dejar de capturar sus datos
  run [--minutes M] [--ws-max N]               vigilante (WS ≤ N, el resto por REST)
  report [--minutes M] [--json]                latencia, coincidencia y huecos
  history 0xDIR [--last N]                     historial guardado de un líder

Solo lectura de datos públicos: no hay claves ni órdenes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from pydantic import ValidationError

from eim.core.leaders import Leader, leader_id
from eim.data.leader_discover import discover
from eim.data.leader_report import render, summary
from eim.data.leader_store import LeaderStore
from eim.data.leader_watch import LeaderWatch
from eim.data.providers.leaders import HyperliquidInfo, now_ms
from eim.leaders.parse import vault_leader


def _hl_id(addr: str) -> str:
    return leader_id("hyperliquid", addr.strip())


def _add(store: LeaderStore, a: argparse.Namespace) -> str:
    now = now_ms()
    if a.vault:
        ld = vault_leader(HyperliquidInfo().vault_details(a.address.lower()), now)
    else:
        addr = a.address.strip().lower()
        try:
            ld = Leader(id=_hl_id(addr), venue="hyperliquid", address=addr, label=a.label or "",
                        origin="manual", discovered_at=now, source="manual")
        except ValidationError:
            return f"dirección Hyperliquid inválida: {a.address} (0x + 40 hex)"
    new = store.upsert_leader(ld, now)
    if a.watch:
        _toggle_watch(store, ld.id, True, now)
    return f"{'alta' if new else 'actualizado'}: {ld.id} {ld.label}"


def _toggle_watch(store: LeaderStore, lid: str, on: bool, now: int) -> str:
    """Solo alterna candidate ↔ watch: aprobar o rechazar es decisión de T41/usuario."""
    current = {ld.id: ld.status for ld in store.leaders()}.get(lid)
    if current is None:
        return f"{lid}: no existe"
    if current in ("approved", "rejected"):
        return f"{lid}: sin cambios (estado {current})"
    store.set_status(lid, "watch" if on else "candidate", now)
    return f"{lid}: ok"


def _list(store: LeaderStore, status: str | None) -> str:
    rows = store.leaders((status,) if status else None)
    return "\n".join(f"{ld.status:9s} {ld.origin:9s} {ld.id} {ld.label} {ld.evidence}"
                     for ld in rows) or "(sin líderes)"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eim.leaders", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default="data", help="carpeta de datos (leaders.duckdb)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add")
    p.add_argument("address")
    p.add_argument("--label", default="")
    p.add_argument("--vault", action="store_true")
    p.add_argument("--watch", action="store_true")
    p = sub.add_parser("add-binance")
    p.add_argument("id")
    p.add_argument("--label", required=True)
    p = sub.add_parser("discover")
    p.add_argument("--seconds", type=float, default=300.0)
    p.add_argument("--coins", default="BTC,ETH")
    p.add_argument("--top", type=int, default=20)
    p = sub.add_parser("list")
    p.add_argument("--status", choices=["candidate", "watch", "approved", "rejected"])
    for name in ("watch", "unwatch"):
        sub.add_parser(name).add_argument("addresses", nargs="+")
    p = sub.add_parser("run")
    p.add_argument("--minutes", type=float, default=None)
    p.add_argument("--ws-max", type=int, default=10, help="líderes por WS (máx. oficial 10)")
    p = sub.add_parser("report")
    p.add_argument("--minutes", type=float, default=60.0)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("history")
    p.add_argument("address")
    p.add_argument("--last", type=int, default=30)
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):  # Windows redirigido a archivo: cp1252 no basta
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    store = LeaderStore.at_root(a.root)
    try:
        out = _dispatch(store, a)
    finally:
        store.close()
    print(out)
    return 0


def _dispatch(store: LeaderStore, a: argparse.Namespace) -> str:
    now = now_ms()
    if a.cmd == "add":
        return _add(store, a)
    if a.cmd == "add-binance":
        ld = Leader(id=leader_id("binance", a.id), venue="binance", address=a.id,
                    label=a.label, origin="manual", discovered_at=now, source="manual")
        store.upsert_leader(ld, now)
        return f"registrado (solo manual, sin datos automáticos): {ld.id}"
    if a.cmd == "discover":
        coins = tuple(c.strip().upper() for c in a.coins.split(",") if c.strip())
        found = asyncio.run(discover(store, a.seconds, coins, a.top))
        return f"{len(found)} candidatos nuevos\n" + _list(store, "candidate")
    if a.cmd == "list":
        return _list(store, a.status)
    if a.cmd in ("watch", "unwatch"):
        return "\n".join(_toggle_watch(store, _hl_id(x), a.cmd == "watch", now)
                         for x in a.addresses)
    if a.cmd == "run":
        watch = LeaderWatch(store, HyperliquidInfo(), store.leaders(("watch", "approved")),
                            ws_max=max(0, min(a.ws_max, 10)))
        if not watch.books:
            return "No hay líderes en seguimiento: usa `watch 0x…` primero."
        if watch.manual_only:
            print(f"Solo manual (sin captura): {', '.join(watch.manual_only)}", file=sys.stderr)
        start = now_ms()
        try:
            asyncio.run(watch.run(asyncio.Event(), a.minutes))
        except KeyboardInterrupt:
            pass
        return render(summary(store, start))
    if a.cmd == "report":
        s = summary(store, now - int(a.minutes * 60_000))
        return json.dumps(s, indent=1, default=str) if a.json else render(s)
    if a.cmd == "history":
        ev = store.history(_hl_id(a.address))[-a.last:]
        return "\n".join(json.dumps(e, ensure_ascii=False) for e in ev) or "(sin historial)"
    raise SystemExit(f"orden desconocida: {a.cmd}")
