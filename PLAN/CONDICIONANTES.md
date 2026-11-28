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
| T172 | juanpablo-cpu | Comprobar el primer informe real (`v2/reports/nursery/`) y que los hechos se ven en la Biblioteca (tras reiniciar la API) | 2026-12-18 |
| T135 | juanpablo-cpu | Leer el veredicto del A/B de M8: la tarea semanal y la copia `backups/t135_ab` están instaladas allí | 2026-12-06 |
| T66 | juanpablo-cpu | Medir la muestra etiquetada (`python -m eim.video.visual eval`): RapidOCR y el entorno de motores (`C:\eim-localai`) solo están allí | cuando haya ≥ 40 etiquetas |
| T116 | juanpablo-cpu | 3 corridas del gate con los servicios parados: ya cerraron T31, T143 y la semana de T178; falta tu permiso para parar los servicios | ya |
| T171 | juanpablo-cpu | Traer `main` y reiniciar la API: la pestaña «Cantera» muestra allí el balance de ganadas y perdidas y el capital por agente, y la API empieza a publicar el **espejo en vivo** que ve la portátil (rama `cantera/espejo` de `Santivego/eim-shared-data`; esa cuenta de git necesita permiso de escritura en ese repo). Comprobar `mirror_publish.error` vacío en `GET /v2/nursery` | ya |
| T96 | laptop | En pausa por tu decisión en T95: no empezar antes de la revisión automática de ese día (tarea «EIM - revision para decidir T96», informe en `TRADINGBOT/_revision_t96.md`); arranca solo si dice «ARRANCAR T96» | 2026-12-29 |
| T97 | laptop | En pausa por tu decisión del 2026-11-26 (sin proveedor de acciones aprobado, ◆2 de T88): se decide con el informe de la revisión de T96 de ese día (`TRADINGBOT/_revision_t96.md`). Si dice «ARRANCAR T96», se te pregunta el proveedor y T97 arranca; si no, sigue en pausa con T96 (`PLAN/notas/T97_pausa.md`) | 2026-12-29 |

## Seguimiento de las tareas en curso

Lo que muestra la sección «Vigía» de cada tarea en curso: avance, fechas, requisitos, equipo y qué
necesita. Con inicio y fin (UTC), el avance se calcula en vivo por fechas en la página; si no, se
muestra el texto de «Avance». Requisitos, separados por comas (p. ej. «PC encendido, API en
marcha, tu decisión ◆»). Equipo: dónde se hace lo que falta («cualquiera» si da igual). Al cerrar
una tarea (☑), se borra su fila.

| Tarea | Inicio | Fin | Hito del fin | Avance | Requisitos | Equipo | Necesita |
|---|---|---|---|---|---|---|---|
| T135 | 2026-11-08T00:00Z | 2026-12-06T00:00Z | veredicto del A/B de M8 (como pronto) | — | PC encendido | juanpablo-cpu | Corre sobre una copia, sin tocar el vivo ni T31; necesita unas 315 operaciones emparejadas. El veredicto no se revisa |
| T172 | 2026-11-17T03:25Z | 2026-12-17T03:25Z | 1.ª revisión de la cantera (el informe sale el 18) | Tarea diaria instalada el 2026-11-20; falta el primer informe con datos reales | PC encendido, API en marcha | juanpablo-cpu | Nada hasta el 18-dic. La tarea escribirá el informe sola; para que pueda leer el libro con el servicio en marcha hace falta el PR #333 (el libro de la cantera no entraba en la copia diaria) |
| T116 | — | — | 3 corridas con los servicios parados | Portátil: 6 corridas verdes · juanpablo-cpu: faltan 3 con los servicios parados | PC encendido, tu decisión ◆ | juanpablo-cpu | Ya cerraron T31, T143 y la semana de T178. Falta tu permiso para parar los servicios ≈ 1 h (antes hay que quitar la tarea del vigilante, que relanza lo parado): esa hora queda sin medir en T187, T188 y T189 |
| T187 | 2026-11-19T00:00Z | 2026-12-17T00:00Z | 1.ª mirada (luego 14-ene y 11-feb) | — | PC encendido, API en marcha | cualquiera | Mide sola en la API (vigía cada hora); lo de costo y riesgo que pase se adopta solo |
| T188 | 2026-11-19T00:00Z | 2026-12-17T00:00Z | 1.ª mirada (luego 14-ene y 11-feb) | — | PC encendido, API en marcha, tu decisión ◆ | cualquiera | Corredor en sombra; aunque pase no se adopta solo: tu decisión |
| T189 | 2026-11-19T00:00Z | 2026-12-17T00:00Z | 1.ª mirada (luego 14-ene y 11-feb) | — | PC encendido, API en marcha | cualquiera | Entrada límite medida en vivo por marco; si pasa se adopta sola en ese marco |
| T194 | 2026-11-18T00:00Z | 2026-12-17T00:00Z | fase 3 en la 1.ª mirada de T187 | Fase 2 encendida sola el 2026-11-28 00:00 UTC (riesgo con costos y freno gradual) | PC encendido, API en marcha | cualquiera | Nada: en cada mirada de T187 el vigía adopta solo lo de costo y riesgo que pase (`EIM_ASYM_ADOPT=0` lo impide) |
| T66 | 2026-11-20T15:00Z | — | — | Código y pruebas 100 % · muestra etiquetada 0 de 40 fotogramas | tu decisión ◆, material de video permitido | juanpablo-cpu | Etiquetar a mano ≥ 40 fotogramas de videos propios o aportados (formato en `v2/tests/fixtures/video/labels/README.md`); luego `eval` allí y decides si la lectura visual es fiel |
| T45 | — | — | — | Código 100 % · prueba real 0 % (aparcada) | claves de testnet | cualquiera | Se retoma si creas claves de Binance testnet sin permiso de retiro |
| T222 | 2026-11-28T00:00Z | 2027-05-28T00:00Z | veredicto final (1.ª mirada el 2027-02-28) | ◆ «sí» (2026-11-28) · herramienta hecha y probada en sintético · 0 de 2 miradas | PC encendido, API en marcha | cualquiera | Nada hasta el 2027-02-28: ese día, `python scripts/t222_marco_15m.py --look 1` con la familia de Holm del día y los cambios de régimen anotados (§3.6) |
| T206 | 2026-11-20T15:00Z | — | — | Arreglo fusionado y gate de confirmación verde el 2026-11-26 (5 032 pasadas, 0 fallos) | PC encendido, API en marcha | juanpablo-cpu | Mirar en vivo si la memoria de la API deja de crecer y cerrar los dos criterios que quedan (candado por serie y `/v2/health` que marque una ruta colgada). Lo demás está en BACKLOG |
| T209 | 2026-11-23T02:50Z | — | — | Opción A (tu ◆) fusionada en el PR #349 y ya cargada en la API | API en marcha | juanpablo-cpu | Verificar en vivo que `literature` y `vwap` dejan de vetar planes por la ventana de datos y cerrar la tarea |
| T210 | 2026-11-23T00:00Z | — | — | Diagnóstico hecho; criterios 1–4 sin empezar | — | cualquiera | Empezar los criterios de `PLAN/T210.md` (diagnóstico en `PLAN/notas/T210_utilidad_perfiles.md`) |
| T211 | 2026-11-23T00:00Z | 2027-11-24T00:00Z | veredicto, no antes (1.er informe mensual el 2026-12-24) | Medido: el patrón enunciado no está; la ruptura del canal queda en vigilancia | PC encendido, tu decisión ◆ | juanpablo-cpu | Tu ◆: registrar la tarea diaria `v2/scripts/apertura_informe_mensual.ps1` para que salgan los informes mensuales |
| T221 | 2026-11-19T00:00Z | — | — | Pre-registro y medición escritos (11 pruebas); la medición no ha corrido | PC encendido | juanpablo-cpu | Correr la medición por la cola (`python -m eim.analytics.regime_weights_report --store data/t197_banco --workers 2`) y escribir el veredicto; mide, no adopta |
