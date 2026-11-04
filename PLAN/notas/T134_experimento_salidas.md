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

Pendiente de completar con la corrida (ver `v2/reports/exits_ab.md`).

## 6. La pregunta ◆

Pendiente de formular con las cifras delante: «¿Qué salida y qué tamaño adoptan los perfiles?»
