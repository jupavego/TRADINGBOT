"""T177: el examen físico de T169 (mismo código y mismos umbrales) sobre los 16 reemplazos.

Solo cambia qué prospectos entran: los inscritos que reemplazan a un descartado de T169 (campo
`replaces` de su expediente). La copia del banco es la de T169, en solo lectura: el plan nuevo
guarda su huella y se comprueba al reanudar. Por la cola, un proceso (`~/.claude/CLAUDE.md`):

    python scripts/t177_examen.py plan --bank backups/t169_examen/banco --work backups/t177_examen
    python scripts/t177_examen.py generate --work backups/t177_examen     # largo y reanudable
    python scripts/t177_examen.py identity --work backups/t177_examen
    python scripts/t177_examen.py lookahead --work backups/t177_examen
    python scripts/t177_examen.py exam --work backups/t177_examen --task T177 \\
        --notes PLAN/notas/T177_bibliografia_prospectos.md --out reports/t177_examen_fisico

Protocolo fijado antes de buscar: `PLAN/T177.md`.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))     # el `eim` de este checkout
sys.path.insert(0, str(HERE))

import t169_examen as base  # noqa: E402

from eim.nursery.prospect import Prospect, load_dossiers, load_prospects  # noqa: E402


def replacements() -> tuple[Prospect, ...]:
    """Los prospectos inscritos que reemplazan a un descartado de T169."""
    ids = {p["id"] for d in load_dossiers().values() if d.get("status") == "inscrito"
           for p in d.get("prospects", []) if p.get("replaces")}
    return tuple(p for p in load_prospects() if p.id in ids)


base.load_prospects = replacements       # el resto del examen es el de T169, sin tocar

if __name__ == "__main__":
    base.main()
