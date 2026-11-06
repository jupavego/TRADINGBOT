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

**Lo que no está probado:** que el bloqueo sea lo que provoca el `WinError 64`. Es lo coherente con la coincidencia de las 02:00: con el bucle parado, el cliente se cansa y abandona la conexión antes del `accept`. Falta reproducirlo (T140).

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
- **Racha:** 5 h desde las 08 UTC. Si no se corta, llega a 72 h el 2026-11-09 hacia las 08:00 UTC.

## 5. El reinicio (2026-11-06, con permiso del usuario)

Se esperó a que terminara el gate de T139 y a que acabara un ciclo, y se detuvo solo el proceso hijo de `uvicorn` (`Stop-Process -Id <pid> -Force`). No se trajo código nuevo: la carpeta principal sigue en `d1921eb`.

| UTC | Hecho |
|---|---|
| 13:51:18 | Proceso detenido |
| 13:51:26 → 13:51:31 | El vigilante lo detecta («el proceso terminó») y relanza |
| 13:51:50 | `servicio_iniciado`, con las 5 operaciones del servicio |
| 13:51:54 | Puerto en `Listen` |
| 13:52:38 | `/v2/paper` responde 200; antes daba 503 mientras calculaba la primera vista, que es lo previsto |
| 13:52:37 | Salen las 5 alertas críticas de §3, las mismas |

Los otros 14 procesos de servicio siguieron vivos y la captura escribió un parquet a las 13:51:58. La interfaz sale «SIN CONEXIÓN» unos segundos, hasta que responde `/v2/snapshot` (≈ 10 s con el equipo cargado), y después «EN VIVO» con el precio en movimiento. **Falta auditar la hora 13 de T78**, que aún no había cerrado.

**El fallo sigue sin arreglar:** puede repetirse hasta cerrar T140, y este reinicio solo lo cura por ahora.
