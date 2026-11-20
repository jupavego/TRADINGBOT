# T80 — Prueba de techo del carril HFT (informe de decisión)

Modo: **ANÁLISIS** (no se opera nada aquí). Símbolo **BTCUSDT**, cubos de 1000 ms, reacción aplicada 1000 ms.
Ventana: **2026-11-02 → 2026-11-19** (18 días UTC, 386 horas completas de la captura de T78, 1330396 cubos utilizables de 1389105).
Pre-registro `hft_ceiling_v1` · SHA-256 `a5dbd8e56540191d…` · calculado en 92 s.

## 1. Criterios (congelados ANTES de calcular cualquier resultado)

Archivo `eim/hft/prereg/hft_ceiling_v1.json`, con su SHA-256 fijado en el código: cambiar un umbral es una versión nueva, no una edición. Ni uno de estos números se tocó después de ver los resultados.

| # | Criterio | Umbral |
|---|---|---|
| C1 | Oportunidad: fracción de ventanas en las que |Δmid| supera el ida y vuelta (previsión perfecta de la dirección, reacción medida) | ≥ 1,00 % |
| C2 | IC fuera de muestra de alguna señal (Spearman por día) | media > 0, IC 95 % inferior > 0 y **p de Holm < 0,05** sobre 68 intentos |
| C3 | pb netos por operación fuera de muestra, con el costo de ese estilo | media ≥ **+1,0 pb** e IC 95 % inferior > 0 |
| C4 | Muestra | ≥ 14 días con panel y ≥ 8 días de prueba |

Horizontes: 1 s, 5 s, 30 s, 60 s (T77 fijó 30 s como tenencia mínima viable y taker desde 60 s; 1 s y 5 s se miden como variables, no como tenencia).
Costos de ida y vuelta (`CostParams`, VIP 0): taker 10,0 pb · mixto 7,0 pb · maker 4,0 pb.
Partición: walk-forward por días UTC contiguos, 5 de entrenamiento, 1 de prueba, embargo de 1 día y purga por la etiqueta (ninguna fila de entrenamiento tiene su etiqueta dentro del día de prueba).

Regla de veredicto, fijada de antemano:

- **SUPERA**: C4 y, en al menos un horizonte con un estilo de ejecución, C1, C2 y C3 a la vez → sigue T81–T85
- **NO SUPERA**: C4 pero ningún horizonte cumple C1, C2 y C3 → se archiva con el resultado honesto (como T28) o se redirige (otro horizonte, otro símbolo, comisión VIP/rebate), decisión ◆ del usuario
- **SIN POTENCIA**: no se cumple C4: no se publica veredicto de techo

## 2. Cómo se obtuvo la evidencia

```
python -m eim.data.collectors.hft_panel --from 2026-11-02T00 --to 2026-11-19T23     # panel: reproduce el libro de T78
python -m eim.hft.ceiling_run --root data --out reports      # esta corrida
```

El panel tiene una fila por segundo con el libro top-5 al CIERRE del cubo, el OFI multinivel acumulado dentro del cubo y el flujo agresor del cubo; se muestrea por hora de RECEPCIÓN, que es lo que se pudo saber en el momento. Solo entran horas que el control de calidad de T78 da por completas y sin huecos sin detectar, y dentro de ellas solo los cubos completos.

Contexto del libro: cola visible al frente 4,611 BTC (mediana), spread 0,01 pb (p50) y 0,02 pb (p95), volumen negociado 2,185 BTC/s de media.

Avisos que hay que leer con los números:

- Las ventanas se solapan (una por cubo): las medias por día y sus IC por bloques de día valen; el número de operaciones **no es realizable** (el equivalente sin solape es filas ÷ horizonte en segundos).
- La reacción se aplica retrasando la entrada un cubo entero (1 000 ms) cuando lo medido en T77 es 233/310 ms (p50/p99): el resultado es **más pesimista** que la latencia real.
- El camino del mid se mira al cierre de cada cubo: un toque y vuelta dentro del mismo segundo no se ve.
- Una fila solo entra si su cubo está completo, todas sus variables son finitas y los cubos de su ventana más larga son contiguos (una ventana que cruza una hora no capturada mezclaría datos de los dos lados). El VPIN se mide en cubos de volumen y es la única ventana que puede arrastrar historia de antes de un hueco.

## 3. (a) Techo con previsión perfecta de la dirección

Se conoce el signo del Δmid y se entra siempre del lado bueno, sin selección adversa, sin cola y sin impacto: **nadie puede superar esto**. «paga» = las ventanas en las que |Δmid| supera el ida y vuelta; «techo» = E[máx(|Δmid| − costo, 0)] por ventana (pb).

### Sin reacción (cota de arriba absoluta)

| h | n | |Δmid| medio | p90 | p99 | paga taker / techo | paga mixto / techo | paga maker / techo |
|---|---|---|---|---|---|---|---|
| 1 s | 1388916 | 0,347 | 1,190 | 3,302 | 0,02 % / 0,001 | 0,08 % / 0,002 | 0,56 % / 0,009 |
| 5 s | 1388895 | 1,146 | 2,946 | 7,298 | 0,35 % / 0,014 | 1,14 % / 0,033 | 5,28 % / 0,112 |
| 30 s | 1388035 | 3,247 | 7,412 | 17,932 | 5,08 % / 0,264 | 11,23 % / 0,494 | 27,83 % / 1,040 |
| 60 s | 1387135 | 4,633 | 10,374 | 25,139 | 10,80 % / 0,663 | 20,74 % / 1,118 | 40,99 % / 2,010 |

### Con la reacción medida (entrada un cubo después)

| h | n | |Δmid| medio | p90 | p99 | paga taker / techo | paga mixto / techo | paga maker / techo |
|---|---|---|---|---|---|---|---|
| 1 s | 1388847 | 0,347 | 1,190 | 3,302 | 0,02 % / 0,001 | 0,08 % / 0,002 | 0,56 % / 0,009 |
| 5 s | 1388853 | 1,146 | 2,946 | 7,298 | 0,35 % / 0,014 | 1,14 % / 0,033 | 5,28 % / 0,112 |
| 30 s | 1388005 | 3,247 | 7,412 | 17,932 | 5,08 % / 0,264 | 11,23 % / 0,494 | 27,83 % / 1,040 |
| 60 s | 1387105 | 4,633 | 10,374 | 25,139 | 10,80 % / 0,663 | 20,74 % / 1,118 | 40,99 % / 2,010 |

## 4. (b) IC fuera de muestra de cada variable y de la ridge conjunta

IC de Spearman medio por día de prueba. **=** marca p de Holm < 0,05 sobre los 68 intentos de la familia (todos los de esta tabla).

| señal | IC 1 s | IC 5 s | IC 30 s | IC 60 s |
|---|---|---|---|---|
| `baseline_v1` | 0,0747 = | 0,0602 = | 0,0116 | 0,0078 |
| `depth_imb` | 0,1410 = | 0,1280 = | 0,0618 = | 0,0438 = |
| `flow_imb_30` | 0,0211 = | 0,0166 | 0,0033 | 0,0042 |
| `flow_imb_5` | 0,0575 = | 0,0473 = | 0,0211 | 0,0142 |
| `intensity` | -0,0002 | 0,0008 | -0,0077 | -0,0119 |
| `jump_share` | 0,0032 | 0,0031 | -0,0002 | -0,0050 |
| `ofi_all_1` | 0,0673 = | 0,0483 = | 0,0189 = | 0,0079 |
| `ofi_all_30` | 0,0215 = | 0,0144 | 0,0086 | 0,0075 |
| `ofi_all_5` | 0,0515 = | 0,0348 = | 0,0118 | 0,0057 |
| `ofi_top_1` | 0,0381 | -0,0089 | 0,0193 = | 0,0041 |
| `ofi_top_30` | 0,0371 = | 0,0311 | 0,0128 | -0,0022 |
| `ofi_top_5` | -0,0023 | 0,0420 | 0,0243 | 0,0076 |
| `ridge_all` | 0,1393 = | 0,1258 = | 0,0533 = | 0,0283 = |
| `rv_bps` | -0,0089 | -0,0096 | -0,0079 | -0,0099 |
| `spread_bps` | 0,0036 | -0,0017 | 0,0347 = | 0,0455 = |
| `tilt_bps` | 0,1417 = | 0,0149 | 0,0617 = | 0,0435 = |
| `vpin` | 0,0000 | -0,0014 | 0,0077 | 0,0096 |

Detalle de la mejor señal de cada horizonte (IC 95 % por bloques de día):

| h | señal | IC medio | IC 95 % | días + | p | p Holm |
|---|---|---|---|---|---|---|
| 1 s | `tilt_bps` | 0,1417 | 0,1319 … 0,1521 | 100 % | 0,000 | 0,014 |
| 5 s | `depth_imb` | 0,1280 | 0,1083 … 0,1516 | 100 % | 0,000 | 0,014 |
| 30 s | `depth_imb` | 0,0618 | 0,0426 … 0,0905 | 100 % | 0,000 | 0,014 |
| 60 s | `spread_bps` | 0,0455 | 0,0299 … 0,0610 | 92 % | 0,000 | 0,014 |

Calibración y acierto de esa misma señal (F0 exige salida probabilística): la predicción se juzga como probabilidad y como cuantil con la σ del Δmid medida solo en el entrenamiento, frente a la caminata aleatoria (como la C7 de T27). El acierto balanceado es sobre la dirección NETA de costos maker (0 = no paga).

| h | señal | Brier skill | pinball 10 | pinball 90 | acierto balanceado |
|---|---|---|---|---|---|
| 1 s | `tilt_bps` | 0,3704 % | -0,0514 % | 0,0966 % | 52,088 % |
| 5 s | `depth_imb` | 1,4505 % | 0,0215 % | 0,2882 % | 53,252 % |
| 30 s | `depth_imb` | 0,4551 % | -0,1630 % | 0,2398 % | 52,420 % |
| 60 s | `spread_bps` | 0,1049 % | -0,2775 % | 0,3116 % | 50,030 % |

## 5. (c) pb brutos por operación, antes de pagar el costo

Media de signo(predicción) × Δmid por día de prueba, con la reacción aplicada y SIN restar costo: es el edge bruto que existe. «decil» = solo el 10 % de filas con la predicción más fuerte. Al lado, el costo más bajo que habría que pagar (4,0 pb, maker-maker).

| h | señal | bruto todas (pb) | IC 95 % | bruto decil (pb) | IC 95 % |
|---|---|---|---|---|---|
| 1 s | `depth_imb` | 0,0537 | 0,0464 … 0,0586 | 0,1080 | 0,0970 … 0,1171 |
| 5 s | `depth_imb` | 0,1332 | 0,1203 … 0,1433 | 0,2509 | 0,2307 … 0,2718 |
| 30 s | `spread_bps` | 0,0797 | 0,0292 … 0,1293 | 0,5104 | 0,3957 … 0,6341 |
| 60 s | `spread_bps` | 0,1583 | 0,0574 … 0,2590 | 0,9875 | 0,7559 … 1,2174 |

### pb netos por operación, con el costo de cada estilo

De cada horizonte, la señal con los mejores pb netos de cada estilo: se opera solo cuando la predicción (ajustada con el entrenamiento) supera el costo. «—» significa que la predicción nunca llegó a ese costo: no hay operación que hacer.

| h | estilo | señal | pb netos | IC 95 % | operaciones | % de filas | sin solape |
|---|---|---|---|---|---|---|---|
| 1 s | taker | `tilt_bps` | -11,063 | — … — | 4 | 0,01 % | 4 |
| 1 s | mixto | `tilt_bps` | -8,971 | — … — | 6 | 0,01 % | 6 |
| 1 s | maker | `ridge_all` | 0,838 | -3,465 … 5,140 | 5 | 0,00 % | 5 |
| 5 s | taker | `ofi_top_1` | -9,426 | — … — | 1 | 0,00 % | 0 |
| 5 s | mixto | `ofi_top_1` | -3,395 | -6,426 … -0,364 | 2 | 0,00 % | 0 |
| 5 s | maker | `ofi_top_30` | -3,517 | — … — | 30 | 0,03 % | 6 |
| 30 s | taker | `spread_bps` | 13,797 | -1,210 … 28,934 | 18 | 0,01 % | 0 |
| 30 s | mixto | `spread_bps` | 7,594 | -3,281 … 21,566 | 40 | 0,01 % | 1 |
| 30 s | maker | `spread_bps` | 6,645 | -1,620 … 17,626 | 87 | 0,01 % | 2 |
| 60 s | taker | `spread_bps` | 7,254 | -8,277 … 24,930 | 29 | 0,01 % | 0 |
| 60 s | mixto | `spread_bps` | 1,234 | -12,293 … 16,787 | 48 | 0,01 % | 0 |
| 60 s | maker | `ofi_top_30` | 7,693 | -8,993 … 37,856 | 707 | 0,10 % | 11 |

## 6. (d) Qué parte del movimiento se come el costo

Con la reacción medida, sobre las ventanas que pagan: «bruto» es |Δmid| medio ahí y «costo/bruto» la parte que se lleva la comisión más el spread.

| h | estilo | bruto (pb) | neto (pb) | costo/bruto | costo/|Δmid| medio |
|---|---|---|---|---|---|
| 1 s | taker | 14,343 | 4,343 | 69,72 % | 28,82× |
| 1 s | mixto | 9,872 | 2,872 | 70,90 % | 20,17× |
| 1 s | maker | 5,692 | 1,692 | 70,27 % | 11,53× |
| 5 s | taker | 13,950 | 3,950 | 71,68 % | 8,72× |
| 5 s | mixto | 9,923 | 2,923 | 70,54 % | 6,11× |
| 5 s | maker | 6,120 | 2,120 | 65,36 % | 3,49× |
| 30 s | taker | 15,194 | 5,194 | 65,82 % | 3,08× |
| 30 s | mixto | 11,393 | 4,394 | 61,44 % | 2,16× |
| 30 s | maker | 7,736 | 3,736 | 51,71 % | 1,23× |
| 60 s | taker | 16,140 | 6,140 | 61,96 % | 2,16× |
| 60 s | mixto | 12,392 | 5,391 | 56,49 % | 1,51× |
| 60 s | maker | 8,903 | 4,903 | 44,93 % | 0,86× |

### Llenado de la cola: ¿existe la entrada pasiva?

Cola pesimista (al final de la cola visible al llegar, sin avanzar por cancelaciones): fracción de cubos en los que una orden al mejor precio se habría llenado dentro de la espera.

| espera | compra | venta | media |
|---|---|---|---|
| 1 s | 9,09 % | 8,91 % | 9,00 % |
| 5 s | 23,00 % | 22,12 % | 22,56 % |
| 30 s | 38,98 % | 38,02 % | 38,50 % |

## 7. Veredicto

### NO SUPERA

- **C4 muestra**: 18 días (mínimo 14) y 12 días de prueba (mínimo 8) → cumple.

| h | C1 estilos que pagan | C2 señales con IC (Holm) | C3 (señal, estilo) | ¿supera? |
|---|---|---|---|---|
| 1 s | — | `tilt_bps`, `depth_imb`, `ridge_all`, `baseline_v1` | — | no |
| 5 s | mixto, maker | `depth_imb`, `ridge_all`, `baseline_v1`, `ofi_all_1` | — | no |
| 30 s | taker, mixto, maker | `depth_imb`, `tilt_bps`, `ridge_all`, `spread_bps` | — | no |
| 60 s | taker, mixto, maker | `spread_bps`, `depth_imb`, `tilt_bps`, `ridge_all` | — | no |

Lo que decide el usuario (◆, §Aceptación de T80):

- si el techo o el IC no superan los costos con margen en ningún horizonte → se archiva con el resultado honesto (como T28) o se redirige: otro horizonte, otro símbolo, comisión VIP/rebate;
- si lo superan → siguen T81–T85 con este marco y estas variables.

Registro de intentos: `eim/hft/attempts_t80.json` (68 intentos; cuentan en la familia de Holm de T84 aunque se descarten).
