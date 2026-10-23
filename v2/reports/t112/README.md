# T112 — Capturas del panel de protección (2026-10-23)

Web de la rama `claude/t112-panel-proteccion` servida en el navegador integrado (1440×1000, tema
futurista: desde T122 es el único, ya no hay claro ni oscuro) contra la **API en vivo** (corrida
de T31, código de `main` anterior a T112), solo con lecturas GET a través de un proxy de Vite.

| Captura | Datos | Qué muestra |
|---|---|---|
| `1_perfiles_proteccion_datos_reales.jpg` | reales | Bloque «Protección por perfil»: modo, dinero real deshabilitado, leyenda de estados, sin violaciones, umbrales e incrementos (R → USDT), cierres por motivo, máximo flotante → realizado |
| `2_historial_motivo_cierre_datos_reales.jpg` | reales | Historial del Moderado: cada cierre con su estado (stop inicial / dinámico), escalón y nivel protegido **estimado** junto al PnL realizado |
| `3_perfiles_violacion_SINTETICA.jpg` | **sintéticos** | Aviso rojo de violación y recuento por estado de las abiertas |
| `4_operaciones_abiertas_estados_SINTETICA.jpg` | **sintéticos** | Tabla por operación: stop inicial, protección inactiva, protección activa e incidencia técnica; nivel, stop vigente, máximo y flotante neto, neto estimado si salta el stop |
| `5_posiciones_proteccion_SINTETICA.jpg` | **sintéticos** | Pestaña «Posiciones»: la celda «TP / SL · protección» con estado, nivel y estimación |
| `6_bitacora_violaciones_SINTETICA.jpg` | **sintéticos** | Bitácora con el aviso de violaciones y el filtro «Ver solo violaciones» |

**Por qué hay datos sintéticos:** al verificar, la mesa real no tenía ninguna posición abierta en
ningún perfil ni ninguna violación (0 en los cuatro). Para ver esos estados se inyectaron en la
respuesta, solo en la pestaña de prueba del navegador, cuatro posiciones y una violación
rotuladas «SINTÉTICA»; la API y el almacén no se tocaron.

**Coherencia con la API (datos reales, comparados por script en la propia página):** umbral e
incremento por perfil = `ladder.first_usd`/`step_usd` (Conservador 4,99/2,49 · Moderado 7,79/3,90
· Agresivo 6,17/3,09 · control 10/5 USDT fijos), fracciones de R = `first_r`/`step_r`
(0,1/0,05 · 0,1/0,05 · 0,075/0,0375), cierres por motivo = `ladder.exits` (2·8 · 82·383 · 83·359 ·
103·306), violaciones = `counts.violations` (0), máximo flotante → realizado y realizado −
protegido = `avg_*` del resumen; Historial = `/v2/paper/trades` (465 cierres del Moderado:
383 `SLD`, 82 `SL`).

La API en vivo aún no publica `stop_est_usd`, `last_step`, `violations_recent` ni el `reason` de
los eventos (llegan al desplegar esta rama): el panel lo dice en lugar de inventar la cifra.
