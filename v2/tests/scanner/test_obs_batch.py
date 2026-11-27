"""T102 — eventos del escáner por lotes: dentro del tope de T72, válidos, con la traza del
instrumento y deterministas (republicar no duplica)."""

from __future__ import annotations

import json
import time

import pytest

import eim.observability.emit as E
from eim.core import Mode
from eim.observability import catalog as C
from eim.observability.events import ObsEvent
from eim.observability.thresholds import MAX_CYCLE_OVERHEAD_MS, MAX_EVENTS_PER_CYCLE
from eim.scanner import health as H
from eim.scanner import obs_batch as OB
from eim.scanner import trace as TR
from tests.scanner._t102 import NOW, STATUS, make_view


def _validate(e: dict) -> ObsEvent:
    kw = {k: v for k, v in e.items() if k != "event_key"}
    return ObsEvent(event_id="0-0", process="scanner", mode=Mode.ANALISIS, **kw)


def test_a_large_universe_stays_within_the_event_cap_and_every_event_is_valid():
    v = make_view({"crypto": 600, "equity": 120, "commodity": 8}, shortlist=25, above=2)
    h = H.build(v, STATUS, NOW)
    ev = OB.build(v, h, None)
    assert len(ev) <= MAX_EVENTS_PER_CYCLE
    assert all(C.has(e["component_id"]) for e in ev)
    for e in ev:
        _validate(e)
    per_class = [e for e in ev if (e.get("detail") or {}).get("lote") == "clase"]
    assert len(per_class) == 2 * 3          # datos y agentes por clase, no por instrumento
    assert sum(1 for e in ev if e["kind"] == "plan") == OB.TOP


@pytest.mark.perf
def test_building_the_batch_costs_far_less_than_the_overhead_threshold():
    v = make_view({"crypto": 600, "equity": 120}, shortlist=25)
    h = H.build(v, STATUS, NOW)
    t0 = time.perf_counter()
    for _ in range(10):
        OB.build(v, h, None)
    assert (time.perf_counter() - t0) * 100 < MAX_CYCLE_OVERHEAD_MS     # media de 10, en ms


def test_the_strongest_candidates_carry_their_instrument_trace_and_decision():
    v = make_view(shortlist=3, above=1)
    ev = OB.build(v, H.build(v, STATUS, NOW), None)
    first = v["ranking"]["rows"][0]["instrument_id"]
    tid = TR.trace_id_of(v, first)
    mine = [e for e in ev if e.get("trace_id") == tid]
    assert [e["kind"] for e in mine] == ["data_fetch", "synthesis", "forecast", "plan"]
    assert mine[-1]["status"] == "ok" and mine[-1]["detail"]["validated"] is False
    other = [e for e in ev if e["kind"] == "plan" and e.get("trace_id") != tid]
    assert other and all(e["status"] == "rejected" for e in other)   # bajo el umbral del azar


def test_without_a_view_only_the_health_heartbeat_goes_out():
    ev = OB.build(None, H.build(None, None, NOW), None)
    assert [e["kind"] for e in ev] == ["heartbeat"] and ev[0]["status"] == "no_data"


def test_emitted_batches_are_deterministic(tmp_path, monkeypatch):
    monkeypatch.setenv("EIM_OBS", "on")
    spool = tmp_path / "spool"
    E.configure(process="scanner", mode=Mode.ANALISIS, spool_dir=spool, enabled=True)
    try:
        v = make_view()
        ev = OB.build(v, H.build(v, STATUS, NOW), None)
        info = OB.emit_batch(ev)
        OB.emit_batch(ev)
        assert E.flush(5.0)
        assert info["queued"] == len(ev) and info["within"] is True
        lines = [json.loads(x) for f in spool.glob("*.jsonl")
                 for x in f.read_text(encoding="utf-8").splitlines()]
        assert len(lines) == 2 * len(ev)
        assert len({x["event_id"] for x in lines}) == len(ev)          # mismo hecho, mismo id
    finally:
        E.close()
        E.configure(process="eim", spool_dir=tmp_path / "unused", enabled=False)
