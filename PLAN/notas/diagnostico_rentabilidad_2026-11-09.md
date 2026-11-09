# Diagnóstico de rentabilidad (2026-11-09) — por qué ganamos más veces y perdemos dinero

**Modo: SIMULADO.** Esta nota no cambia ningún perfil, no toca la corrida de T31 y no habilita dinero real. Es solo lectura: no se ejecutó nada que escriba en `data/`.

**Pregunta del usuario (2026-11-09):** «con base en todo lo aprendido por el sistema y sus algoritmos, un análisis senior de qué está pasando para que aún no sea rentable, teniendo en cuenta que las operaciones ganadas ya superan a las perdidas».

**Respuesta corta:** el acierto del 66 % es real, pero **no es señal de que funcione: es un efecto secundario de cómo salimos**. El sistema cobra los aciertos a +0,35 R y paga los fallos a −1,07 R. Con ese reparto el punto de equilibrio está en **75,4 % de acierto**, no en 50 %. Debajo de eso, tres mediciones independientes dicen que **no hay ventaja bruta** que recuperar.

De aquí salen **T143–T146** (fase 24).

---

## 0. De dónde salen las cifras

| Fuente | Qué aporta |
|---|---|
| `GET /v2/paper/ledger.csv` de la API viva de `juanpablo-cpu`, leído el 2026-11-09 ≈ 04:40 UTC | 3 449 cierres: 411 con peso (`scope=perfil`) y 3 038 en sombra (`scope=sombra`, sin peso). De los de peso, **214 vividos** y 197 `retro` |
| `v2/reports/edge_gate.md` (T27) | Agregado fuera de muestra, 242 + 237 operaciones |
| `v2/reports/exits_ab.md` (T134) | 87 variantes de salida pre-registradas |
| `v2/reports/t136_riesgo.md` (T136) | Costo ex ante y simulación de ruina, 29 828 operaciones fuera de muestra |
| `v2/reports/t137_entrada.md` (T137) | Bruto frente a costo de las estrategias vigentes |
| `v2/reports/t139_entradas.md` (T139) | Nueve hipótesis de entrada en datos limpios; veredicto P1 |
| `v2/reports/agents_marginal.md` (T44) | Cobertura y correlación de los agentes en el panel histórico |
| `v2/reports/operation/semana_2026-W4{3,4,5}.md` (T31) | Informes semanales oficiales, calibración, incidentes |

**Aviso de método.** `pnl_usdt` vale 0 en las operaciones sin peso, así que clasificar «ganada» por `pnl_usdt > 0` cuenta como perdedoras las de sombra que ganaron. Todo lo que sigue clasifica por **`r > 0`** y separa siempre **con peso** / **sombra** / **`retro`**. Las 197 `retro` (T142) se excluyen de las cifras de resultado: se decidieron al recalcular y nadie las vivió.

---

## 1. La paradoja, en aritmética

Libro vivido con peso, **n = 214**:

| | |
|---|--:|
| Ganadas / perdidas | **142 / 72** → acierto **66,4 %** |
| R medio del ganador | **+0,349** |
| R medio del perdedor | **−1,071** |
| Cociente ganancia/pérdida | **0,33** |
| Esperanza neta | **−0,129 R** = −6,72 USDT por operación |
| **Acierto necesario para empatar** | **75,4 %** |
| **Cociente necesario con el acierto de hoy** | **0,51** |

Ganamos 2 de cada 3 veces y cada victoria vale un tercio de lo que cuesta una derrota. Faltan **9 puntos de acierto** o un **55 % más de cociente**. El patrón se repite en los cuatro perfiles, así que no es un perfil mal configurado:

| Perfil | n | Acierto | R medio | PnL |
|---|--:|--:|--:|--:|
| `agresivo` | 87 | 70,1 % | −0,069 | **−739,5 USDT** |
| `moderado` | 97 | 66,0 % | −0,118 | −336,0 |
| `ppp_btcusdt` | 23 | 69,6 % | −0,197 | −226,3 |
| `conservador` | 7 | 14,3 % | −0,794 | −136,8 |

Es exactamente lo que ya anticipó T129 con menos muestra (+0,11 R / −0,96 R, 90 % de acierto necesario). **El diagnóstico de la fase 22 se confirma con el libro en la mano.**

---

## 2. El mecanismo: la mezcla de salidas fabrica el acierto

| Salida | n | % | R medio | Aporte a la esperanza |
|---|--:|--:|--:|--:|
| **SLD** (stop desplazado / escalera) | 125 | **58,4 %** | +0,108 | **+0,063 R** |
| **SL** (stop inicial) | 66 | 30,8 % | −1,144 | **−0,353 R** |
| **TP** | 20 | 9,3 % | +1,790 | +0,167 R |
| TIEMPO | 3 | 1,4 % | −0,424 | −0,006 R |

**El 58 % de las operaciones son rasguños.** La escalera las cierra en +0,11 R (mediana de duración 37 min). Son las que fabrican el 66 % de acierto y aportan +0,06 R en total, menos de lo que cuestan en comisiones. El lado perdedor, en cambio, **no está protegido por nada**: se va al stop inicial completo, −1,14 R.

La asimetría está invertida: **truncamos los ganadores y dejamos correr los perdedores.** Aquí no es un sesgo del operador, lo hace el código.

### 2.1. Contrafactuales, y por qué uno de ellos es una trampa

Sobre las mismas entradas:

| Si… | Esperanza |
|---|--:|
| los ganadores cerraran a +1,79 R (como los TP) | +0,827 R |
| los ganadores cerraran a +0,80 R | **+0,171 R** |
| no hubiera costos | **−0,004 R** |
| los perdedores cerraran a −0,60 R | +0,030 R |
| **hoy** | **−0,129 R** |

**Los dos primeros no son alcanzables y ya está medido.** T134 probó 87 variantes pre-registradas sobre 29 828 operaciones fuera de muestra y **las rechazó todas**; la mejor dio E[R] −0,1045. Sostener a los ganadores hasta +0,8 R convierte a buena parte de ellos en stops completos, y el contrafactual no lo ve porque fija el ganador sin mover al perdedor. **La salida ya se optimizó hasta agotarla: no es ahí donde está el problema.**

---

## 3. El costo: la operación nace perdiendo el 12 % de su riesgo

| | |
|---|--:|
| Fricción total del libro vivido | **1 630,1 USDT** (comisiones 965,0 + deslizamiento 685,1 − funding 20,0) |
| Resultado neto | **−1 438,5 USDT** |
| Fricción por operación | 7,75 USDT = **14,1 pb del nocional** |
| Distancia mediana del SL inicial | **1,21 %** del precio |
| **Costo en R** | **0,125 R de media (0,116 mediana)** |

**La fricción es mayor que toda la pérdida.** Con el stop a 1,2 % y 14 pb de ida y vuelta, cada operación arranca con el 12 % de su riesgo gastado.

| Marco | Distancia mediana del SL | Costo en R |
|---|--:|--:|
| 15 m | 0,90 % | **0,157** |
| 1 h | 1,18 % | 0,123 |
| 4 h | 1,56 % | 0,091 |

Dos agujeros concretos, ambos ya medidos y ambos apagados hoy:

- **El riesgo no incluye el costo** (T136 §1): quien declara arriesgar 1 % arriesga **1,17 %**. `risk_includes_costs` está apagado. T136 dejó dicho que se enciende al cerrar T31.
- **256 de 411 entradas son `market`** (taker, 5 pb) pudiendo ser `limit` (maker, 2 pb). El resto, 155, ya son `limit`.

Corregir ambas cosas lleva el costo de 0,125 R a ~0,06 R. **Sigue sin bastar**, por §4.

> Aviso ya registrado en T139: las entradas maker **bajan el costo, no suben el bruto**, y pueden empeorarlo por selección adversa (BACKLOG T47 (1), T48b (2)). Por eso T143 lo mide antes de adoptarlo, y no lo da por bueno.

---

## 4. El problema de fondo: no hay ventaja bruta

Quitando los costos, la esperanza del libro vivido es **−0,004 R**: un empate. Con n = 214 eso es indistinguible de cero. Con muestras grandes, empeora:

- **T27** (242 + 237 operaciones fuera de muestra): Sharpe **−2,39 / −2,80**, E[R] **−0,49 / −0,51 R**, PF 0,5, DD **70 %**, retorno −70 %. Comprar y mantener en el mismo periodo: **+188 %**. Y la **entrada al azar** con el mismo SL/TP y los mismos costos dio **−0,43 R: mejor que la estrategia.**
- **T137**: la estrategia vigente tiene **bruto −0,128 R** antes de costos (lectura oficial, todos los marcos). 0 de 520 versiones llegan al mínimo de muestra de V1.
- **T139**: el mejor bruto encontrado fue **+0,012 a +0,060 R**, contra un **mínimo necesario de 0,19 a 0,50 R** según marco y muestra. Veredicto **P1: parar la búsqueda**. Faltan entre 3 y 10 veces.
- **Calibración (W45)**: acierto direccional **46,5 %** (n = 200), Brier skill **−0,2 %**, cobertura 68 % donde debería ser 80 %. La capa de pronóstico **no supera a la caminata aleatoria**, y el informe ya lo dice con esas palabras.

### 4.1. La razón mecánica: el comité vota cinco veces lo mismo

En el panel histórico de T44, **6 de 14 agentes están al 100 % `no_data`** (`calendar`, `derivatives`, `liquidations`, `microstructure`, `seasonality`, `smart_money`) y `technical` al 100 % `degraded`. Los que sí votan —`ema`, `structure`, `price_action`, `levels`, `elliott`, `regime`— **correlacionan entre sí entre 0,44 y 0,68** (Pearson, tramo de descubrimiento).

No hay un comité de 14 especialistas: hay **un seguidor de tendencia sobre velas, votando cinco veces**. La síntesis no agrega información, agrega el mismo error. Y eso también se ve en el libro: la familia `agentes` deja −215,9 R en 646 operaciones de sombra, la peor de todas.

### 4.2. El control aleatorio, leído con cuidado

En sombra (sin peso, todas las semanas):

| | n | E[R] | IC 95 % |
|---|--:|--:|---|
| `control_aleatorio` | 159 | **−0,461** | [−0,663, −0,259] |
| resto de estrategias | 2 879 | **−0,301** | [−0,351, −0,252] |

Las estrategias son **menos malas** que el azar en el libro vivo, y los intervalos casi no se solapan. **No es una prueba de ventaja**: con n = 159 el control tiene mucho error, los dos conjuntos no comparten geometría ni ritmo, y T139 ya contrastó entradas reales contra sus series sustitutas con el método correcto y no destacaron (p = 1,000 en 1 h; p = 0,429 en 4 h). Se anota porque es la única señal con signo favorable en todo el libro, no porque decida nada.

---

## 5. El dimensionamiento convierte el empate en ruina

T136 §3 lo mide sin anestesia: con las reglas de hoy y **sin frenos, los cuatro perfiles llegan a −100 % de capital** en las 29 828 operaciones fuera de muestra. El freno gradual los salva (DD 5–10 %), pero porque **deja de operar**: toma entre 7 y 147 operaciones de 29 828. El freno no arregla la ventaja, la esconde.

El libro vivido lo confirma: **las 5 peores operaciones suman −890,7 USDT, el 62 % de toda la pérdida neta**, y las 5 mejores +1 288,6. Con apalancamiento 10× en 190 de las 411 entradas, una cola mala basta.

---

## 6. Lo que contamina la medición

1. **Dos contabilidades que no cuentan lo mismo.** El informe semanal de T31 —el que decide el paso a dinero real— ve **1, 0 y 1 operación con resultado** en W43–W45 (4 en W43 contando las no cerradas); el libro de perfiles cierra **43, 30, 118 y 23** con peso en W43–W46. Solo **45 de 411** están marcadas `floor_trade`. Son universos distintos (el informe mira la corrida de operación; el libro, los cuatro perfiles) y en ningún sitio se dice cuál manda. **La decisión de capital real se está tomando con el instrumento pequeño.**
2. **Posiciones fantasma (T142).** 5 congeladas, −142,86 USDT al reconciliar, y **18 entradas marcadas `retro` que nunca se vivieron**. El arreglo ya está desplegado, pero las 197 `retro` siguen dentro del libro y hay que excluirlas de toda cifra de resultado.
3. **n = 214 no decide nada.** T49 exige ≥ 100 operaciones y ≥ 2 regímenes con ≥ 20. En vivo hay 214 repartidas entre 4 perfiles y 3 marcos. Cualquier lectura de «está mejorando» con estos números es ruido; los propios informes semanales lo dicen («no concluyente, n < 20»).
4. **La captura HFT va al 86,8 %** de horas completas (W45) con 4 reinicios. Lo que no se captura no se puede analizar después, y es justo la fuente de datos propia de §7.

---

## 7. Qué se propone (fase 24)

**El cambio de marco:** el sistema está bien construido —la instrumentación, los pre-registros y la honestidad de los informes son su mayor activo— pero está midiendo con mucha precisión una estrategia **que no tiene ventaja**. Seguir afinando salidas, pesos o perfiles es optimizar el decimal de un número negativo. T139 ya cerró la búsqueda de entradas direccionales con estos datos; lo que queda abierto, y consta como ◆ pendiente del usuario en `ESTADO_PROYECTO.md` §0, es **para qué sirve entonces el sistema**. Esta fase es esa decisión, con la aritmética delante.

| Tarea | Qué hace | Por qué |
|---|---|---|
| **T143** Dejar de pagar por nada | Entradas maker por defecto (medido, no decretado), `risk_includes_costs` encendido y marco de 15 m retirado mientras su costo siga en 0,157 R | Baja el costo de 0,125 R a ~0,06 R. No crea ventaja: deja de destruirla |
| **T144** Una sola contabilidad | El informe semanal y el libro de perfiles cuentan el mismo universo, declarado; las `retro` fuera de toda cifra de resultado | Hoy la decisión de dinero real se toma con 1 operación por semana mientras el libro cierra 118 |
| **T145** ◆ Qué clase de ventaja se persigue | Informe comparativo de costo frente a ventaja alcanzable por clase (microestructura T78–T86, arbitraje/funding, market making pasivo, o solo análisis). **No construye nada** | Es la ◆ que T139 dejó abierta. Las ventajas que sobreviven a 14 pb son de **estructura y costo**, no de predicción |
| **T146** La síntesis no suma cinco veces el mismo voto | Los agentes al 100 % `no_data` salen del voto o se alimentan; penalización por correlación efectiva y verificable | 6 de 14 no aportan nada y los que quedan correlacionan 0,44–0,68 |

**Orden:** T143 ‖ T144 (independientes, baratas, no tocan la ventaja) → **T145 ◆** (decide el rumbo) → T146 solo si T145 mantiene viva alguna línea direccional.

**Lo que esta fase NO hace:** no reabre la búsqueda de entradas (T139 P1 es vinculante), no adopta ninguna salida nueva (T134 las rechazó todas), no habilita dinero real y no toca la corrida de T31 mientras esté en marcha.

---

## 8. Reproducir este diagnóstico

```
curl -s http://127.0.0.1:8000/v2/paper/ledger.csv -o ledger.csv
```

Clasificar por `r > 0`, separar `scope`, `retro` y `weight > 0`, y agrupar por `reason`, `profile`, `timeframe` y `strategy`. El costo en R de cada operación es `(fees + slip + funding) / (|pnl_usdt| / |r|)`. El libro está abierto por la API viva, así que `data/paper.duckdb` no se puede leer en paralelo: hay que ir por la API.
