# T123 — Colas acotadas entre etapas: inventario, políticas y medición

Tarea `PLAN/T123.md`. Equipo de referencia: `juanpablo-cpu` (`DESKTOP-93R810K`, 4 núcleos, 16 GB).
Idea de Firedancer (etapas aisladas, cola acotada en cada frontera, contrapresión declarada); no se
copia código ni se añade dependencia.

## 1. Inventario de fronteras (antes de tocar código, 2026-11-07)

Leído en el código de `main` (`868e53f`) y medido en los servicios vivos a las 16:40 UTC. «Cola hoy»
es lo que existe en el código, no lo que debería haber.

| Id | Proceso | Frontera | Cola hoy | Tamaño real | Qué pasa hoy al llenarse |
|---|---|---|---|---|---|
| `hft.red` | captura HFT | red → recepción (3 conexiones) | interna de `websockets` 16.0 | `max_queue` 16 tramas por conexión, por defecto y sin declarar | deja de leer del socket (TCP) y Binance acaba cortando; la recepción solo sella y ofrece, así que no se llena |
| `hft.recepcion` | captura HFT | recepción → proceso | `Inbox` (`asyncio.Queue`) | 50 000 mensajes. **Medido: máximo 15 353 en 2,5 días, 0 descartes** (latido de `micro_hft`) | descarta lo nuevo y deja una marca `overflow` con cuántos y entre qué instantes (QC `cola_llena`) |
| `hft.buffers` | captura HFT | proceso → búfer por (tipo, hora) | listas en `HftStore.bufs` | vuelca a las 50 000 filas o cada 30 s | acotado por tiempo y filas |
| `hft.escritor` | captura HFT | búfer → hilo escritor | `ThreadPoolExecutor(1)` + `_futs` | **sin tope**: la cola interna del ejecutor y el `deque` no tienen límite | con el disco lento cada volcado queda en memoria con sus filas y la memoria crece sin límite (medido: §3) |
| `micro.escritor` | captura HFT (`micro_feed`), liquidaciones, recolector T23 | proceso → disco | lista en `HourlyWriter.buf` | 5 000 filas o 30 s (`micro_feed`: solo 30 s, 1 fila/s) | escritura síncrona: el bucle espera al disco; **si la escritura falla, las filas ya salieron del búfer y se pierden sin contarse** |
| `liq.red`, `micro.red` | liquidaciones, recolector T23 | red → proceso | interna de `websockets` | 16 tramas por conexión | igual que `hft.red`, pero aquí el proceso es síncrono: mientras se escribe a disco no se lee |
| `api.ticks` | API | klines de Binance → difusor | interna de `websockets` | 16 tramas | **el difusor espera al análisis de cada cierre** (agentes + pronóstico, hasta 30 s o más): mientras tanto no lee ticks, la interfaz deja de ver el precio en vivo y la librería deja de leer el socket |
| `api.cierres` | API | cierre de vela → análisis | ninguna (llamada en serie) | — | ver la fila anterior: el análisis bloquea la recepción |
| `api.clientes` | API | difusor → cada cliente WebSocket | `asyncio.Queue` por cliente | 256 mensajes | descarta lo más viejo, **sin contarlo** |
| `agentes.hilos` | API y operación | instantánea → agentes | un hilo por agente (`ThreadPoolExecutor`) | tantos hilos como agentes por llamada | **(a)** el plazo se espera agente por agente: con k agentes colgados el ciclo espera k × 30 s, aunque el docstring dice «segundos desde el envío»; **(b)** el hilo que excede el plazo sigue vivo: un agente colgado deja un hilo nuevo por vela, **sin tope**, y como son hilos del ejecutor (no daemon) impiden cerrar el proceso |
| `pronostico.hilos` | API y operación | análisis → pronóstico | ninguna | — | **sin plazo**: en la API `asyncio.to_thread` sin límite; en el ciclo, llamada directa. Un pronóstico colgado para el ciclo entero: sin decisiones, sin reconciliación y sin reglas del kill-switch |
| `ciclo` | operación | vuelta → vuelta | ninguna | — | bucle en serie cada 60 s; si una vuelta tarda, la siguiente empieza al acabar y no se acumulan |
| `obs.emisor` | todos | proceso → spool del observatorio | `queue.Queue` | 10 000 eventos (`thresholds.QUEUE_MAX`) | descarta lo nuevo y cuenta (`stats()["dropped"]`), pero **la ocupación máxima no se mide y el contador no sale del proceso** |
| `obs.spool` | API | spool → indexador | archivos JSONL en disco | disco; alerta a `SPOOL_ALERT_MB` | el indexador lee por tandas; memoria acotada por tanda |
| colas internas acotadas | captura HFT | libro: `pending`, `ring`; reloj: `_devs` | `deque(maxlen)` | 600, 600, ventana fija | descartan lo más viejo por construcción |

Memoria de los procesos de la tubería en ese momento (memoria privada, `Get-Process`): API
2 568 MB, captura HFT 342 MB, liquidaciones 228 MB, ciclo de operación 174 MB.

Fuera de la tubería de análisis (no se tocan aquí): `execution/user_stream.py` (`SimUserStream.queue`,
`deque` sin tope, lo vacía `pump` en el mismo hilo) → una línea en `BACKLOG.md`.

## 2. Política elegida por frontera

| Id | Tope | Política | Por qué |
|---|---|---|---|
| `red.websocket` (filas `hft.red`, `liq.red`, `micro.red` y `api.ticks`) | 16 tramas por conexión, ahora declarado (`max_queue=16`) | frenar al productor | es la red: lo único que se puede hacer es dejar de leer; el corte que llega después ya queda como hueco `desconexion`. La librería no expone su ocupación: no se inventa un contador |
| `hft.recepcion` | 50 000 | descartar lo nuevo (sin cambio) | el libro es una secuencia: descartar lo nuevo deja **un** tramo contiguo marcado; descartar lo viejo partiría la secuencia dos veces. Ahora también va al observatorio |
| `hft.buffers` | 50 000 filas / 30 s | volcar (sin cambio) | acotado por construcción |
| `hft.escritor` | 200 000 filas sin escribir (≈ 4 min de disco parado, ≈ 70 MB; se cuenta en filas porque un volcado puede tener de 1 a 50 000) | frenar al productor | el consumidor espera y la recepción sigue: si el disco no se recupera se llena la `Inbox`, que descarta con marca. La pérdida queda en un solo sitio y marcada |
| `micro.escritor` | 5 000 filas / 30 s (sin cambio) | frenar al productor (escritura síncrona) | ahora las filas que se pierden por un fallo de escritura se cuentan |
| `api.cierres` | 1 por canal | descartar lo más viejo | si cierra otra vela mientras se analiza la anterior, vale más analizar la última; la vela se guarda igual en el almacén antes de pasar al buzón |
| `api.clientes` | 256 por cliente | descartar lo más viejo (sin cambio) | un cliente lento pierde lo viejo y nunca frena al difusor; ahora se cuenta |
| `agentes.hilos` | plazo común desde el envío; 1 hilo colgado por (agente, versión, símbolo, marco) | descartar lo nuevo | mientras un agente siga colgado de una vela anterior sale degradado sin lanzar otro hilo; los hilos son daemon |
| `pronostico.hilos` | plazo de 60 s; 1 hilo colgado por (símbolo, marco) | descartar lo nuevo | el pronóstico que no llega a tiempo se salta y se cuenta; el ciclo sigue con la decisión |
| `obs.emisor` | 10 000 (sin cambio) | descartar lo nuevo | observar nunca frena lo observado (T72); ahora se mide la ocupación máxima y se emite |

`hft.buffers` no tiene id propio en el código: es una lista que vuelca por tiempo y filas, sin
cola entre medias; lo que sí puede crecer es lo que se entrega al escritor, `hft.escritor`.

## 3. Qué cambió en el código

- **Registro de fronteras** `v2/eim/observability/queues.py`: cada frontera con su tope, unidad,
  política y motivo; contadores por proceso (`gauge(id)`: descartes, esperas del productor,
  ocupación máxima, última causa, exactos desde el arranque). Un hilo daemon los emite como
  `heartbeat` de la pieza `observability.queues` (nueva en el catálogo) con `detail.queue`: cada
  60 s si algo cambió y, sin cambios, cada 10 min. Va en una pieza propia para no maquillar el
  latido de la dueña (si salieran como `api.hub`, el difusor parecería al día sin analizar nada).
- **Captura HFT** (`hft_ws.py`, `hft_writer.py`): `max_queue` declarado en las 3 conexiones; la
  `Inbox` cuenta sus descartes y su ocupación en el registro; el escritor cuenta las filas sin
  escribir (`pending_rows`) y, al llegar a 200 000, el consumidor espera (`_hold`) y lo cuenta.
- **Escritor por hora** (`writer.py`): las filas que deja fuera un fallo de escritura se cuentan
  antes de propagar el error (antes se perdían sin contarse).
- **Difusor de la API** (`api/live.py`): guarda la vela cerrada y la deja en un buzón de 1 por
  canal; un analizador por canal lo vacía. El difusor ya no espera al análisis: los ticks siguen
  llegando a la pantalla mientras corren los agentes. Cola por pantalla con contador. El
  pronóstico tiene plazo de 60 s.
- **Agentes** (`agents/runner.py`): plazo común desde el envío; hilos daemon; un agente colgado
  deja como mucho un hilo por (agente, versión, símbolo, marco) y, mientras siga colgado, sale
  degradado («sigue colgado de una vela anterior») sin lanzar otro. `call_with_deadline` aplica
  lo mismo al pronóstico en la API y en el ciclo de operación (`OperationParams.forecast_timeout_s`).
- **Emisor del observatorio** (`emit.py`): mide su ocupación máxima y la última causa de descarte.
- **API** `GET /v2/obs/queues` (`api/obs_queues.py`): por frontera, tope, política y el último
  informe de cada proceso, con `source` y `coverage`. Sin informe en 24 h o con uno de hace más de
  25 min sale `no_data` con el motivo; la de la red sale «no medible» en vez de con ceros.
- **Interfaz** (mesa → «Mapa del sistema»): lista «Colas entre etapas (k con descartes · m sin
  informe)» y, en el detalle de cada pieza, «Colas de esta pieza» con descartes, esperas,
  ocupación máxima de su tope, última causa, fuente y cobertura (`web/src/obs_queues.ts`).
- **Pruebas**: `tests/observability/test_queues_bounded.py` recorre los 138 módulos de la tubería y
  falla con una cola sin tope, un ejecutor (`ThreadPoolExecutor`) o un WebSocket sin
  `max_queue`; con el código anterior a T123 marca 5 casos (el ejecutor de los agentes y las 4
  conexiones sin `max_queue`). También comprueba que las constantes del código coinciden con el
  inventario y que esta nota nombra cada frontera. Carga: `tests/data/test_backpressure_load.py`.
  Aislamiento: `tests/agents/test_runner.py`, `tests/api/test_hub_backpressure.py`,
  `tests/operation/test_cycle_forecast_deadline.py`. Observatorio: `tests/observability/test_queues.py`.

## 4. Medición en el equipo de referencia (2026-11-07, `juanpablo-cpu`)

**Prueba de la suite** (`test_backpressure_load.py`, memoria de Python con `tracemalloc`): 100 000
mensajes a 640 por vuelta frente a 64 del consumidor (10×). Con la cola de 2 000: la memoria del
último cuarto no pasa de la del segundo en más de 512 KB, 88 171 descartes contados igual en la
`Inbox`, en sus marcas `overflow` y en el registro, y `entregados + descartados = ofrecidos`. La
misma carga sin tope crece más de 4 MB y acumula más del 70 % de lo ofrecido.

**Proceso entero** (`v2/scripts/t123_carga.py --secs 20`, memoria privada confirmada del proceso,
leída cada segundo, prioridad baja):

| Escenario | Antes de T123 | Después |
|---|---|---|
| Recepción HFT, productor 10× (mensajes de 300 B) | 263 → **718 MB en 10 s** y subiendo ~45 MB/s; se corta a los 700 MB; 2,95 M mensajes en cola | **225 MB plana** los 20 s (últimos 5 s: 224,9 MB cada uno); cola máx. 50 000; 4,3 M descartes contados |
| Disco parado con la captura escribiendo | 230 → 303 MB en 20 s, **+3,5 MB/s sin fin** (450 000 filas sin escribir y subiendo) | **259 MB plana** (últimos 5 s idénticos); 200 000 filas sin escribir; el resto, descartado y contado en la recepción |

En ambos, las dos etapas siguieron vivas al terminar. A 3,5 MB/s, 10 min de disco parado eran
+2 GB en el código anterior.

**Servicios vivos antes de T123** (16:40 UTC): API 2 568 MB, captura HFT 342 MB, liquidaciones
228 MB, ciclo de operación 174 MB; cola de la captura con máximo 15 353 de 50 000 y 0 descartes en
2,5 días (su latido). **Después:** el código no está desplegado; ver §5.

## 5. Pendiente

- **Despliegue (◆ del usuario).** Cargar T123 exige reiniciar la captura HFT, la API y el ciclo.
  Reiniciar la captura rompe la hora en curso de la racha de T78, que como pronto se cumple al
  cerrar la hora 2026-11-09T14 UTC. Propuesta: desplegar después de esa hora (o en cuanto la racha
  se rompa por otra causa) y entonces medir la memoria y la ocupación «después» en vivo con
  `GET /v2/obs/queues` y `Get-Process`, y anotarlas aquí.
- Medido sin desplegar: la interfaz y el endpoint se comprobaron con una API temporal del
  worktree (puerto 8011, datos vacíos): `api.cierres`, `api.clientes`, `agentes.hilos`,
  `pronostico.hilos` y `obs.emisor` llegaron al observatorio con fuente y cobertura; las de la
  captura salen «sin datos» porque esa API no tiene captura.
