# T166 — Régimen: modelo de saltos estadístico frente a HMM y BOCPD

**Modo: SIMULADO.** Fase 26. Hecho el 2026-11-11. Nada en vivo se tocó: ni el agente `regime`, ni
el riesgo, ni la ejecución, ni la corrida de papel T31.

**Veredicto: SIN POTENCIA. La hipótesis no se abre y no se construye ningún modelo de régimen.**
Con 1 037 días de evaluación, la mejora de QLIKE más pequeña que este banco puede detectar es
**0,146**, siete veces la puerta pre-registrada de 0,020 y el **35 % del nivel de QLIKE de la
referencia**. Para detectar 0,020 harían falta **≈ 55 065 días (151 años)**. Así que no se calculó
el MCS ni ninguna p: eso es lo que manda el pre-registro y lo que BACKLOG T161 (3) dejó escrito.

Las dos preguntas que **sí** se pueden contestar con estos datos se contestan, y ninguna cambia el
plan: en **persistencia** el modelo de saltos aplasta al HMM gaussiano (51,9 frente a 2,6 días de
permanencia media, §4), y sobre el **R del banco** el estado separa el banco en dos mitades
distinguibles en las que **todas pierden** (la mejor, −0,1043 R frente a −0,1538 del conjunto,
§5), igual que ya decía T133 con un oráculo perfecto.

Pre-registro: `PLAN/notas/T166_preregistro.md` (v1 en el commit `d5ae85e`, v2 en `9c6cce2`, las dos
**anteriores a cualquier cifra del banco**). Cifras: `reports/t166_regimen.json` y
`reports/t166_r_por_estado.json`.

**Gate completo verde por la cola sobre el árbol publicado** (`gate-t166-final`: 3 635 pruebas pasadas, 8 omitidas, 0 fallos, 1 847 s, rc 0) y `ruff check eim tests` limpio.

Reproducible con, desde `v2/` y por la cola:

```
python scripts/t166_regimen.py --data <ruta>/backups/t131_banco        # 264 s
python scripts/t166_r_por_estado.py --data <ruta>/backups/t131_banco
```

## 1. Qué se midió

Banco de T133 (`backups/t131_banco`): BTCUSDT, 2 019 972 velas de 1 min, cobertura 100 %
(`backups/t131_banco/cobertura.md`). **1 381 días usables** del 2023-01-22 al 2026-11-02: de los
1 403 días del camino, 1 se descarta por cobertura < 90 %, 1 es el primero (sin cierre anterior, no
tiene retorno diario) y 20 son el calentamiento de la estandarización expansiva. **Cero huecos**
entre días consecutivos en los 1 381. Tramos: ajuste inicial hasta
2023-07-01, **potencia** 2023-07-01 → 2023-12-31 (184 días) y **evaluación** 2024-01-01 → final
(1 037 días).

Familia declarada, los cinco sobre los mismos cuatro rasgos del día (retorno, log de la RV5,
eficiencia de Kaufman y rango relativo), todos causales y con reajuste cada 20 días:

| Id | Modelo |
|---|---|
| U0 | suelo sin régimen (media expansiva de ln RV) |
| M0 | **referencia:** el BOCPD de producción (`RegimeParams`), recalculado día a día |
| J1, J2, J3 | modelo de saltos K = 2 con c = 0,5 / 2 / 8 (λ = c × distancia cuadrática media) |
| H1 | HMM gaussiano K = 2, Baum-Welch |

Métrica principal: **QLIKE del pronóstico de la varianza del día siguiente condicionado al
estado**. Métricas descriptivas: persistencia de los estados y R por estado del banco.

## 2. Por qué no hay potencia (y por qué eso es el resultado)

La puerta se calculó **antes** de mirar el tramo de evaluación, con la σ de las diferencias
emparejadas de QLIKE en el tramo de potencia:

| Candidato | σ de (Mk − M0) en 2023-07 → 2023-12 |
|---|--:|
| J1 | 1,814 |
| J2 | 1,373 |
| J3 | 0,795 |
| **H1 (la peor, la que decide)** | **1,887** |

MDE = 2,4865 × 1,887 / √1 037 = **0,1457**. La puerta pre-registrada era 0,020.

El motivo es de forma, no de mala suerte. La QLIKE es L = RV/ĥ − ln(RV/ĥ) − 1, con cola derecha
larga: un día en que ĥ se queda corto por un factor 5 aporta L ≈ 2,4. Dos **etiquetadores de
régimen** se contradicen a menudo por factores así, porque cada uno pronostica la media de su
estado y los estados son gruesos. En T162, las diferencias entre su Log-HAR y el GARCH fijo tenían
σ ≈ **0,43** —dos modelos continuos y parecidos, que casi todos los días dicen casi lo mismo—,
cuatro veces menos ruido con el doble de días. Esa cifra **no está guardada**: se deduce de su IC
publicado (−0,0511 … −0,0144 con 2 135 días → σ ≈ 0,0183·√2 135/1,96 ≈ 0,43,
`reports/t162_cono_volatilidad.json`). Esa es la diferencia entre una pregunta contestable y esta.

**La consecuencia práctica:** el orden de la tabla de QLIKE de §3 no es información. El hueco más
grande que se observa (0,069 entre M0 y J1) es **menos de la mitad** de lo que haría falta para
distinguirlos, y en el tramo de potencia **el orden se invierte**. Publicar ese orden como si
dijera algo sería exactamente lo que T161 dejó prohibido.

## 3. QLIKE en el tramo de evaluación (descriptivo, no decide nada)

| Modelo | QLIKE evaluación | QLIKE tramo de potencia | media de RV/ĥ |
|---|--:|--:|--:|
| U0 (sin régimen) | 0,4125 | 0,5666 | 1,015 |
| **M0 (BOCPD de hoy)** | **0,4175** | **0,5593** | 1,056 |
| J1 (saltos, c = 0,5) | 0,3484 | 0,8095 | 1,145 |
| J2 (saltos, c = 2) | 0,4048 | 0,6931 | 1,174 |
| J3 (saltos, c = 8) | 0,3738 | 0,6223 | 1,072 |
| H1 (HMM) | 0,3669 | 0,7318 | 1,159 |
| *Log-HAR-RV de T162 (fuera de la familia y fuera del MCS)* | *0,2713* | — | — |

Dos lecturas que sí se sostienen, porque no dependen de distinguir candidatos entre sí:

- **Ningún etiquetador se acerca a un modelo continuo.** El Log-HAR-RV que T162 sí mediría para
  adoptar da 0,2713, entre un 22 % y un 35 % mejor que cualquier estado de régimen. Un estado es
  una media por grupo; no compite con una regresión sobre la volatilidad reciente.
- **Los cuatro candidatos se quedan cortos de varianza** (media de RV/ĥ entre 1,072 y 1,174;
  M0 1,056 y el suelo 1,015): la media de ln RV del estado llega tarde cuando la volatilidad
  sube, y cuanto más fino es el troceado, más tarde llega. El suelo sin régimen es el único bien
  centrado.

## 4. Persistencia: aquí sí hay un hallazgo, y es el de la literatura

La persistencia es una propiedad del etiquetador, se observa directamente y no exige distinguir
dos pérdidas ruidosas, así que esta parte sí se puede leer. Sobre los 1 037 días de evaluación:

| Modelo | permanencia media (días) | cambios | entropía normalizada | ocupación |
|---|--:|--:|--:|---|
| M0 (BOCPD) | 43,2 | 23 | 0,071 | **92,1 % en «rango»**; 4,8 % volátil; 2,5 % / 0,6 % tendencia |
| J1 (c = 0,5) | 4,6 | 225 | 0,674 | 22 % / 78 % |
| J2 (c = 2) | 10,6 | 97 | 0,425 | 25 % / 75 % |
| **J3 (c = 8)** | **51,9** | **19** | **0,132** | 62 % / 38 % |
| H1 (HMM) | 2,6 | 393 | 0,933 | 39 % / 61 % |

- **Lo que dicen Nystrup y Shu, Yu y Mulvey se reproduce en BTC a resolución diaria:** el modelo de
  saltos da estados mucho más persistentes que el HMM gaussiano con los mismos rasgos y el mismo
  K. Con c = 8, permanencia 51,9 días y 19 cambios, frente a **2,6 días y 393 cambios** del HMM.
  La penalización del salto hace el trabajo que la matriz de transición estimada no hace.
- **El HMM es inservible como etiquetador aquí:** 393 cambios en 1 037 días y entropía 0,933. Con
  el umbral del propio agente (`RegimeParams.min_dwell` = 10 velas, `max_entropy` = 0,85) sería
  «esquema de regímenes inestable». T77 planeaba un HMM: esta medición dice que, si se hace, el
  modelo de saltos es el que hay que usar.
- **El BOCPD de hoy no es un hombre de paja, pero es casi constante:** segmenta (23 cambios) y es
  el segundo más persistente, y a la vez pasa el **92 % del tiempo en una sola etiqueta**. Su
  pronóstico condicionado se parece tanto al suelo sin régimen (0,4175 frente a 0,4125) justamente
  por eso. Aviso de método: corrió con los parámetros del agente, que son de **velas** (hazard
  1/800, `min_seg` 24, `min_gap` 12); llevados al día, cada uno cubre mucho más tiempo. Un BOCPD
  calibrado a la frecuencia diaria es otro intento, con su pre-registro (BACKLOG).

## 5. ¿Condiciona el estado el R del banco? (descriptivo)

Esta pregunta **sí tiene potencia**, y se declaró así en el pre-registro. Banco de T133 con la
salida vigente (`M0 first_r=0.1`, la escalera): 60 720 ideas, 45 833 operaciones y **29 828 fuera
de muestra** en los tramos de prueba de sus 10 pliegues, con purga y embargo de 200 h —las mismas
29 828 de T133— con R medio **−0,1538** (T133 publicó −0,154 para esta serie: cuadra). Una
operación decidida el día `d` hereda el estado del día `d−1`, el último que se conoce al entrar;
las 29 828 tienen estado en los cinco modelos.

Potencia: σ del R por operación **0,5446** → para detectar Δ = +0,05 R hacen falta **734**
operaciones y hay 29 828. (El pre-registro había anotado ≈ 306 usando la σ de las *diferencias
emparejadas* que publicó T134, 0,352; la σ que corresponde a una comparación entre dos grupos es la
del nivel, 0,5446, de donde salen las 734. La conclusión no cambia: sobra historia por un factor
de 40.)

| Modelo | estado peor (n, R medio) | estado mejor (n, R medio) | ΔR | IC 95 % por bloques de día |
|---|---|---|--:|---|
| M0 (BOCPD) | `trend_up` (714, −0,1766) | `trend_down` (191, −0,0601) | +0,1165 | [+0,0145, +0,2178] |
| J1 (c = 0,5) | 1 (23 615, −0,1669) | 0 (6 213, −0,1043) | +0,0625 | [+0,0396, +0,0849] |
| J2 (c = 2) | 1 (22 797, −0,1659) | 0 (7 031, −0,1145) | +0,0514 | [+0,0284, +0,0725] |
| J3 (c = 8) | 1 (9 670, −0,1775) | 0 (20 158, −0,1425) | +0,0350 | [+0,0122, +0,0576] |
| H1 (HMM) | 1 (18 715, −0,1737) | 0 (11 113, −0,1204) | +0,0533 | [+0,0330, +0,0735] |

**Sí separa, y no sirve de nada.** Los cuatro candidatos parten el banco en dos mitades que se
diferencian entre 0,035 y 0,063 R, con IC que excluyen 0, y la mitad buena acierta más (79–80 %
frente a 74–75 %). Y **todas las mitades pierden**: la mejor de todas, el estado 0 de J1, da
**−0,1043 R** frente a los −0,1538 del banco entero. Saber el régimen del día antes de entrar
mejora algo la media y no la cruza a positivo, que es exactamente lo que T133 midió con un oráculo
**perfecto** (−0,093 R) y el motivo por el que M4 se descartó. Esto no reabre nada.

El BOCPD «gana» la tabla (+0,1165) por un artefacto que conviene nombrar: su separación es entre
dos etiquetas con **714 y 191 operaciones en 22 y 6 días**, de ahí un IC diez veces más ancho; su
etiqueta real, la que cubre el 92 % del tiempo (27 380 operaciones), está en −0,1548, es decir en
la media del banco. No separa el banco: separa dos rincones.

Tres avisos sobre esta tabla, para que no se lea como más de lo que es:

1. **El par está elegido a posteriori** (el mejor y el peor estado de cada modelo), así que el ΔR
   está sesgado al alza; con las 4 etiquetas de M0 el sesgo es mayor que con las 2 de los demás.
2. **Son cinco modelos y los IC no están corregidos por familia.** El pre-registro declaró esta
   parte descriptiva y sin regla de adopción, así que no se les aplicó Holm.
3. **El MinTRL frente a 0 es infinito** para esta serie (`mintrl_zero` nulo): con Sharpe por
   operación −0,282, ninguna cantidad de historia permitirá rechazar «media ≤ 0». El banco pierde,
   y eso no es cuestión de potencia.

## 6. Decisión

**No se construye ningún modelo de régimen y no se adopta nada.** El pre-registro pide que, si la
historia no alcanza, se cierre con ese veredicto en vez de forzar un resultado, y es lo que se
hace. Lo que queda establecido, y es más útil que un orden inventado:

1. **La pregunta, planteada así, no es contestable con los datos que hay.** Comparar etiquetadores
   de régimen por la QLIKE diaria del día siguiente exige dos órdenes de magnitud más de historia
   de la que existe. No es un «no hay efecto»: es un «no se puede ver», con número (0,146) y con
   lo que haría falta (151 años).
2. **El modelo de saltos domina al HMM en lo único medible aquí, la persistencia**, y por mucho.
   Si en algún momento se vuelve a tocar el régimen, el candidato es el modelo de saltos, no el
   HMM de T77.
3. **El camino que podría aportar algo no es el que se midió.** Un estado de régimen no compite
   con un modelo continuo de volatilidad (0,35–0,42 frente a 0,2713 del Log-HAR). La forma en que
   una etiqueta podría ayudar es **como regresor dentro del HAR**, donde la diferencia entre
   modelos es pequeña y por tanto medible. Es otro intento con su propio pre-registro (BACKLOG).
4. **Sobre el R del banco la respuesta sí se puede dar, y es la de T133 otra vez:** el estado
   separa (ΔR de 0,035 a 0,063 con IC que excluyen 0, §5) y **ninguna mitad gana** —la mejor es
   −0,1043 R—. Un oráculo perfecto de régimen daba −0,093 R en T133; un etiquetador real se queda
   a mitad de camino de un techo que ya era perdedor. El problema sigue estando en la **entrada**
   (T27/T49), que es lo que la fase 22 concluyó por cuatro vías independientes.

La ficha de T166 preveía «construir solo el ganador; si ninguno condiciona nada, se documenta y se
cierra la línea». El resultado real es un tercer caso que la ficha no preveía y que hay que decir
tal cual: **no se puede saber cuál condiciona mejor**, así que no se construye ninguno.

## 7. Límites, dicho sin adornos

- La puerta de 0,020 se fijó mirando los efectos que T162 (0,032) y T165 (0,021) **sí** habían
  encontrado. Con la σ deducida de T162 (≈ 0,43) y sus 2 135 días, su propio MDE rondaba 0,023: la
  puerta estaba al borde de lo que el mejor montaje del proyecto alcanza. No era una puerta
  caprichosa, pero tampoco holgada; con una puerta de 0,05 tampoco se habría pasado (MDE 0,146).
- Solo se midió **K = 2** (más el BOCPD de 4 etiquetas) con los **4 rasgos del día** del banco de
  T133. K = 3 y los rasgos de Shu, Yu y Mulvey (desviación a la baja y Sortino a varias semividas)
  no se probaron y son otros intentos.
- La rejilla de penalizaciones c ∈ {0,5, 2, 8} se declaró a priori y se gastó entera: tres
  intentos. Afinarla es otro intento.
- `jumpmodels` (PyPI, **Apache 2.0** por clasificador OSI y por el README; `info.license` del JSON
  de PyPI está vacío) **no se instaló**: exige `scikit-learn`, que no está en el venv. El modelo se
  implementó en NumPy siguiendo el algoritmo publicado, sin copiar código, y se probó contra fuerza
  bruta y contra regímenes sintéticos conocidos.
- La σ de la puerta se estimó con **184 días**, que no es mucho; la toma del peor candidato es lo
  conservador, pero un tramo de potencia más largo daría una estimación más firme. En todo caso la
  σ del candidato **menos** ruidoso (J3, 0,795) también deja el MDE en 0,061, tres veces la puerta:
  el veredicto no depende de esa elección.
- Solo BTCUSDT; el alcance de este trabajo es BTC por decisión del usuario (2026-11-11).
- El R por estado de §5 es **descriptivo y no puede adoptar nada**: T133 descartó M4 y T134 no
  adoptó ninguna salida. Cualquier regla condicionada al régimen exigiría entradas con ventaja
  (T27/T49) y su propio pre-registro.
