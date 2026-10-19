"""Catálogo de componentes del observatorio (T72): el grafo estructural del sistema.

Datos en `components*.py`; aquí solo el acceso y las comprobaciones de consistencia
(`problems()` devuelve la lista de defectos; vacía = catálogo sano).
"""

from __future__ import annotations

from eim.observability.catalog.components import COMPONENTS
from eim.observability.catalog.glossary import GLOSSARY
from eim.observability.catalog.model import (
    MAX_EXPLAIN,
    STAGE_EXPLAIN_ES,
    STAGE_TITLES_ES,
    STAGES,
    Component,
    Flow,
)

BY_ID: dict[str, Component] = {x.id: x for x in COMPONENTS}


def get(component_id: str) -> Component | None:
    return BY_ID.get(component_id)


def has(component_id: str) -> bool:
    return component_id in BY_ID


def by_stage(stage: str) -> list[Component]:
    return [x for x in COMPONENTS if x.stage == stage]


def edges() -> list[tuple[str, str, str]]:
    """(origen, destino, artefacto) de todo el grafo estructural."""
    return [(f.source, x.id, f.artifact) for x in COMPONENTS for f in x.consumes]


def problems() -> list[str]:
    """Defectos del catálogo: ids repetidos, aristas hacia componentes o artefactos que no
    existen, textos ausentes o demasiado largos, etapas vacías."""
    out: list[str] = []
    seen: set[str] = set()
    for x in COMPONENTS:
        if x.id in seen:
            out.append(f"id repetido: {x.id}")
        seen.add(x.id)
        if not x.explain_es.strip() or not x.title_es.strip():
            out.append(f"{x.id}: falta title_es/explain_es")
        if len(x.explain_es) > MAX_EXPLAIN:
            out.append(f"{x.id}: explain_es de {len(x.explain_es)} caracteres (máx {MAX_EXPLAIN})")
        for f in x.consumes:
            src = BY_ID.get(f.source)
            if src is None:
                out.append(f"{x.id}: consume de un componente inexistente ({f.source})")
            elif f.artifact not in src.produces:
                out.append(f"{x.id}: {f.source} no produce «{f.artifact}»")
    for s in STAGES:
        if not by_stage(s):
            out.append(f"etapa sin componentes: {s}")
    return out


__all__ = [
    "BY_ID", "COMPONENTS", "GLOSSARY", "STAGES", "STAGE_EXPLAIN_ES", "STAGE_TITLES_ES",
    "Component", "Flow", "by_stage", "edges", "get", "has", "problems",
]
