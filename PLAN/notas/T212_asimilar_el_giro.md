# T212 · ¿Por qué el análisis no asimiló el giro al alza?

**Fecha:** 2026-11-23 (≈ 15:00 UTC), desde `juanpablo-cpu`. **Modo: SIMULADO.** Continuación de la
retroalimentación de T210, a partir de una observación del usuario: «identificamos la tendencia bajista
y operamos sobre ella con éxito, pero cuando cambió y el precio empezó a subir, el análisis no supo
asimilar el cambio, y eso puede haber ocasionado la pérdida de la tendencia alcista en las ganancias».
**La observación es correcta y se puede medir.** Solo lectura: no se tocó `eim/`, ni el libro, ni los
perfiles, ni la corrida de T31.

## 1. Qué fija el lado: una puerta con tres relojes

`ProfileParams.htf` (`eim/paper/params.py:99`) define la tendencia del marco mayor por marco de
decisión: **15m → 1h EMA21/55**, **1h → 4h EMA21/55**, **4h → 4h EMA50/200**. `HtfTrend`
(`eim/paper/trend.py:15`) es el signo de EMA rápida − EMA lenta en la última vela **cerrada** del marco
mayor, y el veto `contra_tendencia` (`eim/paper/vetoes.py:60`) rechaza toda idea que vaya en contra
mientras `require_htf` esté activo. No hay nada más que decida el lado: la dirección del libro **es**
esa puerta.

## 2. El retraso, medido sobre las velas reales del disco

Mínimo de 1 h: **55 127 el 2026-11-21 a las 06:00 UTC**. Cierre del 11-23 14:00: **63 833, +15,8 %**.

| puerta | estado ahora | desde | retraso frente al mínimo |
|---|---|---|---|
| 15m → 1h EMA21/55 | **alcista** | 11-22 17:00 | **35 h**, con el precio ya **+11,1 %** |
| 1h → 4h EMA21/55 | **bajista** | 10-23 00:00 (**758 h**) | no ha girado |
| 4h → 4h EMA50/200 | **bajista** | 10-24 16:00 (**718 h**) | no ha girado |

Dicho sin tecnicismos: **hoy, con el precio un 15,8 % por encima del mínimo, dos de las tres puertas
siguen prohibiendo comprar**, y la tercera tardó 35 horas y once puntos de subida en permitirlo.

## 3. Lo que costó, en el libro oficial

Aperturas posteriores al mínimo del 11-21 06:00 (BTCUSDT, universo T144):

| | n | cortas | PnL |
|---|---|---|---|
| total | 49 | **45** | **−731,7** |
| marco 1h (puerta bajista) | 18 | 18 | −313,9 |
| marco 4h (puerta bajista) | 15 | 15 | −272,7 |
| marco 15m (puerta girada el 11-22) | 16 | 12 | −145,1 |

- Los dos marcos cuya puerta **sigue** bajista son **33 operaciones, todas cortas, −586,6 USDT**.
- Antes de que girara la puerta de 15m: **43 operaciones, todas cortas, −474,1**. Después: 6, de las
  que 4 largas.
- Por día de apertura: 11-21 **45 (45 cortas) −498,3** · 11-22 **20 (20 cortas) −157,7** · 11-23
  **5 (1 corta) −261,3**.
- Y esto es exactamente «la pérdida de la tendencia alcista en las ganancias»: el acumulado oficial
  pasó de **−2 584,7 USDT** (medición de las 08:39) a **−2 856,3** (15:00) mientras el precio subía.

## 4. El otro filo: llegar tarde también convierte el acierto en pérdida

Los cuatro largos que la puerta ya permitió:

| perfil | estrategia | abre | entrada | cierre | resultado |
|---|---|---|---|---|---|
| agresivo | `ind_bb_ruptura@15m` | 11-23 14:00 | 63 834 | 14:15, SL 63 264 | **−194,4 (−1,31 R)** |
| agresivo | `ind_macd@15m` | 11-23 14:00 | 63 834 | 14:15, SL 63 264 | **−62,8 (−1,31 R)** |
| moderado | `base_retroceso@15m` | 11-23 05:45 | 61 515 | 09:16, escalera | +10,0 (+0,10 R) |
| ppp_btcusdt | `sugerencia_alineada@15m` | 11-23 03:45 | 61 114 | 05:23, escalera | +10,2 (+0,22 R) |

Cuando la puerta por fin dejó comprar, la entrada estaba **+14 a +16 % por encima del mínimo** y el
primer retroceso tocó el stop. Es la misma asimetría de la escalera que explica T210 (+0,14 R de
ganancia media contra −1,09 R de pérdida), ahora del lado largo: **el retraso no solo pierde la
subida, convierte la entrada tardía en una pérdida completa**.

## 5. ¿Y si se acelera la puerta? Lo que dicen los datos (descriptivo, sin contraste)

95 días de velas de 1 h en el disco (2026-08-20 → 11-23, 2 282 velas), rendimiento siguiente del precio
según el estado de cada puerta:

| puerta | tramos | duración mediana | retorno a 24 h: alcista vs bajista |
|---|---|---|---|
| 1h EMA21/55 (la de 15m) | **39** | 34 h (mínimo 1 h) | **−0,338 % vs −0,158 %** (diferencia **−0,180 %**) |
| 4h EMA21/55 (la de 1h) | 15 | 212 h | +0,168 % vs −0,287 % (**+0,455 %**) |
| 4h EMA50/200 (la de 4h) | 7 | 292 h | +0,124 % vs −0,110 % (**+0,234 %**) |

**Las puertas que tienen signo son las lentas, y la única rápida no tiene signo** (en 24 h su estado
«alcista» precede retornos peores, y cambia de opinión 39 veces en 95 días). Por eso el arreglo no es
«poner EMAs más cortas»: eso cambia un sesgo por ruido. Ventanas solapadas, una sola plaza y 95 días:
**esto es descriptivo, no un contraste**, y no puede convertirse en regla sin pre-registro, con cada
intento contando en la familia de Holm (T49, T139).

## 6. Dónde choca con lo ya decidido

- **T139 (P1, vinculante hasta 2027-05-06)** cerró la búsqueda de entradas. Cambiar la puerta **es**
  una entrada nueva: no se toca sin ◆ del usuario que reabra T139.
- **T145 (D, solo análisis)**: lo que falta no es operar mejor, es **decirlo**. Hoy nada en el panel
  avisa de que la puerta de 1 h lleva 758 h bajista mientras el precio sube 15,8 %; el veto es
  silencioso, un rechazo más entre miles. Eso sí es producto de la decisión D y es lo que T212 pide.
- **T194 (2026-11-28 00:00 UTC)** recorta el tamaño (×0,8522 y freno gradual). Si la puerta sigue
  bajista mientras el precio sube, eso **reduce la pérdida, no corrige la dirección**.
- **T210** queda confirmada desde otro ángulo: la utilidad de los cuatro perfiles es el camino del
  precio filtrado por una sola puerta, no cuatro lecturas independientes.

## 7. Un detalle que corrige la premisa

El universo oficial no es solo BTC: incluye **38 operaciones de ETHUSDT (+255,1 USDT)** entre el 10-21
y el 10-28, antes del foco en BTC (T122). Parte de las ganancias de W43 —la única semana en verde— no
eran de BTC. El tramo que el usuario recuerda bien es el del 11-17 al 11-20: **+655,4 USDT**, todo en
BTC y todo en cortos, con la tendencia a favor.

## 8. Qué se abre

- **T212** (fase 25): publicar el estado y el retraso de cada puerta, y el costo visible de lo que veta.
- BACKLOG bajo T159: la ◆ de si, tras cerrar T31, se pre-registra en sombra una puerta alternativa
  (reabre T139) y la de si el informe de cierre declara que el libro es direccionalmente una sola
  apuesta mientras la puerta no gire.
