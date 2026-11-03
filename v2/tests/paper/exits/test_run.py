"""T131 — la corrida completa del banco de punta a punta, con un pre-registro de juguete.

Con un paseo aleatorio de 10 meses y entradas al azar se comprueba que las piezas encajan en el
orden que fija el pre-registro y que el resultado es honesto: sin fugas entre tramos, con las
variantes pendientes declaradas, con el control en su sitio y con un informe que se puede leer.
Las cifras no importan aquí (es ruido); lo que importa es que el banco no se engañe a sí mismo.
"""

from __future__ import annotations

import json

import pytest

from eim.paper.exits import run
from eim.paper.exits.prereg import VERSIONS_DIR, load_prereg
from eim.paper.exits.report import render
from tests.paper.exits.helpers import COSTED, LADDER, ctx, random_ideas, walk_path

MONTH_BARS = 30 * 96        # velas de 15 m en 30 días
SEED = 131


@pytest.fixture(scope="module")
def small_prereg(tmp_path_factory):
    """El pre-registro real con tramos y réplicas pequeños (no publicado: sin huella fijada)."""
    data = json.loads((VERSIONS_DIR / "prereg_t131_v1.json").read_bytes())
    data["version"] = "prereg_t131_v9"
    data["design"] |= {"fit_months": 2, "test_months": 1, "step_months": 1,
                       "embargo_feature_hours": 24, "start": "2025-01-01T00:00:00Z",
                       "end": "2030-01-01T00:00:00Z"}
    data["bootstrap"]["reps"] = 1000
    data["multiple"]["reps"] = 1000
    data["ruin"] |= {"reps": 50, "trades": 50}
    p = tmp_path_factory.mktemp("prereg") / "prereg_t131_v9.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return load_prereg(path=p)


@pytest.fixture(scope="module")
def world():
    path = walk_path(13 * MONTH_BARS, seed=SEED)
    ideas = (random_ideas(path, 200, seed=SEED + 1, strategy="consenso")
             + random_ideas(path, 60, seed=SEED + 2))          # las del control
    return path, ideas


def test_the_runnable_grid_is_the_pre_registered_one(small_prereg):
    vs = run.variants_of(small_prereg, LADDER)
    assert [v.id for v in vs] == [
        "M0 first_r=0.075", "M0 first_r=0.1", "M0 first_r=0.25", "M0 first_r=0.5",
        "M0 first_r=1", "M1 be=0.5/0", "M1 be=0.5/0.1", "M1 be=1/0", "M1 be=1/0.1",
        "M1 be=1.5/0", "M1 be=1.5/0.1"]
    assert run.base_id("M0") == "M0 first_r=0.1" and run.base_id("M1") == "M1 be=1/0.1"
    assert sum(v.is_base for v in vs) == 2
    assert all(v.policy.id == v.id for v in vs)


def test_the_plateau_neighbours_never_cross_from_one_family_to_another(small_prereg):
    nb = run.neighbours_of(run.variants_of(small_prereg, LADDER))
    assert nb["M0 first_r=1"] == ["M0 first_r=0.5"]
    assert nb["M1 be=0.5/0"] == ["M1 be=0.5/0.1"]
    for k, vs in nb.items():
        assert all(v.split()[0] == k.split()[0] for v in vs)


@pytest.fixture(scope="module")
def result(world, small_prereg):
    path, ideas = world
    return run.analyse(ideas, ctx(path, COSTED), small_prereg, LADDER)


def test_the_bench_pairs_the_same_entries_for_every_variant(result):
    b = result["bench"]
    assert b["ideas"] > 100 and b["paired"] > 50
    assert len(b["policies"]) == 11
    assert set(b["dropped"]) == set(b["policies"])


def test_there_are_no_leaks_between_fit_and_test_in_any_fold(result):
    w = result["walkforward"]
    assert w["leaks_total"] == 0
    assert len(w["folds"]) >= 8
    for f in w["folds"]:
        assert f["fold"]["embargo_hours"] >= 24          # la ventana de los rasgos, como mínimo
        p = f["fit"][run.base_id("M0")]["purga"]
        assert p["kept"] <= p["in_window"]
        assert "selection" in f and "reason" in f["selection"]


def test_the_control_entries_are_measured_apart_and_never_enter_the_bench(world, small_prereg,
                                                                         result):
    path, ideas = world
    ctrl = run.control_report(ideas, ctx(path, COSTED), small_prereg, LADDER)
    assert ctrl["n_ideas"] == 60
    assert result["bench"]["ideas"] <= 200              # el banco solo lleva las 200 reales
    for v in ctrl["variants"].values():
        assert v["n"] >= 0 and "gross_ci" in v


def test_the_multiplicity_block_reports_both_corrections_against_both_bases(result):
    for base, blk in result["multiplicity"].items():
        assert blk["base"] == base
        assert set(blk["p_rw"]) == set(blk["p_holm"]) == set(blk["p_raw"])
        assert base not in blk["p_rw"]                  # una base no compite contra sí misma
        for k in blk["p_rw"]:
            assert blk["p_rw"][k] >= blk["p_raw"][k]
            assert blk["p_holm"][k] >= blk["p_raw"][k]


def test_the_pbo_is_computed_over_the_test_spans(result):
    pb = result["pbo"]
    assert pb["pbo"] is not None, pb.get("reason")
    assert pb["variants"] == 11 and pb["splits"] == 8
    assert 0.0 <= pb["pbo"] <= 1.0


def test_the_pending_variants_and_the_attempts_are_declared(result):
    assert result["attempts"] == 107
    assert set(result["pending_variants"]) >= {"M2", "M3", "M4", "M5", "M6", "M7", "M8",
                                               "S1", "S2", "S3"}
    for v in result["variants"].values():
        assert "dsr" in v and "years" in v and "by_regime" in v


def test_random_entries_do_not_turn_profitable_with_any_implemented_exit(result):
    """El banco mide ruido: ninguna variante puede salir con E[R] neto claramente positivo."""
    for vid, v in result["variants"].items():
        exp = v["test"].get("expectancy_r")
        if exp is not None and v["test"]["n"] >= 20:
            assert exp < 0.5, f"{vid}: E[R] {exp:+.3f} sobre entradas al azar"


def test_the_adapters_are_identical_to_the_engine_t111_called(world, small_prereg):
    """Regresión de T111 sobre el mismo camino que usa el banco, no solo sobre fixtures."""
    path, ideas = world
    got = run.engine_identity(ideas, ctx(path, COSTED), LADDER, small_prereg.risk_usd, 120)
    assert got["identical"] is True and got["mismatches"] == []
    assert got["checked"] > 50


def test_a_broken_adapter_would_be_caught(world, small_prereg, monkeypatch):
    """Si el adaptador dejara de delegar, la comprobación lo diría en vez de callarlo."""
    from dataclasses import replace

    from eim.paper.exits import run as run_mod

    path, ideas = world
    real = run_mod.simulate

    def shifted(idea, p, ep):
        o = real(idea, p, ep)
        return replace(o, mfe_r=o.mfe_r + 1.0)

    monkeypatch.setattr(run_mod, "simulate", shifted)
    got = run_mod.engine_identity(ideas, ctx(path, COSTED), LADDER, small_prereg.risk_usd, 40)
    assert got["identical"] is False
    assert all(m["policy"] == "M1" and "mfe_r" in m["fields"] for m in got["mismatches"])


def test_the_report_renders_with_everything_that_matters(world, small_prereg, result):
    path, ideas = world
    ctrl = run.control_report(ideas, ctx(path, COSTED), small_prereg, LADDER)
    meta = {"prereg": small_prereg.to_json(), "symbol": "BTCUSDT", "commit": "abc1234",
            "built": "2026-11-03T18:00+00:00", "data": "copia"}
    md = render(meta, result, ctrl)
    for piece in ("# T131", "Pliegues, purga y embargo", "Pruebas múltiples",
                  "Control aleatorio", "Sharpe deflactado", "Lo que este informe NO dice",
                  "Fugas entre tramos: 0", "pendiente_T132"):
        assert piece in md, piece
    assert "T134" in md                                  # la decisión no es de este informe
