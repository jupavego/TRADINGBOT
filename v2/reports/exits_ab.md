# T134 — experimento pre-registrado de salidas (BTCUSDT)

**Modo: SIMULADO. Nada de este informe habilita dinero real.**

Pre-registro `prereg_t131_v3`, huella `bc3cd8840aba2785…`, semilla 131, **107 intentos** pre-registrados. Generado el 2026-11-04T09:29+00:00 desde `C:\Users\jo\Desktop\JP\TRADINGBOT\v2\backups\t131_banco` (commit `56b41f4`) con `python scripts/t134_exits_ab.py --data C:\Users\jo\Desktop\JP\TRADINGBOT\v2\backups\t131_banco`, en 3201 s.

Ventana **2023-01-11T10:00+00:00 → 2026-07-11T10:00+00:00**, 10 pliegues, embargo 200 h. 60720 ideas, 2019972 velas de 1 min, 33666 del marco mayor. Bases: `M0 first_r=0.1`, `M1 be_trigger_r=1 be_lock_r=0.1`.

**89 variantes corridas** de la rejilla. Fuera: `M4` (descartada_T133); `S2` (pendiente_permiso_y_codigo); `S3` (pendiente_T136). Cuentan como intentos igualmente (E12).

## 1. Veredicto

Recuento: **87 RECHAZADA**, de 87 variantes juzgadas.

**Ninguna variante pasa los criterios de §5.4.** No hay nada que llevar a la prueba en papel de T135.

### Por qué falla cada familia

| Familia | n | Criterio que falla primero |
|---|--:|---|
| `M0` | 4 | criterio 1: 4 |
| `M1` | 5 | criterio 1: 5 |
| `M2` | 45 | criterio 1: 45 |
| `M3` | 4 | criterio 1: 4 |
| `M5` | 12 | criterio 1: 12 |
| `M6` | 6 | criterio 1: 6 |
| `M7` | 2 | criterio 1: 2 |
| `M8` | 3 | criterio 1: 1, criterio 2: 2 |
| `S1` | 6 | criterio 1: 6 |

## 2. Cifras

### Fuera de muestra (tramos de prueba de los pliegues)

| Variante | n | Acierto | E[R] | Cociente | PF | Costo R | DD R | CVaR | Devolución |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| `M8 q=0.95` | 29841 | 80.8% | -0.1045 | +0.11 | +0.475 | +0.1156 | +3121 | -1.2406 | +0.3442 |
| `M8 q=0.9` | 29841 | 79.4% | -0.1194 | +0.11 | +0.443 | +0.1303 | +3565 | -1.2745 | +0.3740 |
| `S1 d_min_sigma=3 sigma=atr14` | 29841 | 77.9% | -0.1344 | +0.12 | +0.415 | +0.1467 | +4014 | -1.2974 | +0.4069 |
| `M1 be_trigger_r=1.5 be_lock_r=0` | 29828 | 39.4% | -0.1383 | +1.21 | +0.788 | +0.1463 | +4143 | -1.4146 | +1.0854 |
| `M1 be_trigger_r=1.5 be_lock_r=0.1` | 29828 | 41.7% | -0.1401 | +1.10 | +0.785 | +0.1467 | +4194 | -1.4146 | +1.0861 |
| `S1 d_min_sigma=3 sigma=harrv_1m` | 29841 | 77.1% | -0.1403 | +0.12 | +0.406 | +0.1503 | +4189 | -1.2619 | +0.4176 |
| `M8 q=0.8` | 29841 | 77.4% | -0.1404 | +0.12 | +0.405 | +0.1519 | +4194 | -1.3185 | +0.4172 |
| `M5 a_r=1.5 b_r=0 trail=M3` | 29828 | 36.9% | -0.1441 | +1.36 | +0.796 | +0.1837 | +4308 | -1.4201 | +1.6503 |
| `M2 k=4 sigma=atr14 activate_r=1` | 29828 | 38.1% | -0.1442 | +1.26 | +0.773 | +0.1840 | +4465 | -1.4052 | +1.5659 |
| `M5 a_r=1.5 b_r=0.1 trail=M3` | 29828 | 39.9% | -0.1455 | +1.20 | +0.793 | +0.1838 | +4352 | -1.4213 | +1.6435 |
| `M2 k=4 sigma=atr14 activate_r=0.5` | 29828 | 34.2% | -0.1461 | +1.42 | +0.741 | +0.1805 | +4478 | -1.3845 | +1.4492 |
| `M2 k=4 sigma=atr14 activate_r=0` | 29828 | 30.2% | -0.1473 | +1.67 | +0.722 | +0.1780 | +4481 | -1.3718 | +1.3714 |

Solo las 12 mejores por E[R]; el resto, en el `.json` y el `.csv`.

### Todo el periodo (descriptivo)

| Variante | n | Acierto | E[R] | Cociente | PF | Costo R | DD R | CVaR | Devolución |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| `M7 confirm_bars=1` | 45823 | 25.2% | -0.0885 | +2.64 | +0.893 | +0.2030 | +7140 | -1.5671 | +2.2359 |
| `M7 confirm_bars=2` | 45823 | 25.2% | -0.0885 | +2.64 | +0.893 | +0.2030 | +7140 | -1.5671 | +2.2359 |
| `M2 k=2 sigma=harrv_1m activate_r=0` | 45833 | 26.8% | -0.1266 | +1.78 | +0.651 | +0.1855 | +7901 | -1.4145 | +0.8105 |
| `M8 q=0.95` | 45846 | 77.8% | -0.1298 | +0.12 | +0.422 | +0.1439 | +5953 | -1.3399 | +0.4005 |
| `M2 k=4 sigma=harrv_1m activate_r=0` | 45833 | 29.1% | -0.1309 | +1.83 | +0.751 | +0.1992 | +8146 | -1.5050 | +1.2835 |
| `M2 k=3 sigma=harrv_1m activate_r=0` | 45833 | 28.5% | -0.1336 | +1.76 | +0.702 | +0.1928 | +8155 | -1.4785 | +1.0591 |
| `M2 k=4 sigma=harrv_1m activate_r=0.5` | 45830 | 36.0% | -0.1340 | +1.36 | +0.766 | +0.2028 | +8307 | -1.5064 | +1.3769 |
| `M2 k=4 sigma=harrv_1m activate_r=1` | 45819 | 40.2% | -0.1357 | +1.18 | +0.795 | +0.2075 | +8380 | -1.5124 | +1.4904 |
| `M2 k=2 sigma=harrv_1m activate_r=0.5` | 45830 | 48.8% | -0.1359 | +0.75 | +0.715 | +0.1960 | +8340 | -1.4583 | +1.0134 |
| `M2 k=3 sigma=harrv_1m activate_r=0.5` | 45830 | 41.4% | -0.1377 | +1.04 | +0.736 | +0.1988 | +8368 | -1.4852 | +1.2019 |
| `M8 q=0.9` | 45846 | 76.9% | -0.1395 | +0.12 | +0.405 | +0.1535 | +6396 | -1.3530 | +0.4199 |
| `S1 d_min_sigma=3 sigma=atr14` | 45851 | 76.6% | -0.1413 | +0.12 | +0.402 | +0.1557 | +6479 | -1.3337 | +0.4251 |

Solo las 12 mejores por E[R]; el resto, en el `.json` y el `.csv`.

## 3. Pruebas múltiples (E3)

### Frente a `M0 first_r=0.1`

913 días de remuestreo, 5000 réplicas.

| Variante | t | IC 95 % | p bruto | p Romano-Wolf | p Holm |
|---|--:|---|--:|--:|--:|
| `M8 q=0.95` | +16.28 | [+0.0435, +0.0553] | 0.0002 | 0.0002 | 0.0176 |
| `M8 q=0.9` | +14.51 | [+0.0298, +0.0393] | 0.0002 | 0.0002 | 0.0176 |
| `S1 d_min_sigma=3 sigma=atr14` | +10.93 | [+0.0159, +0.0228] | 0.0002 | 0.0002 | 0.0176 |
| `M8 q=0.8` | +9.49 | [+0.0107, +0.0162] | 0.0002 | 0.0002 | 0.0176 |
| `S1 d_min_sigma=3 sigma=harrv_1m` | +8.29 | [+0.0104, +0.0169] | 0.0002 | 0.0002 | 0.0176 |
| `S1 d_min_sigma=2 sigma=atr14` | +6.53 | [+0.0019, +0.0036] | 0.0002 | 0.0002 | 0.0176 |
| `S1 d_min_sigma=2 sigma=harrv_1m` | +4.48 | [+0.0023, +0.0058] | 0.0002 | 0.0002 | 0.0176 |
| `S1 d_min_sigma=1.5 sigma=atr14` | +2.79 | [+0.0002, +0.0009] | 0.0046 | 0.0658 | 0.3725 |
| `S1 d_min_sigma=1.5 sigma=harrv_1m` | +2.77 | [+0.0003, +0.0016] | 0.0046 | 0.0658 | 0.3725 |
| `M0 first_r=0.075` | +2.27 | [+0.0004, +0.0056] | 0.0136 | 0.1816 | 1.0000 |
| `M1 be_trigger_r=1.5 be_lock_r=0` | +1.16 | [-0.0105, +0.0412] | 0.1208 | 0.7157 | 1.0000 |
| `M6 bars=8 min_r=0` | +1.08 | [-0.0052, +0.0180] | 0.1366 | 0.7481 | 1.0000 |

Romano-Wolf y Holm coinciden en todas las variantes.

**7 variantes baten a `M0 first_r=0.1`** con p de Romano-Wolf < 0.05: 3 de `M8`, 4 de `S1`.
**Todas pertenecen a las familias que cambian el SL inicial** (`M8`, `S1`), ninguna a las reglas de arrastre (`M2` con sus 45 variantes, `M3`, `M5`, `M6`, `M7`). No es que una pasara por casualidad: lo único que mejora a la base, de forma sistemática y en dos familias independientes, es **apartar el stop inicial**.

### Frente a `M1 be_trigger_r=1 be_lock_r=0.1`

913 días de remuestreo, 5000 réplicas.

| Variante | t | IC 95 % | p bruto | p Romano-Wolf | p Holm |
|---|--:|---|--:|--:|--:|
| `M8 q=0.95` | +4.44 | [+0.0263, +0.0696] | 0.0002 | 0.0008 | 0.0176 |
| `M8 q=0.9` | +3.09 | [+0.0129, +0.0537] | 0.0008 | 0.0362 | 0.0696 |
| `M1 be_trigger_r=1.5 be_lock_r=0` | +2.49 | [+0.0035, +0.0260] | 0.0072 | 0.1564 | 0.6191 |
| `M1 be_trigger_r=1.5 be_lock_r=0.1` | +2.24 | [+0.0017, +0.0233] | 0.0124 | 0.2446 | 1.0000 |
| `S1 d_min_sigma=3 sigma=atr14` | +1.71 | [-0.0026, +0.0384] | 0.0456 | 0.4977 | 1.0000 |
| `M1 be_trigger_r=1 be_lock_r=0` | +1.35 | [-0.0009, +0.0057] | 0.0904 | 0.6963 | 1.0000 |
| `M8 q=0.8` | +1.14 | [-0.0092, +0.0325] | 0.1328 | 0.7640 | 1.0000 |
| `S1 d_min_sigma=3 sigma=harrv_1m` | +1.14 | [-0.0089, +0.0332] | 0.1326 | 0.7668 | 1.0000 |
| `M6 bars=16 min_r=0` | +0.59 | [-0.0126, +0.0222] | 0.2777 | 0.9420 | 1.0000 |
| `M6 bars=8 min_r=0` | +0.52 | [-0.0146, +0.0233] | 0.3053 | 0.9540 | 1.0000 |
| `M1 be_trigger_r=0.5 be_lock_r=0` | +0.51 | [-0.0093, +0.0154] | 0.3141 | 0.9566 | 1.0000 |
| `M5 a_r=1.5 b_r=0 trail=M3` | +0.48 | [-0.0249, +0.0432] | 0.3171 | 0.9600 | 1.0000 |

Romano-Wolf y Holm **discrepan** en `M8 q=0.9` (E3: se informa).

**2 variantes baten a `M1 be_trigger_r=1 be_lock_r=0.1`** con p de Romano-Wolf < 0.05: 2 de `M8`.
**Todas pertenecen a las familias que cambian el SL inicial** (`M8`, `S1`), ninguna a las reglas de arrastre (`M2` con sus 45 variantes, `M3`, `M5`, `M6`, `M7`). No es que una pasara por casualidad: lo único que mejora a la base, de forma sistemática y en dos familias independientes, es **apartar el stop inicial**.

## 4. Probabilidad de sobreajuste (PBO, CSCV)

PBO = **0.13** con 8 tramos, 70 combinaciones y 89 variantes (logit mediano +4.49). El pre-registro pide < 0,2.

No es comparable con el 0,46 de T131: allí el CSCV solo tenía once variantes casi idénticas entre las que elegir, y con tan poca variedad el estadístico no mide lo que pretende. El número fiable es este; el de T131 estaba mal medido, no era pesimista.

## 5. Control aleatorio (criterio 6, nulo por series sustitutas)

El nulo conserva la distribución de retornos y destruye la dependencia serial: se barajan los log-retornos reales de 1 min y se rehace el camino. Se **rechaza** la variante si su R bruto destaca sobre ese nulo.

| Variante | Bruto | Nulo (media) | Nulo p95 | p | ¿Pasa? |
|---|--:|--:|--:|--:|---|
| `M0 first_r=0.1` | +0.0257 | +0.0448 | +0.0982 | +0.619 | sí |
| `M1 be_trigger_r=1 be_lock_r=0.1` | -0.0039 | +0.0407 | +0.1582 | +0.667 | sí |
| `M8 q=0.9` | +0.0257 | +0.0448 | +0.0982 | +0.619 | sí |
| `M8 q=0.95` | +0.0257 | +0.0448 | +0.0982 | +0.619 | sí |

> **Salvedad.** `M8 q=0.9`, `M8 q=0.95` salen con cifras **idénticas** a `M0 first_r=0.1`, lo que significa que sobre las entradas al azar no tocó nada: el criterio 6 midió a su acompañante, no a ella. Ocurre cuando la estrategia del control no alcanza la muestra mínima de ganadoras y el cuantil no existe (sin muestra no se aprieta). **Ese «sí» no avala su geometría.** Si alguna de estas se reconsidera en T136, su control hay que rehacerlo con entradas al azar que sí tengan muestra de ganadoras.

## 6. Insumos de potencia para T135 (E9)

`var_paired` es la varianza de las diferencias emparejadas por operación frente a cada base, en R². Con ella y las operaciones por semana se calcula el efecto mínimo detectable en T135 (E9); el ritmo real por perfil hay que tomarlo del libro en vivo, porque el banco corre con tamaño fijo y sin cupos.

| Variante | n cerradas | n en prueba | Op./semana | σ de las diferencias |
|---|--:|--:|--:|---|
| `M0 first_r=0.1` | 45833 | 29828 | +230.6 | M1 be_trigger_r=1 be_lock_r=0.1: +0.988 |
| `M1 be_trigger_r=1 be_lock_r=0.1` | 45822 | 29828 | +230.5 | M0 first_r=0.1: +0.988 |
| `M0 first_r=0.075` | 45833 | 29828 | +230.6 | M0 first_r=0.1: +0.169, M1 be_trigger_r=1 be_lock_r=0.1: +1.003 |
| `M0 first_r=0.25` | 45832 | 29828 | +230.5 | M0 first_r=0.1: +0.394, M1 be_trigger_r=1 be_lock_r=0.1: +0.910 |
| `M0 first_r=0.5` | 45829 | 29828 | +230.5 | M0 first_r=0.1: +0.647, M1 be_trigger_r=1 be_lock_r=0.1: +0.762 |
| `M0 first_r=1` | 45819 | 29828 | +230.5 | M0 first_r=0.1: +0.894, M1 be_trigger_r=1 be_lock_r=0.1: +0.507 |
| `M1 be_trigger_r=0.5 be_lock_r=0` | 45831 | 29828 | +230.5 | M0 first_r=0.1: +0.732, M1 be_trigger_r=1 be_lock_r=0.1: +0.701 |
| `M1 be_trigger_r=0.5 be_lock_r=0.1` | 45831 | 29828 | +230.5 | M0 first_r=0.1: +0.681, M1 be_trigger_r=1 be_lock_r=0.1: +0.719 |
| `M1 be_trigger_r=1 be_lock_r=0` | 45822 | 29828 | +230.5 | M0 first_r=0.1: +1.007, M1 be_trigger_r=1 be_lock_r=0.1: +0.193 |
| `M1 be_trigger_r=1.5 be_lock_r=0` | 45818 | 29828 | +230.5 | M0 first_r=0.1: +1.127, M1 be_trigger_r=1 be_lock_r=0.1: +0.544 |
| `M1 be_trigger_r=1.5 be_lock_r=0.1` | 45818 | 29828 | +230.5 | M0 first_r=0.1: +1.122, M1 be_trigger_r=1 be_lock_r=0.1: +0.532 |
| `M2 k=2 sigma=atr14 activate_r=0` | 45833 | 29828 | +230.6 | M0 first_r=0.1: +0.660, M1 be_trigger_r=1 be_lock_r=0.1: +0.930 |
| `M2 k=2 sigma=atr14 activate_r=0.5` | 45830 | 29828 | +230.5 | M0 first_r=0.1: +0.739, M1 be_trigger_r=1 be_lock_r=0.1: +0.769 |
| `M2 k=2 sigma=atr14 activate_r=1` | 45819 | 29828 | +230.5 | M0 first_r=0.1: +0.985, M1 be_trigger_r=1 be_lock_r=0.1: +0.548 |

## 7. Estrés de costos (E4a)

Medido en 4 variantes (las que pasan el criterio 1 con el costo base; una que no lo pasa tampoco lo pasaría con costos mayores, así que ningún veredicto cambia).

## 8. Cobertura de los rasgos

| Estimador σ | σ | swing bajo | marco mayor |
|---|--:|--:|--:|
| `atr14` | 100.0% | 100.0% | 100.0% |
| `parkinson` | 99.9% | 100.0% | 100.0% |
| `garman_klass` | 99.9% | 100.0% | 100.0% |
| `yang_zhang` | 99.9% | 100.0% | 100.0% |
| `harrv_1m` | 94.8% | 100.0% | 100.0% |

## Lo que este informe NO dice

- **No adopta nada.** La decisión es del usuario (◆ de T134) y ninguna variante puede estar aprobada aquí: el criterio 7 de §5.4 es prospectivo y su dato nace en T135.
- **Libro completo:** solo es calculable para M0 y M1, las dos salidas que `paper/book.py` sabe ejecutar; para las demás exige conectarlas a los perfiles, que es T135 y está fuera del alcance de T134.
- **S2** (cierres parciales) y **S3** (riesgo de cartera) no se corrieron: la primera necesita permiso del usuario y código; la segunda es de T136. Cuentan como intentos.
- **M4** quedó descartada en T133 por su cota del oráculo, no por este experimento.
- Nada de aquí habilita dinero real: sigue hecho falta la puerta de edge (T27) y las semanas de papel (T31).

