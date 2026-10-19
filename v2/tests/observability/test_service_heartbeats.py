"""T74 (seguimiento): los servicios que faltaban dejan latido, cadencia real y errores."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

import eim.observability.emit as E
from eim.observability import hooks_service
from eim.observability.catalog import has


@pytest.fixture(autouse=True)
def _fresh_throttle():
    hooks_service._last_beat.clear()
    hooks_service._skipped.clear()
    hooks_service._last_err.clear()


def _events(spool, component=None) -> list[dict]:
    E.flush()
    ev = sorted((json.loads(x) for f in spool.glob("*.jsonl")
                 for x in f.read_text(encoding="utf-8").splitlines()),
                key=lambda r: r["ts_utc"])
    return [e for e in ev if component is None or e["component_id"] == component]


async def _run_for(coro, seconds: float) -> None:
    task = asyncio.create_task(coro)
    await asyncio.sleep(seconds)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def test_sampled_beat_counts_real_runs_and_sampled_errors(spool):
    for _ in range(5):
        hooks_service.beat("data.arb_market", min_interval_s=3600)
    hooks_service._last_beat["data.arb_market"] -= 7200      # pasó el intervalo
    hooks_service.beat("data.arb_market", min_interval_s=3600)
    ev = _events(spool, "data.arb_market")
    # el orden entre eventos del mismo milisegundo no está definido: se distinguen por contenido
    assert len(ev) == 2
    (second,) = [e for e in ev if "runs" in e["detail"]]
    assert second["detail"]["runs"] == 5 and second["detail"]["interval_s"] > 3600
    assert len([e for e in ev if "runs" not in e["detail"]]) == 1
    for _ in range(4):
        hooks_service.service_error("data.arb_market", RuntimeError("x"), min_interval_s=3600)
    assert len([e for e in _events(spool, "data.arb_market") if e["kind"] == "alert"]) == 1


def test_arb_scanner_heartbeat_and_error(spool):
    from eim.data.arb_sync import ArbSync

    sync = ArbSync.__new__(ArbSync)
    sync.interval_s, calls = 0.01, {"n": 0}

    def run_once():
        calls["n"] += 1
        if calls["n"] == 1:
            return SimpleNamespace(errors=("funding BTC",))
        raise ConnectionError("sin red")

    sync.run_once = run_once
    asyncio.run(_run_for(sync.loop(), 0.15))
    ev = _events(spool, "data.arb_market")
    hb = [e for e in ev if e["kind"] == "heartbeat"]
    assert len(hb) == 1 and hb[0]["status"] == "degraded" and hb[0]["detail"]["errors"] == 1
    err = [e for e in ev if e["kind"] == "alert"]
    assert len(err) == 1 and "ConnectionError" in err[0]["detail"]["error"]   # muestreado
    assert has("data.arb_market")


def test_arb_executor_loop_heartbeat_in_testnet_mode_and_error(spool):
    from eim.api.arb_execution import arb_loop

    n = {"i": 0}

    def cycle():
        n["i"] += 1
        if n["i"] == 2:
            raise RuntimeError("exchange caído")
        return {"opened": True, "actions": ["a"], "decisions": [1, 2], "skipped": None}

    rt = SimpleNamespace(cycle=cycle, error="", interval_s=0.01)
    asyncio.run(_run_for(arb_loop(rt), 0.15))
    ev = _events(spool, "arbitrage.executor")
    hb = [e for e in ev if e["kind"] == "heartbeat"]
    err = [e for e in ev if e["kind"] == "alert"]
    assert hb and all(e["mode"] == "TESTNET" for e in ev)
    assert hb[0]["detail"]["opened"] is True and hb[0]["detail"]["decisions"] == 2
    assert err and "exchange caído" in err[0]["detail"]["error"]
    assert has("arbitrage.executor")


def test_experience_sync_heartbeat_or_error_after_each_tick(spool):
    from eim.data.share_auto import share_loop

    class Agent:
        role, error, ticks = "api", "", 0

        def due(self):
            return self.ticks < 2

        def tick(self):
            self.ticks += 1
            self.error = "" if self.ticks == 1 else "RuntimeError: carpeta compartida ausente"

    asyncio.run(_run_for(share_loop(Agent(), poll_s=0.01, first_s=0), 0.2))
    ev = _events(spool, "operation.experience_sync")
    assert [e["kind"] for e in ev] == ["heartbeat", "alert"]
    assert ev[1]["status"] == "error" and "carpeta compartida" in ev[1]["detail"]["error"]
    assert has("operation.experience_sync")


def test_live_ticks_heartbeat_is_sampled_and_drop_is_an_event(spool, monkeypatch):
    import websockets

    from eim.api.sources import BinanceKlineSource

    msg = json.dumps({"k": {"t": 1, "o": 1, "h": 2, "l": 1, "c": 2, "v": 3, "x": False}})

    class Conn:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def __aiter__(self):
            async def gen():
                for _ in range(5):
                    yield msg
                raise ConnectionError("corte de red")
            return gen()

    monkeypatch.setattr(websockets, "connect", lambda *a, **k: Conn())
    seen = []

    async def consume():
        src = BinanceKlineSource("wss://x", max_backoff=0.01)
        async for ev in src.stream("BTCUSDT", "1h"):
            seen.append(ev)

    asyncio.run(_run_for(consume(), 1.4))      # el reintento espera 1 s
    ticks = [e for e in seen if e["type"] == "tick"]
    assert len(ticks) >= 5                              # el flujo de ticks no se altera
    ev = _events(spool, "data.live_ticks")
    assert len([e for e in ev if e["kind"] == "heartbeat"]) == 1        # 5+ ticks, 1 latido
    assert any(e["kind"] == "alert" and "ConnectionError" in e["detail"]["error"] for e in ev)
    assert any(e["detail"].get("what") == "conexión restablecida" for e in ev)
    assert has("data.live_ticks")
