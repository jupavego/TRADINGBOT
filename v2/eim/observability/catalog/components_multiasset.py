"""Catálogo: la plataforma multiactivo (Fase 17) en el Observatorio (T102).

El escáner (`scanner.service`, T93) ya estaba; aquí entran las piezas que lo rodean, con textos
llanos: el registro de instrumentos (T89), las fuentes por clase (T90), los agentes sobre el
universo (T94), el ranking con su control del azar (T95), la salud multiactivo y el despliegue
gradual (T102). La cartera (T96) y el adaptador de papel (T103) entran como planeados.

Eventos: el escáner emite por LOTES (`eim/scanner/obs_batch.py`): un resumen por clase y paso, y
el recorrido completo solo de las candidatas más fuertes, con una traza por instrumento
(`trace_for_instrument`). Así un barrido de cientos de instrumentos no inunda el observatorio.
"""

from __future__ import annotations

from eim.observability.catalog.model import Component, c

_P = {"built": "planeado"}

MULTIASSET: tuple[Component, ...] = (
    c("instruments.registry", "data", "datos", "store", "scanner", "T89",
      "Registro de instrumentos",
      "Lista de todo lo que el sistema puede mirar, con su clase, su plaza, su calendario y su "
      "nivel de permiso. Se pone al día con una sola consulta pública cada día.",
      cadence="a diario (con el escáner)", produces=("instrument_catalog",)),
    c("data.class_sources", "data", "datos", "provider", "scanner", "T90",
      "Fuentes por clase",
      "Fichas de cada fuente de datos: qué clase cubre, con qué retraso, qué límite de uso y qué "
      "licencia. Una fuente sin ficha cuenta como solo investigación.",
      cadence="a demanda", produces=("class_series",)),
    c("scanner.deep", "data", "analisis", "engine", "scanner", "T94",
      "Agentes sobre el universo",
      "Pasa la lista corta del escáner por los analistas que pueden opinar de cada instrumento "
      "y deja oportunidades candidatas con su rastro. Nunca son órdenes.",
      cadence="tras cada barrido",
      consumes=(("scanner.service", "scanner_scores"), ("instruments.registry",
                                                        "instrument_catalog")),
      produces=("scanner_opportunities",)),
    c("scanner.rank", "validation", "validacion", "gate", "scanner", "T95",
      "Ranking y control del azar",
      "Ordena las candidatas de forma comparable, agrupa las apuestas parecidas y las mide contra "
      "un placebo y contra todas las pruebas hechas. Ninguna sale validada de aquí.",
      cadence="tras cada barrido", consumes=(("scanner.deep", "scanner_opportunities"),),
      produces=("ranked_candidates",)),
    c("scanner.health", "observability", "validacion", "service", "scanner", "T102",
      "Salud multiactivo",
      "Dice por clase y por fuente qué se vigila, con qué datos, cuán frescos y qué no se puede "
      "ver. Un mercado sin datos nunca aparece como sano; los fallos avisan en el equipo.",
      cadence="tras cada barrido",
      consumes=(("scanner.rank", "ranked_candidates"), ("data.class_sources", "class_series"),
                ("instruments.registry", "instrument_catalog")),
      produces=("multiasset_health",)),
    c("scanner.rollout", "observability", "validacion", "gate", "scanner", "T102",
      "Despliegue gradual",
      "Lleva cada clase y cada agente por alerta, simulación y papel según un protocolo escrito, y "
      "los apaga solo si se degradan. La ejecución real nunca se enciende sola.",
      cadence="tras cada barrido", consumes=(("scanner.health", "multiasset_health"),),
      produces=("rollout_level",)),
    c("scanner.portfolio", "risk", "riesgo", "engine", "scanner", "T96",
      "Cartera multiactivo",
      "Repartirá el riesgo entre clases e instrumentos sin repetir la misma apuesta. Aún no "
      "existe: espera a que el escáner supere el azar.",
      consumes=(("scanner.rank", "ranked_candidates"), ("scanner.rollout", "rollout_level")),
      produces=("portfolio_plan",), **_P),
    c("scanner.paper_adapter", "execution", "ejecucion", "service", "scanner", "T103",
      "Papel multiactivo",
      "Llevará a un intermediario de papel lo que la cartera apruebe. Aún no existe y nunca usará "
      "dinero real.",
      consumes=(("scanner.portfolio", "portfolio_plan"),), produces=("paper_order",), **_P),
)
