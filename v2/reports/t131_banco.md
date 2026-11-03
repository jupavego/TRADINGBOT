# T131 — banco de salidas emparejado (BTCUSDT)

**Modo: SIMULADO.** Pre-registro `prereg_t131_v2`, huella `0dd3d9d8550beac0…`, 107 intentos pre-registrados. Generado el 2026-11-03T18:08+00:00 desde la copia `C:\Users\jo\Desktop\JP\TRADINGBOT\v2\backups\t131_banco` (commit `cb54615`).

Ventana medida: **2023-01-11T10:00+00:00 → 2026-08-16T00:00+00:00**, embargo 200 h. Ideas simuladas: 60720, de las que 45814 están emparejadas (todas las variantes las cerraron); 0 se descartaron por no llegar a la cantidad mínima con el riesgo fijo de 100 USDT.

Marcos de decisión del pre-registro: 1h, 4h; se dejaron fuera 6213 ideas de otros marcos y 2826 del control, que se mide aparte.

Lo que **no** se mide aquí, con su tarea: `M2` (pendiente_T132), `M3` (pendiente_T132), `M4` (pendiente_T133), `M5` (pendiente_T132), `M6` (pendiente_T132), `M7` (pendiente_T132), `M8` (pendiente_T132), `S1` (pendiente_T132), `S2` (pendiente_T132), `S3` (pendiente_T136). Cuentan como intentos aunque no se corran (E12).

## 1. Variantes

**Regresión con T111:** M0 y M1 devuelven exactamente lo que `simulate_ladder` y `engine.simulate` —las dos funciones que llamó T111— en las 500 ideas reales comprobadas, campo a campo. Cualquier cifra de T111 sale igual del banco por construcción.

### Fuera de muestra (solo los tramos de prueba de los pliegues)

| Variante | n | Acierto | E[R] | Gan. media | Pérd. media | Cociente | PF | Costo R | DD máx. R | CVaR 95 % | Devolución | MFE≥1R → pérdida |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| `M0 first_r=0.075` | 29828 | 75.8% | -0.151 | +0.106 | -0.958 | +0.11 | +0.35 | +0.166 | +4501.86 | -1.345 | +0.422 | 2.0% |
| `M0 first_r=0.1` | 29828 | 76.1% | -0.154 | +0.127 | -1.048 | +0.12 | +0.39 | +0.167 | +4591.00 | -1.350 | +0.446 | 1.4% |
| `M0 first_r=0.25` | 29828 | 70.7% | -0.154 | +0.269 | -1.176 | +0.23 | +0.55 | +0.173 | +4603.37 | -1.368 | +0.570 | 1.1% |
| `M0 first_r=0.5` | 29828 | 60.2% | -0.165 | +0.511 | -1.188 | +0.43 | +0.65 | +0.180 | +4916.11 | -1.387 | +0.752 | 0.2% |
| `M0 first_r=1` | 29828 | 50.3% | -0.175 | +0.816 | -1.179 | +0.69 | +0.70 | +0.186 | +5218.44 | -1.394 | +1.010 | 0.5% |
| `M1 be=0.5/0` | 29828 | 44.8% | -0.149 | +0.562 | -0.726 | +0.77 | +0.63 | +0.155 | +4454.40 | -1.357 | +0.884 | 22.0% |
| `M1 be=0.5/0.1` | 29828 | 60.9% | -0.152 | +0.401 | -1.013 | +0.40 | +0.62 | +0.157 | +4547.03 | -1.357 | +0.843 | 2.0% |
| `M1 be=1/0` | 29828 | 40.2% | -0.150 | +1.045 | -0.953 | +1.10 | +0.74 | +0.151 | +4495.76 | -1.394 | +1.058 | 21.1% |
| `M1 be=1/0.1` | 29828 | 49.2% | -0.152 | +0.843 | -1.115 | +0.76 | +0.73 | +0.152 | +4560.38 | -1.394 | +1.051 | 2.0% |
| `M1 be=1.5/0` | 29828 | 39.4% | -0.138 | +1.307 | -1.078 | +1.21 | +0.79 | +0.146 | +4143.31 | -1.415 | +1.085 | 22.8% |
| `M1 be=1.5/0.1` | 29828 | 41.7% | -0.140 | +1.230 | -1.118 | +1.10 | +0.79 | +0.147 | +4193.54 | -1.415 | +1.086 | 18.0% |

### Todo el periodo (descriptivo: incluye los tramos de ajuste)

| Variante | n | Acierto | E[R] | Gan. media | Pérd. media | Cociente | PF | Costo R | DD máx. R | CVaR 95 % | Devolución | MFE≥1R → pérdida |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| `M0 first_r=0.075` | 45814 | 74.2% | -0.160 | +0.108 | -0.931 | +0.12 | +0.33 | +0.176 | +7324.47 | -1.387 | +0.443 | 3.3% |
| `M0 first_r=0.1` | 45814 | 74.7% | -0.162 | +0.129 | -1.020 | +0.13 | +0.37 | +0.177 | +7424.23 | -1.391 | +0.467 | 3.0% |
| `M0 first_r=0.25` | 45814 | 69.9% | -0.167 | +0.269 | -1.178 | +0.23 | +0.53 | +0.184 | +7646.15 | -1.412 | +0.597 | 1.9% |
| `M0 first_r=0.5` | 45814 | 59.7% | -0.181 | +0.508 | -1.200 | +0.42 | +0.63 | +0.193 | +8300.26 | -1.434 | +0.786 | 1.0% |
| `M0 first_r=1` | 45814 | 50.0% | -0.195 | +0.801 | -1.192 | +0.67 | +0.67 | +0.200 | +8917.64 | -1.443 | +1.042 | 0.7% |
| `M1 be=0.5/0` | 45814 | 45.2% | -0.164 | +0.541 | -0.746 | +0.72 | +0.60 | +0.165 | +7520.52 | -1.392 | +0.891 | 21.0% |
| `M1 be=0.5/0.1` | 45814 | 59.7% | -0.167 | +0.399 | -1.004 | +0.40 | +0.59 | +0.167 | +7638.94 | -1.392 | +0.852 | 2.4% |
| `M1 be=1/0` | 45814 | 40.4% | -0.165 | +1.023 | -0.969 | +1.06 | +0.71 | +0.162 | +7605.15 | -1.441 | +1.069 | 20.3% |
| `M1 be=1/0.1` | 45814 | 48.6% | -0.168 | +0.839 | -1.118 | +0.75 | +0.71 | +0.163 | +7731.60 | -1.441 | +1.062 | 2.7% |
| `M1 be=1.5/0` | 45814 | 39.2% | -0.155 | +1.297 | -1.091 | +1.19 | +0.77 | +0.157 | +7184.19 | -1.468 | +1.099 | 22.9% |
| `M1 be=1.5/0.1` | 45814 | 41.2% | -0.157 | +1.227 | -1.127 | +1.09 | +0.76 | +0.157 | +7245.46 | -1.468 | +1.098 | 18.5% |

## 2. Pliegues, purga y embargo

| Pliegue | Ajuste | Prueba | Embargo (h) | Elegida en el ajuste | Motivo |
|--:|---|---|--:|---|---|
| 0 | 2023-01-11T10:00+00:00 → 2024-01-11T10:00+00:00 | 2024-01-11T10:00+00:00 → 2024-04-11T10:00+00:00 | 200 | `—` | ninguna variante factible mejora a la base formando meseta |
| 1 | 2023-04-11T10:00+00:00 → 2024-04-11T10:00+00:00 | 2024-04-11T10:00+00:00 → 2024-07-11T10:00+00:00 | 200 | `—` | ninguna variante factible mejora a la base formando meseta |
| 2 | 2023-07-11T10:00+00:00 → 2024-07-11T10:00+00:00 | 2024-07-11T10:00+00:00 → 2024-10-11T10:00+00:00 | 200 | `—` | ninguna variante factible mejora a la base formando meseta |
| 3 | 2023-10-11T10:00+00:00 → 2024-10-11T10:00+00:00 | 2024-10-11T10:00+00:00 → 2025-01-11T10:00+00:00 | 200 | `—` | ninguna variante factible mejora a la base formando meseta |
| 4 | 2024-01-11T10:00+00:00 → 2025-01-11T10:00+00:00 | 2025-01-11T10:00+00:00 → 2025-04-11T10:00+00:00 | 200 | `—` | ninguna variante factible mejora a la base formando meseta |
| 5 | 2024-04-11T10:00+00:00 → 2025-04-11T10:00+00:00 | 2025-04-11T10:00+00:00 → 2025-07-11T10:00+00:00 | 200 | `—` | ninguna variante factible mejora a la base formando meseta |
| 6 | 2024-07-11T10:00+00:00 → 2025-07-11T10:00+00:00 | 2025-07-11T10:00+00:00 → 2025-10-11T10:00+00:00 | 200 | `—` | ninguna variante factible mejora a la base formando meseta |
| 7 | 2024-10-11T10:00+00:00 → 2025-10-11T10:00+00:00 | 2025-10-11T10:00+00:00 → 2026-01-11T10:00+00:00 | 200 | `—` | ninguna variante factible mejora a la base formando meseta |
| 8 | 2025-01-11T10:00+00:00 → 2026-01-11T10:00+00:00 | 2026-01-11T10:00+00:00 → 2026-04-11T10:00+00:00 | 200 | `—` | ninguna variante factible mejora a la base formando meseta |
| 9 | 2025-04-11T10:00+00:00 → 2026-04-11T10:00+00:00 | 2026-04-11T10:00+00:00 → 2026-07-11T10:00+00:00 | 200 | `—` | ninguna variante factible mejora a la base formando meseta |

**Fugas entre tramos: 0.** Ninguna operación de un tramo de ajuste se cierra dentro de su tramo de prueba ni de su embargo (purga y embargo de E1).

Purga del primer pliegue (ejemplo): 11130 operaciones decididas en el ajuste, 10857 se conservan, 8 se cierran dentro de la prueba y 265 dentro del embargo.

## 3. Pruebas múltiples (E3)

### ΔE[R] emparejado frente a `M0 first_r=0.1`

29828 operaciones emparejadas en los tramos de prueba, 913 días de remuestreo, 5000 réplicas.

| Variante | ΔE[R] (t) | IC 95 % | p bruto | p Romano-Wolf | p Holm |
|---|--:|---|--:|--:|--:|
| `M0 first_r=0.075` | +2.27 | [+0.0004, +0.0056] | 0.0126 | 0.0570 | 0.1260 |
| `M1 be=1.5/0` | +1.16 | [-0.0110, +0.0416] | 0.1218 | 0.3223 | 1.0000 |
| `M1 be=1.5/0.1` | +1.04 | [-0.0122, +0.0391] | 0.1458 | 0.3691 | 1.0000 |
| `M1 be=0.5/0` | +0.58 | [-0.0109, +0.0194] | 0.2817 | 0.5531 | 1.0000 |
| `M1 be=1/0` | +0.32 | [-0.0185, +0.0255] | 0.3669 | 0.6607 | 1.0000 |
| `M1 be=0.5/0.1` | +0.22 | [-0.0122, +0.0151] | 0.4059 | 0.6971 | 1.0000 |
| `M1 be=1/0.1` | +0.13 | [-0.0199, +0.0223] | 0.4411 | 0.7109 | 1.0000 |
| `M0 first_r=0.25` | -0.08 | [-0.0069, +0.0062] | 0.5363 | 0.7582 | 1.0000 |
| `M0 first_r=0.5` | -1.80 | [-0.0221, +0.0007] | 0.9646 | 0.9878 | 1.0000 |
| `M0 first_r=1` | -2.44 | [-0.0389, -0.0040] | 0.9926 | 0.9926 | 1.0000 |

Romano-Wolf y Holm coinciden en todas las variantes.

### ΔE[R] emparejado frente a `M1 be=1/0.1`

29828 operaciones emparejadas en los tramos de prueba, 913 días de remuestreo, 5000 réplicas.

| Variante | ΔE[R] (t) | IC 95 % | p bruto | p Romano-Wolf | p Holm |
|---|--:|---|--:|--:|--:|
| `M1 be=1.5/0` | +2.49 | [+0.0029, +0.0254] | 0.0064 | 0.0336 | 0.0640 |
| `M1 be=1.5/0.1` | +2.24 | [+0.0015, +0.0232] | 0.0122 | 0.0646 | 0.1098 |
| `M1 be=1/0` | +1.35 | [-0.0011, +0.0056] | 0.0846 | 0.2925 | 0.6767 |
| `M1 be=0.5/0` | +0.51 | [-0.0093, +0.0156] | 0.3043 | 0.5647 | 1.0000 |
| `M0 first_r=0.075` | +0.15 | [-0.0196, +0.0231] | 0.4385 | 0.6947 | 1.0000 |
| `M1 be=0.5/0.1` | +0.03 | [-0.0131, +0.0138] | 0.4887 | 0.7355 | 1.0000 |
| `M0 first_r=0.1` | -0.13 | [-0.0220, +0.0194] | 0.5497 | 0.7403 | 1.0000 |
| `M0 first_r=0.25` | -0.16 | [-0.0213, +0.0171] | 0.5645 | 0.7403 | 1.0000 |
| `M0 first_r=0.5` | -1.46 | [-0.0278, +0.0043] | 0.9292 | 0.9660 | 1.0000 |
| `M0 first_r=1` | -4.59 | [-0.0321, -0.0129] | 1.0000 | 1.0000 | 1.0000 |

Romano-Wolf y Holm **discrepan** en `M1 be=1.5/0` (E3: se informa).

## 4. Probabilidad de sobreajuste (PBO, CSCV)

PBO = **0.46** con 8 tramos, 70 combinaciones y 11 variantes (logit mediano +0.34; degradación media +0.0132). El pre-registro pide < 0.2.

## 5. Control aleatorio

2826 ideas de `control_aleatorio`. Lo que tiene que pasar es que el R **bruto** (neto + costo) sea compatible con 0: la salida no puede volver rentables unas entradas al azar. Si el 0 no está en el IC, hay un error o anticipación.

| Variante | n | E[R] neto | Costo R | IC 95 % del bruto | ¿contiene el 0? |
|---|--:|--:|--:|---|---|
| `M0 first_r=0.075` | 2820 | -0.191 | +0.216 | [+0.0041, +0.0467] | NO |
| `M0 first_r=0.1` | 2820 | -0.191 | +0.217 | [+0.0040, +0.0470] | NO |
| `M0 first_r=0.25` | 2820 | -0.209 | +0.224 | [-0.0123, +0.0417] | sí |
| `M0 first_r=0.5` | 2820 | -0.218 | +0.232 | [-0.0191, +0.0468] | sí |
| `M0 first_r=1` | 2819 | -0.235 | +0.239 | [-0.0358, +0.0456] | sí |
| `M1 be=0.5/0` | 2820 | -0.203 | +0.199 | [-0.0383, +0.0299] | sí |
| `M1 be=0.5/0.1` | 2820 | -0.208 | +0.200 | [-0.0412, +0.0256] | sí |
| `M1 be=1/0` | 2819 | -0.197 | +0.196 | [-0.0439, +0.0403] | sí |
| `M1 be=1/0.1` | 2820 | -0.201 | +0.197 | [-0.0456, +0.0368] | sí |
| `M1 be=1.5/0` | 2819 | -0.188 | +0.191 | [-0.0403, +0.0470] | sí |
| `M1 be=1.5/0.1` | 2819 | -0.190 | +0.191 | [-0.0430, +0.0452] | sí |

## 6. Estrés de costos (E4a)

| Factor | Variante | E[R] fuera de muestra | Costo R |
|--:|---|--:|--:|
| ×1.5 | `M0 first_r=0.075` | -0.183 | +0.198 |
| ×1.5 | `M0 first_r=0.1` | -0.184 | +0.200 |
| ×1.5 | `M0 first_r=0.25` | -0.189 | +0.209 |
| ×1.5 | `M0 first_r=0.5` | -0.203 | +0.219 |
| ×1.5 | `M0 first_r=1` | -0.214 | +0.227 |
| ×1.5 | `M1 be=0.5/0` | -0.177 | +0.183 |
| ×1.5 | `M1 be=0.5/0.1` | -0.181 | +0.185 |
| ×1.5 | `M1 be=1/0` | -0.178 | +0.178 |
| ×1.5 | `M1 be=1/0.1` | -0.180 | +0.180 |
| ×1.5 | `M1 be=1.5/0` | -0.164 | +0.172 |
| ×1.5 | `M1 be=1.5/0.1` | -0.166 | +0.173 |
| ×2 | `M0 first_r=0.075` | -0.212 | +0.231 |
| ×2 | `M0 first_r=0.1` | -0.214 | +0.234 |
| ×2 | `M0 first_r=0.25` | -0.225 | +0.245 |
| ×2 | `M0 first_r=0.5` | -0.243 | +0.258 |
| ×2 | `M0 first_r=1` | -0.251 | +0.267 |
| ×2 | `M1 be=0.5/0` | -0.205 | +0.211 |
| ×2 | `M1 be=0.5/0.1` | -0.209 | +0.213 |
| ×2 | `M1 be=1/0` | -0.205 | +0.206 |
| ×2 | `M1 be=1/0.1` | -0.208 | +0.208 |
| ×2 | `M1 be=1.5/0` | -0.190 | +0.198 |
| ×2 | `M1 be=1.5/0.1` | -0.192 | +0.199 |

## Sharpe deflactado

Con 107 intentos pre-registrados:

| Variante | DSR |
|---|--:|
| `M0 first_r=0.075` | +0.000 |
| `M0 first_r=0.1` | +0.000 |
| `M0 first_r=0.25` | +0.000 |
| `M0 first_r=0.5` | +0.000 |
| `M0 first_r=1` | +0.000 |
| `M1 be=0.5/0` | +0.000 |
| `M1 be=0.5/0.1` | +0.000 |
| `M1 be=1/0` | +0.000 |
| `M1 be=1/0.1` | +0.000 |
| `M1 be=1.5/0` | +0.000 |
| `M1 be=1.5/0.1` | +0.000 |

El DSR usa TODOS los intentos de la rejilla, no solo los corridos: es lo honesto cuando la rejilla ya está pre-registrada.

## Lo que este informe NO dice

- No decide qué salida se adopta: eso es T134, con los criterios de §5.4.
- Las variantes de M2 a M8 y S1 a S3 no están implementadas (T132, T133 y T136).
- El tramo posterior a la ventana queda de reserva; la prueba definitiva es la prospectiva en papel (T135).

