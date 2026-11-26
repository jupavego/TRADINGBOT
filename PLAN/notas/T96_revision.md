# Revisión para decidir T96 — regla fijada el 2026-11-26

**Origen:** ◆ de T95. El placebo dijo que hoy el escáner **no supera el azar** (mejor candidata real 0,664 frente al umbral 0,669; p global 0,16). El usuario **aceptó el resultado y pausó T96** hasta tener evidencia hacia adelante. Cambiar esta regla = archivo nuevo, nunca editar este.

## Qué corre solo
- **Cada día, 00:45 UTC (19:45 Bogotá)** — tarea «EIM - escaner diario (T95)» (`v2/scripts/escaner_diario.ps1`, solo en la laptop): catálogo y velas al día, barrido, pasada de agentes con ranking y registro de intentos. Vigía propio: comprueba que la vista salió con el ranking; si no, reintenta a los 20 min; registro en `data/operation/logs/escaner_diario.log`.
- **2026-12-29, 09:00 hora local** (o en cuanto se encienda la laptop) — tarea «EIM - revision para decidir T96 (2026-12-29)» (`v2/scripts/revision_t96.ps1`): `python -m eim.scanner calibrate` (adopta pesos solo si mejoran fuera de muestra), repite el placebo con los pesos vigentes y corre `scripts/scanner_revision.py`. Informe en `TRADINGBOT/_revision_t96.md`.

## Regla (α = 0,05 de `validation_v1`)
1. **Muestra mínima:** ≥ 200 resultados maduros de la síntesis (a 25 velas, netos del costo de su clase). Si no se llega → **POSPONER** 4 semanas (y revisar que el escáner corrió a diario).
2. **La síntesis gana al azar hacia adelante:** media de los resultados > 0 y p < α en la prueba de lado al azar con **una media por día de decisión** (los instrumentos de un mismo día comparten mercado; los horizontes de días seguidos se solapan, así que este p es optimista y por eso no basta solo).
3. **El placebo repetido ese día supera el azar** con la regla del pre-registro de T95.
- **ARRANCAR T96** solo si se cumplen 2 **y** 3. Si no → **NO ARRANCAR**: repetir en 4 semanas o replantear la fase 17. En ningún caso se valida nada: la única puerta que valida es la v1 de T49.
