# T165 — Pre-registro: DVOL de Deribit y prima de varianza en la varianza diaria

Fijado el 2026-11-11, **antes de calcular ningún resultado**, en un commit propio. Nada de lo que
sigue se cambia después de mirar cifras; si un defecto del código obliga a repetir, se declara en
el informe.

**Modo: SIMULADO.** Mide; no toca el forecaster en vivo, ni las bandas dibujadas, ni `regime`.
Aunque pase, no se adopta antes del cierre de T31 (2026-11-27), igual que T160 y T162.

## Pregunta

¿Añadir la volatilidad implícita de Deribit (DVOL de BTC, índice público de σ implícita a 30 días)
mejora el pronóstico de la varianza realizada del día siguiente de BTCUSDT **por encima del
Log-HAR-RV que ganó T162**? La referencia a batir ya no es el GARCH fijo del cono (M0 de T162),
es **M1**.

## Datos

- **Objetivo (idéntico a T162):** RV5 del día UTC sobre velas de 1 min de BTCUSDT del banco
  `backups/t139_banco` (hasta 2026-11-06). Un día solo cuenta con ≥ 90 % de sus velas de 1 min.
  Retorno diario = log del último cierre de 1 min del día sobre el del día anterior.
- **DVOL:** `public/get_volatility_index_data` de Deribit (público, sin clave), `currency=BTC`,
  `resolution=3600`, guardado en el almacén del proyecto (`kind="dvol"`, símbolo `BTC`, marco
  `1h`) para que la medición se repita sin red. Se descarga también ETH, que **no** se mide aquí.
- **Comprobado antes de escribir esto** (único dato mirado; ninguna pérdida calculada): la historia
  pública del DVOL empieza el **2021-03-24T00:00Z** para BTC y ETH; antes no existe.
- **Regla sin fuga:** la varianza implícita del día `d` es el **cierre de la última vela horaria de
  DVOL cerrada por completo antes de las 00:00 UTC de `d`** (la vela de las 23:00 del día `d−1`).
  DVOL es σ anualizada en %, así que IV²_d = (DVOL/100)² / 365.
- Un día solo entra si tiene RV válida, retorno válido, DVOL válido y pronóstico de los cuatro
  modelos.

## Tramo evaluado

**2022-01-01 → último día completo del banco (2026-11-05)**, ≈ 1 770 días. El inicio deja ≥ 250
días de DVOL (desde 2021-03-24) para el calentamiento de las regresiones, el mismo mínimo que usó
M1 en T162. Se informa además el subtramo **2024-01-01 → final** por separado, como en T162.

## Familia (3 intentos; familia de calibración propia, no se suma a la de trading de 841)

Referencia, no es un intento:

| Id | Modelo | Ajuste |
|---|---|---|
| M1 | Log-HAR-RV de T162: ln RV_{t+1} = c + β_d ln RV_t + β_w ln RV̄_t^(5) + β_m ln RV̄_t^(22); pronóstico exp(ŷ + s²/2) | Mínimos cuadrados con todos los días anteriores, reajuste diario |

Intentos:

| Id | Modelo | Ajuste |
|---|---|---|
| A1 | **HAR-IV**: M1 + γ·ln IV²_t | Igual que M1 (mismo estimador, mismo reajuste diario) |
| A2 | **HAR-IV-P**: A1 + δ·s_t, con la pendiente s_t = ln IV²_t − ln IV²_{t−5} | Igual |
| A3 | **Combinación** de pesos iguales de M1 y A1 | — |

Se declara de antemano: la **prima de varianza en logaritmos**, ln IV²_t − ln RV_t, genera el mismo
espacio de columnas que el diseño de A1 (es ln IV²_t menos un regresor que ya está), así que
**A1 _es_ el modelo de la prima en logaritmos** y no se cuenta como un intento aparte. La prima en
niveles (IV²_t − RV_t) se describe en el informe —nivel, signo, persistencia— pero no decide nada.
A2 cubre la pendiente del DVOL. Todos los ajustes son por mínimos cuadrados **solo con días
anteriores**, ventana recursiva, exactamente el mismo estimador de M1.

## Métricas

- **Principal:** QLIKE diaria media, L = RV/ĥ − ln(RV/ĥ) − 1 (Patton 2011), sobre el tramo evaluado.
- **Descriptivas, no deciden:** MSE de la varianza; CRPS y PIT de la predictiva N(0, ĥ) del retorno
  diario; cobertura de la banda del 80 % con y sin ACI (γ = 0,005, ventana 250) y la peor ventana
  de 90 días. Mismo código que T162 (`eim/forecast/vol_eval.py`).

## Regla de adopción (se aplica tal cual)

Un intento Ak (k = 1, 2, 3) **pasa** si se cumplen las tres:

1. **Model Confidence Set** al 10 % sobre las pérdidas QLIKE de {M1, A1, A2, A3} (bootstrap
   estacionario, bloque de Politis-White, 5 000 repeticiones, **semilla 165**): Ak está dentro y
   **M1 queda fuera**.
2. **Mejora frente a M1:** la diferencia media de QLIKE (Ak − M1) tiene un IC del 95 % por bootstrap
   estacionario que **excluye 0 por debajo**, y su p unilateral **ajustada por Holm en la familia de
   3** es < 0,05.
3. **Cobertura con ACI** de la banda del 80 % dentro de **80 % ± 2 pp** en todo el tramo evaluado y
   también en 2024–2026.

Si pasan varios, se propone el de menor QLIKE media. Si no pasa ninguno, el cono se queda con M1,
el DVOL queda solo como contexto en la interfaz y el informe lo dice así.

## Potencia declarada de antemano

Con n ≈ 1 770 días, el contraste unilateral al 5 % con potencia 0,80 detecta una diferencia media
de QLIKE de ≈ 2,49·s/√n, con s la desviación típica de la diferencia diaria (se informa la s
observada y la mejora mínima detectable que implica). En T162 la diferencia M1 − M0 tenía s ≈ 0,43
(semiancho del IC 0,0184 sobre 2 135 días), que a n = 1 770 exigiría ≈ 0,026 de QLIKE, un −8 % sobre
el 0,305 de M1; dos variantes de HAR que comparten regresores tienen una s bastante menor, así que
la mejora mínima detectable real se calcula y se publica. **Si la historia disponible del DVOL no
alcanza para detectar la mejora —es decir, si la mejora observada queda por debajo de la mínima
detectable—, la tarea se cierra con ese veredicto en lugar de forzar un resultado.**

## Lo que esta tarea no hace

- No cambia el forecaster en vivo (`forecast/base_engine.py`), ni las bandas dibujadas, ni `regime`,
  ni el tamaño de los stops: la adopción, si la hay, es otra entrega tras el cierre de T31.
- No mide el skew 25Δ, la gamma de dealers, los flujos de ETF ni el COT (descartados en la ficha).
- No usa datos de pago (Tardis) ni estrategias con opciones (T100).
- No mide ETH ni otros símbolos: el contraste es BTCUSDT.
