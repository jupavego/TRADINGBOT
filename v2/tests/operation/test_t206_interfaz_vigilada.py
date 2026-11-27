"""T206: la interfaz también se vigila, aparte de los cinco servicios de datos.

El 2026-11-25 Vite murió a las 16:27 UTC y nadie la levantó en siete horas: los cinco servicios
estaban vivos y el vigilante decía «ok» en cada pasada. Aquí todo es simulado (latidos falsos,
sonda falsa, lanzador de mentira); no se toca ningún proceso ni ningún puerto de verdad.
"""

from __future__ import annotations

import json

import pytest

from eim.operation import fleet_watch, fleet_web
from tests.operation.test_fleet_watch import T0, Lanzador, _beats, _usage


def pasada(tmp_path, now_s, lz, escucha):
    """Una pasada con los cinco servicios latiendo: lo único caído es la pantalla."""
    _beats(tmp_path, now_s)
    _usage(tmp_path, now_s)
    return fleet_watch.check(tmp_path, now_s=now_s, launcher=lz, notify=False, ops=[],
                             web_probe=lambda: escucha)


def eventos(tmp_path):
    return [json.loads(ln) for f in (tmp_path / "operation" / "logs").glob("*.jsonl")
            for ln in f.read_text(encoding="utf-8").splitlines()]


def test_con_los_cinco_vivos_y_la_interfaz_caida_se_levanta(tmp_path):
    lz = Lanzador()
    assert pasada(tmp_path, T0, lz, False)["interfaz"] == "esperar"      # aún no toca
    assert lz.calls == 0
    out = pasada(tmp_path, T0 + fleet_web.DOWN_S, lz, False)
    assert out["action"] == "ok" and out["interfaz"] == "levantar" and lz.calls == 1
    assert any(e["event"] == "interfaz_levantar" for e in eventos(tmp_path))


def test_cuando_vuelve_se_avisa_y_se_olvida(tmp_path):
    lz = Lanzador()
    pasada(tmp_path, T0, lz, False)
    pasada(tmp_path, T0 + fleet_web.DOWN_S, lz, False)
    out = pasada(tmp_path, T0 + fleet_web.DOWN_S + 300, lz, True)
    assert out["interfaz"] == "recuperada" and out["interfaz_down_s"] >= fleet_web.DOWN_S
    assert pasada(tmp_path, T0 + 2 * fleet_web.DOWN_S, lz, True).get("interfaz") is None


def test_una_sonda_que_no_sabe_no_levanta_nada(tmp_path):
    lz = Lanzador()
    for i in range(4):
        assert pasada(tmp_path, T0 + i * fleet_web.DOWN_S, lz, None).get("interfaz") is None
    assert lz.calls == 0


def test_no_gasta_los_intentos_de_los_cinco_ni_al_reves(tmp_path):
    """La cuenta de la interfaz es suya: cuatro intentos de pantalla no rinden a la captura."""
    lz = Lanzador()
    pasada(tmp_path, T0, lz, False)                  # la primera pasada solo empieza a contar
    t = T0 + fleet_web.DOWN_S
    for espera in fleet_web.BACKOFF_S:
        t += espera
        pasada(tmp_path, t, lz, False)
    estado = json.loads((tmp_path / "operation" / "fleet_watch.json").read_text(encoding="utf-8"))
    assert estado["web_tries"] == fleet_web.MAX_TRIES and estado["tries"] == 0
    assert lz.calls == fleet_web.MAX_TRIES
    t += fleet_web.BACKOFF_S[-1]
    assert pasada(tmp_path, t, lz, False)["interfaz"] == "rendirse"     # y deja de intentarlo
    assert lz.calls == fleet_web.MAX_TRIES


def test_la_variable_de_entorno_la_deja_fuera(tmp_path, monkeypatch):
    monkeypatch.setenv(fleet_web.ENV, "0")
    lz = Lanzador()
    assert pasada(tmp_path, T0 + 10 * fleet_web.DOWN_S, lz, False).get("interfaz") is None
    assert lz.calls == 0


def test_solo_el_arranque_de_la_interfaz_pide_conweb(monkeypatch):
    """El guion es el mismo; `-ConWeb` solo va cuando lo que falta es la pantalla (T148)."""
    vistas = []

    class Fin:
        returncode, stdout, stderr = 0, "", ""

    monkeypatch.setattr(fleet_watch.subprocess, "run",
                        lambda cmd, **k: (vistas.append(cmd), Fin())[1])
    fleet_watch.launch("D:/datos")
    fleet_watch.launch("D:/datos", con_web=True)
    assert "-ConWeb" not in vistas[0] and vistas[1][-1] == "-ConWeb"


@pytest.mark.parametrize("escucha", [True, False, None])
def test_la_decision_es_pura_y_no_toca_nada(escucha):
    from eim.operation.fleet_state import State

    d = fleet_web.decide(escucha, State(), 1_700_000_000_000)
    assert d.action in ("ok", "esperar") and not d.lift
