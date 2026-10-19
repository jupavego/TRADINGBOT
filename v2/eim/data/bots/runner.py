"""Ejecutor aislado de bots, modo B (T57): el bot corre sin claves y sin autoridad de operar.

Qué garantiza (probado en `tests/bots/test_runner.py`):
- **Entorno limpio**: lista blanca de variables; ninguna `*_KEY/SECRET/TOKEN/PASSWORD` llega al
  proceso, ni un `.env`: el directorio de trabajo es nuevo, vacío y se borra al terminar.
- **Sin descargas**: proxies muertos, pip sin índice, modo sin conexión de HF; en Linux además
  `unshare --net` (sin red) si el sistema lo permite. En Windows no hay aislamiento de red por
  proceso fiable: ver `docs/SEGURIDAD.md` (se compensa con lo anterior y la revisión de T56).
- **Recursos acotados**: tiempo (se mata el grupo de procesos), memoria y CPU (rlimit vía
  lanzador, solo POSIX), tamaño de la salida.
- **Versión fijada**: si se pasa `bot_dir`+`expected_sha`, el checkout debe estar en ese SHA y
  limpio; si no, el bot no se ejecuta.
- **Nunca lanza**: cualquier fallo (timeout, caída, salida corrupta) vuelve como `degraded`.
Las velas y la petición cruzan por archivos (`candles.json`, `request.json`); la respuesta se
lee de `out.json`. El proceso no recibe órdenes, solo datos.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

IS_WINDOWS = os.name == "nt"
LAUNCHER = Path(__file__).with_name("_launch.py")
SECRET_NAME = re.compile(r"(KEY|SECRET|TOKEN|PASSW|PASSPHRASE|CREDENTIAL|AUTH|COOKIE)", re.I)
_PASS = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "PATHEXT", "LANG", "LC_ALL")  # sin datos sensibles
DEAD_PROXY = "http://127.0.0.1:9"  # puerto discard: toda descarga por proxy falla


@dataclass(frozen=True)
class Limits:
    timeout_s: float = 60.0
    memory_mb: int = 2048
    cpu_s: int = 120
    max_output_bytes: int = 5_000_000


@dataclass(frozen=True)
class RunSpec:
    python: Path                              # intérprete del entorno del bot
    script: Path                              # punto de entrada (cwd = directorio temporal)
    request: Mapping = field(default_factory=dict)        # → request.json
    files: Mapping[str, str | bytes] = field(default_factory=dict)  # → archivos de entrada
    bot_dir: Path | None = None               # checkout del bot (solo lectura)
    expected_sha: str | None = None           # SHA que debe tener `bot_dir`
    extra_env: Mapping[str, str] = field(default_factory=dict)
    limits: Limits = field(default_factory=Limits)
    isolate_network: bool = True


@dataclass(frozen=True)
class RunResult:
    status: str                               # «ok» | «degraded»
    output: dict | None = None
    warnings: tuple[str, ...] = ()
    duration_s: float = 0.0
    network_isolated: bool = False


def clean_env(workdir: Path, extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Entorno del bot: solo lo imprescindible. `extra` no puede traer nombres de secretos."""
    for name in extra or {}:
        if SECRET_NAME.search(name):
            raise ValueError(f"variable con aspecto de secreto no permitida: {name}")
    wd = str(workdir)
    env = {"PATH": os.environ.get("PATH", "") if IS_WINDOWS else "/usr/local/bin:/usr/bin:/bin",
           "HOME": wd, "USERPROFILE": wd, "TMPDIR": wd, "TEMP": wd, "TMP": wd,
           "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
           "PYTHONUTF8": "1", "HTTP_PROXY": DEAD_PROXY, "HTTPS_PROXY": DEAD_PROXY,
           "ALL_PROXY": DEAD_PROXY, "NO_PROXY": "", "PIP_NO_INDEX": "1",
           "PIP_DISABLE_PIP_VERSION_CHECK": "1", "HF_HUB_OFFLINE": "1", "OFFLINE": "1"}
    env |= {k: os.environ[k] for k in _PASS if k in os.environ and not SECRET_NAME.search(k)}
    env |= dict(extra or {})
    return env


def checkout_state(bot_dir: Path) -> tuple[str | None, bool]:
    """(SHA de HEAD, ¿hay cambios locales o archivos nuevos sin versionar?) del checkout."""
    git = shutil.which("git")
    if git is None or not (Path(bot_dir) / ".git").exists():
        return None, False
    # autocrlf=input: con HOME aislado no se lee la config del usuario; en Windows un checkout con
    # CRLF (autocrlf=true al clonar) se vería «modificado» sin que nadie lo tocara.
    base = [git, "-c", "core.autocrlf=input", "-C", str(bot_dir)]
    env = {"PATH": os.environ.get("PATH", ""), "GIT_CONFIG_NOSYSTEM": "1", "HOME": str(bot_dir)}
    try:
        head = subprocess.run([*base, "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=20, env=env, check=True).stdout.strip()
        dirty = subprocess.run([*base, "status", "--porcelain", "--untracked-files=all"],
                               capture_output=True, text=True, timeout=20, env=env,
                               check=True).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return None, False
    return head, bool(dirty)


_UNSHARE: bool | None = None


def can_unshare_net() -> bool:
    """¿Se puede arrancar un proceso sin red (`unshare --net`)? Se prueba una vez."""
    global _UNSHARE
    if _UNSHARE is None:
        exe = shutil.which("unshare")
        ok = False
        if exe and not IS_WINDOWS:
            try:
                ok = subprocess.run([exe, "--net", "--map-root-user", "true"], timeout=10,
                                    capture_output=True).returncode == 0
            except (subprocess.SubprocessError, OSError):
                ok = False
        _UNSHARE = ok
    return _UNSHARE


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        if IS_WINDOWS:
            proc.kill()
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _command(spec: RunSpec) -> tuple[list[str], bool]:
    cmd = [str(spec.python), str(spec.script)]
    if not IS_WINDOWS:   # lanzador: fija rlimits y hace exec (sin preexec_fn en procesos con hilos)
        lim = spec.limits
        cmd = [sys.executable, "-I", str(LAUNCHER), str(lim.memory_mb), str(lim.cpu_s),
               str(lim.max_output_bytes), *cmd]
    net = spec.isolate_network and can_unshare_net()
    if net:
        cmd = [shutil.which("unshare") or "unshare", "--net", "--map-root-user", *cmd]
    return cmd, net


def _fail(reason: str, t0: float, net: bool = False) -> RunResult:
    return RunResult("degraded", None, (reason,), time.monotonic() - t0, net)


def run_isolated(spec: RunSpec) -> RunResult:
    """Corre el bot una vez. Jamás lanza: devuelve `degraded` con el motivo."""
    t0 = time.monotonic()
    try:
        return _run(spec, t0)
    except Exception as exc:  # noqa: BLE001 - el servicio no debe caer por un bot
        return _fail(f"error del ejecutor: {type(exc).__name__}: {exc}", t0)


def _run(spec: RunSpec, t0: float) -> RunResult:
    if spec.bot_dir is not None and spec.expected_sha is not None:
        head, dirty = checkout_state(spec.bot_dir)
        if head != spec.expected_sha:
            return _fail(f"versión del bot distinta de la fijada: {head} ≠ {spec.expected_sha}", t0)
        if dirty:
            return _fail("el checkout del bot tiene cambios locales: no se ejecuta", t0)
    if not Path(spec.python).exists() or not Path(spec.script).exists():
        return _fail("falta el intérprete o el script del bot", t0)
    with tempfile.TemporaryDirectory(prefix="eim-bot-") as tmp:
        wd = Path(tmp)
        (wd / "request.json").write_text(json.dumps(dict(spec.request)), encoding="utf-8")
        for name, data in spec.files.items():
            if Path(name).name != name:
                return _fail(f"nombre de archivo de entrada no permitido: {name}", t0)
            (wd / name).write_bytes(data if isinstance(data, bytes) else data.encode())
        env = clean_env(wd, spec.extra_env)
        cmd, net = _command(spec)
        proc = subprocess.Popen(cmd, cwd=wd, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                start_new_session=not IS_WINDOWS)
        try:
            _, err = proc.communicate(timeout=spec.limits.timeout_s)
        except subprocess.TimeoutExpired:
            _kill_group(proc)
            proc.communicate()
            return _fail(f"el bot excedió {spec.limits.timeout_s:g}s y fue detenido", t0, net)
        tail = err.decode(errors="replace").strip()[-400:]
        if proc.returncode != 0:
            return _fail(f"el bot terminó con código {proc.returncode}: {tail}", t0, net)
        out = wd / "out.json"
        if not out.exists():
            return _fail("el bot no escribió out.json", t0, net)
        if out.stat().st_size > spec.limits.max_output_bytes:
            return _fail("salida del bot demasiado grande", t0, net)
        try:
            data = json.loads(out.read_text(encoding="utf-8"))
        except ValueError:
            return _fail("out.json no es JSON válido", t0, net)
        if not isinstance(data, dict):
            return _fail("out.json debe ser un objeto", t0, net)
        return RunResult("ok", data, (), time.monotonic() - t0, net)
