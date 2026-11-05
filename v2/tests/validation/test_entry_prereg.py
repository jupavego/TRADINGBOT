"""El pre-registro de T137 es inmutable y sus cuentas cuadran con el catálogo real."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from eim.paper.catalog import CATALOG
from eim.paper.params import ExecParams
from eim.validation.criteria import load_criteria
from eim.validation.entry_prereg import PREREG_DIR, PUBLISHED, load_prereg


def test_published_file_loads_with_pinned_hash():
    p = load_prereg()
    assert p.version == "prereg_t137_v1" and p.sha256 == PUBLISHED[p.version]
    assert p.criteria == "validation_v1" and p.mode == "SIMULADO"
    assert p.geometry.m8.q == 0.95 and p.geometry.s1.d_min_sigma == 3.0
    assert p.geometry.s1.sigma == "atr14" and p.cost_cap.max_cost_r == 0.08


def test_edited_file_is_refused(tmp_path):
    raw = json.loads((PREREG_DIR / "prereg_t137_v1.json").read_text(encoding="utf-8"))
    raw["cost_cap"]["max_cost_r"] = 0.2      # «ajustar» el tope tras ver resultados
    p = tmp_path / "prereg_t137_v1.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="versión nueva"):
        load_prereg(path=p)


def test_frozen_in_memory():
    p = load_prereg()
    with pytest.raises(ValidationError):
        p.cost_cap.max_cost_r = 1.0          # type: ignore[misc]


def test_every_strategy_of_the_catalog_counts_as_attempts():
    """Se declara TODO el catálogo: las cuentas de Holm salen de él, no de una lista elegida."""
    p = load_prereg()
    tfs = ExecParams().timeframes
    by_tf = {tf: sum(1 for i in CATALOG.values() if i.runs_in(tf)) for tf in tfs}
    assert p.strategies.by_timeframe == by_tf
    assert p.attempts.per_variant == sum(by_tf.values())
    assert p.attempts.total == p.attempts.per_variant * len(p.variants)


def test_null_reps_are_the_ones_of_the_criteria():
    """Las réplicas declaradas son las que `validation_v1` exige para esa familia de Holm."""
    p = load_prereg()
    assert load_criteria().null_reps(p.attempts.family) == p.attempts.null_reps


def test_only_the_official_reading_gives_a_verdict():
    p = load_prereg()
    assert {r.id for r in p.readings} == {"oficial", "reserva", "banco"}
    assert [r.id for r in p.readings if r.verdict] == ["oficial"]


@pytest.mark.parametrize("edit", [
    lambda d: d["attempts"].update(total=519),
    lambda d: d["attempts"].update(family=1),
    lambda d: d["variants"][1].update(n=d["variants"][0]["n"]),
    lambda d: d["readings"][1].update(verdict=True),
])
def test_incoherent_counts_are_refused(tmp_path, edit):
    raw = json.loads((PREREG_DIR / "prereg_t137_v1.json").read_text(encoding="utf-8"))
    edit(raw)
    p = tmp_path / "prereg_t137_v1.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_prereg(path=p, strict=False)
