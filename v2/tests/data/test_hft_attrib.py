"""T148 E3: un proceso muerto no se parece a un exchange callado.

Con la regla de T147, la hora 2026-11-09T17 —truncada porque nuestro proceso murió a las 17:55—
salía «ajena»: sus dos únicas marcas eran `silencio` y no hubo ningún reinicio. La señal que los
separa es el tiempo perdido que NADIE marcó: cuando el exchange calla, el recolector está vivo y lo
anota; cuando el proceso muere, no queda nadie para anotar.

Las cifras de `test_la_hora_real_del_apagon_*` son las del JSON de QC de verdad de esa hora
(`book_usable` 0,9228, cobertura máxima 0,9244, dos tramos `silencio` de 4,3 y 5,0 s solapados).
"""

from __future__ import annotations

from eim.data.collectors import hft_attrib
from eim.data.collectors.hft_read import parse_hour
from eim.data.collectors.hft_schema import HOUR_NS

H17 = parse_hour("2026-11-09T17")


def _rep(hour: int, cov: float, gaps: list[tuple[float, float, str]] | None = None, **kw) -> dict:
    """Un informe de QC con la cobertura dada y tramos marcados en segundos desde la hora."""
    h0 = hour * HOUR_NS
    marks = [{"stream": s, "cause": s if s in ("silencio", "desconexion") else "silencio",
              "start_ns": int(h0 + a * 1e9), "end_ns": int(h0 + b * 1e9)}
             for a, b, s in (gaps or [])]
    causes: dict[str, int] = {}
    for m in marks:
        causes[m["cause"]] = causes.get(m["cause"], 0) + 1
    return {"hour_index": hour, "complete": False, "book_usable": cov, "restarts": 0, "runs": 1,
            "overflow_dropped": 0, "clock": {"jumps": 0},
            "streams": {"depth": {"coverage": cov}, "bbo": {"coverage": cov},
                        "trades": {"coverage": cov * 0.9}, "mark": {"coverage": cov},
                        "liq": {"msgs": 3}},
            "holes": {"found": len(marks), "undetected": 0},
            "gaps_marked": {"by_cause": causes, "list": marks}, **kw}


def test_la_hora_real_del_apagon_se_atribuye_a_causa_nuestra():
    """El caso que abrió T148: 267 s perdidos que ninguna marca explica."""
    rep = _rep(H17, 0.9244, [(3250.0, 3254.3, "silencio"), (3249.4, 3254.5, "silencio")])
    assert round(hft_attrib.unmarked_s(rep), 0) == 267
    assert hft_attrib.attribute(rep, H17) == "nuestra"
    assert "ningún tramo marcado" in hft_attrib.why(rep, H17)


def test_el_exchange_callado_sigue_siendo_ajeno():
    """Mismo síntoma por fuera (cobertura al 92 %) pero el recolector lo marcó todo: ajena."""
    rep = _rep(H17, 0.9244, [(600.0, 600.0 + 276.2, "silencio")])
    assert hft_attrib.unmarked_s(rep) < 1.0
    assert hft_attrib.attribute(rep, H17) == "ajena"
    assert "solo tramos del exchange" in hft_attrib.why(rep, H17)


def test_los_tramos_que_se_solapan_cuentan_una_vez():
    """Sumarlos explicaría más tiempo del que falta y taparía un corte de verdad.

    El mismo silencio deja marca en `depth` y en `mark`: 150 s cada una, 160 s de unión. Faltan
    400 s, así que con la unión quedan 240 s sin explicar (nuestra) y sumándolas solo 100
    (ajena), que es precisamente el corte que no se debe tapar."""
    solapados = _rep(H17, 0.8889, [(600.0, 750.0, "silencio"), (610.0, 760.0, "silencio")])
    assert round(hft_attrib.unmarked_s(solapados)) == 240
    assert hft_attrib.attribute(solapados, H17) == "nuestra"


def test_una_hora_sin_json_de_qc_es_nuestra():
    """Si no hay informe es porque no había quien lo escribiera (ya era así en T147)."""
    assert hft_attrib.attribute(None, H17) == "nuestra"
    assert "no había quien lo escribiera" in hft_attrib.why(None, H17)


def test_una_hora_que_el_registro_de_consumo_no_vio_es_nuestra():
    """El registro de consumo es otro de los cinco: si él tampoco estaba, faltó el equipo."""
    rep = _rep(H17, 0.98, [(600.0, 600.0 + 72.0, "silencio")])
    assert hft_attrib.attribute(rep, H17) == "ajena"
    assert hft_attrib.attribute(rep, H17, blind_hours={H17}) == "nuestra"
    assert "el registro de consumo tampoco" in hft_attrib.why(rep, H17, blind_hours={H17})


def test_el_mantenimiento_declarado_manda_sobre_todo_lo_demas():
    """Un corte previsto no es deuda de nadie, aunque el proceso muriera dentro."""
    maint = [{"from_h": H17, "to_h": H17}]
    assert hft_attrib.attribute(_rep(H17, 0.10), H17, maint) == "mantenimiento"
    assert hft_attrib.attribute(None, H17, maint) == "mantenimiento"


def test_una_hora_casi_perfecta_no_se_culpa_a_nadie_por_el_ruido():
    """El umbral sale de medir: ninguna hora completa de las 241 auditadas pasa de 28,8 s."""
    rep = _rep(H17, 0.9917, [])            # 30 s sin cobertura y sin marcas
    assert 29 < hft_attrib.unmarked_s(rep) < 31
    assert hft_attrib.attribute(rep, H17) == "sin causa"


def test_un_reinicio_sigue_siendo_nuestro():
    """Las señales de T147 no se pierden al añadir la nueva."""
    assert hft_attrib.attribute(_rep(H17, 0.999, [], restarts=1), H17) == "nuestra"
    assert hft_attrib.attribute(_rep(H17, 0.999, [], overflow_dropped=5), H17) == "nuestra"
    assert hft_attrib.attribute(
        _rep(H17, 0.999, [], clock={"jumps": 2}), H17) == "nuestra"


def test_sin_flujos_no_se_inventa_nada():
    """Un JSON viejo o recortado no debe convertirse en una acusación."""
    assert hft_attrib.unmarked_s({"hour_index": H17}) == 0.0
    assert hft_attrib.unmarked_s({"streams": {"depth": {"coverage": 0.1}}}) == 0.0
