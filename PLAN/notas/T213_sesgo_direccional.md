# T213 · ¿Por qué casi todo lo que operamos es corto? Auditoría del lado

**Fecha:** 2026-11-26 (05:30 UTC), desde `juanpablo-cpu`. **Modo: SIMULADO.** Abierta por una
observación del usuario: «la gran cantidad de cortos y la poca cantidad de largos que hemos estado
operando en los últimos días». Solo lectura: no se tocó `eim/`, ni el libro, ni los perfiles, ni la
corrida de T31. Continuación de T210 (utilidad por perfil) y T212 (la puerta, a la vista).

## 1. La premisa es correcta, y es más extrema de lo que parece

Libro oficial (universo T144, `counts_as_result`, sin `retro`): **726 operaciones, 652 cortas
(89,8 %)**. Por día de apertura:

| día | largas | cortas | PnL largas | PnL cortas |
|---|---|---|---|---|
| 11-08 → 11-22 (15 días) | **0** | 461 | — | −1 394,2 |
| 11-23 | **18** | 7 | **−302,4** | +5,8 |
| 11-24 | 1 | 29 | +10,2 | +83,0 |
| 11-25 | 0 | 29 | — | −116,2 |

Quince días seguidos sin una sola operación larga. En los últimos 7 días (11-19 → 11-25): **19 largas
y 236 cortas (92,5 %)**.

## 2. La causa está medida y no es un misterio: una puerta con tres relojes

`ProfileParams.htf` fija el lado por marco de decisión (15m → 1h EMA21/55, 1h → 4h EMA21/55,
4h → 4h EMA50/200) y el veto `contra_tendencia` lo aplica en los cuatro perfiles (T212). Estado con
las velas reales del disco al cierre del 11-26 04:00 UTC (precio **60 951**):

| puerta | estado | desde | horas |
|---|---|---|---|
| 15m → 1h EMA21/55 | **alcista** | 11-26 05:00 | 0 |
| 1h → 4h EMA21/55 | **bajista** | 10-23 00:00 | **821** |
| 4h → 4h EMA50/200 | **bajista** | 10-24 16:00 | **781** |

**Dos de las tres puertas no han girado ni una vez en 34 días.** Los marcos 1h y 4h —dos tercios del
libro— solo pueden vender: no es una lectura del mercado repetida, es la misma lectura congelada.
La única puerta que puede autorizar un largo es la rápida, y en cuatro días **giró tres veces**:
11-22 17:00 alcista → 11-24 09:00 bajista → 11-26 05:00 alcista. Los 18 largos del 11-23 son
exactamente la ventana que abrió el primer giro, y perdieron **−302,4 USDT**.

Con el veto ya contado (T212, medición del 11-24 sobre 2 000 rechazos): la puerta de 1h dejó fuera
**56 ideas (100 rechazos, todos largos)** y la de 4h **11 ideas (29 rechazos, todos largos)**.
Hoy no se pudo refrescar ese recuento: `GET /v2/paper` lleva más de 8 min en «Calculando la vista
del bróker simulado» y `/v2/health` no respondió en 30 s — el mismo atasco del único trabajador ya
anotado en BACKLOG para T206.

## 3. Y aun así, el sesgo no es lo que está costando el dinero esta semana

El contraste de los dos lados sobre las ideas de BTCUSDT del **11-19 al 11-25**:

| universo | largas | cortas | diferencia L−S |
|---|---|---|---|
| libro oficial | n = 19, E[R] **−0,188** | n = 236, E[R] **−0,024** | −0,165 ± 0,299 (t = −1,08) |
| sombra (sin veto) | n = 420, E[R] **−0,333** | n = 667, E[R] **+0,156** | **−0,490 ± 0,154** (t = −6,21) |
| sombra, agrupada por vela de apertura | 240 grupos, −0,397 | 318 grupos, +0,133 | **−0,530 ± 0,204** (t = −5,09) |

En la sombra —que evalúa **todas** las ideas, incluidas las que el veto no dejó pasar— el lado largo
fue **mucho peor** que el corto en esta ventana, y la diferencia sobrevive al agrupar por vela de
apertura (el solapamiento de ideas no la explica). Dicho sin tecnicismos: **esta semana haber
operado más largos habría perdido más, no menos.** La sombra genera largos de sobra (420 de 1 087
ideas, 39 %), así que el desequilibrio del libro es del veto, no de las estrategias.

Coherente con el precio: el mínimo del 11-21 fue 55 127, el rebote llevó a 63 833 el 11-23 (+15,8 %)
y hoy el precio está en **60 951**, que es **−4,5 % frente a ese máximo del rebote** y **−25,6 %
frente al máximo de 30 días** (81 954 el 10-29). Las dos puertas lentas siguen bajistas y el precio
no las ha desmentido todavía; la rápida, que giró dos veces en ese tramo, sí autorizó los largos
peor pagados del mes.

**Lo que T212 sí midió como costo del retraso sigue en pie** y no se contradice con esto: en el
rebote del 11-21, 49 aperturas, 45 cortas, **−731,7 USDT**, y los dos marcos con la puerta bajista
pusieron 33 operaciones, todas cortas, −586,6. El sesgo cuesta **en los giros**; el resto del tiempo
el lado corto fue el lado correcto.

## 4. Dónde se va el dinero de verdad (auditoría del 2026-11-26)

n = 726 · E[R] **−0,074 R** [−0,118, −0,030] · **bruto +0,051** · **costo +0,125** · acierto 78,1 %
frente a un equilibrio de 84,2 % · PnL **−2 915 USDT**. Últimos 7 días: n = 250, E[R] −0,040,
costo 0,124. Δ frente al 11-23: n +83, E[R] +0,002, PnL −330.

El bruto es **positivo** y el neto negativo: la fricción (0,125 R/op) se come toda la ventaja bruta
y algo más. Con T210: lo que mueve la utilidad es **cuántas operaciones tocan el tope completo**,
no el lado. Un libro con más largos, con este costo, seguiría por debajo de cero.

## 5. Qué se puede proponer y qué no

- **T139 está cerrada con P1 (vinculante hasta 2027-05-06)**: cambiar la puerta —su marco, sus
  EMAs, su veto— **es una entrada nueva**. No se toca sin ◆ del usuario que reabra T139, y cada
  intento contaría en la familia de Holm (841, T49).
- **Acelerar la puerta no es el arreglo**: en los 98 días de velas de 1 h del disco la puerta
  rápida gira 40 veces y **no distingue dirección** (+0,220 % alcista frente a bajista, con un
  mínimo detectable de ±1,157 %). Sus tres giros de esta semana y los largos del 11-23 lo
  confirman **en vivo**: acortar EMAs cambia sesgo por ruido. Y las lentas tampoco distinguen,
  por falta de giros (§6 corrige el método con que T212 las leyó).
- **T145 D (solo análisis)**: lo que falta no es operar el otro lado, es **decirlo con número**.
  T212 ya publica la puerta, su retraso y lo que veta. Lo que todavía no existe es la puntuación
  continua del lado: nadie mide si cada puerta acierta, ni compara los dos lados en la sombra, así
  que la pregunta del usuario hubo que contestarla a mano.
- **T194** (28-nov 00:00 UTC) recorta el tamaño: reduce la pérdida, no corrige la dirección.

## 6. Una corrección al método de T212 §5 (encontrada al implementar T213)

T212 juzgó el signo de cada puerta promediando el retorno a 24 h de **todas las velas** de sus
tramos: la rápida salía con −0,180 % (alcista peor que bajista) y las lentas con +0,455 % y
+0,234 %. **Ese promedio inventa signo.** La ventana de 24 h de las últimas velas de un tramo cae
ya al otro lado del giro, y un giro es por construcción una vuelta del precio, así que los tramos
cortos salen castigados y los largos premiados. Medido así, **10 de 12 caminatas aleatorias puras
dan «la puerta distingue al revés» con significación**; es un artefacto, no una lectura.

Midiendo **desde el instante del giro** —un dato por giro, sin solapamiento y sin conocer el
futuro— las tres puertas quedan así en los 98 días de velas de 1 h del disco:

| puerta | giros ↑/↓ | ret. 24 h ↑ | ret. 24 h ↓ | diferencia | mín. detectable | lectura |
|---|---|---|---|---|---|---|
| 15m (1h EMA21/55) | 20/20 | +0,138 % | −0,081 % | +0,220 % | ±1,157 % | **no distingue** |
| 1h (4h EMA21/55) | 3/3 | +1,397 % | −0,576 % | +1,973 % | ±6,206 % | **no distingue** |
| 4h (4h EMA50/200) | 1/1 | +7,365 % | +1,054 % | — | — | muestra corta |

La conclusión de T212 **se mantiene y se refuerza**: ninguna puerta tiene signo medible con este
historial. La rápida porque sus 40 giros son ruido; las lentas porque **casi no giran** (3 y 1 giro
en 98 días), así que no hay muestra con la que juzgarlas ni con la que juzgar una alternativa. Lo
que cambia es que ya no puede decirse «las lentas sí distinguen»: eso era el mismo artefacto con el
signo a favor. Y refuerza la línea de T139: una puerta alternativa necesitaría años de historia
propia antes de poder compararse, exactamente lo que P1 exige.

## 7. Qué se abre

- **T213** (fase 25), **hecha el 2026-11-26 en esta misma sesión**: el sesgo, el contraste de los
  dos lados y el signo de cada puerta salen ya solos en cada auditoría (`eim/analytics/audit/
  sides.py`, encabezado del informe, §6 del Markdown y dos líneas de consola), sin tocar la puerta.
- BACKLOG bajo T159: la ◆ de si, tras cerrar T31, se pre-registra en sombra una puerta alternativa
  (reabre T139), que ya estaba abierta por T212 y esta semana gana una cifra a favor y una en
  contra: el retraso cuesta en los giros, pero el lado largo de esta ventana fue peor.
