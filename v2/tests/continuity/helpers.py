"""Ayudas de las pruebas de continuidad (T125): un «GitHub» de versiones en una carpeta, un
repo con remoto `--bare` local y copias de T115 pequeñas. Sin red."""

from __future__ import annotations

import fnmatch
import shutil
import subprocess
from pathlib import Path

from eim.data import backup as B
from tests.data.backup_helpers import T0, data


class FakeReleases:
    """Mismo contrato que `eim.continuity.releases.Releases`, sobre una carpeta."""

    repo = "prueba/datos"

    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.uploads: list[str] = []
        self.deleted: list[str] = []
        self.created: dict[str, str] = {}

    def ensure(self) -> None:
        pass

    def assets(self) -> dict[str, dict]:
        return {p.name: {"bytes": p.stat().st_size,
                         "created": self.created.get(p.name, "2099-01-01T00:00:00Z")}
                for p in self.root.iterdir()}

    def upload(self, path: Path) -> None:
        shutil.copy2(path, self.root / path.name)
        self.uploads.append(path.name)

    def download(self, pattern: str, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        for p in self.root.iterdir():
            if fnmatch.fnmatch(p.name, pattern):
                shutil.copy2(p, dest / p.name)

    def delete(self, name: str) -> None:
        (self.root / name).unlink()
        self.deleted.append(name)


def backup(tmp_path: Path, n: int = 0, sub: str = "src") -> tuple[Path, Path]:
    """(carpeta de datos, copia completa) con las tres bases de `backup_helpers.data`."""
    d = data(tmp_path / sub) if not (tmp_path / sub / "data").exists() else tmp_path / sub / "data"
    out = B.create(d, tmp_path / sub / "backups", clock=lambda: T0 + n * 3600, keep=0)
    return d, out


def run(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd,
                          check=True, capture_output=True, text=True).stdout


def repo(tmp_path: Path) -> tuple[Path, Path]:
    """(clon con `v2/` y `PLAN/`, remoto `--bare`). Un commit ya subido a `origin/main`."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    clone = tmp_path / "clon"
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True,
                   capture_output=True)
    (clone / "v2").mkdir()
    (clone / "v2" / "x.py").write_text("x = 1\n", encoding="utf-8")
    (clone / "PLAN").mkdir()
    (clone / "PLAN" / "STATUS.md").write_text(
        "| ID | Tarea | Depende de | Estado | Notas |\n|---|---|---|---|---|\n"
        "| T01 | Cimientos | — | ☑ | hecho |\n| T02 | Datos | T01 | ◐ | a medias |\n"
        "| T03 | Riesgo | T02 | ☐ |  |\n", encoding="utf-8")
    run("checkout", "-q", "-b", "main", cwd=clone)
    run("add", "-A", cwd=clone)
    run("commit", "-q", "-m", "inicio", cwd=clone)
    run("push", "-q", "-u", "origin", "main", cwd=clone)
    return clone, origin
