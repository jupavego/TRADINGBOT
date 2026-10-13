"""Validación de techo/piso (sr_eval): estructura de salida y consistencia básica."""
from __future__ import annotations

from eim.forecast import BaseEngine
from eim.forecast.backfill import backfill
from eim.forecast.sr_eval import collect, summarize
from tests.agents.conftest import make_snapshot


def test_collect_and_summarize():
    c = make_snapshot().candles
    fcs = list(backfill(BaseEngine(), c, symbol="ETHUSDT", timeframe="1h", horizon=20, n=100,
                        stride=4))
    rows = collect(fcs, c, draws=5)
    assert rows and all(r["role"] in ("techo", "piso") for r in rows)
    rep = summarize(rows, 20)
    for g in rep.values():
        assert g["n"] > 0 and 0 <= g["touch"]["snap"] <= 1
        assert g["verdict"] in ("mejor que aleatorio", "peor que aleatorio",
                                "no distinguible del azar")
