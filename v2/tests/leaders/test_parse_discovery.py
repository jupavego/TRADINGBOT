"""Contratos, parseo de respuestas reales y descubrimiento de candidatos (T40)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from eim.core.leaders import Leader, leader_id
from eim.leaders.discovery import aggregate, rank
from eim.leaders.parse import parse_funding, parse_positions, vault_leader
from tests.leaders.helpers import ACTIVE, leader, load


def test_leader_contract_rules():
    with pytest.raises(ValidationError):  # dirección inválida
        Leader(id="hyperliquid:0x12", venue="hyperliquid", address="0x12", origin="manual",
               discovered_at=0, source="t")
    with pytest.raises(ValidationError):  # Binance solo manual (T33)
        Leader(id="binance:abc", venue="binance", address="abc", origin="trades_ws",
               discovered_at=0, source="t")
    ld = Leader(id=leader_id("binance", "ABC"), venue="binance", address="ABC",
                origin="manual", discovered_at=0, source="manual")
    assert ld.id == "binance:ABC" and not ld.tracked


def test_parse_real_positions():
    ld = leader(ACTIVE)
    t, pos = parse_positions(ld, load("active_state0"), observed_at=t_obs())
    assert t == load("active_state0")["time"]
    btc = next(p for p in pos if p.symbol == "BTC")
    assert btc.side == "short" and btc.size == pytest.approx(6.14891)
    assert btc.leverage is not None and btc.margin_mode in ("cross", "isolated")
    assert all(p.source == "hyperliquid" and p.observed_at == t_obs() for p in pos)


def t_obs() -> int:
    return 1_792_097_000_000


def test_parse_real_funding_sign():
    rows = parse_funding(leader(ACTIVE), load("active_funding"), t_obs())
    assert rows and all(r.source == "hyperliquid" for r in rows)
    for r, raw in zip(rows, load("active_funding"), strict=True):
        assert r.usdc == float(raw["delta"]["usdc"]) and r.t == raw["time"]


def test_vault_leader_from_real_details():
    ld = vault_leader(load("vault_details"), 5)
    assert ld.origin == "vault" and ld.label.startswith("Hyperliquidity Provider")
    assert ld.address == "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303"
    assert ld.evidence["manager"].startswith("0x")


def test_discovery_from_real_trades_sample():
    msgs = load("ws_trades")
    samples = aggregate(msgs)
    trades = [t for m in msgs if m.get("channel") == "trades" for t in m["data"]]
    assert sum(s.trades for s in samples.values()) == 2 * len(trades) - sum(
        1 for t in trades if t["users"][0] == t["users"][1])
    found = rank(samples, 99, window_s=20, min_trades=1, min_notional=0, min_taker_share=0)
    assert found and all(ld.origin == "trades_ws" and ld.status == "candidate" for ld in found)
    notional = [ld.evidence["notional_usd"] for ld in found]
    assert notional == sorted(notional, reverse=True)
    assert "0x" + "0" * 40 not in {ld.address for ld in found}


def test_discovery_filters_makers_and_small_traders():
    def tr(side, buyer, seller, sz="1.0"):
        return {"coin": "BTC", "side": side, "px": "100000", "sz": sz, "time": 1,
                "users": [buyer, seller]}
    taker, maker, small = "0x" + "11" * 20, "0x" + "22" * 20, "0x" + "33" * 20
    msgs = [{"channel": "trades", "data": [tr("B", taker, maker) for _ in range(5)]},
            {"channel": "trades", "data": [tr("A", maker, small, "0.0001")]}]
    s = aggregate(msgs)
    assert s[taker].taker_share == 1.0 and s[maker].taker_share == 0.0
    found = rank(s, 1, window_s=1, min_trades=3, min_notional=50_000, min_taker_share=0.1)
    assert [ld.address for ld in found] == [taker]
