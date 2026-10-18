"""Los criterios v1 son inmutables: ni en memoria ni en el archivo publicado (T49)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from eim.validation.criteria import PUBLISHED, VERSIONS_DIR, load_criteria


def test_v1_loads_with_pinned_hash():
    c = load_criteria()
    assert c.version == "validation_v1" and c.sha256 == PUBLISHED["validation_v1"]
    assert (c.v1_data.min_trades, c.v1_data.min_regimes, c.v1_data.min_per_regime) == (100, 2, 20)
    assert c.v2_expectancy.boot_reps >= 5000 and c.v2_expectancy.level == 0.95
    assert c.v3_random.min_reps >= 500 and c.v3_random.alpha == 0.05
    assert (c.v4_drawdown.risk_per_trade, c.v4_drawdown.max_dd) == (0.01, 0.25)
    assert c.v5_stability.window_days == 30 and c.v5_stability.min_windows == 4
    assert c.v5_stability.min_positive_frac == 0.6 and c.v5_stability.live_min_trades == 20
    assert c.v6_costs.max_cost_r == 0.3


def test_frozen_in_memory():
    c = load_criteria()
    with pytest.raises(ValidationError):
        c.v6_costs.max_cost_r = 1.0          # type: ignore[misc]
    with pytest.raises(ValidationError):
        c.version = "otra"                   # type: ignore[misc]


def test_edited_published_file_is_refused(tmp_path):
    raw = json.loads((VERSIONS_DIR / "validation_v1.json").read_text(encoding="utf-8"))
    raw["v6_costs"]["max_cost_r"] = 0.5      # «ajustar» un umbral tras ver resultados
    p = tmp_path / "validation_v1.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="versión nueva"):
        load_criteria(path=p)


def test_new_version_is_a_new_file(tmp_path):
    raw = json.loads((VERSIONS_DIR / "validation_v1.json").read_text(encoding="utf-8"))
    raw["version"] = "validation_v2"
    p = tmp_path / "validation_v2.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    assert load_criteria(path=p).version == "validation_v2"
    p2 = tmp_path / "validation_v3.json"            # nombre y versión deben coincidir
    p2.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="no coincide"):
        load_criteria(path=p2)


def test_null_reps_grow_with_attempts():
    c = load_criteria()
    assert c.null_reps(1) == 500
    # con 87 intentos el p mínimo (1/(B+1)) debe poder pasar Holm: 87/(B+1) < 0,05
    b = c.null_reps(87)
    assert 87 / (b + 1) < c.v3_random.alpha
