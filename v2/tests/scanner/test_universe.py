"""T93 — etapas 1 y 2 del embudo: cada exclusión con su motivo y su contador."""

from __future__ import annotations

import importlib.util

import pytest

from eim.instruments.models import (
    AssetClass,
    EventKind,
    InstrumentEvent,
    InstrumentStatus,
    SessionKind,
    TradableLevel,
)
from eim.scanner import universe
from eim.scanner.params import ScannerParams
from eim.scanner.universe import REASONS, DataStats
from tests.scanner._helpers import DAY, T0, perp

ASOF = T0 + 101 * DAY + 3_600_000            # la vela de T0+100d cerró a las 00:00 de T0+101d
P = ScannerParams()


def good(last_t: int = T0 + 100 * DAY, **kw) -> DataStats:
    base = {"n_bars": 90, "last_t": last_t, "last_close": 100.0,
            "median_quote_volume": 5e6, "spread_bps": None}
    return DataStats(**(base | kw))


def test_stage1_reasons_are_written_and_counted():
    insts = [perp("BTCUSDT"), perp("OLDUSDT", status=InstrumentStatus.DELISTED),
             perp("BTCUSDT_260327", expiry=T0 + 200 * DAY),
             perp("ETHUSDC", currency="USDC"), perp("OPENAIUSDT"),
             perp("XYZUSDT", level=TradableLevel.RESEARCH),
             perp("DEADUSDT", expiry=T0 - DAY)]
    kept, out = universe.stage1(insts, P.model_copy(update={"min_level": 2}), ASOF)
    assert [i.symbol for i in kept] == ["BTCUSDT"]
    why = {e.instrument_id.rsplit(".", 1)[1]: e.reason for e in out}
    assert why == {"OLDUSDT": "estado", "BTCUSDT_260327": "no_perpetuo", "ETHUSDC": "moneda",
                   "OPENAIUSDT": "pre_opv", "XYZUSDT": "nivel", "DEADUSDT": "vencido"}
    assert all(e.stage == 1 and e.detail for e in out)
    assert set(why.values()) <= set(REASONS)


def test_other_venues_are_not_part_of_the_universe_nor_excluded():
    other = perp("BTCUSDT").model_copy(update={"venue": "otra"})
    kept, out = universe.stage1([other], P, ASOF)
    assert kept == [] and out == []


def test_stage2_data_filters():
    insts = [perp(s) for s in ("OKUSDT", "NODATAUSDT", "FEWUSDT", "OLDUSDT", "THINUSDT",
                               "WIDEUSDT", "ZEROUSDT")]
    ids = {i.symbol: i.id for i in insts}
    stats = {ids["OKUSDT"]: good(), ids["FEWUSDT"]: good(n_bars=30),
             ids["OLDUSDT"]: good(last_t=T0 + 90 * DAY),
             ids["THINUSDT"]: good(median_quote_volume=10_000.0),
             ids["WIDEUSDT"]: good(spread_bps=55.0), ids["ZEROUSDT"]: good(last_close=0.0)}
    kept, out, notes = universe.stage2(insts, stats, P, DAY, ASOF)
    assert [i.symbol for i in kept] == ["OKUSDT"]
    why = {e.instrument_id.rsplit(".", 1)[1]: e.reason for e in out}
    assert why == {"NODATAUSDT": "sin_datos", "FEWUSDT": "pocas_velas", "OLDUSDT": "dato_viejo",
                   "THINUSDT": "liquidez", "WIDEUSDT": "spread", "ZEROUSDT": "precio_invalido"}
    assert notes["spread_sin_medir"] == 1             # el que pasó no tenía cotización: se dice


def test_freshness_grace_is_per_asset_class():
    crypto, gold = perp("AUSDT"), perp("XAUUSDT", asset_class=AssetClass.COMMODITY)
    two_days_old = good(last_t=T0 + 98 * DAY)          # faltan 2 velas cerradas
    st = {crypto.id: two_days_old, gold.id: two_days_old}
    kept, out, _ = universe.stage2([crypto, gold], st, P, DAY, ASOF)
    assert [i.symbol for i in kept] == ["AUSDT"]       # cripto: margen 2; el resto: 1
    assert out[0].reason == "dato_viejo" and "margen 1" in out[0].detail


def test_spread_can_be_required():
    inst = perp("AUSDT")
    p = P.model_copy(update={"require_spread": True})
    _, out, _ = universe.stage2([inst], {inst.id: good()}, p, DAY, ASOF)
    assert out[0].reason == "spread_sin_medir"


def test_liquidity_floor_scales_with_the_timeframe():
    inst = perp("AUSDT")
    hourly = good(last_t=(ASOF // 3_600_000 - 1) * 3_600_000, median_quote_volume=50_000.0)
    kept, _, _ = universe.stage2([inst], {inst.id: hourly}, P, 3_600_000, ASOF)
    assert kept                                         # 1 M/día ≈ 41 667 por vela de 1 h


def test_closed_market_is_not_scanned(monkeypatch):
    inst = perp("SPYUSDT", calendar_id="XNYS", session=SessionKind.EXCHANGE_HOURS,
                asset_class=AssetClass.ETF)
    monkeypatch.setattr(universe.calendars, "is_open", lambda *_a, **_k: False)
    _, out, _ = universe.stage2([inst], {inst.id: good()}, P, DAY, ASOF)
    assert out[0].reason == "mercado_cerrado"


def test_calendar_unavailable_is_an_exclusion_not_a_guess(monkeypatch):
    from eim.instruments.calendar_specs import CalendarUnavailable

    inst = perp("SPYUSDT", calendar_id="XNYS", session=SessionKind.EXCHANGE_HOURS,
                asset_class=AssetClass.ETF)

    def nope(*_a, **_k):
        raise CalendarUnavailable("sin exchange_calendars")
    monkeypatch.setattr(universe.calendars, "is_open", nope)
    _, out, _ = universe.stage2([inst], {inst.id: good()}, P, DAY, ASOF)
    assert out[0].reason == "calendario" and "exchange_calendars" in out[0].detail


@pytest.mark.skipif(importlib.util.find_spec("exchange_calendars") is None,
                    reason="sin el extra `calendars` (exchange_calendars)")
def test_a_weekend_is_not_stale_for_an_exchange_calendar():
    inst = perp("SPYUSDT", calendar_id="XNYS", session=SessionKind.EXCHANGE_HOURS,
                asset_class=AssetClass.ETF)
    friday = 1_767_916_800_000                # 2026-01-09 (viernes) 00:00 UTC
    monday_open = friday + 3 * DAY + 15 * 3_600_000      # lunes 15:00 UTC, abierta
    gap = universe.missing_bars(inst, DAY, friday, monday_open)
    assert gap == 0                           # sábado y domingo no son velas que falten


def test_lifecycle_counts_recent_listings_and_delistings():
    evs = [InstrumentEvent(instrument_id="crypto.binance.usdm.NEWUSDT", kind=EventKind.LISTED,
                           t=ASOF - DAY),
           InstrumentEvent(instrument_id="crypto.binance.usdm.OLDUSDT",
                           kind=EventKind.DELISTED, t=ASOF - 2 * DAY),
           InstrumentEvent(instrument_id="crypto.binance.usdm.ANCIENT", kind=EventKind.LISTED,
                           t=ASOF - 30 * DAY)]
    got = universe.lifecycle(evs, ASOF, 7)
    assert got == {"delisted": ["crypto.binance.usdm.OLDUSDT"],
                   "listed": ["crypto.binance.usdm.NEWUSDT"]}


def test_filter_universe_reports_counts_by_reason_and_stage():
    insts = [perp("AUSDT"), perp("BUSDT"), perp("OPENAIUSDT")]
    st = {insts[0].id: good(), insts[1].id: good(median_quote_volume=1.0)}
    res = universe.filter_universe(insts, st, P, DAY, ASOF)
    assert [i.symbol for i in res.included] == ["AUSDT"]
    assert res.counts == {"liquidez": 1, "pre_opv": 1}
    assert res.stage_counts() == {1: 1, 2: 1}


def test_closed_cut_follows_the_weekly_grid():
    week, off = 7 * DAY, 4 * DAY                       # la semana empieza el lunes
    monday = T0 + 4 * DAY                              # 2026-01-05
    assert universe.closed_cut(week, monday + 3 * DAY, off) == monday
    assert universe.closed_cut(DAY, T0 + DAY + 5) == T0 + DAY
