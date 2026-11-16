"""T174: el mapa no pinta «sin datos» lo que está apagado a propósito o se usa a demanda, y las
piezas que trabajan de verdad emiten con el nombre del catálogo."""

from __future__ import annotations

import json
from types import SimpleNamespace

from eim.observability import catalog as C
from eim.observability import switches as S
from eim.observability.hooks import _component_for


def test_every_switch_in_the_catalog_has_a_check():
    used = {c.switch for c in C.COMPONENTS if c.switch}
    assert used and used <= set(S.CHECKS), used - set(S.CHECKS)
    for cid in ("execution.testnet_broker", "arbitrage.executor", "risk.arb_engine",
                "execution.hft", "risk.hft_engine", "operation.experience_sync",
                "agent.context", "video.watcher"):
        assert C.get(cid).switch, cid


def test_switches_off_by_default_and_on_with_their_variable(tmp_path):
    for key in S.CHECKS:
        assert S.off_reason(key, env={}, data_dir=tmp_path), key
    on = {"testnet": {"EIM_EXECUTION": "testnet"}, "arb_testnet": {"EIM_ARB_EXECUTION": "testnet"},
          "share": {"EIM_SHARED_DIR": "Z:/x"}, "context_llm": {"EIM_CONTEXT_LLM": "local"},
          "video": {"EIM_VIDEO": "1"}}
    for key, env in on.items():
        assert S.off_reason(key, env=env, data_dir=tmp_path) is None, key
    assert S.off_reason("context_llm", env={"ANTHROPIC_API_KEY": "x"}) is None
    assert S.off_reason("hft_live", env={"EIM_EXECUTION": "testnet"})   # hasta T85
    assert S.off_reason(None, env={}) is None and S.off_reason("desconocido", env={}) is None


def test_share_switch_reads_the_saved_config_and_respects_auto_off(tmp_path):
    (tmp_path / "share_config.json").write_text(json.dumps({"shared_dir": "D:/nube"}))
    assert S.off_reason("share", env={}, data_dir=tmp_path) is None
    assert S.off_reason("share", env={"EIM_SHARE_AUTO": "0"}, data_dir=tmp_path)


def test_off_reasons_never_echo_secret_values():
    env = {"ANTHROPIC_API_KEY": "sk-secreto", "EIM_EXECUTION": "paper"}
    for key in S.CHECKS:
        assert "sk-secreto" not in (S.off_reason(key, env=env) or "")


def test_snapshot_sources_map_to_their_own_pieces():
    assert _component_for("headlines") == "data.news"
    assert _component_for("liquidations") == "data.liquidations"
    assert _component_for("liq_flow") == "data.liquidations"
    assert _component_for("events") == "data.calendar"
    assert _component_for("arb:BTC") == "data.arb_market"
    assert _component_for("candles_4h") == "data.store"


def test_snapshot_fetches_emits_snapshot_and_calendar_is_not_degraded(monkeypatch):
    from eim.observability import hooks as H
    out = []
    monkeypatch.setattr(H, "current_trace", lambda: "t")
    monkeypatch.setattr(H, "emit", lambda kind, comp, **kw: out.append((kind, comp, kw)))
    asof = 10 * 3_600_000
    snap = SimpleNamespace(
        candles=[SimpleNamespace(t=t * 3_600_000) for t in range(10)], asof=asof,
        symbol="BTCUSDT", timeframe="1h",
        sources={"candles": "binance", "events": "fed", "headlines": "rss"},
        coverage={"events": (asof - 3_600_000, asof + 7 * 86_400_000),
                  "headlines": (0, 9 * 3_600_000)})
    H.snapshot_fetches(snap, 10)
    by = {comp: kw for _, comp, kw in out}
    assert set(by) == {"data.store", "data.calendar", "data.news", "data.snapshot"}
    cal = by["data.calendar"]
    assert cal["status"] == "ok" and cal["coverage"] is None and cal["detail"]["age_min"] == 0


def test_catalog_declares_what_really_feeds_the_synthesis_and_ledger_is_on_demand():
    srcs = {f.source for f in C.get("synthesis.thesis").consumes}
    assert {f"agent.{a}" for a in ("arbitrage", "bots", "calendar", "context",
                                   "literature")} <= srcs
    assert C.get("execution.sim_ledger").cadence_s is None
