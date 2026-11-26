"""T94 — `/v2/scanner/...`: solo lectura, siempre con el modo y el aviso «candidata, no validada»,
filtros, detalle por instrumento y ningún método que cambie estado."""

from __future__ import annotations

from fastapi import FastAPI

from eim.api.scanner import build_scanner_router
from eim.data.scanner_view import build_view, write_view
from eim.scanner import deep
from tests.local_client import LocalClient
from tests.scanner._helpers import DAY, T0, candles, perp
from tests.scanner.test_deep import CUT, FakeAgent

ASOF = T0 + 101 * DAY + 3_600_000


def _app(path) -> FastAPI:
    app = FastAPI()
    app.include_router(build_scanner_router(path))
    return app


def _publish(path) -> dict:
    insts = {i.id: i for i in (perp("AUSDT"), perp("BUSDT"))}
    a, b = insts.values()
    ags = [FakeAgent("ema", 0.6), FakeAgent("structure", 0.5), FakeAgent("microstructure", 1.0)]
    r1 = deep.analyze(a, candles(150, seed=1), ags, asof=ASOF, timeframe="1d", cut=CUT,
                      run_id="barrido-1").as_json()
    scores = [{"instrument_id": a.id, "rank": 1, "score": 0.8, "quality": 0.9, "last_t": CUT - DAY},
              {"instrument_id": b.id, "rank": 2, "score": 0.4, "quality": 1.0, "last_t": CUT - DAY}]
    base = {"run_id": "barrido-1", "asof": ASOF, "timeframe": "1d",
            "detail": {"exclusions": {"liquidez": 4}, "shortlist": [a.id]}}
    view = build_view(base=base, scores=scores, insts=insts,
                      market_state={a.id: "abierto", b.id: "abierto"},
                      deep_run={"run_id": "agentes-1", "asof": ASOF}, results=[r1],
                      runs=[{"run_id": "barrido-1", "rhythm": "profundo", "asof": ASOF,
                             "timeframe": "1d", "started_at": 1, "finished_at": 2,
                             "detail": base["detail"]}], now=ASOF)
    write_view(path, view)
    return r1


def test_without_view_it_says_so(tmp_path):
    with LocalClient(_app(tmp_path)) as c:
        u = c.get("/v2/scanner/universe").json()
        assert u["available"] is False and u["mode"] == "ANALISIS" and "sweep" in u["reason"]
        assert c.get("/v2/scanner/opportunities").json()["opportunities"] == []
        assert c.get("/v2/scanner/instrument/x").status_code == 404


def test_read_only_views_with_mode_and_notice(tmp_path):
    r1 = _publish(tmp_path)
    oid = r1["opportunity"]["opportunity_id"]
    with LocalClient(_app(tmp_path)) as c:
        u = c.get("/v2/scanner/universe").json()
        assert u["mode"] == "ANALISIS" and u["status_label"] == "candidata, no validada"
        assert len(u["rows"]) == 2 and u["exclusions"] == {"liquidez": 4}
        assert u["markets"] == [{"market": "binance·usdm", "asset_class": "crypto", "n": 2,
                                 "abierto": 2, "cerrado": 0, "sin_calendario": 0}]
        assert c.get("/v2/scanner/universe", params={"asset_class": "fx"}).json()["rows"] == []
        body = c.get("/v2/scanner/opportunities").json()
        ops = body["opportunities"]
        assert [o["opportunity_id"] for o in ops] == [oid]
        assert body["ranking"]["available"] is False             # vista sin ranking (T95)
        assert c.get("/v2/scanner/opportunities", params={"side": "corto"}).json()[
            "opportunities"] == []
        assert c.get("/v2/scanner/opportunities", params={"horizon_max_days": 5}).json()[
            "opportunities"] == []                       # 25 velas diarias > 5 días
        assert c.get("/v2/scanner/runs").json()["runs"][0]["run_id"] == "barrido-1"
        d = c.get(f"/v2/scanner/instrument/{r1['instrument_id']}").json()
        assert d["opportunity"]["input_hash"] == r1["input_hash"] and d["rank"] is None
        assert [s["agent_id"] for s in d["deep"]["skipped"]] == ["microstructure"]
        other = c.get("/v2/scanner/instrument/crypto.binance.usdm.BUSDT").json()
        assert other["deep"] is None and "fuera de la lista corta" in other["note"]
        assert c.get("/v2/scanner/instrument/nada").status_code == 404


def test_no_method_changes_state(tmp_path):
    _publish(tmp_path)
    app = _app(tmp_path)
    paths = {p: ops for p, ops in app.openapi()["paths"].items() if p.startswith("/v2/scanner")}
    assert len(paths) == 4                                   # esquema público, no rutas internas
    assert {m for ops in paths.values() for m in ops} == {"get"}
    with LocalClient(app) as c:
        for verb in ("post", "put", "delete", "patch"):
            assert getattr(c, verb)("/v2/scanner/opportunities").status_code == 405
