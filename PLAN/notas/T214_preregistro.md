# T214 — Pre-registro: superficie de volatilidad implícita de BTC sobre A2 de T165

Fijado el **2026-11-27**, **antes de que exista ningún resultado**: el colector de T213 hizo su
primera toma ese mismo día a las 16:37 UTC y la primera que cuenta para la evaluación es la de las
23 h UTC (día 2026-11-28). Va en un commit propio, anterior al del código. Cambiar cualquier regla
= archivo nuevo `T214_preregistro_v2.md`, nunca editar este; su SHA-256 queda en el informe
`v2/reports/t214_superficie.md`. Lo único mirado antes de escribirlo: que los rasgos se pueden
calcular sobre esa primera toma (es una sola toma: no hay pérdida ni pronóstico que mirar).

**Modo: ANÁLISIS.** Mide; no toca el cono, las bandas, `regime`, el tamaño de los stops, la
síntesis, el plan, el riesgo ni el bróker. Nunca vota dirección (◆ de T100). Aunque pasara, la
adopción es otra entrega y una ◆ del usuario, como A2 de T165.

## 1. Pregunta

¿La **superficie** de volatilidad implícita de BTC (estructura temporal, sesgo, prima por plazo)
mejora el pronóstico de la varianza realizada del día siguiente de BTCUSDT **por encima de A2**
(HAR-IV con la pendiente del DVOL, el que ganó T165)? Hipótesis nula: no. Un «no» o un «sin
potencia» son resultados válidos.

## 2. Datos

- **Cadenas:** las tomas horarias de T213 (`data/options/BTC/<día>/<HH>.jsonl.gz`, Deribit, nivel
  1, solo uso personal; viven en la portátil y **no se pueden volver a descargar**). Solo hacia
  adelante: T213 §1.5 dejó sin verificar el histórico (`history.deribit.com`) y una superficie
  rehecha con operaciones pasadas mezcla instantes; no se usa ni como contraste.
- **Toma del día `d`:** la última con `taken_ms` en **[22:00, 24:00) UTC del día `d−1`**. Si no
  hay, el día falta. **No se rellena** con una toma anterior (T165: una lectura de un día de
  antigüedad era peor que no tenerla).
- **Objetivo, M1/A2 y DVOL: idénticos a T165.** RV5 del día UTC con velas de 1 min de BTCUSDT
  perpetuo (≥ 90 % de las velas del día), reconstruidas para la evaluación desde la descarga
  pública de Binance (licencia aprobada en T88) igual que el banco `t139_banco`; DVOL de las 23:00
  de `d−1` (`eim/data/dvol.py`), IV²_d = (DVOL/100)²/365; pendiente s_d = ln IV²_d − ln IV²_{d−5}.
- **Día válido:** RV válida, retorno válido, DVOL válido, toma válida **con calidad `ok`**
  (abajo) y pronóstico de los cuatro modelos. Muestra común: si falta para uno, falta para todos.

## 3. Rasgos (`v2/eim/options/surface.py`, versión **1.0.0**)

Sobre la IV de la marca de Deribit de la opción fuera del dinero de cada precio de ejercicio
(puts K ≤ F, calls K > F; F = subyacente del vencimiento), con vencimientos de **≥ 2 días**:

| Rasgo | Definición |
|---|---|
| σ7, σ30 | σ ATM (interpolación lineal en ln K/F en F) de los dos vencimientos que rodean 7 y 30 días; entre ellos, lineal en la varianza total σ²·T. **Sin extrapolar** |
| Estructura | TS_d = ln(σ7² / σ30²) |
| Sesgo | RR_d = σ(put −25Δ) − σ(call +25Δ) a 30 días (delta forward de Black-76 a la IV de cada opción; lineal en el plazo entre los dos vencimientos) |
| Prima por plazo | VRP7_d = ln(σ7²/365) − ln RV̄⁽⁷⁾ y VRP30_d = ln(σ30²/365) − ln RV̄⁽³⁰⁾, con RV̄⁽ⁿ⁾ la media de la RV5 diaria de los n días hasta `d−1` |
| Sesgo 90/110 | σ(0,9F) − σ(1,1F) a 30 días: **solo descriptivo**, no decide |

**Calidad de la toma** (cada vencimiento usado por σ7, σ30 o el sesgo): ≥ 6 opciones fuera del
dinero; las 2 más cercanas al forward de cada lado con dos lados, sin cruzar y horquilla ≤ 25 %;
la σ ATM de la marca a ≤ 0,02 de la del precio medio (Black-76); varianza total creciente entre
los dos vencimientos de cada plazo. Todo pasa → `ok`; algo no → `degradado`; falta σ7 o σ30 →
`no_data`. **`degradado` y `no_data` no entran ni se rellenan.** (El estado por vencimiento que
guarda T213 marca `degradado` ante una sola mariposa negativa de un tick en las alas —12 de 13
vencimientos en la primera toma— y no se usa como filtro.)

## 4. Familia (3 intentos)

Referencia, no es un intento: **A2** de T165, tal cual (Log-HAR-RV + γ·ln IV² + δ·s).

| Id | Modelo |
|---|---|
| C1 | A2 + β·TS_d (estructura temporal) |
| C2 | A2 + β·RR_d (sesgo 25Δ; T165 avisó de que se atenúa desde 2024: va con su intento propio) |
| C3 | A2 + β₇·VRP7_d + β₃₀·VRP30_d (prima por plazo) |

Declarado de antemano, como en T165: con RV̄ en el diseño, la prima en logaritmos genera casi el
mismo espacio que añadir ln σ7² y ln σ30²; C3 se distingue de C1 porque deja libres los dos
coeficientes (C1 los ata a signos opuestos e iguales) y porque σ30 de la superficie no es el DVOL
(otra hora, otra construcción). Ajuste de todos: mínimos cuadrados **solo con días anteriores**,
ventana recursiva, reajuste diario, pronóstico exp(ŷ + s²/2), el mismo estimador de T165.

## 5. Métricas y regla de adopción

- **Principal:** QLIKE diaria media, L = RV/ĥ − ln(RV/ĥ) − 1. Descriptivas (no deciden): MSE,
  CRPS, PIT, cobertura del 80 % con y sin ACI (γ = 0,005, ventana 250) y peor ventana de 90 días.
- Un intento Ck **pasa** si se cumplen las cuatro:
  1. **MCS** al 10 % sobre las QLIKE de {A2, C1, C2, C3} (bootstrap estacionario, bloque de
     Politis-White, 5 000 repeticiones, **semilla 214**): Ck dentro y **A2 fuera**.
  2. **Mejora frente a A2:** IC 95 % de la diferencia media (Ck − A2) por bootstrap estacionario
     que excluye 0 por debajo, y p unilateral **ajustada por Holm en la familia ampliada** < 0,05.
     Familia ampliada = la de T95 el día de la evaluación (841 de T49 + todos los del escáner,
     **sin reiniciar**) + estos 3. Benjamini-Hochberg, informativa.
  3. **Cobertura con ACI** de la banda del 80 % en 80 % ± 2 pp en todo el tramo evaluado.
  4. **Potencia:** la mejora observada ≥ la mínima detectable con la s observada (regla de T165).
- Si pasan varios, se propone el de menor QLIKE. Si ninguno, el agente queda como **contexto en
  la interfaz** y el informe lo dice así.

## 6. Potencia y fecha de la primera evaluación

- **Mejora mínima declarada:** δ = 5 % de la QLIKE de A2 en T165 = 0,05 × 0,29450 = **0,0147**
  (fija en valor absoluto: no se mira la QLIKE de A2 del tramo nuevo para fijarla).
- **Días puntuados necesarios** (método de T163): n_k = κ_k · ((z_{1−α/m} + z_{0,80}) · s_k / δ)²,
  α = 0,05, m = familia ampliada del día de la revisión, κ_k ≥ 1 por dependencia serie
  (Newey-West con el bloque de Politis-White) y s_k la desviación de la diferencia diaria Ck − A2.
- **Calentamiento:** los primeros **250 días válidos** no puntúan (regresiones, como T165).
- **A priori** (s de T165, que es lo único que existe; ningún dato de T214): con m = 1 141
  (1 138 al 2026-11-26 + 3), z = 4,764; s = 0,2405 (A2 vs M1) → n ≈ **6 055 días puntuados**;
  s = 0,1242 (la menor publicada) → n ≈ 1 615. **Ninguno cabe antes del tope.** Para caber haría
  falta s ≤ 0,090, por debajo de toda s publicada para modelos anidados de este tipo.
- **Tope:** **2029-11-27** (tres años de tomas). Más allá no se espera: SIN POTENCIA.
- **Revisión de potencia** (una sola, con fecha fijada por datos): el día en que se cumplan **250
  días válidos** (no antes del **2026-11-28 + 250 = 2027-08-05**). Sobre esos 250 días, con
  ajustes recursivos desde el día 60, se calculan **solo** s_k y κ_k de las diferencias Ck − A2
  (días 61–250): **nunca su media, ni ninguna QLIKE**; esos días no puntúan después. Con ellas y la
  tasa de días válidos observada:
  - si algún Ck llega a n_k antes del tope, **la primera evaluación es el día en que se cumplan
    250 + mín_k n_k días válidos**, se evalúan los tres ese día y el que no tenga potencia sale
    «sin potencia»;
  - si ninguno llega, **T214 se cierra SIN POTENCIA**: no se evalúa nada, los 3 intentos **no se
    suman** a la familia (como T163) y el agente queda como contexto.
- Hasta la evaluación (o el cierre), el agente `vol_surface` corre **en sombra, como informante**:
  se ve en la interfaz y no entra en nada.

## 7. Lo que esta tarea no hace

No opera opciones ni estrategias con opciones; no da sesgo de dirección; no usa datos de pago ni
histórico reconstruido; no mide ETH (T213 solo recoge BTC con el presupuesto medido); no cambia
síntesis, plan, riesgo ni bróker.
