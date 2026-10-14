"""Canales de aviso locales: registro estructurado (JSON por líneas) y notificación de Windows.

Sin cuentas ni credenciales: la notificación usa un globo de la bandeja del sistema mediante
PowerShell (System.Windows.Forms), lanzado en segundo plano para no bloquear el ciclo.
`EIM_NOTIFY=0` la desactiva; fuera de Windows no hace nada.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from eim.operation.alerts import CRITICAL, WARN, Alert

_PS = """
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$n = New-Object System.Windows.Forms.NotifyIcon
$n.Icon = [System.Drawing.SystemIcons]::{icon}
$n.BalloonTipTitle = {title}
$n.BalloonTipText = {text}
$n.Visible = $true
$n.ShowBalloonTip(10000)
Start-Sleep -Seconds 12
$n.Dispose()
"""


def _ps_str(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def toast_script(a: Alert) -> str:
    icon = {CRITICAL: "Error", WARN: "Warning"}.get(a.level, "Information")
    title = ("EIM · " + a.title)[:63]
    return _PS.format(icon=icon, title=_ps_str(title), text=_ps_str((a.detail or a.title)[:250]))


class WindowsToast:
    """Aviso de escritorio. `min_level`: no se notifican avisos por debajo (los «resuelta»
    sí, para saber que una crítica terminó)."""

    def __init__(self, enabled: bool | None = None,
                 spawn: Callable[[list[str]], object] | None = None) -> None:
        env = os.environ.get("EIM_NOTIFY", "1") != "0"
        self.enabled = (sys.platform == "win32" and env) if enabled is None else enabled
        self._spawn = spawn or (lambda args: subprocess.Popen(  # noqa: S603 - comando fijo
            args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)))

    def __call__(self, a: Alert) -> None:
        if not self.enabled or (a.level not in (WARN, CRITICAL) and not a.resolved):
            return
        code = base64.b64encode(toast_script(a).encode("utf-16-le")).decode()
        self._spawn(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", code])


class JsonLog:
    """Registro estructurado: un archivo JSONL por día UTC en `root` (rotación natural)."""

    def __init__(self, root: str | Path, clock: Callable[[], int] | None = None,
                 echo: bool = False) -> None:
        self.root = Path(root)
        self._clock = clock or (lambda: int(time.time() * 1000))
        self._lock = threading.Lock()
        self._echo = echo

    def path_for(self, t: int) -> Path:
        return self.root / f"op-{time.strftime('%Y-%m-%d', time.gmtime(t / 1000))}.jsonl"

    def write(self, event: str, level: str = "info", **fields) -> dict:
        t = self._clock()
        row = {"t": t, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t / 1000)),
               "level": level, "event": event, **fields}
        line = json.dumps(row, ensure_ascii=False, default=str)
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            with self.path_for(t).open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        if self._echo:
            print(line, flush=True)
        return row

    def alert_sink(self, a: Alert) -> None:
        fields = a.to_json()
        self.write("alerta", fields.pop("level"), **fields)
