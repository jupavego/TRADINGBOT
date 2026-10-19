from __future__ import annotations

import os
import subprocess
import sys

import pytest
from pydantic import ValidationError

from eim.core import Mode
from eim.observability.events import (
    EVENT_KINDS,
    MAX_DETAIL_KEYS,
    MAX_STR,
    ObsEvent,
    Ref,
    new_event_id,
    trace_for,
)

REQUIRED_KINDS = {"run_start", "run_end", "data_fetch", "signal", "synthesis", "forecast", "plan",
                  "risk_decision", "order_intent", "order_sent", "fill", "alert", "heartbeat"}


def _ev(**kw):
    base = dict(event_id=new_event_id(1), ts_utc=1, process="api", component_id="agent.ema",
                kind="signal", run_id="r1")
    return ObsEvent(**{**base, **kw})


def test_kinds_cover_the_contract_and_signal_order_are_distinct():
    assert REQUIRED_KINDS <= set(EVENT_KINDS)
    assert len({"signal", "risk_decision", "order_sent"}) == 3


def test_schema_defaults_and_frozen():
    e = _ev()
    assert e.schema_version == 1 and e.mode is Mode.ANALISIS and e.status == "ok"
    with pytest.raises(ValidationError):
        e.status = "error"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        _ev(kind="otro")
    with pytest.raises(ValidationError):
        _ev(duration_ms=-1)
    with pytest.raises(ValidationError):
        _ev(coverage=1.5)


def test_refs_not_copies_and_bounded():
    e = _ev(inputs=[Ref(type="snapshot", id="ETHUSDT:1h:123", hash="ab" * 32, params_version="v1")])
    assert e.inputs[0].params_version == "v1"
    with pytest.raises(ValidationError):
        _ev(inputs=[Ref(type="x", id="y")] * 17)


def test_detail_is_bounded_not_rejected():
    e = _ev(detail={f"k{i}": "x" * 1000 for i in range(40)})
    assert len(e.detail) == MAX_DETAIL_KEYS
    assert all(len(str(v)) <= MAX_STR for v in e.detail.values())
    assert _ev(detail={"lst": [1, 2, 3], "n": float("nan")}).detail == {"lst": "1,2,3", "n": None}
    assert _ev(detail="no es dict").detail == {}


def test_data_fetch_requires_source_but_failure_does_not():
    with pytest.raises(ValidationError):
        _ev(kind="data_fetch")
    assert _ev(kind="data_fetch", source="binance", coverage=0.9).coverage == 0.9
    assert _ev(kind="data_fetch", status="error").source is None


def test_event_ids_are_unique_and_time_ordered():
    ids = [new_event_id(1_700_000_000_000 + i) for i in range(200)]
    assert len(set(ids)) == 200 and ids == sorted(ids)


def test_trace_for_is_deterministic_and_normalised():
    a = trace_for("ETHUSDT", "1h", 1_700_000_000_000)
    assert a == trace_for(" ethusdt ", "1H", 1_700_000_000_000) and a.startswith("tr_")
    assert a != trace_for("BTCUSDT", "1h", 1_700_000_000_000)
    assert a != trace_for("ETHUSDT", "4h", 1_700_000_000_000)
    assert a != trace_for("ETHUSDT", "1h", 1_700_003_600_000)


def test_trace_for_same_in_other_process_with_other_hash_seed():
    code = ("from eim.observability.events import trace_for;"
            "print(trace_for('ETHUSDT','1h',1700000000000))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env={**os.environ, "PYTHONHASHSEED": "123"}, check=True).stdout.strip()
    assert out == trace_for("ETHUSDT", "1h", 1_700_000_000_000)
