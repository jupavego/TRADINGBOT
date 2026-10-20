# Perfil PPP — Progressive Profit Protection · BTCUSDT (T105)

Cuarto perfil del bróker simulado (`ppp_btcusdt`). **Solo simulación**: `LadderParams` rechaza
`real_money`, `time_exit` y `fixed_take_profit` (error de validación si se intentan activar).

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
`LadderParams`: `first_usdt=10`, `step_usdt=5`, `tick=0.1`, `qty_step=0.001`,
`min_target_vs_first=1.0`, `fixed_take_profit/time_exit/real_money=False` (inmutables).
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
`neto(p) ≥ L`; si no, se sube un tick. Escalón: `nivel = 1 + ⌊(máx_neto − 10) / 5⌋` si
`máx_neto ≥ 10`, con protección nominal `10 + 5·(nivel−1)`.

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

## 8. Limitaciones conocidas

- **Estimado ≠ realizado**: el SL usa el deslizamiento esperado de la vela que lo fija; el real
  depende de la vela de salida; huecos y funding posterior pueden dejar el neto bajo el nominal
  (se mide como «realizado − protegido estimado»).
- Camino de 15 m: sin datos de tick el orden intra-vela es desconocido, de ahí la regla conservadora
  (es posible que se devuelva más de lo real en alzas rápidas).
- Las ideas vienen de las estrategias existentes (su TP solo estima si el primer escalón es
  alcanzable; no es una salida). La escalera no aprende de sus propios resultados todavía.
- Posiciones correlacionadas: máx. 2 y vetada la segunda en la misma vela y lado; no hay límite de
  drawdown diario ni freno por pérdidas seguidas (solo se miden).
- El historial local disponible es corto; con pocas operaciones el backtest no demuestra
  rentabilidad (ver `reports/ppp_backtest.md`).

## 9. Resultado del backtest (2026-10-20) — NO es rentable en esta muestra

`python scripts/ppp_backtest.py --data <carpeta>` → `v2/reports/ppp_backtest.md` (rejilla de
umbrales/escalones en desarrollo y fuera de muestra, y sensibilidad a costos). Datos: 40 días de
BTCUSDT (2026-09-10 → 2026-10-20), 5 992 ideas, velas públicas de Binance en una copia aparte;
funding real solo en parte del periodo (el resto, tasa supuesta y marcada).

- Referencia (+10/+5): 84 operaciones, **−500 USDT (−5,0 %)**, PF 0,55, esperanza −5,95 USDT/op,
  DD máx. 5,2 %, 0 violaciones de reglas, 0 incidencias.
- Acierto 68 % pero con pérdidas grandes: 19 cierres por SL inicial suman −1 062 USDT; 65 cierres
  por SL dinámico suman ≈ +560. El escalón +10 se alcanza en 65 de 84 (77 %); el máximo llegó a +85.
- Fuera de muestra peor que en desarrollo (PF 0,33 vs 0,82) y ninguna variante de la rejilla sale
  positiva: no hay configuración que seleccionar. Con costos ×0,5 sigue negativo (−366).
- Los otros tres perfiles, en el mismo periodo: Conservador −438, Moderado −1 356, Agresivo −4 934
  USDT: el periodo es adverso para las ideas existentes, no solo para este perfil.

Lectura: el mecanismo funciona según lo especificado (verificado por tests y auditoría), pero
**las entradas actuales no tienen ventaja** frente a un SL inicial a ~2 % y costos de ≈0,16 %.
No se declara rentable. Siguiente paso razonable (fuera de este alcance): entradas propias del
perfil con filtro de calidad más estricto y SL inicial más corto, validado con la puerta T49.
