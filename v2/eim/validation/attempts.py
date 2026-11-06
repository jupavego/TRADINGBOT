"""Intentos evaluados fuera del servicio (T137): archivo versionado que llega al registro vivo.

T137 no puede escribir en `data/paper.duckdb`: lo tiene abierto la API, DuckDB admite un solo
proceso escritor y parar la API tocaría la corrida de T31. Así que cada intento queda en un archivo
versionado en git (`attempts_t137.json`), y el `Validator` de la API lo da de alta la primera vez
que calcula tras cargar este código. Hasta entonces el archivo es el registro.

Cuentan en Holm igual que cualquier versión retirada, y sin p (= 1), lo que es lo conservador: lo
que importa de Holm es el tamaño de la familia. No son versiones vigentes: nacen retiradas y el
servicio no las evalúa ni las publica, así que nada cambia en lo que abren los perfiles.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from eim.validation.lineage import Version, Window, iso_ms, ms_iso

ATTEMPTS_FILE = Path(__file__).parent / "attempts_t137.json"


def write_attempts(path: Path, prereg: str, sha: str, versions: Sequence[Version],
                   variant_of: dict[str, str]) -> dict:
    """Escribe el archivo con una fila por intento. Las ventanas se guardan una vez cada una."""
    windows: dict[str, dict] = {}
    rows = []
    for v in sorted(versions, key=lambda x: (x.sid, x.n)):
        keys = []
        for w in v.windows:
            k = f"{ms_iso(w.from_ms)}|{ms_iso(w.to_ms)}"
            windows.setdefault(k, {"from": ms_iso(w.from_ms), "to": ms_iso(w.to_ms),
                                   "symbol": w.symbol, "note": w.note})
            keys.append(k)
        rows.append({"sid": v.sid, "n": v.n, "fingerprint": v.fingerprint, "parent": v.parent,
                     "variant": variant_of[v.label], "windows": keys})
    created = {v.created_ms for v in versions}
    out = {"description": "Intentos de T137: cuentan en Holm aunque se descarten. Solo se añaden "
                          "archivos; este no se edita.",
           "prereg": prereg, "prereg_sha256": sha, "origin": next(iter(versions)).origin,
           "created": ms_iso(min(created)), "windows": windows, "attempts": rows}
    path.write_text(json.dumps(out, ensure_ascii=False, indent=0) + "\n", encoding="utf-8",
                    newline="\n")
    return out


def load_attempts(path: Path = ATTEMPTS_FILE) -> list[Version]:
    """Los intentos del archivo como versiones retiradas; vacío si aún no se ha corrido."""
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    alta = iso_ms(raw["created"])
    wins = {k: Window(iso_ms(w["from"]), iso_ms(w["to"]), w.get("symbol"), w.get("note", ""))
            for k, w in raw["windows"].items()}
    out = []
    for a in raw["attempts"]:
        strategy, tf = a["sid"].split("@")
        out.append(Version(a["sid"], int(a["n"]), a["fingerprint"], strategy, tf, alta, a["parent"],
                           raw["origin"], f"T137 {a['variant']}: {raw['prereg']}", alta,
                           tuple(wins[k] for k in a["windows"])))
    return out
