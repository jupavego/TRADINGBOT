# Protección progresiva de ganancias — PPP (T105, T108, T109)

Escalera de protección del bróker simulado: SL dinámico por escalones de beneficio **neto**.
Nació en el perfil de control `ppp_btcusdt` (T105); T108 dio a los tres perfiles (Conservador,
Moderado, Agresivo) sus propios parámetros y **T109 los hace salir solo por su stop**.
**Solo simulación**: `LadderParams` rechaza `real_money`, `time_exit` y `fixed_take_profit`
(error de validación si se intentan activar).

> **Estado (T109).** Los cuatro perfiles salen con `exit_mode="ladder"`: sin TP fijo y sin cierre
> por tiempo. Antes del primer umbral manda el stop inicial; después, el stop dinámico, que solo
> sube. Nada más cierra una operación de la estrategia (§2.3). El modo `"tp"` sigue siendo un
> parámetro para medir cada salida por separado (T111) y para la elección dinámica de ◆1
> (T113/T114). La persistencia del estado de protección es T110; el panel, T112.

## 1. Arquitectura identificada y qué se reutilizó

| Capa del encargo | Componente real del proyecto | ¿Reutilizado? |
|---|---|---|
| 1 Datos | `Store` (velas 15 m/1 h/4 h, funding), `PaperStore` (contextos) | sí |
| 2 Agentes | `agents/*` → contexto por vela → estrategias (`paper/catalog`) → `Idea` | sí |
| 3 Decisión | filtros del libro (`book._vetoes`): confianza, R:B, síntesis, tendencia mayor, costo, cobertura, cupo | sí + 2 vetos propios (viabilidad del primer escalón, posición duplicada) |
| 4 Riesgo | tamaño por riesgo (`risk_pct` × capital), apalancamiento por distancia de liquidación, margen aislado | sí; cantidad al paso 0,001 BTC |
| 5–6 Apertura/seguimiento | `book.run_profile`, `engine._limit_fill/_slip/_funding` | sí |
| 7–9 Protección y cierre | **nuevo** `paper/ladder.py` | nuevo |
| 10 Evaluación | `summary.profile_summary`, `balance`, bitácora | sí + `ladder_stats.py` |
| Agentes/IA | consolidados por la síntesis existente (T44); el perfil exige ir a favor de `syn_bias` y de la tendencia del marco mayor. No se añadió ningún agente | sí |

La salida TP/BE/tiempo sigue en `engine.simulate` (la **sombra** que evalúa estrategias y la
salida `"tp"` del A/B); la escalera se simula **dentro del libro** porque los escalones están en
USDT y dependen de la cantidad, que el libro fija después de dimensionar. Un perfil en modo `"tp"`
ignora el camino de la escalera (`test_ladder_book.py::test_does_not_touch_other_profiles`).

## 2. Parámetros (todos en `paper/params.py`)

`ProfileParams(id="ppp_btcusdt", …, exit_mode="ladder", symbols=("BTCUSDT",))` y
`LadderParams`: `basis="usdt"`, `first_usdt=10`, `step_usdt=5`, `min_target_vs_first=1.0`,
`fixed_take_profit/time_exit/real_money=False` (inmutables).

### 2.1 Escalones por perfil (T108, ◆6 de T106)

Los escalones se expresan de dos maneras. `LadderParams.steps(riesgo_usdt)` resuelve el par
(primer escalón, incremento) **en USDT para cada operación**:

| Perfil | `basis` | Primer escalón | Incremento | Equivalente con el capital inicial |
|---|---|---|---|---|
| Conservador | `r` | 0,100 R | 0,050 R | +5,00 / +2,50 USDT (riesgo 0,5 % = 50 USDT) |
| Moderado | `r` | 0,100 R | 0,050 R | +10,00 / +5,00 USDT (riesgo 1 % = 100 USDT) |
| Agresivo | `r` | 0,075 R | 0,0375 R | +15,00 / +7,50 USDT (riesgo 2 % = 200 USDT) |
| `ppp_btcusdt` (control) | `usdt` | +10 USDT | +5 USDT | fijos: no dependen del riesgo |

Son la traducción exacta a R de los 5/2,5 · 10/5 · 15/7,5 USDT del encargo con el capital
inicial. En USDT los tres perfiles no son comparables (el Agresivo protegería **antes**, a
0,075 R, que el Conservador, a 0,100 R) ni resisten un cambio de capital; en R sí. **Son el punto
de partida del experimento, no un óptimo**: T111 mide la sensibilidad (0,1 · 0,25 · 0,5 · 1,0 R)
y decide. `be_with_ladder=True` en los tres (◆3): BE+ y escalones conviven y el stop vigente es
el mejor de los dos, nunca el peor (§2.3).

### 2.2 Ficha del instrumento (A6 de T106)

`SYMBOL_SPECS` (en `paper/params.py`) guarda `tick`, `qty_step` y `min_qty` de cada símbolo,
consultados en `fapi/v1/exchangeInfo` el 2026-10-22: BTCUSDT 0,1 / 0,001 / 0,001 y ETHUSDT
0,01 / 0,001 / 0,001. Antes eran constantes de BTC dentro de `LadderParams`, así que ETHUSDT
habría redondeado el SL con el tick de BTC (10 veces más grueso). Un símbolo sin ficha **no se
opera**: `spec_for` falla con el motivo y `check_profiles` impide arrancar la mesa.
Perfil: capital 10 000 USDT, riesgo 0,5 % por operación, apalancamiento ≤ 5x, máx. 2 posiciones,
confianza ≥ 0,30, R:B estimado ≥ 1,3, a favor de síntesis y de tendencia mayor, costo ≤ 0,15 R,
sin cobertura (largo y corto a la vez). Costos: los de `ExecParams.costs` (taker 0,05 %,
deslizamiento base + volatilidad, funding real del almacén). Feedback fijo: peso 1, nunca pausa y
**nunca sube el tamaño tras una pérdida**.

### 2.3 Solo cierra el stop (T109)

**Qué puede terminar una operación**, cada cosa con su motivo propio en el libro y contada por
separado en `summary["ladder"]["exits"]` (`ladder_stats.exit_counts`):

| Motivo | Código | Qué es |
|---|---|---|
| Stop inicial | `SL` | el de la idea, antes del primer umbral |
| Stop dinámico | `SLD` | el SL movido por un escalón **o por el BE+** (`ladder.stop_source`) |
| Liquidación simulada | `LIQUIDACION` | margen aislado de T107: un hueco que atraviesa la liquidación |
| Salvaguarda independiente | `SALVAGUARDA` | cierre ordenado por el kill-switch (T31); el bróker simulado hoy no lo emite |
| Incidencia técnica | — | **no cierra**: datos no finitos dejan la posición abierta marcada «incidencia» |

**Nadie más cierra.** Un cierre por TP, por tiempo, por alcanzar un escalón, por una señal
contraria de un agente, por retroceso del flotante sin tocar el stop o manual
(`ladder_audit.FORBIDDEN_CLOSE`) se registra como **violación** (evento «violacion», contador
`counts.violations` y `ladder.exits.rechazados`) y **no se ejecuta**: la posición sigue abierta
con su stop vigente y el capital y el margen no se mueven (`book._reject`). Un cierre por el stop
cuyo historial tiene anomalías sí se ejecuta —el precio tocó el stop— y queda auditado aparte con
su PnL contabilizado (T106 A5).

**Señales contrarias**: solo informan. El evento de la señal que llega contra una posición abierta
lleva `against` (las posiciones a las que se opone) y el resumen las cuenta
(`ladder.contrary_signals`); con cobertura el perfil puede abrir la contraria, sin cobertura se
rechaza, y en ningún caso se toca la posición abierta.

**El tiempo solo se registra**: `hold_h` de la idea ya no cierra en ningún perfil; la duración
queda en `ladder.elapsed_ms` y en las métricas (`avg_hours`, `duration`). El objetivo de la idea
solo es una **estimación** para los filtros de entrada (`min_rr`, `max_cost_r`,
`min_target_vs_first`) y para el análisis, jamás una orden de salida.

**BE+ conviviendo (◆3).** Si el precio avanza `be_trigger_r` = 1 R (solo ideas de 1 h y 4 h, como
en T48b), desde la vela siguiente el BE+ propone un stop en entrada + 0,1 R + costo estimado; el
stop vigente es el **mejor** entre ese y el del escalón, y solo se mueve si sube. Con los umbrales
reales (0,075–0,100 R) el escalón ya protege ≈ 0,8 R cuando el BE+ se dispara, así que **en la
práctica no interviene** (`test_with_the_real_steps_be_plus_never_beats_the_ladder`); sí manda con
un primer escalón lejano (`test_be_plus_coexists_and_the_best_stop_wins`).

**Entradas sin cambios.** El veto «una posición por vela y lado» (`one_per_bar`) y el freno propio
de la escalera (`brake`) son del control; los tres perfiles conservan sus mínimos de abiertas, su
cobertura y sus `caps` (T106 §3 señalaba el choque).

**Aprendizaje coherente.** Con escalera el perfil aprende de **sus propios cierres**
(`LadderRisk`), no de la sombra con TP; el resumen lo declara (`learning`) y los pesos que muestra
salen de esa memoria. Consecuencias que hay que saber: la memoria **empieza de cero** al encender la
escalera (el Conservador, que solo opera lo probado, vuelve a entrar sobre todo por su mínimo de
abiertas hasta acumular 10 cierres propios por estrategia), y el peso queda acotado a
`LadderParams.max_weight` = 1,5. El Agresivo (`gain` 2,5, `w_max` 3,0) llegaba a 3,0 tras una
racha corta; con la escalera las ganadoras son pequeñas y frecuentes, la muestra propia es chica y
una racha no debe multiplicar el tamaño. Con el tope del 3 % por dirección, 1,5 × 2 % es el mismo
techo que ya imponía `caps`; en el Moderado baja de 2,0 a 1,5; el Conservador (1,5) y el control
(1,0) no cambian.

**Protección monotónica.** El nivel protegido solo sube dentro de la simulación; una señal nueva
de la misma estrategia, una señal contraria o un cambio de versión de la estrategia no lo tocan, y
recalcular la vista (reinicio) da el mismo estado
(`test_new_signal_or_strategy_version_does_not_reset_the_protection`). Entre procesos lo sostiene
el diario de la protección (T110, §5): el SL recalculado nunca queda por debajo del guardado.

## 3. Fórmulas

Beneficio neto estimado de salir a `p` (misma contabilidad que `Outcome.net`), con `qty` BTC,
entrada `f`, `K = fee_ent + desl_ent + desl_sal + funding`:

```
neto(p) = qty·(lado·(p − f) − fee_sal·p) − qty·f·K
```

Precio del SL para el nivel `L` (despeje exacto):

```
largo : p = (L/qty + f·(1+K)) / (1 − fee_sal)
corto : p = (f·(1−K) − L/qty) / (1 + fee_sal)
```

Se redondea al tick **en contra del operador** (largo arriba, corto abajo) y se comprueba
`neto(p) ≥ L`; si no, se sube un tick. Escalón, con `(primero, paso) = lp.steps(qty·|llenado − SL|)`:
`nivel = 1 + ⌊(máx_neto − primero) / paso⌋` si `máx_neto ≥ primero`, con protección nominal
`primero + paso·(nivel−1)`. Con `basis="usdt"` el par es fijo (10 y 5, el control); con
`basis="r"` sale del riesgo realmente abierto en esa operación.

## 4. Máquina de estados de una posición

`pendiente` → (llenado) `inicial` (manda el SL de la idea) → (neto máx. ≥ primer escalón, o BE+)
`protegida` (escalón n, SL solo sube) → cierra en `cerrada_sl_inicial` o `cerrada_sl_dinamico`
(o liquidación / salvaguarda, §2.3). `incidencia`: dato de vela no finito; la posición queda
abierta, sin cierre inventado. `inconsistente` (T110, §5): lo guardado no deja reconstruirla con
seguridad; queda abierta, sin cierre inventado y sin mover el stop por lo guardado, hasta
reconciliarla a mano. Un cierre `TIEMPO/TP/BE/NIVEL/AGENTE/RETROCESO/MANUAL` es una
**violación**: evento «violacion» y la posición sigue abierta; no se ejecuta (`book._reject`,
comprobado en cada cierre del libro).

Reglas dentro de una vela de 15 m (sin anticipación, conservador): 1) manda el SL vigente **al
abrir** la vela (hueco más allá del SL → se ejecuta a la apertura); 2) el avance de la vela solo
sube el SL desde la **siguiente**; 3) una vela que cruza varios escalones aplica el último
confirmado por su extremo, sin inventar los intermedios; 4) la vela de llenado de una orden límite
solo comprueba el SL inicial.

## 5. Persistencia y reinicio (T110)

La mesa recalcula su vista de forma determinista desde contextos y velas guardados: con los mismos
datos y parámetros, tras un reinicio la posición se reconstruye idéntica (escalón, máximo flotante,
SL vigente, historial, costos). Pero el recálculo puede dar MENOS que lo vivido (velas de 1 min que
ya no están, parámetros nuevos, contextos importados): por eso existe el **diario de la protección**.

**Diario** (`eim/paper/protection.py`, tabla `paper_protection` en `data/paper.duckdb`, solo
adición, clave `op_id|seq` con `op_id = perfil|símbolo|idea`): por cada operación de origen `vivo`
con escalera, una fila al abrirla (`alta`), una por cada cambio del stop (`escalon`: escalón o BE+)
y una al cerrarla (`cierre`); la de mayor `seq` es la vigente. Cada fila: perfil, símbolo, lado,
entrada, cantidad, nocional, SL inicial, umbral de activación e incremento, protección activada,
máximo neto alcanzado, escalón, neto protegido, SL vigente y su origen, instante de la última
actualización, costos y reservas estimadas, estado (`abierta`, `protegida`, `cerrada`,
`inconsistente`, `reconciliada`, `descartada`), historial completo de cambios del stop y motivo
final de cierre. `paper_protection_pass` recuerda por símbolo cuándo empezó el diario y qué
operaciones dejó abiertas la última pasada. No viaja con la experiencia compartida (T61).

**Pasada** (`protection_sync.py`, tras cada recálculo de la vista; la primera de cada proceso es la
recuperación al arrancar): el diario se lee ANTES de simular y su estado vigente entra como **suelo
del SL** (`ladder_floor.py`): si el SL recalculado queda por debajo del guardado, se adopta el
guardado desde el instante en que se confirmó (historial `source = "recuperado"`) y se avisa
(«Protección recuperada del diario», fila `recuperacion`). Si al arrancar el recálculo va por delante
(el precio siguió con la API parada), se adopta el recálculo y se registran los cambios que
faltaban (aviso informativo). El nivel adoptado es siempre el mayor de los dos; ninguna fila
automática deja el SL por debajo del guardado (salvaguarda `_never_lower`).

**Estado inconsistente**: instantánea ausente (la última pasada la dejó abierta y ya no tiene filas)
o corrupta (ilegible, símbolo o identidad que no cuadran), instantánea de otra operación (lado,
entrada o cantidad distintos), recálculo que la cerraría ANTES del instante en que la instantánea
la vio viva, velas que no llegan hasta ese instante, operación guardada que el recálculo no
encuentra, o guardada cerrada y abierta al recalcular. Entonces: fila `inconsistente`, la operación
no se cierra sola ni mueve su stop por lo guardado, el diario de esa operación se congela, cuenta
en el resumen (`protection.n_inconsistent` y `profiles[].protection.inconsistent` de `/v2/paper`)
y queda una alerta crítica en `op_alerts`. Se resuelve a mano (`docs/RUNBOOK.md` §14):
`python -m eim.paper proteccion reconciliar <op_id> --decision recalculo|descartar --nota "…"`.

**Observatorio** (contrato de T72): cada fila del diario y cada recuperación emiten un evento
`alert` del componente `paper.broker` (`detail.what = proteccion_<evento>`) con una traza propia por
operación (`trace_of(op_id)`), así el mapa cuenta la historia completa de una protección.

**API**: `GET /v2/paper/protection` (estado vigente e inconsistencias), `GET
/v2/paper/protection/history?op_id=` (todas sus filas) y `POST /v2/paper/protection/resolve`
(`X-EIM-Confirm: paper-protection`). Tests: `tests/paper/test_protection*.py`.

## 6. Métricas (`summary["ladder"]`, API `/v2/paper`)

Motivos de cierre por separado (`exits`: stop inicial, stop dinámico, liquidación, salvaguarda,
incidencias abiertas, otros motivos —debe ser 0— y cierres rechazados), señales contrarias,
operaciones que alcanzaron cada escalón, cierres por SL inicial/dinámico, máximo flotante medio,
realizado medio, lo devuelto frente al máximo, realizado − protegido estimado, resultado y
retrocesos por escalón máximo, lado, régimen, hora UTC de entrada y estrategia, duración
(solo analítica), pérdidas seguidas, violaciones e incidencias. La UI (pestaña «Perfiles») las
muestra; la mesa muestra el SL vigente y su escalón en lugar de TP.

## 7. Cómo seguirlo

`python -m uvicorn eim.api.main:app --port 8000` y abrir la mesa de papel: el cuarto perfil
(morado) aparece junto a los otros tres; bitácora con «Violación de reglas» para auditoría.
Backtest: `python scripts/ppp_backtest.py --data <carpeta de datos>` (informe en `reports/`).

## 8. Reservas, aprendizaje propio y freno (corrige las limitaciones iniciales)

- **Realizado vs nominal.** El SL se fija con reservas (`slip_lookback=4`: mayor deslizamiento de
  las últimas 4 velas; `funding_reserve=1`: una liquidación de funding futura a la tasa supuesta).
  El realizado queda en general ≥ nominal (test: +0,7 USDT de colchón en el caso medido). Un hueco
  real de precio sigue pudiendo dejarlo por debajo: es inherente a un stop y se mide como
  «realizado − protegido estimado».
- **Aprendizaje propio.** La escalera ya no usa la sombra con TP: aprende de SUS cierres
  (`LadderRisk`: R por estrategia@marco y por contexto, solo con lo cerrado antes de la señal). Con
  ≥ 8 cierres y expectativa claramente negativa esa estrategia/contexto se pausa. El tamaño nunca
  sube (peso fijo 1).
- **Freno de entradas.** `max_consec_losses=4` pérdidas seguidas o drawdown ≥ `max_drawdown=8 %`
  desde el máximo → no abre durante `pause_hours=24`, luego reanuda partiendo del capital actual.
  Solo frena entradas nuevas: jamás cierra posiciones abiertas. Visible en el resumen
  (`ladder.brake`), en la pestaña Perfiles y en la bitácora.

## 9. Orden intra-vela, entradas propias y funding real (T105, segunda ronda)

- **Orden de los precios dentro de la vela de 15 m.** Las velas *ambiguas* (las que pueden subir
  el SL y volver a tocarlo, dentro de la misma vela) se resuelven con las velas de **1 min** en su
  orden real (`ladder._sub_bars`), con la misma regla dentro de cada minuto (manda el SL vigente
  al abrir el minuto; el avance sube el SL desde el minuto siguiente). Si faltan velas finas o
  alguna no es válida, esa vela vuelve a la regla conservadora. El servicio en vivo sincroniza
  las velas de 1 min (7 días de retroceso al arrancar) y la mesa las carga sola
  (`LadderParams.fine_tf`). En el backtest: 67 velas ambiguas; la regla conservadora sola
  subestimaba el resultado en ≈ 67 USDT (−605 frente a −537).
- **Entradas propias.** Estrategia `ppp_tendencia` (familia `ppp`, solo 1 h y 4 h, solo la opera
  este perfil): marco mayor + síntesis de agentes + fuerza (ADX/DI) + RSI sin agotamiento, SL
  2,2 ATR. Son confirmaciones distintas; no se apilan SuperTrend/EMA/MACD porque miden lo mismo
  que +DI/−DI. Umbrales fijados a priori, con una sola corrección documentada (la primera versión
  apilaba esos indicadores y producía 5 ideas en 40 días). La puerta T49 la evalúa como a las demás.
- **Funding real.** El backtest descargó el funding completo del periodo (138 liquidaciones,
  3 por día): 0 de 86 operaciones con funding supuesto. En vivo el servicio ya lo sincroniza
  cada ciclo (30 días de retroceso); la tasa supuesta solo aparece si falta algún tramo y queda
  marcada.

## 10. Limitaciones que siguen

- Dentro de cada vela de **1 min** el orden sigue siendo desconocido (regla conservadora allí); es
  la mejor resolución disponible sin ticks.
- Las entradas propias son pocas: **9 operaciones en 40 días** (8 en desarrollo, 1 fuera de
  muestra), con +31 USDT y 5 aciertos de 6 cerradas por SL dinámico/inicial. Es una muestra que
  no permite concluir nada; hay que acumular meses de datos y pasarla por T49 antes de confiar.
- Posiciones correlacionadas: máx. 2, y se veta la segunda en la misma vela y lado.
- El historial local es corto: el backtest no demuestra rentabilidad.

## 11. Resultado del backtest (2026-10-20) — NO es rentable en esta muestra

`python scripts/ppp_backtest.py --data <carpeta>` → `v2/reports/ppp_backtest.md` (velas de 1 min en
las ambiguas, funding real, entradas propias frente al resto, rejilla de umbrales/escalones en
desarrollo y fuera de muestra, y sensibilidad a costos). Datos: 40 días de BTCUSDT
(2026-09-10 → 2026-10-20), 5 997 ideas, velas y funding públicos de Binance en una copia aparte.

- Referencia (+10/+5): 86 operaciones, **−537 USDT (−5,4 %)**, PF 0,54, esperanza −6,25 USDT/op,
  DD máx. 5,6 %, 0 violaciones de reglas, 0 incidencias, 0 operaciones con funding supuesto. El
  freno de entradas no llegó a activarse (máx. 3 pérdidas seguidas, drawdown < 8 %).
- Acierto 73 %, pero 21 cierres por SL inicial pesan más que los 65 por SL dinámico. El escalón
  +10 se alcanza en 65 de 86 (76 %); pocos llegan más lejos (+15: 9, +20: 3, +30: 1).
- Con la regla conservadora sola (sin velas de 1 min) el resultado era −605 USDT: resolver el
  orden real de las velas ambiguas lo corrige en ≈ +67 USDT.
- Fuera de muestra peor que en desarrollo (PF ≈ 0,36 frente a 0,71) y ninguna variante de la
  rejilla sale positiva: no hay configuración que seleccionar. Con costos ×0,5 sigue negativo
  (−324).
- Entradas propias (`ppp_tendencia`): 9 operaciones en total, +31 USDT; sin entradas propias el
  perfil pierde −155 (desarrollo) y −348 (fuera de muestra). Con tan pocas operaciones no se puede
  decir si tienen ventaja.
- Los otros tres perfiles, en el mismo periodo: Conservador −438, Moderado −1 356, Agresivo −4 934
  USDT: el periodo es adverso para las ideas existentes, no solo para este perfil.

Lectura: el mecanismo funciona según lo especificado (verificado por tests y auditoría), pero
**las entradas generales no tienen ventaja** frente a un SL inicial a ~2 % y costos de ≈0,16 %; las
entradas propias son demasiado pocas para evaluarlas. No se declara rentable el perfil.
