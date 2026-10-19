"""T61: manifest alterado, esquema futuro, estado de máquina y secretos."""

import json

from eim.data.machine import machine_id
from eim.data.share_spec import SCHEMA_VERSION
from tests.share.helpers import M15, T0, apply, build, publish, rows


def _setup(tmp_path):
    a = build(tmp_path, "a", asofs=[T0 + M15])
    b = build(tmp_path, "b", asofs=[T0 + 2 * M15, T0 + 3 * M15], fills=[1])
    shared = tmp_path / "cloud"
    return a, b, shared, publish(b, shared, "b")


def test_tampered_parquet_rejected(tmp_path):
    a, b, shared, out = _setup(tmp_path)
    f = out / "paper_ctx.parquet"
    f.write_bytes(f.read_bytes() + b"x")
    rep = apply(a, shared, "a")
    assert rep.rejected and "hash distinto" in rep.rejected[0]["problems"][0]
    assert not rep.results and len(rows(a, "paper.duckdb", "SELECT * FROM paper_ctx")) == 1


def test_tampered_manifest_rejected(tmp_path):
    a, b, shared, out = _setup(tmp_path)
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    m["tables"]["paper_ctx"]["sha256"] = "0" * 64
    (out / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    assert apply(a, shared, "a").rejected
    (out / "manifest.json").write_text("{no json", encoding="utf-8")
    assert "ilegible" in apply(a, shared, "a").rejected[0]["problems"][0]


def test_future_schema_rejected_with_clear_message(tmp_path):
    a, b, shared, out = _setup(tmp_path)
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    m["schema_version"] = SCHEMA_VERSION + 1
    (out / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    rep = apply(a, shared, "a")
    msg = rep.rejected[0]["problems"][0]
    assert "más nuevo" in msg and "git pull" in msg
    assert len(rows(a, "paper.duckdb", "SELECT * FROM paper_ctx")) == 1


def test_machine_state_and_secrets_never_travel(tmp_path):
    a = build(tmp_path, "a", asofs=[T0 + M15])
    b = build(tmp_path, "b", asofs=[T0 + 2 * M15], fills=[1])
    (b / ".env").write_text("EIM_TESTNET_API_SECRET=zzz", encoding="utf-8")
    (b / "operation").mkdir()
    (b / "operation" / "heartbeat.json").write_text("{}", encoding="utf-8")
    shared = tmp_path / "cloud"
    out = publish(b, shared, "b")
    assert all(p.suffix == ".parquet" or p.name == "manifest.json" for p in out.iterdir())
    assert b"zzz" not in b"".join(p.read_bytes() for p in out.iterdir())
    tables = set(json.loads((out / "manifest.json").read_text(encoding="utf-8"))["tables"])
    assert not tables & {"copy_state", "op_alerts", "op_equity", "risk_decisions", "forecasts",
                         "val_verdicts", "leader_verdicts", "leader_portfolio"}
    ks = (a / "kill_switch.json").read_bytes()
    apply(a, shared, "a")
    assert (a / "kill_switch.json").read_bytes() == ks                   # b lo tenía activo
    assert json.loads(ks)["active"] is False
    assert not (a / "operation").exists() and not (a / ".env").exists()


def test_machine_id_is_stable_and_alias_overrides(tmp_path):
    d = tmp_path / "data"
    first = machine_id(d, env={})
    assert first == machine_id(d, env={}) and (d / "machine_id").read_text().strip() == first
    assert machine_id(d, env={"EIM_MACHINE": "Juan Portátil"}) == "juan-port-til"
    assert machine_id(d, env={}) == first                     # el alias no pisa el archivo


def test_own_folder_is_ignored(tmp_path):
    a, b, shared, out = _setup(tmp_path)
    publish(a, shared, "a")
    rep = apply(a, shared, "a")
    assert [e["machine"] for e in rep.exports] == ["b"]
