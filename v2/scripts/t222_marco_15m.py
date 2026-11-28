"""T222: una mirada del pre-registro «¿sale 15 m de la mesa principal?» (`PLAN/T222.md` §3).

    python scripts/t222_marco_15m.py --look 1 --family <m del día> \
        (--api http://127.0.0.1:8000 | --csv <ledger.csv> | --store <COPIA de paper.duckdb>) \
        [--regime <ms>,<ms>...] [--out reports/t222_marco_15m]

- **No calcula antes de la fecha de la mirada** (2027-02-28 y 2027-05-28, 00:00 UTC): el tramo de
  prueba no se mira antes.
- **El primer veredicto no se revisa:** si `<out>.json` ya tiene esa mirada, o un PASA / NO PASA
  anterior, se niega a escribir.
- `--api` lee el libro fijo (`GET /v2/paper/ledger.csv?scope=perfil`) y la bitácora de rechazos
  (`GET /v2/paper/journal`) en solo lectura. `--store` abre una COPIA del libro (nunca la viva) y
  sabe qué equipo vivió cada fila (T196), lo que da la sensibilidad «solo este equipo».
- `--regime`: instantes (ms) de los cambios de §3.6 anotados en sus propios registros.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
import urllib.request
from pathlib import Path

from eim.analytics import tf_retire as tr
from eim.analytics import tf_retire_report as rep
from eim.paper.universe import PROFILES

FINAL = (tr.PASS, tr.FAIL)


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=300) as r:  # noqa: S310 - solo la API local
        return r.read()


def from_api(api: str, look: int) -> tuple[list[dict], list[dict]]:
    rows = list(csv.DictReader(io.StringIO(
        _get(f"{api}/v2/paper/ledger.csv?scope=perfil").decode("utf-8"))))
    events: list[dict] = []
    for pid in PROFILES:
        before = tr.LOOKS_MS[look]
        while True:
            page = json.loads(_get(f"{api}/v2/paper/journal?profile={pid}&cat=rechazada"
                                   f"&limit=2000&before={before}"))["events"]
            events += [{**e, "profile": e.get("profile", pid)} for e in page]
            if len(page) < 2000 or min(int(e["t"]) for e in page) < tr.T0_MS:
                break
            before = min(int(e["t"]) for e in page)
    return rows, events


def from_store(path: Path, look: int) -> list[dict]:
    from eim.data.paper_store import PaperStore
    from eim.paper import ledger, provenance
    ps = PaperStore(path)
    rows = ledger.window_rows(ps, 0, tr.LOOKS_MS[look])
    return provenance.annotate(rows, provenance.origins(ps))


def main(argv: list[str] | None = None, now_ms: int | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--look", type=int, required=True, choices=sorted(tr.LOOKS_MS))
    ap.add_argument("--family", type=int, required=True, help="familia ampliada de Holm del día")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--api")
    src.add_argument("--csv", type=Path)
    src.add_argument("--store", type=Path)
    ap.add_argument("--regime", default="", help="instantes en ms separados por comas")
    ap.add_argument("--out", type=Path, default=Path("reports/t222_marco_15m"))
    a = ap.parse_args(argv)
    tr.guard(a.look, int(time.time() * 1000) if now_ms is None else now_ms)
    tr.z_crit(a.family)                         # falla antes de leer nada si m es menor
    jpath = a.out.with_suffix(".json")
    done = json.loads(jpath.read_text(encoding="utf-8")) if jpath.exists() else {"looks": {}}
    if str(a.look) in done["looks"] or any(
            x["verdict"]["status"] in FINAL for x in done["looks"].values()):
        print("Ya hay un veredicto escrito: no se revisa (PLAN/T222.md §3.5).", file=sys.stderr)
        return 2
    events = None
    if a.api:
        rows, events = from_api(a.api.rstrip("/"), a.look)
    elif a.csv:
        with a.csv.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    else:
        rows = from_store(a.store, a.look)
    changes = [int(x) for x in a.regime.split(",") if x.strip()]
    done["looks"][str(a.look)] = {
        "verdict": tr.verdict(rows, a.look, a.family, changes),
        "describe": rep.describe(rows, a.look, events, machine_known=a.store is not None),
        "source": "api" if a.api else "csv" if a.csv else "store",
        "generated_ms": int(time.time() * 1000)}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    jpath.write_text(json.dumps(done, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    a.out.with_suffix(".md").write_text(rep.render(done["looks"]), encoding="utf-8")
    print(done["looks"][str(a.look)]["verdict"]["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
