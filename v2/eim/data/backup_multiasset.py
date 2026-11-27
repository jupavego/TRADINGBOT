"""La plataforma multiactivo en la copia de seguridad (T102): catálogo, escáner y resúmenes.

Hasta T102 la copia diaria (`eim/data/backup.py`) no guardaba nada del escáner global. Desde aquí
entra, en la carpeta `multiactivo/` de cada copia:

- `instruments.duckdb` — el registro de instrumentos de T89 (catálogo con altas y bajas fechadas);
- `scanner.duckdb` — corridas, exclusiones, puntuaciones, oportunidades y el **registro de
  intentos** de T95 (irrepetible: cuenta los resultados maduros hacia delante que decide la
  revisión del 2026-12-29);
- los resúmenes publicados: `view.json`, `status.json`, `health.json`, `rollout.json`,
  `placebo.json`.

Las dos bases se copian en frío (adjuntadas en solo lectura): las abre y las cierra su único
escritor, el escáner, que solo corre a ratos. Si en ese momento está en marcha, la base queda
**ausente con motivo** en `manifest.json` (`multiasset.absent`) y la copia sigue siendo completa:
no es una base de la API. Sin escáner en el equipo (no hay nada que copiar) no se crea la carpeta.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from eim.data.backup_dbs import BackupError, copy_db_cold

DIR = "multiactivo"
#: nombre en la copia → ruta bajo `data/`
DBS = {"instruments.duckdb": "instruments.duckdb", "scanner.duckdb": "scanner/scanner.duckdb"}
SUMMARIES = ("view.json", "status.json", "health.json", "rollout.json", "placebo.json")


def copy_multiasset(data_dir: Path, dst_root: Path) -> dict:
    """Copia lo multiactivo a `dst_root/multiactivo/`; devuelve qué entró y qué faltó."""
    out: dict = {"dbs": {}, "absent": {}, "summaries": []}
    dst = dst_root / DIR
    for name, rel in DBS.items():
        src = data_dir / rel
        if not src.exists():
            continue
        dst.mkdir(parents=True, exist_ok=True)
        try:
            out["dbs"][name] = {"tables": copy_db_cold(src, dst / name), "via": "frío"}
        except BackupError as exc:
            (dst / name).unlink(missing_ok=True)
            out["absent"][name] = str(exc)[:300]
    for name in SUMMARIES:
        src = data_dir / "scanner" / name
        if src.exists():
            dst.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst / name)
            out["summaries"].append(name)
    return out
