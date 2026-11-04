# T134 — Experimento pre-registrado de salidas y decisión de adopción

**Modo: SIMULADO. Nada de esta tarea habilita dinero real.** Fase 22, la tarea que decide. Corre
en el banco de T131 la rejilla pre-registrada completa, aplica los ocho criterios de §5.4 de
`PLAN/notas/T129_sl_dinamico.md` tal cual y lleva la pregunta ◆ al usuario.

Informe de cifras: `v2/reports/exits_ab.md` (+ `.json` y `.csv`). Se reproduce con una orden:

```
python scripts/t134_exits_ab.py --data backups/t131_banco
```

## 1. Lo que cambió en el pre-registro, y por qué

`prereg_t131_v3` es la versión del experimento. Cambia **tres cosas** respecto a la v2, y ninguna
más. La v1 y la v2 quedan publicadas e intactas, con sus huellas fijadas en `prereg.py`.

### 1.1 Las políticas de T132 pasan a implementadas

M2, M3, M5, M6, M7, M8 y S1 están construidas y probadas, así que dejan de ser «pendientes» y
entran en la corrida. Son 89 variantes corribles de las 107 pre-registradas.

### 1.2 M4 pasa a descartada, y sus intentos **siguen contando**

T133 midió su cota del oráculo y no cumple los criterios 1–3 ni conociendo el régimen con certeza.
Lo que no se hace es descontar sus 2 combinaciones del recuento de intentos: **declararlas ya fue
un grado de libertad gastado**, y quitarlas abarataría la corrección por pruebas múltiples a
posteriori, que es justo lo que el pre-registro existe para impedir. Se mantienen los 107.

### 1.3 El criterio 6 se redefine: el nulo del control estaba mal especificado

Esto es lo más importante de la v3, y viene de BACKLOG T131 (8).

El nulo de la v1 y la v2 pedía que el R **bruto** de unas entradas al azar contuviera el 0. Eso
solo se cumple si la serie es una **martingala**. El BTC no lo es a 15 min, y un stop de arrastre
es *precisamente* una apuesta a esa dependencia (Kaminski y Lo; Lo y Remorov). Medido en T131: la
escalera ajustada daba +0,025 R de bruto con el 0 fuera del intervalo **sin que hubiera ninguna
anticipación** —sobre paseos aleatorios independientes y sin costos da 0—. Con ese nulo, el
criterio rechazaba por una propiedad del mercado, no por un defecto del código. Y T132 acababa de
añadir cinco políticas con arrastre, así que el problema iba a multiplicarse.

El nulo nuevo conserva **la distribución de los retornos** y destruye **la dependencia**: se
barajan los log-retornos de las velas de 1 min reales, se rehace el camino de 15 m **agregando**
desde ellas —no con mechas inventadas, que ya sesgaron una medición en T132— y las entradas al
azar se generan sobre ese camino con la misma geometría y los mismos costos. Se rechaza la salida
si su bruto destaca sobre esa distribución (p de una cola < α). Una prueba demuestra que sobre las
sustitutas un arrastre tiene bruto ≈ 0, que es lo que justifica el nulo.

### 1.4 Dos huecos de la propia v3, cerrados antes de calcular nada

Al implementar el experimento aparecieron dos grados de libertad que la v3 no fijaba. Los dos se
cerraron en la misma versión y **antes de calcular ningún resultado con ella**; el historial de git
lo muestra.

- **La salida de referencia de E5.** El cuantil del MAE de las ganadoras necesita una definición
  fija de «ganadora», y no la había nombrado. Es `M1 be=1/0.1` (`winners_mae.reference`): no es
  ninguna de las candidatas que usan el cuantil, así que no hay circularidad, y sus ganadoras
  corren hasta el TP, de modo que su MAE refleja el retroceso que aguanta una operación que acaba
  bien. Con la escalera como referencia pasaría lo contrario: sus ganadoras cierran a +0,1 R y su
  MAE diminuto daría stops ajustadísimos, que es el defecto H1.
- **El acompañante de S1 y M8.** Las dos cambian la **geometría del SL inicial**, no la salida, así
  que necesitan una que las acompañe, y con cuál es un grado de libertad. Es M0 con sus valores
  vigentes (`initial_stop.companion`): así la comparación contra la base M0 aísla exactamente lo
  que cambian, con la misma salida a los dos lados, y responde la pregunta útil —¿mejora apartar el
  stop inicial la salida que el sistema de verdad usa?—.

## 2. Tres defectos que habrían falseado el experimento

Medir el coste por familia **antes** de lanzar la corrida completa destapó tres cosas. Las dos
primeras dejaban variantes pre-registradas **inertes**: T134 habría informado de políticas que no
hacían nada creyendo que medía las suyas.

| Defecto | Qué pasaba | Efecto |
|---|---|---|
| El piso de ruido lo decidía el redondeo al tick | El piso se medía sobre el candidato **ya redondeado**, y como el redondeo va en contra del operador, una variante con `k` igual al piso quedaba siempre por dentro: el stop **no se movía nunca** | 15 variantes de M2 inertes; con k=2 y piso 2σ, 0 movimientos, 55 221 velas recorridas en balde por idea y 28 de 60 operaciones sin cerrar. 276,5 s → 0,0 s por variante |
| La barrera de tiempo con `min_r = 0` nunca disparaba | La condición era «avance < 0», imposible porque el avance está acotado en 0 | 3 variantes de M6 midiendo «no cerrar nunca». 26,3 → 0,09 ms por idea |
| El chequeo de vela ambigua no miraba el piso ni el trinquete | Bajaba a las velas de 1 min aunque el stop no pudiera moverse | Coste inútil en el camino caliente |

El piso ahora se mide sobre el candidato **sin redondear** (el tick es precisión del instrumento,
no una decisión de la política), `min_r = 0` significa **sin excepción** —la barrera vertical sin
objetivo de beneficio— y la vela es ambigua solo si el stop *podría* moverse ahí.

En total, **18 de las 89 variantes estaban inertes**, y el experimento completo pasó de ~200 horas
a unos 45 minutos de cómputo.

## 3. Cómo se corre, y por lotes

La rejilla se corre **por lotes** porque el banco guarda una operación por idea y por política, y
las 89 a la vez serían millones de objetos en memoria. Eso traía un riesgo que una prueba atrapó:
el conjunto emparejado de `bench.run` es la **intersección de todas** las políticas de la corrida,
así que las cifras de una variante dependían de con quién le tocaba lote (la base daba n=112 con
el lote completo y n=121 en lotes de uno). Habría invalidado el experimento entero.

Ahora cada variante se mide sobre las ideas que **ella** cerró, y cada comparación contra una base
sobre las que cerraron **las dos**, con su propio n a la vista. Una prueba compara lotes contra
corrida completa y exige que no cambie ni una cifra.

## 4. Lo que este experimento NO puede hacer

- **No aprueba nada.** El criterio 7 de §5.4 es prospectivo —≥ 4 semanas en papel con la potencia
  calculada— y su dato nace en T135. Lo máximo que una variante puede ser aquí es **candidata a
  T135**, que es un estado propio y no lo mismo que «pendiente» de algo que no se pudo medir.
- **El libro completo** del diseño secundario de §5.3 solo es calculable para M0 y M1, las dos
  salidas que `paper/book.py` sabe ejecutar. Para las demás exige conectarlas a los perfiles, que
  es T135 y está fuera del alcance de T134. Se informa así, no se omite.
- **S2** (cierres parciales) y **S3** (riesgo de cartera) no se corrieron: la primera necesita
  permiso del usuario (◆2 de T129) y código que T132 no construyó; la segunda es de T136. Las dos
  cuentan como intentos.
- **Nada habilita dinero real:** sigue haciendo falta la puerta de edge (T27) y las semanas de
  papel (T31).

## 5. Resultados

89 variantes corridas sobre 60 720 ideas, ventana **2023-01-11 → 2026-07-11**, 10 pliegues,
embargo 200 h, **29 828–29 846 operaciones fuera de muestra** por variante. 53 min de cómputo.

### 5.1 El veredicto: 87 de 87 rechazadas

Ninguna variante es adoptable. Por familia, el primer criterio que falla:

| Familia | n | Falla | Mejor variante | E[R] fuera de muestra |
|---|--:|---|---|--:|
| M0 escalera | 4 | criterio 1 (4) | `M0 first_r=0.075` | −0,1508 |
| M1 sombra | 5 | criterio 1 (5) | `M1 be=1.5/0` | −0,1383 |
| M2 volatilidad | 45 | criterio 1 (45) | `M2 k=4 atr14 activate=1` | −0,1442 |
| M3 estructura | 4 | criterio 1 (4) | `M3 fractal=3 piso=2` | −0,1513 |
| M5 híbrida | 12 | criterio 1 (12) | `M5 a=1.5 b=0 trail=M3` | −0,1441 |
| M6 tiempo | 6 | criterio 1 (6) | `M6 bars=16 min_r=0` | −0,1473 |
| M7 marco mayor | 2 | criterio 1 (2) | `M7 confirm=1` | −0,1680 |
| **M8 cuantil del MAE** | 3 | criterio 1 (1), **criterio 2 (2)** | **`M8 q=0.95`** | **−0,1045** |
| S1 SL con piso | 6 | criterio 1 (6) | `S1 d_min=3 atr14` | −0,1344 |

Bases: `M0 first_r=0.1` −0,1538 (acierto 76,1 %, PF 0,386) y `M1 be=1/0.1` −0,1525 (acierto
49,2 %, PF 0,731).

### 5.2 Lo que sí encontró: el stop inicial, no el arrastre

Las **únicas dos** variantes que pasan el criterio 1 son de M8, y la segunda mejor de todo el
banco es de S1. Las dos cambian **la geometría del SL inicial**, no la regla de arrastre. Y M8
muestra un patrón monótono: cuanto más se aparta el stop, mejor.

| Variante | E[R] | ΔE[R] vs M0 | IC 95 % | p Romano-Wolf | DD máx. R | CVaR 95 % |
|---|--:|--:|---|--:|--:|--:|
| `M0 first_r=0.1` (base) | −0,1538 | — | — | — | 4 591 | −1,350 |
| `M8 q=0.8` | −0,1404 | +0,013 | — | no pasa | — | — |
| `M8 q=0.9` | −0,1194 | **+0,0345** | [+0,0298, …] | **0,0002** | 3 565 | −1,274 |
| `M8 q=0.95` | **−0,1045** | **+0,0493** | [+0,0435, …] | **0,0002** | **3 121** | **−1,241** |
| `S1 d_min=3 atr14` | −0,1344 | +0,019 | — | no pasa | — | — |

`M8 q=0.95` mejora la esperanza en +0,049 R por operación, el drawdown de 4 591 a 3 121 R y la
cola (CVaR de −1,350 a −1,241), **y aguanta el estrés de costos**: con el deslizamiento de los
stops ×1,5 su Δ sube a +0,0595 (p 0,0002). Es coherente con Lo y Remorov: al alejar el stop, la
misma pérdida en R cuesta menos en costos.

### 5.3 Por qué ni siquiera esa se adopta

`M8 q=0.95` falla tres de los ocho criterios:

- **Criterio 2:** el cociente ganancia/pérdida se queda en **0,11** (se exige ≥ 0,50) y el PF en
  **0,475** (se exige ≥ 1,15 × 0,731 = 0,841). Apartar el stop inicial mejora la media y la cola,
  pero **no cambia la forma de las operaciones**: las ganadoras siguen siendo diminutas.
- **Criterio 4:** 10 de 10 pliegues con Δ > 0, pero **2023 falla**. La mejora no aguanta todos los
  años naturales.
- **Criterio 5:** no forma meseta. El PBO sí pasa (**0,129** < 0,20), que es una mejora real sobre
  el 0,46 de T131 y se explica porque T131 medía con once variantes casi idénticas.
- Y sobre todo: **sigue perdiendo** −0,1045 R por operación.

### 5.4 El criterio 6 queda validado

Todas las variantes medidas pasan el control contra el nulo por sustitutas (p = 0,62 y 0,67): el
bruto observado (+0,026) queda **por debajo** del nulo (media +0,045, p95 +0,098). El «fallo» que
T131 veía era la mala especificación del nulo, no un defecto del banco. Es la confirmación de que
el arreglo de BACKLOG T131 (8) era necesario y suficiente.

### 5.5 Insumos de potencia para T135 (E9)

Desviación típica de las diferencias emparejadas por operación de `M8 q=0.95` frente a M0:
**0,352 R**. Con ese dato, detectar su Δ de +0,0493 R con α = 0,05 a una cola y potencia 0,80
exige **≈ 315 operaciones emparejadas**:

```
n = (z_0,05 + z_0,20)² · σ²/Δ² = 2,4866² · (0,352/0,0493)² ≈ 315
```

El banco cierra 230 operaciones por semana, pero **con tamaño fijo y sin cupos**: el ritmo real
por perfil hay que tomarlo del libro en vivo, y es mucho menor. Sin ese ritmo no se puede traducir
315 operaciones a semanas, y esa traducción es parte de T135.

## 6. La pregunta ◆

**¿Qué salida y qué tamaño adoptan los perfiles?**

Lo que la evidencia sostiene, y lo que no:

- **Ninguna salida de la rejilla cumple §5.4**, así que la respuesta por defecto es **no adoptar
  ninguna**: los perfiles siguen con la escalera (M0), que es lo que ◆1 de T129 ya decidió como
  referencia provisional. No hace falta hacer nada para que eso siga.
- **Lo único con señal es apartar el SL inicial** (M8 y S1). Mejora la esperanza, el drawdown y la
  cola, y aguanta el estrés de costos y la corrección por pruebas múltiples. Pero falla el
  cociente, el PF, el año 2023 y la meseta, y sigue perdiendo. **Llevarlo a T135 sería medir en
  papel algo que ya sabemos que pierde**; lo honesto es tratarlo como lo que es: una indicación
  para **T136** (riesgo por operación con costos) y para **T49** (versiones nuevas de las
  estrategias con stops más amplios), no una salida que adoptar.
- **El tamaño** no se decide aquí: T136 lo mide en el mismo banco, y con E[R] ≤ 0 el freno de
  Kelly da tamaño cero (§2.1). Mientras la entrada no tenga ventaja, aumentar el tamaño solo
  aumenta la pérdida.

Y la lectura de conjunto de la fase 22, que es el resultado más sólido que deja: **cuatro
mediciones independientes apuntan a la entrada, no a la salida.** El PBO de T131, el oráculo de
régimen de T133, las 87 variantes de aquí, y el hecho de que la única mejora real sea geométrica
(apartar el stop) y no de la regla de salida. La fase 22 ha hecho su trabajo: ha descartado con
pruebas que el problema esté en cómo se sale.
