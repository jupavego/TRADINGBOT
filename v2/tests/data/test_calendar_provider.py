"""Calendario: parsers con recortes reales, husos, almacén point-in-time y snapshot (sin red)."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from eim.data import Store, build_snapshot
from eim.data.calendar import CalendarStore, quarterly_expiries
from eim.data.calendar_sync import sync_calendar
from eim.data.providers.calendar import (
    BEA_URL,
    BLS_URL,
    FOMC_URL,
    OfficialCalendar,
    et_to_utc_ms,
    make_event,
    parse_bea_json,
    parse_bls_ics,
    parse_fomc_html,
)
from eim.data.providers.fred import FredValues

FIX = Path(__file__).parent.parent / "fixtures" / "calendar"
H = 3_600_000
DAY = 24 * H


def _ms(*a) -> int:
    return int(datetime(*a, tzinfo=UTC).timestamp() * 1000)


def _read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


# --- husos horarios ---------------------------------------------------------
def test_eastern_time_to_utc_handles_dst():
    assert et_to_utc_ms(2026, 10, 14, 8, 30) == _ms(2026, 10, 14, 12, 30)  # EDT (−4)
    assert et_to_utc_ms(2026, 11, 6, 8, 30) == _ms(2026, 11, 6, 13, 30)    # EST (−5)
    assert et_to_utc_ms(2026, 3, 6, 8, 30) == _ms(2026, 3, 6, 13, 30)      # antes del cambio
    assert et_to_utc_ms(2026, 3, 9, 8, 30) == _ms(2026, 3, 9, 12, 30)      # después (8-mar)


# --- parsers ----------------------------------------------------------------
def test_bls_ics_parsed_in_eastern_time():
    evs = parse_bls_ics(_read("bls.ics"), fetched_at=1)
    cpi = {e.t_utc for e in evs if e.name == "Consumer Price Index"}
    assert cpi == {_ms(2026, 3, 11, 12, 30), _ms(2026, 10, 14, 12, 30), _ms(2026, 11, 10, 13, 30)}
    nfp = next(e for e in evs if e.name == "Employment Situation")
    assert nfp.t_utc == _ms(2026, 11, 6, 13, 30) and nfp.impact == "alto"
    assert next(e for e in evs if e.name == "Real Earnings").impact == "bajo"
    assert next(e for e in evs if e.name == "Producer Price Index").impact == "medio"
    assert all(e.forecast is None and e.country == "US" and e.fetched_at == 1 for e in evs)
    assert parse_bls_ics(_read("bls.ics").replace("\r\n", "\n"), 1) == evs  # LF o CRLF


def test_bls_ics_unfolds_lines_and_reads_utc():
    ics = ("BEGIN:VEVENT\r\nDTSTART:20261014T123000Z\r\nSUMMARY:Consumer Price\r\n  Index\r\n"
           "END:VEVENT\r\n")
    (e,) = parse_bls_ics(ics, 0)
    assert e.name == "Consumer Price Index" and e.t_utc == _ms(2026, 10, 14, 12, 30)


def test_fomc_decision_at_14_et_last_day():
    evs = parse_fomc_html(_read("fomc_calendars.html"), 0)
    ts = {e.t_utc for e in evs}
    assert _ms(2026, 10, 28, 18) in ts       # 27-28 oct, 14:00 EDT
    assert _ms(2026, 12, 9, 19) in ts        # 8-9* dic, 14:00 EST
    assert _ms(2022, 11, 2, 18) in ts        # "Oct/Nov 1-2" → 2 de noviembre
    assert len([e for e in evs if e.t_utc >= _ms(2026, 1, 1)]) == 16  # 2026 + 2027
    assert all(e.impact == "alto" and e.id.startswith("fed_fomc:") for e in evs)


def test_bea_json_is_utc_and_deduplicated():
    evs = parse_bea_json(_read("bea_release_dates.json"), 0)
    gdp = [e for e in evs if e.name == "Gross Domestic Product"]
    assert [e.t_utc for e in gdp] == [_ms(2026, 9, 30, 12, 30), _ms(2026, 10, 29, 12, 30),
                                      _ms(2026, 11, 25, 13, 30)]
    assert len({e.id for e in evs}) == len(evs)
    dup = '{"Gross Domestic Product": {"release_dates": ["2026-10-29T12:30:00+00:00", ' \
          '"2026-10-29T12:30:00+00:00"]}}'
    assert len(parse_bea_json(dup, 0)) == 1


def test_provider_none_when_offline_or_broken():
    pages = {FOMC_URL: _read("fomc_calendars.html"), BLS_URL: _read("bls.ics"),
             BEA_URL: "<html>mantenimiento</html>"}

    def handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        return httpx.Response(200, text=pages[url]) if url in pages else httpx.Response(404)

    cal = OfficialCalendar(httpx.Client(transport=httpx.MockTransport(handler)))
    out = cal.fetch_all(5)
    assert out["fed_fomc"] and out["bls"] and out["bea"] is None  # JSON roto → None

    def down(req):
        raise httpx.ConnectError("sin red")

    assert OfficialCalendar(httpx.Client(transport=httpx.MockTransport(down))).fetch("bls", 0) \
        is None


# --- FRED (opcional) ----------------------------------------------------------
def _fred_client(vintages: dict[str, list[tuple[str, str]]]) -> httpx.Client:
    def handler(req: httpx.Request) -> httpx.Response:
        day = req.url.params["realtime_start"]
        obs = [{"date": d, "value": v} for d, v in vintages.get(day, [])]
        return httpx.Response(200, json={"observations": obs})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fred_point_in_time_values():
    v = {"2026-11-05": [("2026-09-01", "159000"), ("2026-08-01", "158900")],
         "2026-11-06": [("2026-10-01", "159150"), ("2026-09-01", "158980"),
                        ("2026-08-01", "158900")]}
    out = FredValues("k", _fred_client(v)).values("Employment Situation", _ms(2026, 11, 6, 13, 30))
    assert out == {"actual": 170.0, "previous": 100.0, "revised": 80.0,
                   "unit": "nóminas no agrícolas, miles (variación)"}


def test_fred_disabled_or_not_released_returns_none():
    assert FredValues("").values("Employment Situation", _ms(2026, 11, 6)) is None
    same = {d: [("2026-09-01", "1"), ("2026-08-01", "1")] for d in ("2026-11-05", "2026-11-06")}
    assert FredValues("k", _fred_client(same)).values("Employment Situation",
                                                      _ms(2026, 11, 6)) is None
    assert FredValues("k", _fred_client({})).values("Real Earnings", _ms(2026, 11, 6)) is None


# --- almacén point-in-time ------------------------------------------------------
def _ev(name: str, t: int, src: str = "bls"):
    return make_event(src, name, t, 0)


def test_store_keeps_history_and_reads_as_of(tmp_path):
    cs = CalendarStore(tmp_path)
    cpi = _ms(2026, 10, 14, 12, 30)
    t1, t2 = cpi - 3 * DAY, cpi + H
    cs.record("bls", [_ev("Consumer Price Index", cpi)], t1)
    assert cs.record("bls", [_ev("Consumer Price Index", cpi)], t1 + H)["changed"] == 0
    eid = _ev("Consumer Price Index", cpi).id
    assert cs.update_values(eid, {"actual": 0.4, "previous": 0.3, "unit": "%"}, t2)
    assert cs.update_values(eid, {"actual": 0.4, "previous": 0.3, "revised": 0.2}, t2 + DAY)
    assert len(cs.versions(eid)) == 3  # nada se sobrescribe
    (before,), *_ = cs.window(cpi - H)
    assert before.actual is None and before.fetched_at == t1 + H
    (after,), *_ = cs.window(t2 + 2 * H)
    assert after.actual == 0.4 and after.revised is None
    assert cs.window(t1 - 1) is None  # antes de la primera consulta no se sabía nada


def test_store_failed_fetch_keeps_events_and_cancels_removed_future(tmp_path):
    cs = CalendarStore(tmp_path)
    now = _ms(2026, 10, 1)
    a, b = _ev("Consumer Price Index", now + 13 * DAY), _ev("Employment Situation", now + 5 * DAY)
    cs.record("bls", [a, b], now)
    assert cs.record("bls", None, now + H)["ok"] is False
    assert cs.last_fetches(now + 2 * H)["bls"][0] == now  # la fallida no cuenta como fresca
    assert cs.last_attempt()["bls"] == (now + H, False)
    res = cs.record("bls", [a], now + 2 * H)  # el NFP desaparece → cancelado (reprogramado)
    assert res["cancelled"] == 1
    evs, _, _ = cs.window(now + 3 * H, after=14 * DAY)
    assert [e.name for e in evs if e.country == "US"] == ["Consumer Price Index"]
    evs_old, _, _ = cs.window(now + H, after=14 * DAY)  # a esa fecha seguía programado
    assert {e.name for e in evs_old} >= {"Employment Situation", "Consumer Price Index"}


def test_quarterly_expiries_last_friday_0800_utc():
    lo, hi = _ms(2026, 10, 1), _ms(2027, 7, 1)
    ts = [e.t_utc for e in quarterly_expiries(lo, hi, 0)]
    assert ts == [_ms(2026, 12, 25, 8), _ms(2027, 3, 26, 8), _ms(2027, 6, 25, 8)]


def test_sync_and_snapshot_window(tmp_path):
    pages = {FOMC_URL: _read("fomc_calendars.html"), BLS_URL: _read("bls.ics"),
             BEA_URL: _read("bea_release_dates.json")}
    cal = OfficialCalendar(httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, text=pages[str(r.url)]))))
    now = _ms(2026, 10, 14, 6)
    res = sync_calendar(CalendarStore(tmp_path), cal, now)
    assert all(s["ok"] for s in res["sources"]) and res["values"] == 0
    snap = build_snapshot(Store(tmp_path), "ETHUSDT", "1h", 10, asof=now)
    names = [e.name for e in snap.events]
    assert "Consumer Price Index" in names and "Producer Price Index" in names
    assert all(now - DAY <= e.t_utc <= now + 7 * DAY for e in snap.events)
    assert snap.coverage["events:bls"] == (now, _ms(2026, 11, 13, 13, 30))
    assert snap.coverage["events"] == (now - DAY, now + 7 * DAY)
    assert "bls" in snap.sources["events"] and "events:binance_expiry" in snap.sources
    assert build_snapshot(Store(tmp_path / "vacio"), "ETHUSDT", "1h", 10, asof=now).events \
        is None


@pytest.mark.parametrize("asof", [_ms(2026, 12, 24, 8), _ms(2026, 12, 25, 9)])
def test_snapshot_includes_expiry_inside_window(tmp_path, asof):
    CalendarStore(tmp_path).record("fed_fomc", [_ev("Decisión de tipos FOMC", asof + 30 * DAY,
                                                    "fed_fomc")], asof - H)
    snap = build_snapshot(Store(tmp_path), "BTCUSDT", "1h", 5, asof=asof)
    assert [e.t_utc for e in snap.events if e.country == "CRYPTO"] == [_ms(2026, 12, 25, 8)]
