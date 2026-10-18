"""T44: panel histórico de agentes (fidelidad) y prueba de contribución marginal (sin red)."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from eim.analytics import agents_marginal as am
from eim.analytics.agent_panel import PanelData, compute_panel
from eim.core import Candle
from eim.data.snapshot import build_snapshot
from eim.data.store import Store
from tests.agents.conftest import make_snapshot

H = 3_600_000
SKIP_KEYS = {"events", "arb", "leaders", "leader_weights", "micro", "orderbook", "sources",
             "coverage"}


@pytest.fixture(scope="module")
def store(tmp_path_factory) -> Store:
    """Almacén con 1000 velas reales de 1 h, el marco de 4 h agregado y funding cada 8 h."""
    cs = make_snapshot().candles
    s = Store(tmp_path_factory.mktemp("panel"))
    s.upsert_candles("ETHUSDT", "1h", cs, "fixture")
    four = [Candle(t=g[0].t, o=g[0].o, h=max(c.h for c in g), l=min(c.l for c in g), c=g[-1].c,
                   v=sum(c.v for c in g)) for g in (cs[i:i + 4] for i in range(0, len(cs) - 3, 4))
            if g[0].t % (4 * H) == 0]
    s.upsert_candles("ETHUSDT", "4h", four, "fixture")
    s.upsert_series("funding", "ETHUSDT", "-", [(c.t, 1e-4) for c in cs if c.t % (8 * H) == 0],
                    "fixture")
    return s


def test_panel_snapshot_equals_build_snapshot(store):
    data = PanelData(store, "ETHUSDT", "1h")
    for k in (-1, -7, -333, -480):                       # incluye cierres con funding exacto
        asof = data.t[k] + H
        a = build_snapshot(store, "ETHUSDT", "1h", 500, asof=asof).model_dump(exclude=SKIP_KEYS)
        assert data.snapshot(asof).model_dump(exclude=SKIP_KEYS) == a


def test_compute_panel_runs_real_agents_without_future(store):
    data = PanelData(store, "ETHUSDT", "1h")
    asofs = [data.t[k] + H for k in (-200, -100, -1)]
    df = compute_panel(store.root, "ETHUSDT", "1h", asofs, workers=1)
    assert sorted(df["asof"].unique()) == asofs
    agents = set(df.agent)
    assert {"ema", "structure", "technical", "smart_money", "calendar"} <= agents
    assert not ({"plan", "context", "arbitrage"} & agents)
    sm = df[df.agent.isin(["smart_money", "calendar"])]
    assert (sm.status == "no_data").all()                # sin historia point-in-time
    # el reporte en `asof` no cambia si se añaden velas posteriores (sin anticipación)
    early = compute_panel(store.root, "ETHUSDT", "1h", asofs[:1], workers=1)
    pd.testing.assert_frame_equal(early.reset_index(drop=True),
                                  df[df["asof"] == asofs[0]].reset_index(drop=True))


# --- estudio marginal sobre un panel sintético con efecto conocido ---------------------------
def _synthetic(n: int = 3000, seed: int = 7):
    rng = np.random.default_rng(seed)
    t0 = 1_700_000_000_000 // H * H
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    cs = [Candle(t=t0 + i * H, o=float(close[i - 1] if i else close[0]),
                 h=float(max(close[i], close[i - 1] if i else close[0]) * 1.003),
                 l=float(min(close[i], close[i - 1] if i else close[0]) * 0.997),
                 c=float(close[i]), v=1e6) for i in range(n)]
    rows = []
    for i in range(100, n - 1, 4):
        asof = cs[i].t + H
        j = min(i + 24, n - 1)
        fut = math.copysign(0.8, close[j] - close[i])     # «agente» que ve el futuro: aporta
        for ag, b, st in (("ema", rng.uniform(-0.6, 0.6), "ok"),
                          ("structure", rng.uniform(-0.6, 0.6), "ok"),
                          ("technical", fut, "ok"), ("smart_money", 0.0, "no_data")):
            rows.append((asof, ag, float(b), 0.0 if st == "no_data" else 0.7, st, None))
    return pd.DataFrame(rows, columns=["asof", "agent", "bias", "conf", "status", "regime"]), cs


@pytest.fixture(scope="module")
def study():
    mp = pytest.MonkeyPatch()
    mp.setattr(am, "WIN_TEST", 300)
    mp.setattr(am, "WARMUP", 100)
    mp.setattr(am, "N_BOOT", 60)
    df, cs = _synthetic()
    res = am.evaluate(df, cs, None, "SYNTH", log=lambda _m: None)
    yield res
    mp.undo()


def test_predictive_agent_passes_the_rule(study):
    ok, why = am.passes(study, "technical")
    v = study["variants"]["+technical"]
    assert v["ic"][1]["ic"] > 0.3 and v["ic"][1]["delta"] > 0
    assert ok, why


def test_agent_without_history_is_not_measurable(study):
    ok, why = am.passes(study, "smart_money")
    assert not ok and "no medible" in why
    assert study["coverage"]["smart_money"] == {"no_data": 1.0}


def test_anti_predictive_agent_fails(monkeypatch):
    monkeypatch.setattr(am, "WIN_TEST", 300)
    monkeypatch.setattr(am, "WARMUP", 100)
    monkeypatch.setattr(am, "N_BOOT", 30)
    df, cs = _synthetic(seed=11)
    df.loc[df.agent == "technical", "bias"] *= -1
    ok, why = am.passes(am.evaluate(df, cs, None, "SYNTH", log=lambda _m: None), "technical")
    assert not ok, why


def test_correlation_measured_on_discovery_only(study):
    c = study["corr_disc"]["technical~ema"]
    assert c["n"] > 100 and abs(c["pearson"]) < 0.2       # ruido independiente
    assert study["corr_disc"]["smart_money~ema"]["n"] == 0
    thr = {k: v["thr"] for k, v in study["variants"].items()}
    assert all(t >= 0 for t in thr.values())
