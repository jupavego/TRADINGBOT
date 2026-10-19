"""Modelo del catálogo de componentes (T72): datos declarativos, sin lógica de negocio.

El catálogo es el grafo ESTRUCTURAL (lo que el sistema declara ser). El grafo de EJECUCIÓN
(lo que de verdad pasó) sale de los eventos; las diferencias entre ambos se muestran (T75).
Textos para quien no programa: `title_es` y `explain_es` (≤ 280 caracteres, lenguaje llano).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from eim.core.market import Frozen

Stage = Literal["datos", "analisis", "proyeccion", "plan", "riesgo", "ejecucion", "validacion"]
STAGES: tuple[str, ...] = Stage.__args__  # type: ignore[attr-defined]
STAGE_TITLES_ES: dict[str, str] = {
    "datos": "Datos",
    "analisis": "Análisis",
    "proyeccion": "Proyección",
    "plan": "Plan",
    "riesgo": "Riesgo",
    "ejecucion": "Ejecución / Simulación",
    "validacion": "Validación y aprendizaje",
}
STAGE_EXPLAIN_ES: dict[str, str] = {
    "datos": "Se reúne lo que el sistema necesita saber: precios, noticias, calendario y líderes.",
    "analisis": "Cada analista mira los datos desde su especialidad y da su opinión con una confianza.",
    "proyeccion": "Se simulan futuros posibles y se resumen en tres escenarios con probabilidad.",
    "plan": "Con la opinión conjunta se propone una operación: entrada, salida de pérdida y objetivo.",
    "riesgo": "Un código fijo, sin opinión, aprueba, ajusta el tamaño o veta el plan.",
    "ejecucion": "Si el riesgo aprueba, la orden se envía al simulador o a la testnet (nunca dinero real).",
    "validacion": "Se comprueba si lo que funcionó fue suerte y qué se aprende de cada resultado.",
}

Layer = Literal[
    "data", "agent", "forecast", "synthesis", "risk", "execution", "operation", "api", "web",
    "paper", "validation", "leaders", "arbitrage", "library", "bots", "localai", "video",
    "observability",
]
Kind = Literal["agent", "provider", "store", "engine", "gate", "service", "view"]
Built = Literal["construido", "planeado"]
MAX_EXPLAIN = 280


class Flow(Frozen):
    """Una arista: este componente recibe `artifact` de `source`."""

    source: str
    artifact: str


class Component(Frozen):
    id: str = Field(pattern=r"^[a-z0-9_]+\.[a-z0-9_]+$")  # «capa.nombre», estable
    layer: Layer
    stage: Stage
    kind: Kind
    process: str                      # proceso donde corre: api, leaders, collector, cli, …
    version: str | None = None        # versión del agente/contrato si existe
    cadence: str                      # texto llano: «cada vela de 1 h», «cada 10 s», «a demanda»
    cadence_s: int | None = None      # segundos esperados entre eventos (None = a demanda)
    consumes: tuple[Flow, ...] = ()
    produces: tuple[str, ...] = ()
    built: Built
    task: str = Field(pattern=r"^T\d+$")  # tarea de PLAN/STATUS.md que lo construye / lo construirá
    title_es: str = Field(min_length=3, max_length=60)
    explain_es: str = Field(min_length=20, max_length=MAX_EXPLAIN)

    @model_validator(mode="after")
    def _agent_has_version(self) -> Component:
        if self.kind == "agent" and self.built == "construido" and not self.version:
            raise ValueError(f"{self.id}: un agente construido declara su versión")
        return self


def c(id: str, layer: Layer, stage: Stage, kind: Kind, process: str, task: str,
      title_es: str, explain_es: str, *, cadence: str = "a demanda",
      cadence_s: int | None = None, consumes: tuple[tuple[str, str], ...] = (),
      produces: tuple[str, ...] = (), version: str | None = None,
      built: Built = "construido") -> Component:
    """Constructor compacto para las tablas de datos."""
    return Component(
        id=id, layer=layer, stage=stage, kind=kind, process=process, version=version,
        cadence=cadence, cadence_s=cadence_s,
        consumes=tuple(Flow(source=s, artifact=a) for s, a in consumes), produces=produces,
        built=built, task=task, title_es=title_es, explain_es=explain_es)
