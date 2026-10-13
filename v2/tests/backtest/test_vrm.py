"""Backtest VRM v2 vs. `EIMEngine.run_backtest` legado sobre el mismo CSV (sin red)."""
from __future__ import annotations

import pytest

from eim.agents.structure.agent import structure_frame
from eim.backtest.vrm import run_backtest
from tests.legacy import _runner as r


@pytest.fixture(scope="module")
def v2_result():
    return run_backtest(structure_frame(r.load_ohlcv()), horizon=6)


@pytest.fixture(scope="module")
def legacy_result():
    r._legacy_path()
    from eim_engine import EIMEngine

    eng = EIMEngine.__new__(EIMEngine)
    from eim_brm_irm import BRMThresholds
    eng.symbol, eng.timeframe, eng.thresholds = "ETHUSDT", "1h", BRMThresholds()
    eng.run_historical = lambda candles, save=False: r.run_frm_brm_irm()
    return r._quiet(eng.run_backtest, candles=1000, horizon=6, save=False)


def test_metrics_match_legacy(v2_result, legacy_result):
    for k in ("MET-001_accuracy_global", "MET-002_accuracy_by_scenario", "MET-003_f1_by_state",
              "MET-004_calibration_error", "MET-005_stability", "MET-006_coverage_pct",
              "MET-008_detection_latency_p50", "total_evaluated", "correct_diagnoses",
              "scenario_distribution", "avg_confidence_score", "avg_conviction_score"):
        assert v2_result[k] == legacy_result[k], k
    assert (v2_result["acceptance_criteria"]["overall_status"]
            == legacy_result["acceptance_criteria"]["overall_status"])


def test_unevaluated_never_invented(v2_result):
    ca = v2_result["acceptance_criteria"]["criteria"]
    assert all(ca[k]["status"] == "NO_EVALUADO" for k in ("CA-007", "CA-009", "CA-010"))
    assert v2_result["MET-007_cross_tf_consistency"] is None


def test_too_few_bars():
    with pytest.raises(ValueError, match="insuficientes"):
        run_backtest(structure_frame(r.load_ohlcv().head(300)))
