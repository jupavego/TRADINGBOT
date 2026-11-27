"""T102 — recorrido de una candidata, del dato a la decisión, con la traza de sus eventos."""

from __future__ import annotations

from eim.observability.events import trace_for, trace_for_instrument
from eim.scanner import trace as TR
from tests.scanner._t102 import ASOF, iid, make_view

KEYS = ["dato", "embudo", "agentes", "sintesis", "proyeccion", "oportunidad", "ranking",
        "decision"]


def test_a_shortlisted_candidate_is_traced_from_its_data_to_its_decision():
    v = make_view(above=1)
    i = iid("crypto", "CRY0USDT")
    t = TR.candidate_trace(v, i)
    assert [s["key"] for s in t["steps"]] == KEYS
    assert t["trace_id"] == trace_for_instrument(i, "1d", ASOF) and t["mode"] == "ANALISIS"
    data = t["steps"][0]["detail"]
    assert data["level"] == 2 and data["input_hash"] and data["input_ref"]["cut"] == ASOF
    assert data["license"]                                       # la licencia viaja con el dato
    agents = t["steps"][2]["detail"]
    assert len(agents["ran"]) == 3 and agents["skipped"][0]["agent_id"] == "derivatives"
    rank = t["steps"][6]["detail"]
    assert rank["above_threshold"] is True and rank["multiplicity"]["n_family"] == 1138
    d = t["steps"][-1]["detail"]
    assert d["validated"] is False and d["visible"] is True and d["level"] == "alerta"
    assert any("no está validada" in w for w in d["why"])


def test_outside_the_shortlist_the_trace_stops_at_the_funnel():
    v = make_view(shortlist=1)
    t = TR.candidate_trace(v, iid("crypto", "CRY3USDT"))
    assert [s["key"] for s in t["steps"]] == ["dato", "embudo", "decision"]
    assert "fuera de la lista corta" in t["steps"][1]["summary"]
    assert t["steps"][-1]["detail"]["visible"] is False


def test_unknown_instrument_or_no_view():
    assert TR.candidate_trace(make_view(), "crypto.binance.usdm.NOPEUSDT") is None
    assert TR.candidate_trace(None, iid("crypto", "CRY0USDT")) is None


def test_a_deactivated_class_sends_the_candidate_to_shadow():
    st = {"units": {"class:crypto": {"kind": "class", "id": "crypto", "level": "alerta",
                                     "active": False, "reason": "sin datos", "next": []}}}
    d = TR.candidate_trace(make_view(), iid("crypto", "CRY0USDT"), st)["steps"][-1]["detail"]
    assert d["visible"] is False and d["shadow"].startswith("clase desactivada")


def test_instrument_traces_do_not_collide_with_candle_traces():
    i = iid("crypto", "BTCUSDT")
    a = trace_for_instrument(i, "1d", ASOF)
    assert a == trace_for_instrument(i, "1D", ASOF) and a.startswith("tr_")
    assert a != trace_for("BTCUSDT", "1d", ASOF) and a != trace_for(i, "1d", ASOF)
    assert a != trace_for_instrument("equity.binance.usdm.BTCUSDT", "1d", ASOF)
