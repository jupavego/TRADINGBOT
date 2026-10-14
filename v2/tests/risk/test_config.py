"""Configuración versionada e inmutable."""

import json

import pytest
from pydantic import ValidationError

from eim.risk import load_config
from eim.risk.config import VERSIONS_DIR


def test_default_config_loads_with_hash():
    cfg = load_config()
    assert cfg.version == "risk_v1" and len(cfg.sha256) == 64
    assert "REAL" not in cfg.allowed_modes


def test_config_is_frozen():
    cfg = load_config()
    with pytest.raises(ValidationError):
        cfg.risk_per_trade = 0.5


def _write(tmp_path, name, **changes):
    data = json.loads((VERSIONS_DIR / "risk_v1.json").read_text(encoding="utf-8"))
    data.update(version=name, **changes)
    p = tmp_path / f"{name}.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_version_must_match_file_name(tmp_path):
    p = _write(tmp_path, "risk_v9")
    p2 = tmp_path / "otro.json"
    p2.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ValueError, match="no coincide"):
        load_config(p2)


def test_hash_changes_with_content(tmp_path):
    a = load_config(_write(tmp_path, "risk_va"))
    b = load_config(_write(tmp_path, "risk_vb", risk_per_trade=0.004))
    assert a.sha256 != b.sha256


@pytest.mark.parametrize("changes", [
    {"allowed_modes": ["SIMULADO", "REAL"]},
    {"risk_per_trade": 0.05},
    {"max_daily_loss": 0.1, "max_weekly_loss": 0.05},
    {"min_sl_frac": 0.1, "max_sl_frac": 0.05},
    {"min_liq_sl_ratio": 1.0},
    {"unknown_field": 1},
])
def test_invalid_configs_rejected(tmp_path, changes):
    with pytest.raises(ValidationError):
        load_config(_write(tmp_path, "risk_vx", **changes))
