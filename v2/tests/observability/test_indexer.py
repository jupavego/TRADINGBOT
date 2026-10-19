"""T73: indexador — idempotencia, reanudación por offset, líneas corruptas, retención y traza."""

from __future__ import annotations

import os
import random
import time

import pytest

from eim.observability import thresholds as T
from eim.observability.events import trace_for
from eim.observability.indexer import Indexer
from eim.observability.store import ObsStore
from tests.observability.helpers import CLOSE, SYM, T0, TF, candle_trace, ev, write

DAY = 86_400_000


@pytest.fixture
def env(tmp_path):
    store = ObsStore(tmp_path / "obs.duckdb")
    spool = tmp_path / "spool"
    spool.mkdir()
    ix = Indexer(store, spool)
    ix._last_purge_ms = 2**62                  # la purga horaria no corre sola: los tests la piden
    yield store, spool, ix
    store.close()


def test_idempotent_index_twice_is_once(env):
    store, spool, ix = env
    write(spool / "api.20251001.1.jsonl", candle_trace())
    assert ix.run_once()["new"] == 11
    assert ix.run_once()["new"] == 0
    # el mismo contenido en otro archivo (copia) tampoco duplica
    write(spool / "api.20251001.2.jsonl", candle_trace())
    assert ix.run_once()["new"] == 0
    assert store.counts()["events"] == 11 and store.counts()["decisions"] == 1


def test_resumes_by_offset_after_restart(env, tmp_path):
    store, spool, ix = env
    f = write(spool / "a.20251001.1.jsonl", [ev(i) for i in range(10)])
    ix.run_once()
    write(f, [ev(i) for i in range(10, 25)])
    ix2 = Indexer(store, spool)                    # «reinicio»: objeto nuevo, misma base
    assert ix2.run_once()["new"] == 15
    assert store.counts()["events"] == 25
    off = store.scalar("SELECT byte_offset FROM spool_files WHERE file = ?", [f.name])
    assert off == f.stat().st_size
    assert ix2.run_once()["new"] == 0


def test_crash_between_data_and_offset_loses_nothing(env):
    """Datos y offset van en una transacción: si falla a mitad, ni se pierde ni se duplica."""
    store, spool, ix = env
    write(spool / "a.20251001.1.jsonl", [ev(i) for i in range(5)])
    real = store.insert
    calls = {"n": 0}

    def boom(table, *a, **k):
        if table == "spool_files":
            calls["n"] += 1
            raise RuntimeError("caída simulada")
        return real(table, *a, **k)
    store.insert = boom
    out = ix.run_once()
    assert calls["n"] == 1 and ix.last_error and out["new"] == 0
    assert store.counts()["events"] == 0                    # nada a medias
    store.insert = real
    assert ix.run_once()["new"] == 5 and store.counts()["events"] == 5


def test_corrupt_and_truncated_lines_are_counted_and_skipped(env):
    store, spool, ix = env
    good = [ev(i) for i in range(4)]
    p = spool / "a.20251001.1.jsonl"
    write(p, good[:2])
    with p.open("ab") as f:
        f.write(b'{"event_id": "x", "esto no es un evento"}\n')
        f.write(b"basura \xff\xfe sin json\n")
    write(p, good[2:], tail=b'{"event_id":"trunc","ts_utc":1')    # cola a medias, aún reciente
    out = ix.run_once()
    assert out["new"] == 4 and out["corrupt"] == 2
    # la cola a medias espera (el escritor podría completarla)…
    off = store.scalar("SELECT byte_offset FROM spool_files")
    assert off < p.stat().st_size
    # …y si no crece en TRUNCATED_LINE_GRACE_S se da por truncada y se cuenta
    old = time.time() - T.TRUNCATED_LINE_GRACE_S - 5
    os.utime(p, (old, old))
    assert ix.run_once()["corrupt"] == 1
    assert store.scalar("SELECT sum(corrupt) FROM spool_files") == 3
    assert store.scalar("SELECT byte_offset FROM spool_files") == p.stat().st_size
    assert ix.status()["corrupt_lines"] == 3


def test_partial_line_completed_later_is_indexed(env):
    store, spool, ix = env
    p = spool / "a.20251001.1.jsonl"
    line = ev(1).model_dump_json().encode()
    p.write_bytes(line[:40])
    assert ix.run_once()["new"] == 0
    with p.open("ab") as f:
        f.write(line[40:] + b"\n")
    assert ix.run_once()["new"] == 1 and store.counts()["events"] == 1


def test_trace_of_a_candle_is_complete_and_ordered(env):
    store, spool, ix = env
    evs = candle_trace()
    random.Random(7).shuffle(evs)                           # llegada desordenada, varios archivos
    write(spool / "operation.20251001.1.jsonl", [e for e in evs if e.process == "operation"])
    write(spool / "api.20251001.2.jsonl", [e for e in evs if e.process == "api"])
    ix.run_once()
    tr = trace_for(SYM, TF, CLOSE)
    d = store.query("SELECT * FROM decisions WHERE trace_id = ?", [tr])[0]
    assert d["outcome"] == "ejecutada" and d["n_signals"] == 2 and d["symbol"] == SYM
    assert d["risk_status"] == "ok" and d["n_events"] == 11 and not d["has_error"]
    assert all(d[k] for k in ("synthesis_event", "plan_event", "risk_event", "order_event",
                              "sent_event", "fill_event"))
    assert '"risk_decision": ["rd-1"]' in d["links"] and "sim_trade" in d["links"]
    run = store.query("SELECT * FROM runs WHERE run_id = 'cyc'")[0]
    assert run["status"] == "ok" and run["duration_ms"] == 9.0 and run["started_ms"] == T0 + 1
    assert store.scalar("SELECT count(*) FROM refs WHERE hash = ?", ["h" * 64]) == 3


def test_veto_outcome_and_run_error(env):
    store, spool, ix = env
    tr = trace_for(SYM, TF, CLOSE + 3_600_000)
    write(spool / "a.20251001.1.jsonl", [
        ev(1, "run_start", "operation.cycle", run="c2", trace=tr),
        ev(2, "plan", "synthesis.thesis", run="c2", trace=tr),
        ev(3, "risk_decision", "risk.engine", run="rk2", trace=tr, status="rejected"),
        ev(4, "run_end", "operation.cycle", run="c2", trace=tr, status="error",
           detail={"error": "ValueError: x", "params_version": "p7"}),
    ])
    ix.run_once()
    assert store.scalar("SELECT outcome FROM decisions WHERE trace_id = ?", [tr]) == "vetado"
    assert store.scalar("SELECT has_error FROM decisions WHERE trace_id = ?", [tr]) is True
    r = store.query("SELECT * FROM runs WHERE run_id = 'c2'")[0]
    assert r["status"] == "error" and r["error"] == "ValueError: x" and r["params_version"] == "p7"


def test_retention_keeps_runs_and_decisions(env):
    store, spool, ix = env
    now = int(time.time() * 1000)
    old = now - (T.EVENT_RETENTION_DAYS + 5) * DAY
    tr = trace_for(SYM, TF, old)
    write(spool / "a.20250101.1.jsonl", [
        ev(1, "run_start", "operation.cycle", ts=old, run="old", trace=tr),
        ev(2, "plan", "synthesis.thesis", ts=old + 1, run="old", trace=tr),
        ev(3, "run_end", "operation.cycle", ts=old + 2, run="old", trace=tr, duration_ms=2),
        ev(4, "signal", "agent.levels", ts=now - 1000, run="new"),
    ])
    ix.run_once()
    assert store.counts() == {"events": 4, "refs": 0, "runs": 1, "decisions": 1}
    out = ix.purge()
    assert out["events"] == 3
    c = store.counts()
    assert c["events"] == 1 and c["runs"] == 1 and c["decisions"] == 1   # se conservan
    # un evento tardío de la traza purgada se pliega sobre el resumen existente
    write(spool / "a.20251002.1.jsonl", [ev(9, "risk_decision", "risk.engine", ts=old + 10,
                                            run="rk", trace=tr, status="ok")])
    ix.run_once()
    d = store.query("SELECT * FROM decisions WHERE trace_id = ?", [tr])[0]
    assert d["plan_event"] and d["risk_event"] and d["outcome"] == "aprobado"


def test_retention_drops_old_runs_and_decisions_only_after_their_longer_window(env):
    store, spool, ix = env
    far = int(time.time() * 1000) - (T.RUN_RETENTION_DAYS + 2) * DAY
    tr = trace_for(SYM, TF, far)
    write(spool / "a.20240101.1.jsonl", [
        ev(1, "run_start", "operation.cycle", ts=far, run="vieja", trace=tr),
        ev(2, "plan", "synthesis.thesis", ts=far, run="vieja", trace=tr)])
    ix.run_once()
    ix.purge()
    assert store.counts() == {"events": 0, "refs": 0, "runs": 0, "decisions": 0}


def test_spool_file_deleted_only_when_indexed_and_old(env):
    store, spool, ix = env
    done = write(spool / "a.20250101.1.jsonl", [ev(1)])
    pend = write(spool / "b.20250101.1.jsonl", [ev(2)])
    ix.run_once()
    write(pend, [ev(3)])                                    # llegó más tras indexar
    for p in (done, pend):
        t = time.time() - (T.SPOOL_RETENTION_DAYS + 1) * 86400
        os.utime(p, (t, t))
    assert ix.purge()["files"] == 1
    assert not done.exists() and pend.exists()              # el pendiente no se borra
    assert any("sin indexar" in p for p in ix.status()["problems"])
    fresh = write(spool / "c.20251001.1.jsonl", [ev(4)])
    ix.run_once()                                           # ahora sí indexa lo pendiente de `pend`
    assert ix.purge()["files"] == 1 and not pend.exists()
    assert fresh.exists() and ix.purge()["files"] == 0      # indexado pero dentro de retención


def test_catalog_copy_is_versioned_once(env):
    store, _, ix = env
    ix.run_once()
    ix.run_once()
    assert store.scalar("SELECT count(*) FROM catalog_versions") == 1
    n = store.scalar("SELECT n_components FROM catalog_versions")
    assert n == store.scalar("SELECT count(*) FROM components") > 50
    assert store.scalar("SELECT count(*) FROM edges") > 0


def test_status_reports_lag_and_pending(env):
    store, spool, ix = env
    assert ix.status()["index_lag_s"] is None
    p = write(spool / "a.20251001.1.jsonl", [ev(1)])
    assert ix.status()["pending_bytes"] == p.stat().st_size
    ix.run_once()
    st = ix.status()
    assert st["pending_bytes"] == 0 and st["ok"] and st["index_lag_s"] <= T.INDEX_LAG_S_MAX
    assert st["counts"]["events"] == 1
