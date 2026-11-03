"""Copia externa (T125): la copia completa de T115 fuera del disco del equipo.

Destino: las versiones (*releases*) de un repo PRIVADO de GitHub, por defecto el mismo de la
experiencia compartida (`Santivego/eim-shared-data`, decisión de T117; `EIM_OFFSITE_REPO`).
Una sola versión, `eim-copias`, anclada a un commit mínimo propio (no a una rama `machine/*`,
que se reescribe), guarda los archivos de todas las copias de todos los equipos:
`<máquina>__<copia>.zip.NNN` (partes ≤ `PART_BYTES`, GitHub corta en 2 GiB) y, AL FINAL,
`<máquina>__<copia>.meta.json` (SHA-256 de cada parte y del zip, filas por tabla de cada
base, commit, equipo). Sin `meta` no hay copia: una subida interrumpida nunca se ve completa.

Subir la misma copia dos veces no duplica nada (`push` la salta). Una subida cortada retoma
desde la última parte subida (T127): con `work`, el empaquetado queda en
`<work>/pack-<máquina>__<copia>/` con `pack.json` (partes, SHA-256 y cuáles ya subieron) hasta
que sube el `meta`; los extras quedan los del primer intento. Solo se retoma la MISMA copia:
si llega otra más nueva, su empaquetado sustituye al anterior. Cada parte se reintenta
(`RETRIES`): la pausa de la cola de trabajos puede cortar una conexión a medias. `pull` verifica
cada parte, el zip y después la copia entera (`backup_restore.verify`). Cada equipo solo poda
lo suyo.
Nunca viajan claves: la copia de T115 no las tiene y los extras tampoco (`extras.py`).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from eim.continuity.releases import DEFAULT_REPO, TAG, OffsiteError, Releases, repo_from_env
from eim.data.backup_restore import read_manifest, verify

__all__ = ["DEFAULT_REPO", "SEP", "TAG", "OffsiteError", "Releases", "RemoteCopy", "pack",
           "prune", "pull", "push", "remote_copies", "repo_from_env"]

SEP = "__"
FORMAT = 1
PART_BYTES = 256 * 1024 * 1024
BLOCK = 8 * 1024 * 1024
ORPHAN_S = 86_400.0                 # partes sin `meta` más viejas: subida abandonada
RETRIES, RETRY_WAIT_S = 3, (20.0, 60.0)


def base_name(machine: str, backup: str) -> str:
    return f"{machine}{SEP}{backup}"


def file_sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while chunk := f.read(BLOCK):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class RemoteCopy:
    machine: str
    backup: str
    meta: dict
    complete: bool
    missing: list[str]

    @property
    def rows(self) -> dict[str, dict[str, int]]:
        return {db: d.get("tables", {}) for db, d in self.meta.get("dbs", {}).items()}


def pack(backup: Path, extras: Path | None, work: Path, base: str,
         part_bytes: int = PART_BYTES) -> tuple[list[dict], str, int]:
    """Comprime la copia (`copia/…`) y los extras (`extras/…`) y la trocea. Devuelve
    (partes con su SHA-256, SHA-256 del zip, bytes del zip)."""
    work.mkdir(parents=True, exist_ok=True)
    zpath = work / f"{base}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for prefix, root in (("copia", backup), ("extras", extras)):
            for p in sorted(root.rglob("*")) if root else []:
                if p.is_file():
                    z.write(p, f"{prefix}/{p.relative_to(root).as_posix()}")
    whole, parts, n = hashlib.sha256(), [], 0
    with zpath.open("rb") as src:
        while True:
            name = f"{base}.zip.{n:03d}"
            h, size = hashlib.sha256(), 0
            with (work / name).open("wb") as dst:
                while size < part_bytes and (chunk := src.read(min(BLOCK, part_bytes - size))):
                    dst.write(chunk)
                    h.update(chunk)
                    whole.update(chunk)
                    size += len(chunk)
            if not size:
                (work / name).unlink()
                break
            parts.append({"name": name, "bytes": size, "sha256": h.hexdigest()})
            n += 1
    zbytes = zpath.stat().st_size
    zpath.unlink()
    return parts, whole.hexdigest(), zbytes


def remote_copies(t: Releases, assets: dict | None = None) -> list[RemoteCopy]:
    assets = t.assets() if assets is None else assets
    metas = [n for n in assets if n.endswith(".meta.json")]
    if not metas:
        return []
    out = []
    with tempfile.TemporaryDirectory() as d:
        t.download("*.meta.json", Path(d))
        for name in sorted(metas):
            try:
                meta = json.loads((Path(d) / name).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            missing = [p["name"] for p in meta.get("parts", [])
                       if assets.get(p["name"], {}).get("bytes") != p["bytes"]]
            out.append(RemoteCopy(meta.get("machine", "?"), meta.get("backup", "?"), meta,
                                  not missing and meta.get("format") == FORMAT, missing))
    return sorted(out, key=lambda c: (c.machine, c.backup))


def _load_pack(d: Path) -> dict | None:
    """El empaquetado de un intento anterior, si sigue entero (cada parte, con su tamaño)."""
    try:
        pk = json.loads((d / "pack.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    whole = all((d / p["name"]).is_file() and (d / p["name"]).stat().st_size == p["bytes"]
                for p in pk.get("parts", []))
    return pk if whole and pk.get("parts") else None


def _save_pack(d: Path, pk: dict) -> None:
    (d / "pack.json.tmp").write_text(json.dumps(pk, ensure_ascii=False), encoding="utf-8")
    os.replace(d / "pack.json.tmp", d / "pack.json")


def _upload(t: Releases, path: Path, sleep: Callable[[float], None]) -> None:
    for i in range(RETRIES):
        try:
            t.upload(path)
            return
        except OffsiteError:
            if i == RETRIES - 1:
                raise
            sleep(RETRY_WAIT_S[min(i, len(RETRY_WAIT_S) - 1)])


def push(t: Releases, backup: Path, machine: str, *, extras: Path | None = None,
         info: dict | None = None, work: Path | None = None,
         part_bytes: int = PART_BYTES, sleep: Callable[[float], None] = time.sleep) -> dict:
    """Sube la copia (si no estaba ya completa). Devuelve su `meta` con `skipped` y
    `resumed_parts` (partes que ya había subido un intento anterior)."""
    m = read_manifest(backup)
    if m is None or (problems := verify(backup)):
        raise OffsiteError(f"{backup.name} no es una copia íntegra: "
                           f"{'falta manifest.json' if m is None else '; '.join(problems)}")
    t.ensure()
    base = base_name(machine, backup.name)
    assets = t.assets()
    for c in remote_copies(t, assets):
        if c.machine == machine and c.backup == backup.name and c.complete:
            return {**c.meta, "skipped": True}
    now = datetime.now(UTC)
    if work:
        work.mkdir(parents=True, exist_ok=True)
        for old in [*work.glob(f"pack-{machine}{SEP}*"), *work.glob(".offsite-*")]:
            if old.name != f"pack-{base}":                 # de copias o versiones anteriores
                shutil.rmtree(old, ignore_errors=True)
        tmp = work / f"pack-{base}"
        pk = _load_pack(tmp)
    else:
        tmp, pk = Path(tempfile.mkdtemp(prefix="eim-offsite-")), None
    try:
        if pk is None:
            shutil.rmtree(tmp, ignore_errors=True)
            parts, zsha, zbytes = pack(backup, extras, tmp, base, part_bytes)
            pk = {"parts": parts, "zip_sha256": zsha, "zip_bytes": zbytes, "uploaded": [],
                  "extras": sorted(p.relative_to(extras).as_posix() for p in extras.rglob("*")
                                   if p.is_file()) if extras else []}
            _save_pack(tmp, pk)
        resumed = 0
        for p in pk["parts"]:
            if p["name"] in pk["uploaded"] and assets.get(p["name"], {}).get("bytes") == p["bytes"]:
                resumed += 1                                    # la subió un intento anterior
                continue
            _upload(t, tmp / p["name"], sleep)
            pk["uploaded"] = sorted({*pk["uploaded"], p["name"]})
            _save_pack(tmp, pk)
        meta = {"format": FORMAT, "machine": machine, "backup": backup.name,
                "created_at": m.get("created_at"), "published_at": now.isoformat(),
                "git_commit": m.get("git_commit"), "dbs": m.get("dbs", {}),
                "absent": m.get("absent", {}),
                "backup_bytes": sum(f["bytes"] for f in m.get("files", {}).values()),
                "zip_bytes": pk["zip_bytes"], "zip_sha256": pk["zip_sha256"],
                "parts": pk["parts"], "extras": pk["extras"], **(info or {})}
        mp = tmp / f"{base}.meta.json"
        mp.write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
        _upload(t, mp, sleep)
    except BaseException:
        if not work:                     # sin `work` no hay punto de control que guardar
            shutil.rmtree(tmp, ignore_errors=True)
        raise
    shutil.rmtree(tmp, ignore_errors=True)
    return {**meta, "skipped": False, "resumed_parts": resumed}


def _safe_extract(z: zipfile.ZipFile, dest: Path) -> None:
    for n in z.namelist():
        p = Path(n)
        if p.is_absolute() or ".." in p.parts or p.parts[0] not in ("copia", "extras"):
            raise OffsiteError(f"ruta no permitida en el zip: {n}")
    z.extractall(dest)


def pull(t: Releases, copy: RemoteCopy, dest_root: Path) -> Path:
    """Descarga, verifica y deja la copia en `dest_root/remote/<máquina>/<copia>/` (y los
    extras al lado, en `<copia>.extras/`). Lista para `python -m eim.data.backup restore`."""
    if not copy.complete:
        raise OffsiteError(f"copia remota incompleta (faltan {', '.join(copy.missing)})")
    out = dest_root / "remote" / copy.machine / copy.backup
    if out.exists() and not verify(out):
        return out
    tmp = out.parent / f".{copy.backup}.partial"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        t.download(f"{base_name(copy.machine, copy.backup)}.zip.*", tmp)
        zpath, whole = tmp / "copia.zip", hashlib.sha256()
        with zpath.open("wb") as dst:
            for p in copy.meta["parts"]:
                f = tmp / p["name"]
                if not f.exists() or file_sha(f) != p["sha256"]:
                    raise OffsiteError(f"parte dañada o ausente: {p['name']}")
                with f.open("rb") as src:
                    while chunk := src.read(BLOCK):
                        dst.write(chunk)
                        whole.update(chunk)
                f.unlink()
        if whole.hexdigest() != copy.meta["zip_sha256"]:
            raise OffsiteError("el zip reensamblado no coincide con su SHA-256")
        with zipfile.ZipFile(zpath) as z:
            _safe_extract(z, tmp)
        zpath.unlink()
        if problems := verify(tmp / "copia"):
            raise OffsiteError("copia descargada no íntegra: " + "; ".join(problems))
        shutil.rmtree(out, ignore_errors=True)
        (tmp / "copia").replace(out)
        if (tmp / "extras").exists():
            ex = out.parent / f"{copy.backup}.extras"
            shutil.rmtree(ex, ignore_errors=True)
            (tmp / "extras").replace(ex)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def prune(t: Releases, machine: str, keep: int, now_s: float | None = None) -> list[str]:
    """Deja las `keep` copias completas más recientes de ESTE equipo (nunca toca las de otro)
    y borra partes huérfanas propias de más de un día. Primero el `meta` (la copia deja de
    verse) y después sus partes."""
    if keep <= 0:
        return []
    assets = t.assets()
    mine = [c for c in remote_copies(t, assets) if c.machine == machine]
    done = [c for c in mine if c.complete]
    gone: list[str] = []
    for c in done[:-keep]:
        names = [f"{base_name(machine, c.backup)}.meta.json",
                 *(p["name"] for p in c.meta.get("parts", []))]
        for n in names:
            if n in assets:
                t.delete(n)
                gone.append(n)
    known = {base_name(machine, c.backup) for c in mine}
    now = datetime.now(UTC).timestamp() if now_s is None else now_s
    for n, a in assets.items():
        stem = n.split(".zip.")[0]
        if not n.startswith(machine + SEP) or ".zip." not in n or stem in known or n in gone:
            continue
        try:
            age = now - datetime.fromisoformat(a["created"].replace("Z", "+00:00")).timestamp()
        except (KeyError, ValueError):
            continue
        if age > ORPHAN_S:
            t.delete(n)
            gone.append(n)
    return gone
