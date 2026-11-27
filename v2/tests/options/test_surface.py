"""T214: rasgos de la superficie de volatilidad (puros, sin red)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from eim.data.options_parse import by_expiry, normalize
from eim.options.realized import realized_vol
from eim.options.surface import SurfaceParams, expiry_smile, forward_delta, surface_features
from tests.options.surface_helpers import DAY, T0, chain, expiry_rows

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "options" / \
    "deribit_btc_book_summary.json"


def test_flat_surface_recovers_its_level_and_has_no_slope_or_skew():
    f = surface_features(chain(((3, .5), (10, .5), (24, .5), (52, .5))), T0)
    assert f.status == "ok" and not f.warnings
    assert f.atm[7] == pytest.approx(0.5, abs=1e-9) and f.atm[30] == pytest.approx(0.5, abs=1e-9)
    assert f.term_slope == pytest.approx(0.0, abs=1e-9)
    assert f.rr25 == pytest.approx(0.0, abs=1e-9)
    assert f.skew_90_110 == pytest.approx(0.0, abs=1e-9)
    assert [round(s.days) for s in f.used] == [3, 10, 24, 52]


def test_atm_between_expiries_interpolates_total_variance():
    f = surface_features(chain(), T0)
    w3, w10 = 0.50 ** 2 * 3 / 365, 0.48 ** 2 * 10 / 365
    w7 = w3 + (7 - 3) / (10 - 3) * (w10 - w3)
    assert f.atm[7] == pytest.approx(math.sqrt(w7 * 365 / 7), rel=1e-6)
    assert f.term_slope == pytest.approx(2 * math.log(f.atm[7] / f.atm[30]))
    assert f.term_slope > 0                      # el plazo corto paga más en esta curva


def test_skew_sign_follows_the_smile():
    up = surface_features(chain(slope=0.2), T0)
    down = surface_features(chain(slope=-0.2), T0)
    assert up.skew_90_110 == pytest.approx(0.2 * math.log(1.1 / 0.9), rel=1e-6)
    assert up.rr25 > 0 > down.rr25
    assert up.rr25 == pytest.approx(-down.rr25, rel=0.05)    # la delta no es simétrica en k


def test_forward_delta_signs_and_atm():
    assert 0.5 < forward_delta(0.0, 0.5, 0.1, "call") < 0.55
    assert -0.5 < forward_delta(0.0, 0.5, 0.1, "put") < -0.45
    assert forward_delta(-1.0, 0.5, 0.1, "put") == pytest.approx(0.0, abs=1e-4)


def test_never_extrapolates_a_tenor():
    f = surface_features(chain(((10, .5), (24, .5), (52, .5))), T0)
    assert f.status == "no_data" and f.atm[7] is None and f.term_slope is None
    assert any("7 días" in w for w in f.warnings)


def test_expiries_shorter_than_two_days_do_not_count():
    f = surface_features(chain(((1, .5), (10, .5), (24, .5), (52, .5))), T0)
    assert f.atm[7] is None and f.status == "no_data"
    looser = surface_features(chain(((1, .5), (10, .5), (24, .5), (52, .5))), T0,
                              p=SurfaceParams(min_expiry_days=0.5))
    assert looser.atm[7] == pytest.approx(0.5)


def test_mark_far_from_mid_degrades_but_is_not_filled():
    f, ref = surface_features(chain(mark_shift=0.05), T0), surface_features(chain(), T0)
    assert f.status == "degradado"
    assert f.atm[7] == pytest.approx(ref.atm[7] + 0.05, abs=2e-3)   # se publica la marca, avisada
    assert any("se aparta" in w for w in f.warnings)


def test_crossed_quote_near_the_money_degrades():
    rows = chain()
    target = min((r for r in rows if r["kind"] == "put" and round((r["expiry"] - T0) / DAY) == 10
                  and r["strike"] <= 90_000), key=lambda r: abs(r["strike"] - 90_000))
    target["bid"], target["ask"] = target["ask"] * 1.1, target["ask"]
    f = surface_features(rows, T0)
    assert f.status == "degradado" and any("cruzada" in w for w in f.warnings)


def test_decreasing_total_variance_is_flagged():
    f = surface_features(chain(((3, 1.2), (10, .3), (24, .46), (52, .45))), T0)
    assert f.status == "degradado"
    assert any("arbitraje de calendario" in w for w in f.warnings)


def test_variance_premium_uses_the_given_realized_vol():
    f = surface_features(chain(), T0, realized={7: 0.40, 30: None})
    assert f.vrp[7] == pytest.approx(2 * math.log(f.atm[7] / 0.40))
    assert f.vrp[30] is None


def test_too_few_otm_options_is_an_issue():
    sm = expiry_smile(expiry_rows(10, 0.5, ks=(-0.05, 0.0, 0.05)), T0)
    assert sm.atm == pytest.approx(0.5) and any("fuera del dinero" in i for i in sm.issues)


def test_realized_vol_rms_and_coverage():
    step, r = 3_600_000, 0.01
    ts = [T0 - (800 - i) * step for i in range(801)]
    closes = [100 * math.exp(r * (1 if i % 2 else -1)) for i in range(801)]
    rv = realized_vol(ts, closes, 7, T0)
    assert rv == pytest.approx(2 * r * math.sqrt(365 * 24), rel=1e-6)
    assert realized_vol(ts, closes, 60, T0) is None           # 800 h no cubren 60 días


def test_deterministic_and_metrics_are_flat():
    a, b = surface_features(chain(slope=0.1), T0), surface_features(chain(slope=0.1), T0)
    assert a.metrics() == b.metrics()
    m = a.metrics()
    assert {"atm_7d", "atm_30d", "term_slope", "rr25", "skew_90_110", "vrp_7d", "vrp_30d",
            "surface_status", "surface_version", "expiries_used"} <= set(m)
    json.dumps(m)


def test_real_fixture_marks_agree_with_mids_near_the_money():
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows, dropped = normalize(doc["result"])
    assert rows and not dropped
    for group in by_expiry(rows).values():
        sm = expiry_smile(group, doc["recorded_ms"])
        assert sm.n_otm >= 6 and 0.1 < sm.atm < 2.0
        assert sm.mid_atm is not None and sm.mark_gap < 0.02, sm.issues
