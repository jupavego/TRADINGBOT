# Condicionantes de las tareas en curso: qué se hace desde qué equipo

Lo que **solo puede hacerse en un equipo concreto** porque allí viven sus datos, su corrida o su
tarea programada (`ESTADO_PROYECTO.md` §0: «Lo que vive solo en `juanpablo-cpu`»). La hoja de ruta
(`roadmap.html`, sección «Vigía», que es el Vigía de tareas EIM desde el 2026-11-19) lo lee de aquí por
`python PLAN/build_roadmap.py` → `status.js` (campo `where` de cada tarea).

Es información compartida: al fusionarse en `main`, el icono de la bandeja de cada equipo la trae
en ≤ 5 min (`v2/scripts/sincronizar_main.ps1`) y la publica en la hoja de ruta, así que los dos
colaboradores ven lo mismo. Para añadir o quitar un condicionante, se edita aquí, se corre
`python PLAN/build_roadmap.py` y se fusiona.

Una fila por condicionante. Al cumplirse, se borra la fila (queda en la BITÁCORA). Columnas:
tarea · equipo · qué hay que hacer allí · fecha (desde cuándo se puede, o «ya»).

| Tarea | Equipo | Condicionante | Fecha |
|---|---|---|---|
| T172 | juanpablo-cpu | Traer `main`, correr el gate por la cola e instalar la tarea `v2\scripts\cantera_informe_mensual.ps1 -Instalar`: la cantera_v1 y su libro (`paper_cantera.duckdb`) solo existen allí | ya |
| T172 | juanpablo-cpu | Comprobar el primer informe real (`v2/reports/nursery/`) y que los hechos se ven en la Biblioteca (tras reiniciar la API) | 2026-12-18 |
| T31 | juanpablo-cpu | Cerrar la corrida oficial de ≥ 4 semanas con su informe final: la corrida que cuenta es la de ese equipo | 2026-11-27 |
| T135 | juanpablo-cpu | Leer el veredicto del A/B de M8: la tarea semanal y la copia `backups/t135_ab` están instaladas allí | 2026-12-06 |
| T143 | juanpablo-cpu | Decidir si la variante t143 pasa a oficial: la variante y su `data/paper/tf_gate_t143.json` solo corren allí | 2026-11-27 |
| T116 | juanpablo-cpu | Decidir si el gate aguanta Ollama generando y hacer 3 corridas con el equipo descargado (◆ permiso para parar servicios) | ya |
| T178 | juanpablo-cpu | Desplegar la retención y medir una semana con las copias diarias de `leaders.duckdb` del servicio de líderes de ese equipo | ya |

## Seguimiento de las tareas en curso

Lo que muestra la sección «Vigía» de cada tarea en curso: avance, fechas, requisitos, equipo y qué
necesita. Con inicio y fin (UTC), el avance se calcula en vivo por fechas en la página; si no, se
muestra el texto de «Avance». Requisitos, separados por comas (p. ej. «PC encendido, API en
marcha, tu decisión ◆»). Equipo: dónde se hace lo que falta («cualquiera» si da igual). Al cerrar
una tarea (☑), se borra su fila.

| Tarea | Inicio | Fin | Hito del fin | Avance | Requisitos | Equipo | Necesita |
|---|---|---|---|---|---|---|---|
| T31 | 2026-10-30T23:35Z | 2026-11-27T23:35Z | cierre de la corrida (4 semanas) | — | PC encendido, API en marcha | juanpablo-cpu | El bróker simulado vive dentro de la API: si se cierra, la corrida se detiene. Al cerrar, el informe final; riesgo con costo y freno gradual se encienden solos el 28-nov (T194) |
| T143 | 2026-11-10T04:17Z | 2026-11-27T23:35Z | fin de la corrida aparte t143 | — | PC encendido, API en marcha, tu decisión ◆ | juanpablo-cpu | La corrida t143 vive dentro de la API, como T31. Los entregables 2–5 esperan tu decisión; al cerrar, si la variante pasa a oficial |
| T135 | 2026-11-08T00:00Z | 2026-12-06T00:00Z | veredicto del A/B de M8 (como pronto) | — | PC encendido | juanpablo-cpu | Corre sobre una copia, sin tocar el vivo ni T31; necesita unas 315 operaciones emparejadas. El veredicto no se revisa |
| T172 | 2026-11-17T03:25Z | 2026-12-17T03:25Z | 1.ª revisión de la cantera (el informe sale el 18) | Herramienta hecha; falta el primer informe con datos reales | PC encendido, API en marcha | juanpablo-cpu | Traer main, correr el gate por la cola e instalar la tarea del informe mensual (`cantera_informe_mensual.ps1 -Instalar`) |
| T178 | — | — | — | Entregables 1, 2 y 4 hechos; falta desplegar y medir una semana | PC encendido | juanpablo-cpu | Reiniciar el servicio de líderes para que corra la retención y medir una semana con las copias diarias |
| T116 | — | — | — | Portátil: 6 corridas verdes · juanpablo-cpu: faltan 3 con los servicios parados | PC encendido, tu decisión ◆ | juanpablo-cpu | Tu permiso para parar los servicios (corta el bróker simulado) o esperar al cierre de T31 y T143 el 28-nov; y decidir si el gate debe aguantar Ollama generando |
| T187 | 2026-11-19T00:00Z | 2026-12-17T00:00Z | 1.ª mirada (luego 14-ene y 11-feb) | — | PC encendido, API en marcha | cualquiera | Mide sola en la API (vigía cada hora); lo de costo y riesgo que pase se adopta solo |
| T188 | 2026-11-19T00:00Z | 2026-12-17T00:00Z | 1.ª mirada (luego 14-ene y 11-feb) | — | PC encendido, API en marcha, tu decisión ◆ | cualquiera | Corredor en sombra; aunque pase no se adopta solo: tu decisión |
| T189 | 2026-11-19T00:00Z | 2026-12-17T00:00Z | 1.ª mirada (luego 14-ene y 11-feb) | — | PC encendido, API en marcha | cualquiera | Entrada límite medida en vivo por marco; si pasa se adopta sola en ese marco |
| T194 | 2026-11-18T00:00Z | 2026-11-28T00:00Z | encendido automático de la fase 2 | — | PC encendido, API en marcha | cualquiera | Nada: se enciende sola si la API ya corre el código nuevo |
| T196 | 2026-11-19T00:00Z | 2026-11-28T00:00Z | encendido del libro central | Gate y despliegue hechos | PC encendido, API en marcha | cualquiera | Nada: se enciende solo en su fecha |
| T45 | — | — | — | Código 100 % · prueba real 0 % (aparcada) | claves de testnet | cualquiera | Se retoma si creas claves de Binance testnet sin permiso de retiro |
