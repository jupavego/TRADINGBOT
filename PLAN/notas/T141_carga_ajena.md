# T141 — Qué ahoga a la API, y qué se puede decidir (2026-11-06)

Hecho desde `juanpablo-cpu`, solo leyendo: 4,6 días de `data/usage` (2-nov 03:38 a 6-nov 19:10 UTC, 12 534 muestras, con un hueco de 6,3 h el 3-nov), `data/operation/logs`, `data/jobs/log`, los JSON de QC de la captura y los registros locales de las sesiones de Claude. El informe se hizo sin cambiar ninguna prioridad ni reiniciar ningún servicio; los cambios se probaron antes en un proceso de prueba propio. Después el usuario decidió (abajo).

**Cerrada el 2026-11-10 (§8):** en los 3 días medidos tras ◆A y ◆B no hubo ningún reinicio de la API, y ◆B quedó demostrada. Los 12 ciclos lentos tienen culpable: 7, el `ng serve` de `RECUAPP`; 5, un trabajo de la cola pausado que retenía 6–8 GB (pasa a T149).

Salvo que se diga otra cosa, las horas son UTC y la CPU es % del equipo entero: con 4 núcleos, un núcleo lleno es el 25 %.

## Decisión del usuario (2026-11-06 ≈ 20:00 UTC): ◆A y ◆B

**◆A, regla para el trabajo pesado:** escrita en `~/.claude/CLAUDE.md`, de este equipo y fuera del repositorio. Va ahí, y no solo en `OPERACION`, porque `RECUAPP` y el propio EIM también aparecen en los episodios de carga. Rige para las sesiones que arranquen desde ahora: las ya abiertas no la leen. La orden se probó desde otra carpeta con un trabajo de prueba.

**◆B, memoria y E/S de los recolectores:** aplicada **a las 20:01:48 UTC, en marcha y sin reiniciar** (`python -m eim.operation.priority_memory apply`).

| Proceso | Antes | Después |
|---|---|---|
| `hft_collector` (PID 11376, 14 hilos) | memoria 2, E/S baja | **memoria 5, E/S normal**, en todos sus hilos |
| `liq_collector` (PID 17348, 12 hilos) | memoria 2, E/S baja | **memoria 5, E/S normal**, en todos sus hilos |
| API (PID 13376) y el resto de los servicios | memoria 2, E/S baja | sin cambios |

**Se queda fijo:** `priority.apply_role`, ya en `main`, sube a los recolectores cuando arrancan. La captura sigue en el arranque del 5-nov, con el cambio hecho en marcha, y lo conservará si se reinicia.

**Auditoría de la captura:**

| | Antes (19:58 UTC) | Después |
|---|---|---|
| Racha T78 (`hft_ops --streak`) | 4 h, desde 2026-11-06T15; mejor racha, 23 h | 11 h, de 2026-11-06T15 a 2026-11-07T01, leída a las 02:44 UTC |
| Última hora | T18 completa | T20 a T01, todas completas |
| Latido y cola | cola 1, sin descartes, mismo arranque | a los 8 s: cola 1, sin descartes, mismo arranque. En las 6 h 43 min siguientes: cola máxima 100, ninguna muestra por encima de 1 000, sin descartes. |
| Horas incompletas del día (`usage summary`) | 00, 06, 07 y 14 | las mismas 4; ninguna desde el cambio |

**Desde el cambio hasta las 02:44 UTC del 7-nov:** ningún ciclo de 120 s o más ni reinicio por latido, y el aviso no habría saltado. La API tuvo un reinicio por salida a las 20:04 y el despliegue de T140 a las 02:36, ninguno por carga.

**Primera prueba de ◆A:** `24_facetas_radio.py`, el script que el 6-nov corrió con `--procesos 7` justo cuando la API cayó a 10 MB, fue por la cola con `--procesos 2` (01:54–02:14). La cola lo pausó dos veces por tener menos de 1 GB libre.

**Primera prueba de ◆B, y no es limpia:** en ese tramo, con hasta 480 MB libres y 31 GB comprometidos, la captura conservó 136 MB, con cola máxima 4. En un tramo parecido del 6-nov (473 MB libres) bajó a 72 MB. Pero esta vez la API, que sigue en memoria 2, tampoco cayó (790 MB frente a 10 MB), así que la presión fue menor. **La mejora de ◆B sigue sin demostrarse:** hará falta un episodio en el que la API caiga y la captura no, y se lee con `python -m eim.operation.usage incidents --days 7`.

## Resumen

1. **Quién.** Cuatro de los cinco bloqueos coinciden con scripts de `OPERACION/PROTOTIPO` lanzados desde sesiones de Claude, con 4 a 7 procesos en un equipo de 4 núcleos, en prioridad normal y fuera de la cola. El quinto, el reinicio de las 04:14, fue memoria acumulada de Claude, Chrome y WebView, sin un culpable único. **Ningún bloqueo tuvo un trabajo de la cola en marcha.**
2. **Hallazgo que T126 no vio: todo el EIM, captura incluida, corre con prioridad de memoria 2 y de E/S baja.** Los programas del usuario tienen 5 y normal. T126 ajustó la clase de CPU y dejó esto como estaba. Explica por qué la API pierde casi toda su RAM mientras Chrome y Claude conservan la suya.
3. **La CPU llena no ha dañado a la captura. La presión de memoria sí.** Con el equipo al 100 % de CPU y memoria de sobra, todas las horas salieron completas. Con presión de memoria, la captura bajó de 132 MB a 18–40 MB, su cola llegó a 5 662 mensajes y hubo 3 horas incompletas. La prioridad ABOVE_NORMAL de T126 hace su trabajo; lo que falta es protegerla en memoria.
4. **Los 7 min de arranque son falta de CPU.** El arranque hace el mismo trabajo, 23–37 núcleo-segundos, pero lo recibe a menos del 9 % de un núcleo, frente al 19–70 % de los arranques normales.
5. **El aviso temprano ya está hecho.** Repasado sobre estos días, habría avisado de los 3 reinicios entre 11 y 45 min antes de los 900 s.
6. **Mi recomendación:** empezar por una regla para el trabajo pesado (◆A), que no toca ninguna prioridad y evita 4 de los 5 bloqueos. Después, subir la prioridad de memoria de la captura (◆B). Subir la API solo después de eso: hacerlo antes dejaría a la captura como la primera en perder memoria.

## 1. Quién estaba detrás de cada bloqueo

**Cómo se sabe, y cuánto vale:** el registro aún no guardaba las órdenes, así que no es una lectura directa. Se cruzó la hora de cada bloqueo con las órdenes de los registros locales de las sesiones de Claude (solo hora, proyecto y orden). Coinciden la hora y el número de procesos, y en un caso hasta el segundo. Es un indicio fuerte, no una prueba: lo que se lance fuera de Claude no aparece. El muestreo nuevo lo dirá directamente desde que se reinicie (§6).

| Bloqueo (UTC) | Duración | Qué corría | Encaje |
|---|---|---|---|
| 11-05 **04:14** reinicio | 906 s | **Memoria acumulada, sin culpable único:** Claude 6,0 GB, Chrome 4,0 GB, WebView 3,6 GB. Scripts de `OPERACION/PROTOTIPO` (`14_estado_actual.py`, `15_desgaste.py`, `16_modelo_paciente.py`) y `generar_barrios.py` de `RECUAPP` se sumaron con el bloqueo ya en marcha | El latido se paró a las 03:59:00 y ningún `python.exe` figuraba entre los 8 programas anotados hasta las 04:02 |
| 11-05 **07:12** reinicio | 959 s | Render de Blender desde las 06:38, más `09_referencia_sana.py --procesos 4` (06:59) y `--procesos 6` (07:00), de `OPERACION/PROTOTIPO` | De 3 a 9–10 `python.exe` a las 07:01, con 3,0–3,7 GB; memoria comprometida hasta 47 GB |
| 11-05 07:29 ciclo | 571 s | `09_referencia_sana.py`: la sesión lo paró a las 07:28:43 y relanzó `--asimetria --procesos 6` a las 07:37 | Hasta 11 `python.exe` entre las 07:28 y las 07:42 |
| 11-06 **01:41** reinicio | 932 s | `23_modelo_forma_semilunar.py --max 14` (01:22:15) y `--procesos 7` (**01:25:47**), de `OPERACION/PROTOTIPO` | **El último latido es de las 01:25:47, el mismo segundo.** Son los «12 `python.exe`» de la nota de T140: 65–106 % de CPU |
| 11-06 03:05–03:23, 3 ciclos seguidos | 272, 293 y 309 s | Tanda en segundo plano lanzada a las 02:56:56 (`12b_mallas_visuales`, `14_estado_actual`, `15_desgaste`, `16_radiografias`, `17_modelo_paciente`, `23_modelo…`) | 12 `python.exe`, 78–87 % de CPU |

**Otros dos momentos que importan, aunque no son reinicios:**

- **11-06 ≈ 02:00, la pérdida del socket de T140:** `24_facetas_radio.py --procesos 7` (02:00:13) y `22_lesion_semilunar.py` (02:01:39). De ahí salen los 17–18 `python.exe` con hasta 7,5 GB y la API cayendo de 1 468 a 10 MB. Sigue sin probarse que esto provoque el `WinError 64`, pero la coincidencia queda ahora con nombre. La cola se pausó a las 02:00:47 por «RAM libre 674 MB».
- **11-04 18:24, trabajo del propio EIM:** `scripts/t136_riesgo.py` y otro análisis de T136, en prioridad IDLE, más un `pytest tests/paper` directo. Eran 6 `python.exe` con 9,4 GB de RAM y 12,9 GB comprometidos; la API cayó a 10 MB y la cola de la captura subió a 5 323. La hora 18 salió incompleta. **IDLE protege la CPU, no la memoria.**

**La cola no estuvo implicada:** 0 de los 5 bloqueos tuvieron un trabajo suyo en marcha (`data/jobs/log`).

## 2. Dos mecanismos distintos

| Bloqueo | CPU equipo | Memoria compr. | RAM libre mín. | RAM API | CPU API | Dominante |
|---|---|---|---|---|---|---|
| 11-05 04:14 | 75 % | 39 GB | 304 MB | 334 → 9 MB | **3,36 %** | memoria |
| 11-05 07:12 | 98 % | 47 GB | 303 MB | 68 → 4 MB | 0,23 % | las dos |
| 11-05 07:29 | 100 % | 46 GB | 432 MB | 109 → 15 MB | 0,25 % | las dos |
| 11-06 01:41 | 99 % | 31 GB | 1 136 MB | 1 248 → 455 MB | 0,24 % | CPU |
| 11-06 03:18 | 100 % | 25 GB | 3 516 MB | 354 MB | 0,13 % | CPU |

Con la API en marcha y sin bloqueos, su mediana es 2,43 %, y su memoria comprometida ronda los 2,4 GB.

- **Falta de CPU:** con el equipo lleno de procesos en prioridad 8, la API en 6 recibe unas 10–20 veces menos. El ciclo de 729 s consumió unos 3,4 núcleo-segundos: el trabajo de un ciclo normal, repartido en 12 min.
- **Falta de memoria:** a las 04:14 la API no iba corta de CPU. Gastó 122 núcleo-segundos en esos 906 s, lo normal es un ciclo de 1,3 s de mediana, y aun así no avanzó. Es lo que cabe esperar si cada acceso tiene que volver del disco, pero **no se midió**, porque el registro no guardaba los fallos de página. Desde T141 los guarda (`faults`).

**Por qué la API pierde la RAM primero, medido en vivo el 2026-11-06:**

| Proceso | Clase de CPU | Prioridad de memoria | Prioridad de E/S |
|---|---|---|---|
| Captura HFT y liquidaciones | 10 (T126) | **2** en sus 14 y 12 hilos | **baja** |
| API, líderes, vigilantes, consumo | 6 (T126) | **2**, también los 26 hilos de la API | **baja** |
| `explorer.exe`, `claude.exe`, `chrome.exe` | 8 | 5 | normal |
| Un proceso lanzado a mano | — | 5 | normal |

Windows quita primero las páginas de prioridad baja. **Origen probable:** las tres tareas programadas del EIM tienen prioridad 7 (`Get-ScheduledTask`), y sus hijos heredan esos niveles. `apply_role` cambia la clase y deja lo demás como estaba. No se comprobó lanzando una tarea de prueba.

## 3. Por qué un arranque tarda 7 min

Mientras arranca, la API cuenta como hija del vigilante, así que su CPU se puede medir. Incluye los primeros 30 s tras arrancar.

| Lanzado (UTC) | Duración | CPU recibida | Reparto (sobre duración + 30 s) | CPU equipo | Memoria compr. |
|---|---|---|---|---|---|
| 11-02 23:13 | 17 s | 31 núcleo-s | 66 % de un núcleo | 58 % | 18 GB |
| 11-06 13:51 | 19 s | 34 núcleo-s | 70 % | 65 % | 19 GB |
| 11-03 16:08 | 22 s | 25 núcleo-s | 48 % | 68 % | 15 GB |
| 11-05 04:14 | 47 s | 47 núcleo-s | 61 % | 67 % | 35 GB |
| 11-05 08:13 | 72 s | 19 núcleo-s | 19 % | 78 % | 8 GB |
| **11-06 01:41** | **428 s** | **37 núcleo-s** | **8,1 %** | **98 %** | 31 GB |
| **11-05 07:12** | **489 s** | **23 núcleo-s** | **4,4 %** | **100 %** | 47 GB |

(Falta el arranque del 11-03 15:57, de 71 s, sin datos de CPU.)

**Conclusión:** el trabajo es el mismo, de 20 a 50 núcleo-segundos, y lo que cambia es el reparto. Los dos arranques largos son los únicos con el equipo saturado durante todo el arranque. Con 35 GB comprometidos y CPU al 67 % bastaron 47 s, así que la memoria alta sola no explica los 7 min. No se separó cuánto añade la E/S baja, que debe de sumar. Importar los módulos de la API cuesta solo 2,4 s de CPU, de modo que el resto del arranque se va en otras cosas.

## 4. Qué le pasa a la captura

| Franja (UTC) | CPU | RAM libre mín. | RAM captura mín. (normal 132) | Cola máx. | Horas de QC |
|---|---|---|---|---|---|
| 11-04 18:20–18:30 | 61–77 % | 133 MB | **23 MB** | **5 323** | 18 **incompleta** (18 huecos) |
| 11-05 03:45–04:16 | 75 % | 304 MB | 39 MB | 3 050 | 03 y 04 completas |
| 11-05 06:45–07:22 | 98 % | 303 MB | **18 MB** | 3 029 | 06 y 07 **incompletas** (27 y 74 huecos) |
| 11-05 07:25–07:42 | 100 % | 432 MB | 44 MB | **5 662** | 07 **incompleta** |
| 11-06 01:20–01:50 | 99 % | 928 MB | 159 MB | 363 | 01 completa |
| 11-06 01:58–02:06 | 90 % | 473 MB | 72 MB | 9 | 02 completa |
| 11-06 03:10–03:26 | 100 % | 1 935 MB | 152 MB | 8 | 03 completa |

De las 12 muestras con la cola por encima de 1 000 en estos días, 9 tuvieron la RAM libre en 1,1 GB o menos. Una más llegó segundos después de terminar el proceso de 12,9 GB, y las otras dos no tuvieron presión.

**Lectura:** las 3 horas con CPU al 100 % y sin presión de memoria sostenida salieron completas; las 3 horas incompletas de esta tabla tuvieron presión de memoria. **Son pocas horas, y una correlación:** también hay horas perdidas por red con el equipo libre (nota de T140, §4), y las horas 03 y 04 del 5-nov aguantaron con cola de 3 050.

## 5. El aviso temprano

Lo vigila el registro de consumo, porque cuando hace falta avisar la API es la que no responde. Salta si se cumple alguna de estas condiciones en 3 muestras seguidas, y termina con 10 limpias:

| Condición | Por qué ese valor | Qué aporta |
|---|---|---|
| Memoria comprometida ≥ 36 GB | Por encima, los 2 tramos vistos acabaron en bloqueo; con 32 GB ya aparecían tramos sin él | Es lo que daña a la captura |
| RAM de la API ≤ 200 MB | Percentil 1 de estos días: 184 MB | Windows ya se la ha quitado |
| CPU ≥ 95 % y API ≤ 0,3 % | Con 0,1 % solo vería 1 de los 5 bloqueos; con 0,3 %, 4 de 5, a cambio de 1 tramo sin ciclo lento | El único que ve el caso de las 01:41 |
| Latido parado ≥ 300 s | Solo 5 pausas tan largas en estos días, todas bloqueos | Última red; no se pudo repasar, porque el latido no se guardaba |

**Repasado con el código real sobre estos 4,6 días:**

| Bloqueo | Aviso activo desde | Margen hasta los 900 s |
|---|---|---|
| Reinicio 11-05 04:14 | 04:03:16 (y otro antes, a las 03:38:51) | **644 s** |
| Reinicio 11-05 07:12 | 06:26:12 | **2 705 s** |
| Reinicio 11-06 01:41 | 01:24:40, antes de que el latido se parara | **967 s** |
| Ciclos de más de 120 s | 8 de 10 | Los dos sin aviso duraron 131 y 146 s |

Serían **11 avisos en 4,6 días (2,4 al día)**, uno por tramo. Cuatro de los 11 tramos no tuvieron bloqueo cerca y uno más vino justo tras un reinicio; en los 5 la API bajó de 140 MB y la captura de 88 MB. Uno de ellos es el de T136 del 11-04. No los cuento como falsas alarmas, pero tampoco anunciaron un reinicio: si molestan, se suben los umbrales.

**Canales:** notificación de Windows, con el programa que más carga, y registro de operación y observatorio, solo con las causas. Las órdenes se quedan en `data/usage`, que no viaja en las copias (`continuity/inventory.py`).

**Límites:**
- El registro corre en prioridad 6 y también se queda sin turno: el intervalo de 30 s llegó a 152 s. Los márgenes de arriba ya lo incluyen.
- Si los servicios arrancan por la tarea al encender (sesión 0), la notificación no se ve, aunque queda el registro. Hoy corren en la sesión 1.
- El panel de la interfaz no lo muestra: sus alertas viven en la base de la API.
- No se lanzó ninguna notificación real; ese canal es el mismo que usa el vigilante.

## 6. Qué falta, y hasta cuándo

**Lo que ya se puede leer:** los 3 reinicios y los ciclos lentos de esta ventana, en §1 a §5.

**Desplegado:** PR #216 fusionado y registro de consumo reiniciado a las 03:00:50 UTC del 7-nov, solo ese servicio; la captura y la API conservaron sus PID. Se comprobó con un proceso de prueba de 350 MB: salió con su orden y su carpeta, con la clave falsa de sus argumentos oculta y sin rastro en el registro de operación. Desde ahora, cada bloqueo sale con su orden y su carpeta:

```bash
python -m eim.operation.usage incidents --days 7
```

**Ventana:** **hasta el 2026-11-10 03:00 UTC**, lo que además cubre el final de la racha de T78. Esa racha se rompió en la hora 14 del 6-nov y va desde la 15, así que se cumple como pronto al cerrar la hora 2026-11-09T14 UTC. Si en esa ventana no hay bloqueos, se dirá que no los hubo. La medición también deja `faults`, para separar por fin memoria y CPU en un caso como el de las 04:14.

**Sin comprobar:** una notificación real en pantalla, y leer las órdenes desde la sesión 0, donde no se ha probado; hoy los servicios corren en la sesión 1. Si falla, el árbol queda medido y sin nombre, sin más daño.

## 7. Opciones para decidir (◆)

**Antes y después de cualquier cambio de prioridad**, por la aceptación de T141: `python -m eim.data.collectors.hft_ops --root data --streak` y `python -m eim.operation.usage summary --days 7`. Lo que se dice de la captura es lo que se espera, no lo medido, salvo donde se indica.

| | Opción | Qué resolvería de lo observado | Qué se espera en la captura | Coste o riesgo |
|---|---|---|---|---|
| **◆A** | **Regla para el trabajo pesado**: en los proyectos de este equipo, como máximo 2 procesos e ir por la cola | 4 de 5 bloqueos, y la pérdida del socket de las 02:00 | **Mejor.** Menos presión de memoria, y la cola se pausa si la captura sufre o si quedan menos de 1 GB libres | Los scripts tardan más. Depende de que se cumpla. Un trabajo pausado conserva su memoria |
| **◆B** | **Memoria y E/S de la captura y los recolectores** a 5 y normal | Ningún bloqueo de la API. Protege a T78 | **Mejor, es el objetivo:** conservaría sus ~150 MB bajo presión. No probado | Muy bajo: solo son ~150 MB. Reversible |
| **◆C** | **Memoria y E/S de la API** a 5 y normal, **solo después de ◆B** | El caso de las 04:14, y parte del de las 07:12. No el de las 01:41 | **Neutra con ◆B. Peor sin ◆B:** la captura se quedaría como la primera en perder memoria | La API conservaría 1,2–1,9 GB, y lo perderían antes los programas del usuario |
| **◆D** | **API a prioridad normal** (6 → 8) | Los de CPU: 01:41 y 03:05–03:23, y parte de 07:12. Haría más cortos los arranques de 7 min | **Sin cambio esperado:** la captura sigue por encima (10). La CPU llena no le ha dañado (§4, medido) | La API compite de igual a igual con los programas del usuario, justo lo que T126 evitó, con ráfagas del 20–37 %. Sus hilos de fondo de T128 pasarían de 4 a 6 |
| **◆E** | **Que la cola también se pause si la API sufre** | Nada de lo observado: la cola no estuvo en ningún bloqueo | Neutra | Gates más lentos en horas de carga |

**Cómo se aplicaría:**

- **◆A** (decidida) está en `~/.claude/CLAUDE.md`. La orden, válida desde cualquier carpeta:
  ```bash
  C:/Users/jo/Desktop/JP/TRADINGBOT/v2/.venv/Scripts/python.exe -m eim.operation.jobs --data-dir C:/Users/jo/Desktop/JP/TRADINGBOT/v2/data submit --name forma --cwd C:/Users/jo/Desktop/JP/OPERACION/PROTOTIPO --min-ram-mb 4000 -- python -I scripts/23_modelo_forma_semilunar.py --procesos 2
  ```
  No limita ni cierra ningún programa del usuario. Es una regla para lo que se lanza desde las sesiones.
- **◆B** (decidida) está aplicada y fijada (arriba). **◆C** se podría aplicar igual, en marcha y sin reiniciar, y exigiría añadir la API a `priority_memory.targets` y a `apply_role`; las pruebas fallan si la API sube sin decidirlo.
- **◆D** es añadir un nivel que dé NORMAL en `priority.WINDOWS_CLASS`, asignárselo a la API en `ROLES` y reiniciarla, y antes hay que confirmar qué hijos lanza la API, porque heredarían la clase normal.

**Mi recomendación:**

1. **◆A ya.** Es lo que más evita y no toca ninguna prioridad.
2. **◆B ya, si aceptas el riesgo mínimo**, o al terminar la racha de T78 si prefieres no tocar nada durante la medición. Es la única que protege a la captura frente a lo que le ha hecho daño.
3. **◆C después de ◆B y de auditar**, si los bloqueos por memoria siguen.
4. **◆D solo si tras ◆A siguen los bloqueos por CPU.** Con ◆A puede no hacer falta, y revierte una decisión de T126 con un motivo que sigue vigente.
5. **◆E no, por ahora.** Solo si `usage incidents` llega a mostrar un trabajo de la cola en un bloqueo: saldrían con prioridad 4.

**Un dato para el umbral de 900 s, sin cambiarlo:** los 3 reinicios saltaron entre 906 y 959 s, apenas pasado el límite. En el de las 01:41 el ciclo ya había terminado 129 s antes de que lo mataran, y el reinicio costó otros 7 min de arranque. Es un solo caso; queda en `BACKLOG.md`.

## 8. Cierre (2026-11-10 04:30 UTC): la ventana medida

Medido con `python -m eim.operation.usage incidents --days 7` y `usage summary --days 4`, del **2026-11-07 03:00 al 2026-11-10 03:00 UTC**. También se cruzaron `data/jobs/log/2026-11-09.jsonl` y las muestras crudas de `data/usage/2026-11-09.jsonl.gz`.

**Lo que cambió con ◆A y ◆B:**

| | 5–6 nov (antes) | Ventana medida |
|---|---|---|
| Reinicios por latido (≥ 900 s) | 3 | **0** |
| Arranques lentos | 2 | **0** |
| Reinicios por salida de la API | 3 (el último, 7-nov 02:47) | **0** |
| Ciclos lentos (≥ 120 s) | 9 | 12, todos con culpable nombrado |

**◆B, demostrada.** Hacía falta un episodio en el que la API cayera y la captura no (§ decisión). Hubo tres: el 7-nov a las 06 h la API bajó a 40 MB y la captura conservó 135 MB, con cola máxima 4; el 9-nov a las 07:31, 52 MB frente a 187 MB; y el 9-nov a las 12 h, 125 MB frente a 190 MB. **En ninguno de los 12 ciclos lentos se perdió una hora de captura.** Las horas incompletas de la ventana son la 7-nov 05 (saturada, antes del primer ciclo lento) y las del apagón (9-nov 17 y 23, 10-nov 00), que son de T148.

**Quién estaba detrás de los 12 ciclos lentos:**

1. **7 con el `ng serve` de `RECUAPP`**, que el usuario abre por su cuenta: 7-nov a las 06 y 08 h, 9-nov de 07:00 a 09:00. Eran 2 o 3 servidores de 0,9 a 1,4 GB cada uno, con la CPU entre el 70 y el 96 % y entre 130 y 400 MB libres. Limitarlos está fuera de alcance; son el caso de ◆C.
2. **5 con un trabajo de la cola, `t143-maker`**, el 9-nov de 11 a 16 h. Era el caso que ◆E esperaba ver (§7). `usage incidents` lo nombra mal, como `submit --name gate-t143-final`. El `submit` que coge `runner.lock` se queda haciendo de ejecutor y vacía la cola entera (`jobs.py`), así que todo lo que corre después cuelga de su árbol. El gate terminó a las 10:38:14 y en ese mismo segundo arrancó `t143-maker`: el árbol pasó de 0,9 a 5,3 GB en un minuto y llegó a 7,9 GB.
   - **La cola lo pausó 32 veces por «RAM libre < 1 GB», pero esa RAM la tenía él.** Al pausarlo no se libera memoria. A los 900 s (`MAX_PAUSE_S`) se reanuda por fuerza y vuelve a pausarse a los 5 s. Así estuvo 5 h 39 min, con la RAM libre entre 70 y 600 MB y la API cayendo a 125 MB.
   - Se canceló a mano a las 16:17:36. Relanzado a las 16:40:42 con el equipo libre, **terminó en 350 s**.
   - Es exactamente el riesgo anotado en ◆A («Un trabajo pausado conserva su memoria»). Pasa a **T149**.

**Punto ciego:** el registro no tomó muestras del 9-nov 17:55:45 al 23:22:14 (5 h 26 min) ni del 10-nov 00:33:49 al 00:38:34. **En esos tramos no se puede afirmar que no hubo bloqueos.** Lo arregla T148, hecha y sin desplegar, que además los declara como `apagon_registro`.

**Las ◆ que quedaban (§7):**

- **◆C (API en memoria 5): no, por ahora.** Sin ella no ha habido ningún reinicio. Lo que queda son ciclos lentos sin consecuencia en la captura, y subirla le quitaría la memoria al usuario. Se reabre si vuelven los reinicios por latido.
- **◆D (API a prioridad normal): no.** No hubo ningún bloqueo por CPU sin presión de memoria.
- **◆E (pausar la cola si la API sufre): no tal cual.** El trabajo ya estaba pausado y el daño lo hacía su memoria retenida. Pausarlo más no habría ayudado. El arreglo de verdad es T149.

**Sin comprobar:** una notificación real del aviso temprano en pantalla, y leer las órdenes desde la sesión 0 (BACKLOG T141 (3)).
