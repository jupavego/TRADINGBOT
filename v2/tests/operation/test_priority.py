"""Niveles de prioridad por proceso (T126): solo con EIM_PRIORITY=on, uno por papel declarado."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from eim.operation import priority

ON = {"EIM_PRIORITY": "on"}
V2 = Path(__file__).resolve().parents[2]
win = pytest.mark.skipif(sys.platform != "win32", reason="clases de prioridad de Windows")


def _py(*args: str, env: dict | None = None) -> str:
    out = subprocess.run([sys.executable, *args], cwd=V2, env={**os.environ, **(env or {})},
                         capture_output=True, text=True, timeout=60, check=True)
    return out.stdout.strip().splitlines()[-1]


def test_sin_la_variable_no_toca_nada():
    before = priority.current_class()
    assert not priority.enabled()                       # conftest retira las EIM_* del equipo
    assert priority.apply_role("hft_collector") is None
    with priority.lowered("batch"):
        assert priority.current_class() == before
    assert priority.current_class() == before


def test_roles_y_niveles_validos():
    assert set(priority.ROLES.values()) <= set(priority.WINDOWS_CLASS)
    assert priority.apply_role("desconocido", env=ON) is None
    assert priority.enabled({"EIM_PRIORITY": " ON "})
    assert not priority.enabled({"EIM_PRIORITY": "0"})
    with pytest.raises(ValueError):
        priority.set_tier("turbo")


def test_cada_punto_de_arranque_declara_su_nivel():
    """Un servicio nuevo que llama a `configure(process=...)` y olvida su nivel correría con la
    prioridad de quien lo lanzó (BELOW_NORMAL desde la tarea programada)."""
    seen = set()
    for f in (V2 / "eim").rglob("*.py"):
        src = f.read_text(encoding="utf-8")
        for name in re.findall(r'configure\(process="(\w+)"', src):
            seen.add(name)
            assert name in priority.ROLES, f"{f.name}: papel {name} sin nivel en ROLES"
            assert f'apply_role("{name}")' in src, f"{f.name}: falta apply_role({name!r})"
    assert {"api", "hft_collector", "leaders"} <= seen


@win
def test_la_captura_sube_y_el_mantenimiento_baja_y_se_restaura():
    code = ("import json\nfrom eim.operation import priority as p\n"
            "a = p.apply_role('hft_collector'); c1 = p.tier_of(p.current_class())\n"
            "with p.lowered('batch'):\n    c2 = p.tier_of(p.current_class())\n"
            "print(json.dumps([a, c1, c2, p.tier_of(p.current_class())]))")
    assert json.loads(_py("-c", code, env=ON)) == ["realtime", "realtime", "batch", "realtime"]
    api = ("from eim.operation import priority as p; p.apply_role('api')\n"
           "print(p.tier_of(p.current_class()))")
    assert _py("-c", api, env=ON) == "service"     # por debajo de los programas del usuario


LEVELS = ("import json, os\nfrom eim.operation import priority as p, priority_memory as m\n"
          "m.set_levels(None, 2, 1)\np.apply_role('{role}')\nr = m.read(os.getpid())\n"
          "print(json.dumps([r['memory'], r['io'], sorted(r['threads'])]))")


@win
@pytest.mark.parametrize("role", ["hft_collector", "liq_collector", "collector"])
def test_los_recolectores_suben_su_memoria_y_su_es_al_arrancar(role):
    assert json.loads(_py("-c", LEVELS.format(role=role), env=ON)) == [5, 2, ["5/2"]]


@win
@pytest.mark.parametrize("role", ["api", "leaders", "hft_watchdog", "usage"])
def test_los_demas_servicios_conservan_memoria_y_es(role):
    """Subir la API antes de decidirlo dejaría a la captura sin ventaja (◆C de T141)."""
    assert json.loads(_py("-c", LEVELS.format(role=role), env=ON)) == [2, 1, ["2/1"]]


@win
def test_sin_la_variable_la_memoria_tampoco_cambia():
    assert json.loads(_py("-c", LEVELS.format(role="hft_collector"))) == [2, 1, ["2/1"]]


@win
def test_run_deja_la_orden_y_sus_hijos_por_debajo_de_los_servicios():
    """Windows hace heredar IDLE: también al proceso real detrás del lanzador del venv."""
    child = "from eim.operation import priority as p; print(p.tier_of(p.current_class()))"
    assert _py("-m", "eim.operation.priority", "run", "batch", "--",
               sys.executable, "-c", child) == "batch"
