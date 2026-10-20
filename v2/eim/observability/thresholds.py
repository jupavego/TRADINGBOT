"""Umbrales numéricos del observatorio, fijados en T72 ANTES de construir T73–T76.

Justificación y mediciones: `PLAN/notas/T72_decisiones.md`. Cambiarlos exige reabrir esa nota.
"""

from __future__ import annotations

# Emisor (medido: p50 50 µs, p95 148 µs, p99 371 µs por emit() en el equipo de referencia)
EMIT_P95_US_MAX = 500            # coste de emit() en el hilo que llama, percentil 95
MAX_EVENTS_PER_CYCLE = 100       # un ciclo no emite más que esto (el resto se agrega)
MAX_CYCLE_OVERHEAD_MS = 50       # sobrecosto absoluto máximo por ciclo…
MAX_CYCLE_OVERHEAD_FRACTION = 0.01  # …y como fracción del tiempo del ciclo (lo que sea menor)
QUEUE_MAX = 10_000               # cola acotada por proceso; llena → se descarta y se cuenta

# Retención
SPOOL_RETENTION_DAYS = 7         # JSONL del spool, ya indexados o no (T73 avisa si no se indexan)
EVENT_RETENTION_DAYS = 30        # eventos en la base del indexador
SPOOL_ALERT_MB = 500             # tamaño del spool que dispara una alerta
EVENTS_PER_DAY_DESIGN = 100_000  # volumen de diseño (≈ 33 MB/día a ~335 B por línea)

# «Sin datos»: un componente no emite en `STALE_FACTOR` × su cadencia (mínimo `STALE_MIN_S`)
STALE_FACTOR = 3
STALE_MIN_S = 120

# Mapa (T75): presupuesto de la librería de grafo en el equipo de referencia
GRAPH_NODES_TARGET = 80
GRAPH_REDRAW_MS_MAX = 50         # redibujado completo de 60–80 nodos
GRAPH_BUNDLE_GZIP_KB_MAX = 200   # peso añadido a la interfaz


def stale_after_s(cadence_s: int | None) -> int | None:
    """Segundos sin eventos a partir de los cuales un componente se pinta «sin datos».
    None = componente a demanda: no hay umbral, se muestra solo la antigüedad."""
    if cadence_s is None:
        return None
    return max(STALE_MIN_S, STALE_FACTOR * cadence_s)

# Indexador y consultas (T73, fijados antes de construirlo; ver `PLAN/notas/T72_decisiones.md` §6)
RUN_RETENTION_DAYS = 180         # `runs` y `decisions` viven más que los eventos crudos (30 d)
INDEX_INTERVAL_S = 5.0           # pausa entre pasadas del indexador dentro de la API
INDEX_LAG_S_MAX = STALE_MIN_S    # retraso de indexación aceptable: lo mismo que «sin datos»
TRUNCATED_LINE_GRACE_S = 60      # línea sin salto final que no crece en este tiempo = corrupta
QUERY_P95_MS_MAX = 100           # consulta con 100 000 eventos indexados (p95; medido ≤ 32)
PAGE_MAX = 500                   # filas por página en la API de solo lectura

# Calidad de la evidencia (T76): un dato es «obsoleto» si su antigüedad supera este múltiplo del
# marco de la vela (una vela de 1 h con un dato de más de 2 h). Solo informa; no excluye nada.
EVIDENCE_STALE_TF_FACTOR = 2
