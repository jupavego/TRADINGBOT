"""T140: el registro del vigilante se conserva entre arranques (`servicio_continuo.ps1`).

`Start-Process` lo reescribía al lanzar, y con él se perdía la evidencia de los fallos anteriores.
Se ejecuta la función real del script, sin lanzar nada más.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

import eim

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="script de PowerShell")
SCRIPTS = Path(eim.__file__).parents[1] / "scripts"
SCRIPT = SCRIPTS / "servicio_continuo.ps1"
WHEN = 1_793_000_000.0


def _stamp(when: float) -> str:
    return datetime.fromtimestamp(when, UTC).strftime("%Y%m%d-%H%M%S")


def _function() -> str:
    text = SCRIPT.read_text(encoding="utf-8-sig")
    found = re.search(r"^function Conservar\b.*?^}", text, re.M | re.S)
    assert found, "servicio_continuo.ps1 ya no tiene la función Conservar"
    return found.group(0)


def _keep(tmp_path: Path, target: Path, *args: str) -> subprocess.CompletedProcess:
    runner = tmp_path / "ejecutar.ps1"
    runner.write_text(f"$ErrorActionPreference = 'Stop'\n{_function()}\n"
                      f"Conservar '{target}' {' '.join(args)}\n", encoding="utf-8-sig")
    return subprocess.run(  # noqa: S603
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(runner)],  # noqa: S607
        capture_output=True, text=True, timeout=120, check=False)


def _log(d: Path, name: str, text: str = "x\n", when: float | None = None) -> Path:
    p = d / name
    p.write_text(text, encoding="utf-8")
    if when is not None:
        os.utime(p, (when, when))
    return p


def test_the_previous_log_is_set_aside_with_its_time(tmp_path):
    d = tmp_path / "logs"
    d.mkdir()
    log = _log(d, "vigilante.err.log", "Accept failed\n", when=WHEN)
    out = _keep(tmp_path, log)
    assert out.returncode == 0, out.stderr
    assert not log.exists()
    [kept] = list(d.glob("vigilante.err.*.log"))
    assert kept.name == f"vigilante.err.{_stamp(WHEN)}.log"
    assert kept.read_text(encoding="utf-8") == "Accept failed\n"


def test_an_empty_or_missing_log_is_left_alone(tmp_path):
    d = tmp_path / "logs"
    d.mkdir()
    empty = _log(d, "vigilante.out.log", "")
    assert _keep(tmp_path, empty).returncode == 0
    assert _keep(tmp_path, d / "no_existe.log").returncode == 0
    assert [p.name for p in d.iterdir()] == ["vigilante.out.log"]


def test_only_the_most_recent_are_kept_and_other_logs_are_not_touched(tmp_path):
    d = tmp_path / "logs"
    d.mkdir()
    for day in (20261101, 20261102, 20261103):
        _log(d, f"vigilante.err.{day}-000000.log")
    other = _log(d, "vigilante.out.20261101-000000.log")
    now = WHEN + 10 * 86_400                            # posterior a los tres anteriores
    log = _log(d, "vigilante.err.log", when=now)
    assert _keep(tmp_path, log, "2").returncode == 0
    assert sorted(p.name for p in d.glob("vigilante.err.*.log")) == [
        "vigilante.err.20261103-000000.log", f"vigilante.err.{_stamp(now)}.log"]
    assert other.exists()


def test_a_failure_to_keep_it_never_stops_the_launch(tmp_path):
    """Un registro retenido por otro proceso no puede dejar el servicio sin lanzar."""
    d = tmp_path / "logs"
    d.mkdir()
    log = _log(d, "vigilante.err.log")
    with log.open("r+b"):                               # abierto sin permiso para moverlo
        out = _keep(tmp_path, log)
    assert out.returncode == 0, out.stderr
    assert log.exists()


@pytest.mark.parametrize("name", ["servicio_continuo.ps1", "icono_bandeja.ps1"])
def test_the_scripts_still_parse(name):
    """Los editados en T140 llevan BOM: sin él, PowerShell 5.1 estropea los acentos."""
    path = SCRIPTS / name
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    _assert_parses(path)


def test_the_weekly_ab_script_parses_and_stays_in_ascii():
    """T135: sin BOM y sin acentos, para que PowerShell 5.1 no estropee nada."""
    path = SCRIPTS / "t135_ab_semanal.ps1"
    assert path.read_bytes().isascii()
    _assert_parses(path)


def _assert_parses(path: Path) -> None:
    probe = ("$e = $null; [void][System.Management.Automation.Language.Parser]::ParseFile("
             f"'{path}', [ref]$null, [ref]$e); $e.Count")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", probe],  # noqa: S603, S607
                         capture_output=True, text=True, timeout=120, check=False)
    assert out.stdout.strip() == "0", out.stdout + out.stderr
