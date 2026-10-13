"""Backtest completo (agentes → síntesis → plan) sobre el fixture de ETHUSDT 1h, sin red."""
from __future__ import annotations

import json

import pytest

from eim.backtest.params import BacktestParams
from eim.backtest.report import build_report, write_report
from eim.backtest.strategy import PlanStrategy
from eim.backtest.walkforward import walk_forward
from tests.agents.conftest import make_snapshot


def test_full_pipeline_report_is_reproducible(tmp_path):
    snap = make_snapshot()
    cs = snap.candles[:560]
    params = BacktestParams(eval_step=12, lookback=250)

    def run():
        w = walk_forward(cs, None, lambda _t: PlanStrategy(), params, train=100, test=180,
                         warmup=130)
        return build_report(w, params, cs, None, {"symbol": "ETHUSDT", "timeframe": "1h"})

    rep = run()
    assert len(rep["windows"]) == 2
    c = rep["pooled"]["costs"]
    assert c["gross_pnl"] - c["total_costs"] == pytest.approx(c["net_pnl"])
    assert rep["meta"]["mode"] == "SIMULADO" and "warning_funding" in c  # sin funding: se avisa
    assert json.dumps(rep, sort_keys=True, default=float) == json.dumps(
        run(), sort_keys=True, default=float)
    pj, pm = write_report(rep, "t", tmp_path)
    assert json.loads(pj.read_text(encoding="utf-8"))["meta"]["data_hash"]
    assert "Comisiones" in pm.read_text(encoding="utf-8")
