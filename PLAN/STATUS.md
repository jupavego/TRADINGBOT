# Estado del plan (actualizar al cerrar cada tarea)

Leyenda: ☐ pendiente · ◐ en curso · ☑ hecha

| ID | Tarea | Depende de | Estado | Notas de cierre |
|---|---|---|---|---|
| T01 | Cimientos: paquete, contratos, git, gate | — | ☑ | v2/eim/core (contratos pydantic) + v2/tests/core; pyproject, .gitignore, skill eim-new-agent. Gate OK (12 tests). |
| T02 | Red de seguridad: regresión del legado | T01 | ☐ | |
| T03 | Capa de datos y almacén | T01 | ☑ | v2/eim/data: `providers/` (Provider, BinanceFutures con reintentos/tasa), `store.py` (Parquet+DuckDB, huecos), `sync.py` (relleno incremental), `snapshot.py` (`build_snapshot`). Manual real: 6000 velas 1h BTCUSDT, 0 huecos. Evaluación OpenBB en PLAN/notas/T03_openbb.md. Gate OK (19 tests). |
| T04 | Auditoría de repos (licencia/seguridad) | — | ☑ | PLAN/notas/T04_auditoria.md: 13 repos con veredicto. Rojas: market-regime y limit-order-book sin licencia real, Freqtrade GPL, OpenBB redirige a org nueva, circuit-framework descartado. Usar: Optuna, Kronos oficial. |
| T05 | Runner de agentes + agente `structure` | T01 T02 T03 | ☐ | |
| T06 | Agentes VWAP + price action | T05 | ☐ | |
| T07 | Agentes Elliott + estacionalidad + liquidaciones | T05 | ☐ | |
| T08 | API v2 (REST + WebSocket + persistencia) | T05 | ☐ | |
| T09 | Frontend base + gráfico de velas en vivo | T08 | ☐ | |
| T10 | Panel de agentes + síntesis (UI) | T09 | ☐ | |
| T11 | Portar pestañas legadas | T10 | ☐ | |
| T12 | Agente de niveles (S/R, canal, rango) | T05 | ☐ | |
| T13 | Agente de plan (entrada/SL/TP/R:R) | T12 | ☐ | |
| T14 | Capas sobre el gráfico + hover de evidencia | T09 T12 T13 | ☐ | |
| T15 | Marcas de operaciones + bitácora + reproducción | T14 | ☐ | |
| T16 | Proyección: trayectorias OHLC (base + Kronos opc.) | T03 T05 | ☐ | |
| T17 | Escenarios (3, probabilidad, invalidación) + API | T16 T08 | ☐ | |
| T18 | Escenarios sobre el gráfico (+ toggle velas) | T09 T17 | ☐ | |
| T19 | Seguimiento y calibración de escenarios | T17 T18 | ☐ | |
| T20 | Síntesis v1 | T06 T07 T12 | ☐ | |
| T21 | Agente de derivados (funding/OI/basis) | T03 T05 | ☐ | |
| T22 | Agente de régimen (BOCPD + transición) | T05 | ☐ | |
| T23 | Microestructura: recolector + agente OFI | T03 T05 | ☐ | |
| T24 | Agente de contexto (LLM) | T05 | ☐ | |
| T25 | Backtest con costos de perpetuos | T13 T20 | ☐ | |
| T26 | Calibración (optuna, walk-forward) | T25 | ☐ | |
| T27 | **Puerta de edge** (informe de decisión) | T26 T19 | ☐ | |
| T28 | (Opcional) Laboratorio ESN con conectoma | T27 | ☐ | |
| T29 | Motor de riesgo (veto determinista) | T27 | ☐ | |
| T30 | Ejecución en testnet + reconciliación | T29 | ☐ | |
| T31 | Paper trading + kill-switch + monitoreo | T30 | ☐ | |
| T32 | Endurecimiento y documentación | T31 | ☐ | |
