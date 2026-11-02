"""Un solo proceso por servicio aunque el lanzador no lo vea (T126): con la tarea al encender los
servicios corren en la sesión 0 y, desde la sesión del usuario, su línea de órdenes no se puede
leer. Lo que impide duplicados es el cerrojo de instancia; el lanzador lo consulta antes."""

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from eim.data.collectors import liq_ws
from eim.data.collectors.health import micro_dir
from eim.operation import __main__ as op_main
from eim.operation.watchdog import instance_lock

LAUNCHER = Path(__file__).resolve().parents[2] / "scripts" / "servicio_continuo.ps1"


def test_un_segundo_vigilante_de_la_api_no_arranca(tmp_path, monkeypatch, capsys):
    started = []
    monkeypatch.setattr(op_main, "Watchdog", lambda *a, **k: started.append(a))
    lock = instance_lock(tmp_path / "operation" / "supervisor.lock")
    try:
        assert op_main.main(["run", "--data-dir", str(tmp_path), "--allow-empty-data"]) == 4
    finally:
        lock.close()
    assert started == [] and "Ya hay un vigilante" in capsys.readouterr().err


def test_un_segundo_recolector_de_liquidaciones_no_arranca(tmp_path, monkeypatch):
    def no_debe_correr(*_a, **_k):
        raise AssertionError("arrancó un segundo recolector")

    monkeypatch.setattr(liq_ws, "run", no_debe_correr)
    monkeypatch.setattr(sys, "argv", ["liq_ws", "BTCUSDT", "--root", str(tmp_path)])
    lock = instance_lock(micro_dir(tmp_path) / "liq_collector.lock")
    try:
        with pytest.raises(SystemExit) as e:
            liq_ws.main()
    finally:
        lock.close()
    assert e.value.code == 3


@pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell"),
                    reason="comprobación de PowerShell en Windows")
def test_el_lanzador_ve_el_cerrojo_de_python(tmp_path):
    """`Ocupado` de `servicio_continuo.ps1` y `instance_lock` deben coincidir: si no, el lanzador
    duplicaría servicios o dejaría de lanzarlos."""
    func = re.search(r"function Ocupado\(.*?\n}\n", LAUNCHER.read_text(encoding="utf-8-sig")
                     .replace("\r\n", "\n"), re.S).group(0)
    path = tmp_path / "servicio.lock"

    def ocupado() -> str:
        cmd = f"{func}\nOcupado '{path}'"
        return subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True,
                              text=True, timeout=60, check=True).stdout.strip()

    assert ocupado() == "False"                       # no existe
    lock = instance_lock(path)
    try:
        assert ocupado() == "True"                    # lo tiene un proceso vivo
    finally:
        lock.close()
    assert ocupado() == "False"                       # el archivo queda, el bloqueo no
