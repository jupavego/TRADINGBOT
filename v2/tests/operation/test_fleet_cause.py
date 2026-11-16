"""T173: un servicio bloqueado no es un servicio muerto, y nuestra red no es la del exchange.

Todo simulado, como en `test_fleet_watch.py`: latidos falsos en una carpeta de prueba, eventos de
operación escritos a mano con la forma que tienen en `data/operation/logs/` y un lanzador de
mentira. Los instantes imitan el corte de DNS del 2026-11-10 (20:07:55 → 23:46:33 UTC).
"""

from __future__ import annotations

import json
from pathlib import Path

from eim.data.collectors import hft_attrib, hft_window
from eim.operation import fleet_cause, fleet_watch
from tests.operation.test_fleet_watch import Lanzador, _beats, _usage

T_CORTE = 1_794_341_275.0      # 2026-11-10 20:07:55 UTC, primer `getaddrinfo failed`
T_VUELVE = 1_794_354_393.0     # 2026-11-10 23:46:33 UTC, «Resuelta» de la desconexión
RED = ("ProviderError: /fapi/v1/klines agotó 4 reintentos (red: [Errno 11001] "
       "getaddrinfo failed)")


def _fallo(t_s: float) -> dict:
    return {"t": int(t_s * 1000), "event": "datos_fallidos", "level": "warn", "error": RED}


def _desconexion(t_s: float, resuelta: bool) -> dict:
    return {"t": int(t_s * 1000), "event": "alerta", "kind": "desconexion",
            "key": "desconexion:BTCUSDT", "resolved": resuelta, "level": "critical"}


def _corte(t0: float, t1: float, cada_s: float = 80.0) -> list[dict]:
    """Los `datos_fallidos` de un corte de red, uno cada ~80 s como el 2026-11-10."""
    n = int((t1 - t0) // cada_s) + 1
    return [_fallo(t0 + i * cada_s) for i in range(n)]


def _check(tmp_path, now_s, lz, ops):
    return fleet_watch.check(tmp_path, now_s=now_s, launcher=lz, notify=False, ops=ops)


def _rows(tmp_path: Path) -> list[dict]:
    out = []
    for p in sorted((tmp_path / "operation" / "logs").glob("op-*.jsonl")):
        out += [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines()]
    return out


# ---------------------------------------------------------------- E1: sin red no es sin servicio

def test_con_la_red_caida_no_gasta_intentos_y_avisa_una_vez(tmp_path):
    """El 2026-11-10 se gastaron cuatro intentos en balde; ahora ninguno."""
    now = T_CORTE + 20 * 60
    _beats(tmp_path, now, solo=("API", "bróker simulado", "captura HFT"))
    _beats(tmp_path, now, age_s=15 * 60, solo=("líderes",))
    _usage(tmp_path, now)
    lz = Lanzador()
    acciones = [_check(tmp_path, now + i * 300, lz, _corte(T_CORTE, now + i * 300))["action"]
                for i in range(6)]
    assert acciones == ["sin_red"] * 6 and lz.calls == 0
    st = fleet_watch.State.load(tmp_path / "operation" / "fleet_watch.json")
    assert st.tries == 0 and st.down_since_ms is not None
    rows = _rows(tmp_path)
    assert len([r for r in rows if r["event"] == "conjunto_sin_red"]) == 1
    avisos = [r for r in rows if r["event"] == "alerta"]
    assert len(avisos) == 1 and "sin red" in avisos[0]["title"]
    assert avisos[0]["level"] == "warn" and "getaddrinfo" in avisos[0]["detail"]


def test_al_volver_la_red_espera_una_pasada_y_despues_relanza(tmp_path):
    """Si el latido no vuelve solo en una pasada tras volver la red, entonces sí se relanza."""
    now = T_CORTE + 3600
    _beats(tmp_path, now, solo=("API", "bróker simulado", "captura HFT"))
    _beats(tmp_path, now, age_s=3000, solo=("líderes",))
    _usage(tmp_path, now)
    ops = _corte(T_CORTE, now)
    lz = Lanzador()
    assert _check(tmp_path, now, lz, ops)["action"] == "sin_red"
    despues = now + fleet_watch.fleet_cause.NET_WINDOW_S + 60      # ya sin fallos recientes
    ops_ok = [*ops, _desconexion(despues - 30, resuelta=True)]
    _beats(tmp_path, despues, solo=("API", "bróker simulado", "captura HFT"))
    _usage(tmp_path, despues)
    assert _check(tmp_path, despues, lz, ops_ok)["action"] == "esperar" and lz.calls == 0
    out = _check(tmp_path, despues + 300, lz, ops_ok)
    assert out["action"] == "levantar" and out["missing"] == ["líderes"] and lz.calls == 1


def test_una_desconexion_abierta_con_la_api_muerta_no_bloquea(tmp_path):
    """Si la API murió con la alerta abierta, nadie la va a cerrar: no puede frenar el arranque."""
    now = T_CORTE + 6 * 3600
    _beats(tmp_path, now, age_s=5 * 3600)
    lz = Lanzador()
    out = _check(tmp_path, now, lz, [_desconexion(now - 5 * 3600, resuelta=False)])
    assert out["action"] == "levantar" and lz.calls == 1


def test_una_desconexion_abierta_con_la_api_viva_si_cuenta(tmp_path):
    now = T_CORTE + 600
    _beats(tmp_path, now, solo=("API", "bróker simulado", "captura HFT"))
    _beats(tmp_path, now, age_s=900, solo=("líderes",))
    _usage(tmp_path, now)
    cause = fleet_cause.network_cause([_desconexion(T_CORTE + 240, resuelta=False)],
                                      int(now * 1000))
    assert cause is not None and cause["alert_open"] and cause["fails"] == 0
    out = _check(tmp_path, now, Lanzador(), [_desconexion(T_CORTE + 240, resuelta=False)])
    assert out["action"] == "sin_red"


# ------------------------------------------------- E3: lo que vive dentro de otro no se relanza

def test_el_broker_dentro_de_la_api_viva_no_se_intenta_levantar(tmp_path):
    """El guion no puede levantar el bróker con la API en pie: se dice qué hace falta."""
    now = T_CORTE - 3600
    _beats(tmp_path, now, solo=("API", "líderes", "captura HFT"))
    _beats(tmp_path, now, age_s=1500, solo=("bróker simulado",))
    _usage(tmp_path, now)
    lz = Lanzador()
    outs = []
    for i in range(4):                     # la API y los demás siguen latiendo; el bróker, no
        t = now + i * 300
        _beats(tmp_path, t, solo=("API", "líderes", "captura HFT"))
        _usage(tmp_path, t)
        outs.append(_check(tmp_path, t, lz, []))
    assert [o["action"] for o in outs] == ["dentro_de_otro"] * 4 and lz.calls == 0
    assert outs[0]["dentro_de_otro"] == ["bróker simulado"]
    avisos = [r for r in _rows(tmp_path) if r["event"] == "alerta"]
    assert len(avisos) == 1 and avisos[0]["level"] == "critical"
    assert "RUNBOOK §16" in avisos[0]["detail"] and "T31" in avisos[0]["detail"]


def test_si_tambien_falta_la_api_se_levanta_el_conjunto(tmp_path):
    """Con el anfitrión caído, relanzarlo sí sirve: arrastra al bróker."""
    now = T_CORTE - 3600
    _beats(tmp_path, now, solo=("líderes", "captura HFT"))
    _beats(tmp_path, now, age_s=1500, solo=("API", "bróker simulado"))
    _usage(tmp_path, now)
    lz = Lanzador()
    out = _check(tmp_path, now, lz, [])
    assert out["action"] == "levantar" and lz.calls == 1 and "dentro_de_otro" not in out


# ------------------------------------------------------- E2: un intento se juzga por su efecto

def test_un_arranque_con_rc_0_que_no_mueve_el_latido_queda_sin_efecto(tmp_path):
    now = T_CORTE - 7200
    _beats(tmp_path, now, solo=("API", "bróker simulado", "captura HFT"))
    _beats(tmp_path, now, age_s=1200, solo=("líderes",))
    _usage(tmp_path, now)
    lz = Lanzador(rc=0)
    first = _check(tmp_path, now, lz, [])
    assert first["action"] == "levantar" and "sin_efecto" not in first
    _beats(tmp_path, now + 300, solo=("API", "bróker simulado", "captura HFT"))
    _usage(tmp_path, now + 300)
    second = _check(tmp_path, now + 300, lz, [])          # 2.º intento: líderes siguen igual
    assert second["action"] == "levantar" and second["sin_efecto"] is True
    avisos = [r for r in _rows(tmp_path) if r["event"] == "alerta"]
    assert "no contó" in avisos[-1]["detail"]


def test_un_arranque_que_si_mueve_el_latido_no_se_marca(tmp_path):
    now = T_CORTE - 7200
    _beats(tmp_path, now, solo=("API", "bróker simulado", "captura HFT"))
    _beats(tmp_path, now, age_s=1200, solo=("líderes",))
    _usage(tmp_path, now)
    lz = Lanzador(rc=0)
    _check(tmp_path, now, lz, [])
    # Late una vez tras el arranque y vuelve a caer: el intento sí sirvió.
    _beats(tmp_path, now + 300, age_s=20 * 60 - 400, solo=("líderes",))
    _beats(tmp_path, now + 300, solo=("API", "bróker simulado", "captura HFT"))
    _usage(tmp_path, now + 300)
    out = _check(tmp_path, now + 300, lz, [])
    assert "sin_efecto" not in out


# ------------------------------------------------------------- E4: late pero no produce

def _qc(tmp_path: Path, hour_s: float, usable: float, runs: int) -> None:
    p = fleet_cause._qc_path(tmp_path, "BTCUSDT", int(hour_s * 1000))
    p.parent.mkdir(parents=True, exist_ok=True)
    label = p.parent.name.removeprefix("date=") + "T" + p.stem.removeprefix("hour=")
    p.write_text(json.dumps({"hour": label, "book_usable": usable, "runs": runs}),
                 encoding="utf-8")


def test_la_captura_que_late_sin_capturar_se_avisa_una_vez_por_hora(tmp_path):
    """Horas 21 y 22 del 2026-11-10: latido cada ~28 s y `runs: 0`."""
    now = 1_794_349_500.0                       # 2026-11-10 22:25 UTC
    _beats(tmp_path, now)
    _usage(tmp_path, now)
    _qc(tmp_path, now - 3600, usable=0.0, runs=0)
    lz = Lanzador()
    for i in range(4):                          # la misma hora cerrada en cuatro pasadas
        out = _check(tmp_path, now + i * 120, lz, [])
        assert out["late_sin_producir"]["runs"] == 0
    rows = _rows(tmp_path)
    assert len([r for r in rows if r["event"] == "conjunto_late_sin_producir"]) == 1
    avisos = [r for r in rows if r["event"] == "alerta" and r["key"] == "captura_sin_producir"]
    assert len(avisos) == 1 and "no captura" in avisos[0]["detail"] and lz.calls == 0


def test_una_hora_buena_no_avisa(tmp_path):
    now = 1_794_349_500.0
    _qc(tmp_path, now - 3600, usable=0.999, runs=1)
    assert fleet_cause.not_producing(tmp_path, now) is None


# ------------------------------------------------- E5: nuestra red no es la del exchange

def test_los_tramos_de_red_local_se_juntan_y_acaban_en_la_resuelta():
    ops = [*_corte(T_CORTE, T_VUELVE - 200), _desconexion(T_CORTE + 247, False),
           _desconexion(T_VUELVE, True)]
    spans = fleet_cause.local_net_spans(ops)
    assert len(spans) == 1 and spans[0]["t1"] == int(T_VUELVE * 1000)
    horas = fleet_cause.net_hours(spans)
    # 20, 21, 22 y 23 UTC del 2026-11-10.
    assert sorted(h % 24 for h in horas) == [20, 21, 22, 23]


def test_una_desconexion_sin_fallos_de_red_sigue_siendo_ajena():
    """Las alertas de desconexión solas saltan también cuando se calla el exchange."""
    assert fleet_cause.local_net_spans([_desconexion(T_CORTE, False),
                                        _desconexion(T_CORTE + 600, True)]) == []


def test_una_hora_de_red_local_es_nuestra_aunque_el_recolector_dijera_desconexion():
    """La hora 20 del 2026-11-10: tramos `desconexion` que sí suman la hora y libro útil 9,8 %."""
    hora = int(T_CORTE // 3600)
    rep = {"hour": "2026-11-10T20", "complete": False, "book_usable": 0.0978, "runs": 1,
           "gaps_marked": {"by_cause": {"desconexion": 150}, "total_s": 3600.0}}
    assert hft_attrib.attribute(rep, hora) in ("ajena", "nuestra")
    assert hft_attrib.attribute(rep, hora, local_net_hours={hora}) == "nuestra"
    assert hft_attrib.why(rep, hora, local_net_hours={hora}).startswith("red_local")


def test_la_ventana_reparte_las_horas_de_red_local_como_nuestras():
    hora = int(T_CORTE // 3600)
    reps = [{"hour": f"h{i}", "hour_index": hora + i, "complete": i != 0, "book_usable": 0.1,
             "runs": 1, "gaps_marked": {"by_cause": {"desconexion": 150}, "total_s": 3600.0}}
            for i in range(3)]
    con = hft_window.window(reps, hora + 2, local_net_hours={hora})
    assert con["attribution"] == {"nuestra": 1}
