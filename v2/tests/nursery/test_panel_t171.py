"""Panel «Cantera» (T171): panorámica por agente, honesta con la muestra, y ficha del prospecto."""

from __future__ import annotations

import math

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from eim.api.nursery import build_nursery_router
from eim.core import Candle
from eim.data.paper_store import PaperStore
from eim.data.store import Store
from eim.nursery.desk import NurseryDesk
from eim.nursery.panel import STAGE_ORDER, family_z, verdict_eta
from eim.nursery.params import NurseryParams
from eim.nursery.prereg import family_prospects, load_prereg
from eim.nursery.prospect import load_prospects
from eim.validation.power import min_track_record
from tests.nursery.helpers import H1, M15, T0, make_ctxs, make_path

PR = load_prereg()
N = len(PR.family.members)
DAY = 24 * H1


def test_family_z_is_the_bonferroni_of_the_family():
    assert abs(family_z(50) - 3.09) < 0.01          # rec. 8: z ≈ 3,09 con m = 50


def test_verdict_eta_says_when_the_sample_does_not_give():
    v = verdict_eta([0.4, -0.1], 3.0, 50, T0, T0 + DAY, T0 + 100 * DAY)
    assert v["state"] == "sin_muestra" and v["days"] is None
    neg = verdict_eta([-0.5, 0.1, -0.2, -0.3, 0.05, -0.1], 3.0, 50, T0, T0 + DAY, T0 + 9 * DAY)
    assert neg["state"] == "sin_ventaja" and neg["days"] is None


def test_verdict_eta_is_the_mintrl_with_the_family_alpha():
    obs = [0.9, -0.4, 1.2, 0.3, -0.6, 0.8, 0.5, -0.2, 1.1, 0.1]
    v = verdict_eta(obs, 3.0, 50, T0, T0 + 5 * DAY, T0 + 180 * DAY)
    from eim.copytrading.stats import moments
    m, sd, sk, ku = moments(obs)
    need = min_track_record(m / sd, 0.0, sk, ku, 0.05 / 50)
    assert v["state"] == "estimable" and abs(v["mintrl"] - round(need, 1)) < 1e-9
    assert v["remaining"] == max(0, math.ceil(need) - len(obs))
    assert abs(v["days"] - v["remaining"] / 2.0) < 0.1          # 10 observaciones en 5 días
    assert v["beyond_deadline"] is (v["days"] > 175)


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
    own = PaperStore(tmp_path / "data" / "paper_cantera.duckdb")
    d = NurseryDesk(store, main, own, prospects=family_prospects(PR, load_prospects()),
                    prereg=PR, params=NurseryParams())
    d.compute(now=T0 + 2 * H1)                  # alta
    d.compute(now=T0 + 4 * DAY + 20 * H1)       # cuatro días hacia adelante
    yield d
    main.close()
    own.close()


def test_panel_is_by_agent_and_stage_never_by_performance(desk):
    p = desk.summary()["panel"]
    ps = p["prospects"]
    assert len(ps) == N and p["mode"] == "SIMULADO"
    order = {s: i for i, s in enumerate(STAGE_ORDER)}
    keys = [(x["agent_id"], order[x["stage"]], x["id"]) for x in ps]
    assert keys == sorted(keys)
    assert [a["agent_id"] for a in p["agents"]] == sorted({x["agent_id"] for x in ps})
    assert sum(len(a["prospects"]) for a in p["agents"]) == N
    assert "nunca por rendimiento" in p["order"]


def test_panel_header_declares_separate_books_and_expected_false_promises(desk):
    p = desk.summary()["panel"]
    assert "paper_cantera.duckdb" in p["accounting"] and "T144" in p["accounting"]
    assert "no se suman nunca" in p["accounting"]
    fp = p["header"]["false_promises"]
    assert fp["mean"] == PR.false_promises["mean"] and fp["q"] == PR.ladder.promise.q
    assert p["header"]["family_m"] == PR.m and p["header"]["deadline_ms"] > T0
    assert p["source"].startswith("data/paper_cantera.duckdb")
    assert p["coverage"]["from_ms"] == T0 + 2 * H1


def test_every_prospect_carries_figures_comparisons_and_its_sample(desk):
    p = desk.summary()["panel"]
    for x in p["prospects"]:
        for k in ("net_return_pct", "balance", "max_drawdown_pct", "n", "hit_rate",
                  "cost_paid_usd", "regime", "r_net", "early", "verdict", "sample", "band"):
            assert k in x, k
        assert set(x["vs"]) == {"sibling", "random", "buy_hold", "generic"}
        assert x["vs"]["generic"]["id"].startswith("control:agente_")
        assert {"gross_r", "d_raw", "d_shrunk"} <= set(x["r_net"])
        s = x["sample"]
        assert s["ok"] is (s["obs"] >= 30)
        assert (s["label"] == "muestra insuficiente") is (not s["ok"])
        assert x["unit"] == ("días" if x["band"] == "semanal" else "operaciones")
    assert any(x["n"] for x in p["prospects"])        # hubo operaciones hacia adelante
    bands = {b["id"]: b for b in p["bands"]}
    assert set(bands) == {"scalping", "intradia", "tres_dias", "semanal"}
    assert sum(b["count"] for b in bands.values()) == N


def test_prospect_card_and_route_are_read_only(desk):
    app = FastAPI()
    app.include_router(build_nursery_router(desk))
    c = TestClient(app)
    pid = next(x["id"] for x in desk.summary()["panel"]["prospects"] if x["n"])
    card = c.get(f"/v2/nursery/prospect/{pid}").json()
    assert card["id"] == pid and card["mode"] == "SIMULADO" and card["theory"]
    assert card["rule"] and card["variables"] and card["equity_curve"]
    assert all({"name", "value", "source"} <= set(q) for q in card["params"])
    assert all(w["stance"] in ("apoya", "condiciona", "objeta", None) for w in card["literature"])
    assert card["trades_total"] == len(card["trades"]) > 0
    assert c.get("/v2/nursery/prospect/no_existe").status_code == 404
    assert c.post(f"/v2/nursery/prospect/{pid}").status_code == 405
    off = FastAPI()
    off.include_router(build_nursery_router(None))
    assert TestClient(off).get("/v2/nursery/prospect/x").status_code == 404
