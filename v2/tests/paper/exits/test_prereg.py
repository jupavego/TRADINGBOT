"""T131 — el pre-registro es inmutable: si se edita, el banco no arranca.

Es la pieza que impide ajustar la rejilla, los tramos o los criterios después de ver los
resultados. La prueba de que funciona es que una coma de más en el archivo publicado rompe la
carga con un motivo claro, igual que con los criterios de T49 (`validation_v1`).
"""

from __future__ import annotations

import json

import pytest

from eim.paper.exits import prereg as pr


def test_the_published_version_loads_and_its_hash_matches():
    p = pr.load_prereg()
    assert p.version == pr.DEFAULT_VERSION
    assert p.sha256 == pr.PUBLISHED[pr.DEFAULT_VERSION]
    assert p.symbol == "BTCUSDT" and p.seed == 131 and p.risk_usd > 0


def test_editing_a_published_file_fails_with_the_reason(tmp_path):
    raw = (pr.VERSIONS_DIR / f"{pr.DEFAULT_VERSION}.json").read_bytes()
    data = json.loads(raw)
    data["accept"]["pbo_max"] = 0.9                   # relajar un criterio a posteriori
    bad = tmp_path / f"{pr.DEFAULT_VERSION}.json"
    bad.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="versión nueva"):
        pr.load_prereg(path=bad)


def test_a_file_whose_name_and_version_disagree_fails(tmp_path):
    data = json.loads((pr.VERSIONS_DIR / f"{pr.DEFAULT_VERSION}.json").read_bytes())
    other = tmp_path / "prereg_t131_v9.json"
    other.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="no coincide"):
        pr.load_prereg(path=other)


def test_an_unknown_field_is_refused_instead_of_ignored(tmp_path):
    data = json.loads((pr.VERSIONS_DIR / f"{pr.DEFAULT_VERSION}.json").read_bytes())
    data["accept"]["atajo"] = True
    p = tmp_path / "prereg_t131_v9.json"
    data["version"] = "prereg_t131_v9"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(Exception, match="atajo"):
        pr.load_prereg(path=p)


def test_the_grid_counts_every_attempt_including_what_t132_has_not_built_yet():
    p = pr.load_prereg()
    by_id = {g.id: g for g in p.grid}
    assert set(by_id) == {"M0", "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8",
                          "S1", "S2", "S3"}
    assert by_id["M2"].combos == 3 * 5 * 3            # k × σ × activación
    assert by_id["S3"].combos == 2 * 3 * 2            # E12: los parámetros de T136 cuentan
    assert p.attempts() == sum(g.combos for g in p.grid) == 107
    assert p.implemented() == ("M0", "M1")
    assert set(p.pending()) == set(by_id) - {"M0", "M1"}
    assert p.pending()["M4"] == "pendiente_T133"


def test_the_design_is_the_one_of_5_3():
    d = pr.load_prereg().design
    assert (d.fit_months, d.test_months, d.step_months) == (12, 3, 3)
    assert d.start.startswith("2023-01-01") and d.end.startswith("2026-08-16")
    assert d.path_timeframe == "15m" and d.fine_timeframe == "1m"
    assert d.embargo_quantile == 0.99 and d.embargo_feature_hours >= 200


def test_the_acceptance_criteria_are_the_ones_of_5_4():
    a = pr.load_prereg().accept
    assert a.bases == ("M0", "M1")
    assert a.win_loss_ratio_min == 0.5                # hoy 0,11
    assert a.pf_vs_base_min == 1.15 and a.max_dd_vs_base_max == 1.1
    assert a.pbo_max == 0.2 and a.cvar_not_worse is True
    assert a.years == (2023, 2024, 2025, 2026)
    assert a.prospective_weeks_min >= 4


def test_the_cost_stress_includes_the_approval_factor():
    c = pr.load_prereg().cost_stress
    assert c.stop_slip_multipliers == (1.0, 1.5, 2.0)
    assert c.approve_at in c.stop_slip_multipliers and c.approve_at > 1


def test_asking_for_a_variant_outside_the_grid_fails():
    with pytest.raises(KeyError, match="rejilla pre-registrada"):
        pr.load_prereg().item("M99")


def test_the_selection_objective_is_declared_not_improvised():
    s = pr.load_prereg().selection
    assert s.objective == "expectancy_r" and s.base == "M0"
    assert s.choose == "plateau_center" and s.plateau_keep == 0.7
    assert "cvar95_r_not_worse_than_base" in s.constraints
