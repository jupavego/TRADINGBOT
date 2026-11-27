"""T90, partes puras: ajuste crudo/ajustado, calidad contra calendario, velas de sesión, marcos y
proveedores por capacidades. Sin red, sin disco y sin `exchange_calendars`."""

from __future__ import annotations

import math

import pytest

from eim.core import Candle
from eim.data import adjust, quality, session_bars
from eim.data import timeframes as tf
from eim.data.providers import base, meta
from eim.data.providers.binance import BinanceFutures
from tests.data.t90_helpers import DAY, HOUR, load, ms, weekdays


def _raw_gaps(ts: list[int], step: int) -> list[tuple[int, int]]:
    return [(a + step, b - step) for a, b in zip(ts, ts[1:], strict=False) if b - a > step]


# --- marcos ----------------------------------------------------------------------------------
def test_1d_y_1w_son_de_primera_clase_y_la_api_no_cambia():
    assert tf.TF_MS == {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}
    assert tf.tf_ms("1d") == DAY and tf.tf_ms("1w") == 7 * DAY
    assert "1d" not in tf.STORE_ONLY_TF_MS and "1d" in tf.SESSION_TF_MS
    assert tf.tf_ms("1m") == 60_000 and tf.tf_ms("5m") == 300_000
    with pytest.raises(ValueError):
        tf.tf_ms("1M")                       # mensual: T88 no lo aprobó


def test_la_semana_empieza_el_lunes():
    assert tf.align(ms("2026-01-08T15:00"), "1w") == ms("2026-01-05")   # jueves → lunes
    assert tf.align(ms("2026-01-05"), "1w") == ms("2026-01-05")
    assert tf.align(ms("2026-01-08T15:20"), "1h") == ms("2026-01-08T15:00")


def test_la_escalera_de_los_marcos_de_siempre_no_gana_vecinos():
    assert tf.analysis_ladder("4h") == ["15m", "1h", "4h"]     # el 4 h sigue sin vecino diario
    assert tf.analysis_ladder("1d") == ["15m", "1h", "4h", "1d", "1w"]


# --- proveedores por capacidades ----------------------------------------------------------------
class _Equity:
    """Proveedor de acciones de mentira: velas y eventos corporativos, sin funding."""

    name = "fixture-equity"

    def klines(self, symbol, timeframe, start, end):
        return []

    def corporate_actions(self, symbol, start, end):
        return []


def test_binance_cumple_el_contrato_de_siempre_y_declara_su_ficha():
    b = BinanceFutures()
    assert isinstance(b, base.Provider)
    assert base.capabilities(b) == ("candles", "funding", "open_interest")
    m = meta.meta_of(b)
    assert (m.name, m.coverage, m.rate_limit_per_min) == ("binance-futures", 2, 2400)
    assert "NO VERIFICADOS" in m.license


def test_un_proveedor_cumple_solo_lo_que_tiene():
    p = _Equity()
    assert base.capabilities(p) == ("candles", "corporate_actions")
    assert not isinstance(p, base.Provider)
    m = meta.meta_of(p)                      # no declara ficha: nivel 1, licencia no declarada
    assert m.coverage == 1 and m.license == meta.UNKNOWN_LICENSE and m.delay_ms is None


def test_las_fuentes_antiguas_se_reconocen_por_su_nombre():
    assert meta.lookup("binance futures (fapi/v1/klines)").name == "binance-futures"
    assert meta.lookup("binance-futures").coverage == 2
    assert meta.lookup("yahoo finance 1d (^GSPC)").coverage == 1
    assert "FRED" in meta.lookup("fred").attribution
    with pytest.raises(ValueError):
        meta.SourceMeta(name="x", coverage=4, license="y")


# --- crudo frente a ajustado -------------------------------------------------------------------
def test_accion_con_split_y_dividendo_ajusta_sin_saltos():
    d = load("equity_split_dividend")
    raw, evs = d["candles"], d["events"]
    adj = adjust.adjust_candles(raw, evs)
    assert adj[-1] == raw[-1]                                # la última vela no cambia
    i = next(k for k, c in enumerate(raw) if c.t >= evs[0].t)   # primera vela tras el split
    assert raw[i].o / raw[i - 1].c < 0.3                     # la cruda se desploma un 75 %
    assert abs(adj[i].o / adj[i - 1].c - 1) < 0.02           # la ajustada no salta
    assert raw[i - 1].v * 4 == pytest.approx(adj[i - 1].v)   # volumen × 4 antes del split
    j = next(k for k, c in enumerate(raw) if c.t >= evs[1].t)   # primera vela tras el dividendo
    f = 1 - 0.5 / raw[j - 1].c
    assert adj[j - 1].c == pytest.approx(raw[j - 1].c * f)
    assert adj[0].c == pytest.approx(raw[0].c * f / 4)
    assert adjust.describe(evs) == "1 split, 1 dividendo"
    assert raw == load("equity_split_dividend")["candles"]  # la cruda no se tocó


def test_futuro_con_empalme_queda_continuo():
    d = load("future_roll")
    raw, evs = d["candles"], d["events"]
    adj = adjust.adjust_candles(raw, evs)
    i = next(k for k, c in enumerate(raw) if c.t >= evs[0].t)
    assert raw[i].c / raw[i - 1].c - 1 > 0.025               # el empalme salta un 3 %
    assert abs(adj[i].c / adj[i - 1].c - 1) < 0.005          # ajustada: solo la deriva diaria
    assert adj[i - 1].v == raw[i - 1].v                      # el empalme no toca el volumen


def test_eventos_invalidos_o_imposibles():
    with pytest.raises(ValueError):
        adjust.PriceEvent(t=1)
    with pytest.raises(ValueError):
        adjust.PriceEvent(t=1, split=0)
    c = [Candle(t=0, o=1, h=1, l=1, c=1, v=1), Candle(t=DAY, o=1, h=1, l=1, c=1, v=1)]
    with pytest.raises(ValueError):                          # dividendo mayor que el precio
        adjust.adjust_candles(c, [adjust.PriceEvent(t=DAY, dividend=2.0)])
    # un dividendo anterior a toda la serie no tiene sobre qué actuar
    assert adjust.adjust_candles(c, [adjust.PriceEvent(t=-DAY, dividend=0.1)]) == c


# --- calidad: cerrado frente a roto -------------------------------------------------------------
def test_fx_el_fin_de_semana_es_cierre_y_el_lunes_que_falta_es_hueco():
    d = load("fx_weekend")
    ts = [c.t for c in d["candles"]]
    real, closed = quality.calendar_gaps(_raw_gaps(ts, HOUR), HOUR, weekdays)
    assert real == [tuple(d["missing"])] and closed == 1
    q = quality.assess(ts, [c.c for c in d["candles"]], None, step=HOUR, asof=ts[-1] + HOUR,
                       raw_gaps=_raw_gaps(ts, HOUR), sessions=weekdays, calendar_id="24/5")
    assert q.status == "rota" and q.closed_gaps == 1 and q.missing_bars == 3
    assert q.expected == 48 and q.continuity == pytest.approx(45 / 48)
    assert q.zero_volume is None and q.off_session == 0 and q.stale is False


def test_fx_sin_huecos_solo_cierre_esta_bien():
    d = load("fx_weekend")
    ts = [c.t for c in d["candles"] if c.t < d["missing"][0] or c.t > d["missing"][1]]
    ts = sorted(set(ts) | {d["missing"][0], d["missing"][0] + HOUR, d["missing"][1]})
    q = quality.assess(ts, [1.0] * len(ts), None, step=HOUR, asof=ts[-1] + HOUR,
                       raw_gaps=_raw_gaps(ts, HOUR), sessions=weekdays)
    assert q.status == "ok" and q.closed_gaps == 1 and not q.gaps


def test_cripto_todo_hueco_es_de_verdad():
    d = load("crypto_gap")
    ts = [c.t for c in d["candles"]]
    q = quality.assess(ts, [c.c for c in d["candles"]], [c.v for c in d["candles"]], step=HOUR,
                       asof=ts[-1] + HOUR, raw_gaps=_raw_gaps(ts, HOUR), sessions=None,
                       continuous=True, grace_bars=2)
    assert q.status == "rota" and q.gaps == [tuple(d["gap"])] and q.missing_bars == 5
    assert q.closed_gaps == 0 and q.zero_volume == 0 and q.n_jumps == 0
    src, cov = quality.marks("candles", q)
    assert src["quality:candles"].startswith("rota: 1 huecos con mercado abierto (5 velas)")
    assert cov["quality:candles"] == (ts[0], ts[-1])


def test_obsoleta_segun_la_cadencia_de_su_clase():
    ts = [ms("2026-01-05") + k * HOUR for k in range(48)]
    kw = dict(step=HOUR, raw_gaps=[], sessions=None, continuous=True, grace_bars=2)
    fresh = quality.assess(ts, [1.0] * 48, None, asof=ts[-1] + 2 * HOUR, **kw)
    old = quality.assess(ts, [1.0] * 48, None, asof=ts[-1] + 4 * HOUR, **kw)
    assert fresh.stale is False and old.stale is True and old.status == "obsoleta"
    # FX el sábado: el viernes cerró a medianoche y no se esperaba nada más
    fri = [ms("2026-01-09") + k * HOUR for k in range(24)]
    sat = quality.assess(fri, [1.0] * 24, None, step=HOUR, asof=ms("2026-01-10T18:00"),
                         raw_gaps=[], sessions=weekdays)
    assert sat.stale is False and sat.status == "ok"


def test_sin_calendario_no_se_adivina():
    ts = [0, HOUR, 5 * HOUR]
    q = quality.assess(ts, [1.0] * 3, None, step=HOUR, asof=6 * HOUR,
                       raw_gaps=_raw_gaps(ts, HOUR), sessions=None)
    assert q.status == "desconocida" and q.stale is None
    assert any("sin juzgar" in f for f in q.flags)


def test_saltos_anomalos_y_velas_fuera_de_sesion():
    ts = [ms("2026-01-05") + k * HOUR for k in range(60)]
    cs = [100.0 + (k % 3) for k in range(60)]
    cs[30] = 180.0
    q = quality.assess(ts, cs, None, step=HOUR, asof=ts[-1] + HOUR, raw_gaps=[],
                       sessions=None, continuous=True)
    assert q.n_jumps == 2 and q.jumps == [ts[30], ts[31]]
    sat = [ms("2026-01-10") + k * HOUR for k in range(3)]       # sábado: FX cerrado
    q2 = quality.assess(sat, [1.0] * 3, None, step=HOUR, asof=sat[-1] + HOUR, raw_gaps=[],
                        sessions=weekdays)
    assert q2.off_session == 3 and any("zona horaria" in f for f in q2.flags)


# --- velas de sesión ----------------------------------------------------------------------------
def _nyse_winter(start: int, end: int):
    """Sesiones 14:30-21:00 UTC de lunes a viernes (NYSE en invierno, sin festivos)."""
    out = []
    for s in weekdays(start - DAY, end + DAY):
        day = s.open_t - s.open_t % DAY
        o, c = day + 14 * HOUR + 30 * 60_000, day + 21 * HOUR
        lo, hi = max(o, start), min(c, end)
        if hi > lo:
            out.append(type(s)(lo, hi))
    return out


def test_agregar_a_sesion_y_a_semana():
    cs = [Candle(t=ms("2026-01-05") + k * 1_800_000, o=1, h=2, l=0.5, c=1.5, v=1)
          for k in range(48 * 7)]
    days = session_bars.aggregate(cs, "1d", sessions=_nyse_winter, asof=ms("2026-01-09T20:00"))
    assert [c.t for c in days] == [ms(f"2026-01-0{d}T14:30") for d in (5, 6, 7, 8)]
    assert days[0].v == 13                     # 6,5 h de velas de 30 min; el viernes sigue abierto
    weeks = session_bars.aggregate(cs, "1w", sessions=_nyse_winter)
    assert [(c.t, c.v) for c in weeks] == [(ms("2026-01-05T14:30"), 65)]
    utc = session_bars.aggregate(cs, "1d", asof=ms("2026-01-12"))     # 24/7: días UTC
    assert len(utc) == 7 and utc[0].t == ms("2026-01-05") and utc[0].v == 48
    with pytest.raises(ValueError):
        session_bars.aggregate(cs, "4h")


def test_la_vela_de_sesion_cierra_con_su_sesion():
    cut = session_bars.closed_before("1d", ms("2026-01-08T15:00"), _nyse_winter)
    assert cut == ms("2026-01-08")                          # la del jueves sigue abierta
    cut = session_bars.closed_before("1d", ms("2026-01-08T22:00"), _nyse_winter)
    assert ms("2026-01-08T14:30") < cut <= ms("2026-01-08T22:00") + 1   # ya cerró
    assert session_bars.closed_before("1h", 10 * HOUR) == 9 * HOUR + 1  # regla de siempre
    assert session_bars.closed_before("1d", 10 * DAY) == 9 * DAY + 1
    assert math.isfinite(session_bars.closed_before("1w", ms("2026-01-10T12:00"), _nyse_winter))
