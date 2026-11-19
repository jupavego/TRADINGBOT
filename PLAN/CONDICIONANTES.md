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
