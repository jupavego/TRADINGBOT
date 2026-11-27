"""Catálogo completo: construido (agentes + flujo + operación + multiactivo, T102) y planeado.
Solo datos."""

from __future__ import annotations

from eim.observability.catalog.components_agents import AGENTS, BOTS
from eim.observability.catalog.components_flow import CORE
from eim.observability.catalog.components_multiasset import MULTIASSET
from eim.observability.catalog.components_planned import PLANNED

COMPONENTS = AGENTS + BOTS + CORE + MULTIASSET + PLANNED
