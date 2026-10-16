"""API del bróker simulado (T47) y generación de contextos sin anticipación."""

from __future__ import annotations

import time

import pytest

from eim.api.config import Settings
from eim.api.main import create_app
from eim.core import Candle
from eim.data.paper_store import PaperStore
from eim.data.store import Store
from eim.paper.generate import CtxGenerator
from tests.local_client import LocalClient
from tests.paper.helpers import H1, M15
from tests.paper.test_strategies import ctx_for, walk

N = 700


def _m15(cs: list[Candle]) -> list[Candle]:
    """Cuatro velas de 15 m por vela de 1 h (camino lineal o → c, rango de la hora)."""
    out = []
    for c in cs:
        for k in range(4):
            a = c.o + (c.c - c.o) * k / 4
            b = c.o + (c.c - c.o) * (k + 1) / 4
            out.append(Candle(t=c.t + k * M15, o=a, h=max(a, b) + (c.h - max(c.o, c.c)) / 2,
                              l=min(a, b) - (min(c.o, c.c) - c.l) / 2, c=b, v=c.v / 4))
    return out


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("paper")
    cs = walk(N)
    st = Store(tmp_path)
    st.upsert_candles("BTCUSDT", "1h", cs, "test")
    st.upsert_candles("BTCUSDT", "15m", _m15(cs), "test")
    cfg = Settings(data_dir=tmp_path, heartbeat_s=0.2)

    class Idle:
        name = "idle"

        async def stream(self, symbol, timeframe):
            import asyncio
            yield {"type": "status", "state": "up", "detail": ""}
            await asyncio.sleep(3600)

    with LocalClient(create_app(cfg, source=Idle())) as c:
        ps = c.app.state.paper.pstore
        for i in range(450, 650):
            ps.save("BTCUSDT", "1h", ctx_for(cs[i]), "backtest", 0)
        c.cs = cs
        yield c


def test_summary_profiles_and_strategies(client):
    v = client.get("/v2/paper?symbol=BTCUSDT").json()
    assert v["mode"] == "SIMULADO" and v["coverage"]["contexts"] == 200
    assert [p["id"] for p in v["profiles"]] == ["conservador", "moderado", "agresivo"]
    for p in v["profiles"]:
        assert p["equity"] > 0 and set(p["weights"]) == {s["id"] for s in v["strategies"]}
    assert sum(p["n_closed"] for p in v["profiles"]) > 0     # el Conservador solo opera lo probado
    assert sum(s["n"] for s in v["strategies"]) > 0 and v["insights"]
    b = v["balance"]
    assert list(b) == ["todo", "30d", "7d", "24h"]
    a = b["todo"]["all"]
    assert a["wins"]["n"] + a["losses"]["n"] == sum(p["n_closed"] for p in v["profiles"])
    assert set(b["todo"]["profiles"]) == {"conservador", "moderado", "agresivo"}
    assert client.get("/v2/paper?symbol=XRPUSDT").status_code == 400


def test_trades_journal_ideas(client):
    tr = client.get("/v2/paper/trades?symbol=BTCUSDT&profile=moderado").json()
    assert tr["mode"] == "SIMULADO" and tr["trades"]
    t = tr["trades"][0]
    assert t["profile"] == "moderado" and t["exit_t"] >= t["fill_t"] >= t["t"]
    assert t["pnl"] == pytest.approx(t["r"] * t["qty"] * abs(t["fill"] - t["sl"]), rel=1e-6)
    j = client.get("/v2/paper/journal?symbol=BTCUSDT&cat=tp,sl&limit=50").json()
    assert j["events"] and {e["cat"] for e in j["events"]} <= {"tp", "sl"}
    assert j["events"][0]["t"] >= j["events"][-1]["t"]
    assert client.get("/v2/paper/journal?cat=nada").status_code == 400
    assert client.get("/v2/paper/trades?profile=nadie").status_code == 400
    i = client.get("/v2/paper/ideas?symbol=BTCUSDT&strategy=sugerencia_1").json()
    assert i["ideas"] and all(x["strategy"] == "sugerencia_1" for x in i["ideas"])


def test_backtest_requires_confirm_and_runs(client):
    assert client.post("/v2/paper/backtest?symbol=BTCUSDT&days=0.05").status_code == 403
    h = {"X-EIM-Confirm": "paper-backtest"}
    assert client.post("/v2/paper/backtest?days=0.05&tf=1m", headers=h).status_code == 400
    r = client.post("/v2/paper/backtest?symbol=BTCUSDT&days=0.05&tf=1h,15m", headers=h)
    assert r.status_code == 200 and r.json()["state"] == "corriendo"
    for _ in range(120):
        job = client.get("/v2/paper/status").json()["job"]
        if job["state"] != "corriendo":
            break
        time.sleep(0.25)
    assert job["state"] == "terminado" and job["total"] == 1 + 4    # 1 h: 1 vela, 15 m: 4


def test_ctx_has_no_lookahead(tmp_path):
    cs = walk(N, seed=3)
    st = Store(tmp_path)
    st.upsert_candles("BTCUSDT", "1h", cs, "test")
    asof = cs[600].t + H1
    gen = CtxGenerator(st)
    a = gen.ctx_at("BTCUSDT", asof)
    st.upsert_candles("BTCUSDT", "1h", [Candle(t=c.t, o=c.o * 2, h=c.h * 2, l=c.l * 2, c=c.c * 2,
                                               v=1) for c in cs[601:]], "test")
    assert gen.ctx_at("BTCUSDT", asof) == a and a["t"] == asof and a["agents"]
    ps = PaperStore(tmp_path / "p.duckdb")
    assert gen.run(ps, "BTCUSDT", [asof, cs[-1].t + 10 * H1], lambda _t: "backtest") == 1
    assert ps.counts("BTCUSDT", "1h") == {"backtest": 1}


def test_live_signals_route(client):
    ps = client.app.state.paper.pstore
    for i in range(650, 680):
        ps.save("BTCUSDT", "1h", ctx_for(client.cs[i]), "vivo", 0)
    f = client.get("/v2/paper/live?symbol=BTCUSDT&limit=20").json()
    assert f["mode"] == "SIMULADO" and f["candles_total"] == 30 and f["total"] > 0
    assert f["live"]["error"] == "" and len(f["decisions"]) <= 20
    ts = [d["t"] for d in f["decisions"]]
    assert ts == sorted(ts, reverse=True) and all(d["origin"] == "vivo" for d in f["decisions"])
    for d in f["decisions"]:
        assert set(d["profiles"]) == {"conservador", "moderado", "agresivo"}
    assert set(f["profiles"]) == {"conservador", "moderado", "agresivo"}
    assert client.get("/v2/paper/live?symbol=XRPUSDT").status_code == 400
    assert client.get("/v2/paper/live?limit=0").status_code == 422
