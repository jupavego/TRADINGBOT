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

Medido con datos reales (BTCUSDT, una semana, 15 m + 1 h + 4 h, `EIM_NURSERY=1` en una copia):

Medido sobre reportes **reales** del almacén vivo (BTCUSDT, 2026-11-11), contexto a contexto:

| Marco | Contexto sin `nat` | Con `nat` | Lo que añaden las variables nativas | Agentes con `nat` |
|---|---|---|---|---|
| 15 m | 2 106 B | 4 135 B | **+2 029 B** | 11 de 13 |
| 1 h | 2 176 B | 4 612 B | **+2 436 B** | 12 de 13 |
| 4 h | 2 182 B | 4 759 B | **+2 577 B** | 12 de 13 |

A la cadencia del bróker (96 contextos de 15 m + 24 de 1 h + 6 de 4 h al día):

**≈ 262 KiB de JSON al día, ≈ 1,8 MiB a la semana, ≈ 7,7 MiB al mes.** El contexto pasa de ~2,1 KB
a ~4,4 KB: la cantera **duplica** el tamaño de cada contexto, y eso es lo que cuesta guardar las
variables propias de los 13 agentes en vez de solo sus tres números. En disco pesa menos: DuckDB
comprime el JSON y crece por bloques, así que la cifra de arriba es el techo. Para dar la escala:
`paper.duckdb` lleva hoy 91 MB con más de un año de corrida, así que la cantera encendida un año
añadiría del orden del 10 % de lo que ya ocupa, sin tocar nada de lo que hay.

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

La corrida de **una semana entera** (882 contextos reales de 15 m, 1 h y 4 h) quedó lanzada por la
cola y su resultado se añade aquí: es la que dice cuántos de los 43 prospectos operan de verdad en
una semana y cuánto crece la base en disco. El primer intento murió por una carrera con la captura
HFT —estaba leyendo una parte parquet de `micro/top` de la hora en curso mientras el colector la
compactaba (`IOException`)—, así que la semana se desplazó un día hacia atrás, donde las
particiones ya están quietas. **Aviso para T169, que va a leer mucho más del almacén:** cualquier
lectura del tramo vivo necesita reintentos o un corte un día atrás.

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
