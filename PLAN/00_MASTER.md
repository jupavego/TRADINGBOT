# Plan maestro — EIM Agente de trading

## Cómo usar este plan (una tarea = una sesión)
Abre una sesión nueva y escribe: `Ejecuta PLAN/T05.md`. Nada más; `CLAUDE.md` se carga solo. Al terminar, la sesión actualiza `PLAN/STATUS.md`.
Cada tarea es autocontenida: qué leer, qué entregar, criterios de aceptación y qué NO hacer. Cada una sugiere esfuerzo (bajo/medio basta para casi todas; alto solo donde se indica).

## Fases y orden
| Fase | Tareas | Resultado |
|---|---|---|
| 0 Cimientos | T01 T02 T03 T04 | Paquete `eim/`, contratos, red de seguridad del legado, datos, auditoría de repos |
| 1 Agentes | T05 T06 T07 | Runner de agentes y módulos actuales migrados |
| 2 API + UI base | T08 T09 T10 T11 | Tablero con gráfico en vivo y panel de agentes |
| 3 Niveles y plan | T12 T13 T14 T15 | Soportes/resistencias, canal, entrada/SL/TP dibujados; marcas y reproducción |
| 4 Proyección | T16 T17 T18 T19 | 3 escenarios con probabilidad sobre el gráfico + calibración |
| 5 Inteligencia | T20 T21 T22 T23 T24 | Síntesis y agentes nuevos (derivados, régimen, microestructura, contexto) |
| 6 Validación | T25 T26 T27 (T28 opcional) | Backtest con costos de perpetuos, calibración, **puerta de edge** |
| 7 Operación | T29 T30 T31 T32 | Riesgo, testnet, paper trading, endurecimiento |

Dependencias: ver `STATUS.md`. Paralelizables en sesiones distintas: T06‖T07, T09‖T16, T12‖T21‖T22‖T23.
**Puntos de decisión humana:** fin de T10 (¿la UI sirve?), T19 (¿las probabilidades están calibradas?), T27 (¿hay edge? si no, se corrige antes de T29) y T31 (¿pasamos a dinero real?).

## Skills y plugins (investigados)
No hay skills de trading cuantitativo en el catálogo. Lo útil:
| Recurso | Uso | Cuándo |
|---|---|---|
| `CLAUDE.md` + `PLAN/` | Contexto fijo y corto | Siempre |
| Skill `run` | Levantar la app y comprobarla | Tareas con API/UI |
| Skill `simplify` | Limpieza al cerrar tarea | Cierre de tarea |
| Skill `code-review` (nivel low/medium) | Revisión barata del diff | T05, T16, T25, T29, T30 |
| Skill `dataviz` | Colores y diseño de gráficos consistentes | T09–T19 |
| Skill `claude-api` | Llamadas a Claude con caché y salida estructurada | T24 |
| Skill `update-config` | Hooks (ruff+pytest tras editar) y permisos | Antes de T01 (opcional) |
| Skill `fewer-permission-prompts` | Allowlist para menos interrupciones | Tras 2–3 sesiones |
| Skill `skill-creator` | Skills propios (`eim-new-agent`, `eim-verify`) | T01 |
| Plugin `frontend-design` (Anthropic) | Calidad visual de la UI | T09–T19 (instalar antes) |
| Plugin `quick-gate-python` (comunidad) | Ruff+Pyright+pytest con auto-reparación acotada | Opcional |
| Plugin `TradingCalc` (MCP remoto) | **No recomendado**: envía datos a un tercero; la aritmética se escribe y prueba localmente (T25) | — |

## Repos a reciclar (detalle y auditoría en T04)
NautilusTrader (ejecución/backtest, T25/T30) · Kronos (trayectorias OHLC, T16, opcional frente a línea base) · TradingAgents y circuit-framework (patrón multiagente, T20/T24) · OpenBB (datos, T03 evaluar) · de los 36 locales: Kats/BOCPD y market-regime (T22), limit-order-book y crypto_lob_stream (T23), optuna (T26), hftbacktest (T23 referencia). Ver `repos/repo_profiles_master.md`.

## Reglas de eficiencia de tokens
1. Una tarea por sesión; sesión nueva por tarea.
2. Legado grande: Grep, no lectura completa.
3. Decisiones y estado en archivos (`STATUS.md`, `BACKLOG.md`), no en el chat.
4. Salidas de tests/logs: solo resumen (`-q`, `--tb=short`).
5. Subagentes solo para investigación pesada y paralela (T04, T23, T25), no para tareas lineales.
6. Revisión y verificación visual al final de la tarea, no en cada edición.
