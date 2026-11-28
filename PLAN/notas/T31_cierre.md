# T31 — Cierre de la corrida en papel (4 semanas)

**Modo: SIMULADO.** Sin dinero real. Esta nota cierra la aceptación de T31 y **no habilita capital
real**: esa decisión la toma el usuario por escrito, y hoy la cierran T27 (NO PASA) y la postura de
solo análisis de T145.

- **Corrida:** `juanpablo-cpu`, arrancada el 2026-10-30 23:35 UTC con `servicio_continuo.ps1 -ConWeb`
  (decisión del usuario del 2026-10-31). Las 4 semanas se cumplen el **2026-11-27 23:35 UTC**.
- **Informe del cierre:** `python -m eim.operation report` sobre el periodo completo, vía
  `POST /v2/operation/report?start=1793403300000` → `v2/reports/operation/periodo_1793403300000_<fin>.{md,json}`.
  Hay un corte previo, a las 14:38 UTC (3,95 semanas), y el definitivo se genera a las 23:40 UTC
  (§6), antes de que T194 y T182 se enciendan a las 00:00 UTC del 28-nov.

## 1. Aceptación

| Criterio (`PLAN/T31.md`) | Resultado |
|---|---|
| ≥ 4 semanas de operación continua | **Cumple** al cerrar el 27-nov 23:35 UTC. El vigilante relanzó la API cuando se cayó (más de 20 reinicios, casi todos por memoria ajena; ver T141/T206). Ninguna caída cortó la corrida: el estado y los cursores sobreviven a cada reinicio. |
| Sin incidentes de reconciliación sin resolver | **Cumple:** «Reconciliación sin resolver: ninguna». La única distorsión es T142, ya reconciliada (§4). |
| Informe final con comparación contra el backtest | **Cumple:** §2–§3, con el informe del periodo completo. |

## 2. Resultados — universo oficial (T144), corte de las 14:38 UTC

Es el libro fijo de los cuatro perfiles, solo con lo vivido, con peso y sin `retro`.

| Alcance | Cuentan | R medio | IC95 % | Acierto | R total | PnL (USDT) |
|---|--:|--:|--:|--:|--:|--:|
| **Total** | **667** de 701 | **−0,06** | −0,10 … −0,03 | 83 % | −41,12 | **−2 257,16** |
| agresivo | 219 | −0,08 | — | 85 % | −16,72 | −1 616,02 |
| moderado | 315 | −0,07 | — | 81 % | −20,64 | −454,98 |
| ppp_btcusdt | 133 | −0,03 | — | 82 % | −3,76 | −186,16 |

- Quedan fuera 34 operaciones `retro` (−862,98 USDT, −14,59 R): nadie las vivió en su momento.
- Drawdown: 2 292,83 USDT (8,2 %). Huella de lo contado: `65993de7b1b1`.
- **La fricción decide el signo.** El costo medido es 0,125 R por operación (4 276 USDT, 17,9 pb del
  nocional), así que el bruto ronda **+0,06 R** y el neto queda en −0,06 R. El costo es el mismo
  diagnóstico que T143 y T215 (antes T213). Por marco: 15m 0,155 R · 1h 0,125 R · 4h 0,078 R. Por
  entrada: límite 0,095 R frente a mercado 0,135 R.
- **La corrida de operación** (la vista del servicio, no la cifra oficial) solo hizo 2 operaciones,
  con +0,37 R y n = 2 (no concluyente): **74 de 76 decisiones se vetaron por «datos»**. Esa es la
  causa que T209 (PR #349) corrige: `literature` y `vwap` se marcaban degradados por una limitación
  de la ventana, no por datos rotos.

## 3. Comparación con el backtest (T27)

- BTCUSDT tiene un backtest de 242 operaciones en 182 semanas, con esperanza **−0,49 R** y DD de
  23 %. Fuente: `reports/edge/edge_results.json`; no es reproducible (T124).
- El universo oficial da −0,06 R frente a −0,49 R: es **diferente del backtest y menos malo**, pero
  su IC95 % no incluye el cero. **No hay ventaja.** La comparación sostiene lo mismo que T27.
- **Calibración de escenarios:** 891 pronósticos (≈ 36 independientes). Las bandas 50/80/90 cubren
  cerca de lo nominal, pero el Brier skill da −0,1 % y el pinball +0,4 %: no superan a la caminata
  aleatoria. El acierto direccional es de 55 % (n = 875), indistinguible del azar. La proyección
  sirve como rango de incertidumbre, no como señal.

## 4. Incidentes y distorsiones

- Hubo 587 alertas: 516 `obs_sin_latido`, 38 del indexador, 23 de agentes degradados, 5 de
  protección y 5 de dato obsoleto. Ninguna quedó como reconciliación abierta.
- **T142:** 5 posiciones fantasma entre el 2026-11-04 y el 2026-11-07, ya reconciliadas
  (−142,86 USDT en total). Las 18 entradas `retro` de ese episodio no suman (`PLAN/notas/T142_posiciones_fantasma.md`).
- **Captura HFT (T78/T147):** 148 h de 72 en la ventana, así que **cumple**. Se completaron 576 de
  663 horas (86,9 %): 69 se perdieron por causa nuestra y 17 por causa ajena.
- **Carga del equipo:** muchos días con horas saturadas, sobre todo por `chrome.exe`, `claude.exe`
  y `ffmpeg.exe` (T141). La RAM libre llegó a 0,0 GB el 09-nov y el 24-nov.

## 5. Lo que sigue al cierre

- **00:00 UTC del 28-nov:** T194 (riesgo con costos y freno gradual) y T182 (lo vivo manda) se
  encienden solas, sin reiniciar. El turno lo marca este cierre: no se mueve la fecha.
- **T143:** compara su marco de costos contra este cierre (las cifras de §2 son la base).
- **Capital real:** no. Lo decide el usuario por escrito; hoy no hay ventaja (T27 NO PASA, y
  T145 deja el proyecto en solo análisis).

## 6. Cifras del periodo completo (23:40 UTC)

Informe: `v2/reports/operation/periodo_1793403300000_1795822500000.{md,json}` (fin 2026-11-27
23:35 UTC, generado a las 23:41 UTC). Mismo universo oficial que §2 (T144).

| Alcance | Cuentan | R medio | IC95 % | Acierto | R total | PnL (USDT) |
|---|--:|--:|--:|--:|--:|--:|
| **Total** | **685** de 719 | **−0,06** | −0,09 … −0,02 | 83 % | −37,79 | **−2 031,81** |
| agresivo | 227 | −0,07 | — | 85 % | −15,27 | −1 501,60 |
| moderado | 321 | −0,06 | — | 82 % | −19,47 | −377,37 |
| ppp_btcusdt | 137 | −0,02 | — | 82 % | −3,05 | −152,84 |

- Drawdown: 2 292,83 USDT (8,20 %), el mismo que en §2. Huella de lo contado: `498b4209a391`.
- `retro` excluidas: 34 (−862,98 USDT, −14,59 R), las mismas que en §2.
- Costo medido: 0,125 R de media (mediana 0,119) por operación, 4 425,95 USDT en total (17,9 pb
  del nocional). Por marco: 15m 0,156 R · 1h 0,125 R · 4h 0,077 R. Por entrada: límite 0,095 R
  frente a mercado 0,136 R.
- Calibración: 900 pronósticos (≈ 36 independientes). Brier skill −0,1 %, pinball +0,3 %, acierto
  direccional 54,4 % (n = 884). No supera a la caminata aleatoria.
- Reconciliación sin resolver: ninguna. 609 alertas (531 `obs_sin_latido`, 44 del indexador,
  21 de agentes degradados, 7 de dato obsoleto, 6 de protección).
- Semanas operadas: 4,0. La corrida de operación sigue en 2 operaciones (+0,37 R, n = 2) y 74 de 76
  decisiones vetadas por «datos».

**La conclusión de §2 se mantiene:** el R medio sigue en −0,06 con un IC95 % que excluye el 0, no hay
ventaja y el costo sigue en ~0,125 R por operación.

## 7. Potencia (lo que pedía T161)

Con `eim/validation/power.py::mde` sobre el universo oficial del periodo completo (n = 685,
σ = 0,46 R por operación; α = 5 % bilateral y potencia del 80 %):

- Estas 4 semanas detectan una ventaja neta de **±0,05 R** por operación o mayor.
- Los cuatro perfiles salen de las mismas ideas, así que la muestra efectiva es menor que 685. En el
  peor caso, que los perfiles fueran copias unos de otros, quedaría en el perfil más grande
  (moderado, n = 321) y el mínimo detectable subiría a **≈ 0,07 R**.
- T161 esperaba ≥ 0,18 R, porque suponía σ ≈ 1,15 R y unas 250 operaciones. El libro fue menos
  disperso (83 % de acierto con salidas cortas) y cerró casi el triple de operaciones.

**Lectura:** si hubiera una ventaja neta de +0,05 a +0,07 R o mayor, estas 4 semanas la habrían visto
con un 80 % de probabilidad. No la vieron, y la media sale negativa con el IC95 % fuera del cero. Una
ventaja más pequeña no se habría podido validar con esta muestra. El bruto ronda +0,07 R, del mismo
orden que ese mínimo, y el costo de 0,125 R se lo come (§2).
