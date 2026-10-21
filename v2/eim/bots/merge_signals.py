"""Pasa posturas de `bot_signals` de una carpeta de datos a otra (solo añade, nunca sobrescribe).

Sirve para llevar a los datos vivos un relleno hecho sobre una COPIA (la API vive bloqueando
`reports.duckdb`: no se puede rellenar encima sin pararla):

    python -m eim.bots.merge_signals --from D:/copia/data --into data [--bots a,b] [--dry-run]

Mismo contrato que `BotSignalStore.append`: la clave (bot, estrategia, versión, símbolo, marco,
asof) ya existente se respeta (`ON CONFLICT DO NOTHING`); el `created_ms` original se conserva, de
modo que lo rellenado sigue contando como «backtest» y no como «vivo» para la puerta de T49.
Abre el destino en escritura: páralo (API/operación) o apunta a una copia.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

from eim.api.reports_db import ReportStore
from eim.data.bots.store import BotSignalStore

COLS = ("bot_id, strategy, version, symbol, timeframe, asof_ms, stance, confidence, status, "
        "created_ms, signal")


def counts(con, schema: str = "main") -> dict[tuple, int]:
    rows = con.execute(f"SELECT bot_id, strategy, timeframe, count(*) FROM {schema}.bot_signals "
                       "GROUP BY ALL").fetchall()
    return {(b, s, t): int(n) for b, s, t, n in rows}


def merge(src: Path, dst: Path, bots: tuple[str, ...] = (), dry_run: bool = False) -> dict:
    """Añade al destino lo que le falta del origen. Devuelve {(bot, estrategia, marco): nuevas}."""
    store = ReportStore(dst / "reports.duckdb")
    BotSignalStore(*store.connection)                     # crea la tabla si no existe
    con, lock = store.connection
    where = f" WHERE bot_id IN ({','.join('?' * len(bots))})" if bots else ""
    with lock:
        lit = (src / "reports.duckdb").as_posix().replace("'", "''")   # ATTACH no admite parámetros
        con.execute(f"ATTACH '{lit}' AS origen (READ_ONLY)")
        try:
            before = counts(con)
            if not dry_run:
                con.execute(f"INSERT INTO main.bot_signals ({COLS}) SELECT {COLS} "
                            f"FROM origen.bot_signals{where} ON CONFLICT DO NOTHING", list(bots))
            wanted = counts(con, "origen")
            after = counts(con)
            if dry_run:
                after = {k: before.get(k, 0) for k in wanted}
        finally:
            con.execute("DETACH origen")
    out = {}
    for k, n in wanted.items():
        if bots and k[0] not in bots:
            continue
        have = after.get(k, 0)
        out[k] = {"origen": n, "destino_antes": before.get(k, 0), "destino_despues": have,
                  "nuevas": have - before.get(k, 0),
                  "faltan": (n - (before.get(k, 0) if dry_run else have))}
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="eim.bots.merge_signals", description=__doc__)
    p.add_argument("--from", dest="src", required=True, help="carpeta de datos de origen")
    p.add_argument("--into", dest="dst", required=True, help="carpeta de datos de destino")
    p.add_argument("--bots", default="", help="ids de bot separados por coma (todos si se omite)")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    bots = tuple(x for x in a.bots.split(",") if x)
    try:
        res = merge(Path(a.src), Path(a.dst), bots, a.dry_run)
    except duckdb.IOException as exc:
        print("no se pudo abrir el destino (¿lo tiene abierto la API?):", exc)
        return 2
    for (b, s, t), r in sorted(res.items()):
        print(f"{b}:{s}@{t}  origen {r['origen']}  nuevas {r['nuevas']}  faltan {r['faltan']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
