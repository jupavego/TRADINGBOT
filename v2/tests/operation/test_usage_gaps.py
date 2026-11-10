"""T148 E2: el registro de consumo detecta su propio silencio.

El caso que lo motiva es real: el 2026-11-09 `usage incidents --days 1` daba cero incidentes
después de las 17:00 porque el registro murió con los demás a las 17:55:45. Aquí se comprueba que
la ausencia de muestras se declara por sí sola, con su duración y sus bordes, y que no se inventa
un apagón donde solo falta instalación.
"""

from __future__ import annotations

import json

from eim.operation import usage_gaps, usage_incidents, usage_summary

BASE = 1_794_225_600_000          # 2026-11-09 12:00:00 UTC
HOUR = 3_600_000


def _s(t_ms: int, cpu: float = 40.0) -> dict:
    """Una muestra del registro, con lo que `_edge` mira."""
    import time
    return {"t": t_ms, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t_ms / 1000)),
            "dt_s": 30.0, "machine": {"cpu": cpu, "ram_free_mb": 3000, "commit_mb": 30000},
            "eim": {"n": 9, "cpu": 10.0, "ram_mb": 900.0},
            "roles": {"api": {"n": 1, "cpu": 1.0, "ram_mb": 300.0, "commit_mb": 400.0, "prio": 6}},
            "others": [], "hft": {"queue": 1}, "api_beat_age_s": 2.8}


def _serie(n: int, every_ms: int = 30_000, t0: int = BASE) -> list[dict]:
    return [_s(t0 + i * every_ms) for i in range(n)]


def test_el_hueco_entre_muestras_es_un_incidente_con_sus_bordes():
    """Lo que un proceso muerto no puede anotar se deduce después de su ausencia."""
    antes, despues = _serie(10), _serie(10, t0=BASE + 10 * 30_000 + 5 * HOUR)
    g = usage_gaps.gaps(antes + despues)
    assert len(g) == 1
    inc = usage_gaps.as_incidents(g)[0]
    assert inc["kind"] == "apagon_registro" and inc["samples"] == 0
    assert inc["dur_s"] == 5 * 3600 + 30     # del último latido al primero de la vuelta
    assert inc["edges"]["last_before"]["ts"] == antes[-1]["ts"]
    assert inc["edges"]["first_after"]["ts"] == despues[0]["ts"]
    assert inc["edges"]["last_before"]["machine"]["ram_free_mb"] == 3000
    assert inc["edges"]["last_before"]["services"] == ["api"]


def test_un_tropiezo_corto_no_es_un_apagon():
    """Una muestra perdida pasa; diez seguidas (5 min) ya no."""
    serie = [*_serie(5), *_serie(5, t0=BASE + 5 * 30_000 + 90_000)]
    assert usage_gaps.gaps(serie) == []
    largo = [*_serie(5), *_serie(5, t0=BASE + 5 * 30_000 + 400_000)]
    assert len(usage_gaps.gaps(largo)) == 1


def test_antes_de_la_primera_muestra_no_se_declara_nada():
    """Que no haya registro de ayer no significa que se cayera: no estaba instalado."""
    assert usage_gaps.gaps([]) == []
    assert usage_gaps.gaps([], until_ms=BASE + 10 * HOUR) == []
    assert usage_gaps.coverage([], BASE, BASE + HOUR)["coverage"] == 0.0


def test_un_registro_que_callo_y_no_ha_vuelto_da_un_apagon_abierto():
    """El apagón que está pasando: `after` a None y se dice que sigue callado."""
    g = usage_gaps.gaps(_serie(10), until_ms=BASE + 4 * HOUR)
    assert len(g) == 1 and g[0]["after"] is None
    inc = usage_gaps.as_incidents(g)[0]
    assert "sigue callado" in inc["detail"] and inc["edges"]["first_after"] is None


def test_las_horas_que_tapa_un_hueco_quedan_marcadas_como_ciegas():
    """Es lo que la atribución necesita para no culpar al exchange (T148 E3)."""
    g = usage_gaps.gaps([_s(BASE + 59 * 60_000), _s(BASE + 59 * 60_000 + 3 * HOUR)])
    horas = usage_gaps.blind_hours(g)
    h0 = BASE // HOUR
    assert horas == {h0, h0 + 1, h0 + 2, h0 + 3}
    # Un hueco que solo roza una hora por menos de un minuto no la deja ciega.
    rozado = usage_gaps.gaps([_s(BASE + 3_599_000), _s(BASE + 3_599_000 + 400_000)])
    assert usage_gaps.blind_hours(rozado) == {h0 + 1}


def test_la_cobertura_del_dia_descuenta_el_apagon():
    """Un día con 5 horas en blanco no se lee como si estuviera medido."""
    dia0 = BASE - 12 * HOUR                        # 2026-11-09 00:00 UTC
    serie = [*_serie(10, t0=dia0), *_serie(10, t0=dia0 + 5 * HOUR)]
    cov = usage_gaps.coverage(serie, dia0, dia0 + 24 * HOUR)
    assert cov["blind_s"] > 23 * 3600 and cov["coverage"] < 0.05
    assert len(cov["gaps"]) == 1 and cov["gaps"][0]["dur_s"] == 5 * 3600 - 270


def test_usage_incidents_declara_el_apagon_junto_a_los_demas(tmp_path):
    """La prueba de lo que faltaba: sin registro de operación que leer, el hueco igual sale."""
    d = tmp_path / "usage"
    d.mkdir(parents=True)
    serie = [*_serie(10), *_serie(10, t0=BASE + 6 * HOUR)]
    with (d / "2026-11-09.jsonl").open("w", encoding="utf-8") as f:
        for r in serie:
            f.write(json.dumps(r) + "\n")
    rows = usage_incidents.report(tmp_path, ["2026-11-09"], until_ms=BASE + 7 * HOUR)
    # Dos: el hueco de 6 h que ya se cerró y el que sigue abierto hasta ahora.
    assert [r["kind"] for r in rows] == ["apagon_registro", "apagon_registro"]
    assert rows[0]["dur_s"] == 6 * 3600 - 270 and rows[0]["edges"]["first_after"] is not None
    assert rows[1]["edges"]["first_after"] is None
    dia = usage_summary.day_summary(serie, "2026-11-09", until_ms=BASE + 7 * HOUR)
    assert dia["samples"] == 20 and dia["blind_s"] > 5 * 3600


def test_el_umbral_ve_un_apagon_corto_y_no_un_atasco_bajo_carga():
    """Calibrado con casos reales: el apagón del 2026-11-10 00:33:49, que el parche provisional
    levantó en minutos, dejó 284 s sin muestras (un umbral de 300 s no lo veía); el peor atasco del
    propio registro bajo carga, el 2026-11-05, fue de 182 s y no es un apagón."""
    apagon = [_s(BASE), _s(BASE + 284_000)]
    atasco = [_s(BASE), _s(BASE + 182_000)]
    assert [g["t1"] - g["t0"] for g in usage_gaps.gaps(apagon)] == [284_000]
    assert usage_gaps.gaps(atasco) == []
