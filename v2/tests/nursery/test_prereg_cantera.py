"""El pre-registro `cantera_v1` (T170) es inmutable y coincide con lo que corre."""

from __future__ import annotations

import json
import shutil

import pytest

from eim.nursery.exam import verdict
from eim.nursery.params import NurseryParams
from eim.nursery.prereg import PREREG_DIR, PUBLISHED, family_prospects, load_prereg
from eim.nursery.prospect import CEILING, load_prospects
from eim.validation.criteria import PUBLISHED as CRITERIA

PR = load_prereg()


def test_published_hash_is_pinned_and_a_modified_copy_fails(tmp_path):
    assert PUBLISHED["prereg_cantera_v1"] == PR.sha256 != ""
    dst = tmp_path / "prereg_cantera_v1.json"
    shutil.copy(PREREG_DIR / "prereg_cantera_v1.json", dst)
    data = json.loads(dst.read_text(encoding="utf-8"))
    data["ladder"]["promise"]["q"] = 0.2           # «endurecer» o «aflojar» después: prohibido
    dst.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="modificado"):
        load_prereg(path=dst)
    assert PR.criteria_sha256 == CRITERIA["validation_v1"]


def test_family_matches_the_code_and_the_ceiling():
    ps = family_prospects(PR, load_prospects())
    fam = PR.family
    n = len(fam.members)
    assert len(ps) == n and n + len(fam.discarded) == fam.enrolled_t167 + len(fam.replacements)
    assert fam.ceiling == CEILING == 50 and fam.enrolled_t167 == 43 and PR.m <= fam.ceiling
    assert PR.m == n + fam.reserve_slots
    assert set(fam.redesigned) == {"estructura_ruptura", "tec_acuerdo_marcos"}
    assert {"elliott_onda3", "elliott_onda5_giro", "regimen_tramo",
            "regimen_tramo_estable"} <= {x.id for x in fam.discarded}


def test_a_changed_rule_is_not_preregistered():
    p = load_prospects()
    other = [x.model_copy(update={"params": {**x.params, "z": 9}}) if x.id == "pa_bos" else x
             for x in p]
    with pytest.raises(ValueError, match="pa_bos"):
        family_prospects(PR, other)


def test_accounts_and_exam_use_the_running_values():
    np_ = NurseryParams()
    a = PR.accounts
    assert (a.initial_equity_usdt, a.risk_pct, a.cost_gate_max_r, a.twins_k, a.seed) == \
        (np_.initial_equity, np_.risk_pct, np_.tf_max_cost_r, np_.twins_k, np_.seed)
    fx = PR.ladder.forward_exam
    assert fx.min_ops_month == verdict.MIN_OPS_MONTH
    assert fx.min_pos_days_frac == verdict.MIN_POS_DAYS_FRAC
    assert fx.max_cost_r == verdict.MAX_COST_R == PR.ladder.first_team.max_cost_r
    assert fx.min_closed_for_band == verdict.MIN_CLOSED_FOR_BAND
    assert tuple(fx.band_max_hours) == (verdict.SCALP_MAX_H, verdict.INTRADAY_MAX_H,
                                        verdict.THREE_DAYS_MAX_H)
    assert PR.ladder.deadline_days == verdict.TERM_DAYS


def test_sensitive_layer_is_not_hardened():
    """Decisión del usuario (2026-11-11): q = 0,10 dentro; StepM estricto solo en la puerta."""
    lad = PR.ladder
    assert lad.promise.q == 0.10 and lad.futility.mu_min_r == 0.10
    assert lad.first_team.stepm_size == 0.05 and lad.first_team.max_dd == 0.25
    assert lad.drawdown.target_edge_r == 0.25
    assert PR.false_promises["m"] == PR.m and PR.false_promises["members"] == len(PR.family.members)
