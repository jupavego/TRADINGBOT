from __future__ import annotations

import re
from pathlib import Path

import pytest

from eim.agents.registry import default_registry
from eim.observability import catalog as C
from eim.observability.catalog.model import MAX_EXPLAIN, STAGES
from eim.observability.thresholds import stale_after_s

STATUS = Path(__file__).resolve().parents[3] / "PLAN" / "STATUS.md"
STAGE_NAMES = ["Datos", "Análisis", "Proyección", "Plan", "Riesgo", "Ejecución / Simulación",
               "Validación y aprendizaje"]


def test_catalog_is_consistent():
    assert C.problems() == []


def test_seven_stages_with_titles_and_explanations():
    assert len(STAGES) == 7
    assert [C.STAGE_TITLES_ES[s] for s in STAGES] == STAGE_NAMES
    assert all(C.STAGE_EXPLAIN_ES[s] for s in STAGES)
    assert all(C.by_stage(s) for s in STAGES)


def test_every_registered_agent_is_in_the_catalog_with_its_version():
    reg = default_registry()
    assert reg.ids(), "el registro no puede estar vacío"
    for agent in reg.latest():
        comp = C.get(f"agent.{agent.id}")
        assert comp is not None, f"falta en el catálogo: agent.{agent.id}"
        assert comp.kind == "agent" and comp.built == "construido"
        assert comp.version == agent.version, f"{agent.id}: {comp.version} ≠ {agent.version}"


def test_catalog_agents_without_code_are_planned():
    ids = set(default_registry().ids())
    for comp in C.COMPONENTS:
        if comp.kind == "agent" and comp.built == "construido":
            assert comp.id.split(".", 1)[1] in ids, f"{comp.id}: construido pero no registrado"
        if comp.kind == "agent" and comp.built == "planeado":
            assert comp.id.split(".", 1)[1] not in ids, f"{comp.id} ya está registrado"


def test_every_edge_points_to_existing_components_and_artifacts():
    for src, dst, art in C.edges():
        assert C.has(src) and C.has(dst)
        assert art in C.BY_ID[src].produces, f"{src} no produce {art}"
    assert len(C.edges()) > 60


def test_every_component_explains_itself_to_a_non_programmer():
    for x in C.COMPONENTS:
        assert x.stage in STAGES and x.title_es.strip()
        assert 20 <= len(x.explain_es) <= MAX_EXPLAIN, x.id
        assert x.explain_es.rstrip().endswith("."), x.id


def test_ids_are_stable_unique_and_task_format():
    ids = [x.id for x in C.COMPONENTS]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"[a-z0-9_]+\.[a-z0-9_]+", i) for i in ids)


def _status_rows() -> dict[str, str]:
    rows = {}
    for line in STATUS.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*(T\d+)\s*\|.*?\|.*?\|\s*([☐◐☑])\s*\|", line)
        if m:
            rows[m.group(1)] = m.group(2)
    return rows


@pytest.mark.skipif(not STATUS.exists(), reason="PLAN/STATUS.md no está en este árbol")
def test_built_vs_planned_matches_status_md():
    rows = _status_rows()
    assert len(rows) > 50
    for x in C.COMPONENTS:
        state = rows.get(x.task)
        assert state is not None, f"{x.id}: la tarea {x.task} no existe en STATUS.md"
        if x.built == "planeado":
            assert state == "☐", f"{x.id}: {x.task} ya no está pendiente ({state})"
        else:
            assert state in "◐☑", f"{x.id}: {x.task} está pendiente pero se declara construido"


def test_planned_modules_cover_the_future_phases():
    planned_layers = {x.layer for x in C.COMPONENTS if x.built == "planeado"}
    assert {"localai", "video"} <= planned_layers   # bots (T60) y la Fase 15 ya se construyeron


def test_glossary_has_the_terms_the_view_needs():
    for term in ("sesgo", "confianza", "degradado", "veto", "SL/TP", "traza", "sin datos", "modo"):
        assert C.GLOSSARY.get(term), term


def test_signal_decision_and_order_are_three_different_components():
    assert C.has("agent.structure") and C.has("risk.engine") and C.has("execution.gateway")
    assert "risk_decision" in C.BY_ID["risk.engine"].produces
    assert "order" in C.BY_ID["execution.gateway"].produces


def test_stale_threshold_rule():
    assert stale_after_s(None) is None
    assert stale_after_s(10) == 120 and stale_after_s(60) == 180 and stale_after_s(3600) == 10800
    for x in C.COMPONENTS:
        assert x.cadence_s is None or x.cadence_s > 0
