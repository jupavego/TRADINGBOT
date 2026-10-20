"""Reglas de alerta del observatorio (T75): sin latido, dato obsoleto, indexador atrasado."""

import threading

import duckdb

from eim.observability import catalog
from eim.observability.obs_alerts import load_rules, obs_conditions


def _db(events, last_pass=None):
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE events (component_id VARCHAR, ts_utc BIGINT, kind VARCHAR)")
    con.execute("CREATE TABLE meta (key VARCHAR PRIMARY KEY, value VARCHAR)")
    for e in events:
        con.execute("INSERT INTO events VALUES (?,?,?)", e)
    if last_pass is not None:
        con.execute("INSERT INTO meta VALUES ('last_pass_ms', ?)", [str(last_pass)])
    return con, threading.Lock()


def _by(cs):
    return {c.key: c for c in cs}


def test_rules_are_versioned():
    assert load_rules()["version"] == "obs_alerts_v1"


def test_silent_component_alerts_and_healthy_does_not():
    comp = next(c for c in catalog.COMPONENTS if c.built == "construido" and c.cadence_s)
    now = 10_000_000_000
    con, lock = _db([(comp.id, now - 10 * comp.cadence_s * 1000 - 200_000, "heartbeat")],
                    last_pass=now)
    got = _by(obs_conditions(con, lock, now))
    assert got[f"obs_sin_latido:{comp.id}"].on
    con, lock = _db([(comp.id, now - 1000, "heartbeat")], last_pass=now)
    assert not _by(obs_conditions(con, lock, now))[f"obs_sin_latido:{comp.id}"].on


def test_stale_data_and_late_indexer():
    now = 10_000_000_000
    con, lock = _db([("data.store", now - 2_000_000, "data_fetch")], last_pass=now - 1_000_000)
    got = _by(obs_conditions(con, lock, now))
    assert got["obs_dato_obsoleto"].on and got["obs_indexador"].on


def test_unreadable_observatory_flags_indexer_not_green():
    con = duckdb.connect(":memory:")       # sin tablas
    got = _by(obs_conditions(con, threading.Lock(), 1))
    assert got["obs_indexador"].on
    assert not any(c.on for k, c in got.items() if k.startswith("obs_sin_latido"))
