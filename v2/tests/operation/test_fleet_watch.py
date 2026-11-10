"""T148 E1: el vigilante del conjunto levanta los cinco servicios y no entra en bucle.

Los servicios de verdad corren 24/7 desde la carpeta principal y cada reinicio cuesta horas de
captura, así que aquí todo es simulado: latidos falsos en una carpeta de datos de prueba y un
lanzador de mentira. Nada de esto toca ningún proceso.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from eim.operation import fleet_watch

T0 = 1_794_246_945.0          # 2026-11-09 17:55:45 UTC, la última muestra antes del apagón
HOUR = 3600.0


def _beats(data_dir: Path, now_s: float, age_s: float = 10.0,
           solo: tuple[str, ...] | None = None) -> None:
    """Escribe los cuatro latidos de archivo con la edad pedida."""
    for name, rel in fleet_watch.BEATS.items():
        if solo is not None and name not in solo:
            continue
        p = data_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        key = "last_tick" if "paper" in rel else "last_heartbeat"
        p.write_text(json.dumps({key: int((now_s - age_s) * 1000)}), encoding="utf-8")


def _usage(data_dir: Path, now_s: float, age_s: float = 10.0) -> None:
    """Una muestra del registro de consumo, que es el quinto servicio y no tiene latido propio."""
    t = now_s - age_s
    d = data_dir / "usage"
    d.mkdir(parents=True, exist_ok=True)
    day = time.strftime("%Y-%m-%d", time.gmtime(t))
    (d / f"{day}.jsonl").write_text(
        json.dumps({"t": int(t * 1000), "ts": "x", "machine": {"cpu": 1.0}}) + "\n",
        encoding="utf-8")


class Lanzador:
    """Un `servicio_continuo.ps1` de mentira: cuenta las veces y devuelve lo que se le diga."""

    def __init__(self, rc: int = 0) -> None:
        self.rc, self.calls = rc, 0

    def __call__(self, data_dir: Path) -> tuple[int, str]:
        self.calls += 1
        return self.rc, "salida de prueba"


def _check(tmp_path, now_s, lanzador, **kw):
    return fleet_watch.check(tmp_path, now_s=now_s, launcher=lanzador, notify=False, **kw)


# ------------------------------------------------------------------------------ lo que ve

def test_los_cinco_servicios_se_leen_y_el_quinto_sale_de_sus_muestras(tmp_path):
    """El registro de consumo no publica latido: su señal de vida son sus propias muestras."""
    _beats(tmp_path, T0, age_s=12.0)
    _usage(tmp_path, T0, age_s=45.0)
    seen = fleet_watch.ages(tmp_path, T0)
    assert sorted(seen) == sorted([*fleet_watch.BEATS, fleet_watch.USAGE])
    assert seen["API"] == 12.0 and seen[fleet_watch.USAGE] == 45.0
    assert fleet_watch.missing(seen) == []


def test_un_servicio_sin_senal_nunca_tambien_cuenta_como_caido(tmp_path):
    """Equipo recién instalado o archivo ilegible: hay que levantarlo igual."""
    seen = fleet_watch.ages(tmp_path, T0)
    assert all(v is None for v in seen.values())
    assert fleet_watch.missing(seen) == [*fleet_watch.BEATS, fleet_watch.USAGE]


def test_con_todo_al_dia_no_hace_nada(tmp_path):
    _beats(tmp_path, T0)
    _usage(tmp_path, T0)
    lz = Lanzador()
    assert _check(tmp_path, T0, lz)["action"] == "ok"
    assert lz.calls == 0


def test_un_latido_viejo_pero_dentro_del_margen_no_dispara(tmp_path):
    """Decisión del usuario: se levanta a los 10 min, el doble del ciclo más lento, para no
    pisar un reinicio en curso."""
    _beats(tmp_path, T0, age_s=fleet_watch.DOWN_S - 60)
    _usage(tmp_path, T0, age_s=30.0)
    lz = Lanzador()
    assert _check(tmp_path, T0, lz)["action"] == "ok" and lz.calls == 0


# ------------------------------------------------------------------- levanta y deja constancia

def test_con_los_cinco_caidos_levanta_y_registra_que_faltaba_y_cuanto(tmp_path):
    """El caso del 2026-11-09: los cinco parados a la vez y nadie que los levantara."""
    _beats(tmp_path, T0, age_s=6 * HOUR)
    _usage(tmp_path, T0, age_s=6 * HOUR)
    lz = Lanzador()
    out = _check(tmp_path, T0, lz)
    assert out["action"] == "levantar" and lz.calls == 1 and out["rc"] == 0
    assert out["missing"] == [*fleet_watch.BEATS, fleet_watch.USAGE]
    assert out["tries"] == 1 and out["ages_s"]["API"] == 6 * HOUR
    rows = [json.loads(ln) for ln in
            (tmp_path / "operation" / "logs").glob("op-*.jsonl").__next__()
            .read_text(encoding="utf-8").splitlines()]
    levantar = [r for r in rows if r["event"] == "conjunto_levantar"]
    assert len(levantar) == 1
    assert levantar[0]["missing"] == out["missing"] and levantar[0]["ages_s"]["API"] == 6 * HOUR
    # Entregable 5: el usuario se entera, no solo el registro.
    avisos = [r for r in rows if r["event"] == "alerta"]
    assert avisos and "estaba caído" in avisos[0]["title"]


def test_un_solo_servicio_caido_basta_para_levantar(tmp_path):
    """`servicio_continuo.ps1` es idempotente: no duplica lo que está en pie."""
    _beats(tmp_path, T0, solo=("API", "líderes", "captura HFT"))
    _beats(tmp_path, T0, age_s=20 * 60, solo=("bróker simulado",))
    _usage(tmp_path, T0)
    lz = Lanzador()
    out = _check(tmp_path, T0, lz)
    assert out["action"] == "levantar" and out["missing"] == ["bróker simulado"]
    assert lz.calls == 1


def test_dry_run_decide_pero_no_lanza_ni_guarda_estado(tmp_path):
    _beats(tmp_path, T0, age_s=6 * HOUR)
    lz = Lanzador()
    out = _check(tmp_path, T0, lz, dry_run=True)
    assert out["action"] == "simulado" and lz.calls == 0
    assert not (tmp_path / "operation" / "fleet_watch.json").exists()


# --------------------------------------------------------------------------- no entrar en bucle

def test_el_arranque_que_falla_no_entra_en_bucle(tmp_path):
    """Lo que el vigilante del puerto de T140 ya hacía: tope de intentos y espera creciente.

    Se simulan pasadas cada 5 min durante 3 h con el arranque fallando siempre. Sin tope serían
    36 lanzamientos; con él son 4, y después se rinde y avisa."""
    _beats(tmp_path, T0, age_s=6 * HOUR)
    lz = Lanzador(rc=1)
    acciones = []
    for i in range(36):
        acciones.append(_check(tmp_path, T0 + i * 300, lz)["action"])
    assert lz.calls == fleet_watch.MAX_TRIES == 4
    assert acciones.count("levantar") == 4 and acciones.count("esperar") > 0
    assert acciones[-1] == "rendirse"
    # La espera entre intentos crece: 0, 5, 15 y 30 min.
    assert [i for i, a in enumerate(acciones) if a == "levantar"] == [0, 1, 4, 10]
    rows = [json.loads(ln) for ln in
            (tmp_path / "operation" / "logs").glob("op-*.jsonl").__next__()
            .read_text(encoding="utf-8").splitlines()]
    criticas = [r for r in rows if r["event"] == "alerta" and r["level"] == "critical"]
    assert criticas and "hay que mirarlo a mano" in criticas[-1]["title"]


def test_tras_rendirse_lo_vuelve_a_intentar_mucho_despues(tmp_path):
    """Rendirse para siempre dejaría un fallo pasajero convertido en un apagón eterno."""
    _beats(tmp_path, T0, age_s=6 * HOUR)
    lz = Lanzador(rc=1)
    for i in range(20):
        _check(tmp_path, T0 + i * 300, lz)
    assert lz.calls == 4
    assert _check(tmp_path, T0 + 3 * HOUR, lz)["action"] == "rendirse" and lz.calls == 4
    # Pasadas las 6 h de penitencia, una pasada más vuelve a probar.
    out = _check(tmp_path, T0 + 20 * 300 + fleet_watch.GIVE_UP_S + 60, lz)
    assert out["action"] == "levantar" and lz.calls == 5


def test_cuando_vuelve_a_haber_latidos_avisa_y_olvida_los_intentos(tmp_path):
    """Un conjunto que se levanta solo tiene que notarse (entregable 5)."""
    _beats(tmp_path, T0, age_s=6 * HOUR)
    lz = Lanzador(rc=1)
    _check(tmp_path, T0, lz)
    _beats(tmp_path, T0 + 600, age_s=5.0)
    _usage(tmp_path, T0 + 600, age_s=5.0)
    out = _check(tmp_path, T0 + 600, lz)
    # Caído desde el último latido (6 h antes de la primera pasada), no desde que la pasada lo vio.
    assert out["action"] == "recuperado" and out["down_s"] == 6 * HOUR + 600.0
    assert out["missing"] == [*fleet_watch.BEATS, fleet_watch.USAGE]
    st = fleet_watch.State.load(tmp_path / "operation" / "fleet_watch.json")
    assert st.tries == 0 and st.down_since_ms is None and st.gave_up_ms is None
    rows = (tmp_path / "operation" / "logs").glob("op-*.jsonl").__next__()\
        .read_text(encoding="utf-8")
    assert "Resuelta: el conjunto del EIM estaba caído" in rows
    # Y a partir de ahí, silencio.
    assert _check(tmp_path, T0 + 660, lz)["action"] == "ok"


def test_el_estado_roto_no_impide_levantar(tmp_path):
    """Un JSON de estado a medio escribir tras un corte no puede dejar el conjunto caído."""
    p = tmp_path / "operation" / "fleet_watch.json"
    p.parent.mkdir(parents=True)
    p.write_text("{a medio escr", encoding="utf-8")
    _beats(tmp_path, T0, age_s=6 * HOUR)
    lz = Lanzador()
    assert _check(tmp_path, T0, lz)["action"] == "levantar" and lz.calls == 1


def test_el_guion_que_se_lanza_existe_y_es_el_de_siempre():
    """No se inventa un arranque nuevo: corre el mismo script idempotente de T48."""
    p = fleet_watch.script_path()
    assert p.name == "servicio_continuo.ps1" and p.exists()
