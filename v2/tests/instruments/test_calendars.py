"""Calendarios de mercado (T89): festivo, media jornada, cambio de hora y fin de semana.

La aceptación de T89 pide que el calendario distinga «cerrado» de «sin datos» en un caso de
acciones y uno de FX: son `test_acciones_festivo_*` y `test_fx_*`.
"""

from __future__ import annotations

import datetime as dt
import importlib.util

import pytest

from eim.instruments import calendars as cal
from eim.instruments import registry

DAY = cal.DAY_MS
HOUR = 3_600_000
#: `24/7` se calcula aquí y se prueba siempre; los calendarios de bolsa necesitan el extra
#: `calendars` (`exchange_calendars`, ◆ T88 §1), que no está en todos los equipos.
needs_xcals = pytest.mark.skipif(
    importlib.util.find_spec("exchange_calendars") is None,
    reason="calendarios de bolsa: extra `calendars` (◆ T88 §1)")


def ms(iso: str) -> int:
    return int(dt.datetime.fromisoformat(iso).replace(tzinfo=dt.UTC).timestamp() * 1000)


def utc(t: int) -> str:
    return dt.datetime.fromtimestamp(t / 1000, tz=dt.UTC).isoformat()


# --- 24/7: regla propia, sin librería ------------------------------------
def test_24_7_siempre_abierto_y_sin_libreria():
    sp = cal.spec(cal.ALWAYS)
    assert sp.native and sp.xcals_name is None
    assert cal.is_open(cal.ALWAYS, ms("2026-01-03T03:00"))      # un sábado
    assert cal.next_open(cal.ALWAYS, ms("2026-01-03T03:00")) == ms("2026-01-03T03:00")


def test_24_7_barras_esperadas():
    assert cal.expected_bars(cal.ALWAYS, HOUR, ms("2026-01-03"), ms("2026-01-04")) == 24
    assert cal.expected_bars(cal.ALWAYS, DAY, ms("2026-01-03"), ms("2026-01-10")) == 7
    assert cal.expected_bars(cal.ALWAYS, 4 * HOUR, ms("2026-01-03"), ms("2026-01-04")) == 6


def test_ventana_vacia_o_invertida():
    assert cal.sessions(cal.ALWAYS, ms("2026-01-03"), ms("2026-01-03")) == []
    with pytest.raises(ValueError):
        cal.expected_bars(cal.ALWAYS, 0, ms("2026-01-03"), ms("2026-01-04"))


# --- acciones: cerrado frente a sin datos --------------------------------
@needs_xcals
def test_acciones_festivo_es_cerrado():
    """2026-07-03: el 4 de julio cae sábado y la NYSE cierra el viernes anterior."""
    a = cal.classify_absence(registry.SP500, DAY, ms("2026-07-03"), ms("2026-07-04"))
    assert a.kind == "closed" and a.closed and a.expected == 0
    assert a.calendar_id == "XNYS" and "exchange_calendars" in a.source


@needs_xcals
def test_acciones_dia_habil_sin_datos_es_sin_datos():
    a = cal.classify_absence(registry.SP500, DAY, ms("2026-07-02"), ms("2026-07-03"))
    assert a.kind == "missing" and a.expected == 1 and not a.closed


@needs_xcals
def test_acciones_dia_habil_con_su_vela_esta_completo():
    a = cal.classify_absence(registry.SP500, DAY, ms("2026-07-02"), ms("2026-07-03"), observed=1)
    assert a.kind == "complete"


@needs_xcals
def test_acciones_semana_con_festivo_espera_cuatro_sesiones():
    # lunes 2026-11-23 a sábado: jueves 26 es Acción de Gracias.
    assert cal.expected_bars(registry.SP500, DAY, ms("2026-11-23"), ms("2026-11-28")) == 4


@needs_xcals
def test_media_jornada_se_ve_en_las_barras_intradia():
    """El viernes después de Acción de Gracias la NYSE cierra a las 13:00 de Nueva York."""
    media = cal.sessions(registry.SP500, ms("2026-11-27"), ms("2026-11-28"))
    assert len(media) == 1
    assert utc(media[0].open_t) == "2026-11-27T14:30:00+00:00"
    assert utc(media[0].close_t) == "2026-11-27T18:00:00+00:00"
    assert cal.expected_bars(registry.SP500, HOUR, ms("2026-11-27"), ms("2026-11-28")) == 3
    assert cal.expected_bars(registry.SP500, HOUR, ms("2026-11-25"), ms("2026-11-26")) == 6


@needs_xcals
def test_cambio_de_hora_mueve_la_apertura_en_utc():
    """EE. UU. adelanta el reloj el 2026-03-08: la apertura pasa de 14:30 a 13:30 UTC."""
    antes = cal.sessions(registry.SP500, ms("2026-03-06"), ms("2026-03-07"))[0]
    despues = cal.sessions(registry.SP500, ms("2026-03-09"), ms("2026-03-10"))[0]
    assert utc(antes.open_t) == "2026-03-06T14:30:00+00:00"
    assert utc(despues.open_t) == "2026-03-09T13:30:00+00:00"
    assert antes.ms == despues.ms == 6 * HOUR + 1800_000


@needs_xcals
def test_sesiones_se_recortan_a_la_ventana():
    s = cal.sessions(registry.SP500, ms("2026-11-25T16:00"), ms("2026-11-25T17:00"))
    assert s == [cal.Session(ms("2026-11-25T16:00"), ms("2026-11-25T17:00"))]


# --- FX: fin de semana y el aviso que lleva ------------------------------
@needs_xcals
def test_fx_sabado_es_cerrado():
    a = cal.classify_absence(cal.WEEKDAYS, DAY, ms("2026-01-03"), ms("2026-01-04"))
    assert a.kind == "closed" and a.expected == 0


@needs_xcals
def test_fx_lunes_sin_datos_es_sin_datos():
    a = cal.classify_absence(cal.WEEKDAYS, DAY, ms("2026-01-05"), ms("2026-01-06"))
    assert a.kind == "missing" and a.expected == 1


@needs_xcals
def test_fx_next_open_salta_el_fin_de_semana():
    assert cal.next_open(cal.WEEKDAYS, ms("2026-01-03T12:00")) == ms("2026-01-05T00:00")


@needs_xcals
def test_fx_declara_que_no_conoce_festivos():
    """`24/5` es una convención de días hábiles: el aviso viaja con la respuesta."""
    a = cal.classify_absence(cal.WEEKDAYS, DAY, ms("2026-12-25"), ms("2026-12-26"))
    assert a.kind == "missing"                      # Navidad en viernes: lo da por abierto
    assert any("festivos" in w for w in a.warnings)


# --- dos calendarios por instrumento (T88) -------------------------------
@needs_xcals
def test_el_perpetuo_tradfi_no_cierra_aunque_su_subyacente_si():
    """Sábado 2026-07-04: el contrato de Binance negocia y CME está cerrada."""
    xau = registry.XAUUSDT
    t = ms("2026-07-04T15:00")
    assert cal.is_open(xau, t) is True
    assert cal.is_open(xau, t, underlying=True) is False
    assert cal.expected_bars(xau, HOUR, ms("2026-07-04"), ms("2026-07-05")) == 24
    assert cal.expected_bars(xau, HOUR, ms("2026-07-04"), ms("2026-07-05"),
                             underlying=True) == 0


@needs_xcals
def test_el_hueco_del_contrato_y_el_del_subyacente_se_clasifican_distinto():
    """24 velas del contrato sin datos son «sin datos»; en el subyacente, «cerrado»."""
    xau = registry.XAUUSDT
    ini, fin = ms("2026-07-04"), ms("2026-07-05")
    assert cal.classify_absence(xau, HOUR, ini, fin).kind == "missing"
    assert cal.classify_absence(xau, HOUR, ini, fin, underlying=True).kind == "closed"


@needs_xcals
def test_cierre_adelantado_del_subyacente():
    """2026-07-03 CME cierra a las 17:00 UTC en vez de a las 22:00: menos barras esperadas."""
    xau = registry.XAUUSDT
    ini, fin = ms("2026-07-03"), ms("2026-07-04")
    assert cal.expected_bars(xau, HOUR, ini, fin, underlying=True) == 17
    assert cal.expected_bars(xau, HOUR, ini, fin) == 24


def test_sin_calendario_de_subyacente_no_se_afirma_nada():
    with pytest.raises(cal.CalendarUnavailable, match="subyacente"):
        cal.is_open(registry.BTCUSDT, ms("2026-07-03T15:00"), underlying=True)


@needs_xcals
def test_las_sesiones_cruzan_el_fin_de_anio():
    """El calendario se cachea por años enteros: una ventana a caballo no se queda corta."""
    s = cal.sessions(registry.SP500, ms("2026-12-30"), ms("2027-01-05"))
    dias = {utc(x.open_t)[:10] for x in s}
    assert dias == {"2026-12-30", "2026-12-31", "2027-01-04"}   # 1 de enero: festivo


@needs_xcals
@pytest.mark.perf
def test_barrer_un_anio_de_ventanas_no_reconstruye_el_calendario():
    """`find_gaps` (T90) barre miles de ventanas: construir el calendario cuesta ~1,5 s y solo
    puede pasar una vez por año pedido."""
    import time

    cal.sessions(registry.SP500, ms("2026-01-01"), ms("2026-01-02"))     # calienta la caché
    t0 = time.perf_counter()
    for d in range(365):
        base = ms("2026-01-01") + d * DAY
        cal.expected_bars(registry.SP500, DAY, base, base + DAY)
    assert time.perf_counter() - t0 < 3.0


# --- registro de calendarios ---------------------------------------------
def test_calendario_desconocido_levanta():
    with pytest.raises(cal.CalendarUnavailable, match="no registrado"):
        cal.spec("XBOGOTA")


@needs_xcals
def test_todos_los_registrados_se_pueden_contestar_aqui():
    assert all(cal.available().values())


def test_cada_ficha_declara_su_fuente():
    for sp in cal.CALENDARS.values():
        assert sp.source and sp.tz
        assert sp.native or sp.xcals_name
