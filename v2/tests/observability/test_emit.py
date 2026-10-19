from __future__ import annotations

import errno
import json
import multiprocessing as mp
import statistics
import time

import pytest

import eim.observability.emit as E
from eim.core import Mode
from eim.observability import thresholds as T
from eim.observability.events import ObsEvent, Ref


def _lines(spool):
    return [json.loads(x) for f in sorted(spool.glob("*.jsonl")) for x in
            f.read_text(encoding="utf-8").splitlines()]


def test_emit_writes_valid_jsonl_per_process_and_day(spool):
    assert E.emit("signal", "agent.ema", detail={"bias": 0.3}, ts_utc=1_700_000_000_000,
                  inputs=[Ref(type="snapshot", id="s1")], coverage=1.0, source="velas")
    assert E.flush()
    (f,) = list(spool.glob("*.jsonl"))
    assert f.name.startswith("test.20231114.") and f.suffix == ".jsonl"
    (row,) = _lines(spool)
    ev = ObsEvent.model_validate(row)
    assert ev.component_id == "agent.ema" and ev.mode is Mode.ANALISIS and ev.process == "test"
    assert E.stats()["written"] == 1 and E.stats()["dropped"] == 0


def test_mode_comes_from_configuration(tmp_path):
    E.configure(process="paper", mode=Mode.SIMULADO, spool_dir=tmp_path / "s", enabled=True)
    E.emit("fill", "execution.sim_broker")
    E.flush()
    assert _lines(tmp_path / "s")[0]["mode"] == "SIMULADO"
    E.close()


def test_switch_off_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("EIM_OBS", "off")
    E.configure(process="x", spool_dir=tmp_path / "s")
    assert E.emit("heartbeat", "operation.supervisor") is False
    E.flush()
    assert not (tmp_path / "s").exists() and E.stats()["enabled"] is False


def test_unwritable_destination_never_raises(tmp_path):
    blocker = tmp_path / "es_un_archivo"
    blocker.write_text("x")
    E.configure(process="x", spool_dir=blocker / "spool", enabled=True)  # mkdir imposible
    for _ in range(50):
        E.emit("signal", "agent.ema")
    assert E.flush()
    s = E.stats()
    assert s["written"] == 0 and s["dropped"] == 50 and s["errors"] >= 1
    E.close()


def test_disk_full_never_raises_and_counts(spool):
    E.emit("signal", "agent.ema")
    assert E.flush()  # abre el archivo
    em = E._em()

    class Full:
        def write(self, *_):
            raise OSError(errno.ENOSPC, "No space left on device")

        def flush(self): ...
        def close(self): ...

    em._fh = Full()
    for _ in range(20):
        E.emit("signal", "agent.ema")
    assert E.flush()
    assert E.stats()["dropped"] >= 1 and E.stats()["errors"] >= 1
    E.emit("signal", "agent.ema")  # y se recupera al reabrir el archivo
    assert E.flush() and E.stats()["written"] >= 2


def test_full_queue_drops_and_counts_without_blocking(tmp_path, monkeypatch):
    def slow_write(self, batch):
        time.sleep(0.4)

    monkeypatch.setattr(E._Emitter, "_write", slow_write)
    E.configure(process="q", spool_dir=tmp_path / "s", enabled=True, queue_size=3)
    t0 = time.perf_counter()
    results = [E.emit("signal", "agent.ema") for _ in range(300)]
    assert time.perf_counter() - t0 < 1.0  # nunca espera al escritor lento
    s = E.stats()
    assert False in results and s["dropped"] >= 200 and s["emitted"] <= 300
    E.flush(5)
    E.close()


def test_invalid_event_is_dropped_not_raised(spool):
    assert E.emit("data_fetch", "data.binance_rest") is False  # exitoso sin `source`
    assert E.emit("no_existe", "x") is False  # type: ignore[arg-type]
    assert E.stats()["dropped"] == 2


def test_span_start_end_nesting_and_trace(spool):
    with E.span("operation.cycle", trace_id="tr_x") as outer:
        with E.span("agent.ema") as inner:
            inner.set(detail={"bias": 0.1}, output=Ref(type="agent_report", id="r"))
        E.emit("signal", "agent.ema")
    assert E.flush()
    rows = _lines(spool)
    kinds = [(r["component_id"], r["kind"]) for r in rows]
    assert kinds == [("operation.cycle", "run_start"), ("agent.ema", "run_start"),
                     ("agent.ema", "run_end"), ("agent.ema", "signal"),
                     ("operation.cycle", "run_end")]
    by = {(r["component_id"], r["kind"]): r for r in rows}
    assert by[("agent.ema", "run_start")]["parent_run_id"] == outer.run_id
    assert all(r["trace_id"] == "tr_x" for r in rows)
    assert by[("agent.ema", "run_end")]["duration_ms"] >= 0
    assert by[("agent.ema", "run_end")]["outputs"][0]["id"] == "r"


def test_span_propagates_body_exception_and_marks_error(spool):
    with pytest.raises(ZeroDivisionError):
        with E.span("agent.ema"):
            _ = 1 / 0
    E.flush()
    end = [r for r in _lines(spool) if r["kind"] == "run_end"][0]
    assert end["status"] == "error" and "ZeroDivisionError" in end["detail"]["error"]


def test_span_with_broken_disk_is_transparent(tmp_path):
    f = tmp_path / "f"
    f.write_text("x")
    E.configure(process="x", spool_dir=f / "s", enabled=True)
    with E.span("agent.ema") as sp:
        sp.set(status="degraded")
        result = 42
    assert result == 42
    E.close()


def _writer(spool, name, n):
    import eim.observability.emit as em
    em.configure(process=name, spool_dir=spool)
    for i in range(n):
        em.emit("signal", "agent.ema", detail={"i": i, "pad": "z" * 150})
    em.flush(15)
    em.close()


@pytest.mark.parametrize("same_name", [False, True])
def test_two_processes_do_not_corrupt_lines(tmp_path, same_name):
    spool = tmp_path / "spool"
    n = 1500
    ps = [mp.Process(target=_writer, args=(str(spool), "p" if same_name else f"p{i}", n))
          for i in range(2)]
    for p in ps:
        p.start()
    for p in ps:
        p.join(60)
    rows = _lines(spool)  # json.loads falla si hay una línea cortada o mezclada
    assert len(rows) == 2 * n and len({r["event_id"] for r in rows}) == 2 * n
    assert len(list(spool.glob("*.jsonl"))) == 2  # un archivo por proceso (el pid va en el nombre)


def test_emit_cost_within_threshold(spool):
    for _ in range(300):
        E.emit("signal", "agent.ema", detail={"bias": 0.3}, source="b", coverage=1.0)  # calienta
    E.flush()
    lat = []
    for i in range(2000):
        t = time.perf_counter()
        E.emit("signal", "agent.ema", detail={"i": i, "bias": 0.3}, source="b", coverage=1.0)
        lat.append((time.perf_counter() - t) * 1e6)
    lat.sort()
    assert lat[int(len(lat) * 0.95)] <= T.EMIT_P95_US_MAX, statistics.fmean(lat)


def test_cycle_overhead_within_budget_even_if_disk_fails(tmp_path):
    """Un «ciclo» de MAX_EVENTS_PER_CYCLE eventos con el disco roto cuesta menos que el
    presupuesto y su resultado es idéntico al de un ciclo sin observar."""
    from eim.agents.registry import default_registry
    from eim.agents.runner import run_agents
    from tests.agents.conftest import make_snapshot

    snap = make_snapshot(400)
    agents = [a for a in default_registry().latest() if a.id in ("ema", "vwap", "levels")]
    t_plain = 1e9
    for _ in range(3):
        t = time.perf_counter()
        plain = run_agents(agents, snap)
        t_plain = min(t_plain, time.perf_counter() - t)
    blocker = tmp_path / "f"
    blocker.write_text("x")
    best = 1e9
    for _ in range(3):
        E.configure(process="cyc", spool_dir=blocker / "s", enabled=True)
        t = time.perf_counter()
        with E.span("operation.cycle", trace_id="tr_x"):
            observed = run_agents(agents, snap)
            for r in observed:
                E.emit("signal", f"agent.{r.agent_id}", detail={"bias": r.bias})
            for i in range(T.MAX_EVENTS_PER_CYCLE - 2 - len(observed)):
                E.emit("heartbeat", "operation.supervisor", detail={"i": i})
        best = min(best, time.perf_counter() - t)
        E.close()
    assert [r.model_dump() for r in observed] == [r.model_dump() for r in plain]
    overhead = best - t_plain
    assert overhead <= max(T.MAX_CYCLE_OVERHEAD_MS / 1000, T.MAX_CYCLE_OVERHEAD_FRACTION * t_plain)
