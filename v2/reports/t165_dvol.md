# T165 — DVOL de Deribit y prima de varianza en la varianza diaria de BTCUSDT

**Modo: SIMULADO.** Esto mide; no toca el forecaster en vivo, ni las bandas dibujadas, ni
`regime`. Nada se adopta antes del cierre de T31 (2026-11-27).

- **Pre-registro:** `PLAN/notas/T165_preregistro.md`, commit `5f8ba0f`, **anterior a cualquier
  resultado**. Lo único mirado antes de fijarlo fue dónde empieza la historia pública del DVOL.
- **Medición:** `python scripts/t165_dvol.py --data <banco t139> --dvol <almacén>`, por la cola
  (trabajos `t165` y `t165b`). Cifras completas en `reports/t165_dvol.json`.
- **Referencia a batir:** **M1, el Log-HAR-RV que ganó T162**, no el GARCH fijo del cono.

## Veredicto

**A2 (HAR-IV con la pendiente del DVOL) pasa las tres condiciones pre-registradas.** Baja la QLIKE
un **6,7 %** frente a M1 (IC 95 % −0,032…−0,010, p de Holm 0,0006), es **el único que sobrevive al
MCS** (M1 queda fuera, p 0,004) y mantiene la cobertura del 80 % con ACI (80,2 % en todo el tramo,
80,3 % en 2024–2026). La mejora (0,021) está por encima de la mínima detectable declarada de
antemano (0,014), así que **sí hay historia suficiente** para sostenerla.

**El DVOL por sí solo no basta.** A1, que añade únicamente el nivel de la volatilidad implícita,
mejora un 1,0 % y **no es distinguible de M1** (p 0,33, IC que cruza el 0, fuera del MCS). Lo que
informa es el **cambio reciente** del DVOL, no su nivel.

Nada cambia hoy: la adopción, si la hay, es otra entrega posterior al cierre de T31 y va junto con
la de M1 + ACI que dejó pendiente T162.

## Datos

| | |
|---|---|
| Objetivo | RV5 del día UTC de **BTCUSDT**, velas de 1 min del banco `t139_banco` (idéntico a T162) |
| DVOL | `public/get_volatility_index_data` de Deribit, BTC, velas de 1 h |
| Historia del DVOL | 2021-03-24T00:00Z → 2026-11-11T06:00Z · **49 399 velas, cobertura 100 %** |
| Tramo evaluado | **2022-01-01 → 2026-11-05**, **1 770 días**; subtramo 2024-01-01 → final, 1 040 |
| Días descartados | 0 por falta de DVOL · 1 por cobertura de 1 min < 90 % |
| Bloque del bootstrap | 1,0 (Politis-White) · 5 000 repeticiones · semilla 165 |

La varianza implícita del día `d` es el cierre de la vela horaria de las **23:00 del día `d−1`**,
la última cerrada al abrir el día: (DVOL/100)² / 365. La ingesta vive en `eim/data/dvol.py` y la
serie se guarda en el almacén del proyecto (`kind="dvol"`), así que la medición se repite sin red.

## Resultados

### QLIKE (métrica principal; menor es mejor)

| Modelo | QLIKE 2022–2026 | Δ vs M1 | QLIKE 2024–2026 | MCS (p) | IC 95 % de la diferencia | p de Holm |
|---|--:|--:|--:|--:|---|--:|
| M1 Log-HAR-RV (referencia) | 0,31562 | — | 0,26436 | 0,0036 ✗ | — | — |
| A1 HAR-IV (nivel) | 0,31248 | −1,0 % | 0,25584 | 0,0198 ✗ | −0,0137…+0,0099 | 0,332 |
| **A2 HAR-IV + pendiente** | **0,29450** | **−6,7 %** | **0,24831** | **1,000 ✓** | **−0,0325…−0,0102** | **0,0006** |
| A3 combinación M1+A1 | 0,30925 | −2,0 % | 0,25536 | 0,0198 ✗ | −0,0112…−0,0005 | 0,0096 |

Las tres condiciones, aplicadas tal cual:

| | A1 | A2 | A3 |
|---|---|---|---|
| 1. En el MCS con M1 fuera | ✗ | **✓** | ✗ |
| 2. Mejora con IC que excluye 0 y Holm < 0,05 | ✗ | **✓** | ✓ |
| 3. Cobertura con ACI en 80 % ± 2 pp (todo y 2024–26) | ✓ | **✓** | ✓ |
| **Pasa** | no | **sí** | no |

A3 es un caso instructivo: su mejora es significativa por Holm, pero **queda fuera del MCS** (hay
un modelo, A2, del que no se puede decir que no sea mejor) y además su mejora observada (0,0064)
está por debajo de su propia mínima detectable (0,0073). Es justo lo que el pre-registro quería
evitar: un «gana» que el contraste de la familia no sostiene.

### Potencia observada

| Modelo | s de la diferencia diaria | Mínima detectable (80 %) | Mejora observada | ¿Detectable? |
|---|--:|--:|--:|---|
| A1 | 0,2731 | 0,0161 | 0,0031 | no |
| **A2** | 0,2405 | **0,0142** | **0,0211** | **sí** |
| A3 | 0,1242 | 0,0073 | 0,0064 | no |

### Calibración y distribución del retorno (descriptivas, no deciden)

| Modelo | CRPS | Cobertura 80 % sin ACI | Con ACI (todo) | Con ACI (2024–26) | Peor ventana de 90 días | media de RV/ĥ |
|---|--:|--:|--:|--:|--:|--:|
| M1 | 0,013706 | 84,1 % | 80,28 % | 80,29 % | 90,0 % | 0,998 |
| A1 | 0,013587 | 82,3 % | 80,03 % | 80,10 % | 88,9 % | 1,154 |
| A2 | 0,013594 | 83,1 % | 80,16 % | 80,29 % | 88,9 % | 1,108 |
| A3 | 0,013642 | 83,5 % | 80,03 % | 80,19 % | 88,9 % | 1,066 |

En la **distribución del retorno** la ventaja es mucho menor que en el nivel de la varianza: el
CRPS baja un 0,8 % y A1 y A2 empatan entre sí. El mismo matiz que dejó T162 entre M0 y M1.
También conviene ver que M1 es casi insesgado en el cociente medio RV/ĥ (0,998) mientras A2 se
queda corto en media (1,108): A2 acierta mejor el día a día —que es lo que mide la QLIKE— pero
subestima algo el nivel medio. El ACI corrige la banda en todos los casos.

### Coeficientes (ajuste único sobre el tramo, solo descriptivo)

| | c | ln RV_d | ln RV_w | ln RV_m | ln IV² | pendiente 5 d |
|---|--:|--:|--:|--:|--:|--:|
| A1 | −0,100 | 0,414 | 0,048 | 0,051 | 0,513 | — |
| A2 | −0,471 | 0,351 | −0,045 | 0,263 | 0,407 | **0,949** |

La implícita se lleva ≈ 0,4–0,5 del peso que el HAR repartía entre los rezagos, y la pendiente
entra con un coeficiente grande (0,95): cuando el DVOL sube, la varianza realizada del día
siguiente sube más de lo que diría el HAR solo.

### Prima de varianza

| | |
|---|--:|
| Media de IV² − RV (diaria) | +1,42 · 10⁻⁴ |
| Mediana | +2,47 · 10⁻⁴ |
| Días con prima positiva | **76,2 %** |
| Autocorrelación de orden 1 | 0,405 |
| Media de ln(IV²/RV) | 0,531 (cociente típico ≈ 1,70) |
| IV² media / RV media | 8,62 · 10⁻⁴ / 7,21 · 10⁻⁴ = 1,20 (≈ 56,1 % frente a 51,3 % anualizados) |

**Positiva y persistente**, como anticipaba la ficha. Ahora bien, tal como se declaró en el
pre-registro, **la prima en logaritmos no es un modelo aparte**: ln IV² − ln RV genera el mismo
espacio de columnas que el diseño de A1 (es ln IV² menos un regresor que ya estaba ahí), de modo
que **A1 _es_ el modelo de la prima** en logaritmos. Y A1 no gana. La prima, por sí sola, no
mejora el pronóstico de la varianza; el cambio reciente de la implícita, sí.

### Control posterior al resultado (declarado como tal)

Añadido **después** de ver el resultado principal, para descartar fuga; no cambia ninguna cifra
anterior (misma semilla, mismos números). Reconstruye A2 corriendo el DVOL un día:

| Variante | QLIKE | Lectura |
|---|--:|---|
| M1 | 0,31562 | referencia |
| **A2 oficial** (DVOL de las 00:00 del día) | **0,29450** | lo que se mide |
| A2 con el DVOL de ayer | 0,31784 | **peor que M1** |
| A2 con el DVOL de mañana (imposible) | 0,24168 | −23 %: así se vería una fuga |

El orden es el que debe ser: cuanto más fresca la lectura, mejor el pronóstico, y el A2 oficial
está lejos del caso con fuga. Pero deja un aviso operativo de primer orden: **con un DVOL de un
día de antigüedad el modelo es peor que el HAR sin DVOL**. Toda la ventaja vive en la lectura del
momento.

## Límites

1. **La frescura es la condición, no un detalle.** El control de arriba lo deja claro: el colector
   tiene que estar al día y el modelo debe **degradar a M1** si el DVOL falta o está viejo.
   `daily_implied_var` ya devuelve `nan` por encima de un día de antigüedad; quien adopte esto
   tiene que decidir qué hace con ese `nan` en vivo.
2. **Dependencia externa sin compromiso de servicio.** Deribit es pública y gratuita, sin clave y
   sin SLA. La serie se guarda en el almacén, así que la medición es repetible, pero la operación
   depende de que la API responda.
3. **Historia corta.** El DVOL empieza el 2021-03-24: 1 770 días frente a los 2 135 de T162. No ve
   ni el desplome de 2020 ni el primer tramo del toro de 2021.
4. **Solo BTC.** La serie de ETH está descargada (49 399 velas, cobertura 100 %) pero no se ha
   medido: sería otro intento con su propio pre-registro.
5. **Horizontes distintos.** El DVOL es implícita a 30 días y aquí pronostica un día; el
   coeficiente de 0,4 lo corrige en parte, pero el desajuste está ahí.
6. **La ventaja es de nivel de varianza, no de distribución.** CRPS −0,8 % y A1 ≈ A2 ahí.
7. **Nada corre todavía.** El colector es una orden (`python -m eim.data.dvol --data v2/data
   --currency BTC,ETH`), no una tarea programada: dejarla periódica es decisión del usuario, y
   mostrar el dato en una esfera o panel toca vistas vivas, fuera del modo SIMULADO de esta tarea.

## Qué sigue (en `PLAN/BACKLOG.md`)

- Al cerrar T31 (≥ 2026-11-27): valorar **A2 junto con M1 + ACI** en el cono, midiendo en paralelo
  y en vivo, con la degradación a M1 escrita y probada.
- Programar el colector (decisión del usuario) y meter `data/dvol/` en la copia diaria.
- ETHUSDT con la misma regla; pendiente de 1 día frente a la de 5 (pre-registrada); skew 25Δ aparte.
- Mostrar el DVOL con su fuente en la interfaz cuando se adopte algo.

## Reproducir

```
python -m eim.data.dvol --data v2/data --currency BTC,ETH
python scripts/t165_dvol.py --data v2/backups/t139_banco --dvol v2/data
```
