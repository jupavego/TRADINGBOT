"""Registro de intentos de T80: todos cuentan en Holm, también los que se descartan.

Un archivo versionado en git (como `attempts_t137.json` y `attempts_t139.json` de T139): la
familia de Holm de T84 tiene que incluir lo que T80 probó, y la única forma honesta de que eso no
se olvide es dejarlo escrito con la huella del pre-registro que lo fijó.
"""

from __future__ import annotations

import json
from pathlib import Path

ATTEMPTS_FILE = Path(__file__).parent.parent / "attempts_t80.json"


def rows_from(oos: dict) -> list[dict]:
    """Una fila por intento: señal × horizonte, con su p y su p corregida por Holm."""
    out = []
    for h, block in sorted(oos["horizons"].items(), key=lambda kv: int(kv[0])):
        for name, s in sorted(block.items()):
            out.append({"signal": name, "horizon_s": int(h), "metric": "ic_spearman",
                        "test_days": s["test_days"],
                        "ic_mean": None if s["ic"]["mean"] is None else round(s["ic"]["mean"], 6),
                        "p": round(s["ic_p"], 6), "p_holm": round(s["ic_p_holm"], 6)})
    return out


def write_attempts(path: Path, prereg, oos: dict, window: dict) -> dict:
    """Escribe el registro (familia completa) y lo devuelve."""
    rows = rows_from(oos)
    out = {"description": "Intentos de T80 (prueba de techo del carril HFT): cuentan en la "
                          "familia de Holm de T84 aunque se descarten. Solo se añaden archivos; "
                          "este no se edita.",
           "task": prereg.task, "prereg": prereg.version, "prereg_sha256": prereg.sha256,
           "family": prereg.attempts.family, "declared_rule": prereg.attempts.rule,
           "window": window, "attempts": rows}
    if len(rows) != prereg.attempts.family:
        raise ValueError(f"intentos calculados {len(rows)} ≠ familia declarada "
                         f"{prereg.attempts.family}: revisa el pre-registro, no el resultado")
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8",
                    newline="\n")
    return out


def load_attempts(path: Path = ATTEMPTS_FILE) -> dict | None:
    """El registro, o None si T80 aún no se ha corrido en este equipo."""
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
