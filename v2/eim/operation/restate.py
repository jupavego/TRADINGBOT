"""Reexpresar informes semanales ya publicados con el universo oficial (T144, entregable 5).

    python -m eim.operation.restate --ledger-csv ledger.csv --reports-dir reports/operation \
        --weeks 2026-W43 2026-W44 2026-W45 2026-W46

**No se borra nada.** La tabla original de cada informe se queda tal cual —es lo que se publicó
en su momento— y debajo se añade un bloque delimitado con la lectura corregida, diciendo que la
anterior contaba otra cosa. Volver a correrlo reemplaza solo ese bloque, nunca el informe. Una
semana sin informe publicado (la que está en curso) recibe su lectura en un archivo aparte.

El libro entra por CSV (`GET /v2/paper/ledger.csv` de la API viva, o `--ledger-db` si nadie tiene
la base abierta): con los servicios en marcha `data/paper.duckdb` no se puede leer en paralelo.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path

from eim.operation import report as report_io
from eim.operation.weekly import WEEK_MS
from eim.paper import accounting, universe

BEGIN = "<!-- T144:reexpresion -->"
END = "<!-- /T144:reexpresion -->"
HEAD = (
    "## Reexpresión con el universo oficial (T144)\n\n"
    "**La lectura de arriba contaba otra cosa.** Esa tabla mide el carril de ejecución del "
    "servicio (la «corrida de operación»), que en esta semana vio muy pocas operaciones, mientras "
    "el libro fijo de los cuatro perfiles cerraba muchas más. Desde T144 el universo oficial de "
    "T31 es el libro de perfiles sin las operaciones `retro` (◆ del usuario, 2026-11-09), así que "
    "esta es la lectura que decide. Lo publicado antes no se borra: se conserva encima para que "
    "se vea qué cambió y por qué.\n"
)
APART = (
    "# Reexpresión de {label} con el universo oficial (T144)\n\n"
    "Esta semana **no tiene informe semanal publicado** (el servicio lo escribe al cerrar la "
    "semana UTC), así que la lectura corregida se publica aquí, aparte y sin tocar nada. Es una "
    "lectura **parcial**: cuenta lo que el libro tenía cerrado al generarla.\n"
)


def week_bounds(label: str) -> tuple[int, int]:
    """`2026-W43` → (lunes 00:00 UTC, +7 días) en ms."""
    year, wk = label.split("-W")
    t0 = int(dt.datetime.fromisocalendar(int(year), int(wk), 1)
             .replace(tzinfo=dt.UTC).timestamp() * 1000)
    return t0, t0 + WEEK_MS


def rows_from_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return [r for r in csv.DictReader(fh) if r.get("scope") == universe.PROFILE_SCOPE]


def rows_from_db(path: Path, t0: int, t1: int) -> list[dict]:
    from eim.data.paper_store import PaperStore
    from eim.paper.ledger import window_rows
    return window_rows(PaperStore(path), t0, t1)


def section(label: str, rows: list[dict], t0: int, t1: int) -> tuple[str, dict]:
    """(bloque Markdown de la reexpresión, cifras en JSON) de una semana ya publicada."""
    figs = accounting.figures(accounting.window(rows, t0, t1))
    figs["window"] = {"from": t0, "to": t1}
    figs["available"] = True
    # el mismo renderizador que usan los informes nuevos: las dos lecturas no pueden divergir
    body = report_io.official_lines({"official": figs, "universe": universe.declaration()})
    text = "\n".join([BEGIN, "", HEAD, *body[2:], END, ""])
    return text, {"week": label, "task": "T144", **figs}


def splice(md: Path, text: str) -> str:
    """Añade (o reemplaza) el bloque de la reexpresión al final, sin tocar el resto."""
    old = md.read_text(encoding="utf-8")
    if BEGIN in old and END in old:
        head, rest = old.split(BEGIN, 1)
        return head + text + rest.split(END, 1)[1].lstrip("\n")
    return old.rstrip("\n") + "\n\n" + text


def restate(rows: list[dict], reports_dir: Path, weeks: list[str],
            write: bool = True) -> list[dict]:
    """Añade a cada informe publicado su lectura corregida; sin informe, la publica aparte."""
    out = []
    for label in weeks:
        t0, t1 = week_bounds(label)
        md = reports_dir / f"semana_{label}.md"
        text, figs = section(label, rows, t0, t1)
        existed = md.exists()
        target = md if existed else reports_dir / f"semana_{label}_t144.md"
        if write:
            body = splice(md, text) if existed else APART.format(label=label) + "\n" + text
            target.write_text(body, encoding="utf-8")
            (reports_dir / f"semana_{label}_t144.json").write_text(
                json.dumps(figs, indent=2, ensure_ascii=False), encoding="utf-8")
        out.append({"week": label, "md": str(target), "existed": existed,
                    "n_total": figs["tally"]["n_total"], "n_counted": figs["n"],
                    "retro_excluded": figs["retro_excluded"]["n"],
                    "pnl_usdt": figs["pnl_usdt"] or 0.0,
                    "digest": figs["counted_digest"]})
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="eim.operation.restate", description=__doc__)
    p.add_argument("--ledger-csv", type=Path, help="export de GET /v2/paper/ledger.csv")
    p.add_argument("--ledger-db", type=Path, help="data/paper.duckdb (solo si nadie la tiene "
                                                  "abierta: los servicios la bloquean)")
    p.add_argument("--reports-dir", type=Path, required=True)
    p.add_argument("--weeks", nargs="+", required=True, help="p. ej. 2026-W43 2026-W44")
    p.add_argument("--dry-run", action="store_true", help="solo imprime, no escribe")
    a = p.parse_args(argv)
    if not a.ledger_csv and not a.ledger_db:
        p.error("hace falta --ledger-csv o --ledger-db")
    if a.ledger_csv:
        rows = rows_from_csv(a.ledger_csv)
    else:
        lo = min(week_bounds(w)[0] for w in a.weeks)
        hi = max(week_bounds(w)[1] for w in a.weeks)
        rows = rows_from_db(a.ledger_db, lo, hi)
    print(f"libro: {len(rows)} filas de alcance perfil")
    for r in restate(rows, a.reports_dir, a.weeks, write=not a.dry_run):
        state = ("simulado" if a.dry_run else
                 "añadido al informe" if r["existed"] else f"publicado aparte en {r['md']}")
        print(f"{r['week']}: {r['n_counted']} de {r['n_total']} cuentan "
              f"({r['retro_excluded']} retro fuera), PnL {r['pnl_usdt']:+.2f} USDT, "
              f"huella {r['digest']} · {state}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
