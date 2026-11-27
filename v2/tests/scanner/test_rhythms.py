"""T93 — ritmos: el rápido avisa sobre lo ya puntuado sin mirar mercados cerrados ni
cotizaciones viejas; el profundo pasa la lista corta a la cola con su huella de datos."""

from __future__ import annotations

import math

from eim.instruments.models import AssetClass, SessionKind
from eim.scanner import rhythms as R
from eim.scanner.params import ScannerParams
from tests.scanner._helpers import T0, perp

P = ScannerParams()
NOW = T0 + 50_000_000


def row(inst, close=100.0, vol=0.02):
    return {"instrument_id": inst.id, "last_close": close, "metrics": {"vol_20": vol}}


def test_price_and_spread_alerts():
    a, b, c = perp("AUSDT"), perp("BUSDT"), perp("CUSDT")
    up = 100 * math.exp(0.05)                                 # +2,5 σ con vol 0,02
    quotes = {"AUSDT": (up - 0.01, up + 0.01, NOW), "BUSDT": (100.0, 100.01, NOW),
              "CUSDT": (99.0, 101.0, NOW)}                    # 200 pb de diferencial
    res = R.fast_pass([row(a), row(b), row(c)], quotes, {i.id: i for i in (a, b, c)}, NOW, P)
    got = {(x["instrument_id"].rsplit(".", 1)[1], x["kind"]) for x in res.alerts}
    assert got == {("AUSDT", "precio"), ("CUSDT", "spread")} and res.checked == 3
    price = next(x for x in res.alerts if x["kind"] == "precio")
    assert price["value"] == round(0.05 / 0.02, 3)


def test_stale_quotes_and_missing_ones_are_skipped_not_used():
    a, b = perp("AUSDT"), perp("BUSDT")
    quotes = {"AUSDT": (150.0, 150.1, NOW - P.quote_max_age_ms - 1)}
    res = R.fast_pass([row(a), row(b)], quotes, {a.id: a, b.id: b}, NOW, P)
    assert res.alerts == [] and res.checked == 0
    assert res.skipped == {"cotizacion_vieja": 1, "sin_cotizacion": 1}


def test_closed_market_is_skipped(monkeypatch):
    s = perp("SPYUSDT", calendar_id="XNYS", session=SessionKind.EXCHANGE_HOURS,
             asset_class=AssetClass.ETF)
    monkeypatch.setattr(R.calendars, "is_open", lambda *_a, **_k: False)
    res = R.fast_pass([row(s)], {"SPYUSDT": (150.0, 150.1, NOW)}, {s.id: s}, NOW, P)
    assert res.alerts == [] and res.skipped == {"mercado_cerrado": 1}


def test_market_state_never_guesses_a_holiday(monkeypatch):
    from eim.instruments.calendar_specs import CalendarUnavailable

    s = perp("SPYUSDT", calendar_id="XNYS", session=SessionKind.EXCHANGE_HOURS,
             asset_class=AssetClass.ETF)
    assert R.market_state(perp("BTCUSDT"), NOW) == "abierto"

    def nope(*_a, **_k):
        raise CalendarUnavailable("x")
    monkeypatch.setattr(R.calendars, "is_open", nope)
    assert R.market_state(s, NOW) == "sin_calendario"


def test_spreads_only_from_fresh_valid_quotes():
    a, b, c = perp("AUSDT"), perp("BUSDT"), perp("CUSDT")
    q = {"AUSDT": (100.0, 100.1, NOW), "BUSDT": (100.0, 100.1, NOW - 10**9),
         "CUSDT": (101.0, 100.0, NOW)}                       # cruzada: no es un diferencial
    got = R.spreads_of(q, [a, b, c], NOW, P.quote_max_age_ms)
    assert list(got) == [a.id] and round(got[a.id], 2) == round(0.1 / 100.05 * 1e4, 2)


def test_deep_jobs_carry_priority_and_data_hash():
    a, b = perp("AUSDT"), perp("BUSDT")
    jobs = R.deep_jobs("run1", [b.id, a.id], {a.id: a, b.id: b}, {a.id: "ha", b.id: "hb"},
                       root="/x", timeframe="1d", n_bars=90, cut=T0, asof=T0 + 1, t=5)
    assert [j.instrument_id for j in jobs] == [b.id, a.id]
    assert [j.priority for j in jobs] == [2, 1] and [j.data_hash for j in jobs] == ["hb", "ha"]
    assert jobs[0].kind == "deep_prep" and jobs[0].rhythm == "profundo"
    assert jobs[0].payload["instrument"]["id"] == b.id and jobs[0].payload["cut"] == T0


def test_sync_jobs_are_rate_limited_network_jobs():
    insts = [perp(f"S{k}USDT") for k in range(5)]
    jobs = R.sync_jobs("rel", insts, root="/x", timeframe="1d", now=NOW, days=120, limit=3)
    assert len(jobs) == 3 and all(j.provider == "binance" for j in jobs)
    assert [j.priority for j in jobs] == [0, -1, -2]
