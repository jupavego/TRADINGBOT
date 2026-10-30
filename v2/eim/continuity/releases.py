"""Transporte de la copia externa (T125): la CLI `gh` sobre las versiones de un repo PRIVADO.

Una sola versión (`TAG`) anclada a un commit mínimo propio, con el mismo SHA en todos los
equipos (fecha y autor fijos): no a una rama `machine/*` de la experiencia, que se reescribe con
cada exportación (anclarla allí retendría para siempre una foto vieja de ~160 MB). Credenciales
de `gh auth login`; nunca se piden por consola.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

DEFAULT_REPO = "Santivego/eim-shared-data"
TAG = "eim-copias"
README = ("# Datos privados de EIM\n\nRamas `machine/<id>`: experiencia compartida (T61/T117).\n"
          "Versión `eim-copias`: copias completas de cada equipo (T125, `python -m "
          "eim.continuity offsite`).\nNunca código ni claves.\n")


class OffsiteError(RuntimeError):
    pass


def repo_from_env(env: dict | None = None) -> str:
    return (env if env is not None else os.environ).get("EIM_OFFSITE_REPO") or DEFAULT_REPO


class Releases:
    """Transporte con la CLI `gh` (credenciales de `gh auth login`; nunca pide nada)."""

    def __init__(self, repo: str, tag: str = TAG, *, timeout: float = 3600.0,
                 run: Callable = subprocess.run) -> None:
        self.repo, self.tag, self.timeout, self._run = repo, tag, timeout, run

    def _gh(self, *args: str, check: bool = True) -> str:
        env = {**os.environ, "GH_PROMPT_DISABLED": "1", "GIT_TERMINAL_PROMPT": "0"}
        try:
            out = self._run(["gh", *args], capture_output=True, text=True, env=env,
                            timeout=self.timeout, encoding="utf-8", errors="replace")
        except (OSError, subprocess.SubprocessError) as e:
            raise OffsiteError(f"gh {args[0]}: {e}") from e
        if check and out.returncode != 0:
            raise OffsiteError(f"gh {' '.join(args[:2])}: "
                               f"{(out.stderr or out.stdout).strip()[:300]}")
        return out.stdout

    def _anchor(self) -> None:
        """Etiqueta `TAG` sobre un commit mínimo (mismo SHA en todos los equipos)."""
        with tempfile.TemporaryDirectory() as d:
            env = {**os.environ, "GIT_AUTHOR_DATE": "2026-10-30T00:00:00Z",
                   "GIT_COMMITTER_DATE": "2026-10-30T00:00:00Z", "GIT_TERMINAL_PROMPT": "0"}
            ident = ["-c", "user.name=eim", "-c", "user.email=eim@localhost",
                     "-c", "core.autocrlf=false"]
            (Path(d) / "README.md").write_text(README, encoding="utf-8", newline="\n")
            for args in (["init", "-q"], ["add", "README.md"],
                         ["commit", "-q", "-m", "ancla de las copias completas"],
                         ["push", "-q", f"https://github.com/{self.repo}.git",
                          f"HEAD:refs/tags/{self.tag}"]):
                r = self._run(["git", *ident, *args], cwd=d, capture_output=True, text=True,
                              env=env, timeout=300)
                if r.returncode != 0:
                    raise OffsiteError(f"git {args[0]}: {(r.stderr or r.stdout).strip()[:300]}")

    def ensure(self) -> None:
        if self._gh("release", "view", self.tag, "-R", self.repo, "--json", "tagName",
                    check=False).strip():
            return
        if not self._gh("api", f"repos/{self.repo}/git/ref/tags/{self.tag}",
                        check=False).strip().startswith("{\"ref\""):
            self._anchor()
        self._gh("release", "create", self.tag, "-R", self.repo, "--verify-tag",
                 "--title", "Copias completas EIM (T125)",
                 "--notes", "Copias completas de cada equipo. No borrar a mano: "
                 "`python -m eim.continuity offsite list`.")

    def assets(self) -> dict[str, dict]:
        """{nombre: {bytes, created}}; vacío si la versión aún no existe (nadie publicó)."""
        try:
            out = self._gh("release", "view", self.tag, "-R", self.repo, "--json", "assets")
        except OffsiteError as e:
            if "release not found" in str(e):
                return {}
            raise
        return {a["name"]: {"bytes": int(a["size"]), "created": a.get("createdAt", "")}
                for a in json.loads(out or "{}").get("assets", [])}

    def upload(self, path: Path) -> None:
        self._gh("release", "upload", self.tag, str(path), "-R", self.repo, "--clobber")

    def download(self, pattern: str, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        self._gh("release", "download", self.tag, "-R", self.repo, "-p", pattern,
                 "-D", str(dest), "--clobber")

    def delete(self, name: str) -> None:
        self._gh("release", "delete-asset", self.tag, name, "-R", self.repo, "-y")
