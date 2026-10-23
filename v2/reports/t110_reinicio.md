# T110 — Reinicio real con una posición protegida abierta (2026-10-22)

Evidencia del criterio de aceptación: «un reinicio real del servicio con una posición protegida
abierta conserva el escalón y el stop vigente». Todo SIMULADO.

**Montaje.** La API en vivo (puerto 8000, corrida de T31) no se tocó. Se levantó la API de la rama
de T110 (`uvicorn` con `create_app()`, puerto 8011) sobre una carpeta de datos **sintética**: 760
velas de 1 h y sus 15 m a escala BTC (paseo aleatorio + 16 h finales al alza), contextos `vivo` en
las últimas 30 velas. Sin red: `EIM_PAPER=0` (sin ciclo que descargue velas reales),
`EIM_CALENDAR=0`, `EIM_ARBITRAGE=0`, `EIM_AUTO_HISTORY=0`, `EIM_SHARE_AUTO=0`. La vista se calcula
con `GET /v2/paper`; cada «reinicio» es matar el proceso y arrancarlo de nuevo sobre la misma base.

| Arranque | Qué cambió | Diario (`GET /v2/paper/protection`) | API (`GET /v2/paper`, posición) |
|---|---|---|---|
| 1 | — | 6 filas nuevas; Conservador y Moderado `plan_tp2`: seq 2 `escalon`, **escalón 1, SL 69 646,4**, `t` 2025-11-08 04:00 UTC | escalón 1, SL 69 646,4, `protegida` |
| 2 | proceso nuevo, mismos datos y parámetros | **0 filas nuevas**; la vigente sigue siendo seq 2 (escalón 1, SL 69 646,4) | escalón 1, SL 69 646,4, `protegida` |
| 3 | proceso nuevo con `first_r` y `step_r` ×3 (el recálculo da menos) | seq 3 `recuperacion`: «el recálculo daba escalón 0 (SL 67 979,2) y lo guardado escalón 1 (SL 69 646,4): se adopta el guardado» | **SL 69 646,4** (no 67 979,2), `protection_state = recuperada` |

En el arranque 3 quedaron dos avisos `proteccion`/`warn` en `op_alerts` («Protección recuperada
del diario: conservador/moderado BTCUSDT») y 8 eventos `alert` de `paper.broker` en el observatorio
(`proteccion_alta`, `proteccion_escalon`, `proteccion_recuperacion`), los de cada operación con la
misma traza (`tr_d23c63c946a44afb` para Moderado `plan_tp2`). La CLI contra esa API
(`python -m eim.paper proteccion lista|historial`) listó las mismas filas y `reconciliar` sobre una
operación consistente respondió 409 («solo se reconcilia una operación en estado inconsistente»).

Los casos que no se pueden fabricar con un proceso real sin corromper la base a mano (instantánea
corrupta o ausente, cierre recalculado anterior a lo guardado, operación que desaparece) están en
`tests/paper/test_protection*.py`.
