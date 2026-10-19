"""Catálogo completo: construido (agentes + flujo + operación) y planeado. Solo datos."""

from __future__ import annotations

from eim.observability.catalog.components_agents import AGENTS
from eim.observability.catalog.components_flow import CORE
from eim.observability.catalog.components_planned import PLANNED

COMPONENTS = AGENTS + CORE + PLANNED
