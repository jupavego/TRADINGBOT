"""Espejo en vivo de la cantera entre equipos (pedido del usuario, 2026-11-20). Solo lectura.

La cantera corre en un solo equipo (`juanpablo-cpu`, `EIM_NURSERY=1`): dos canteras tendrían dos
relojes para el mismo pre-registro (T170). Para ver sus progresos desde otro equipo:

- **El equipo que la corre publica**: tras cada cálculo nuevo, como mucho cada
  `EIM_NURSERY_MIRROR_S` segundos (900 por defecto) y al menos cada hora, la foto de lo que muestra
  la pestaña (balance de ganadas y perdidas, capital por agente, escalafón y latido) va a la rama
  `cantera/espejo` del repo privado de la experiencia compartida (`EIM_NURSERY_MIRROR_URL`, por
  defecto el de T117/T196). Un commit raíz y `push --force`: el servidor solo guarda la última foto.
- **Los demás leen**: cada 5 min traen esa rama y la API la sirve en `GET /v2/nursery` con
  `mirror` (equipo de origen, hora de publicación). No calculan nada ni tocan ningún libro.

`EIM_NURSERY_MIRROR=0` lo apaga. Credenciales: las del git del usuario (gestor de credenciales de
Windows / `gh auth`), nunca por consola. Un fallo (sin red, sin permiso) se anota en
`mirror.error` y se reintenta: nunca tumba la API ni la cantera.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

from eim.data.machine import machine_id

DEFAULT_URL = "https://github.com/Santivego/eim-shared-data.git"
BRANCH = "cantera/espejo"
FILE = "cantera.json"
PUBLISH_S = 900.0             # como mucho una foto cada 15 min (una vela de 15 m)
REFRESH_S = 3600.0            # y al menos una por hora, aunque no haya cálculo nuevo (latido)
READ_S = 300.0                # el lector mira cada 5 min
KEEP = ("mode", "variant", "label", "live", "prereg", "balance", "panel", "reason")
_log = logging.getLogger("eim.nursery.mirror")


class MirrorError(RuntimeError):
    pass


def snapshot(payload: dict, machine: str, now_ms: int) -> dict:
    """Lo que viaja: lo que pinta la pestaña, sin las curvas por cuenta ni los eventos."""
    out = {k: payload[k] for k in KEEP if k in payload}
    out["mirror"] = {"machine": machine, "published_ms": int(now_ms)}
    return out


def _rmtree(path: Path) -> None:
    def onexc(func, p, _exc):            # Windows: los objetos de git son de solo lectura
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if path.exists():
        if sys.version_info >= (3, 12):
            shutil.rmtree(path, onexc=onexc)
        else:
            shutil.rmtree(path, onerror=onexc)


class MirrorGit:
    """Rama de una sola foto. Cada operación parte de un repo vacío: nada se acumula en disco."""

    def __init__(self, url: str, base: Path, *, timeout: float = 120.0) -> None:
        self.url, self.base, self.timeout = url, Path(base), timeout

    def _git(self, cwd: Path, *args: str) -> str:
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
        cmd = ["git", "-c", "user.name=eim-cantera", "-c", "user.email=eim@localhost",
               "-c", "core.autocrlf=false", "-c", "gc.auto=0", *args]
        try:
            out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env,
                                 timeout=self.timeout, encoding="utf-8", errors="replace")
        except (OSError, subprocess.SubprocessError) as exc:
            raise MirrorError(f"git {args[0]}: {exc}") from exc
        if out.returncode != 0:
            msg = (out.stderr or out.stdout).strip()[:300]
            raise MirrorError(f"git {' '.join(args[:2])}: {msg}")
        return out.stdout

    def _fresh(self, name: str) -> Path:
        d = self.base / name
        _rmtree(d)
        d.mkdir(parents=True, exist_ok=True)
        self._git(d, "init", "-q")
        self._git(d, "remote", "add", "origin", self.url)
        return d

    def publish(self, data: dict) -> None:
        d = self._fresh("pub")
        (d / FILE).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                              encoding="utf-8")
        self._git(d, "add", FILE)
        self._git(d, "commit", "-q", "-m", f"espejo de la cantera {data['mirror']['machine']}")
        self._git(d, "push", "-q", "--force", "origin", f"HEAD:refs/heads/{BRANCH}")

    def fetch(self) -> dict:
        d = self._fresh("read")
        self._git(d, "fetch", "-q", "--depth", "1", "origin",
                  f"+refs/heads/{BRANCH}:refs/remotes/origin/espejo")
        return json.loads(self._git(d, "show", f"origin/espejo:{FILE}"))


class NurseryMirror:
    """`publish` en el equipo que corre la cantera; `read` en los demás."""

    def __init__(self, role: str, git: MirrorGit, machine: str, *, desk=None,
                 payload=None, publish_s: float = PUBLISH_S) -> None:
        self.role, self.git, self.machine, self.desk = role, git, machine, desk
        self.payload, self.publish_s = payload, publish_s
        self.latest: dict | None = None
        self.error = ""
        self.last_ok_ms: int | None = None
        self._last_obj: object | None = None
        self._last_pub = 0.0

    def status(self) -> dict:
        return {"role": self.role, "machine": self.machine, "branch": BRANCH,
                "error": self.error, "last_ok_ms": self.last_ok_ms}

    def tick(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        try:
            if self.role == "read":
                self.latest = self.git.fetch()
            else:
                summary = self.desk.summary() if self.desk is not None else None
                if summary is None:
                    return
                fresh = summary is not self._last_obj and now - self._last_pub >= self.publish_s
                if not (fresh or now - self._last_pub >= REFRESH_S):
                    return
                self.git.publish(snapshot(self.payload(), self.machine, int(now * 1000)))
                self._last_obj, self._last_pub = summary, now
            self.error, self.last_ok_ms = "", int(now * 1000)
        except (MirrorError, ValueError, OSError) as exc:
            self.error = str(exc)[:300]
            _log.warning("espejo de la cantera (%s): %s", self.role, self.error)

    async def loop(self, first_s: float = 60.0) -> None:
        await asyncio.sleep(first_s)
        while True:
            try:
                await asyncio.to_thread(self.tick)
            except Exception as exc:  # noqa: BLE001 — el espejo nunca tumba la API
                self.error = f"{type(exc).__name__}: {exc}"[:300]
            await asyncio.sleep(READ_S if self.role == "read" else 60.0)


def make_mirror(enabled: bool, data_dir: Path, desk=None, payload=None,
                env: dict | None = None) -> NurseryMirror | None:
    """Con la cantera encendida aquí, publica; apagada, lee. None si el espejo está apagado."""
    if not enabled:
        return None
    e = os.environ if env is None else env
    url = e.get("EIM_NURSERY_MIRROR_URL") or DEFAULT_URL
    git = MirrorGit(url, Path(data_dir) / "nursery_mirror")
    try:
        machine = machine_id(data_dir, e)
    except ValueError:
        machine = "desconocido"
    if desk is not None:
        return NurseryMirror("publish", git, machine, desk=desk, payload=payload,
                             publish_s=float(e.get("EIM_NURSERY_MIRROR_S", PUBLISH_S)))
    return NurseryMirror("read", git, machine)
