# T140–T142 — Diagnóstico: la API deja de escuchar y nadie se entera (2026-11-06)

Hecho desde `juanpablo-cpu`, solo leyendo: registros, consumo del equipo, velas y la copia de seguridad `v2/backups/eim_20261106-000006`. No se tocó la base viva. La API se reinició después, con permiso del usuario (§5).

**Corrige dos cosas escritas antes:** la API sí llegó a escuchar tras el reinicio de las 01:41 UTC; lo que se perdió, hacia las 02:00, fue el socket. Y aquel reinicio no ocurrió «durante la copia»: la copia externa empezó a las 01:48:30, después.

## Resumen

Son tres fallos encadenados por una misma condición, y dos de ellos no son nuevos:

| | Fallo | Efecto | Tarea |
|---|---|---|---|
| 1 | `asyncio` cierra el socket de escucha cuando un `accept` falla, y el vigilante no mira el puerto | API sorda indefinidamente con el proceso «sano» | T140 |
| 2 | Otros procesos ahogan el equipo y la API, en prioridad baja, se queda parada | 3 reinicios «latido detenido» en 46 h, y el terreno para el fallo 1 | T141 |
| 3 | Un escalón guardado antes de tener las velas de 1 m congela la operación | 5 posiciones fantasma desde el 4-nov en los libros de T31 | T142 |

## 1. Por qué la API se queda sorda

**Cronología del 2026-11-06 (UTC):**

| Hora | Hecho | Fuente |
|---|---|---|
| 01:24–01:41 | CPU 100 %. 12 `python.exe` ajenos a EIM usan 65–101 % y ~2,4 GB. La API, a 0,1 % de CPU, baja de 1 432 a 496 MB. Un ciclo tarda 729 s | `data/usage`, `op-2026-11-06.jsonl` |
| 01:41:19 | El vigilante reinicia: «latido detenido 932 s» | `op-…jsonl` |
| 01:41:50 → 01:48:58 | La API tarda 7 min en arrancar (lo normal son 15–60 s) | `op-…jsonl` |
| ≈ 01:49 | `Uvicorn running on http://127.0.0.1:8000`; la interfaz conecta y recibe 200 | `vigilante.{err,out}.log` |
| **02:00:17** | Última petición servida (última escritura de `vigilante.out.log`) | mtime del archivo |
| 02:00–02:03 | CPU 100 %, RAM libre de 3 349 a 480 MB, 17–18 `python.exe` ajenos suben hasta 6,9 GB; la API baja de 1 468 a 10 MB | `data/usage` |
| sin hora | `OSError: [WinError 64] El nombre de red especificado ya no está disponible` y `Accept failed on a socket`, `laddr=('127.0.0.1', 8000)` | `vigilante.err.log:117-124` |
| 13:34 | Proceso vivo, latido y ciclos al día, ningún socket en `Listen` | `Get-NetTCPConnection`, `heartbeat.json` |

**El mecanismo, en el código:**
- `asyncio/proactor_events.py:864-871` (Python 3.12 del `.venv`): ante un `OSError` en el bucle de `accept` registra `Accept failed on a socket` y hace **`sock.close()`**. El servidor no se reabre ni muere.
- `uvicorn/loops/asyncio.py:9-10`: en Windows y sin subprocesos usa `ProactorEventLoop`. Por eso `--loop asyncio`, la solución que se suele citar, **aquí no cambia nada**: hace falta otra fábrica de bucle.
- `eim/operation/watchdog.py:108-126`: el vigilante solo mira si el proceso terminó y la edad del latido. El latido lo escribe el supervisor, una tarea del mismo bucle, que sigue funcionando sin el socket.
- `continuity check` tampoco mira el puerto, y por eso dio «CON AVISOS» sin decir nada de esto.

Es un fallo conocido de CPython en Windows ([python/cpython#93821](https://github.com/python/cpython/issues/93821)): un cliente que se desconecta produce el `WinError 64` y el socket queda cerrado. No se comprobó si la corrección propuesta llegó a alguna versión de Python.

**Ha pasado más de una vez:** `vigilante.err.log` empieza el 2026-11-05 08:13 y, antes de reiniciar, contenía dos arranques y **dos** `Accept failed`, uno en cada uno. La instancia anterior también lo sufrió y el reinicio de las 01:41 la curó por casualidad. El registro no lleva hora, así que no se sabe cuánto tiempo estuvo sorda ni cuántas veces pasó antes: ese archivo se reescribe al arrancar los servicios.

**Reproducido después (§6):** con el bucle bloqueado, un cliente que corta con RST provoca el `WinError 64` y cierra el socket. Lo que sigue sin probarse es qué cliente lo hizo aquel día.

**Qué sigue funcionando sin el socket:** el bróker y el ciclo de operación, a las 13:34 UTC seguían al día. Se pierde la interfaz y todo lo que entra por HTTP. `python -m eim.paper proteccion` intenta entonces abrir la base directamente, con la API aún dueña del archivo.

## 2. Por qué la API se queda parada

Tres reinicios «latido detenido» en 46 h, ninguno en los registros de los días anteriores desde el 30-oct:

| Reinicio (UTC) | Latido | Estado del equipo en los minutos previos |
|---|---|---|
| 11-05 04:14 | 906 s | CPU 63–84 %, memoria comprometida 34–38 GB; API entre 76 y 825 MB |
| 11-05 07:12 | 959 s | CPU 100 %, 9–10 `python.exe` ajenos con 3,0–3,7 GB, memoria comprometida 43–47 GB; API por debajo de 40 MB |
| 11-06 01:41 | 932 s | CPU 100 %, 12 `python.exe` ajenos; API en ~500 MB |

La API corre con prioridad 6 (por debajo de lo normal, T126) y esos procesos con prioridad 8. La memoria de la API cae mientras su memoria comprometida no cambia: Windows le quita RAM y cada acceso la devuelve del disco. **No son trabajos de la cola**, que corren con prioridad 4 (así aparece `git.exe` durante la copia externa), y la cola no tenía nada entre las 00:30 y las 01:48.

**Lo que no se sabe:** qué procesos son. El muestreo de consumo guarda solo el nombre. Hay otras sesiones y proyectos en este equipo (`blender.exe`, `http.server` de `PROTOTIPO/salida_planificador` y `REDISENO_TANDIOY` lanzados desde Claude), pero eso es un indicio, no una identificación.

## 3. Las alertas críticas «el recálculo bajaría el stop guardado»

**No son de esta noche ni las causó el reinicio:** las 5 operaciones están congeladas desde el 4-nov y su aviso se repite en cada arranque.

| Operación | Lado | Escalón / stop guardado | Fijado (UTC) | Congelada |
|---|---|---|---|---|
| `agresivo…4h:1793750400000:consenso_fuerte` | corto | 7 / 77 043,5 | 11-04 00:30 | 00:32 |
| `moderado…4h:1793750400000:consenso_fuerte` | corto | 5 / 77 043,5 | 11-04 00:30 | 00:32 |
| `ppp_btcusdt…4h:1793736000000:agente_levels` | corto | 2 / 77 116,6 | 11-04 00:30 | 00:32 |
| `moderado…15m:1793806200000:base_tendencia` | largo | 2 / 80 911,7 | 11-04 22:45 | 22:46 |
| `moderado…15m:1793806200000:sugerencia_2` | largo | 4 / 80 882,7 | 11-04 22:45 | 22:46 |

**Las 5 repiten el patrón del falso positivo del 31-oct** (`PLAN/notas/T130_anexo_falso_inconsistente.md`): el escalón se guarda al cierre de la vela de 15 m, y en las velas de 1 m su stop ya se había tocado dentro de esa misma vela y vuelve a tocarse justo después.

**T130 no lo eliminó, lo trasladó.** `ladder_floor.early` acepta ahora el cierre con velas de 1 m, pero su propia documentación avisa de que si eso baja el stop guardado, `protection_sync._never_lower` la retiene igual. Y eso es lo que pasa aquí: la única fila que puede quedar por debajo es el cierre. **Lectura: el recálculo ya ve estas operaciones cerradas.**

**Efecto:** una operación congelada no se cierra sola, ni por su stop ni por liquidación (decisión de T110, `ladder_floor.py:14`). Llevan 2,5 días abiertas en los libros de Agresivo, Moderado y PPP, que son los que mide T31. **No se ha medido cuánto distorsionan.** En el caso del 31-oct, el perfil Agresivo rechazó 16 cortos por tope de riesgo mientras duró, sin saberse cuántos se debían a ella.

**`_never_lower` hace bien su trabajo y no hay que aflojarlo:** ninguna ruta automática debe bajar un stop. Lo que falla es guardar un escalón antes de tener los datos para fijarlo.

## 4. De paso: la captura T78

- **El gate de T135 no la dañó:** corrió entre las 05:10 y las 05:26 UTC y la hora 05 salió completa.
- **Las horas 06 y 07 salieron incompletas:** silencios desde las 06:11 y desconexiones desde las 07:54 («keepalive ping timeout»), todos los flujos a la vez. El equipo estaba libre (CPU 4–19 %, más de 7 GB de RAM libres) y la cola vacía, lo que apunta a la red y no a la carga, sin poder asegurarlo. A las 07:54 había un `git-remote-https` en marcha, que no prueba nada.
- **Comprobado con la recalificación de T138, en seco:** las horas 06 y 07 siguen incompletas (libro útil 98,4 % y 93,2 %, con huecos reales). Solo cambiaría la hora 00, por `mark`, y eso no afecta a la racha actual.
- **Racha:** 6 h desde las 08 UTC, medida a las 14:38 UTC. Si no se corta, llega a 72 h el 2026-11-09 hacia las 08:00 UTC.

## 5. El reinicio (2026-11-06, con permiso del usuario)

Se esperó a que terminara el gate de T139 y a que acabara un ciclo, y se detuvo solo el proceso hijo de `uvicorn` (`Stop-Process -Id <pid> -Force`). No se trajo código nuevo: la carpeta principal seguía en `d1921eb`. A las 14:37 UTC, ya con la API en marcha, la carpeta pasó a `b935cde`, que trae T135, sin que esta sesión lo pidiera. La API no lo cargó (`/v2/health`, `/v2/paper` y los ciclos siguieron bien, sin errores en su registro) y lo recogerá en su próximo reinicio, con el motor apagado.

| UTC | Hecho |
|---|---|
| 13:51:18 | Proceso detenido |
| 13:51:26 → 13:51:31 | El vigilante lo detecta («el proceso terminó») y relanza |
| 13:51:50 | `servicio_iniciado`, con las 5 operaciones del servicio |
| 13:51:54 | Puerto en `Listen` |
| 13:52:38 | `/v2/paper` responde 200; antes daba 503 mientras calculaba la primera vista, que es lo previsto |
| 13:52:37 | Salen las 5 alertas críticas de §3, las mismas |

Los otros 14 procesos de servicio siguieron vivos y la captura escribió un parquet a las 13:51:58. La interfaz sale «SIN CONEXIÓN» unos segundos, hasta que responde `/v2/snapshot` (≈ 10 s con el equipo cargado), y después «EN VIVO» con el precio en movimiento. **La hora 13 de T78 salió completa**, con 0 eventos sin detectar: el reinicio no afectó a la captura. A las 14:38 UTC la API seguía escuchando.

**El fallo sigue sin arreglar:** puede repetirse hasta cerrar T140, y este reinicio solo lo cura por ahora.

## 6. T140: la reproducción, el bucle y lo que se hizo

**El fallo se reproduce.** `python -m eim.operation.accept_check`, con uvicorn 0.51.0 y Python 3.12.10 en un puerto efímero. El bucle queda bloqueado, una conexión consume el `accept` pendiente y otra queda en la cola y se rinde:

| Bucle | Cómo se rinde el cliente | Puerto después | HTTP | `Accept failed` |
|---|---|---|---|---|
| Proactor | **RST** | **cerrado** | falla | sí |
| Proactor | cierre normal | abierto | 200 | no |
| Proactor | Python con tiempo de espera | abierto | 200 | no |
| Proactor | `Invoke-RestMethod`, como el icono | abierto | 200 | no |
| Selector | los cuatro | abierto | 200 | no |

Otra sesión lo reprodujo por su cuenta, sin ver este código, con 3 rondas por escenario: Proactor con bloqueo y RST falla 3 de 3, y sin bloqueo o con cierre normal 0 de 3; Selector, 0 de 3 en todos.

**Lo que sigue sin saberse:**
- **Qué cliente mandó el RST aquel día.** El icono queda descartado en este escenario; Chrome y Vite no se probaron.
- **Si el incidente real siguió esta secuencia exacta.** Es lo más probable: aparecen los mismos dos mensajes, y los ciclos estuvieron parados de 01:59:37 a 02:05:59, junto a la última petición servida (02:00:17). Pero el registro de entonces no llevaba hora.

**Se adopta `SelectorEventLoop`** con `uvicorn --loop eim.operation.event_loop:selector_loop`:
- **Por qué:** conserva el puerto, no toca partes privadas de `asyncio` y no deja ruido en el registro.
- **Lo que se cede:** `select` admite 512 sockets en Windows, y la API viva tenía 42 el 2026-11-06. Tampoco admite subprocesos ni tuberías de `asyncio`: `eim/` tiene 0 usos y una prueba lo fija.
- **Descartado:** un parche sobre `_proactor.accept` que absorbe el `WinError 64`. También conservó el puerto (2 de 2), pero depende de un atributo privado y deja un mensaje por cada conexión perdida. Queda como reserva si Selector da problemas.

**Ensayo con la API real** (2026-11-06, 14:50–14:58 UTC): vigilante, API y operación en papel desde este código, puerto 18140, datos vacíos y prioridad IDLE, sin tocar los servicios.
- **Bucle:** la línea de órdenes llevaba `--loop eim.operation.event_loop:selector_loop`.
- **Operación:** análisis de 1 h y 4 h a las 14:51:38 y 6 ciclos correctos.
- **HTTP:** `/v2/health`, `/v2/operation`, `/v2/agents`, `/v2/paper` y `/v2/risk` dieron 200.
- **WebSocket:** 12 mensajes en 4 s, con ticks en vivo desde Binance.
- **Resistencia:** 60 RST seguidos durante una vista pesada; siguió en escucha, `/v2/health` respondió 200 y no hubo `Accept failed`.
- **Parada:** `detener_servicio.ps1 -SoloCon "--port 18140"` paró solo esa instancia.
- **No ensayado:** el relanzamiento con `servicio_continuo.ps1`, porque aquí habría lanzado otros servicios; ni horas de funcionamiento continuo.

**La vigilancia del puerto se aparta de la ficha.** Pedía una conexión TCP; se usa la tabla de puertos del sistema (`port_watch.listening`), porque una sonda que conecta podría provocar el fallo si cortara con RST. Solo si la tabla no muestra a nadie se intenta conectar, porque esa consulta puede fallar sin avisar y entonces ya no hay socket que dañar. Reinicia tras 2 min sin escuchar, o tras 20 min si no llegó a abrirse.

**Efecto de la falta de puerto en T31: ninguno en los libros.** Ventana 02:00:17–13:51:18 UTC, recontado en `op-2026-11-06.jsonl`: 665 ciclos, 663 correctos (los otros 2, «sin datos del proveedor» a las 07:55 y 07:57), reconciliación correcta en los 665, 15 decisiones sin plan vigente y capital igual al principio y al final (9 720,05). Otra sesión midió además las entradas y salidas del bróker en esa ventana (Moderado 3/4, Agresivo 3/4, PPP 1/2, Conservador 0/0); esas no se recontaron aquí. Lo que sí toca a T31 va aparte: las 5 operaciones congeladas (T142) y los huecos de ciclo por saturación (T141).

**Otros cambios:**
- **Registros:** el stderr de todo servicio bajo vigilante y la salida de la API llevan hora UTC. Los `vigilante.*` se conservan entre arranques (los 10 últimos).
- **Por qué solo la API pasa su salida por tubería:** `Watchdog` también vigila la captura y los líderes, y una tubería ataría la captura de T78 al hilo que la lee.
- **Estado:** `continuity check` y el icono de la bandeja distinguen «sin puerto» de «parada», exigiendo un latido de menos de 3 min para no confundirla con una parada normal.

**Desplegarlo exige reiniciar el vigilante además de la API**, porque la vigilancia y la línea de órdenes viven en el vigilante: `RUNBOOK.md` §16. La captura no se toca, y mientras no se reinicien, la captura y los líderes siguen con el código viejo sin que eso afecte a nada.

**Portátil:** el `--loop` propio necesita un uvicorn que lo admita. El lock fija 0.51.0 desde el 2026-10-21; antes de desplegar allí, comprobar `pip show uvicorn`.

**Lo que le pasó a la captura mientras se hacía T140:** la hora 14 UTC salió incompleta y la racha de 6 h de T78 volvió a 0. No se pudo aislar la causa, y este trabajo pudo contribuir:

| UTC | Hueco | Qué había |
|---|---|---|
| 14:34:05–14:34:39 | `bbo`: 28,4 s y desconexión | CPU 13–18 %: ajeno a la carga |
| 14:39:21–14:40:36 | `depth`, `mark` y `bbo`, hasta 18 s, y dos desconexiones | `git worktree add` de T140 a las 14:39:17 (1 602 archivos). CPU al 97 % a las 14:38, antes de ese comando, con Chrome y Claude; 61 % a las 14:39 y 26 % a las 14:40 |
| 14:57:16–14:57:36 | `mark`: 20,2 s | El ensayo de arriba, a prioridad IDLE, con la CPU alrededor del 60 % |

`bbo` perdió ≈ 53 s frente a los 36 que admite el 0,99. Sin la tanda de las 14:39–14:40 habría perdido unos 39 s: tan cerca del límite que no se puede decir que la hora se hubiera perdido igualmente. **Consecuencia práctica:** con una racha en juego, crear un worktree también es trabajo pesado (BACKLOG T140 (7)). La cola además pausó `gate-t140` a las 15:14 por «2 huecos nuevos»; falta el QC de la hora 15.
