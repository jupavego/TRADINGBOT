# T127 — cierre: la semana del registro de consumo y la captura frente a la cola

Revisión del 2026-11-09, al terminar la ventana del vigía (2026-11-02 03:38 → 2026-11-09 03:38 UTC).
Fuentes: `v2/reports/operation/semana_2026-W45.md` (sección «Consumo del equipo»), el QC por hora de
la captura (`data/micro_hft/qc/symbol=BTCUSDT/`), la cola (`data/jobs/queue/*.json` y
`data/jobs/log/*.jsonl`) y el registro de consumo (`data/usage/*.jsonl.gz`, una muestra cada 30 s).

## 1. Una semana del registro de consumo en el informe semanal: cumplido

El informe W45 (generado el 2026-11-08 19:01 UTC) trae los siete días del 2 al 8 de noviembre con
muestras, CPU, RAM libre mínima, reparto del EIM, horas saturadas y su cruce con las horas
incompletas de la captura. Cobertura: 84 % y 74 % el 2 y el 3 (el registro arrancó a las 03:38 del
día 2 y hubo reinicios de despliegue), 98–100 % del 4 al 8.

**Aviso:** el cruce del informe se hizo con el QC de entonces. El 2026-11-09 la recalificación de
T147 (`bbo` y `mark` ya no deciden) dejó completas tres horas que el informe lista como incompletas
(6-nov 00 y 14, 8-nov 01). Las cuentas de abajo usan el QC actual.

## 2. Horas de la captura sin silencios atribuibles a la cola: cumplido

En la ventana hay **14 horas incompletas** en el QC actual. En **11 no había ningún trabajo de la
cola en marcha**. En las tres restantes:

| Hora (UTC) | Qué la rompió | Trabajo de la cola | Veredicto |
|---|---|---|---|
| 2-nov 22 | Racimo de 6 silencios de 3–8 s en todos los flujos (22:04–22:10) y un corte de 23 s a las 22:48 con el libro descartado. Libro útil 0,9817; sin el racimo habría quedado en ≈ 0,992 (completa) | `gate-t116-3` (21:51–22:14), pausado a las 22:05 y a las 22:09 por «3 huecos nuevos» | **Red, no la cola.** 23,5 de los 35,7 s del racimo cayeron con el gate **congelado**; la CPU de la captura siguió en su ~4 %, había 3,3–4 GB libres y a las 22:07 se cortó también el WebSocket de liquidaciones de OKX, que es otro exchange (ya lo anotó `PLAN/notas/T116_gate.md`). El corte de las 22:48 fue 14 min después de terminar el último trabajo |
| 3-nov 18 | Silencio de 299 s (18:16:13 → 18:21:12) con el libro descartado. Libro útil 0,9164 | `gate-t131` (18:13:40–18:46:45), pausado a las 18:16:15 por «RAM libre 978 MB» | **Presión de memoria ajena al gate; el gate coincidió.** Ver §3 |
| 7-nov 05 | Silencio de 30–54 s a las 05:37:49 | Ninguno en ese momento: el último (`operacion-22l`) terminó a las 05:27:42 | **Ajeno.** A las 05:37 había 457 MB libres con `node.exe` 2,7 GB, `claude.exe` 2,6 GB y `chrome.exe` 2,4 GB. El trabajo pesado de la cola de esa hora (`operacion-14`, 2,6 GB) bajó la RAM libre a 617 MB a las 05:06; la cola lo congeló en 1 min y la captura no tuvo ningún hueco en esos 14 min |

La hora 2-nov 23 (incompleta, sin silencios) es el reinicio del despliegue del entregable 5 a las 23:13.

## 3. La hora 18 del 3-nov, mirada de nuevo

La bitácora del 2026-11-03 y BACKLOG T127 (3) la atribuyeron al gate («la pausa llegó tarde»). Con
el registro de consumo, muestra a muestra:

- Antes de arrancar el gate ya había solo 1,7–1,9 GB libres: `msedgewebview2.exe` 2,2 GB,
  `chrome.exe` 1,3 GB, `claude.exe` 1,3 GB. La cola esperó margen (pedía 2 048 MB) y lo admitió a las 18:13:40.
- Entre 18:15:23 y 18:16:53 la RAM libre cayó de 1 679 a 726 MB. En ese tramo **la API creció de
  784 a 1 369 MB** (mismos dos PID, CPU del 2 al 23 %), los programas ajenos +175 MB y **el gate
  +107 MB** (llegó a 366 MB; nunca a «varios GB»).
- El silencio de 299 s empezó a las 18:16:13; la cola congeló el gate **2 s después** y lo tuvo
  congelado hasta las 18:28:20. **Todo el silencio transcurrió con el gate congelado**, mientras la
  API seguía por encima de 1,2 GB y la RAM libre por debajo de 800 MB.

Conclusión: la causa principal fue el salto de la API sobre un equipo que ya estaba al límite por
programas ajenos. El gate aportó ≈ 100 MB y una CPU (≈ 20 %) durante los 2,5 min previos, y la cola
reaccionó en cuanto se cumplió su regla. No es un silencio atribuible a la cola, pero tampoco la
exculpa del todo: la hora habría sido algo menos mala sin el gate. Lo que sigue siendo útil de
BACKLOG T127 (3) es la idea de pausar antes, por la latencia de la captura y no solo por la RAM
libre; su dato de que «el gate llega a varios GB» queda corregido. El salto de la API no se ha
explicado (no es de T127).

## 4. Resto de la aceptación

- **Gate verde:** varios gates completos por la cola con todo T127 dentro, el primero el 2026-11-04
  (2 778 pasadas, 0 fallos) y el último el de T144 (3 323 pasadas, 0 fallos).
- **Pausa y reanudación solas:** comprobado en la semana con trabajos reales, no solo en las
  pruebas: 2-nov 22 (dos pausas de 185 s), 3-nov 18 (725 s y 235 s), 6-nov 14 (125 s) y 7-nov 05
  (876 s y 115 s). Todos se reanudaron solos tras 90 s sin presión.
- **Copia externa reanudable:** probada con 6 pruebas sin red al entregarla (un corte tras 2 partes retoma sin repetirlas; bitácora del 2026-11-02 05:00 UTC). En la semana la copia diaria pasó por la cola sin fallos, pero ninguna se cortó, así que la reanudación con una subida real todavía no se ha visto.

**T127 queda cerrada (☑).** Lo que sigue abierto va en BACKLOG T127 (1)–(3) y, para el hueco del
registro de consumo cuando cae el conjunto, en T148.
