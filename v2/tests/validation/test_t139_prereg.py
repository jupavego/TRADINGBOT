"""El pre-registro de T139 es inmutable y sus cuentas cuadran."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from eim.validation.criteria import load_criteria
from eim.validation.hypotheses.prereg import PREREG_DIR, PUBLISHED, load_prereg


def _raw() -> dict:
    return json.loads((PREREG_DIR / "prereg_t139_v1.json").read_text(encoding="utf-8"))


def test_published_file_loads_with_pinned_hash():
    p = load_prereg()
    assert p.version == "prereg_t139_v1" and p.sha256 == PUBLISHED[p.version]
    assert p.criteria == "validation_v1" and p.mode == "SIMULADO" and p.symbol == "BTCUSDT"


def test_edited_file_is_refused(tmp_path):
    raw = _raw()
    raw["reading_rule"]["cost_stress"] = 1.1      # «aflojar» la regla tras ver resultados
    p = tmp_path / "prereg_t139_v1.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="versión nueva"):
        load_prereg(path=p)


def test_nine_new_keys_and_a_family_of_841():
    p = load_prereg()
    assert p.sids() == ["funding_contra@1h", "funding_contra@4h", "flujo_sigue@1h",
                        "flujo_sigue@4h", "flujo_revierte@1h", "flujo_revierte@4h",
                        "cascada_revierte@1h", "cascada_revierte@4h", "momento_1d@1d"]
    assert p.attempts.new == 9 and p.attempts.family == 841
    assert load_criteria().null_reps(p.attempts.family) == p.attempts.null_reps == 33640


@pytest.mark.parametrize("edit", [
    lambda r: r["attempts"].update(family=840),
    lambda r: r["attempts"].update(new=8),
    lambda r: r["windows"]["adjust"].update(to="2026-11-07T00:00:00Z"),
    lambda r: r["readings"][1].update(verdict=True),
])
def test_accounts_that_do_not_add_up_are_refused(tmp_path, edit):
    raw = _raw()
    edit(raw)
    p = tmp_path / "prereg_t139_v1.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_prereg(path=p, strict=False)


def test_exit_is_the_control_exit_and_stop_rule_binds():
    p = load_prereg()
    assert (p.exit.sl_atr, p.exit.tp_atr, p.exit.kind) == (1.5, 2.5, "market")
    assert p.stop_rule.binding is True
    assert p.live_rule.deadline == "2027-05-06T05:00:00Z"
    assert p.windows.adjust.from_ == "2023-01-01T00:00:00Z"
