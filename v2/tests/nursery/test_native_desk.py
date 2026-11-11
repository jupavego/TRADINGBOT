"""Carga validada, variables nativas en el contexto, mesa aparte y `GET /v2/nursery` (T168)."""

from __future__ import annotations

import hashlib
import json
import shutil

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from eim.agents.registry import default_registry
from eim.api.nursery import build_nursery_router
from eim.core import AgentReport, Candle
from eim.data.paper_store import PaperStore
from eim.data.store import Store
from eim.nursery.desk import NurseryDesk
from eim.nursery.native import extract, native_block, resolve, stored_key
from eim.nursery.prospect import DOSSIERS, load_prospects, native_paths
from eim.nursery.rules.base import UndeclaredVariable, View
from eim.paper.context import make_ctx
from tests.agents.conftest import make_snapshot
from tests.nursery.helpers import H1, M15, make_ctxs, make_path

PROSPECTS = load_prospects()
CANDLE_AGENTS = ("ema", "technical", "vwap", "levels", "structure", "price_action", "elliott",
                 "regime", "literature")


def _copy_dossiers(tmp_path):
    dst = tmp_path / "dossiers"
    shutil.copytree(DOSSIERS, dst)
    return dst


def test_prospect_asking_for_an_unexposed_variable_fails_to_load(tmp_path):
    for declare in (False, True):
        dst = _copy_dossiers(tmp_path / str(declare))
        f = dst / "ema.json"
        d = json.loads(f.read_text(encoding="utf-8"))
        bogus = "metrics.variables.NO_EXISTE"
        if declare:     # el expediente la declara, pero el agente no la publica
            d["variables"].append({"name": bogus, "source": "x", "note": ""})
        d["prospects"][0]["variables"].append(bogus)
        f.write_text(json.dumps(d), encoding="utf-8")
        with pytest.raises(ValueError, match="no expone"):
            load_prospects(dst)


def test_view_refuses_undeclared_variables():
    v = View("ema", frozenset({"metrics.variables.EMA_21"}), ({"variables.EMA_21": 1.0},))
    assert v.get("metrics.variables.EMA_21") == 1.0
    with pytest.raises(UndeclaredVariable):
        v.get("metrics.variables.ELASTICITY")


def test_resolve_and_compact_extract():
    rep = AgentReport(agent_id="x", version="1", asof=0, bias=0.25, confidence=0.5,
                      horizon_bars=12, metrics={"a": {"b": 1.23456789}, "l": [{"p": 1, "q": [1]},
                                                                             {"p": 2}],
                                                "piv": [{"k": "H"}, {"k": "L"}]})
    d = {"bias": rep.bias, "metrics": rep.metrics}
    assert resolve(d, "metrics.l[].p") == [1, 2] and resolve(d, "metrics.piv[-1].k") == "L"
    assert resolve(d, "metrics.missing.x") is None and resolve(d, "metrics.piv[5].k") is None
    out = extract(rep, ["metrics.a.b", "bias", "metrics.l"])
    assert out == {"a.b": 1.234568, "bias": 0.25, "l": [{"p": 1}, {"p": 2}], "_h": 12}
    assert stored_key("metrics.a.b") == "a.b"


def test_declared_paths_exist_in_real_agent_reports():
    """Cada ruta declarada por los prospectos de agentes de velas existe en su reporte real."""
    snap = make_snapshot()
    reg = default_registry()
    wanted = native_paths(PROSPECTS)
    for aid in CANDLE_AGENTS:
        rep = reg.get(aid).run(snap)
        d = {"bias": rep.bias, "metrics": rep.metrics}
        for p in wanted[aid]:
            head = p.split(".")[1].split("[")[0] if p.startswith("metrics.") else p
            assert head in (rep.metrics if p.startswith("metrics.") else d), (aid, p)
            resolve(d, p)


def test_context_without_nursery_is_unchanged():
    snap = make_snapshot(300)
    reps = [default_registry().get(a).run(snap) for a in ("ema", "regime")]
    plain = make_ctx(snap, reps, ["ema", "regime"], None, H1)
    native = native_paths(PROSPECTS)
    with_nat = make_ctx(snap, reps, ["ema", "regime"], None, H1, native=native)
    assert "nat" not in plain and {k: v for k, v in with_nat.items() if k != "nat"} == plain
    assert set(with_nat["nat"]) == {"ema", "regime"}
    assert with_nat["nat"] == native_block(reps, native)
    assert set(with_nat["nat"]["ema"]) == {stored_key(p) for p in native["ema"]} | {"_h"}


def _db_digest(ps: PaperStore) -> str:
    h = hashlib.sha256()
    for (tbl,) in sorted(ps.execute("SELECT table_name FROM information_schema.tables")):
        h.update(tbl.encode())
        for row in ps.execute(f"SELECT * FROM {tbl} ORDER BY ALL"):
            h.update(repr(row).encode())
    return h.hexdigest()


@pytest.fixture()
def desk(tmp_path):
    path = make_path(96 * 5)
    store = Store(tmp_path / "data")
    cs = [Candle(t=int(t), o=o, h=h, l=lo, c=c, v=1.0)
          for t, o, h, lo, c in zip(path.t, path.o, path.h, path.l, path.c, strict=True)]
    store.upsert_candles("BTCUSDT", "15m", cs, "prueba")
    store.upsert_series("funding", "BTCUSDT", "-", list(zip(path.ft.tolist(), path.fr.tolist(),
                                                           strict=True)), "prueba")
    main = PaperStore(tmp_path / "data" / "paper.duckdb")
    for tf, ms in (("15m", M15), ("1h", H1), ("4h", 4 * H1)):
        for c in make_ctxs(path, ms, seed=ms % 97):
            main.save("BTCUSDT", tf, c, "vivo", 0)
    main.execute("CREATE TABLE paper_ledger (id VARCHAR, payload VARCHAR)")   # libro de T31
    main.execute("INSERT INTO paper_ledger VALUES ('a', 'x'), ('b', 'y')")
    own = PaperStore(tmp_path / "data" / "paper_cantera.duckdb")
    d = NurseryDesk(store, main, own, prospects=PROSPECTS)
    yield d, main, own
    main.close()
    own.close()


def test_nursery_never_writes_to_the_t31_books(desk):
    d, main, own = desk
    before = _db_digest(main)
    book = d.compute(now=0)
    assert book.entries and _db_digest(main) == before
    tables = {t for (t,) in main.execute("SELECT table_name FROM information_schema.tables")}
    assert not any(t.startswith("nursery_") for t in tables)
    n = own.execute("SELECT count(*) FROM nursery_trades")[0][0]
    assert n == len(book.entries)
    assert own.execute("SELECT count(*) FROM nursery_accounts")[0][0] == len(book.accounts)


def test_new_account_registers_late_and_inherits_nothing(desk):
    d, _, own = desk
    d.compute(now=0)
    base = d.prospects[0]
    other = base.model_copy(update={"params": {**base.params, "majority": "> 2/3"}})
    d.prospects = (*d.prospects, other)
    late = 2**62
    book = d.compute(now=late)
    assert not book.of(other.account) and book.of(base.account)
    reg = dict(own.execute("SELECT account_id, registered_ms FROM nursery_accounts"))
    assert reg[other.account] == late and reg[base.account] == 0


def test_get_nursery_is_read_only(desk):
    d, _, _ = desk
    app = FastAPI()
    app.include_router(build_nursery_router(d))
    c = TestClient(app)
    assert c.get("/v2/nursery").json()["accounts"] == []
    d.compute(now=0)
    body = c.get("/v2/nursery").json()
    assert body["mode"] == "SIMULADO" and body["prospects"] == 43
    row = next(a for a in body["accounts"] if a["kind"] == "prospecto")
    for k in ("net_return_pct", "balance", "equity_curve", "max_drawdown_pct", "n",
              "hit_rate", "cost_paid_usd", "stage", "r_net", "d_vs_twins"):
        assert k in row
    assert c.post("/v2/nursery").status_code == 405
    off = FastAPI()
    off.include_router(build_nursery_router(None))
    assert TestClient(off).get("/v2/nursery").json()["enabled"] is False
