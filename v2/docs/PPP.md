# Protección progresiva de ganancias — PPP (T105, T108)

Escalera de protección del bróker simulado: SL dinámico por escalones de beneficio **neto**.
Vive en el perfil de control `ppp_btcusdt` (T105) y, desde T108, los tres perfiles
(Conservador, Moderado, Agresivo) traen sus propios parámetros de escalera.
**Solo simulación**: `LadderParams` rechaza `real_money`, `time_exit` y `fixed_take_profit`
(error de validación si se intentan activar).

> **Estado (T108).** Los tres perfiles tienen parámetros de escalera, ficha de instrumento por
> símbolo y validación al arrancar, pero **siguen saliendo por TP/BE/tiempo**: su `exit_mode`
> pasa a `"ladder"` en **T109**, que es quien cambia el motor (precedencia entre BE+ y escalones,
> memoria de aprendizaje y veto de posición duplicada). Hoy solo opera con escalera el control.

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

Los tres perfiles anteriores **no cambian**: mismos trades y eventos con y sin el perfil nuevo
(`tests/paper/test_ladder_book.py::test_does_not_touch_other_profiles`). La salida TP/BE/tiempo
sigue en `engine.simulate`; la escalera se simula **dentro del libro** porque los escalones están
en USDT y dependen de la cantidad, que el libro fija después de dimensionar.

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
y decide. `be_with_ladder=True` en los tres (◆3): BE+ y escalones conviven y el stop vigente será
el mejor de los dos, nunca el peor — lo honra **T109**.

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

`pendiente` → (llenado) `inicial` (manda el SL de la idea) → (neto máx. ≥ 10) `protegida`
(escalón n, SL solo sube) → cierra en `cerrada_sl_inicial` o `cerrada_sl_dinamico`.
`incidencia`: dato de vela no finito; la posición queda abierta, sin cierre inventado.
Un cierre `TIEMPO/TP/BE/NIVEL/AGENTE/MANUAL` es una **violación**: evento «violacion», no entra en
el resultado ni en el capital (`ladder_audit.py`, comprobado en cada cierre del libro).

Reglas dentro de una vela de 15 m (sin anticipación, conservador): 1) manda el SL vigente **al
abrir** la vela (hueco más allá del SL → se ejecuta a la apertura); 2) el avance de la vela solo
sube el SL desde la **siguiente**; 3) una vela que cruza varios escalones aplica el último
confirmado por su extremo, sin inventar los intermedios; 4) la vela de llenado de una orden límite
solo comprueba el SL inicial.

## 5. Persistencia y reinicio

La mesa recalcula su vista de forma determinista desde contextos y velas guardados: tras un
reinicio la posición se reconstruye idéntica (escalón, máximo flotante, SL vigente, historial,
costos). Probado: el estado con velas parciales es prefijo exacto del estado completo y repetir el
cálculo no duplica operaciones ni eventos. No hay estado en memoria que perder.

## 6. Métricas (`summary["ladder"]`, API `/v2/paper`)

Operaciones que alcanzaron cada escalón, cierres por SL inicial/dinámico, máximo flotante medio,
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
