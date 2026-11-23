# Patrón de apertura de sesión en BTC 1m — medición (2026-11-23)

Hipótesis del usuario: en velas de 1 minuto, lo que el precio hace en los **3 primeros minutos
de la apertura de un mercado** se **deshace en los 3 minutos siguientes**. Se midió sobre datos
reales y se evaluó como operativa, con canal de soporte/resistencia y órdenes límite.

## Datos y cobertura

- **BTCUSDT perpetuo, futuros Binance (`/fapi/v1/klines`), 1m, 2024-01-01 00:00 → 2026-11-23 08:01 UTC.**
  1 522 562 minutos de rejilla, **100,000 % con vela** (sin huecos). Descarga a un parquet aparte
  (`v2/scripts/descargar_1m_btc.py`): no se tocó el almacén vivo de `data/candles/`.
- Comprobación cruzada en el almacén vivo del equipo (`timeframe=1m`, 2026-10-15 → hoy, 56 617
  minutos, 100 % con vela): mismo veredicto con n = 27 aperturas.
- Aperturas por zona, en UTC (el horario de verano las mueve; se calcularon en hora local con
  `zoneinfo`, no con un desplazamiento fijo):

  | zona | hora local | en UTC (días de 2024-2026) | n |
  |---|---|---|---|
  | Tokio | 09:00 `Asia/Tokyo` | 00:00 ×756 | 756 |
  | Hong Kong | 09:30 `Asia/Hong_Kong` | 01:30 ×756 | 756 |
  | Londres | 08:00 `Europe/London` | 07:00 ×450, 08:00 ×306 | 756 |
  | Fráncfort | 09:00 `Europe/Berlin` | 07:00 ×450, 08:00 ×306 | 756 |
  | Nueva York | 09:30 `America/New_York` | 13:30 ×510, 14:30 ×245 | 755 |
  | CME (reapertura) | 17:00 `America/Chicago` | 22:00 ×510, 23:00 ×245 | 755 |

  Londres y Fráncfort son **el mismo instante** todo el periodo: sus cifras son idénticas, no es
  un error de copia.
- Costes aplicados: taker 4,5 bps por lado (ida y vuelta **9 bps**) en entradas a mercado;
  maker 1,8 bps + taker 4,5 bps (**6,3 bps**) cuando la entrada es límite. Son las tarifas
  públicas de Binance futuros sin descuentos.

## 1. El patrón, tal como se enunció: no está

Tramo A = cierre de la 3ª vela / apertura de la 1ª. Tramo B = los 3 minutos siguientes.
Se entra **en contra** de A en la apertura del 4º minuto.

| zona | n | reversión | p (binomial) | corr(A,B) | contrario bruto | neto |
|---|---|---|---|---|---|---|
| Londres/Fráncfort | 755 | 49,4 % | 0,77 | −0,023 | **−0,02 bps** | −9,02 bps |
| Nueva York | 755 | 49,1 % | 0,66 | −0,021 | +0,25 bps | −8,75 bps |
| Tokio | 753 | 47,0 % | 0,11 | −0,049 | −0,31 bps | −9,31 bps |

La reversión ocurre el **49 %** de las veces: lo mismo que una moneda. El resultado bruto es
**±0,3 bps**, es decir, el tramo A no informa del tramo B **en ninguno de los dos sentidos**
(hacer lo contrario y hacer lo mismo pierden igual). Lo que se pierde es exactamente la comisión.

**Control** (el mismo cálculo tomando como «apertura» cada uno de los 1440 minutos del día):
la media de reversión de todos los minutos es 50,98 % y la de las aperturas cae **por debajo**
(percentil 19 Londres, 3 Nueva York, 2 Tokio). Si algo hay, es un poco **menos** reversión en la
apertura que en un minuto cualquiera. Los minutos con más reversión del control (14:28 con
54,8 %, 15:48 con 54,7 %) son resultado de probar 1440 veces, no hallazgos.

### Operaciones, con tope de 4 h

Salida por tiempo fijo y salida por objetivo/stop simétricos de tamaño |A| (tope 240 min; empate
en el mismo minuto se cuenta como stop). 4 527 operaciones, 6 zonas, netas de 9 bps:

| salida | n | acierto | media | total | t | PF | peor caída |
|---|---|---|---|---|---|---|---|
| 3 min | 4 527 | 18,3 % | −9,34 bps | −422,98 % | −41,6 | 0,17 | 422,7 % |
| 6 min | 4 527 | 25,6 % | −9,20 bps | −416,66 % | −28,8 | 0,28 | 416,6 % |
| 30 min | 4 527 | 38,0 % | −8,88 bps | −401,87 % | −13,2 | 0,55 | 402,5 % |
| 240 min (tope) | 4 527 | 46,0 % | −8,67 bps | −392,45 % | −5,4 | 0,79 | 416,2 % |
| objetivo/stop | 4 527 | 19,8 % | −9,51 bps | −430,58 % | −42,5 | 0,17 | 430,5 % |

Estable año a año (2024: −9,71 bps · 2025: −8,79 · 2026: −9,55) y **igual en 2 000 minutos al
azar** (−8,33 bps a 3 min), que es la prueba de que no hay nada propio de la apertura: la regla
pierde la comisión donde se aplique. Con objetivo/stop **ninguna** operación llega al tope de
4 h: duran 4-7 minutos de media, porque un objetivo de 8-17 bps lo toca el ruido enseguida.

## 2. Lo que sí hay en la apertura

- **Más volatilidad**, medida y clara. |retorno| por minuto: Nueva York 9,80 bps en el minuto de
  apertura frente a 8,71 en los minutos 15-30 y 4,97 en los 5 previos; CME 6,57 frente a 3,99;
  Hong Kong 5,92 frente a 4,75; Londres 4,67 frente a 4,06. El salto es real; no trae dirección.
- **Nada en los minutos 3 a 8.** Retorno medio en el sentido del tramo A: Londres −0,05, +0,20,
  −0,13, −0,59; Tokio −0,64, +0,23, +0,69; Nueva York −0,10, +0,12, −0,27, −0,80 bps. Todo
  dentro del ruido y un orden de magnitud por debajo del coste. (Los minutos 0, 1 y 2 salen
  positivos **por construcción**: son los que definen A.)
- **La ruptura del canal de apertura es lo único con signo positivo en bruto**, y aun así no
  paga: ver abajo.

## 3. Canal de apertura con órdenes límite

Canal = alto y bajo de las 3 primeras velas. W = alto − bajo; soporte = bajo + f·W,
resistencia = alto − f·W (f = 0 en el extremo; f > 0 metido hacia dentro). Límite de compra en el
soporte y de venta en la resistencia, la primera que toque el precio en 30 minutos; el límite
exige que el precio **atraviese** el nivel; objetivo = medio o extremo opuesto; stop = s·W más
allá; tope 4 h; coste 6,3 bps.

**El canal es estrecho y se llena casi siempre** (contestando la duda de «si es muy amplio no se
opera»): W medio = 14,1 bps en Londres, 16,6 Tokio, 17,8 Hong Kong, 17,9 CME, **34,8 Nueva York**.
Llenado con f = 0: **98,5-98,8 %** de los días. Meter los niveles hacia dentro **empeora** las
dos cosas: con f = 0,30 el llenado baja a 87 % (y 92-103 días quedan ambiguos porque el precio
toca los dos bordes en el mismo minuto) y el resultado cae ~2-6 bps más.

| zona | variante | llenado | W | acierto | **bruto** | neto |
|---|---|---|---|---|---|---|
| Londres | rev f=0 stop=1W obj=opuesto | 98,8 % | 14,1 bps | 41,0 % | **−0,71** | −7,01 |
| Londres | **ruptura** obj=W stop=medio | 98,8 % | 14,1 bps | 36,1 % | **+1,57** | −4,73 |
| Nueva York | rev f=0 stop=0,5W obj=medio | 98,7 % | 34,8 bps | 37,3 % | **−3,09** | −9,39 |
| Nueva York | **ruptura** obj=W stop=medio | 98,7 % | 34,8 bps | 42,8 % | **+4,14** | −2,16 |
| Tokio | ruptura | 98,5 % | 16,6 bps | 36,8 % | **+1,55** | −4,75 |
| Hong Kong | ruptura | 98,8 % | 17,8 bps | 40,4 % | **+2,24** | −4,06 |
| CME | ruptura | 98,7 % | 17,9 bps | 36,8 % | **+1,67** | −4,63 |

Las **24 variantes de reversión** medidas (3 valores de f × 2 stops × 2 objetivos × 5 zonas)
dan bruto **negativo** en todas: el canal de apertura **no rebota**, se rompe. La ruptura tiene
bruto positivo en las 5 zonas (+1,55 a +4,14 bps), lo que confirma el signo del apartado 1 con
otra medida independiente, pero **el mejor caso (Nueva York, +4,14 bruto) sigue 2,2 bps por
debajo del coste de 6,3** y su t es −1,94 en neto. Para que la ruptura de Nueva York empatara
harían falta comisiones de ~2 bps ida y vuelta, que no existen para un particular.

## 4. La apertura de hoy, en vivo (2026-11-23, 08:00 UTC)

| minuto | apertura | cierre | ret |
|---|---|---|---|
| 08:00 | 61 431,1 | 61 457,1 | +4,2 bps |
| 08:01 | 61 457,0 | 61 472,9 | +2,6 bps |
| 08:02 | 61 472,8 | 61 426,7 | −7,5 bps |
| 08:03-08:05 | 61 426,7 | 61 401,2 | −4,2 bps |

Tramo A = **−0,7 bps** (plano: subió dos minutos y lo devolvió en el tercero, el caso en que el
patrón ni siquiera queda definido) y tramo B = −4,2 bps, **misma dirección**: no revirtió.

## 5. Veredicto y qué hacer con la cantera

El perfil **no pasa la puerta de costo**: su valor esperado bruto es ~0 (patrón enunciado) o
+1,5/+4,1 bps (ruptura del canal), contra 6,3-9 bps de coste. Queda **registrado y rechazado**,
no inscrito. Para inscribirlo como prospecto haría falta, además, cambiar dos cosas que hoy lo
impiden y que son decisión del usuario:

1. `nursery/prospect.py` y `prereg.MemberSpec` sólo admiten `timeframe` de **15m, 1h o 4h**;
   este perfil es de 1m.
2. `prereg_cantera_v1` está **congelado con su huella publicada** y `m = los que entran + la
   reserva`; añadir un miembro obliga a `prereg_cantera_v2.json` **con reloj nuevo**, lo que
   reinicia la medición de la familia que corre desde 2026-11-17.

## 6. Dos coberturas adicionales, 60x, toma de ganancias de 200-300 USD

Montaje medido: **principal** 1 unidad en contra del tramo A, **cobertura larga** 1 unidad y
**cobertura corta** 1 unidad, las tres al mismo precio de entrada (apertura del 4º minuto), cada
pata con su toma de ganancias a +200 o +300 USD de recorrido a favor, margen aislado, tope 4 h.
Salida completa: `v2/scripts/patron_apertura_coberturas.py`.

Aritmética del apalancamiento, con el precio medio del periodo (80 670 USD):

| magnitud | en USD de precio | en % del margen a 60x |
|---|---|---|
| toma de ganancias | 200 / 300 | **14,9 % / 22,3 %** |
| coste taker ida y vuelta (9 bps) | 73 | **5,4 % por pata** |
| liquidación (mmr 0,5 %) | **941 en contra** | **70 %** |

Son 3 patas: **16,2 % del margen en comisiones por cada apertura**, y la toma de ganancias está a
menos de un cuarto del camino que lleva a la liquidación. A los 61 400 USD de hoy las cifras
cambian de escala pero no de proporción: TP de 200 = 19,5 % del margen, liquidación a 716 USD.

### Qué hace el precio en las 4 h siguientes (lo que decide si las coberturas sirven)

TP = 200 USD:

| zona | toca +200 arriba | abajo | **las dos** | ninguna | recorrido máx. (mediana) | min hasta el 1er TP |
|---|---|---|---|---|---|---|
| Tokio | 74,9 % | 79,2 % | **54,4 %** | 0,4 % | 753 USD | 19 |
| Hong Kong | 70,7 % | 71,1 % | 42,9 % | 1,1 % | 676 USD | 17 |
| Londres | 70,6 % | 69,4 % | 41,1 % | 1,1 % | 677 USD | 22 |
| Nueva York | 80,8 % | 83,0 % | **63,8 %** | 0,0 % | 1 243 USD | 4 |
| CME | 67,2 % | 73,9 % | 43,8 % | 2,7 % | 633 USD | 22 |

Con TP = 300 el «las dos» baja a 34,5 % (Tokio), 22,3 % (Londres), 50,2 % (Nueva York) y 25,6 %
(CME), y el primer TP tarda de 8 a 49 minutos. Es decir: el caso que busca la cobertura —que el
precio vaya y vuelva y **las dos** patas cobren— **sí ocurre**, entre el 22 % y el 64 % de los
días según zona y TP. Y «ninguna llega» es raro con 200 (0-2,7 %) pero ya no con 300 (hasta 11 %).

### Resultado medido, en % del margen (con comisiones), TP = 200

| variante | Tokio | Hong Kong | Londres | Nueva York | CME | liquidación de una pata |
|---|---|---|---|---|---|---|
| principal sola (1 pata) | −3,42 % | −5,20 % | −6,85 % | −5,78 % | −6,24 % | 9-17 % |
| **H1** cerrar la perdedora cuando la otra cobra | **−5,40 %** | **−5,40 %** | **−5,40 %** | **−5,40 %** | **−5,40 %** | 0 % |
| **H2** cortar la perdedora a −100 USD | −5,28 % | −5,17 % | −4,97 % | −4,67 % | −4,91 % | 0,0-0,1 % |
| **H3** dejar correr la perdedora (las dos con su TP) | −4,23 % | −5,75 % | −6,03 % | −6,50 % | −4,83 % | **19-35 %** |

Con TP = 300 no cambia de signo nada: principal −2,95 a −5,68 %, H1 −5,40 % exacto, H2 −4,36 a
−5,33 %, H3 −4,24 a −6,25 % con una pata liquidada en el 21-45 % de los días.

Lo que dicen estos números:

1. **H1 da −5,40 % del margen todos los días y gana el 0 % de las veces.** No es un resultado
   estadístico, es una identidad: si las dos patas son del mismo tamaño y se cierran en el mismo
   instante, lo que gana una lo pierde la otra y queda **solo la comisión**. Una cobertura
   simétrica no protege: cobra peaje.
2. **La única forma de que el par gane es el vaivén** (las dos patas cobran su TP), y para
   cobrarlo hay que dejar la perdedora abierta — que es H3. Entonces aparece el otro lado:
   **una pata se liquida en el 19-35 % de los días** (45 % en Nueva York con TP 300), y cada
   liquidación cuesta el 70 % del margen de esa pata. La media sigue negativa en las 5 zonas.
3. **H2 es la menos mala** (−4,4 a −5,3 %): el stop de 100 USD elimina las liquidaciones
   (0,0-0,1 %) y su mediana roza 0, pero no genera ganancia; solo reparte mejor la pérdida.
4. **La pata principal ilustra el engaño del apalancamiento alto**: gana el 69-79 % de los días
   con mediana **+7,1 a +8,2 % del margen** (y +11 a +14 % con TP 300), y su media es
   **negativa** porque el 9-21 % de los días se liquida. Con 60x, una racha de aciertos no dice
   nada sobre la esperanza: la cola se la lleva toda.
5. «Según panorama y análisis cruzados» es la pieza que decidiría **cuál** pata cerrar y cuándo:
   ahí tendría que estar todo el valor, porque las dos simétricas suman cero por construcción. Y
   el apartado 1 de esta nota dice que el patrón de apertura **no aporta esa información**
   (corr(A,B) = −0,02): no se puede heredar un criterio que no existe. Mientras no haya una señal
   medida que decida la asimetría, añadir patas solo multiplica la comisión por el número de patas.

Fuera de lo medido, dos avisos: 60x queda muy por encima de lo que admite `eim/risk` y de la
constitución F0 (el proyecto está en **solo análisis**, T145, sin dinero real), y una posición
abierta 4 h puede cruzar un cobro de *funding* (cada 8 h) que no está en estas cifras.

## Reproducir

```
python v2/scripts/descargar_1m_btc.py <salida>.parquet 2024-01-01
python v2/scripts/patron_apertura_sesion.py <salida>.parquet     # perfil + operaciones, tope 4 h
python v2/scripts/patron_apertura_canales.py <salida>.parquet     # canal y órdenes límite
python v2/scripts/patron_apertura_coberturas.py <salida>.parquet --tp 200 300   # 60x
```
