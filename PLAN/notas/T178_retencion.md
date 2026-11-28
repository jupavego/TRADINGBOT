# T178 — Qué crece de verdad en `leaders.duckdb`, y la ◆ que queda

Medido el 2026-11-18 sobre la **copia completa de las 13:07 UTC** (`eim_20261118-130754`), nunca
sobre la base viva. Scripts de medición en el borrador de la sesión; las cifras de abajo se
pueden rehacer con `pragma database_size` y las consultas que se citan.

## 1. La poda de T128 está al día; lo que crece es otra cosa

| Tabla | Filas (18-nov) | Filas/día | ¿Tiene tope? |
|---|---|---|---|
| `leader_fills` | 2 681 574 | — | **Sí**: solo 2 371 filas tienen más de 7 días; la poda borra casi tanto como entra |
| `leader_follow` | 2 600 365 | — | **Sí**, igual que las ejecuciones |
| `leader_positions` | 227 338 | +10 600 | **No** |
| `leader_recon` | 905 941 | +41 300 | **No** |
| `leader_archive_trips` | 116 899 | +5 900 | No (es el archivo plegado: se quiere) |
| `leader_funding` | 95 444 | +2 400 | No (pagos reales: se quieren) |

El archivo pesa 1 628 MB y `pragma database_size` dice 6 508 bloques usados y **0 libres**: no
hay hueco que reutilizar, así que cada fila nueva agranda el archivo.

**Lo que hay que mirar no son las filas, son los bytes por fila.** Escribiendo 20 000 fotos
reales en una base limpia salen **129,2 MB**, es decir **≈ 6,5 KB por foto** (4,9 KB de JSON más
su índice); una fila de `leader_recon` ocupa **≈ 9,6 B** (las 905 941 caben en 8,7 MB). Con eso:

- fotos de posiciones: 10 600 × 6,5 KB ≈ **52 MB/día**
- reconciliaciones: 41 300 × 9,6 B ≈ **0,4 MB/día**

Los **+53 MB/día** que midió T128 son, casi enteros, **las fotos de posiciones**. Y son de los
**rechazados**: 221 633 de las 227 338 fotos (1 080 MB de JSON) son suyas, aunque su detalle ya
esté plegado. Las de `watch` ocupan 2 bytes cada una (no tienen posiciones abiertas).

## 2. Lo que entrega T178

- **Reconciliaciones** (entregable 1): pasados 7 días se quedan todas las que no cuadran o
  resincronizaron (6 397 de 905 941) y, de las correctas, una por líder **cada 2 min**; de las
  demás queda el resumen por día y líder en `leader_recon_daily`. Los 2 min no son un capricho:
  `CopyParams.recon_gap_ms` son 5 min, así que con una rejilla mayor la copia simulada vería
  huecos de flujo que nunca existieron. Quita 627 777 filas ≈ **6 MB**.
- **Fotos** (entregable 2): pasados 7 días se queda la foto de **cada cambio de forma** (moneda,
  lado, tamaño, entrada, apalancamiento, modo de margen) y **una por hora**. Para que el tiempo
  capturado que mide T49 no cambie al borrar, antes de borrar se guarda en `leader_photo_cover`
  el tiempo que cubrían las fotos originales, y `leader_eval.context` lo suma desde ahí.
- **Lo que esto ahorra, medido:** solo el **39 %** de los bytes de las fotos. Porque **el 66 %
  de las fotos de más de 7 días son cambios de forma de verdad** (102 771 de 155 698): estos
  líderes mueven la cartera casi cada minuto, así que deduplicar apenas tiene qué quitar.

**Con solo esos dos entregables, el crecimiento bajaría de ≈ 53 a ≈ 32 MB/día (11,7 GB/año)**, que
no es «dejar de crecer». Con la ◆ de abajo ya resuelta (recodificar la foto), queda en **≈ 5
MB/día (1,8 GB/año)**.

## 3. ◆ Resuelta (usuario, 2026-11-18): se recodifica la foto

Cada posición del JSON repite `leader_id` (65 caracteres), `address` (42), `source`, `t` y
`observed_at`, que **ya están en las columnas de la fila**. Una foto de 15 monedas gasta ~1,5 KB
solo en eso. Medido en disco con las mismas 20 000 fotos reales:

| Opción | Filas | En disco | Frente a hoy | Crecimiento estimado |
|---|---|---|---|---|
| **A. Como hoy** | 20 000 | 129,2 MB | 100 % | ≈ 53 MB/día |
| **B. Cambio + una por hora** (lo que entrega T178) | 8 648 | 78,9 MB | 61 % | ≈ 32 MB/día |
| **C. Recodificar la foto, sin borrar ninguna** | 20 000 | 32,0 MB | **25 %** | ≈ 13 MB/día |
| **D. B + C** | 8 648 | 11,5 MB | **9 %** | **≈ 5 MB/día** |

**El usuario eligió D** (recodificar y podar), así que T178 entrega las dos cosas.

C no pierde **ningún** campo: saca una sola vez por foto lo que hoy se repite en cada posición.
Formato nuevo en `eim/data/leader_photos.py` (`{"v":2,"h":{…},"p":[[…], …]}`, un objeto para
distinguirlo de la lista de antes); `decode` lee los dos, así que **ninguna foto vieja deja de
leerse**, y si alguna vez llegara una foto cuyas posiciones no comparten cabecera se guarda en el
formato de antes antes que perder un campo. Escriben y leen por el códec `leader_store`
(`save_positions`, `positions_at`), `leader_score_store.positions_near` y `copy_replay`.

Las fotos ya guardadas las pasa `recode_photos`: con el servicio en marcha, **50 000 por vuelta**
(unos 250 MB de lectura, en tandas de 5 000 dentro de su transacción), así que las 227 338 de hoy
tardan unos días; en frío (`python -m eim.leaders prune`) va sin tope y el compactado que viene
detrás devuelve el espacio (~800 MB).

## 4. Lo que se comprobó de los lectores

- `leader_report.summary` suma el detalle que queda **más** `leader_recon_daily`: comprobadas,
  saltadas, tamaño, coincidencias y resincronizaciones dan el mismo total que antes de borrar
  (prueba `test_the_quality_report_adds_up_after_thinning`). El desfase de reloj de los días ya
  resumidos sale como media y máximo, no como mediana: de esos días no quedan valores sueltos.
- `leader_eval.context` da el mismo `observed_ms` y el mismo `forward_start` antes y después de
  borrar fotos (prueba `test_the_captured_time_does_not_change_when_photos_are_deleted`).
- `copy_replay` lee las fotos para reconstruir señales; de un rechazado con más de 7 días ya no
  podía repetir nada, porque T128 le borró las ejecuciones. De los aprobados y `watch` no se
  borra nada que no sea una repetición exacta de la forma.
- La poda y la retención corren en la misma vuelta diaria del servicio y, en frío, antes de
  compactar (`python -m eim.leaders prune`).

## Cierre (2026-11-27): una semana con las copias diarias

Tamaño de `leaders.duckdb` en cada copia de las 00:00 UTC (`v2/backups/eim_*`); las filas se cuentan en sólo lectura.

| Copia | MB | Filas | `leader_recon` | `leader_follow` | `leader_fills` | `leader_positions` |
|---|--:|--:|--:|--:|--:|--:|
| 2026-11-19 (antes de desplegar) | 1 665 | — | — | — | — | — |
| 2026-11-20 | 945 | 6 515 380 | 485 320 | 2 597 654 | 2 674 591 | 191 685 |
| 2026-11-23 | 869 | 5 811 661 | 528 112 | 2 188 247 | 2 275 396 | 216 971 |
| 2026-11-25 | 812 | 5 391 548 | 542 221 | 1 953 094 | 2 043 692 | 231 297 |
| 2026-11-27 | 821 | 5 270 502 | 551 192 | 1 871 921 | 1 959 536 | 244 072 |

- Los datos **dejaron de crecer**: −124 MB entre el 20 y el 27-nov, y ≈ +1 MB/día los dos últimos días, frente a +53 MB/día antes. La aceptación se cumple.
- `leader_recon` crece ≈ +9 400 filas/día (antes +41 300), por lo que se queda una por líder cada 2 min. `leader_recon_daily` añade unas 17 filas/día, el resumen diario por líder, y confirma que la retención corre cada día.
- `leader_positions` crece ≈ +7 500/día (antes +10 600). Los últimos 7 días van completos y los anteriores con una foto por cambio y otra por hora.
- `leader_follow` y `leader_fills` bajan porque la poda de T128 recorta a los rechazados.
- **◆ del entregable 3 (usuario, 2026-11-27): el detalle de aprobados y `watch` se queda entero, con alarma.** Si un líder pasa a `approved` y la base crece más de 20 MB/día durante 3 días, se pliega como el de los rechazados (ver `PLAN/BACKLOG.md`).
