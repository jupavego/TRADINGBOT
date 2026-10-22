# T106 — Auditoría de salidas, contabilidad y métricas de los tres perfiles

Fecha: 2026-10-21 · Alcance: **solo lectura** (ningún cambio de lógica). Todo lo medido es
SIMULADO. Rutas relativas a `v2/`.

Corridas que respaldan este informe:
- vista en vivo de la API local: `GET http://127.0.0.1:8000/v2/paper?symbol=BTCUSDT|ETHUSDT`
  (2026-10-22 00:00 COT, `now = 1792634400000`).
- tests que fijan el comportamiento actual: `tests/paper/test_accounting_audit.py` (6 pruebas,
  verdes; documentan el defecto, no el comportamiento deseado).

---

## 0. Alertas (lo que hay que saber antes de tocar el motor)

| # | Alerta | Evidencia |
|---|---|---|
| A1 | **No hay liquidación ni suelo de capital.** `book._close` hace `st.equity += pnl` sin margin call; una pérdida con hueco deja el capital **negativo** y el perfil sigue en el panel. Reproducido: 3 operaciones dejan el capital en −19.970 USDT y el drawdown en **299,70 %**. | `book.py:226` · `test_accounting_audit.py::test_sin_liquidacion_...` |
| A2 | **El drawdown no está acotado.** `_max_dd_pct` = máx((pico−eq)/pico) solo pasa de 100 % si la curva se vuelve negativa. El 1204 % del Agresivo implica una equity de ≈ **−110.400 USDT** (con pico 10.000); no es un problema de las reglas de salida sino de A1. | `summary.py:21-26`, `summary.py:96` |
| A3 | **El panel muestra tres «capitales» distintos** y solo uno es la base de la rentabilidad: tarjeta = `equity`, «Saldo de la cartera» = `balance`, leyenda del gráfico = último punto de la curva (= `equity`). Las filas compartidas mezclan bases (ver §2). | `summary.py:84-86` · `paper_head.ts:59-61`, `paper_head.ts:70` · `paper_profiles.ts:32-34` |
| A4 | **Las cifras del panel no son reproducibles ni auditables.** La vista se **recalcula** desde todos los contextos del almacén en cada consulta, sin ventana y sin guardar instantánea; el capital siempre se **re-simula** desde 10.000 USDT. Lo único inmutable es el libro fijo, que guarda solo cierres `vivo` (hoy 47 filas de perfil en BTCUSDT y 26 en ETHUSDT). | `desk.py:143-174` · `paper_store.py:45-57` · `book.py:271` · `ledger.py:1-9`, `ledger.py:73-91` |
| A5 | **Un cierre que viola las reglas de la escalera descarta el PnL.** `_close` sale antes de sumarlo al capital: la operación no se contabiliza *y el dinero desaparece*. Hoy solo afecta a `ppp_btcusdt` (0 violaciones medidas); al pasar la escalera a los tres perfiles (T109) sería un agujero contable. | `book.py:219-223` |
| A6 | **Una sola `LadderParams` no sirve para BTC y ETH**: `tick` y `qty_step` son únicos (0,1 y 0,001 = BTCUSDT) y las velas finas de 1 min solo existen para BTCUSDT (`data/candles/symbol=BTCUSDT/timeframe=1m`); en ETHUSDT `_fine` devuelve `None` y las velas ambiguas se resuelven solo con la regla conservadora. | `params.py:85-92` · `desk.py:196-206` |
| A7 | **Cambiar `exit_mode` no cambia la versión de T49.** La huella versiona la estrategia y la mecánica de la sombra, no los filtros ni la salida del perfil; la validación mide la **sombra** (con TP/BE/tiempo), así que la escalera hoy no pasa por T49 y la evidencia anterior y posterior se mezclaría. | `versioning.py:8-11` · `ideas.py:104-106` |

---

## 1. Inventario: toda vía de cierre, una por una

Orden de eventos del libro por instante: cierres → cancelaciones → llenados → señales
(`book.py:25`). El libro **no decide** salidas en modo `tp`: recibe el `Outcome` ya resuelto por
`engine.simulate` y solo lo contabiliza.

| Vía | Quién la dispara | Precio | Comisión / costos | Efecto en el libro |
|---|---|---|---|---|
| **SL** (stop inicial) | `engine.simulate`: primera vela que toca `idea.sl` dentro del horizonte; gana al TP y al BE si empatan en la misma vela (conservador) | el nivel, o **la apertura si hay hueco** (`_stop_exit`) | taker de salida + deslizamiento (base + volatilidad, tope `slip_cap_bps`) | `_close` → cuenta en `trades`, suma PnL al capital |
| **SL en la vela del llenado** (solo límite) | si la vela que llenó la orden también toca el SL (orden intra-vela desconocido) | `idea.sl` | taker + deslizamiento | igual |
| **TP** | primera vela que toca `idea.tp` sin SL antes | `idea.tp` | **maker**, sin deslizamiento | igual |
| **BE** (break-even+, T48b) | tras avanzar `be_trigger_r` = 1 R, desde la vela **siguiente** el stop pasa a entrada + costo estimado + `be_lock_r` = 0,1 R; solo en 1 h y 4 h (`be_timeframes`) | el nivel bloqueado, o la apertura si hay hueco | taker + deslizamiento | igual |
| **TIEMPO** | `fill_t + idea.hold_ms` (24 h de 1 h, escalado por marco: 96 h en 4 h) si no se tocó nada antes **y la vela existe** | **apertura** de esa vela | taker + deslizamiento | igual |
| **GEOMETRIA** | al llenar: SL a menos de `min_risk_frac` (0,1 %) del llenado o TP del lado equivocado | — | — | **nunca entra al libro** (`book.py:132` ignora `RECHAZADA`) |
| **NO_LLENADA** | orden límite que vence sin que el precio la toque | — | — | `_cancel`: libera margen, evento «cancelada», no es operación |
| **OBJETIVO_SIN_LLENAR** | el precio alcanza el TP antes de tocar la entrada límite | — | — | `_cancel`, igual |
| **SL / SLD** (perfil escalera) | `ladder.simulate_ladder`: stop inicial o stop dinámico del escalón vigente; sin TP ni tiempo | nivel o apertura del hueco; velas de 1 min resuelven las de 15 m ambiguas | taker + deslizamiento + funding reservados en el propio stop | `_close`; si `audit_outcome` encuentra una violación → **evento «violacion» y PnL descartado** (A5) |
| **PENDIENTE / ABIERTA** | el camino de precios se acaba antes de resolverse | — | — | sigue en `slots`; su PnL flotante entra en `equity` y en la curva, nunca en `trades` |

Referencias: `engine.py:189-257` (SL 223-224, TP 225-226, BE 227-234, TIEMPO 235-236,
GEOMETRIA 209-210, NO_LLENADA 203, OBJETIVO_SIN_LLENAR 205-206, hueco `_stop_exit` 145-148,
costos `net` 68-69), `book.py:216-256` (`_close`) y `book.py:259-264` (`_cancel`),
`ladder.py:155`, `ladder.py:224`, `ladder_audit.py:12-33`.

Distribución real de cierres en la vista de hoy (ventana «todo», `balance.by_reason`):

| Perfil | BTCUSDT | ETHUSDT |
|---|---|---|
| Conservador | 10 ops: TP 5 · SL 4 · TIEMPO 1 | 10 ops: TP 2 · BE 4 · SL 4 |
| Moderado | 26 ops: TP 10 · SL 15 · BE 1 | 41 ops: TP 16 · SL 13 · BE 10 · TIEMPO 2 |
| Agresivo | 24 ops: TP 10 · SL 11 · BE 3 | 29 ops: TP 12 · SL 10 · BE 6 · TIEMPO 1 |
| PPP | 8 ops: **SLD 8** | 0 (solo BTCUSDT) |

### 1.1 Lo que frena pero NO cierra

- **Tope de riesgo abierto por dirección** (`caps.fit_risk`, 3 % en Moderado y Agresivo):
  recorta o rechaza la orden nueva. `caps.py:58-65`, aplicado en `book.py:165-170`.
- **Freno por drawdown** (`caps.Brake`, 5 %): pausa entradas 24 h y reinicia el pico.
  `caps.py:40-55`, aplicado en `book.py:120-121` (veto) y `book.py:229-231` (registro).
- **Freno propio de la escalera** (`LadderRisk`): 4 pérdidas seguidas u 8 % de drawdown pausan
  entradas 24 h. `ladder_book.py:74-98`, aplicado en `book.py:232-235`.
- **Pausas de aprendizaje** por estrategia y por contexto (`feedback`), cupo `max_open`,
  cobertura (`allow_hedge`), margen libre: todos vetan **entradas**. `book.py:87-126`.

### 1.2 ¿Puede un agente o una señal contraria cerrar una posición?

**No.** Probado y cerrado por construcción:

- Los `slots` solo se eliminan en `_close` (`book.py:217`) y `_cancel` (`book.py:260`), y ambos se
  invocan solo desde la cola de eventos construida con el `Outcome` del motor (`book.py:277-286`).
- La API del bróker no tiene ningún POST de cierre: solo `GET` y los dos POST del backtest
  (`api/paper.py:59-178`).
- El capital se muta en **un solo sitio** del repositorio: `book.py:226` (un único resultado al
  buscar asignaciones a `.equity` en `eim/paper`).
- Test: `test_con_capital_negativo_frena_entradas_pero_nadie_cierra` — con el freno activo y la
  cuenta en negativo, la posición abierta sigue en `slots` y no hay evento `sl|tp|be|tiempo`.
- En la escalera, además, `ladder_audit.FORBIDDEN_CLOSE` declara ilegítimos los cierres por
  tiempo, TP, break-even, «alcanzar un escalón», «recomendación de un agente» y «manual»
  (`ladder_audit.py:12-24`).

---

## 2. Verificación de las cifras del panel compartido

Fila compartida por el usuario y lo que exige el código (`return_pct = equity / 10.000 − 1`,
`summary.py:86`; la tarjeta imprime `equity` y ese mismo `return_pct`, `paper_head.ts:59-60`):

| Perfil | Columna de capital | Rentabilidad | Equity que **exige** la rentabilidad | ¿Coincide? | PnL flotante implícito si la columna fuese `balance` |
|---|--:|--:|--:|:--:|--:|
| Conservador | 8.273,03 | −17,27 % | 8.273,00 | **sí** | −0,03 |
| Moderado | 8.907,41 | −40,62 % | 5.938,00 | **no** | −2.969,41 |
| Agresivo | 6.638,78 | −96,32 % | 368,00 | **no** | −6.270,78 |

**(a) Dos bases distintas: confirmado como causa de las filas imposibles.** La tarjeta no puede
mostrar esa combinación (imprime `equity` y su propio `return_pct`), así que las filas mezclan la
columna `balance` («Saldo de la cartera», `paper_head.ts:70`) o la leyenda del gráfico con la
`Rentabilidad` de la pestaña Perfiles (`paper_profiles.ts:32`). El Conservador coincide porque su
flotante es ≈ 0 (hoy, en BTCUSDT, tiene 0 posiciones abiertas). La brecha se reproduce en
`test_balance_y_equity_son_dos_bases_distintas` (−3,99 % contra −0,25 % = 3,74 puntos con una sola
posición abierta). Dicho sin rodeos: **`balance` ≠ `equity` ≠ base de la rentabilidad** y el panel
ofrece las tres sin decir cuál manda.

Acotación honesta: un flotante de −2.969 (Moderado) exige 6 posiciones a ≈ 500 USDT de riesgo cada
una, y el riesgo nominal del Moderado con 10.000 USDT es 100 USDT (× peso ≤ 2 → 200). Es decir,
esas filas vienen de un momento con **capital bastante mayor que el inicial** (el tamaño usa el
capital del instante de la señal, `book.py:165-166`) o con pesos al máximo. No es reproducible hoy
(ver (c) y A4).

**(b) El 1204 % solo se explica con capital negativo: confirmado.** `_max_dd_pct` es
máx((pico−eq)/pico) y la curva arranca en el capital inicial (`book.py:276`), así que el pico es
≥ 10.000 y un 1204 % exige **eq ≈ −110.400 USDT**. El mecanismo está en `book.py:226`: se resta el
PnL sin liquidación, sin margin call y sin suelo. Reproducción mínima (perfil Agresivo real,
`test_sin_liquidacion_el_capital_queda_negativo_y_el_dd_pasa_de_100`):

```
qty=100.00 nocional=10000.00 margen=1000.00 pnl=-9990.00   (×3; el tope del 3 % solo deja 3)
apalancamiento=10x · liquidación informada = 90.40 → la salida fue 0,10: se atravesó sin liquidar
capital final = -19.970,00 · curva = [10000.0, 10.0, -9980.0, -19970.0]
_max_dd_pct = 299,70 %   panel: return_pct = -299,70 %
```

El precio de liquidación se **calcula y se muestra** (`book.py:73-74`, evento de llenado
`book.py:211`, columna de posiciones `summary.py:52`) pero **nunca se aplica**. Nota: el 1204 % y
el −96,32 % no pueden salir del mismo punto final de la curva, así que la curva del Agresivo bajó a
≈ −110.400 y volvió a subir cerrando posiciones ya abiertas (con capital ≤ 0 no entra nada nuevo:
`book.py:165-170`).

**(c) Las 19.132 operaciones: no reproducibles, y por diseño.**

- El contador no tiene ventana: `n_closed` = todas las operaciones de `st.trades`
  (`summary.py:89`), y los libros se reconstruyen desde **todos** los contextos del almacén en cada
  consulta (`desk.py:144` llama a `pstore.load(symbol, tf)` sin `start`, `paper_store.py:45-57`).
  El número solo puede crecer y mezcla `vivo` con `backtest`.
- Es **por símbolo**: `v.books` se calcula por símbolo (`desk.py:170`), así que el panel nunca suma
  BTC + ETH; no hay mesas unidas dentro de una fila. Lo que sí une máquinas es la experiencia
  compartida de T61, que importa `paper_ctx` de otros equipos (`api/share.py`,
  `data/share/import_*.json`): eso **aumenta los contextos** y, con ellos, las operaciones del
  panel.
- Hoy, con este almacén: BTCUSDT 2.760 contextos (2.452 `backtest` + 308 `vivo`), 29.403 ideas,
  4.856 resultados de sombra → Agresivo **24** operaciones; ETHUSDT 244 contextos → **29**. El
  techo absoluto de este almacén es 4.856 cierres por perfil: **19.132 no cabe**.
- Y no hay forma de volver a ver esa pantalla: la vista es un recálculo sin instantánea (A4). El
  único registro inmutable es el libro fijo, que guarda solo cierres `vivo`
  (`ledger.py:73-91`): hoy `perfil:BTCUSDT` 47 y `perfil:ETHUSDT` 26 filas.

Conclusión: la fila del Agresivo corresponde a otro estado del almacén (o a otra máquina de la
experiencia compartida) y **el panel no permite auditarla**. Esto es, por sí solo, motivo
suficiente para T107.

**(d) Comisiones, deslizamiento y funding están dentro del PnL mostrado: confirmado.**
`pnl = notional × o.net` (`book.py:224-226`) y `net = gross − fee_in − fee_out − slip − funding`
(`engine.py:68-69`). Los campos `fees`, `slip` y `funding` del libro (`book.py:243-244`) son
**informativos** y no se vuelven a restar; `balance._cost` los suma solo para los avisos
(`balance.py:37-38`, `balance.py:69-71`). Probado en
`test_el_pnl_del_libro_ya_descuenta_comisiones_deslizamiento_y_funding`. En la vista de hoy los
costos acumulados son 30,67 / 114,46 / 333,62 USDT (BTCUSDT) y 26,92 / 161,76 / 323,10 (ETHUSDT),
con 0 operaciones que habrían ganado sin costos. El funding es el real del almacén y, donde falta,
la tasa supuesta **marcada** (`engine.py:166-171`, `funding_assumed`).

**(e) No existe ninguna recarga de capital: confirmado.** Al buscar asignaciones a `.equity` en
`eim/` aparece una sola mutación (`book.py:226`); el capital se inicializa una vez por corrida
(`book.py:271`, `ProfileParams.initial_equity = 10.000`, `params.py:123`). Lo que sí ocurre —y
conviene no confundir con una recarga— es que **cada recálculo de la vista vuelve a empezar en
10.000 USDT** y repite toda la historia: el panel no es una cuenta persistente, es una
re-simulación. Probado en `test_nadie_recarga_el_capital`.

---

## 3. Qué se reutiliza y qué hay que cambiar (sin módulos paralelos)

| Punto de integración | Archivo / función | Estado y qué falta |
|---|---|---|
| Interruptor por perfil | `params.py:155-157` (`exit_mode`, `ladder`, `symbols`) | **Listo.** Basta `exit_mode="ladder"` + su `LadderParams` en los tres perfiles. |
| Umbrales por perfil | `params.py:73-114` (`LadderParams`) | Falta: 5/2,5 · 10/5 · 15/7,5 y, sobre todo, `tick`/`qty_step` **por símbolo** (A6) y el umbral también en R (◆6). Validar al arrancar (T108). |
| Dimensionado + apertura | `book.py:181-186` → `ladder_book.open_ladder` (`ladder_book.py:45-50`) | **Listo**; recalcula margen y riesgo con la cantidad redondeada. |
| Veto de viabilidad | `ladder_book.viability` (`ladder_book.py:28-42`) usado en `book.py:115-116` | **Listo**; usa `min_target_vs_first` (◆4). |
| Veto de posición duplicada | `book.py:117-119` | **Revisar**: prohíbe dos posiciones del mismo lado decididas en la misma vela. Choca con `allow_hedge=True` y con los mínimos de abiertas del Moderado (2) y del Agresivo (3). |
| Simulación de la salida | `ladder.simulate_ladder` (`ladder.py:172`) | **Listo y genérico** en lado, cantidad y costos. Necesita velas finas por símbolo (A6). |
| Camino de precios | `desk.py:169` (`LadderSim`) y `desk.py:196-206` (`_fine`) | `LadderSim` ya se construye siempre; `_fine` filtra por `p.symbols` → al quitar el filtro de símbolo hace falta 1 m de ETHUSDT en el almacén. |
| Prohibición de cierres ilegítimos | `ladder_audit.audit_outcome` (`ladder_audit.py:28`), llamado en `book.py:219-223` | **Listo** como detector; **arreglar** el descarte silencioso del PnL (A5) antes de activarlo en tres perfiles. |
| Métricas | `ladder_stats.ladder_stats` (`ladder_stats.py:37`), expuesto en `summary.py:74-79` | **Listo**: ya está condicionado a `exit_mode == "ladder"`, así que sirve a varios perfiles sin cambios. |
| Panel | `paper_profiles.ladderPanel` (`paper_profiles.ts:61-82`) | **Listo**: ya itera `ps.filter(p => p.ladder)`. Posiciones sin TP ni vencimiento: `summary.py:48-49`. |
| Aprendizaje | `book.py:136-137` (`st.lrisk.own`) y `ladder_book.LadderRisk` (`ladder_book.py:56-103`) | **Decisión implícita**: en modo escalera el perfil aprende solo de **sus** cierres y deja de usar el `Learner` de la sombra → los tres perfiles **empezarían su memoria de cero**. Hay que decirlo en T108/T111. |
| Validación T49 | `versioning.py:8-11` | **Hueco** (A7): `exit_mode` no entra en la huella y la validación mide la sombra con TP. T111 necesita una decisión explícita. |

No hace falta ningún módulo nuevo: todo lo de T105 es reutilizable tal cual salvo los
parámetros por símbolo y el descarte de PnL de A5.

---

## 4. El problema cuantitativo: 5–15 USDT son 0,1–0,3 R (y ya está medido)

Riesgo por operación = capital × `risk_pct` × peso (`book.py:165-166`), con el capital inicial de
10.000 USDT:

| Perfil | `risk_pct` | Riesgo nominal | Rango por peso | Primer escalón propuesto | En R (nominal) | Paso | Paso en R |
|---|--:|--:|--:|--:|--:|--:|--:|
| Conservador | 0,5 % | 50 USDT | 12,5–75 | 5 USDT | **0,100 R** | 2,5 | 0,050 R |
| Moderado | 1 % | 100 USDT | 25–200 | 10 USDT | **0,100 R** | 5 | 0,050 R |
| Agresivo | 2 % | 200 USDT | 50–600 | 15 USDT | **0,075 R** | 7,5 | 0,038 R |
| PPP (hoy) | 0,5 % | 50 USDT | 50 (peso fijo 1) | 10 USDT | 0,200 R | 5 | 0,100 R |

Dos consecuencias que hay que dejar escritas:

1. **Los umbrales en USDT invierten la intención**: el Agresivo protegería **antes** (0,075 R) que
   el Conservador (0,100 R), y con los pesos el rango real va de 0,025 R a 0,400 R. En USDT los
   tres perfiles no son comparables; en R sí (◆6).
2. **La medición de T105 ya muestra la decapitación**, y con umbrales el doble de holgados que los
   propuestos. De `reports/ppp_backtest.md` (86 operaciones, 40 días, +10/+5 = 0,2 R / 0,1 R):
   acierto **73 %**, PF **0,54**, neto **−537,23 USDT**, cierres 21 por SL inicial y **65 por SL
   dinámico**. Despejando: ganancias 630,7 y pérdidas 1.167,9 USDT → **ganadora media ≈ +10,0 USDT
   (= exactamente el primer escalón, 0,2 R)** y **perdedora media ≈ −50,8 USDT (= 1 R)**. Con esa
   relación hace falta acertar **83 %** para no perder; se acierta 73 %. El «devuelto frente al
   máximo» medio es 14,87 USDT sobre un flotante máximo medio de 9,27.

   Es decir: la escalera **sí** protege (65 de 86 salidas fueron por stop dinámico, 0 violaciones),
   pero corta a la ganadora en 0,2 R mientras la perdedora sigue valiendo 1 R. Bajar el primer
   escalón a 0,075–0,1 R empeora esa relación, no la mejora. **Lo decide la medición de T111**, no
   esta auditoría; lo que T111 tiene que medir es la **sensibilidad del umbral en R** (p. ej.
   0,1 · 0,25 · 0,5 · 1,0 R) y no solo el par USDT propuesto.

---

## 5. ◆ Decisiones del usuario

Respuestas del usuario anotadas el **2026-10-21** (recomendación = lo que propuso esta auditoría):

| # | Decisión | Recomendación (1 línea) | **Respuesta (2026-10-21)** |
|---|---|---|---|
| 1 | ¿La escalera sustituye TP y tiempo en los tres perfiles, o convive por marco? | Sustituirlos en los tres perfiles, conservando el perfil anterior como control (◆5): mezclar por marco impide atribuir el resultado. | **Ninguna de las dos: que el agente orquestador elija la estrategia de salida más conveniente de forma dinámica, según el análisis del mercado** (ver §5.1). |
| 2 | ¿Solo BTCUSDT o todos los símbolos de la mesa? | Solo BTCUSDT por ahora: ETHUSDT no tiene velas de 1 min ni `tick`/`qty_step` propios (A6). | **BTC y ETH** (requisito previo en §5.1). |
| 3 | ¿Se conserva Break-even+ o lo reemplaza el primer escalón? | Lo reemplaza: BE+ (1 R → +0,1 R) y el primer escalón (0,1 R) son dos stops dinámicos compitiendo. | **Conservar los dos.** |
| 4 | Sin TP de salida, ¿`min_rr` y `max_cost_r` siguen filtrando con el objetivo como estimación? | Sí, igual que el 4.º perfil: el objetivo es una estimación de recorrido y `min_target_vs_first` ya exige que cubra el primer escalón. | **Sí** (como el 4.º perfil). |
| 5 | ¿`ppp_btcusdt` se conserva como control o se retira? | Conservarlo: sin control no hay A/B (y el panel ya lo muestra aparte). | **Conservarlo como control.** |
| 6 | ¿Umbrales fijos en USDT (5/10/15) o en R / fracción del capital? | En R (mostrando el equivalente en USDT en el panel): es lo único comparable entre perfiles y lo único que no se desajusta cuando cambia el capital. | **En R, con el equivalente en USDT a la vista.** |

### 5.1 Consecuencias de las respuestas para T108–T111

- **◆1 cambia el alcance de la Fase 18.** La salida deja de ser un parámetro fijo por perfil y pasa
  a ser una **decisión del orquestador por operación o por régimen**. Eso exige, por orden:
  1. `exit_mode` deja de vivir solo en `ProfileParams` (`params.py:155`) y tiene que poder venir
     por idea/contexto; el libro ya decide con `p.exit_mode` en tres sitios
     (`book.py:115-119`, `book.py:136-137`, `book.py:181-186`, `book.py:219`), así que el cambio es
     acotado pero toca la firma de `run_profile`.
  2. **La constitución sigue mandando**: los LLM y el orquestador solo **informan/proponen**; el
     riesgo y la ejecución son código determinista con poder de veto (`CLAUDE.md`). El orquestador
     podrá elegir *entre reglas de salida ya validadas*, nunca inventar una ni mover un stop.
  3. **Sin esto no hay A/B.** Si la salida cambia por decisión dinámica, T111 no puede comparar
     «antes/después»: habría que medir cada modo de salida por separado (y con la huella de T49
     corregida, A7) antes de dejar que el orquestador elija entre ellos.
  4. Esa elección dinámica es justo el objeto de **T113** (auditoría de orquestadores) y **T114**
     (propuesta única y autoridad determinista). Propuesta de orden: T107 → T108 → T109/T110 con
     la salida fija por perfil y el modo **expuesto como parámetro**, medir en T111, y la elección
     dinámica después de T114.
- **◆2 (BTC y ETH)** añade dos requisitos previos a T108, antes de encender la escalera en ETHUSDT:
  sincronizar velas de **1 min de ETHUSDT** en el almacén (hoy solo existen de BTCUSDT) y mover
  `tick`/`qty_step` a parámetros **por símbolo** (A6). Mientras falten, ETHUSDT resolvería las
  velas de 15 m ambiguas solo con la regla conservadora y redondearía con el paso de BTC.
- **◆3 (conservar BE+ y escalones)** deja dos stops dinámicos conviviendo: hay que fijar la
  precedencia explícitamente (el stop vigente es el **mejor de los dos**, y nunca retrocede) y
  `ladder_audit` tiene que dejar de contar el cierre «BE» como violación cuando el BE+ está
  activado a propósito (`ladder_audit.py:12-24`) — hoy lo prohíbe y, con A5, descartaría el PnL.
- **◆6 (umbral en R)** confirma lo de §4: el panel muestra el equivalente en USDT, pero el umbral
  se calcula sobre el riesgo de la operación. T111 debe medir la sensibilidad (0,1 · 0,25 · 0,5 ·
  1,0 R).

---

## 6. Qué queda para las tareas siguientes

- **T107**: liquidación simulada y suelo de capital (A1), drawdown acotado (A2), **una sola**
  definición de capital/equity/variación en el panel (A3), instantánea o libro como fuente
  auditable del panel (A4), y PnL de las violaciones (A5).
- **T108**: `tick`/`qty_step` por símbolo y 1 min de ETHUSDT (◆2, A6), umbral en R (◆6, §4) y
  precedencia entre BE+ y los escalones (◆3).
- **T109**: revisar el veto de posición duplicada frente a los mínimos de abiertas (§3), el
  reinicio de la memoria de aprendizaje al pasar a `ladder` (§3) y dejar el modo de salida
  **expuesto como parámetro** para la elección dinámica de ◆1 (§5.1).
- **T111**: decisión explícita sobre T49 (A7), sensibilidad del umbral en R (§4) y medición de cada
  modo de salida por separado antes de que el orquestador elija (◆1, §5.1).
- **T113 / T114**: la elección dinámica de la salida pedida en ◆1 es su objeto; el riesgo y la
  ejecución conservan el veto determinista.
- Nota menor para el backlog: con capital ≤ 0 el rechazo se registra como «tope de riesgo abierto
  por dirección», que no es el motivo real (`book.py:168-169`).
