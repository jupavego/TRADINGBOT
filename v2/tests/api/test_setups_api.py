"""`GET /v2/setups` (T50): solo versiones VALIDADAS, con evidencia; contrato de CONTRATOS.md."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import eim.api.setups as api
from eim.api.setups import build_setups_router
from eim.core import Candle
from tests.suggestions.helpers import NOW, PRICE, T1H, H, idea, verdict

SETUP_KEYS = {"side", "kind", "entry", "sl", "tp", "rr", "strategy", "timeframe", "version", "id",
              "reason", "hours", "created_at", "valid_until", "state", "evidence",
              "symbol", "idea_id", "context"}                              # T122
EVIDENCE_KEYS = {"n_oos", "mean_r", "ci95", "p_holm", "max_dd", "win_rate", "cost_r", "n_live",
                 "mean_live", "oos_from", "oos_to"}
TOP_KEYS = {"mode", "symbol", "asof", "now", "criteria_version", "verdicts_asof", "price",
            "timeframes", "horizon_hours", "source", "status", "message", "validation",
            "discarded", "setups", "watch", "note", "ranking", "funnel"}   # T122


def make_client(monkeypatch, ideas, verdicts):
    monkeypatch.setattr(api, "now_ms", lambda: NOW)
    cs = [Candle(t=NOW - (30 - k) * H, o=PRICE, h=PRICE + 1, l=PRICE - 1, c=PRICE, v=1.0)
          for k in range(30)]
    view = SimpleNamespace(
        outcomes=[SimpleNamespace(idea=i, status="PENDIENTE") for i in ideas],
        stamp=(((1, T1H), (1, T1H), (1, T1H)),),
        path=SimpleNamespace(c=np.array([PRICE]), t=np.array([NOW - 900_000]), end=NOW))
    desk = SimpleNamespace(
        store=SimpleNamespace(read_candles=lambda *a, **k: cs), tfs=("15m", "1h", "4h"),
        last_tick=NOW - 30_000, cached_view=lambda sym, wait_s=0.0: view,
        view_state=lambda v: {"stale": False})
    validator = SimpleNamespace(
        crit=SimpleNamespace(version="validation_v1"),
        vstore=SimpleNamespace(latest=lambda c, s: (NOW - 2 * H, NOW - 2 * H, verdicts)))
    app = FastAPI()
    app.include_router(build_setups_router(desk, validator))
    return TestClient(app)


def test_validated_idea_is_published_with_contract(monkeypatch):
    r = make_client(monkeypatch, [idea()], [verdict()]).get("/v2/setups?symbol=BTCUSDT")
    j = r.json()
    assert r.status_code == 200 and set(j) == TOP_KEYS
    assert j["mode"] == "ANALISIS" and j["status"] == "ok" and j["criteria_version"]
    assert j["verdicts_asof"] == NOW - 2 * H
    (s,) = j["setups"]
    assert set(s) == SETUP_KEYS and set(s["evidence"]) == EVIDENCE_KEYS
    assert s["state"] == "sugerida_no_ejecutada" and "no garantiza" in j["note"]
    assert not {"p_fill", "p_tp", "ev_r", "score", "confluence"} & set(s)


@pytest.mark.parametrize("v", ["EN OBSERVACIÓN", "RECHAZADA"])
def test_not_validated_never_published(monkeypatch, v):
    j = make_client(monkeypatch, [idea()], [verdict(verdict=v)]).get("/v2/setups").json()
    assert j["setups"] == [] and j["status"] == "sin_validadas" and j["message"]


def test_no_signal_and_no_verdicts(monkeypatch):
    j = make_client(monkeypatch, [], [verdict()]).get("/v2/setups").json()
    assert j["status"] == "sin_senal" and j["setups"] == []
    j = make_client(monkeypatch, [idea()], []).get("/v2/setups").json()
    assert j["status"] == "sin_validadas" and j["setups"] == []


def test_unsupported_symbol(monkeypatch):
    assert make_client(monkeypatch, [], []).get("/v2/setups?symbol=XRPUSDT").status_code == 400


def test_ranking_and_funnel_in_the_route(monkeypatch):
    """T122: siempre tres posiciones; la validada apunta a su tarjeta y las vacías dicen por qué."""
    j = make_client(monkeypatch, [idea(), idea("rsi", side=-1)],
                    [verdict(), verdict("rsi", verdict="EN OBSERVACIÓN")]).get("/v2/setups").json()
    assert [s["state"] for s in j["ranking"]] == ["validada", "vacia", "vacia"]
    first = j["ranking"][0]
    assert j["setups"][first["index"]]["symbol"] == "BTCUSDT" and first["sim_status"] == "PENDIENTE"
    assert first["success"]["calibrated"] is False and first["success"]["n"] == 240
    f = j["funnel"]
    got = (f["identified"], f["analyzed"], f["validated"], f["ranked"], f["pending"])
    assert got == (2, 2, 1, 1, 1)
    assert [w["strategy"] for w in j["watch"]] == ["rsi"]        # pendiente: fuera del ranking
