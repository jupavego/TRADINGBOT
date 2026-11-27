"""T209: lo que no cabe en la ventana no es un dato roto.

Con la ventana que carga el ciclo de operación (`OperationParams.snapshot_bars`, 500 velas de
1h), ni `literature` (el canal de 4 semanas pide 673) ni `vwap` (el mensual deja de caber hacia el
día 21) se degradan, cualquier día del mes y de la semana; y la regla de datos del riesgo no los
cuenta.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from eim.agents.literature import LiteratureAgent
from eim.agents.vwap import VWAPAgent
from eim.agents.vwap.params import VWAPParams
from eim.core import Candle, MarketSnapshot
from eim.operation.cycle import OperationParams
from tests.legacy import _runner as r
from tests.risk.helpers import OK_AGENTS, account, engine, failed, market, plan

H_MS = 3_600_000
BARS = OperationParams().snapshot_bars
# Octubre de 2026 tiene 31 días: recorre todos los días del mes y todos los de la semana.
ENDS = [datetime(2026, 10, d, 12, tzinfo=UTC) for d in range(1, 32)] + [
    datetime(2026, 10, 1, 0, tzinfo=UTC), datetime(2026, 10, 31, 23, tzinfo=UTC)]


def _snapshot(end: datetime) -> MarketSnapshot:
    """Las últimas `BARS` velas reales de la fixture, re-fechadas: la última abre en `end`."""
    df = r.load_ohlcv().iloc[-BARS:]
    t0 = int((end - timedelta(hours=BARS - 1)).timestamp() * 1000)
    candles = [Candle(t=t0 + i * H_MS, o=o, h=h, l=lo, c=c, v=v)
               for i, (_, o, h, lo, c, v) in enumerate(df.itertuples(index=False))]
    return MarketSnapshot(
        symbol="BTCUSDT", timeframe="1h", candles=candles, asof=candles[-1].t + H_MS,
        sources={"candles": "fixture re-fechada (T209)"},
        coverage={"candles": (candles[0].t, candles[-1].t)})


def _data_vetoed(status: dict[str, str]):
    eng, *_ = engine()
    dec = eng.evaluate(plan(), account(), market(agent_status={**OK_AGENTS, **status}))
    return dec, "datos" in failed(dec)


@pytest.mark.parametrize("end", ENDS, ids=lambda d: d.strftime("%d-%a-%H"))
def test_window_limits_do_not_degrade(end):
    snap = _snapshot(end)
    lit, vw = LiteratureAgent().run(snap), VWAPAgent().run(snap)
    assert lit.status == "ok" and vw.status == "ok"
    assert "murphy_weekly_rule" in lit.metrics["rules_out_of_window"]
    assert any("fuera de alcance" in w and "murphy_weekly_rule" in w for w in lit.warnings)
    partial = vw.metrics["partial_periods"]
    assert ("monthly" in partial) == (end.day >= 22)      # 500 h = 20 d 20 h
    if partial:
        assert any("VWAP mensual parcial" in w for w in vw.warnings)
    _, vetoed = _data_vetoed({"literature": lit.status, "vwap": vw.status})
    assert not vetoed


def test_partial_monthly_keeps_its_vote():
    """El arreglo es de estado, no de señal: el período parcial sigue votando con su peso."""
    snap = _snapshot(datetime(2026, 10, 28, 12, tzinfo=UTC))
    rep = VWAPAgent().run(snap)
    assert rep.metrics["partial_periods"] == ["monthly"]
    w0 = {"daily": 1.0, "weekly": 1.0, "quincenal": 1.0, "monthly": 0.0}
    assert VWAPAgent(VWAPParams(period_weights=w0)).run(snap).bias != rep.bias


def test_two_real_degradations_still_veto():
    """La regla de datos sigue igual de estricta con lo que sí falla."""
    dec, vetoed = _data_vetoed({"literature": "ok", "vwap": "ok",
                                "microstructure": "degraded", "liquidations": "degraded"})
    assert vetoed and "2 agentes degradados" in dec.reasons[0]
