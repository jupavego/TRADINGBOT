"""Importación de la experiencia de otras máquinas (T61).

Por defecto es un SIMULACRO: corre la misma unión sobre copias temporales de las bases y descarta
el resultado (el informe del simulacro es exactamente lo que haría `--apply`). Con `apply`:
verifica cada manifest (formato, esquema, SHA-256), hace antes una copia de seguridad local, une
cada base en UNA transacción, deja `import_log`/`share_origin`/`share_conflicts` y escribe el
informe en `data/share/`. Idempotente (importar dos veces = una) y conmutativa (A∪B = B∪A) sobre
las claves y el contenido; el estado de la máquina (kill-switch, latidos, libro simulado) y los
secretos nunca se tocan. Requiere las bases libres: detén la API y el servicio de líderes.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path

import duckdb

from eim.data.machine import FILE as MACHINE_FILE
from eim.data.share_export import ShareError, _sha256
from eim.data.share_merge import Result, merge_table
from eim.data.share_report import Report
from eim.data.share_spec import (
    DB_ORDER,
    FORMAT,
    FORMATS,
    LOG_DDL,
    SCHEMA_VERSION,
    parts_of,
    specs_of,
)
from eim.data.share_versions import merge_versions


class Export:
    def __init__(self, machine: str, path: Path, manifest: dict, use: set[str]) -> None:
        self.machine, self.path, self.manifest = machine, path, manifest
        self.use = use          # bases para las que esta es la exportación más reciente

    @property
    def created_at(self) -> str:
        return self.manifest["created_at"]


def check(path: Path, machine: str) -> tuple[dict | None, list[str]]:
    """(manifest, problemas). Con problemas la exportación entera se rechaza."""
    mf = path / "manifest.json"
    if not mf.exists():
        return None, ["falta manifest.json (¿la nube aún está sincronizando?)"]
    try:
        m = json.loads(mf.read_text(encoding="utf-8"))
        tables = m["tables"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return None, [f"manifest ilegible: {exc}"]
    problems = []
    if m.get("format") not in FORMATS:
        problems.append(f"formato {m.get('format')} no soportado (este código lee hasta el "
                        f"{FORMAT}): actualiza el código (git pull) antes de importar")
    if int(m.get("schema_version", 0)) > SCHEMA_VERSION:
        problems.append(f"esquema {m.get('schema_version')} más nuevo que el local "
                        f"({SCHEMA_VERSION}): actualiza el código (git pull) antes de importar")
    if m.get("machine") != machine:
        problems.append(f"el manifest dice máquina {m.get('machine')!r}, la carpeta {machine!r}")
    try:
        parts = [pt for meta in tables.values() for pt in parts_of(meta)]
    except (KeyError, TypeError) as exc:
        return m, [*problems, f"manifest ilegible: falta {exc}"]
    for pt in parts:
        f = path / pt["file"]
        if not f.exists():
            problems.append(f"falta {pt['file']}")
        elif _sha256(f) != pt["sha256"]:
            problems.append(f"hash distinto: {pt['file']} (manifest alterado o archivo dañado)")
    return m, problems


def files(path: Path, meta: dict) -> list[Path]:
    """Archivos Parquet de una tabla exportada (una o varias partes)."""
    return [path / pt["file"] for pt in parts_of(meta)]


def discover(shared_dir: Path, own: str, only: set[str] | None = None
             ) -> tuple[list[Export], list[dict]]:
    """Por cada OTRA máquina, la exportación más reciente de cada base (una exportación completa
    las cubre todas; las parciales de la API y del servicio de líderes, cada una las suyas).
    Las inválidas van a `rechazadas` y se sigue con la anterior válida."""
    found, rejected = [], []
    dirs = sorted(p for p in shared_dir.iterdir() if p.is_dir()) if shared_dir.exists() else []
    for mdir in dirs:
        if mdir.name == own or (only and mdir.name not in only):
            continue
        covered: set[str] = set()
        stamps = sorted((p for p in mdir.iterdir() if p.is_dir() and not p.name.startswith(".")),
                        reverse=True)
        for p in stamps[:8]:
            m, problems = check(p, mdir.name)
            if problems:
                rejected.append({"machine": mdir.name, "path": str(p), "problems": problems})
                continue
            dbs = set(m.get("dbs") or {t["db"] for t in m["tables"].values()})
            if dbs - covered:
                found.append(Export(mdir.name, p, m, dbs - covered))
                covered |= dbs
            if covered >= set(DB_ORDER):
                break
    return found, rejected


def ensure_schema(db: str, path: Path) -> None:
    """Crea/migra las tablas con las propias clases de almacén (una sola fuente del DDL)."""
    try:
        if db == "reports.duckdb":
            from eim.api.forecast_db import ForecastStore
            from eim.api.reports_db import ReportStore
            from eim.execution.sim_ledger import SimLedger
            rs = ReportStore(path)
            ForecastStore(*rs.connection)
            SimLedger(*rs.connection)
            rs.close()
        elif db == "paper.duckdb":
            from eim.data.paper_store import PaperStore
            from eim.data.validation_store import ValidationStore
            ps = PaperStore(path)
            ValidationStore(ps)
            ps.close()
        else:
            from eim.data.leader_store import LeaderStore
            LeaderStore(path).close()
    except duckdb.IOException as exc:
        raise ShareError(f"{db} está en uso: detén la API y el servicio de líderes "
                         f"({exc})") from exc


def _copy_db(src: Path, dst_dir: Path) -> bool:
    ok = False
    for suffix in ("", ".wal"):
        s = src.with_name(src.name + suffix)
        if s.exists():
            try:
                shutil.copy2(s, dst_dir / s.name)
            except PermissionError as exc:
                raise ShareError(f"{src.name} está en uso: detén la API y el servicio de "
                                 f"líderes ({exc})") from exc
            ok = True
    return ok


def _merge_db(con, db: str, exports: list[Export], import_id: str, now_ms: int, by: str
              ) -> list[Result]:
    out: list[Result] = []
    for e in exports:
        if db not in e.use:
            continue
        tabs = e.manifest["tables"]
        for sp in specs_of(db):
            if sp.name not in tabs or sp.name == "val_windows":
                continue
            if sp.kind == "versions":
                if "val_windows" not in tabs:
                    continue
                v, w = merge_versions(con, files(e.path, tabs["val_versions"]),
                                      files(e.path, tabs["val_windows"]), e.machine,
                                      import_id, now_ms)
                out += [Result("val_versions", e.machine, v.new, v.dup, 0, v.incompatible),
                        Result("val_windows", e.machine, w.new, w.dup, 0, w.incompatible)]
                continue
            out.append(merge_table(con, sp, files(e.path, tabs[sp.name]),
                                   tabs[sp.name]["columns"], e.machine, import_id))
    for r in out:
        e = next(x for x in exports if x.machine == r.src and db in x.use)
        con.execute("INSERT INTO import_log VALUES (?,?,?,?,?,?,?,?,?,?)",
                    [import_id, now_ms, r.tbl, r.src, e.created_at, r.new, r.dup, r.conflict,
                     r.incompatible, by])
    return out


def import_all(data_dir: Path, shared_dir: Path, machine: str, *, apply: bool = False,
               backup_dir: Path | None = None, only: set[str] | None = None,
               now_ms: int | None = None) -> Report:
    now_ms = now_ms or int(time.time() * 1000)
    exports, rejected = discover(shared_dir, machine, only)
    rep = Report(f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(now_ms / 1000))}-{machine}",
                 apply, machine, [{"machine": e.machine, "created_at": e.created_at,
                                   "path": str(e.path)} for e in exports], rejected=rejected)
    exports.sort(key=lambda e: e.machine)           # el orden no cambia el resultado
    if rejected and apply:
        rep.notes.append("Hay exportaciones rechazadas: se importó solo lo válido.")
    with tempfile.TemporaryDirectory(prefix="eim_share_") as tmp:
        work = data_dir
        if apply:
            if backup_dir is not None:
                dst = backup_dir / f"pre-import_{rep.import_id}"
                dst.mkdir(parents=True, exist_ok=True)
                copied = [_copy_db(data_dir / db, dst) for db in DB_ORDER
                          if (data_dir / db).exists()]
                rep.backup = str(dst) if any(copied) else None
        else:
            work = Path(tmp)
            for db in DB_ORDER:
                if (data_dir / db).exists():
                    _copy_db(data_dir / db, work)
            mid = data_dir / MACHINE_FILE
            if mid.exists():
                shutil.copy2(mid, work / MACHINE_FILE)
        for db in DB_ORDER:
            mine = [e for e in exports if db in e.use and any(
                s.name in e.manifest["tables"] for s in specs_of(db))]
            if not mine:
                continue
            ensure_schema(db, work / db)
            con = duckdb.connect(str(work / db))
            try:
                for ddl in LOG_DDL:
                    con.execute(ddl)
                con.execute("BEGIN")
                try:
                    rep.results += _merge_db(con, db, mine, rep.import_id, now_ms, machine)
                    con.execute("COMMIT")
                except BaseException:
                    con.execute("ROLLBACK")
                    raise
            finally:
                con.close()
    if apply:
        rep.write(data_dir)
    return rep
