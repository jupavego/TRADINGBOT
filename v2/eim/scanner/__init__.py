"""Escáner global (T93, 1/2): universo, embudo, cola y caché. Modo ANÁLISIS, sin órdenes.

Mira miles de instrumentos con un presupuesto de cómputo medido (T87: ≤ 20 ms por instrumento)
y entrega una lista corta a los agentes profundos (T94):

1. **Universo** (`universe.py`): etapa 1, descubrimiento (estado, vencimiento, perpetuo,
   moneda, permiso, pre-OPV) y etapa 2, datos (suficientes, frescos según su calendario,
   mercado abierto, liquidez y diferencial). Cada exclusión con su motivo y su contador.
2. **Etapa 3** (`screen.py`): puntuación de interés vectorizada con NumPy sobre el panel
   (`panel.py`), con métricas de calidad. No es una señal: decide a quién mirar.
3. **Cola** (`queue.py`, `backends.py`, `jobs.py`): prioridad, procesos acotados, caché por
   `(instrumento, marco, hash de datos, versión)`, reintentos, tasa por proveedor, reanudación
   y cancelación limpia.
4. **Ritmos** (`rhythms.py`): rápido (alertas de precio y diferencial sobre lo ya puntuado) y
   profundo (lista corta a la cola), sin mirar mercados cerrados ni datos viejos.
5. **Servicio** (`service.py`, `runner.py`, `__main__.py`): `python -m eim.scanner run|status`,
   latido, registro en `data/scanner/scanner.duckdb` y eventos muestreados al Observatorio.
6. **Medición** (`budget.py`): `reports/scanner_budget.md`.
7. **Agentes y oportunidades** (T94: `deep.py`, `candidates.py`, `deep_service.py`): los agentes
   elegibles sobre la lista corta y oportunidades candidatas trazables, nunca órdenes.
8. **Ranking y azar** (T95: `rank.py`, `clusters.py`, `multiplicity.py`, `rank_service.py`,
   `placebo.py`, `placebo_eval.py`): prioridad comparable, apuestas correlacionadas agrupadas,
   registro de intentos con Holm/BH sobre la familia completa y umbral del placebo.

La E/S (catálogo, almacén, red, base) vive en `eim/data/scanner_market.py` y
`eim/data/scanner_store.py`.
"""
