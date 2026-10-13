"""Agente liquidations: consume el snapshot y degrada con datos viejos."""
from __future__ import annotations

import json
from datetime import UTC, datetime

from eim.agents.liquidations import LiquidationsAgent
from eim.core import Candle, LiquidationDay, LiquidationLevel, Liquidations, MarketSnapshot

DAY = 86_400_000


def _ms(date: str) -> int:
    return int(datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC).timestamp() * 1000)


def _snap(last_date: str, asof_date: str, longs=3e6, shorts=1e6, stale=False) -> MarketSnapshot:
    t_last = _ms(last_date)
    liq = Liquidations(
        requested_symbol="ETHUSDT", liquidation_symbol="ETHUSD_PERP", most_recent_date=last_date,
        stale=stale, stale_age_days=0, days_with_data=3, source="fixture",
        daily=[LiquidationDay(t=t_last - i * DAY, longs_usd=longs, shorts_usd=shorts)
               for i in (2, 1, 0)],
        levels=[LiquidationLevel(price=1500 + 10 * i, longs_usd=i * 1e5, shorts_usd=1e4)
                for i in range(6)],
    )
    asof = _ms(asof_date)
    return MarketSnapshot(symbol="ETHUSDT", timeframe="1h", asof=asof, liquidations=liq,
                          candles=[Candle(t=asof - 3_600_000, o=1, h=1, l=1, c=1, v=1)])


def test_fresh_data_emits_bias_and_levels():
    rep = LiquidationsAgent().run(_snap("2026-06-26", "2026-06-27"))
    assert rep.status == "ok" and rep.bias < 0 and rep.confidence > 0  # dominan longs liquidados
    assert rep.metrics["stale"] is False
    assert rep.metrics["liquidation_symbol"] == "ETHUSD_PERP"
    assert rep.metrics["requested_symbol"] == "ETHUSDT"
    assert 1 <= len(rep.overlays) <= 3 and all(o.kind == "level" for o in rep.overlays)
    assert any("proxy" in w for w in rep.warnings)
    json.dumps(rep.model_dump())


def test_stale_data_degrades_without_bias():
    rep = LiquidationsAgent().run(_snap("2024-10-14", "2026-06-27"))
    assert rep.status == "degraded"
    assert rep.bias == 0 and rep.confidence == 0 and rep.overlays == []
    m = rep.metrics
    assert m["stale"] is True and m["most_recent_date"] == "2024-10-14"
    assert m["stale_age_days"] > 600
    assert (m["liquidation_symbol"], m["requested_symbol"]) == ("ETHUSD_PERP", "ETHUSDT")
    assert any("octubre de 2024" in w for w in rep.warnings)


def test_provider_stale_flag_is_respected():
    rep = LiquidationsAgent().run(_snap("2026-06-26", "2026-06-27", stale=True))
    assert rep.status == "degraded" and rep.bias == 0


def test_no_data_and_low_notional():
    empty = MarketSnapshot(symbol="ETHUSDT", timeframe="1h", asof=1, candles=[])
    assert LiquidationsAgent().run(empty).status == "no_data"
    rep = LiquidationsAgent().run(_snap("2026-06-26", "2026-06-27", longs=1e3, shorts=1e3))
    assert rep.status == "ok" and rep.bias == 0 and any("sin sesgo" in w for w in rep.warnings)
