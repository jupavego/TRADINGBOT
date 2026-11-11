"""T151–T158: rutas de la biblioteca digital con libro y base sintéticos."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from eim.api.library_digital import CONFIRM, build_library_digital_router
from eim.data.library_digital import DigitalPaths

ROW = {"ledger_id": "L1", "scope": "perfil", "profile": "moderado", "symbol": "BTCUSDT",
       "strategy": "ind_supertrend", "family": "indicadores", "side": 1, "timeframe": "1h",
       "fill": 100.0, "sl": 98.0, "tp": None, "leverage": 5, "qty": 1.0, "fees": 0.1,
       "slip": 0.0, "r": 0.4, "reason": "sl", "origin": "vivo", "retro": False,
       "exit_t": 1, "opened_t": 0}


def _client(kb, tmp_path) -> TestClient:
    app = FastAPI()
    app.include_router(build_library_digital_router(rows=lambda: [ROW], kb=lambda: kb,
                                                    paths=lambda: DigitalPaths(tmp_path)))
    return TestClient(app)


def test_read_routes(kb, tmp_path):
    c = _client(kb, tmp_path)
    o = c.get("/v2/library/digital/overview").json()
    assert o["digital_total"] == len(kb.refs) and o["mode"] == "Análisis"
    refs = c.get("/v2/library/digital/refs", params={"category": "E"}).json()
    assert refs["n"] >= 3
    assert c.get("/v2/library/digital/refs/mom_a").json()["id"] == "mom_a"
    assert c.get("/v2/library/digital/refs/nope").status_code == 404
    assert c.get("/v2/library/digital/consensus/momentum").json()["verdict"] == "a favor"
    assert c.get("/v2/library/digital/consensus/xx").status_code == 404
    k = c.get("/v2/library/digital/contrast", params={"strategy": "ind_supertrend"}).json()
    assert "trend_following" in k["entry_concepts"]
    d = c.get("/v2/library/digital/diagnose", params={"ledger_id": "L1"}).json()
    assert d["operation"]["ledger_id"] == "L1" and len(d["dimensions"]) == 10
    assert c.get("/v2/library/digital/diagnose", params={"ledger_id": "X"}).status_code == 404
    assert len(c.get("/v2/library/digital/profiles").json()["profiles"]) == 4


def test_learning_record_requires_confirm(kb, tmp_path):
    c = _client(kb, tmp_path)
    assert c.post("/v2/library/digital/learning/record").status_code == 403
    r = c.post("/v2/library/digital/learning/record", headers={"X-EIM-Confirm": CONFIRM})
    assert r.json()["added"] in (0, 1)
    again = c.post("/v2/library/digital/learning/record", headers={"X-EIM-Confirm": CONFIRM})
    assert again.json()["added"] == 0            # solo adición, sin duplicar
