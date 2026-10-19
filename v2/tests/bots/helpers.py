"""Utilidades de las pruebas de bots: velas reales del fixture y snapshots a un `asof` dado."""

import json
from pathlib import Path

from eim.core import Candle, MarketSnapshot

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "bots" / "hummingbot_parity.json"
STEP = 3_600_000


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def candles() -> list[Candle]:
    return [Candle(t=r[0], o=r[1], h=r[2], l=r[3], c=r[4], v=r[5])
            for r in load_fixture()["candles"]]


def snapshot(n: int | None = None, cs: list[Candle] | None = None, **kw) -> MarketSnapshot:
    """Snapshot con las primeras `n` velas (todas por defecto); `asof` = cierre de la última."""
    cs = (cs or candles())[:n]
    return MarketSnapshot(symbol="ETHUSDT", timeframe="1h", candles=cs, asof=cs[-1].t + STEP,
                          sources={"candles": "fixture"}, **kw)
