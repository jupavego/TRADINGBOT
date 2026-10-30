"""Transporte por git de la experiencia compartida (T61): un repo PRIVADO aparte, no el del código.

Misma disposición que la carpeta de nube (`<máquina>/<fecha>/…`), pero la «nube» es GitHub:
- `view/<mi_id>` es un clon de MI rama `machine/<mi_id>`: ahí escribe la exportación; al publicar
  se hace un commit raíz único y `push --force` a MI rama (nadie más la toca, así que no hay
  conflictos y la historia no crece: el servidor solo guarda la última foto);
- `view/<otra>` es un clon superficial (`--depth 1`) de la rama `machine/<otra>`, que se actualiza
  antes de importar.
`view/` es lo que ve el importador como carpeta compartida. Dos procesos (API y servicio de líderes)
comparten el clon propio: un candado de archivo serializa pull/push. Las credenciales son las del
git del usuario (gestor de credenciales de Windows / `gh auth`); nunca se piden por consola.
Rutas de archivos de más de 90 MB se rechazan (GitHub corta en 100 MB).
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import time
from pathlib import Path

PREFIX = "machine/"
MAX_FILE = 90 * 1024 * 1024
IGNORE = ".*.partial/\n_*/\n"
LOCK_STALE_S = 900


class GitError(RuntimeError):
    pass


class GitTransport:
    def __init__(self, url: str, base: Path, machine: str, *, timeout: float = 300.0) -> None:
        self.url, self.base, self.machine, self.timeout = url, Path(base), machine, timeout
        self.view = self.base / "view"
        self.own = self.view / machine
        self.branch = PREFIX + machine

    # --- git -----------------------------------------------------------------------------
    def _git(self, cwd: Path | None, *args: str, check: bool = True) -> str:
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
        cmd = ["git", "-c", f"user.name=eim-{self.machine}", "-c", "user.email=eim@localhost",
               "-c", "core.autocrlf=false", "-c", "gc.auto=0",
               "-c", "core.longpaths=true", *args]     # T117: Windows corta en 260 caracteres
        try:
            out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env,
                                 timeout=self.timeout, encoding="utf-8", errors="replace")
        except (OSError, subprocess.SubprocessError) as exc:
            raise GitError(f"git {args[0]}: {exc}") from exc
        if check and out.returncode != 0:
            raise GitError(f"git {' '.join(args[:2])}: {(out.stderr or out.stdout).strip()[:300]}")
        return out.stdout

    @contextlib.contextmanager
    def lock(self, wait_s: float = 180.0):
        """Candado entre procesos (API y servicio de líderes comparten el clon propio)."""
        self.base.mkdir(parents=True, exist_ok=True)
        path = self.base / "git.lock"
        end = time.monotonic() + wait_s
        while True:
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                break
            except FileExistsError:
                with contextlib.suppress(OSError):
                    if time.time() - path.stat().st_mtime > LOCK_STALE_S:
                        path.unlink()
                        continue
                if time.monotonic() > end:
                    raise GitError("otro proceso está sincronizando (candado git.lock)") from None
                time.sleep(0.5)
        try:
            yield
        finally:
            path.unlink(missing_ok=True)

    def remote_heads(self) -> dict[str, str]:
        """{máquina: sha} de las ramas `machine/*` del repo remoto."""
        out = self._git(None, "ls-remote", "--heads", self.url, PREFIX + "*")
        heads = {}
        for line in out.splitlines():
            sha, _, ref = line.partition("\t")
            heads[ref.removeprefix("refs/heads/" + PREFIX)] = sha
        return heads

    # --- ciclo ---------------------------------------------------------------------------
    def _ensure_own(self, heads: dict[str, str]) -> None:
        if (self.own / ".git").exists():
            return
        self.own.mkdir(parents=True, exist_ok=True)
        self._git(self.own, "init", "-q")
        self._git(self.own, "remote", "add", "origin", self.url)
        if self.machine in heads:       # equipo reinstalado: recupera sus propias exportaciones
            self._git(self.own, "fetch", "-q", "--depth", "1", "origin", self.branch)
            self._git(self.own, "checkout", "-q", "-B", self.branch, "FETCH_HEAD")
        else:
            self._git(self.own, "checkout", "-q", "--orphan", self.branch)
        (self.own / ".gitignore").write_text(IGNORE, encoding="utf-8")

    def prepare_own(self) -> None:
        """Solo el clon de MI rama (T125: exportar sin bajar las ramas de los demás)."""
        with self.lock():
            self._ensure_own(self.remote_heads())

    def pull(self) -> list[str]:
        """Prepara `view/` y trae las ramas nuevas de las demás máquinas. Devuelve las
        máquinas cuya foto cambió."""
        changed = []
        with self.lock():
            heads = self.remote_heads()
            self._ensure_own(heads)
            for m, sha in sorted(heads.items()):
                if m == self.machine:
                    continue
                d = self.view / m
                if not (d / ".git").exists():
                    self._git(None, "clone", "-q", "--depth", "1", "--branch", PREFIX + m,
                              self.url, str(d))
                    changed.append(m)
                elif self._git(d, "rev-parse", "HEAD").strip() != sha:
                    self._git(d, "fetch", "-q", "--depth", "1", "origin", PREFIX + m)
                    self._git(d, "reset", "-q", "--hard", "FETCH_HEAD")
                    self._git(d, "clean", "-qfd")
                    changed.append(m)
        return changed

    def push(self) -> bool:
        """Publica MI rama como un único commit raíz. False si no hay nada nuevo."""
        with self.lock():
            self._ensure_own({})
            for p in self.own.rglob("*"):
                if ".git" not in p.parts and p.is_file() and p.stat().st_size > MAX_FILE:
                    raise GitError(f"{p.name} pesa más de 90 MB: GitHub lo rechazaría")
            self._git(self.own, "add", "-A")
            has_head = self._git(self.own, "rev-parse", "--verify", "-q", "HEAD",
                                 check=False).strip()
            if has_head and not self._git(self.own, "status", "--porcelain").strip():
                return False
            msg = f"exportación de {self.machine}"
            if has_head:
                self._git(self.own, "commit", "-q", "--amend", "-m", msg)
            else:
                self._git(self.own, "commit", "-q", "-m", msg)
            self._git(self.own, "push", "-q", "--force", "origin", f"HEAD:refs/heads/{self.branch}")
            self._git(self.own, "reflog", "expire", "--expire=now", "--all", check=False)
            self._git(self.own, "gc", "-q", "--prune=now", check=False)
            return True


def available() -> bool:
    try:
        return subprocess.run(["git", "--version"], capture_output=True, timeout=10
                              ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
