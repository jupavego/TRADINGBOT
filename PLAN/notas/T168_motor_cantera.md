# T168 — El motor de la cantera: cómo quedó construido (2026-11-11)

**Modo: SIMULADO.** Nada de esto toca los libros de los perfiles de T31, ni la síntesis (peso 0),
ni el riesgo o la ejecución reales. La cantera nace **apagada** (`EIM_NURSERY=0`) y la enciende
T170 tras el pre-registro. Diseño: `PLAN/notas/T167_cantera.md` §3, §4, §5 y §9.

Esta tarea la empezó una sesión que murió a las 02:12 sin confirmar nada y la cerró otra el mismo
día: lo que dejó estaba bien encaminado (unas 1 765 líneas) y se rescató tras revisarlo contra la
ficha. Los tres arreglos que hicieron falta están en §5.

## 1. Las piezas

| Pieza | Qué hace |
|---|---|
| `eim/nursery/prospect.py` | Contrato `Prospect` (inmutable) y carga validada de los 19 expedientes de T167: 43 prospectos, techo de familia 50. La **huella** firma agente@versión, el **código normalizado de la regla**, los parámetros, las variables, el marco, la plantilla de salida y el tope de velas |
| `eim/nursery/rules/<agente>.py` | Las reglas nativas, puras: 13 módulos, uno por agente con prospectos. Cada módulo declara `EXPOSES` (las rutas del reporte que sabe leer) y `RULES` (id → función) |
| `eim/nursery/rules/base.py` | `View` (solo las variables declaradas y solo velas ≤ la actual) y `Signal` (`enter`, `hold`, `target`) |
| `eim/nursery/native.py` | De cada reporte saca **solo** las rutas que algún prospecto declara, compactas (6 decimales), y las guarda en el contexto bajo `nat` |
| `eim/nursery/sim.py` | Una operación sobre el camino real de 15 m: maker conservador, *markout*, funding a la frecuencia real, escalones de la escalera vigente |
| `eim/nursery/book.py` | Las cuentas, los gemelos aleatorios pareados y la puerta de costo por marco, con sus eventos |
| `eim/nursery/summary.py` | La lectura: rentabilidad neta %, saldo, curva de capital, drawdown, n, acierto, costo, etapa, R neto con IC y d frente a los gemelos |
| `eim/nursery/desk.py`, `store.py` | La mesa aparte y su base propia `data/paper_cantera.duckdb` |
| `eim/api/nursery.py` | `GET /v2/nursery` (sin POST) |

## 2. Lo que se decidió al construir (y no estaba escrito en la ficha)

1. **La huella firma el código de la regla, no solo sus parámetros.** Se reutiliza `_canon` de
   `paper/versioning.py` (T49) sobre el AST de la función: retocar una regla cambia la huella y
   por tanto la cuenta, igual que cambiar un parámetro. Es lo que impide «arreglar» un prospecto
   vivo sin que cuente como intento nuevo (nota §9.2).
2. **La cuenta es `prospecto@huella`**, y su alta queda en `nursery_accounts` con la hora. El
   registro es de solo adición: un prospecto nuevo empieza desde el capital inicial, en guardería,
   y **no hereda ni una operación**, porque el libro solo cuenta operaciones con `t ≥` su alta.
3. **El libro se recalcula entero en cada ciclo** y es determinista (mismos contextos y mismo
   camino → mismo libro, comprobado). Lo único que no se recalcula es el alta de cada cuenta.
4. **La puerta de costo de la cantera está en 0,3 R**, el límite V6 de T49, no en los 0,15 R de la
   corrida T143. Con 0,15 R la puerta cierra 15 m **en el primer ciclo**, porque sin operaciones
   de sombra propias se usa el punto de partida de T136 (0,157 R en 15 m) y la banda de scalping
   se quedaría sin medir antes de empezar, que es exactamente lo que avisa la nota §3. El
   mecanismo sigue siendo el mismo y automático; **el valor lo congela el pre-registro de T170**.
5. **Los gemelos se simulan dos veces, no doscientas.** Solo hay dos lados posibles: se simula el
   largo y el corto con la misma plantilla y los mismos costos, saliendo a más tardar cuando sale
   la operación real, y se ponderan por cuántos de los K = 200 sorteos cayeron de cada lado. El
   sorteo sale de una semilla fija por (cuenta, vela) y **no mira precios**. Resultado idéntico al
   de simular K veces, y 100 veces más barato.
6. **Las no llenadas valen 0 R**, no se descartan: una regla que pide entradas que nunca llenan no
   gana nada por no haber operado.
7. **La serie diaria es de P&L realizado**, apuntada al día del cierre, con la **misma convención
   para la cuenta y para sus gemelos**: es la diferencia la que se mide (bootstrap por bloques en
   T170). `days_in_position` cuenta los días con posición abierta, que es la cadencia que la banda
   semanal tiene que cumplir. Una curva diaria a precio de mercado queda en BACKLOG.
8. **Un contexto sin reporte del agente no decide:** si el agente salió `no_data` esa vela, no hay
   fila `nat` y la regla devuelve «nada». Un contexto incompleto tampoco: si la regla revienta por
   una variable que falta, se anota como «nada», nunca como señal.
9. **El tope `max_bars` manda sobre cualquier plantilla**, incluidas `atr_ladder` y `rule_flip`.
   Hoy los seis prospectos de scalping salen por `time_stop` o `mean_target`, así que no cambia
   ninguna operación; está para que T170 no pueda inscribir un scalping sin tope por descuido.

## 3. El costo en disco de las variables nativas (entregable 3)

Medido sobre reportes **reales** del almacén vivo (BTCUSDT, 2026-11-11), contexto a contexto, con
`EIM_NURSERY=1` en una copia:

| Marco | Contexto sin `nat` | Con `nat` | Lo que añaden las variables nativas | Agentes con `nat` |
|---|---|---|---|---|
| 15 m | 2 106 B | 4 135 B | **+2 029 B** | 11 de 13 |
| 1 h | 2 176 B | 4 612 B | **+2 436 B** | 12 de 13 |
| 4 h | 2 182 B | 4 759 B | **+2 577 B** | 12 de 13 |

A la cadencia del bróker (96 contextos de 15 m + 24 de 1 h + 6 de 4 h al día):

**≈ 262 KiB de JSON al día, ≈ 1,8 MiB a la semana, ≈ 7,7 MiB al mes.** El contexto pasa de ~2,1 KB
a ~4,4 KB: la cantera **duplica** el tamaño de cada contexto, y eso es lo que cuesta guardar las
variables propias de los 13 agentes en vez de solo sus tres números.

**Eso es el JSON; en disco salió más, no menos.** Medido en la corrida de la semana (882 contextos
reales), la base pasó de **4,99 MB a 9,71 MB**: **+4,72 MB (+94,5 %)**, o **674 KB al día** para
272 KB de JSON al día. DuckDB añadió **2,5 veces** la carga útil, porque a esta escala pesan los
bloques y el JSON no se comprime bien. Sobre la base viva (`paper.duckdb`, 91 MB y más de un año de
corrida) esa proporción no se ha medido, así que lo honesto es dar el rango: un año de cantera
encendida añade **entre ~0,1 y ~0,25 GB**, y es un punto que T170 debe mirar al encenderla, no una
cifra cerrada. El contexto medio sí quedó donde decía la estimación: **2 149 B sin `nat` y 4 312 B
con `nat`** (+2 163 B).

No se guarda nada que algún prospecto no declare: las rutas salen de `native_paths(prospects)`, y
un agente sin prospectos (los 6 excluidos de T167) no aporta ni un byte. Los números se redondean
a 6 decimales y de los diccionarios solo se guardan sus campos simples.

## 4. El criterio de aceptación, comprobado

La aceptación pide tres cosas; se comprobaron con **datos reales en una copia** (las velas y el
funding se leen del almacén vivo, solo lectura; todo lo que se escribe vive en una carpeta
temporal):

1. **Los contextos de la cantera son los de siempre más `nat`.** Cada contexto generado con
   `EIM_NURSERY=1`, quitándole `nat`, es **idéntico campo a campo** al que genera el bróker con la
   cantera apagada. ✅
2. **Los libros de T31 quedan idénticos.** Se calcula el libro real con la mesa de verdad
   (`PaperDesk.view` + `ledger.rows_from_view`) sobre los dos juegos de contextos y el **digest
   SHA-256 de sus filas coincide**: mismas ideas, mismos perfiles, mismas operaciones. ✅
3. **La cantera no escribe en `paper.duckdb`.** El digest de la base de contextos no cambia tras
   correr la cantera, y en ella no aparece ninguna tabla `nursery_*`: todo va a
   `paper_cantera.duckdb`. ✅ (También está como prueba del gate,
   `tests/nursery/test_native_desk.py::test_nursery_never_writes_to_the_t31_books`.)

**Gate completo verde por la cola, tres veces**, una por cada árbol que hubo: `gate-t168` (rc 0,
1 481 s, 3 641 pruebas), `gate-t168-2` tras la segunda fusión de `main` (rc 0, 1 411 s, 3 645
pruebas) y **`gate-t168-3` sobre el árbol que va en el PR**, con T166 y T173 ya dentro (rc 0,
1 416 s, **3 671 pruebas: 3 663 pasadas, 8 omitidas, 0 fallos**). `ruff check eim tests` limpio en
ese mismo árbol.

### La semana entera, con datos reales (2026-11-11)

Costó tres intentos y salió a la tercera: **882 contextos reales** (164 + 396 de 15 m, 168 de 1 h y
42 de 4 h hasta el 2026-11-10T12:15Z), 5 187 s de generación con un solo proceso. Las tres
comprobaciones de arriba son de esta corrida; el libro de T31 salió **idéntico** en los dos juegos
(digest `efc21670…`, 1 318 filas, 1 413 ideas, 1 087 cerradas; conservador 14, moderado 99, agresivo
95, ppp 23).

**Operan 32 de los 43 prospectos en una semana**, con 239 operaciones propias (494 con los
controles, de las que 475 cerraron):

| Banda | Operan | Operaciones | Los que no operaron |
|---|---|---|---|
| Scalping | 5 de 6 | 56 | `liq_agotamiento` |
| Intradía | 16 de 18 | 144 | `ema_elastico`, `estructura_ruptura` |
| Tres días | 6 de 11 | 26 | `bots_mayoria`, `bots_unanimidad`, `regimen_tramo`, `regimen_tramo_estable`, `tec_acuerdo_marcos` |
| Semanal | 5 de 8 | 13 | `elliott_onda3`, `elliott_onda5_giro`, `estructura_continuacion` |

Una semana **no es un veredicto de cadencia**: eso lo mide T169 sobre la historia, en la unidad de
cada banda. Lo que esta corrida demuestra es que el motor **produce ideas con variables propias en
las cuatro bandas**; por qué callaron esos 11 no se ha averiguado aquí, y quedan nombrados para que
T169 los mida donde una semana no alcanza.

**La puerta de costo se cerró sola, y es el hallazgo de la corrida.** Los tres marcos abrieron con el
punto de partida de T136 (15 m 0,157 R · 1 h 0,123 · 4 h 0,091, todos bajo el umbral de 0,3 R) y al
tercer día, con sus **50 operaciones de sombra** ya medidas, 15 m dio un costo real de **0,342 R** y
el marco **quedó cerrado** para sus nueve cuentas. Dicho de otro modo: con la puerta en 0,15 R el
scalping no habría llegado a medirse (§2.4), y con la puerta en 0,3 R **se midió y no pasó**, que es
exactamente lo que la nota de T167 §3 quería que ocurriera. Dos avisos para T169 y T170: el número
sale de **50 operaciones de una semana** y no decide nada por sí solo, y la banda de scalping es la
que está en riesgo real de baja por costo.

Costo medio de las 494 operaciones **0,185 R**, R medio **−0,156** y diferencia media frente a los
gemelos **−0,011 R**: a una semana no significa nada (ni se pretende), pero confirma que las tres
columnas se calculan y que el vivero nace sin ventaja regalada.

Los **dos primeros intentos son datos útiles para T169**, que va a leer mucho más del almacén:

1. **Carrera con la captura HFT.** Leer una parte parquet de `micro/top` de la hora en curso
   mientras el colector la compacta revienta con `IOException`. Solución: cortar la ventana un día
   atrás, donde las particiones ya están quietas, y reintentar.
2. **La cola lo mató por memoria.** Con 2 procesos el pico fue de **1 807 MB** y el equipo tenía
   ~3 GB libres: cuando la RAM libre bajó a 844 MB, la cola lo reencoló pidiendo 3 328 MB y a las
   2 h se rindió por no encontrar ese margen. Un trabajo largo en este equipo va con **un solo
   proceso** y ha de ser **reanudable**: los contextos ya calculados se guardan vela a vela, así
   que al relanzarlo solo se calcula lo que falta, con la ventana congelada en un archivo para que
   el almacén, que no deja de crecer, no desplace la semana.

## 5. Los tres arreglos sobre lo que dejó la sesión de las 02:12

1. **`compute(now=0)` tomaba la hora real** (`now or now_ms()`): con el reloj por delante de los
   contextos, ninguna cuenta abría nada y el libro salía vacío. Es el fallo que dejó la prueba de
   la mesa en rojo.
2. **La puerta de costo heredaba los 0,15 R de T143** y cerraba 15 m antes de medirla (§2.4).
3. **`max_bars` no se aplicaba con `atr_ladder` ni con `rule_flip`** (§2.9).

## 6. Lo que esta tarea no hace

- **No enciende la cantera** ni fija su fecha de arranque: eso es T170, con el pre-registro y ◆.
- **No mira la historia**: no hay rendimiento histórico de ningún prospecto. El examen físico
  (¿opera?, ¿cuánto?, ¿cuánto cuesta?) es T169.
- **No decide ascensos ni bajas.** `stage` solo dice «guardería» o «cantera» por el número de
  cierres (30, escalafón §3); el escalafón entero, con sus pruebas, es de T170.
- **No hay panel** (T171) ni informe por agente (T172).
- **Solo BTCUSDT.** La mesa arranca con `FOCUS[0]`; medir ETH duplicaría la familia y el techo, y
  eso se decide en el pre-registro.
