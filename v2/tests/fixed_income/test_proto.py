"""T100: agentes de prueba de curva y carry sobre la curva real del Tesoro (fixture) y sobre
historias sintéticas. Ninguno está registrado ni vota."""

from pathlib import Path

import numpy as np
import pytest

from eim.data.providers.treasury import parse_par_csv
from eim.fixed_income import proto

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "treasury" / "par_curve_2026_sample.csv"


def _real():
    return parse_par_csv(FIX.read_text(encoding="utf-8"))


def test_curve_state_on_the_real_curve_of_2026_11_25():
    c = _real()[-1]
    rep = proto.curve_state(c.tenors, c.yields_pct, c.date, c.source)
    assert rep.status == "ok" and rep.mode == "ANÁLISIS" and rep.bias is None
    m = rep.metrics
    assert m["par_10a_pct"] == 4.85 and m["par_2a_pct"] == 4.61 and m["par_3m_pct"] == 4.34
    assert m["pendiente_3m10a_pb"] == pytest.approx(51.0)
    assert m["pend_2s10s_pb"] == pytest.approx(24.0)
    assert m["curvatura_pb"] == pytest.approx(3.0)
    assert m["rmse_svensson_pb"] < proto.MAX_FIT_RMSE_BP
    assert rep.source == "us-treasury" and rep.as_of == "2026-11-25"


def test_curve_state_flags_inversion_and_too_few_points():
    t = [0.25, 0.5, 1, 2, 5, 10, 30]
    rep = proto.curve_state(t, [5.5, 5.4, 5.2, 4.9, 4.5, 4.3, 4.4], "x", "s")
    assert any("invertida" in e for e in rep.evidence)
    assert proto.curve_state([1, 2, 3], [1, 2, 3], "x", "s").status == "no_data"


def _history(n: int, drift_bp: float = 0.0, seed: int = 7):
    rng = np.random.default_rng(seed)
    tenors = (0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0)
    base = np.array([4.0, 4.1, 4.2, 4.4, 4.6, 4.9, 5.2])
    out, level = [], 0.0
    for i in range(n):
        level += drift_bp / 100 + rng.normal(0, 0.05)
        out.append((f"d{i:03d}", tenors, tuple(base + level)))
    return out


def test_carry_state_positive_carry_on_an_upward_curve():
    rep = proto.carry_state(_history(80), "sintética")
    assert rep.status == "ok"
    assert rep.metrics["exceso_pb"] > 0 and rep.bias > 0
    assert 0 < rep.confidence <= 0.2 and -1 <= rep.bias <= 1
    assert rep.metrics["carry_pb"] > rep.metrics["financiacion_pb"]
    assert any("prototipo" in w for w in rep.warnings)


def test_carry_state_needs_history():
    rep = proto.carry_state(_history(30), "sintética")
    assert rep.status == "no_data" and rep.bias is None


def test_carry_state_negative_on_an_inverted_curve():
    inv = [(d, t, tuple(reversed(y))) for d, t, y in _history(80)]
    rep = proto.carry_state(inv, "sintética")
    assert rep.metrics["exceso_pb"] < 0 and rep.bias < 0
