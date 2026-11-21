# T208 — La forja: perfil BTC 5 m intradía de sesión americana

Diseño completo del perfil adicional que pidió el usuario el 2026-11-21. **Modo: ANÁLISIS.** Nada
de esto opera, ni toca el libro oficial, ni cambia `params_fingerprint`.

## 1. Lo que pidió el usuario (literal)

> bitcoin, velas de 5 minutos, intradía (nada abierto de un día para otro), sesión americana,
> compras, ventas o ambas. Datos: con base en los que ya hoy recolectamos. Estrategias: genera
> miles de estrategias diferentes entre sí; utiliza todos los indicadores posibles, de todas las
> maneras posibles; agrúpalos en familias según lo que miden; varía periodos, dirección, un filtro
> opcional y la salida. Normas: cuenta de 10 000 $ sin interés compuesto, riesgo del 1 % por
> operación, apalancamiento máximo 1:10, entra siempre en la vela siguiente a la señal y descuenta
> comisión y spread realistas.

## 2. Dónde vive y qué no toca

La cantera oficial (`prereg_cantera_v1`, T170) es una familia **congelada** de 42 prospectos con
techo 50 y 8 plazas de reserva, elegidos con parámetros canónicos y **nunca mirando rendimiento**.
Meter aquí miles de recetas buscadas en la historia destruiría ese control: su `m` saltaría de 50 a
miles y sus veredictos, ya muy sensibles por decisión del usuario, dejarían de significar nada.

Por eso la forja es una **familia propia y aparte**, `forja_5m_v1`:

- Su `m` (intentos) es el número exacto de recetas enumeradas, declarado antes de medir.
- Vive en `v2/eim/forge/`, lee solo el banco histórico de T131 (copia) y escribe solo en
  `v2/reports/forge/`. No escribe en `data/paper*.duckdb` ni en el libro de la cantera.
- Un superviviente **no entra solo**: se propone con ◆ para una de las 8 plazas de reserva de la
  cantera y, si el usuario la aprueba, entra **hacia adelante** como cualquier prospecto, con su
  cuenta desde cero. La historia nunca cuenta como su rendimiento.

## 3. Los datos: lo que hay de verdad

| Serie | Qué hay | De dónde |
|---|---|---|
| Velas 1 m BTCUSDT | 2022-12-31 → 2026-11-03, **2 019 972 velas, 0 huecos**, cobertura 100 % | banco de T131, `v2/backups/t131_banco/` |
| Velas 5 m | se **agregan** del 1 m (`eim/data/aggregate.py`, solo grupos completos) ≈ 404 000 velas | derivado |
| Campos por vela | `o h l c v taker_buy_v trades` | el proveedor del proyecto (binance-futures) |
| Funding | 4 209 tasas, 2023 → 2026-11 | banco de T131 |

De esos campos sale **todo** lo que puede medir una receta: precio, rango, volumen, **delta de
agresores** (`taker_buy_v` / `v`), CVD, **tamaño medio de operación** (`v` / `trades`) y el VWAP.

Lo que **no** hay en 3,8 años y por tanto queda fuera de este perfil (se declara, no se inventa):
libro y microestructura HFT (solo desde 2026-10), interés abierto y ratio largo/corto (retención
≈ 30 d del proveedor), DVOL, liquidaciones, noticias y calendario macro. La única fecha macro que
sí entra es **la hora del día**, que es dato de la propia vela.

**Reserva (holdout) intacta:** 2026-05-04 → 2026-11-03 (≈ 6 meses, el 13 % de la historia). No se
mira hasta el final y **una sola vez**, sobre las recetas que ya hayan pasado todo lo demás.

## 4. La sesión americana, con precisión

- Zona `America/New_York`, así el horario de verano se resuelve solo (09:30 ET = 13:30 UTC en
  verano, 14:30 UTC en invierno; las dos caen en la rejilla de 5 m).
- **Sesión** = velas cuya apertura ∈ [09:30, 16:00) ET, de lunes a viernes, **sin festivos de
  NYSE** y **sin medias sesiones** (días de cierre a las 13:00 ET: se excluye el día entero para no
  mezclar sesiones de distinta longitud). 78 velas de 5 m por sesión.
- **Señales** solo en velas con apertura ∈ [09:35, 15:00) ET. La primera vela de la sesión no
  dispara (no tiene vela anterior dentro de la sesión) y después de las 15:00 no se abre nada.
- **Entrada** a mercado en la apertura de la **vela siguiente** a la de la señal.
- **Cierre forzoso** a mercado al cierre de la última vela de la sesión (16:00 ET). Nada queda
  abierto de un día para otro: hay una prueba que lo exige en todas las recetas.
- Los indicadores se calculan sobre la serie continua de 5 m (24 h), que es lo que vio el mercado;
  lo que se restringe es **cuándo se puede operar**. Las variables ancladas a la sesión (VWAP de
  sesión, rango de apertura, CVD de sesión, máximos y mínimos del día) se anclan a la **sesión
  americana**, no al día UTC.

## 5. La cuenta y las normas (las del usuario, al pie de la letra)

| Norma | Cómo se implementa |
|---|---|
| 10 000 $ **sin interés compuesto** | el tamaño se calcula siempre sobre 10 000 $, nunca sobre el capital corriente; la curva se suma en dólares, no se reinvierte |
| Riesgo 1 % | R = 100 $. Tamaño `q = 100 / \|entrada − stop\|`, con el stop que fije la salida de la receta |
| Apalancamiento máximo 1:10 | nocional `q·entrada ≤ 100 000 $`. Si el stop es tan estrecho que lo pasaría, se **recorta** `q` al tope y se marca `risk_capped`: esa operación arriesga **menos** del 1 % (el riesgo nunca sube del 1 %) |
| Entrada en la vela siguiente | a mercado en la apertura de la vela siguiente a la señal |
| Comisión y spread realistas | la tarifa única del proyecto (`eim/core/fees.py`, VIP 0 USDⓈ-M verificado 2026-10-15): **taker 5 pb**, **maker 2 pb**. Spread y deslizamiento de `CostParams`: entradas a mercado 0,1 pb (calibrado con el libro real, `reports/slippage_calibracion.md`); salidas por stop, tiempo o cierre de sesión 1 pb + 0,10·(h−l)/o + impacto por tamaño, con tope de 100 pb. El TP es orden límite → maker |
| Funding | se cobra si la posición está abierta a las 16:00 UTC (dentro de la sesión en invierno), con la tasa real del banco |
| Liquidación | a 1:10 con mmr 0,5 %, liquida ≈ 9,5 % en contra; se calcula igual y se informa si alguna receta llega a tocarla |

Dentro de una vela, si caben stop y objetivo, **se asume el stop primero** (regla conservadora ya
vigente en `eim/backtest/perp.py`). Un hueco de apertura más allá del nivel se ejecuta a la
apertura, nunca a un precio mejor.

## 6. El espacio de estrategias (esto es lo que se congela)

`receta = disparador(familia · variable · periodo · umbral) × dirección × filtro opcional × salida`

### Familias, por lo que miden

1. **Tendencia / seguimiento**: cruce de medias (MA, EMA, WMA), pendiente de EMA, giro de
   SuperTrend, giro de SAR, cruce +DI/−DI.
2. **Ruptura de nivel**: Donchian de N velas, rango de apertura (primeras k velas de la sesión),
   máximo y mínimo de la sesión anterior, cierre fuera de Bollinger, cierre fuera de Keltner.
3. **Reversión a la media**: z del cierre contra EMA o contra el VWAP de sesión, RSI, StochRSI, WR
   y CCI en extremos, distancia en ATR al VWAP.
4. **Momento**: histograma de MACD, MTM, TRIX, ROC de n velas, racha de n cierres, KDJ.
5. **Volumen y flujo de agresores**: volumen relativo a su media, MFI, pendiente de OBV, delta de
   agresores extremo, pendiente del CVD de sesión, tamaño medio de operación anómalo, EMV.
6. **Volatilidad y régimen**: compresión de ATR (ATR corto / ATR largo), estrechamiento de
   Bollinger, expansión de rango.
7. **Hora de la sesión**: apertura, media sesión, última hora (estacionalidad intradía pura).

### Las cuatro variaciones que pidió el usuario

- **Periodos**: rejilla canónica por variable (p. ej. medias 5/10/20/50/100 velas; RSI 7/14/21;
  Donchian 10/20/40; ATR 7/14; z 20/50/100), no un barrido fino: los pasos finos solo multiplican
  intentos sin añadir hipótesis.
- **Dirección**: `largo`, `corto`, `ambos`.
- **Filtro opcional** (uno o ninguno): sin filtro · tendencia de 1 h a favor (EMA 50 de 1 h) ·
  ADX ≥ 20 · régimen de volatilidad (ancho de Bollinger sobre o bajo su mediana) · lado del VWAP de
  sesión · volumen relativo ≥ 1 · sub-ventana horaria · delta de agresores a favor.
- **Salida**: ATR con objetivo en múltiplos de R ((k,m) canónicos) · trailing por ATR · tiempo
  (12 y 24 velas) · giro de la propia señal · vuelta al VWAP de sesión · solo el cierre de sesión
  con stop de protección. Todas llevan stop en ATR (así R siempre está definido) y, por encima, el
  cierre forzoso de la sesión. La salida **por giro** mira el disparador **crudo**, sin la
  dirección ni el filtro de entrada: si no, en `largo` o en `corto` nunca habría señal contraria
  que mirar y la salida degeneraría en el cierre de sesión.

El enumerador **deduplica**: dos recetas con la misma serie de señales cuentan una sola vez. El
total exacto (objetivo de diseño: **miles**, 3 000–15 000) queda escrito en el pre-registro junto a
la huella del código que las enumera, y **ese número es el `m`** de las correcciones y el
`attempts` del Sharpe deflactado.

## 7. Cómo se mide (y por qué casi nada va a pasar)

No hay «ajuste»: la rejilla está congelada antes de ver una cifra, así que no se elige nada mirando
resultados. Los pliegues sirven para la estabilidad, no para optimizar.

- **Medida primaria**: R medio neto por operación, con bloques de **un día** (la sesión es el día)
  en todos los remuestreos.
- **Corrección principal**: Romano-Wolf (StepM) sobre las `m` recetas, con el mismo remuestreo de
  días para todas. Holm y e-BH (q = 0,10) de referencia, como en la cantera.
- **Sharpe deflactado** con `attempts = m` exactos, y **PBO por CSCV** (8 tramos).
- **Criterios de supervivencia, pre-registrados:** n ≥ 200 operaciones · E[R] > 0 con
  Romano-Wolf p < 0,05 · DSR > 0,95 · PBO ≤ 0,2 · sigue en positivo con los costos ×1,5 · y solo
  entonces, **una** mirada a la reserva.
- **Control aleatorio**: entradas al azar con la misma cadencia y las mismas salidas. Debe dar
  ≈ −costo; si no, el motor está mal y no se publica nada.
- Se publica siempre, al lado del mejor resultado, **lo que la mejor de `m` recetas al azar daría
  por pura suerte** (el valor esperado del máximo nulo): es la única forma honesta de leer un
  número que salió de miles de intentos.

Con miles de intentos, el umbral del máximo nulo sube mucho: **lo esperable es que no pase nada**,
y eso también es un resultado (es lo que pasó en T49, T131 y T160). El valor de la forja no es
encontrar un ganador, es acotar cuánto hay que pedirle a un ganador para creerle.

## 8. Fuera de alcance

Operar (EIM es solo análisis, T145), tocar la cantera sin ◆, el 1 m, otros símbolos (solo BTC),
microestructura e interés abierto (no hay historia), y optimizar parámetros en pliegues.

## 9. Decisión humana ◆

1. **Antes de la primera cifra**: aprobar la rejilla y su `m`.
2. **Al final**: si algo sobrevive, aprobar (o no) su entrada en una plaza de reserva de la cantera.
