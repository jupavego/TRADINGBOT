# T210 · Retroalimentación: ¿a qué se debe el cambio de tendencia en la utilidad de los cuatro perfiles?

**Fecha:** 2026-11-23, desde `juanpablo-cpu`. **Modo: SIMULADO.** Diagnóstico de solo lectura: no se
tocó `data/`, ni los perfiles, ni la corrida de T31. Fuente: `GET /v2/paper/ledger.csv?scope=perfil`
(848 filas, 643 del universo oficial de T144) y `GET /v2/paper` a las 08:39 UTC, más
`python -m eim.analytics.audit` (tercera auditoría, `reports/audit/audit_2026-11-23.{md,json}`).

## 1. Qué cambió, con fechas

Acumulado del libro oficial (USDT, operaciones cerradas en vivo y con peso, sin `retro`):

| día (UTC) | conservador | moderado | agresivo | ppp_btcusdt | total |
|---|---|---|---|---|---|
| 11-15 | −136,8 | −570,1 | −1 381,0 | −389,2 | **−2 477,1** |
| 11-16 | −136,8 | −548,9 | −1 515,1 | −427,3 | **−2 628,1** ← suelo |
| 11-20 | −136,8 | −404,1 | −1 282,0 | −149,9 | **−1 972,7** ← techo del giro |
| 11-22 | −136,8 | −499,2 | −1 697,7 | −264,9 | **−2 598,6** |
| 11-23 | −136,8 | −495,5 | −1 697,7 | −254,7 | **−2 584,7** |

**No hay un cambio de tendencia, hay dos y se cancelan:** del 11-17 al 11-20 el libro ganó
**+655,4 USDT** (n = 154, E[R] +0,078, acierto 95 %, solo **7** topes completos) y del 11-21 al 11-22
devolvió **−625,9** (n = 67, E[R] −0,223, acierto 70 %, **19** topes completos). Por semana ISO:

| semana | conservador | moderado | agresivo | ppp_btcusdt |
|---|---|---|---|---|
| W45 | 0 (sin operar) | −168,3 | −322,2 | −152,0 |
| W46 | 0 | −201,1 | −690,7 | −144,2 |
| W47 | 0 | **+71,0** | −316,7 | **+124,3** |


**Es la misma curva que muestra el panel** (`profiles[].curve`, `paper_chart.ts`), comprobado punto
a punto: moderado 9 009 (11-16) → 9 154 (11-20) → 9 024 (11-23); agresivo 6 734 → 6 967 → 6 552;
ppp 9 316 → 9 593 → 9 489; conservador plano en 9 840 desde el 2026-10-19. Los +145 USDT de moderado
entre el 11-16 y el 11-20 son los mismos por las dos vías, así que lo de abajo explica lo que se ve.

## 2. La causa, en una frase

Los cuatro perfiles **no son cuatro apuestas, son una**: **587 de las 643 operaciones oficiales son
cortos** (91 %) y las cuatro salen por la misma escalera. Lo que mueve la utilidad no es la ventaja
—el bruto sigue en ≈ 0— sino **cuántas operaciones tocan el tope completo**, y eso lo decide el
camino del BTC. Las semanas en que el precio baja sin rebotar no hay topes y la escalera cobra; en
cuanto hay vuelta en V, un tope borra 5,6 ganancias.

Las cifras que lo sostienen:

- **Asimetría de la escalera (W47):** acierto 86,7 %, ganancia media **+0,141 R**, pérdida media
  **−1,091 R**, equilibrio **88,5 %**. Falta 1,8 puntos de acierto para empatar, no ventaja.
- **El signo de la semana lo ponen los topes:** W47, **29 de 233** operaciones con tope completo =
  **−1 611 USDT** frente a **+1 490** de las otras 204 → −121 netos. W46, 33 de 217 = −2 016 frente a
  +980 → −1 036. Un tope completo cuesta de media **−64,6 USDT** y una ganancia deja **+11,5**.
- **El camino del precio:** los días con |variación| ≥ 2 % dejan **−222,4 USDT** de media y los demás
  **−49,7** (27 días). El giro coincide con la bajada sin rebote 64,8k → 60,0k (11-17 → 11-20: 91-98 %
  de acierto) y la devolución con el suelo en V del 11-21 (57,9k) y el +4,2 % del 11-22.
- **Por qué solo cortos:** el veto «contra la tendencia del marco mayor» es el 1.º o 2.º motivo de
  rechazo de los tres perfiles activos (241, 426 y 288 rechazos) y la tendencia mayor lleva bajando
  desde finales de octubre.

## 3. Lo que NO lo explica (comprobado)

- **No es un despliegue.** `cost_params` es **idéntico en las 643 operaciones** desde el 10-21; los
  cambios de `rules_version` son la huella de los pesos del aprendiz, no una versión nueva. El
  reinicio del 11-18 a las 14:38 UTC entró T179 (variante `t143`, corrida aparte) y T176: ninguna
  toca el libro oficial.
- **No es el costo.** Costo por operación plano: moderado 0,119 → 0,123 R, agresivo 0,146 → 0,140,
  ppp 0,126 → 0,111. Lo que se movió es el **bruto** (moderado +0,070 → +0,091 R; ppp +0,054 → +0,166).
- **No es la rotación del aprendiz, casi.** Descomposición de ΔE[R] W46 → W47 (+0,0485):
  **mezcla de estrategias +0,0147** (6 estrategias desaparecen, con E[R] −0,193 en n = 31, y entran 16)
  y **misma estrategia, mejor resultado +0,0338**. Controlando por régimen: mezcla **−0,0149**,
  mismo régimen **+0,0634**. Dicho de otro modo: ~70 % es el mercado, ~30 % la retroalimentación.
- **No son pérdidas aparcadas.** Solo moderado tiene posiciones abiertas, con −38,8 USDT no
  realizados; agresivo y ppp no tienen ninguna. El giro no es un adelanto de ganancias.
- **El tamaño no mejoró, se encogió.** Riesgo por operación de agresivo: 105,2 → 67,6 USDT por 1 R
  (W43 → W47) porque su capital cayó a 6 552 (−34,5 %). Amortigua las dos direcciones; no es ventaja.
- **Conservador no cambió de tendencia: no tiene tendencia.** 7 operaciones, todas anteriores al
  2026-11-02, congelado en −136,8 USDT. Su línea es plana porque su regla («solo lo ya probado, ≥ 10
  operaciones con expectativa positiva») no la cumple nada: **5 568 rechazos «en observación»** y 1
  idea tomada en toda la corrida.

## 4. Lo honesto: el giro no es medible

- ΔE[R] W46 → W47 = **+0,0485 ± 0,0845** (IC 95 %, t = 1,12). En USDT, **+4,25 ± 5,19 por operación**
  (t = 1,61). Ninguno se distingue de cero.
- Con la varianza de la escalera (sd 0,456 R) y ~230 operaciones por semana, la **diferencia mínima
  detectable** entre dos semanas es **0,121 R/op** (80 % de potencia, 5 % bilateral). Para detectar el
  +0,0485 observado harían falta **1 388 operaciones por lado ≈ 12 semanas**.
- Conclusión: **una lectura semanal de la utilidad por perfil no tiene potencia**. Es la cuarta trampa
  de T175 en otra forma (leer una cifra por su número de operaciones y no por su muestra efectiva), y
  es exactamente lo que invita a hacer la curva del panel.

## 5. Dos cosas que hay que saber antes del cierre de T31

1. **La pendiente reciente coincide, el nivel no.** La curva del panel y el libro oficial de T144 se
   mueven igual día a día (los +145 USDT de moderado del 11-16 al 11-20 salen de las dos), pero el
   **nivel** —y con él la rentabilidad y el drawdown que se leen en la ficha— sale del libro
   recalculado del bróker, no del fijo. T195 arregló el bloque `balance` del panel; las fichas por
   perfil y la curva (`paper_profiles.ts`, `paper_chart.ts`, `profiles[].realized/return_pct`) siguen
   con la otra base:

   | perfil | oficial T144 | libro completo (con `retro`) | ficha del panel (`realized`) |
   |---|---|---|---|
   | conservador | −136,8 | −210,6 | −160,0 |
   | moderado | −495,5 | −291,2 | −937,4 |
   | agresivo | −1 697,7 | −2 188,3 | −3 448,3 |
   | ppp_btcusdt | −254,7 | −369,6 | −511,5 |
   | **total** | **−2 584,7** | **−3 059,7** | **−5 057,1** |

   Agresivo es −17,0 % del capital inicial por el libro oficial y −34,5 % en la ficha. Para juzgar «si
   mejora o empeora» da igual; para el informe de cierre de T31, no.
2. **El próximo cambio de tendencia ya está programado:** el **2026-11-28 00:00 UTC** se encienden
   solos `risk_includes_costs` (tamaño ×0,8522) y el freno gradual (×0,5 desde −5 %, ×0,25 desde
   −10 % del capital de ese instante), más «lo vivo manda» (T182). Con agresivo en −34,5 % y moderado
   en −9,8 %, eso recorta tamaño el primer día. Cualquier lectura que cruce esa fecha mezcla dos
   reglas distintas.

## 6. Qué se abre

- **T210** (fase 25): publicar la utilidad por perfil con su potencia y su descomposición, para que
  ni el panel ni el informe semanal inviten a leer una tendencia que no existe.
- BACKLOG bajo T159: el vacío de conservador, la doble curva del panel y el corte del 11-28.

Nada de esto reabre T145 (D, solo análisis) ni T139 (P1): el bruto sigue en ≈ 0 y ninguna cifra de
aquí es una ventaja.
