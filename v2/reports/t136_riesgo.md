# T136 — Riesgo por operación con costos y control de drawdown gradual

Copia `C:\Users\jo\Desktop\JP\TRADINGBOT\v2\backups\t131_banco` · BTCUSDT · salida `M0 first_r=0.1` (la vigente) · pre-registro `prereg_t131_v3` (`bc3cd8840aba…`) · commit `2f2010d` · 2026-11-04T18:19+00:00 · 65.4 s

Ventana 2023-01-11T10:00+00:00 → 2026-08-16T00:00+00:00 · 10 pliegues · embargo 200.0 h · 45833 operaciones cerradas, **29828 fuera de muestra** (las únicas que se usan aquí).

Nada de esto cambia a ningún perfil: todos los interruptores nuevos (`risk_includes_costs`, `dd_steps`, `cvar_limit_r`, Kelly) salen **apagados**. Encenderlos es decisión ◆ del usuario, y esta medición es para tomarla.

## 1. El costo que el riesgo no incluye

Costo **ex ante** medio (el que el perfil estima al decidir, y con el que veta): **0.1734 R** (mediana 0.1484, p90 0.2952). Costo **realizado** medio 0.1668 R.

Dimensionando como hoy, al saltar el SL inicial no se pierde el riesgo declarado sino **×1.1734**: un perfil que dice arriesgar 0,5 % arriesga 0.587 %. Incluir el costo en el presupuesto multiplica la cantidad por **0.8522** y deja la pérdida al stop exactamente en lo declarado.

| Marco | n | Costo ex ante medio | Costo realizado medio | Se arriesga de más |
|---|--:|--:|--:|--:|
| 1h | 28689 | 0.1767 R | 0.1699 R | 17.7 % |
| 4h | 1139 | 0.0900 R | 0.0897 R | 9.0 % |

**Esta cifra es una cota por abajo de lo que pasa en vivo.** El banco de T131 se pre-registró con marcos de decisión 1 h y 4 h, así que aquí no hay ni una operación de **15 m**, que es el marco donde el stop está más cerca y el costo pesa más (T48b lo midió en 0,48 R por operación con 4 034 ops). Los perfiles sí operan 15 m en vivo, de modo que el exceso real sobre el riesgo declarado es mayor que el medido aquí. Medirlo exige un banco con 15 m, que es una versión nueva del pre-registro.

## 2. El tope de costo en R (rejilla de §4.5)

Con el costo **ex ante**, que es el que decide el veto. «Entra» es la fracción de operaciones fuera de muestra que el tope dejaría pasar.

| Tope | Entra | n | E[R] | Acierto | PF | CVaR 95 % |
|--:|--:|--:|--:|--:|--:|--:|
| 0.08 R | 10.8 % | 3216 | -0.0557 | 85.0 % | 0.632 | -1.1337 |
| 0.10 R | 21.6 % | 6434 | -0.0650 | 84.1 % | 0.596 | -1.1429 |
| 0.12 R | 33.5 % | 9980 | -0.0798 | 82.7 % | 0.546 | -1.1620 |
| 0.15 R | 50.9 % | 15195 | -0.0977 | 80.8 % | 0.492 | -1.1845 |
| 0.20 R | 72.3 % | 21561 | -0.1183 | 78.9 % | 0.444 | -1.2176 |

Topes de hoy por perfil: `conservador` 0.12 R · `moderado` 0.15 R · `agresivo` 0.20 R · `ppp_btcusdt` 0.15 R.

## 3. Frenos: todo o nada frente a gradual (rejilla pre-registrada de S3)

Valores pre-registrados: `dd_brake` [0.05, 0.08, 0.1], `cvar_limit_r` [0.3, 0.5], `vol_target` [0.5, 1.0]. El freno gradual no tiene rejilla propia, así que se construye desde la que hay: último tramo en el `dd_brake` pre-registrado y tramo intermedio en su mitad con el riesgo a la mitad. Se simula el capital con los mismos `caps` que corren en el libro.

### `conservador` (riesgo 0.50% por operación)

| Caso | Tomadas | Frenadas | Recortadas | Capital final | Retorno | DD máx. | CVaR 95 % | ¿ruina? |
|---|--:|--:|--:|--:|--:|--:|--:|---|
| hoy (sin frenos) | 29828 | 0 | 0 | 0 | -100.0 % | 100.0 % | -1.3499 | **sí** |
| todo o nada dd=5% | 18944 | 10884 | 0 | 0 | -100.0 % | 100.0 % | -1.3398 | **sí** |
| gradual dd=5% | 109 | 29719 | 103 | 9,475 | -5.3 % | 5.3 % | -1.2262 | no |
| todo o nada dd=8% | 21924 | 7904 | 0 | 0 | -100.0 % | 100.0 % | -1.3401 | **sí** |
| gradual dd=8% | 139 | 29689 | 126 | 9,178 | -8.2 % | 8.2 % | -1.2193 | no |
| todo o nada dd=10% | 23320 | 6508 | 0 | 0 | -100.0 % | 100.0 % | -1.3407 | **sí** |
| gradual dd=10% | 147 | 29681 | 131 | 8,973 | -10.3 % | 10.3 % | -1.2044 | no |
| CVaR ≥ -0.30 R | 29828 | 0 | 29798 | 0 | -100.0 % | 100.0 % | -0.6786 | **sí** |
| CVaR ≥ -0.50 R | 29828 | 0 | 29798 | 0 | -100.0 % | 100.0 % | -0.6786 | **sí** |

### `moderado` (riesgo 1.00% por operación)

| Caso | Tomadas | Frenadas | Recortadas | Capital final | Retorno | DD máx. | CVaR 95 % | ¿ruina? |
|---|--:|--:|--:|--:|--:|--:|--:|---|
| hoy (sin frenos) | 29828 | 0 | 0 | 0 | -100.0 % | 100.0 % | -1.3499 | **sí** |
| todo o nada dd=5% | 14920 | 14908 | 0 | 0 | -100.0 % | 100.0 % | -1.3325 | **sí** |
| gradual dd=5% | 7 | 29821 | 3 | 9,456 | -5.4 % | 5.4 % | — | no |
| todo o nada dd=8% | 17663 | 12165 | 0 | 0 | -100.0 % | 100.0 % | -1.3382 | **sí** |
| gradual dd=8% | 31 | 29797 | 26 | 9,197 | -8.0 % | 8.0 % | -1.4769 | no |
| todo o nada dd=10% | 19109 | 10719 | 0 | 0 | -100.0 % | 100.0 % | -1.3408 | **sí** |
| gradual dd=10% | 109 | 29719 | 103 | 8,974 | -10.3 % | 10.3 % | -1.2262 | no |
| CVaR ≥ -0.30 R | 29828 | 0 | 29798 | 0 | -100.0 % | 100.0 % | -0.6786 | **sí** |
| CVaR ≥ -0.50 R | 29828 | 0 | 29798 | 0 | -100.0 % | 100.0 % | -0.6786 | **sí** |

### `agresivo` (riesgo 2.00% por operación)

| Caso | Tomadas | Frenadas | Recortadas | Capital final | Retorno | DD máx. | CVaR 95 % | ¿ruina? |
|---|--:|--:|--:|--:|--:|--:|--:|---|
| hoy (sin frenos) | 29828 | 0 | 0 | 0 | -100.0 % | 100.0 % | -1.3499 | **sí** |
| todo o nada dd=5% | 10546 | 19282 | 0 | 0 | -100.0 % | 100.0 % | -1.3113 | **sí** |
| gradual dd=5% | 4 | 29824 | 1 | 9,403 | -6.0 % | 6.0 % | — | no |
| todo o nada dd=8% | 13341 | 16487 | 0 | 0 | -100.0 % | 100.0 % | -1.3280 | **sí** |
| gradual dd=8% | 6 | 29822 | 3 | 9,182 | -8.2 % | 8.2 % | — | no |
| todo o nada dd=10% | 14981 | 14847 | 0 | 0 | -100.0 % | 100.0 % | -1.3331 | **sí** |
| gradual dd=10% | 7 | 29821 | 3 | 8,937 | -10.6 % | 10.6 % | — | no |
| CVaR ≥ -0.30 R | 29828 | 0 | 29798 | 0 | -100.0 % | 100.0 % | -0.6786 | **sí** |
| CVaR ≥ -0.50 R | 29828 | 0 | 29798 | 0 | -100.0 % | 100.0 % | -0.6786 | **sí** |

### `ppp_btcusdt` (riesgo 0.50% por operación)

| Caso | Tomadas | Frenadas | Recortadas | Capital final | Retorno | DD máx. | CVaR 95 % | ¿ruina? |
|---|--:|--:|--:|--:|--:|--:|--:|---|
| hoy (sin frenos) | 29828 | 0 | 0 | 0 | -100.0 % | 100.0 % | -1.3499 | **sí** |
| todo o nada dd=5% | 18944 | 10884 | 0 | 0 | -100.0 % | 100.0 % | -1.3398 | **sí** |
| gradual dd=5% | 109 | 29719 | 103 | 9,475 | -5.3 % | 5.3 % | -1.2262 | no |
| todo o nada dd=8% | 21924 | 7904 | 0 | 0 | -100.0 % | 100.0 % | -1.3401 | **sí** |
| gradual dd=8% | 139 | 29689 | 126 | 9,178 | -8.2 % | 8.2 % | -1.2193 | no |
| todo o nada dd=10% | 23320 | 6508 | 0 | 0 | -100.0 % | 100.0 % | -1.3407 | **sí** |
| gradual dd=10% | 147 | 29681 | 131 | 8,973 | -10.3 % | 10.3 % | -1.2044 | no |
| CVaR ≥ -0.30 R | 29828 | 0 | 29798 | 0 | -100.0 % | 100.0 % | -0.6786 | **sí** |
| CVaR ≥ -0.50 R | 29828 | 0 | 29798 | 0 | -100.0 % | 100.0 % | -0.6786 | **sí** |

### Pliegue a pliegue (tres meses cada uno, capital nuevo)

De corrido, 3,5 años de un sistema con E[R] < 0 arruinan la cuenta en **cualquier** configuración, así que la tabla de arriba no distingue entre frenos: lo único que evita la ruina es dejar de operar. Por pliegue sí se ve qué hace cada uno.

#### `conservador`

| Caso | Pliegues | Retorno mediano | Peor pliegue | DD mediano | Tomadas (mediana) | Pliegues arruinados |
|---|--:|--:|--:|--:|--:|--:|
| hoy (sin frenos) | 10 | -89.2 % | -94.6 % | 89.2 % | 2883 | 0 |
| todo o nada dd=5% | 10 | -72.7 % | -77.8 % | 72.9 % | 1877 | 0 |
| gradual dd=5% | 10 | -4.9 % | -5.3 % | 5.2 % | 68 | 0 |
| todo o nada dd=8% | 10 | -78.4 % | -83.8 % | 78.5 % | 2212 | 0 |
| gradual dd=8% | 10 | -7.9 % | -8.2 % | 8.2 % | 112 | 0 |
| todo o nada dd=10% | 10 | -82.1 % | -86.8 % | 82.2 % | 2309 | 0 |
| gradual dd=10% | 10 | -9.9 % | -10.3 % | 10.1 % | 142 | 0 |
| CVaR ≥ -0.30 R | 10 | -68.2 % | -76.8 % | 68.2 % | 2883 | 0 |
| CVaR ≥ -0.50 R | 10 | -68.2 % | -76.8 % | 68.2 % | 2883 | 0 |

#### `moderado`

| Caso | Pliegues | Retorno mediano | Peor pliegue | DD mediano | Tomadas (mediana) | Pliegues arruinados |
|---|--:|--:|--:|--:|--:|--:|
| hoy (sin frenos) | 10 | -98.9 % | -99.7 % | 98.9 % | 2883 | 4 |
| todo o nada dd=5% | 10 | -80.1 % | -86.5 % | 80.3 % | 1531 | 0 |
| gradual dd=5% | 10 | -4.8 % | -5.4 % | 5.1 % | 22 | 0 |
| todo o nada dd=8% | 10 | -89.9 % | -92.4 % | 90.0 % | 1764 | 0 |
| gradual dd=8% | 10 | -7.7 % | -8.4 % | 8.2 % | 46 | 0 |
| todo o nada dd=10% | 10 | -93.2 % | -95.2 % | 93.3 % | 1906 | 0 |
| gradual dd=10% | 10 | -9.8 % | -10.3 % | 10.3 % | 70 | 0 |
| CVaR ≥ -0.30 R | 10 | -89.9 % | -94.7 % | 90.0 % | 2883 | 0 |
| CVaR ≥ -0.50 R | 10 | -89.9 % | -94.7 % | 90.0 % | 2883 | 0 |

#### `agresivo`

| Caso | Pliegues | Retorno mediano | Peor pliegue | DD mediano | Tomadas (mediana) | Pliegues arruinados |
|---|--:|--:|--:|--:|--:|--:|
| hoy (sin frenos) | 10 | -100.0 % | -100.0 % | 100.0 % | 2883 | 10 |
| todo o nada dd=5% | 10 | -85.4 % | -91.1 % | 85.7 % | 1060 | 0 |
| gradual dd=5% | 10 | -4.4 % | -6.0 % | 5.4 % | 10 | 0 |
| todo o nada dd=8% | 10 | -93.8 % | -97.0 % | 94.1 % | 1366 | 0 |
| gradual dd=8% | 10 | -7.6 % | -8.5 % | 8.4 % | 17 | 0 |
| todo o nada dd=10% | 10 | -96.5 % | -98.4 % | 96.6 % | 1534 | 0 |
| gradual dd=10% | 10 | -9.7 % | -11.0 % | 10.6 % | 23 | 0 |
| CVaR ≥ -0.30 R | 10 | -99.0 % | -99.7 % | 99.0 % | 2883 | 5 |
| CVaR ≥ -0.50 R | 10 | -99.0 % | -99.7 % | 99.0 % | 2883 | 5 |

#### `ppp_btcusdt`

| Caso | Pliegues | Retorno mediano | Peor pliegue | DD mediano | Tomadas (mediana) | Pliegues arruinados |
|---|--:|--:|--:|--:|--:|--:|
| hoy (sin frenos) | 10 | -89.2 % | -94.6 % | 89.2 % | 2883 | 0 |
| todo o nada dd=5% | 10 | -72.7 % | -77.8 % | 72.9 % | 1877 | 0 |
| gradual dd=5% | 10 | -4.9 % | -5.3 % | 5.2 % | 68 | 0 |
| todo o nada dd=8% | 10 | -78.4 % | -83.8 % | 78.5 % | 2212 | 0 |
| gradual dd=8% | 10 | -7.9 % | -8.2 % | 8.2 % | 112 | 0 |
| todo o nada dd=10% | 10 | -82.1 % | -86.8 % | 82.2 % | 2309 | 0 |
| gradual dd=10% | 10 | -9.9 % | -10.3 % | 10.1 % | 142 | 0 |
| CVaR ≥ -0.30 R | 10 | -68.2 % | -76.8 % | 68.2 % | 2883 | 0 |
| CVaR ≥ -0.50 R | 10 | -68.2 % | -76.8 % | 68.2 % | 2883 | 0 |

**Los límites de CVaR pre-registrados son inalcanzables.** El CVaR 95 % real de la salida vigente es -1.3499 R y la rejilla pide -0.30, -0.50 R, así que el límite está activo permanentemente y recorta casi todas las entradas: no es un control de cola, es un recorte fijo del tamaño. Se informa tal como se pre-registró; cambiarlo exige una **versión nueva del pre-registro** (E12), no un ajuste aquí.

## 4. Kelly fraccionado sobre el límite inferior del IC (E10)

Evidencia fuera de muestra: n = 29828, E[R] = -0.1538 R, error estándar agrupado por día 0.0052, E[R²] = 0.3203. Límite inferior con z = 1.96: **-0.1640 R**.

Fracción de Kelly (25% de Kelly): **0.0000** → riesgo por operación **0.0000%** para todos los perfiles.

Es el resultado correcto y es exactamente lo que la fase 22 ha demostrado: **sin ventaja, no hay tamaño.** Por eso se entrega apagado: encenderlo hoy dejaría a los perfiles sin abrir una sola operación y pararía la corrida de T31 y el A/B de T130.

## 5. Comprobación del ES por pliegue (E12, Acerbi y Székely)

Se estima VaR y ES 95 % en el tramo de **ajuste** y se contrasta con la cola del tramo de **prueba**. Z2 negativo = la cola real es peor que la prevista. El nulo es un remuestreo por bloques de día del propio tramo de ajuste, no la distribución predictiva del artículo: es menos exigente y se dice.

| Pliegue | Prueba desde | n ajuste | n prueba | ES ajuste | ES prueba | Z2 | p | Veredicto |
|--:|---|--:|--:|--:|--:|--:|--:|---|
| 0 | 2024-01-11 | 10857 | 2890 | -1.4636 | -1.2825 | +0.796 | 1.0000 | el ES aguanta |
| 1 | 2024-04-11 | 11033 | 2862 | -1.4534 | -1.3591 | +0.357 | 1.0000 | el ES aguanta |
| 2 | 2024-07-11 | 11063 | 2830 | -1.4522 | -1.2913 | +0.654 | 1.0000 | el ES aguanta |
| 3 | 2024-10-11 | 11242 | 3031 | -1.3299 | -1.3034 | +0.145 | 0.9612 | el ES aguanta |
| 4 | 2025-01-11 | 11340 | 2925 | -1.3101 | -1.3038 | -0.013 | 0.4455 | el ES aguanta |
| 5 | 2025-04-11 | 11383 | 2876 | -1.3173 | -1.3989 | -0.792 | 0.0002 | el ES se queda corto |
| 6 | 2025-07-11 | 11397 | 2856 | -1.3198 | -1.4312 | -1.242 | 0.0002 | el ES se queda corto |
| 7 | 2025-10-11 | 11393 | 2860 | -1.3688 | -1.3830 | +0.009 | 0.5313 | el ES aguanta |
| 8 | 2026-01-11 | 11262 | 3026 | -1.3821 | -1.3658 | +0.139 | 0.9436 | el ES aguanta |
| 9 | 2026-04-11 | 11290 | 3672 | -1.3976 | -1.3241 | +0.394 | 1.0000 | el ES aguanta |

Pliegues en los que el ES se queda corto: **2 de 10**.

## 6. Tamaño por volatilidad objetivo (entregable 3, opcional)

Con la σ versionada de T132 (`harrv_1m`), cobertura 94.8 %. Operaciones con σ: 29828 · σ relativa mediana 0.00247.

| Caso | Peso mediano | E[R] | Desv. típica de R | CVaR 95 % |
|---|--:|--:|--:|--:|
| sin escalar | 1,0 | -0.1538 | 0.5446 | -1.3499 |
| objetivo 0.5 (saturado 100.0 %) | 4.00 | -0.6153 | 2.1785 | -5.3998 |
| objetivo 1 (saturado 100.0 %) | 4.00 | -0.6153 | 2.1785 | -5.3998 |
| objetivo mediana (saturado 0.0 %) | 1.00 | -0.1581 | 0.5619 | -1.5669 |

**Los objetivos pre-registrados no están en las unidades de esta σ.** 0.5, 1 dejan el multiplicador en el tope en más del 90 % de las operaciones (σ relativa por vela, mediana 0.00247), así que como están escritos no miden nada. La fila `mediana` es el único objetivo sin parámetro libre: la σ mediana de la propia muestra. Corregir las unidades exige una **versión nueva del pre-registro**, no un ajuste aquí (E12).

## Lo que esto no es

- No elige ninguna salida: eso lo cerró T134 (87 de 87 rechazadas).
- No habilita dinero real ni toca la corrida en vivo.
- El tamaño por volatilidad objetivo es una **medición**: aplicarlo exige la misma σ en el stop y en el tamaño (E11), y el stop sigue siendo el de la escalera.
