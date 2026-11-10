# T120 — Recolectores y esferas: evidencia (2026-11-10, `juanpablo-cpu`)

## Foto de partida (API en vivo, BTCUSDT, antes del cambio)
`python -m eim.analytics.why_no_data --tf 1h` / `--tf 4h` (la herramienta nueva, contra la API vieja):

| Agente | 1 h | 4 h | Motivo real |
|---|---|---|---|
| `context` | no_data | no_data | En este equipo no hay Ollama (`E:\Ollama` no existe, `EIM_OLLAMA_EXE` sin fijar) ni `ANTHROPIC_API_KEY`. La esfera decía «sin datos» a secas. |
| `smart_money` | no_data | no_data | Ningún líder aprobado por el scorecard de T41 (17 en seguimiento). |
| `seasonality` | no_data | ok | En 1 h la historia guardada es de semanas: 1 cierre mensual < 2. |
| `derivatives` | ok | **no_data** | El ciclo solo sincroniza OI, long/short y basis en 1 h: en 4 h no había serie. **Fallo real, arreglado.** |
| `microstructure` | degraded | degraded | 38 % (1 h) y 69 % (4 h) de velas con huecos de secuencia. Con datos (`capturando`). |

Captura «antes»: `PLAN/notas/T120_esferas_antes_2026-11-10.jpg` (interfaz viva en 5173, 06:14 UTC):
Microestructura −0,19 con 11 % «degradado por huecos»; Contexto, Smart money y Estacionalidad
«sin datos» sin motivo.

## Entregables
1. **Una sola tabla de estados del recolector**: `eim/data/collectors/health.py::LABELS`
   (`unidad_ausente` · `apagado` · `sin_flujo` → «sin datos recientes» · `disco_bajo` ·
   `capturando`) y `collector_state()` con motivo y `age_s`. La usan el vigilante (texto de sus
   avisos), `GET /v2/micro/status` (`state`, `label`, `reason`, `age_s`), la esfera
   (`collectorLabel`, manda sobre el motivo del agente) y el RUNBOOK §19, que un test compara con
   el código. «acumulando n/24» y «degradado por huecos» siguen siendo del agente.
2. **Arranque comprobable**: cada latido lleva `checkout` y `proc_started_at`
   (`eim/operation/origin.py`); `GET /v2/health` añade `checkout`, `started_at` y `components`
   (vivo, edad del latido, PID, desde cuándo, checkout); `python -m eim.operation.components`
   lo imprime y sale con código 3 si algo corre desde otra carpeta. `servicio_continuo.ps1` lo
   corre al final: adopta lo de su carpeta y avisa claro de lo ajeno, sin lanzar duplicados.
3. **≥ 24 h con datos**: la microestructura del agente sale de la captura HFT desde T128. La
   ventana de T147 tuvo **58 h seguidas de horas completas** (2026-11-07T06 → 2026-11-09T15 UTC)
   con el servicio en marcha, y el snapshot de 1 h cubre 313 de 500 velas con datos reales desde el
   19-oct. La captura de hoy (`T120_esferas_antes_…jpg`) muestra la esfera con sesgo y confianza
   reales. **T104 se cierra** con esto y con la prueba de la unidad (abajo); la línea base marginal
   de ≥ 7 días queda fuera (tiempo de calendario, BACKLOG).
4. **La unidad que desaparece** (prueba real, abajo).
5. **Contexto explicado**: el motivo empieza por `sin motor de contexto` (no hay motor en el
   equipo), `motor de contexto calculando` (primer análisis en curso), `motor de contexto caído`
   (Ollama no responde, modelo sin descargar o salida ilegible: `LocalContextAnalyzer.last_problem`)
   o, en `degraded`, «sin catalizadores con fuente válida: el motor respondió… (no es el motor
   caído)». La esfera muestra cada uno con su etiqueta.
6. **Repaso de las cinco esferas de PR #111**: Liquidaciones (con datos; 4 h degradado por
   cobertura 67 %), Derivados (4 h arreglado; 15 m «sin open interest»), Contexto (§5),
   Microestructura (con datos, degradado por huecos), Smart money («sin líderes aprobados»).
   Ninguna esfera dice ya «sin datos» a secas: sin etiqueta propia se muestra la primera frase del
   motivo. Captura «después» (Vite del worktree contra la API viva):
   `PLAN/notas/T120_esferas_despues_2026-11-10.jpg` — Estacionalidad «historia corta (1/2
   meses)», Smart money «sin líderes aprobados», Contexto con su motivo.

## Prueba real de la unidad (2026-11-10 06:10–06:14 UTC)
Vigilante de microestructura temporal (`eim.data.collectors.supervise BTCUSDT --root X:\data`,
código del worktree, Binance real) sobre una unidad `X:` hecha con `subst` sobre una carpeta del
scratchpad. Los servicios vivos no se tocaron (otra carpeta de datos, otros cerrojos).

| Hora UTC | Qué | Resultado |
|---|---|---|
| 06:10:58 | arranque | `proceso_lanzado`; a los 75 s, latido con 563 trades y 587 diffs, `checkout` del worktree |
| 06:12:11 | `subst X: /d` | `X:\` deja de existir |
| 06:12:13 | — | **una** línea `en_pausa` («la unidad X:\ no está conectada»); recolector detenido |
| 06:12:58 | — | un aviso `alerta_microestructura`: «… en pausa: unidad de datos ausente» |
| 06:13:12 | `subst X: …` | unidad de vuelta |
| 06:13:13 | — | `reanudado` (`pausa_s` 60) y `proceso_lanzado`; PID nuevo |
| 06:14:27 | — | latido nuevo capturando (825 trades) |

Vigilante vivo todo el tiempo, **0 `proceso_reiniciado`, 0 trazas en stderr**, y las líneas
escritas sin unidad no se perdieron: `JsonLog` las guardó en memoria y las escribió al volver. Tras
la prueba, la poda/medición de disco también se salta mientras falta la unidad.

Nota del equipo: en `juanpablo-cpu` los datos viven en `C:` (no hay `E:`), así que hoy no hay
disco externo que se pueda soltar; lo probado cubre el caso de una carpeta de datos en una unidad
aparte (`--data-dir`).
