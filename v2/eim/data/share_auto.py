"""Experiencia compartida AUTOMÁTICA (T61): el propio sistema exporta e importa, sin comandos.

Cada proceso que tiene abiertas sus bases corre un `ShareAgent` sobre ellas:
- la API (`role="api"`): `reports.duckdb` + `paper.duckdb`;
- el servicio de líderes (`role="leaders"`): `leaders.duckdb`.
Cada `import_every_s` mira la nube: si otra máquina tiene una exportación nueva la une **en vivo**
(bajo el cerrojo de la base, en una transacción, con copia previa en caliente); cada
`export_every_s` exporta lo propio **si cambió** (copia coherente a una carpeta de trabajo, Parquet
+ manifest a la nube, y poda de las propias antiguas). Tras importar contextos nuevos, el
validador recalcula los veredictos sobre la unión. Un fallo (nube sin sincronizar, exportación
corrupta…) se anota en el estado y se reintenta; nunca detiene la operación.

Configuración: `EIM_SHARED_DIR`/`EIM_MACHINE` o, una vez, `python -m eim.data.share setup`
(`data/share_config.json`). Sin carpeta compartida, no hace nada. Siempre SIMULADO.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from eim.data.backup import copy_db_hot
from eim.data.machine import machine_id
from eim.data.share_export import export, prune_own
from eim.data.share_git import GitTransport
from eim.data.share_import import Export, _merge_db, discover
from eim.data.share_report import Report
from eim.data.share_spec import LOG_DDL, specs_of

log = logging.getLogger("eim.share")
CONFIG = "share_config.json"
TEMP_TABLES = ("inc", "newj", "newj2")


def load_config(data_dir: Path, env: dict | None = None) -> dict:
    """{shared_dir, machine?}: el entorno manda sobre `data/share_config.json`."""
    env = os.environ if env is None else env
    try:
        cfg = json.loads((data_dir / CONFIG).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    if env.get("EIM_SHARED_DIR"):
        cfg["shared_dir"] = env["EIM_SHARED_DIR"]
    if env.get("EIM_SHARE_GIT_URL"):
        cfg["git_url"] = env["EIM_SHARE_GIT_URL"]
    return cfg


def save_config(data_dir: Path, shared_dir: str | None, machine: str | None = None,
                git_url: str | None = None) -> Path:
    p = data_dir / CONFIG
    p.parent.mkdir(parents=True, exist_ok=True)
    cfg = {k: v for k, v in (("shared_dir", shared_dir and str(shared_dir)),
                             ("git_url", git_url), ("machine", machine)) if v}
    p.write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    return p


@dataclass
class Live:
    """Una base abierta por este proceso: su conexión, su cerrojo y (opcional) cómo copiarla."""
    con: object
    lock: object
    copier: Callable[[Path], object] | None = None


class ShareAgent:
    def __init__(self, role: str, data_dir: Path, shared_dir: Path, machine: str,
                 live: dict[str, Live], *, backup_dir: Path | None = None,
                 import_every_s: float = 3600.0, export_every_s: float = 6 * 3600.0,
                 keep: int = 3, clock: Callable[[], float] = time.time,
                 on_imported: Callable[[], object] | None = None,
                 transport: GitTransport | None = None) -> None:
        self.transport = transport      # None = carpeta de nube; GitTransport = repo privado
        self.role, self.data_dir = role, data_dir
        self.shared_dir, self.machine = shared_dir, machine
        self.live, self.backup_dir = live, backup_dir
        self.import_every_s, self.export_every_s, self.keep = import_every_s, export_every_s, keep
        self.clock, self.on_imported = clock, on_imported
        self._state_path = data_dir / "share" / f"state_{role}.json"
        try:
            self.state = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.state = {}
        self.state.setdefault("imported", {})
        self.next_import = self.next_export = 0.0
        self.error = ""

    # --- calendario ---------------------------------------------------------------------
    def due(self) -> bool:
        now = self.clock()
        return now >= self.next_import or now >= self.next_export

    def status(self) -> dict:
        return {"role": self.role, "machine": self.machine, "shared_dir": str(self.shared_dir),
                "dbs": sorted(self.live), "last_import": self.state.get("last_import"),
                "last_export": self.state.get("last_export"),
                "imported": self.state["imported"], "last_report": self.state.get("last_report"),
                "error": self.error}

    def tick(self) -> None:
        """Importa y/o exporta lo que toque. Nunca lanza: el error queda en `status()`."""
        now = self.clock()
        self.error = ""
        try:
            if self.transport is not None and (now >= self.next_import
                                               or now >= self.next_export):
                self.transport.pull()           # prepara view/ y trae lo nuevo de las demás
            if not self.shared_dir.exists():
                raise RuntimeError(f"la carpeta compartida no existe: {self.shared_dir} "
                                   "(¿la nube aún no está sincronizada?)")
            if now >= self.next_import:
                self.next_import = now + self.import_every_s
                self.import_now()
            if now >= self.next_export:
                self.next_export = now + self.export_every_s
                self.export_now()
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            log.error("compartir (%s): %s", self.role, self.error)
            self.next_import = self.next_export = now + 600       # reintenta en 10 min
        self._save()

    def _save(self) -> None:
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(json.dumps(self.state), encoding="utf-8")
        except OSError as exc:
            log.error("compartir: no se pudo guardar el estado (%s)", exc)

    # --- importar -----------------------------------------------------------------------
    def import_now(self) -> Report | None:
        found, rejected = discover(self.shared_dir, self.machine)
        todo: dict[str, list[Export]] = {}
        for e in found:
            for db in sorted(e.use & set(self.live)):
                if self.state["imported"].get(f"{e.machine}|{db}") != e.path.name:
                    todo.setdefault(db, []).append(Export(e.machine, e.path, e.manifest, {db}))
        self.state["last_import"] = int(self.clock())
        if rejected:
            self.error = "exportaciones rechazadas: " + "; ".join(
                f"{r['machine']}: {r['problems'][0]}" for r in rejected)
        if not todo:
            return None
        now_ms = int(self.clock() * 1000)
        rep = Report(f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(now_ms / 1000))}-"
                     f"{self.machine}-{self.role}", True, self.machine, rejected=rejected,
                     exports=[{"machine": e.machine, "created_at": e.created_at,
                               "path": str(e.path)} for es in todo.values() for e in es])
        self._backup(rep, sorted(todo))
        for db, exports in sorted(todo.items()):
            exports.sort(key=lambda e: e.machine)
            lv = self.live[db]
            with lv.lock:                       # los escritores esperan; todo en una transacción
                lv.con.execute("BEGIN")
                try:
                    for ddl in LOG_DDL:
                        lv.con.execute(ddl)
                    rep.results += _merge_db(lv.con, db, exports, rep.import_id, now_ms,
                                             self.machine)
                    lv.con.execute("COMMIT")
                except BaseException:
                    lv.con.execute("ROLLBACK")
                    raise
                finally:
                    for t in TEMP_TABLES:
                        lv.con.execute(f"DROP TABLE IF EXISTS {t}")
            for e in exports:
                self.state["imported"][f"{e.machine}|{db}"] = e.path.name
        rep.write(self.data_dir)
        self.state["last_report"] = rep.import_id
        self._save()
        new_ctx = sum(r.new for r in rep.results if r.tbl in ("paper_ctx", "val_versions"))
        if new_ctx and self.on_imported is not None:
            self.on_imported()                  # recalcula los derivados sobre la unión
        return rep

    def _backup(self, rep: Report, dbs: list[str]) -> None:
        if self.backup_dir is None:
            return
        dst = self.backup_dir / f"pre-import_{rep.import_id}"
        dst.mkdir(parents=True, exist_ok=True)
        for db in dbs:
            self._copy(db, dst / db)
        rep.backup = str(dst)
        old = sorted(p for p in self.backup_dir.glob("pre-import_*") if p.is_dir())[:-3]
        for p in old:
            shutil.rmtree(p, ignore_errors=True)

    def _copy(self, db: str, dst: Path) -> None:
        lv = self.live[db]
        dst.unlink(missing_ok=True)
        if lv.copier is not None:
            lv.copier(dst)
        else:
            copy_db_hot(lv.con, lv.lock, dst)

    # --- exportar -----------------------------------------------------------------------
    def _signature(self) -> str:
        parts = []
        for db, lv in sorted(self.live.items()):
            with lv.lock:
                have = {r[0] for r in lv.con.execute(
                    "SELECT table_name FROM duckdb_tables() WHERE database_name = "
                    "current_database()").fetchall()}
                for sp in specs_of(db):
                    if sp.name in have:
                        n = lv.con.execute(f'SELECT count(*) FROM "{sp.name}"').fetchone()[0]
                        parts.append(f"{sp.name}={n}")
        return ",".join(parts)

    def export_now(self) -> Path | None:
        sig = self._signature()
        if sig == self.state.get("export_sig"):
            return None                          # nada nuevo desde la última exportación
        stage = self.data_dir / "share" / f"_stage_{self.role}"
        shutil.rmtree(stage, ignore_errors=True)
        stage.mkdir(parents=True)
        try:
            for db in self.live:
                self._copy(db, stage / db)
            out = export(stage, self.shared_dir, self.machine, dbs=tuple(sorted(self.live)),
                         part=self.role)
        finally:
            shutil.rmtree(stage, ignore_errors=True)
        prune_own(self.shared_dir, self.machine, self.role, self.keep)
        if self.transport is not None:
            self.transport.push()               # si falla, no se anota la firma: se reintenta
        self.state["export_sig"] = sig
        self.state["last_export"] = int(self.clock())
        self.state["last_export_dir"] = out.name
        return out


def make_agent(role: str, data_dir: Path, live: dict[str, Live], *, backup_dir: Path | None = None,
               on_imported: Callable[[], object] | None = None, env: dict | None = None
               ) -> ShareAgent | None:
    """El agente de este proceso, o None si no hay carpeta compartida configurada o
    `EIM_SHARE_AUTO=0`. Cadencias: `EIM_SHARE_IMPORT_S` (3600), `EIM_SHARE_EXPORT_S` (21600),
    `EIM_SHARE_KEEP` (3 exportaciones propias por tipo)."""
    e = os.environ if env is None else env
    cfg = load_config(data_dir, e)
    if not (cfg.get("shared_dir") or cfg.get("git_url")) or e.get("EIM_SHARE_AUTO", "1") == "0":
        return None
    machine = machine_id(data_dir, {"EIM_MACHINE": e.get("EIM_MACHINE") or cfg.get("machine", "")})
    transport = shared = None
    if cfg.get("git_url"):
        transport = GitTransport(cfg["git_url"], data_dir / "share_repo", machine)
        shared = transport.view
    return ShareAgent(role, data_dir, shared or Path(cfg["shared_dir"]), machine, live,
                      backup_dir=backup_dir, on_imported=on_imported, transport=transport,
                      import_every_s=float(e.get("EIM_SHARE_IMPORT_S", 3600)),
                      export_every_s=float(e.get("EIM_SHARE_EXPORT_S", 6 * 3600)),
                      keep=int(e.get("EIM_SHARE_KEEP", 3)))


async def share_loop(agent: ShareAgent, poll_s: float = 60.0, first_s: float = 120.0) -> None:
    """Bucle de fondo del proceso: cada `poll_s` mira si toca (en un hilo: no frena el bucle)."""
    await asyncio.sleep(first_s)
    while True:
        if agent.due():
            await asyncio.to_thread(agent.tick)
        await asyncio.sleep(poll_s)
