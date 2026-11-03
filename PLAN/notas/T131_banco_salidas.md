# T131 — Banco de salidas emparejado, walk-forward y pre-registro

**Modo: SIMULADO.** Fase 22, segunda tarea (después de T130). Entrega la infraestructura con la
que T132, T133 y T134 van a medir y decidir: un banco que compara cualquier política de salida
sobre **las mismas entradas**, con los mismos costos, y un **pre-registro inmutable** que fija la
rejilla, los tramos, el objetivo de selección y los criterios **antes** de calcular nada.

No se cambió ninguna salida en vivo. El bróker simulado sigue con la escalera (◆1 de T129) y
nada de este banco toca `data/`.

## 1. Qué se entregó

| Entregable de `PLAN/T131.md` | Dónde | Estado |
|---|---|---|
| 1. Interfaz pura `ExitPolicy` + M0 y M1 que reproducen T111 | `v2/eim/paper/exits/policy.py` | hecho |
| 2. Historia desde 2023 reconstruida en una COPIA, con cobertura documentada | `v2/scripts/t131_history.py`, `v2/backups/t131_banco/cobertura.md` | hecho |
| 3. Walk-forward 12 + 3 meses, paso 3, purga y embargo (E1); bootstrap por días, Sharpe deflactado y PBO; Romano-Wolf principal y Holm de referencia (E3) | `exits/walkforward.py`, `exits/stats.py` | hecho |
| 4. Control aleatorio con todas las salidas; rejilla pre-registrada con M0–M8, S1–S3, los estimadores σ y los parámetros de T136 (E12) | `exits/bench.py`, `exits/versions/prereg_t131_v1.json` | hecho (la rejilla declarada; corrible lo que existe hoy) |
| 5. Métricas de §5.3, con la devolución desde el MFE, el CVaR 95 % y el riesgo de ruina | `exits/metrics.py` | hecho |
| 6. Archivo de pre-registro inmutable con su huella, confirmado antes del primer cálculo | `exits/versions/prereg_t131_v1.json` + `exits/prereg.py` | hecho |
| 7. Objetivo de selección pre-registrado (E2) | `exits/select.py` | hecho |
| 8. Estrés de costos ×1,5 y ×2 (E4a) | `exits/costs.py` | hecho |

Fuera de alcance, como dice la ficha: implementar M2–M8 y S1–S3 (T132 y T133) y decidir (T134).

## 2. La interfaz, y por qué los adaptadores no reimplementan nada

Una política de salida es una **función pura** `simulate(idea, ctx, qty) -> Outcome`, con el camino,
los costos, las velas finas y la ficha del instrumento en `ExitContext`. M0 delega en
`simulate_ladder` y M1 en `engine.simulate`, que son **las dos funciones que llamó T111**.

Eso es lo que convierte «reproduce T111 cifra a cifra» en una propiedad comprobable en vez de una
comparación de informes: si el adaptador devuelve el mismo `Outcome` campo a campo, cualquier cifra
de T111 sale igual. Se comprueba de dos maneras:

- con fixtures, en los dos lados y con entrada a mercado y límite, con y sin costos
  (`tests/paper/exits/test_policy.py`);
- con **datos reales** de la copia, en las primeras ideas de la historia reconstruida
  (`run.engine_identity`, que el informe del banco imprime en su primer apartado).

## 3. El banco emparejado

Diseño de §5.3: todas las ideas de todas las estrategias, **tamaño fijo** (riesgo pre-registrado de
100 USDT por operación, al paso del instrumento) y **sin la memoria de los perfiles** —sin pesos,
pausas, cupos ni capital—. Sin cuenta no hay margen ni liquidación: lo que se compara es el R de la
salida. El libro completo de cada perfil sigue siendo el análisis secundario (T111).

Una idea entra en la comparación solo si **todas** las variantes la cerraron. Lo que cada salida
deja fuera se cuenta por estado, nunca se descarta en silencio.

## 4. Purga y embargo (E1), y la prueba que lo demuestra

Los tramos de prueba son contiguos y cubren todo el periodo; el que se recorta es el de ajuste:

- **purga:** fuera del ajuste toda operación que se **cierre** dentro del tramo de prueba;
- **embargo:** fuera también lo que se cierre en el hueco anterior a la prueba, de al menos la
  duración **p99** de las operaciones de la política y al menos la ventana más larga de sus rasgos
  (200 h, las `VOL_BARS` de los contextos).

La aceptación pide una prueba de que no hay fuga: es
`test_no_fit_trade_reaches_its_test_span_or_its_embargo`, con operaciones construidas a propósito
para cruzar los dos bordes, y además el informe del banco publica el recuento de fugas de la
corrida real (`leaks_total`), que tiene que ser 0.

## 5. Pruebas múltiples: por qué Romano-Wolf y no solo Holm

Las variantes de la rejilla comparten las entradas y tienen parámetros vecinos: están muy
correlacionadas. Holm no usa esa dependencia y pierde potencia, así que podría rechazar una salida
que de verdad es mejor. Romano-Wolf remuestrea **los mismos días** para todas las variantes y
corrige por pasos sobre el máximo del estadístico.

Decisión de implementación que conviene saber: el estadístico se estudentiza con un error estándar
**agrupado por día y calculado una vez** sobre la muestra original. Es lo que hace comparable el
máximo entre variantes (una escala por variante distinta en cada réplica rompería el paso del
máximo). Si Romano-Wolf y Holm discrepan, el informe lo dice, como pide E3.

Una variante con varianza degenerada (todas sus diferencias iguales) no tiene estadístico: se
informa como saltada en vez de darle una t absurda.

## 6. Objetivo de selección (E2): la regla exacta

§5.3 decía «los parámetros se eligen solo en el tramo de ajuste», pero no qué se maximiza. Queda
pre-registrado:

1. **Factible:** en el tramo de ajuste, CVaR 95 % y DD máximo no peores que la base (M0) en ESE
   tramo.
2. **Objetivo:** E[R] neto de costos entre las factibles.
3. **Centro de la meseta:** es candidata la variante cuyos vecinos a ±1 paso conservan ≥ 70 % de su
   valor **y** que a su vez conserva ≥ 70 % del mejor valor factible del tramo; entre las
   candidatas gana la que maximiza el **mínimo de su entorno**.

La segunda condición del punto 3 salió de una prueba: sin ella, la regla elegía la **peor** variante
de la rejilla, porque «mis vecinos conservan mi valor» lo cumple cualquier punto malo pegado a uno
bueno. Está en `test_without_a_plateau_nothing_is_chosen_...`.

## 7. Datos: la copia reconstruida

El hallazgo que ahorró la parte cara: en `juanpablo-cpu` los **contextos de 1 h ya cubren
2023-01-11 → hoy** (33 399 en `paper.duckdb`, llegados con la mezcla de experiencia de T117). Lo
que faltaba eran **las velas**: el almacén vivo solo tenía 1 m desde 2026-10-15, 15 m desde
2026-10-17, 1 h desde 2026-08-20 y 4 h desde 2026-05-08. Así que no hubo que regenerar ~33 000
contextos (≈ 10 h de CPU), solo descargar velas.

`scripts/t131_history.py` descarga en `v2/backups/t131_banco/` (fuera de `data/`, nunca el almacén
vivo) las velas de 1 m, 15 m, 1 h y 4 h y el funding desde 2023-01-01 con el proveedor del proyecto
(`binance-futures`, el de T111), por ventanas y escribiendo por lotes para no cargar millones de
velas en memoria. Es incremental. Al terminar escribe la cobertura **real** por serie, con sus
huecos declarados: `v2/backups/t131_banco/cobertura.md`.

Fue por la cola de trabajos (T127), en IDLE, para no tocar la captura HFT de T78.

## 8. Lo que el banco NO hace

- No decide qué salida se adopta: eso es T134 con los criterios de §5.4.
- No implementa M2–M8 ni S1–S3. Están **declarados en la rejilla** y cuentan como intentos en el
  Sharpe deflactado y en las correcciones aunque no se corran (E12): 107 intentos
  pre-registrados.
- No mide ningún rasgo de régimen: eso es T133, que además debe pasar la cota del oráculo (E6).
- No toca la salida en vivo ni `data/`.

## 9. Resultados de la primera corrida

Informe completo en `v2/reports/t131_banco.md` (+ `.json`). Pre-registro `prereg_t131_v2`, huella
`0dd3d9d8550beac0…`, 107 intentos. Ventana **2023-01-11 → 2026-08-16**, embargo 200 h, 10 pliegues,
**60 720 ideas** simuladas (1 h y 4 h, los marcos del pre-registro), **45 814 emparejadas** y
**29 828 operaciones fuera de muestra** por variante. Costos base y estrés ×1,5 y ×2. Tiempo: 18 min.

### 9.1 La escalera queda confirmada en 3,5 años, no solo en 307 operaciones

T129 describió el defecto con el libro real: 307 cierres, acierto 75,6 %, ganadora media +0,108 R,
perdedora media −0,964 R, cociente 0,11. El banco lo reproduce **fuera de muestra** sobre 29 828
operaciones y 3,5 años:

| Variante | Acierto | Gan. media | Pérd. media | Cociente | PF | E[R] | Devolución desde el MFE |
|---|--:|--:|--:|--:|--:|--:|--:|
| `M0 first_r=0.075` | 75,8 % | +0,106 R | −0,958 R | 0,11 | 0,35 | −0,151 | +0,422 R |
| `M0 first_r=0.1` (vigente) | 76,1 % | +0,127 R | −1,048 R | 0,12 | 0,39 | −0,154 | +0,446 R |
| `M0 first_r=0.25` | 70,7 % | +0,269 R | −1,176 R | 0,23 | 0,55 | −0,154 | +0,570 R |
| `M0 first_r=0.5` | 60,2 % | +0,511 R | −1,188 R | 0,43 | 0,65 | −0,165 | +0,752 R |
| `M0 first_r=1` | 50,3 % | +0,816 R | −1,179 R | 0,69 | 0,70 | −0,175 | +1,010 R |
| `M1 be=1/0.1` (salida A) | 49,2 % | +0,843 R | −1,115 R | 0,76 | 0,73 | −0,152 | +1,051 R |
| `M1 be=1.5/0` | 39,4 % | +1,307 R | −1,078 R | 1,21 | 0,79 | −0,138 | +1,085 R |

El acierto del 76 % y el cociente de 0,12 **no eran un artefacto de 17 días laterales**: salen
iguales en 3,5 años y fuera de muestra. Cuanto más se afloja la escalera, mejor el cociente y mejor
el PF, y peor el acierto: es el mismo eje que ya describía T129 (H1).

**Ninguna variante tiene E[R] > 0.** Las once pierden entre −0,138 y −0,175 R por operación, con un
costo de 0,146 a 0,186 R. El problema está en **la entrada**, no en la salida, como ya marcaban T27,
T49 y T111: ninguna salida puede arreglar un conjunto de entradas sin ventaja.

### 9.2 Pruebas múltiples: nada bate a la escalera vigente

Frente a `M0 first_r=0.1`, la mejor candidata es `M0 first_r=0.075` (ΔE[R] t = +2,27, IC 95 %
[+0,0004, +0,0056], p bruto 0,0126) y **no sobrevive a la corrección**: Romano-Wolf 0,057 y Holm
0,126. Frente a `M1 be=1/0.1`, `M1 be=1.5/0` sí pasa Romano-Wolf (0,0336 < 0,05) pero **no Holm**
(0,064): es el único caso en que las dos correcciones discrepan, y E3 obliga a decirlo. Era de
esperar que Romano-Wolf tuviera más potencia —las variantes comparten entradas y son vecinas—, y
aquí se ve en una decisión concreta.

Dicho en claro: **con la rejilla de M0 y M1 no hay ninguna mejora que aguante la corrección por
pruebas múltiples contra la salida vigente**.

### 9.3 PBO = 0,46: la rejilla ya está sobreajustada antes de T132

El pre-registro pide PBO < 0,2. Sale **0,46** con 8 tramos, 70 combinaciones y 11 variantes (logit
mediano +0,34). Es decir: la variante que gana dentro de muestra cae en la mitad mala fuera casi la
mitad de las veces. Con solo las once variantes de M0 y M1. Las 107 pre-registradas no van a
mejorar esto, y el Sharpe deflactado de las once es **0,000** (todas tienen Sharpe negativo).

Es el aviso más útil que da esta corrida para T134: **el riesgo de adoptar ruido es alto y hay que
exigir los criterios de §5.4 completos**, no «la mejor del banco».

### 9.4 El control aleatorio **falla** en la escalera ajustada (y por qué)

Criterio pre-registrado: con entradas al azar, el R **bruto** (neto + costo) tiene que ser
compatible con 0. Resultado sobre 2 820 operaciones de `control_aleatorio`:

- `M0 first_r=0.075` → bruto +0,0252, IC [+0,0040, +0,0459]: **el 0 no está dentro**.
- `M0 first_r=0.1` → bruto +0,0257, IC [+0,0036, +0,0478]: **el 0 no está dentro**.
- `M0 0.25`, `M0 0.5`, `M0 1` y las seis de M1: el 0 sí está dentro.

**Se informa como fallo, no se reinterpreta el criterio.** El diagnóstico (2 × 2 sobre las mismas
2 820 ideas, con y sin costos, con y sin velas de 1 min) descompone el sesgo en dos efectos
aditivos de ≈ +0,010 R cada uno:

| `M0 first_r=0.1`, bruto | sin velas de 1 min | con velas de 1 min |
|---|--:|--:|
| **sin costos** | +0,0059 (IC con el 0) | +0,0160 (IC **sin** el 0) |
| **con costos** | +0,0162 (IC con el 0) | +0,0257 (IC **sin** el 0) |

- **Efecto A, las velas de 1 min (≈ +0,010):** el motor solo baja al 1 min en las velas
  **ambiguas** (las que pueden subir el stop y volver a tocarlo). Con un stop de trinquete la regla
  gruesa solo puede **sub-proteger**, nunca sobre-proteger, así que resolver con el 1 min solo puede
  mejorar: la información extra entra de forma asimétrica. No es anticipación —el orden del 1 min es
  real y pasado—, es el sesgo de la regla conservadora que T111 ya medía (`fine_bias`), y el número
  con 1 min es el correcto.
- **Efecto B, la reserva de costos (≈ +0,010):** el stop de cada escalón se coloca en el precio cuyo
  **neto estimado** es el nivel, con una reserva conservadora de deslizamiento y funding. El bruto
  se mide sin costos, así que la reserva lo infla. Afecta al **bruto**, no al neto, que es con el que
  se decide.
- Los dos se encogen al aflojar la escalera (0,25 ya no es significativo, 1,0 es ≈ 0) y **M1 sale
  insesgado en las cuatro celdas** (−0,0037 a −0,0039, IC con el 0 siempre): el control funciona.
- **No hay anticipación en el código:** sobre paseos aleatorios independientes y sin costos, M0 y
  M1 dan E[R] ≈ 0 (`tests/paper/exits/test_bench.py`). Lo que el 1 min aporta sobre datos **reales**
  es dependencia serial de verdad del BTC, que un paseo aleatorio no tiene: un stop de arrastre es
  justamente una apuesta a esa dependencia (Kaminski y Lo; Lo y Remorov).

Consecuencia de método, para T132–T134: **el nulo del control está mal especificado** para una
salida dependiente del camino medida sobre la serie real. «Entradas al azar sobre la serie real»
no implica bruto 0 salvo que la serie sea una martingala. El nulo correcto es la misma salida sobre
una versión de la serie real con la dependencia serial destruida y la distribución intacta
(remuestreo por bloques o aleatorización de fases). Queda en BACKLOG T131 (8) y hay que resolverlo
**antes** de juzgar las candidatas de T132. Y, con todo, el efecto es económicamente irrelevante:
+0,026 R de bruto frente a 0,217 R de costo.

### 9.5 Estrés de costos (E4a)

Las once variantes empeoran de forma monótona con ×1,5 y ×2, y ninguna cruza a positivo. La menos
mala sigue siendo `M1 be=1.5/0` (−0,138 → −0,164 → −0,190 R). El criterio 8 de §5.4 no llega a
aplicarse, porque ninguna candidata pasa el criterio 1.

### 9.6 Purga y embargo, en cifras

0 fugas en los 10 pliegues. En el primero, de 11 130 operaciones decididas en el tramo de ajuste se
conservan 10 857: **8 se purgan por cerrarse dentro de la prueba y 265 caen en el embargo** de
200 h. Sin purga ni embargo, esas 273 habrían llevado información del tramo de prueba al ajuste.

## 10. Abierto

- Panel y despliegue: no aplica, es una herramienta de estudio, no un servicio.
- **El nulo del control** (§9.4) hay que rehacerlo antes de T132: BACKLOG T131 (8).
- La reproducción del informe de T111 sobre la copia (`scripts/t131_t111_diff.py`, con pruebas) está
  lista pero **no se corrió**: la identidad con el motor ya está demostrada campo a campo con
  fixtures y con 500 ideas reales, y el informe de T111 no es comparable cifra a cifra porque desde
  entonces el almacén ganó contextos (37 928 → 39 252). Su tramo «fuera» sí sería comparable; queda
  como comprobación opcional para T132.
- El resto, en BACKLOG T131 (1)–(7).
