# T138 — Por qué la racha de T78 está en 0 sin que falten datos

Fecha: 2026-11-05, desde `juanpablo-cpu`. Solo se leyeron crudos de `mark` (3 600 filas por hora) y columnas escalares de `snap` y `clock`, por la prioridad `batch`. Ningún servicio reiniciado y el reloj sin tocar.

**Decisión del usuario (2026-11-05, «Sí, y recalcula»): se adopta la medida y se recalifica desde 2026-11-05T09.** Aplicado con `--requalify` a las 23:43 UTC, después de un gate verde; los JSON solo se tocaron en ese paso. Detalle en §7.

## 1. Veredicto

**Hipótesis confirmada.** Las horas 10 a 21 UTC del 2026-11-05 salen incompletas por cómo se cuenta `mark`, no porque falten datos. Las 13 horas 09–21 tienen 46 800 mensajes de 46 800 esperados y **0 eventos perdidos**. Contados por segundo de llegada dan 5 308 segundos vacíos y 5 308 dobles, que se compensan exactamente.

La causa de fondo es el reloj del equipo: desde el arranque de las 08:11 UTC va **~835 ms adelantado** respecto a NTP. Eso, sumado a una latencia real de ~170 ms, deja las llegadas de `mark` justo sobre el límite del segundo. Windows Time sincroniza a diario, pero no corrige un desfase menor de 1 s.

## 2. La hora 2026-11-05T14

| Medida | Valor |
|---|---|
| Mensajes | 3 600 de 3 600 |
| Eventos perdidos (saltos de `E`) | 0; el intervalo entre eventos va de 993 a 1 007 ms |
| Segundos de llegada vacíos / dobles / triples | 766 / 766 / 0 |
| Mensajes acumulados − segundos transcurridos | siempre −1 o 0: nunca se pierde ni se acumula uno |
| Intervalo máximo entre llegadas | 1,42 s |
| Cobertura por segundo de llegada (la vigente) | **0,7872** |
| Cobertura por cadencia (§5) | **1,0000** |

La emisión de Binance va en punto: la mediana de `E mod 1000` es 0 en todas las horas. Así que la fase de llegada es la latencia aparente módulo 1 s, y con ~1 000 ms cae sobre el límite.

Por eso hay un modelo sencillo que predice la cobertura. Si `p` es la fracción de mensajes que caen justo antes del límite, un segundo queda vacío cuando su mensaje se adelanta y el siguiente no, así que la cobertura esperada es `1 − p(1 − p)`, con un mínimo de 0,75. Con la `p` medida en los crudos, el modelo reproduce la cobertura real con un error medio de 0,010:

| Hora | Msgs | Fase mediana (ms) | p | Vacíos / dobles | Cobertura vigente | Modelo | Eventos perdidos | Por cadencia |
|---|---|---|---|---|---|---|---|---|
| 09 | 3 600 | −17,4 | 0,990 | 34 / 34 | 0,9906 | 0,9904 | 0 | 1,0000 |
| 10 | 3 600 | −13,6 | 0,973 | 89 / 89 | 0,9753 | 0,9738 | 0 | 1,0000 |
| 11 | 3 600 | −11,5 | 0,961 | 132 / 132 | 0,9633 | 0,9629 | 0 | 1,0000 |
| 12 | 3 600 | −7,9 | 0,901 | 302 / 302 | 0,9161 | 0,9111 | 0 | 1,0000 |
| 13 | 3 600 | −3,6 | 0,712 | 635 / 635 | 0,8236 | 0,7949 | 0 | 1,0000 |
| 14 | 3 600 | −0,5 | 0,530 | 766 / 766 | 0,7872 | 0,7509 | 0 | 1,0000 |
| 15 | 3 599 | +3,0 | 0,355 | 770 / 769 | 0,7861 | 0,7709 | 0 | 0,9997 |
| 16 | 3 601 | +6,4 | 0,200 | 504 / 505 | 0,8600 | 0,8400 | 0 | 1,0000 |
| 17 | 3 599 | +6,3 | 0,203 | 558 / 557 | 0,8450 | 0,8382 | 0 | 0,9997 |
| 18 | 3 601 | +7,5 | 0,147 | 430 / 431 | 0,8806 | 0,8743 | 0 | 1,0000 |
| 19 | 3 600 | +8,0 | 0,118 | 359 / 359 | 0,9003 | 0,8956 | 0 | 0,9995 |
| 20 | 3 600 | +9,9 | 0,078 | 250 / 250 | 0,9306 | 0,9278 | 0 | 1,0000 |
| 21 | 3 600 | +7,2 | 0,164 | 479 / 479 | 0,8669 | 0,8626 | 0 | 1,0000 |

Los 3 599 y 3 601 son el mismo efecto en el borde de la hora: un mensaje pasa de una partición a la siguiente, y cada pareja (15+16, 17+18) suma 7 200.

El límite del segundo no se cruza y ya está: entre las horas 20 y 21 la fase mediana retrocede de +9,9 a +7,2 ms y la cobertura empeora de 0,93 a 0,87. Esperar a que escampe no es un plan.

## 3. Por qué saltó la latencia: el reloj, no la red

**Prueba directa, sin depender de NTP.** Los snapshots REST de `snap` guardan cuándo salió la petición (`req_ns`) y el sello `E` de Binance. Binance no puede sellar antes de recibir la petición, así que `req − E` es una cota inferior del adelanto del reloj local:

| Tramo | Adelanto del reloj local, cota por snapshots |
|---|---|
| Hasta 2026-11-05T07 (antes del arranque) | entre −140 y +219 ms: compatible con ir en hora |
| 2026-11-05T09–T21 (después) | **al menos 624–652 ms, como mucho 936–966 ms** |

**Medida con NTP** (`w32tm /stripchart /computer:time.windows.com`, solo lectura): −835 ms a las 22:32 UTC y otra vez −835 ms a las 22:42 UTC. Encaja: `mark` tiene una latencia aparente de 1 006 ms y 1 006 − 835 = ~171 ms, una latencia real razonable. El 29-oct, justo tras un ajuste de reloj, marcaba 187 ms.

**Windows Time:** `w32tm /query /status` no devolvía datos porque **el servicio está parado** (error 0x80070426), no por un problema de permisos. Es `W32Time`, inicio manual. Lo arranca a diario la tarea `SynchronizeTime` (`sc start w32time task_started`) y el registro del sistema muestra que sí llega a `time.windows.com` (evento 35 a las 18:29:46 UTC de hoy). Pero la corrección aplicada es **de menos de 1 ms**:

| Sincronización | Hora cambiada (Kernel-General 1) | Mediana de `mark` antes → después |
|---|---|---|
| 2026-11-05 18:29 | +0,45 ms | 1 006 → 1 007 |
| 2026-11-04 19:59 | +0,85 ms | 258 → 260 |
| 2026-11-03 18:35 | +0,89 ms | 265 → 264 |
| 2026-10-29 21:03 | **−1,607 s** | **1 793 → 187 (−1 606 ms)** |

La última fila es la clave: cuando el desfase supera 1 s, Windows da el salto y la latencia cae exactamente lo mismo. Coincide con `MaxAllowedPhaseOffset = 1` en la configuración de W32Time, donde un desfase menor se corrige despacio (*slew*), y el servicio se detiene antes de terminar. **Un desfase de menos de 1 s, como el de ahora, se queda indefinidamente** salvo otro arranque.

**El arranque como origen:** el sello de inicio del evento 12 acaba en `.5000000` en los 12 arranques desde el 23-oct, lo que encaja con un reloj que se fija desde un reloj de hardware de resolución de 1 s y pierde la fracción. Los saltos medidos en las horas de arranque son +115 ms (2026-11-01), ~0 ms (2026-11-03) y +726 ms (2026-11-05). **No se pudo observar el reloj de hardware directamente**: esta parte es la explicación más coherente, no una medición, y el salto casi nulo del 3-nov queda sin explicar.

La captura no lo vio porque `hft_clock` se ancla al reloj de pared **después** del arranque, y `clock.jumps` está en 0 todo el tramo. `depth` y `bbo` saltaron igual (~+725 ms) y la mediana de `recv − E` de los snapshots también (de ~224 a ~950 ms).

## 4. Qué consecuencia tiene

- **`latency_ms` del QC es aparente:** hoy lleva +835 ms que no son de red. El banco de T77 (`hft/latency.py`) corrige el desfase con `/fapi/v1/time`; el QC no. T79 no debe tomar la latencia del JSON de QC.
- **La fase se vuelve a sortear en cada arranque.** Con la medida vigente, una corrida de 72 h puede caer en la banda mala sin que falte nada, y no se puede evitar eligiendo el momento.
- Los datos crudos son buenos: `recv_ns` conserva los intervalos exactos (`mono_ns` no salta) y el desfase es constante y medible.

## 5. La medida candidata

`qc.cadence_coverage`, usada solo en `mark` (`QC_VERSION` 2): en lugar de contar segundos de reloj, mide el tiempo sin datos. Cada intervalo entre llegadas mayor de **1,5 s**, también contra los bordes de la hora, resta lo que exceda de 1 s. Tiene además un tope por número de mensajes, para que un flujo más lento que su periodo tampoco pase. `coverage` se sigue guardando igual: nada se oculta, solo deja de decidir en `mark`.

| Comprobación | Resultado |
|---|---|
| Réplica con el código real sobre las **149 horas auditadas** (2026-10-28 → 2026-11-05T21), sin escribir | **Cambian 12: las horas 10–21 del 2026-11-05, todas de no a sí** |
| Horas completas que pasarían a incompletas | 0 |
| Antes del arranque (135 horas): cadencia − vigente | media −0,00013: **la nueva es apenas más estricta** |
| Horas 06 y 07 del 2026-11-05 (silencios reales) | 0,9806 → 0,9800 y 0,9436 → 0,9416: siguen rotas |
| Hora 2026-11-02T02 (25 mensajes perdidos de verdad) | 0,9931 → 0,9931 |
| Fases 0, 1, 100, 250, 500 y 999 ms (prueba sin red) | Hora limpia: 1,0. Con 40 s sin datos: 0,9889 en todas |
| Hueco de 30 s / 40 s con las llegadas sobre el límite | Completa / incompleta |

El umbral de 1,5 s se eligió frente a 2,0 s porque un mensaje perdido deja un intervalo de ~2 s que el vaivén puede bajar de 2,0; con 1,5 s se ve siempre. Es la opción más estricta de las dos.

**Lo que esta medida no cambia:** el mínimo de 0,99, la regla de 72 horas seguidas, el libro útil, `bbo` ni los huecos sin detectar. Por ejemplo, la hora 14 tuvo un silencio real de 17,6 s en `depth` y sigue contando en `book_usable` (0,9947).

## 6. La hora del gate de T136 (2026-11-05T22)

**El gate de T136 no dañó la captura.** Corrió de 21:57:10 a 22:21:20 UTC (1 451 s, una pausa de la cola de 115 s), así que tocó también el final de la hora 21. Las dos horas salieron con libro útil 1,0, sin ningún tramo marcado y 12 de 12 verificaciones REST. `complete` sale falso en ambas, pero solo por `mark` (§2).

| Hora | Gate | Libro útil | `depth`: cobertura, mensajes | `depth` p50 / p99 / máx (ms) | Tramos marcados |
|---|---|---|---|---|---|
| 2026-11-03T18 | T131, por la cola, 2 pausas | **0,9164** | 0,9172, 32 366 | 208 / 216 / 1 295 | 31 desconexiones, 5 silencios… |
| 2026-11-04T17 | fase 22, por la cola, 945 s, sin pausas | 1,0000 | 1,0000, 35 293 | 201 / 219 / 681 | ninguno |
| 2026-11-05T20 | **ninguno (referencia)** | 1,0000 | 1,0000, 35 289 | 950 / 995 / 1 815 | ninguno |
| 2026-11-05T21 | T136, últimos 3 min | 1,0000 | 1,0000, 35 291 | 948 / 984 / 1 357 | ninguno |
| 2026-11-05T22 | T136, primeros 21 min | 1,0000 | 1,0000, 35 294 | 947 / 957 / 1 856 | ninguno |

Las latencias de 2026-11-05 llevan los ~835 ms del reloj (§3); lo comparable es la p99 frente a la p50, y no empeora respecto a la hora de referencia.

**Otra medición, el gate de esta misma tarea** (23:20:47–23:42:58 UTC, 1 331 s, sin pausas). Hora 23: libro útil 0,9989, `depth` con cobertura 0,9994 y 35 292 mensajes, p50 / p99 / máx 948 / 1 124 / 4 177 ms y **2 silencios marcados**. La hora cuenta como completa, pero esta vez sí se nota: la p99 de `depth` sube unos 130 ms sobre la referencia y la de `bbo` llega a 4 874 ms (1 045 en la hora 22). Esa hora `bbo` también tuvo casi el triple de mensajes (4,07 M frente a 1,42 M), así que no se le puede achacar todo al gate.

Van **3 gates que no rompen la hora, de 4**, y el último ya deja huella. El que la rompió también iba por la cola y no se sabe qué cambió, así que la regla sigue en pie: no correr el gate completo con una racha ya avanzada (BACKLOG T127 (3)).

## 7. La decisión ◆

**Resuelta el 2026-11-05: A sí, B opción 1.** La racha pasó de 0 a 14 h al aplicar (09–22) y a 15 h con la hora 23; T78 se cumple como pronto al cerrar la hora 2026-11-08T08 UTC. La réplica en seco previa coincidió con el resultado: 13 horas de no a sí, y dentro de cada JSON solo cambiaron `version`, `complete`, `coverage_cadence` y `requalified`. **C sigue sin decidir.** Lo que sigue es el razonamiento tal como se presentó.

**A. ¿Se adopta la medida de cadencia para `mark`?** Toca el criterio de aceptación de T78, y por eso no se ha aplicado nada.

**B. ¿Se recalculan las horas pasadas?**

| Opción | Qué se hace | Racha hoy | T78, como pronto, si nada la rompe |
|---|---|---|---|
| **1. Recalcular desde 2026-11-05T09 (recomendada)** | `--requalify 2026-11-05T09 --apply` | **14 h** (09–22) | Al cerrar la hora **2026-11-08T08 UTC** |
| 2. Solo de aquí en adelante | Recalificar desde la primera hora que cierre tras decidir | 0 | Decidiendo en la hora 23 de hoy, al cerrar la **2026-11-08T23 UTC**: 15 h más tarde |
| 3. No adoptar la medida | Nada | 0 | Sin fecha: depende de cuándo salga la fase de la banda, salvo corregir el reloj (C) |

La hora 09 es el inicio natural: la 08 está rota de verdad por el reinicio (libro útil 0,9542) y antes de ella la medida no cambia ningún veredicto. Con la réplica de §5 y la hora 22, cambian 13 horas de 150.

**El argumento en contra de recalcular:** es cambiar la vara después de ver el resultado, algo que este proyecto prohíbe en sus experimentos (E12). Se recomienda igualmente porque no baja el mínimo, no mueve ninguna otra hora, es apenas más estricta con los huecos reales y cada JSON recalificado conserva su veredicto original (`requalified.complete_before`) y su `coverage`. Pero la decisión es del usuario: T78 es su criterio.

**C. ¿Se sincroniza el reloj?** No hace falta para T78 si se adopta la medida. Recomendación: **dejarlo como está hasta cerrar T78** y entonces corregirlo con permiso, porque un salto a mitad de corrida no aporta nada y mueve todos los sellos del equipo. Si la medida **no** se adopta, es la única salida. Ojo: `w32tm /resync` no bastaría con un desfase menor de 1 s, por lo visto en §3.

**Despliegue sin parar la captura:** el vigilante carga `qc.py` al arrancar, así que fusionar no cambia lo que hace. Y es el padre del recolector: reiniciarlo corta la captura, que en el despliegue del 2026-11-02 estuvo 49 s parada, y con más de 36 s la hora se pierde. Por eso se añadió `--requalify`, que corre aparte. Mientras el vigilante siga con el código viejo, sus JSON nuevos salen en versión 1 y hay que recalificar antes de leer la racha. **Comprobado de punta a punta con la hora 23:** el vigilante la escribió en versión 1, `--streak` dijo 0 h, y tras `--requalify` dijo 15 h. Reiniciarlo puede esperar a cuando se cumpla T78, como ya prevé §3 de `ESTADO_PROYECTO.md`.

## 8. Lo que queda sin saber

- Por qué el arranque del 2026-11-03 casi no movió el reloj (§3).
- Si la deriva sigue: subió ~3,4 ms/h entre las horas 09 y 16 y luego se aplanó. Los dos NTP de hoy, separados 10 minutos, no bastan para medirla.
- Visto de paso, sin investigar: en la hora 2026-11-05T15 la mediana de latencia de `bbo` fue de 2 335 ms (unos 1 400 ms por encima de lo normal) con cobertura 1,0 y sin marca alguna. La regla de hora completa no mira la latencia. Anotado en BACKLOG.
