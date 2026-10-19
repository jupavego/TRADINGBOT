"""Observatorio (Fase 15): eventos, catálogo de componentes y emisor a prueba de fallos.

Los procesos NO escriben en la base: emiten JSONL a `data/obs/spool/` y un único indexador
(T73) los carga.
Emisor: `from eim.observability.emit import configure, emit, span` (no se reexporta aquí
para que `emit` siga siendo el módulo).
Observar no es operar: nada aquí envía órdenes ni toca posiciones.
"""

from eim.observability.events import EVENT_KINDS, ObsEvent, Ref, trace_for

__all__ = ["EVENT_KINDS", "ObsEvent", "Ref", "trace_for"]
