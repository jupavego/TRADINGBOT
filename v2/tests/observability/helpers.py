"""Eventos sintéticos y archivos del spool para los tests del indexador (T73)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from eim.core.mode import Mode
from eim.observability.events import ObsEvent, Ref, new_event_id, trace_for

T0 = int(time.time() * 1000) - 3_600_000   # hace una hora: dentro de toda retención
SYM, TF, CLOSE = "BTCUSDT", "1h", T0


def ev(i: int, kind="signal", comp="agent.structure", *, ts=None, run="r1", trace=None,
       status="ok", process="api", inputs=(), outputs=(), detail=None, **kw) -> ObsEvent:
    ts = T0 + i if ts is None else ts
    return ObsEvent(event_id=f"{ts:012x}-{i:010x}", ts_utc=ts, process=process,
                    component_id=comp, kind=kind, status=status, run_id=run, trace_id=trace,
                    inputs=tuple(inputs), outputs=tuple(outputs), detail=detail or {},
                    mode=Mode.SIMULADO, **kw)


def write(path: Path, events, *, tail: bytes = b"") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as f:
        for e in events:
            f.write(e.model_dump_json().encode() + b"\n")
        f.write(tail)
    return path


def candle_trace(extra_procs: bool = True) -> list[ObsEvent]:
    """Una vela recorrida por varios procesos: datos → señales → síntesis → plan → riesgo →
    orden → ejecución, con un `run_start`/`run_end` que la envuelve. Orden de llegada mezclado."""
    tr = trace_for(SYM, TF, CLOSE)
    d = {"symbol": SYM, "timeframe": TF}
    snap = Ref(type="snapshot", id="snap-1", hash="h" * 64)
    out = [
        ev(1, "run_start", "operation.cycle", ts=T0 + 1, run="cyc", trace=tr, process="operation"),
        ev(2, "data_fetch", "data.snapshot", ts=T0 + 2, run="cyc", trace=tr, source="duckdb",
           coverage=1.0, outputs=[snap], process="operation", detail=d),
        ev(3, "signal", "agent.structure", ts=T0 + 3, run="a1", trace=tr, inputs=[snap],
           outputs=[Ref(type="agent_report", id=f"{SYM}|{TF}|structure|1|{CLOSE}")],
           process="operation", detail=d),
        ev(4, "signal", "agent.levels", ts=T0 + 3, run="a2", trace=tr, inputs=[snap],
           process="operation", detail=d),
        ev(5, "synthesis", "synthesis.thesis", ts=T0 + 4, run="cyc", trace=tr,
           process="operation", detail=d),
        ev(6, "plan", "synthesis.thesis", ts=T0 + 5, run="cyc", trace=tr,
           outputs=[Ref(type="plan", id="plan-1")], process="operation", detail=d),
        ev(7, "risk_decision", "risk.engine", ts=T0 + 6, run="rk", trace=tr, status="ok",
           outputs=[Ref(type="risk_decision", id="rd-1")], process="api", detail=d),
        ev(8, "order_intent", "execution.service", ts=T0 + 7, run="ex", trace=tr, process="api"),
        ev(9, "order_sent", "execution.sim_broker", ts=T0 + 8, run="ex", trace=tr, process="api",
           outputs=[Ref(type="sim_trade", id="st-1")]),
        ev(10, "fill", "execution.sim_broker", ts=T0 + 9, run="ex", trace=tr, process="api"),
        ev(11, "run_end", "operation.cycle", ts=T0 + 10, run="cyc", trace=tr, duration_ms=9.0,
           process="operation"),
    ]
    return out if extra_procs else out[:3]


def raw_line(e: ObsEvent) -> bytes:
    return json.dumps(json.loads(e.model_dump_json())).encode() + b"\n"


__all__ = ["CLOSE", "SYM", "T0", "TF", "candle_trace", "ev", "new_event_id", "raw_line", "write"]
