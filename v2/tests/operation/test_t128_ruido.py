"""Menos ruido y menos gasto (T128, entregable 4): LLM local mal configurado, vigilancia de lo que
solo emite con la interfaz abierta y cadencia del escáner de arbitraje."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import duckdb

from eim.agents.context import ContextAgent
from eim.agents.registry import default_registry
from eim.api.config import Settings
from eim.core import Candle, MarketSnapshot
from eim.data.providers import local_context
from eim.data.providers.local_context import ollama_problem
from eim.observability import obs_alerts
from eim.observability.obs_alerts import CON_CLIENTE, llm_conditions, obs_conditions


def test_ollama_problem_only_when_configured_and_missing(tmp_path):
    exe = tmp_path / "ollama.exe"
    assert ollama_problem({}) is None                              # sin variable: es una elección
    assert ollama_problem({"EIM_OLLAMA_EXE": str(exe)}).startswith(
        f"EIM_OLLAMA_EXE apunta a {exe}, que no existe")
    exe.write_bytes(b"")
    assert ollama_problem({"EIM_OLLAMA_EXE": f'"{exe}"'}) is None


def test_a_dead_network_drive_does_not_hang_the_check(monkeypatch):
    slow = SimpleNamespace(path=SimpleNamespace(exists=lambda p: time.sleep(5) or True))
    monkeypatch.setattr(local_context, "os", slow)                  # solo en este módulo
    monkeypatch.setattr(local_context, "CHECK_TIMEOUT_S", 0.05)
    t0 = time.monotonic()
    why = local_context.ollama_problem({"EIM_OLLAMA_EXE": r"Z:\Ollama\ollama.exe"})
    assert time.monotonic() - t0 < 2 and "no contesta" in why


def test_llm_alert_turns_on_and_off_and_checks_at_most_every_10_min(monkeypatch):
    monkeypatch.setitem(obs_alerts._llm, "at", None)
    calls = []

    def check(why):
        return lambda: calls.append(why) or why

    (c,) = llm_conditions(0, check("Z: no existe"))
    assert c.on and c.level == "warn" and "Z:" in c.detail
    assert llm_conditions(60_000, check(None))[0].on                # sigue lo de hace 1 min
    assert not llm_conditions(obs_alerts.LLM_EVERY_MS, check(None))[0].on
    assert calls == ["Z: no existe", None]


def test_context_says_why_it_has_no_llm(monkeypatch):
    snap = MarketSnapshot(symbol="BTCUSDT", timeframe="1h", asof=3_600_000,
                          candles=[Candle(t=0, o=1, h=1, l=1, c=1, v=1)])
    r = ContextAgent(unavailable="EIM_OLLAMA_EXE apunta a Z:\\x, que no existe").run(snap)
    assert r.status == "no_data" and any("Z:" in w for w in r.warnings)
    monkeypatch.setenv("EIM_OLLAMA_EXE", r"Z:\no\existe\ollama.exe")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert "Z:" in default_registry().get("context").unavailable


def _db(events):
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE events (component_id VARCHAR, ts_utc BIGINT, kind VARCHAR)")
    con.execute("CREATE TABLE meta (key VARCHAR PRIMARY KEY, value VARCHAR)")
    for e in events:
        con.execute("INSERT INTO events VALUES (?,?,?)", e)
    return con, threading.Lock()


def test_live_price_and_hub_are_not_watched_until_a_client_connects():
    """T126 (11): saltaban «sin latido» en cada arranque hasta que alguien abría la interfaz."""
    now, start = 10_000_000_000, 10_000_000_000 - 30 * 60_000      # API arrancada hace 30 min
    old = [(cid, start - 60_000, "heartbeat") for cid in CON_CLIENTE]
    on = {c.key for c in obs_conditions(*_db(old), now, index_lag_s=0, started_ms=start) if c.on}
    assert not on & {f"obs_sin_latido:{cid}" for cid in CON_CLIENTE}
    on = {c.key for c in obs_conditions(*_db(old), now, index_lag_s=0) if c.on}   # sin arranque
    assert "obs_sin_latido:data.live_ticks" in on
    # un cliente se conectó en este arranque y el precio dejó de llegar: eso sí avisa
    seen = [("data.live_ticks", start + 60_000, "heartbeat")]
    on = {c.key for c in obs_conditions(*_db(seen), now, index_lag_s=0, started_ms=start) if c.on}
    assert "obs_sin_latido:data.live_ticks" in on


def test_arbitrage_scans_every_minute_unless_it_executes(monkeypatch):
    for k in ("EIM_ARBITRAGE_S", "EIM_ARB_EXECUTION"):
        monkeypatch.delenv(k, raising=False)
    assert Settings.from_env().arbitrage_interval_s == 60.0
    monkeypatch.setenv("EIM_ARB_EXECUTION", "Testnet")
    s = Settings.from_env()
    assert s.arb_execution == "testnet" and s.arbitrage_interval_s == 10.0
    monkeypatch.setenv("EIM_ARBITRAGE_S", "30")
    assert Settings.from_env().arbitrage_interval_s == 30.0
