"""Estado de los datos de este equipo (T125), en solo lectura.

Las bases que tiene abiertas un servicio (API, líderes) no se pueden leer desde otro proceso
(DuckDB, un escritor): sus filas salen entonces de la copia local más reciente y se dice de
cuándo es. Nada aquí crea una base: una carpeta sin historial se informa, no se rellena.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from eim.data.backup import listing
from eim.data.backup_dbs import DB_NAME, LEADERS, PAPER, count_file, in_use
from eim.data.backup_restore import complete, read_manifest

HISTORY_DBS = (DB_NAME, PAPER, LEADERS)
HEARTBEATS = {"operación": "operation/heartbeat.json", "líderes": "leaders/heartbeat.json",
              "bróker simulado": "paper/heartbeat.json", "captura HFT": "micro_hft/heartbeat.json",
              "microestructura": "micro/heartbeat.json"}
LIVE_S = 900.0                      # latido más nuevo que esto = servicio en marcha


def has_history(data_dir: Path) -> bool:
    """¿Hay alguna base con historial? (lo que el arranque seguro exige)."""
    return any((Path(data_dir) / db).exists() for db in HISTORY_DBS)


def _beat_ms(p: Path) -> int | None:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for k in ("last_heartbeat", "last_tick"):
        v = d.get(k) if isinstance(d, dict) else None
        if isinstance(v, (int, float)) and v > 1e12:
            return int(v)
    return None


def stamp_s(name: str) -> float | None:
    """Segundos UTC del nombre `eim_AAAAMMDD-HHMMSS[-n]` de una copia."""
    try:
        return datetime.strptime(name[4:19], "%Y%m%d-%H%M%S").replace(tzinfo=UTC).timestamp()
    except ValueError:
        return None


@dataclass
class DataState:
    data_dir: str
    exists: bool
    machine: str = ""
    dbs: dict[str, dict] = field(default_factory=dict)   # base: {bytes, rows|None, in_use}
    services: dict[str, float] = field(default_factory=dict)   # nombre: segundos sin latido
    last_backup: str = ""
    last_backup_age_h: float | None = None
    last_backup_complete: bool = False
    backup_rows: dict[str, dict[str, int]] = field(default_factory=dict)
    share_configured: bool = False

    @property
    def empty(self) -> bool:
        return not any(d.get("bytes") for d in self.dbs.values())

    def running(self) -> list[str]:
        return [k for k, age in self.services.items() if age < LIVE_S]


def state(data_dir: Path, backup_dir: Path, *, now_s: float | None = None) -> DataState:
    now = time.time() if now_s is None else now_s
    d = Path(data_dir)
    s = DataState(str(d.resolve()), d.exists())
    try:
        s.machine = (d / "machine_id").read_text(encoding="utf-8").strip()
    except OSError:
        s.machine = ""
    s.share_configured = (d / "share_config.json").exists()
    for db in HISTORY_DBS:
        p = d / db
        if not p.exists():
            s.dbs[db] = {"bytes": 0, "rows": None, "in_use": False}
            continue
        busy = bool(in_use(p))
        rows = None
        if not busy:
            try:
                rows = count_file(p)
            except Exception:  # noqa: BLE001 - base dañada o versión de DuckDB distinta
                rows = None
        s.dbs[db] = {"bytes": p.stat().st_size, "rows": rows, "in_use": busy}
    for name, rel in HEARTBEATS.items():
        if (ms := _beat_ms(d / rel)) is not None:
            s.services[name] = round(now - ms / 1000.0, 1)
    copies = [p for p in listing(Path(backup_dir)) if complete(p)]
    if copies:
        last = copies[-1]
        s.last_backup, s.last_backup_complete = last.name, True
        if (t := stamp_s(last.name)) is not None:
            s.last_backup_age_h = round((now - t) / 3600.0, 1)
        m = read_manifest(last) or {}
        s.backup_rows = {db: v.get("tables", {}) for db, v in m.get("dbs", {}).items()}
    return s


def stale_dbs(local: dict[str, dict[str, int]], remote: dict[str, dict[str, int]]
              ) -> list[str]:
    """Bases con MENOS filas en total que en la copia remota del MISMO equipo: estos datos son
    más viejos que lo ya publicado (p. ej. se restauró una copia antigua encima). Se compara el
    total por base, no tabla a tabla: la poda normal de una tabla no es un retroceso."""
    out = []
    for db, tables in remote.items():
        mine = local.get(db)
        if mine is None:
            continue
        if (a := sum(mine.values())) < (b := sum(tables.values())):
            out.append(f"{db}: {a:,} filas aquí < {b:,} en la copia publicada")
    return out
