"""Qué componentes del EIM están vivos, desde qué checkout y desde cuándo (T120, entregable 2).

Lo usan `GET /v2/health` (campo `components`) y `servicio_continuo.ps1`, que al final lo imprime y
avisa si algo corre desde otra carpeta (un worktree, una copia vieja). Los latidos son los de
`fleet_watch` (T148): una sola lista de quién publica latido y dónde.

    python -m eim.operation.components --data-dir data [--expect C:/.../v2]   # código 3: ajeno
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from eim.operation.fleet_watch import BEATS, DOWN_S, USAGE, ages
from eim.operation.origin import CHECKOUT, same_checkout

BROKER = "bróker simulado"
# Por qué un servicio no declara su checkout aunque el código sea nuevo (no es «código anterior»).
NOTES = {USAGE: "sin archivo de latido: la señal es su última muestra",
         BROKER: "corre dentro de la API"}


def _beat(path: Path) -> dict:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def components(data_dir: str | Path, now_s: float | None = None,
               down_s: float = DOWN_S) -> list[dict]:
    """Una fila por servicio: vivo, segundos desde su último latido, PID, arranque y checkout.

    `checkout` None = el servicio corre con código anterior a T120 (su latido no lo dice); se ve
    en cuanto se relanza."""
    now = time.time() if now_s is None else now_s
    seen = ages(Path(data_dir), now)
    out = []
    for name, age in seen.items():
        d = _beat(Path(data_dir) / BEATS[name]) if name != USAGE else {}
        out.append({"name": name, "alive": age is not None and age < down_s, "age_s": age,
                    "pid": d.get("pid"),
                    "started_at": d.get("proc_started_at") or d.get("started_at"),
                    "checkout": d.get("checkout"), "note": NOTES.get(name, "")})
    api = next((r for r in out if r["name"] == "API"), None)
    for r in out:     # el bróker corre dentro de la API: su origen es el de ella
        if r["name"] == BROKER and api and r["alive"] and api["alive"] and not r["checkout"]:
            r.update(checkout=api["checkout"], started_at=api["started_at"], pid=api["pid"])
    return out


def foreign(rows: list[dict], expect: str = CHECKOUT) -> list[dict]:
    """Los vivos que dicen correr desde otra carpeta que `expect`."""
    return [r for r in rows if r["alive"] and r["checkout"]
            and not same_checkout(r["checkout"], expect)]


def _fmt(r: dict, now_s: float) -> str:
    age = "nunca" if r["age_s"] is None else f"latido hace {r['age_s']:.0f} s"
    since = ("" if not r["started_at"] else
             f", desde {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(r['started_at'] / 1000))}")
    where = r["checkout"] or r.get("note") or "checkout sin declarar (código anterior a T120)"
    return f"  {'VIVO ' if r['alive'] else 'CAÍDO'}  {r['name']}: {age}{since} · {where}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--expect", default=CHECKOUT, help="carpeta v2 que debería mandar")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):    # consola cp1252: un carácter raro no tumba el informe
        sys.stdout.reconfigure(errors="replace")
    now = time.time()
    rows = components(a.data_dir, now)
    print("Componentes del EIM:")
    for r in rows:
        print(_fmt(r, now))
    bad = foreign(rows, a.expect)
    for r in bad:
        print(f"AVISO: {r['name']} corre desde {r['checkout']}, no desde {a.expect}. Para que lo "
              "adopte esta carpeta: detener_servicio.ps1 -Todo y relanzar servicio_continuo.ps1.")
    return 3 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
