# T144 — Una sola contabilidad: el informe semanal y el libro cuentan lo mismo

**Modo: SIMULADO.** No cambia ninguna regla de operación ni habilita dinero real: cambia **qué se
mide y qué se publica**. Fecha: 2026-11-09, `juanpablo-cpu`, worktree `t144-contabilidad`.

## 1. El problema, medido

`PLAN/notas/diagnostico_rentabilidad_2026-11-09.md` §6: el informe semanal de T31 —el que decide
el paso a dinero real— veía **1, 0 y 1** operación con resultado en W43–W45 mientras el libro fijo
de los cuatro perfiles cerraba **43, 30, 118 y 23** con peso. Eran dos universos (el informe mide
el carril de ejecución del servicio; el libro, los perfiles del bróker simulado) y **en ningún
sitio se decía cuál manda**. Además, **197 de 421** filas de perfil están marcadas `retro` y
entraban en cualquier cifra que no las excluyera a mano.

Leído del libro vivo el 2026-11-09 (`GET /v2/paper/ledger.csv`, 3 505 filas: 3 084 de sombra y
421 de perfil; todas `origin = vivo` y todas con peso):

| Semana | Filas de perfil en el tramo | Cuentan | `retro` |
|---|--:|--:|--:|
| 2026-W43 | 161 | **43** | 118 |
| 2026-W44 | 87 | **30** | 57 |
| 2026-W45 | 140 | **118** | 22 |
| 2026-W46 (en curso) | 33 | **33** | 0 |

**Qué es exactamente una fila `retro`:** la que el libro registró más de 2 h después del cierre
(`ledger.RETRO_MS`). No son solo las de T142: por fecha de registro son 27+27 del estreno del
libro (21 y 22 de octubre), 14+56+3+45 de los días en que el libro se puso al día (27, 28, 29 y
30 de octubre), 2+4 (1 y 3 de noviembre) y **19 de la reconciliación de T142** (6 y 7 de
noviembre). Retardo mediano 34 h, máximo 275 h. Lo que tienen en común, y por lo que no cuentan,
es que **no hay constancia de que se vivieran cuando se cerraron**: las decidió un recálculo
posterior. La regla publicada lo dice con esas palabras, no «son de T142».

## 2. Las dos ◆ del usuario (2026-11-09)

1. **Universo oficial de T31: el libro de los cuatro perfiles, excluyendo `retro`.** La corrida de
   operación del servicio queda como **vista declarada**, no como la cifra que decide.
2. **Se reexpresan W43–W46 añadiendo la lectura corregida junto a la original**, sin borrar nada.

## 3. Inventario: quién publicaba una cifra de resultado, y con qué definición (entregable 1)

| Sitio | Qué publicaba antes | Qué hace ahora |
|---|---|---|
| Informe semanal `eim/operation/weekly.py` | R medio, acierto y R total de los `LiveTrade` del carril de ejecución. Sin decir el universo | Publica `official` (libro, universo declarado) **y** `operation_view` etiquetada como vista |
| Render `eim/operation/report.py` | Una tabla «Resultados» con `n` y «con resultado» | Tabla «Resultados (universo oficial)» con universo, recuento, exclusiones, `retro` y huella; la del carril va debajo rotulada «NO es la cifra oficial» |
| Panel `eim/paper/desk.py` + `summary.py` | Capital, acierto y DD de la vista recalculada, que incluye las `retro` | La vista sigue siendo la mecánica del motor; el panel añade el bloque `accounting` del **libro**, que es la cifra oficial |
| Libro `eim/api/paper.py` (`/ledger`, `/ledger.csv`) | Filas crudas, sin veredicto: había que excluir `retro` a mano (lo hizo el diagnóstico) | Cada fila lleva `counts_as_result` y el CSV, dos columnas más; la respuesta lleva la regla y el recuento |
| Escuadrón `eim/bots/scorecard.py` | Puntúa en **sombra** y no lo decía | Declara `universe = sombra`, `counts_as_result = false` y cuál es el oficial |

No había ninguna otra pieza leyendo `paper_ledger`: la tabla solo la consumían las rutas de la
API (`grep` sobre `eim/`).

## 4. Lo que se construyó

- **`v2/eim/paper/universe.py`** — la única función que responde «¿esta operación cuenta como
  resultado?» (`counts_as_result`), con la regla escrita dimensión a dimensión (alcance, origen,
  perfil, peso, `retro`, cierre y entradas de suelo), los códigos de exclusión con su explicación,
  `tally()` (cuántas existen, cuántas cuentan, por qué quedan fuera las demás) y `declaration()`,
  que es lo que se publica. Los perfiles salen de `paper.params.PROFILES`, no de una lista a mano.
- **`v2/eim/paper/accounting.py`** — las cifras, calculadas **solo** sobre `result_rows`: acierto,
  esperanza, IC95, PnL, costos, drawdown (con su base declarada; en porcentaje solo si todas las
  filas guardan `capital_before`), por perfil, entradas de suelo, las `retro` aparte con el dinero
  que **no** suman, y `counted_digest`, la huella de exactamente qué operaciones entraron.
  `cuadre()` compara dos lados por `ledger_id` y dice qué falta, qué sobra y qué difiere.
- **Informe semanal** — `compose(..., book_rows=...)` publica `official` + `operation_view`;
  `acceptance` dice el universo y el recuento. Sin libro, el informe **lo declara y no publica
  cifra oficial** (nunca la sustituye por la del carril).
- **API** — `GET /v2/paper/accounting` (cifras oficiales, con regla y recuento), `/ledger` con
  veredicto por fila, `/ledger.csv` con `counts_as_result` y `exclusion`.
- **Panel** — `v2/eim/web/src/paper_universe.ts`: franja «Universo oficial» junto a la de alcance
  de T118, con el recuento, las exclusiones, las `retro` y la regla entera. `tsc --noEmit` limpio;
  verificado en el navegador con las 421 filas reales (API temporal en 8011 + Vite en 5174, sin
  tocar los servicios vivos): «cuentan 186 de 363 · acierto 71 % · R medio −0,19 · PnL −1 969,10
  USDT» para BTCUSDT, con «Quedan fuera 177 de 363: retro 177».
- **Reexpresión** — `python -m eim.operation.restate`, que añade un bloque delimitado al informe
  ya publicado (o un archivo aparte si la semana aún no tiene informe) y escribe las cifras en
  JSON. Repetirlo reemplaza solo ese bloque.

### Lo que cambió la revisión de código (`code-review`, medio)
1. **La comparación con el backtest mezclaba símbolos.** La línea del universo oficial comparaba
   el agregado del libro contra la esperanza del **primer** símbolo con línea base. El universo es
   el libro, que puede cubrir varios símbolos, y T27 tiene una esperanza por símbolo: ahora la
   cifra declara qué símbolos incluye y **solo compara cuando hay uno**; con más de uno lo dice y
   no compara.
2. **Una fila que no declara `retro` ya no cuenta** (código `sin_declarar`). Antes, un diccionario
   sin esa columna pasaba como «vivido» por omisión, que es justo el agujero que T144 cierra.
3. **El recuento de entradas de suelo reimplementaba la lectura del booleano**; ahora usa la misma
   (`universe.flag`) que el resto de la regla.

### Movido de sitio
`fee_rate` y `hft_qc` pasaron de `operation/supervisor.py` a `operation/report.py` (son material
del informe, no del servicio) para que el supervisor siguiera cabiendo en 300 líneas.

## 5. Pruebas

| Archivo | Qué fija |
|---|---|
| `tests/paper/test_universe.py` (12) | La regla caso a caso: `retro` nunca cuenta (venga como `True`, `"true"` o `1`), sombra, sin peso, reconstruida, perfil desconocido, sin cierre; entradas de suelo sí cuentan y se informan aparte; el recuento y la declaración |
| `tests/paper/test_universe_single.py` (6) | **La guardia**: quien publica importa `eim.paper.universe`; **nadie fuera** de `universe.py`, `accounting.py` y `ledger.py` lee la columna `retro` por su cuenta (AST); el informe declara universo y recuento en JSON y en Markdown; sin libro no hay cifra oficial |
| `tests/paper/test_cuadre_w43_w46.py` (7) | **Cuadre con los datos reales** de W43–W46 (`tests/fixtures/paper/ledger_w43_w46.csv`, 421 filas): el informe y el libro cuentan lo mismo semana a semana, la huella coincide, y si falta o sobra una operación el cuadre **la nombra** |
| `tests/operation/test_restate.py` (4) | La reexpresión conserva lo publicado palabra por palabra, es idempotente y usa la ventana de cada semana |
| `tests/api/test_paper_api.py` (+1) | `/ledger`, `/ledger.csv`, `/accounting` y el panel declaran el universo; ninguna fila `retro` cuenta |

## 6. Lo que cambia en las cifras publicadas

W43–W46 reexpresadas y publicadas en `v2/reports/operation/` (originales intactas, bloque
`<!-- T144:reexpresion -->` debajo, más `semana_*_t144.json`):

| Semana | Antes (carril de operación) | Ahora (universo oficial) | Huella |
|---|---|---|---|
| W43 | 4 operaciones, 1 con resultado | **43 de 161**, acierto 42 %, R medio +0,08, PnL **+511,67 USDT** | `c53945ef706c` |
| W44 | 0 con resultado | **30 de 87**, acierto 23 %, R medio −0,67, PnL **−1 310,21 USDT** | `5010ba1ca9f0` |
| W45 | 1 con resultado | **118 de 140**, acierto 81 %, R medio −0,10, PnL **−642,56 USDT** | `8efd47b19f54` |
| W46 (parcial, sin informe aún) | — | **33 de 33**, acierto 79 %, R medio −0,15, PnL **−272,94 USDT** | `19cd4b762f8f` |

**Lo que esto cambia para T31:** la puerta al dinero real deja de decidirse con 1 operación por
semana. Con el universo oficial hay 224 operaciones vividas en cuatro semanas, que siguen sin
llegar al mínimo de T49 por perfil y por régimen, pero ya son una muestra que se puede leer. El
acierto del 81 % de W45 **no** es una buena noticia: es el mismo efecto de la escalera que midió
el diagnóstico (R medio −0,10 con 81 % de acierto), y ahora se ve en el informe que decide.

## 7. Lo que NO hace

No cambia reglas de entrada, salida ni riesgo (eso es T143). No reabre T142. No decide si se opera
con dinero real. No recalcula ni borra ninguna fila del libro: las `retro` siguen ahí, consultables
con su etiqueta.

## 8. Fuera de alcance, anotado en BACKLOG

Ver `PLAN/BACKLOG.md`, entradas T144 (1)–(4).
