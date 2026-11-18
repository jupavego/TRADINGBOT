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

**Con los dos entregables, el crecimiento baja de ≈ 53 a ≈ 32 MB/día (11,7 GB/año).** No es
«dejar de crecer». Lo que falta para eso es la ◆ de abajo.

## 3. ◆ Decisión del usuario: cómo se guarda cada foto

Cada posición del JSON repite `leader_id` (65 caracteres), `address` (42), `source`, `t` y
`observed_at`, que **ya están en las columnas de la fila**. Una foto de 15 monedas gasta ~1,5 KB
solo en eso. Medido en disco con las mismas 20 000 fotos reales:

| Opción | Filas | En disco | Frente a hoy | Crecimiento estimado |
|---|---|---|---|---|
| **A. Como hoy** | 20 000 | 129,2 MB | 100 % | ≈ 53 MB/día |
| **B. Cambio + una por hora** (lo que entrega T178) | 8 648 | 78,9 MB | 61 % | ≈ 32 MB/día |
| **C. Recodificar la foto, sin borrar ninguna** | 20 000 | 32,0 MB | **25 %** | ≈ 13 MB/día |
| **D. B + C** | 8 648 | 11,5 MB | **9 %** | **≈ 5 MB/día** |

C no pierde **ningún** campo: saca una sola vez por foto lo que hoy se repite en cada posición.
Cuesta un codificador y un decodificador (`leader_photos.py`) y tocar los cuatro sitios que leen
`positions`; las fotos viejas se siguen leyendo en el formato actual, y rehacerlas una vez
devolvería ~800 MB del archivo de hoy.

**Lo que se pregunta:** ¿se adopta **C** (y con ella **D**), o se queda en **B** y se acepta
crecer ~12 GB al año? T178 entrega B; C es trabajo nuevo, acotado, y es lo único que hace que
«deje de crecer» sea verdad.

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
