"""API del tablero de líderes (T41): lectura del último tablero y señal `smart_money` (sin red)."""

from __future__ import annotations

from eim.api.config import Settings
from eim.api.main import create_app
from eim.data.leader_board import BoardStore
from eim.data.leader_eval import evaluate
from tests.api.test_api import STEP, FakeSource, _candles
from tests.data.test_leader_eval import _approved_store
from tests.local_client import LocalClient

URL = "/v2/leaders/board"


def _client(tmp_path, now: int):
    nxt = _candles(1)[0].model_copy(update={"t": _candles(1)[0].t + STEP})
    app = create_app(Settings(data_dir=tmp_path, heartbeat_s=0.2), source=FakeSource(nxt))
    app.state.leader_desk.clock = lambda: now
    return LocalClient(app)


def test_without_board_is_no_data_with_label(tmp_path):
    with _client(tmp_path, 1_790_000_000_000) as c:
        body = c.get(URL).json()
    assert body["mode"] == "ANALISIS" and "no garantiza" in body["label"]
    assert body["board"] is None and body["stale"] is True
    assert {s["status"] for s in body["signals"].values()} == {"no_data"}


def test_board_ranking_and_signal(tmp_path):
    store, now = _approved_store(tmp_path)
    BoardStore(tmp_path).save(evaluate(store, now))
    store.close()
    with _client(tmp_path, now + 30_000) as c:
        body = c.get(URL).json()
    assert body["stale"] is False and body["age_s"] == 30.0
    (card,) = body["board"]["leaders"]
    assert card["verdict"] == "approved" and card["rank"] == 1 and card["reasons"]
    assert card["fwd"]["mean_ci"][0] > 0 and card["copyability"]["trades"] == 300
    btc, eth = body["signals"]["BTCUSDT"], body["signals"]["ETHUSDT"]
    assert btc["status"] == "ok" and btc["bias"] > 0
    assert eth["status"] == "ok" and eth["bias"] == 0  # aprobado sin posición en ETH: neutral
    with _client(tmp_path, now + 11 * 60_000) as c:  # tablero viejo: sin señal
        late = c.get(URL).json()
    assert late["stale"] is True and late["signals"]["BTCUSDT"]["status"] == "no_data"


def test_copy_sim_is_read_only_and_always_simulated(tmp_path):
    from eim.data.copy_store import write_summary
    with _client(tmp_path, 1_790_000_000_000) as c:
        empty = c.get("/v2/leaders/copy").json()
    assert empty["mode"] == "SIMULADO" and empty["sim"] is None and empty["stale"] is True
    write_summary(tmp_path, {"type": "copy_sim", "mode": "SIMULADO", "asof": 1_790_000_000_000,
                             "accounts": [{"leader_id": "hyperliquid:0x1", "equity": 1.0}]})
    with _client(tmp_path, 1_790_000_005_000) as c:
        body = c.get("/v2/leaders/copy").json()
        assert c.post("/v2/leaders/copy").status_code == 405  # no hay ninguna orden por API
    assert body["stale"] is False and body["age_s"] == 5.0
    assert body["sim"]["accounts"][0]["equity"] == 1.0
