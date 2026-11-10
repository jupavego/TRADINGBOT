"""T118: la cifra que se vio ayer se puede volver a ver hoy (instantánea) y el alcance se dice.

Cada cálculo de la vista guarda su foto; pedirla por su identificador devuelve exactamente las
cifras de entonces aunque el almacén tenga operaciones nuevas. Y la vista declara qué tramo ve,
su techo y lo que deja fuera (libro fijo, instantáneas que contaban más, listas parciales).
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI

from eim.api.paper import build_paper_router
from eim.data.paper_store import PaperStore
from eim.data.store import Store
from eim.paper import ledger, snapshot
from eim.paper.desk import PaperDesk
from eim.paper.view_scope import scope_of
from tests.local_client import LocalClient
from tests.paper.test_strategies import ctx_for, walk

SYM = "BTCUSDT"
SHOWN = ("balance", "equity", "upnl", "return_pct", "max_dd_pct", "n_closed", "win_rate", "pf",
         "available", "counts")


@pytest.fixture
def desk(tmp_path):
    cs = walk(700)
    st = Store(tmp_path)
    st.upsert_candles(SYM, "1h", cs, "test")
    st.upsert_candles(SYM, "15m", cs, "test")
    ps = PaperStore(tmp_path / "p.duckdb")
    for c in cs[450:500]:
        ps.save(SYM, "1h", ctx_for(c), "backtest", 0)
    d = PaperDesk(st, ps)
    d.cs = cs
    yield d
    ps.close()


@pytest.fixture
def client(desk):
    app = FastAPI()
    app.include_router(build_paper_router(desk))
    with LocalClient(app) as c:
        yield c


def _shown(summary: dict) -> dict:
    """Las cifras que el panel muestra, tal como llegan por HTTP (JSON)."""
    s = json.loads(json.dumps(summary))
    return {"coverage": s["coverage"], "scope": s["scope"],
            "profiles": {p["id"]: {k: p[k] for k in SHOWN} for p in s["profiles"]}}


def test_la_instantanea_pedida_devuelve_la_foto_de_entonces_no_la_nueva(desk, client):
    first = client.get(f"/v2/paper?symbol={SYM}").json()
    sid = first["snapshot"]["id"]
    assert sid and first["snapshot"]["error"] == "" and first["scope"]["complete"]
    for c in desk.cs[500:600]:                    # operaciones nuevas en el almacén
        desk.pstore.save(SYM, "1h", ctx_for(c), "backtest", 0)
    second = client.get(f"/v2/paper?symbol={SYM}").json()
    assert second["snapshot"]["id"] != sid
    assert _shown(second) != _shown(first)
    assert sum(p["n_closed"] for p in second["profiles"]) > \
        sum(p["n_closed"] for p in first["profiles"])
    a, b = (client.get(f"/v2/paper/snapshot/{sid}").json() for _ in range(2))
    assert a == b and a["intact"] and a["id"] == sid and a["mode"] == "SIMULADO"
    photo = a["snapshot"]
    assert _shown({**photo, "profiles": photo["profiles"]}) == _shown(first)
    assert photo["computed"] == first["snapshot"]["computed"]
    assert set(photo["versions"]) == {"profiles", "exec", "policy", "code"}
    assert photo["data"]["contexts"]["1h"][0] == 50       # el almacén de entonces
    # la nueva también se puede volver a ver, y el listado tiene las dos
    assert client.get(f"/v2/paper/snapshot/{second['snapshot']['id']}").json()["snapshot"][
        "profiles"][0]["n_closed"] == second["profiles"][0]["n_closed"]
    ids = [x["id"] for x in client.get(f"/v2/paper/snapshots?symbol={SYM}").json()["snapshots"]]
    assert ids[:2] == [second["snapshot"]["id"], sid]


def test_instantanea_alterada_se_delata_y_desconocida_no_se_inventa(desk, client):
    sid = client.get(f"/v2/paper?symbol={SYM}").json()["snapshot"]["id"]
    body = snapshot.get(desk.pstore, sid)["snapshot"]
    body["profiles"][0]["balance"] += 1.0
    desk.pstore.execute("UPDATE paper_view_snapshot SET body = ? WHERE snapshot_id = ?",
                        [snapshot.pack(body), sid])
    assert client.get(f"/v2/paper/snapshot/{sid}").json()["intact"] is False
    desk.pstore.execute("UPDATE paper_view_snapshot SET body = ? WHERE snapshot_id = ?",
                        [b"no es zlib", sid])
    r = client.get(f"/v2/paper/snapshot/{sid}").json()
    assert r["intact"] is False and r["snapshot"] is None
    r = client.get("/v2/paper/snapshot/0123456789ab")
    assert r.status_code == 404 and "no está en este almacén" in r.json()["detail"]
    assert client.get("/v2/paper/snapshot/XYZ").status_code == 400


def test_el_historial_dice_que_es_un_tramo_de_las_mas_recientes(desk, client):
    v = client.get(f"/v2/paper?symbol={SYM}").json()
    p = max(v["profiles"], key=lambda x: x["n_closed"])
    assert p["n_closed"] > 3
    r = client.get(f"/v2/paper/trades?symbol={SYM}&profile={p['id']}&limit=3").json()
    assert r["total"] == p["n_closed"] and r["shown"] == 3 < r["total"]
    assert r["shown_to"] == r["trades"][0]["exit_t"] >= r["shown_from"] == r["trades"][-1][
        "exit_t"]
    assert r["snapshot"] == v["snapshot"]["id"]


def test_la_vista_dice_lo_que_deja_fuera_del_libro_fijo(desk):
    """Una operación en vivo del libro fijo que la vista ya no reproduce rompe la conciliación y
    sale como hueco del alcance, con su ventana y su porqué."""
    p = desk.profiles[1].id
    row = {c: None for c in ledger.COLS} | {
        "ledger_id": f"perfil|{p}|{SYM}|viejo", "scope": "perfil", "profile": p, "symbol": SYM,
        "idea_id": "viejo", "strategy": "s", "sid": "s@1h", "timeframe": "1h", "family": "f",
        "side": 1, "kind": "market", "opened_t": 1, "exit_t": 1_700_000_000_000, "reason": "SL",
        "pnl_usdt": -5.0, "origin": "vivo", "mech_version": "m", "recorded_ms": 2,
        "retro": False}
    ledger.record(desk.pstore, [tuple(row[c] for c in ledger.COLS)])
    s = desk.view(SYM).summary
    (gap,) = s["scope"]["gaps"]
    assert not s["scope"]["complete"] and gap["kind"] == "libro_fijo" and gap["profile"] == p
    assert gap["outside"] == 1 and gap["from"] == gap["to"] == 1_700_000_000_000
    led = next(x for x in s["profiles"] if x["id"] == p)["counts"]["ledger"]
    assert led["rows"] == 1 and not led["match"]
    assert s["scope"]["ceiling"] == s["coverage"]["takeable"] >= max(
        x["n_closed"] for x in s["profiles"])


def test_una_instantanea_que_contaba_mas_sale_como_hueco_con_su_porque():
    cov = {"contexts": 10, "from": 1, "to": 2, "origins": {"backtest": 10}}
    ver = {"profiles": {"agresivo": "b"}, "exec": "e", "policy": "p", "code": "c"}
    prof = {"id": "agresivo", "name": "Agresivo", "n_closed": 482,
            "counts": {"from": 5, "to": 9, "ledger": None}}
    old = {"coverage": {"contexts": 90, "from": 1, "to": 2},
           "versions": {**ver, "profiles": {"agresivo": "a"}}}
    sc = scope_of({"coverage": cov, "profiles": [prof]}, 4856,
                  {"agresivo": {"n": 19132, "id": "abc", "computed": 7}}, {"abc": old}, ver)
    (gap,) = sc["gaps"]
    assert not sc["complete"] and sc["ceiling"] == 4856
    assert (gap["kind"], gap["n"], gap["now"], gap["id"]) == ("instantanea", 19132, 482, "abc")
    assert "90 contextos" in gap["why"] and "parámetros del perfil" in gap["why"]
    # la de hoy, con lo mismo que antes, no es un hueco
    same = scope_of({"coverage": cov, "profiles": [prof]}, 4856,
                    {"agresivo": {"n": 482, "id": "abc", "computed": 7}}, {}, ver)
    assert same["complete"] and same["closes_from"] == 5 and same["closes_to"] == 9
