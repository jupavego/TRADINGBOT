"""La vista del bróker nunca cuelga la API: con datos nuevos entrega la anterior mientras se rehace
en segundo plano (backtest largo de T49), 503 solo durante el primer cálculo; y el juicio del
aprendizaje por sumas acumuladas es el mismo que sobre la rebanada."""

from __future__ import annotations

import threading

import numpy as np
import pytest
from fastapi import FastAPI

from eim.api.paper import build_paper_router
from eim.data.paper_store import PaperStore
from eim.data.store import Store
from eim.paper.desk import PaperDesk
from eim.paper.feedback import Learner, judge
from eim.paper.params import PROFILES, FeedbackParams
from tests.local_client import LocalClient
from tests.paper.test_feedback_book import closed
from tests.paper.test_strategies import ctx_for, walk

SYM = "BTCUSDT"


@pytest.fixture
def desk(tmp_path):
    cs = walk(600)
    st = Store(tmp_path)
    st.upsert_candles(SYM, "1h", cs, "test")
    st.upsert_candles(SYM, "15m", cs, "test")     # camino de precio: basta con que exista
    ps = PaperStore(tmp_path / "p.duckdb")
    for c in cs[450:500]:
        ps.save(SYM, "1h", ctx_for(c), "backtest", 0)
    d = PaperDesk(st, ps)
    d.cs = cs
    yield d
    ps.close()


def _block(desk: PaperDesk) -> threading.Event:
    """Hace que el próximo cálculo espere a la señal devuelta."""
    gate, real = threading.Event(), desk._compute

    def slow(symbol, stamp):
        gate.wait(10)
        return real(symbol, stamp)
    desk._compute = slow
    return gate


def test_new_data_returns_previous_view_while_refreshing(desk):
    first = desk.cached_view(SYM, wait_s=10)
    assert first is not None and desk.view_state(first)["stale"] is False
    desk.pstore.save(SYM, "1h", ctx_for(desk.cs[500]), "backtest", 0)
    gate = _block(desk)
    again = desk.cached_view(SYM, wait_s=0.05)            # no espera al cálculo lento
    assert again is first
    s = desk.view_state(again)
    assert s["stale"] and s["refreshing"] and s["computed"] == first.computed
    gate.set()
    for _ in range(100):
        fresh = desk.cached_view(SYM, wait_s=0.2)
        if fresh is not first:
            break
    assert fresh.summary["coverage"]["contexts"] == 51 and not desk.view_state(fresh)["stale"]


def test_backtest_in_progress_throttles_recompute(desk):
    first = desk.cached_view(SYM, wait_s=10)
    desk.job.state = "corriendo"                          # cada contexto nuevo cambia los datos
    desk.pstore.save(SYM, "1h", ctx_for(desk.cs[500]), "backtest", 0)
    assert desk.cached_view(SYM) is first and not desk.view_state(first)["refreshing"]
    assert desk.view_state(first)["stale"]                # la interfaz lo avisa
    first.computed -= 11 * 60_000                         # pasado el intervalo, se rehace
    assert desk.cached_view(SYM, wait_s=10).summary["coverage"]["contexts"] == 51


def test_api_503_only_while_first_view_computes(desk, monkeypatch):
    monkeypatch.setattr("eim.api.paper.VIEW_WAIT_S", 0.05)
    gate = _block(desk)
    app = FastAPI()
    app.include_router(build_paper_router(desk))
    with LocalClient(app) as c:
        r = c.get(f"/v2/paper?symbol={SYM}")
        assert r.status_code == 503 and "Calculando" in r.json()["detail"]
        assert c.get(f"/v2/paper/trades?symbol={SYM}").status_code == 503
        gate.set()
        for _ in range(100):
            r = c.get(f"/v2/paper?symbol={SYM}")
            if r.status_code == 200:
                break
        assert r.status_code == 200 and r.json()["view"]["stale"] is False
        assert r.json()["coverage"]["contexts"] == 50


def test_learner_prefix_sums_match_judge_on_slice():
    rng = np.random.default_rng(5)
    rs = rng.normal(-0.05, 1.3, 400)
    outs = [closed(float(r), k) for k, r in enumerate(rs)]
    lr = Learner(outs)
    fbs = [p.feedback for p in PROFILES] + [FeedbackParams(n_min=5, prior_n=5, half_life=7)]
    for fb in fbs:
        for n in range(0, 401, 3):
            a, b = lr.at("s@1h", outs[n - 1].exit_t if n else 0, fb), judge(list(rs[:n]), fb)
            assert (a.state, a.n) == (b.state, b.n)
            assert a.weight == pytest.approx(b.weight, abs=1e-12)
            assert a.m == pytest.approx(b.m, abs=1e-12)
