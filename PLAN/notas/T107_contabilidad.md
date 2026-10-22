# T107 — Contabilidad honesta del capital: liquidación simulada, equity y drawdown

Fecha: 2026-10-22 · Alcance: bróker simulado (`v2/eim/paper`), panel y contratos de la vista.
Todo SIMULADO; no se tocó riesgo, apalancamiento, entradas ni ninguna regla de salida. Rutas
relativas a `v2/`.

## 1. Qué se cambió

| # | Cambio | Dónde |
|---|---|---|
| 1 | **Liquidación por posición.** Margen aislado: si el precio de salida quedó al otro lado del precio de liquidación (un hueco que dejó el stop atrás) o la pérdida calculada supera el margen, la posición se cierra con motivo propio `LIQUIDACION` y pierde **el margen entero**, no la pérdida imposible del hueco. | `paper/account.py` (`capped`), `paper/book.py` (`_close`) |
| 2 | **Suelo de la cuenta.** Como ninguna posición pierde más que su margen y ese margen ya estaba apartado del capital, se cumple siempre `capital ≥ margen en uso ≥ 0`: el capital **no puede quedar negativo**. | `paper/account.py` + test de la invariante |
| 3 | **Estado «agotada».** Con el capital realizado ≤ `min_equity_frac` (1 %) del inicial, el perfil queda agotado: deja de abrir, mantiene lo abierto hasta su cierre y lo dice en la bitácora (categoría `cuenta`), en el resumen (`exhausted`, `exhausted_t`, `min_equity`) y en el panel. **Sin recargas**, ni silenciosas ni automáticas. | `paper/params.py`, `paper/account.py`, `paper/vetoes.py`, `paper/summary.py` |
| 4 | **Una sola definición de cada cifra.** `balance` = realizado · `upnl` = flotante · `equity = balance + upnl` · `return_pct` **siempre sobre equity** (declarado en `return_base`) · `available` · `margin_used` · `reserved`. El panel muestra las dos primeras juntas y rotuladas, así que ya no se puede mezclar una columna con la variación de la otra. | `paper/summary.py`, `web/src/paper_head.ts`, `web/src/paper_profiles.ts` |
| 5 | **Drawdown con base y ventana declaradas.** `dd = {pct, base: "equity", from, to}`; el panel dice «Drawdown máx. (equity, todo el periodo)». Acotado al 100 % **por construcción** (consecuencia de 1 y 2), no por recorte: si vuelve a pasar de 100 % es un error y el test lo prohíbe. | `paper/account.py` (`max_dd_pct`), `paper/summary.py` |
| 6 | **Recuento de operaciones trazable.** `counts = {closed, by_origin, liquidations, violations, from, to, scope}`: origen (`vivo` / `backtest`), ventana real de los cierres y una frase que dice que el recuento **no tiene ventana** (la vista se recalcula desde todos los contextos del símbolo) y que, si T61 importó contextos de otras máquinas, también cuentan. | `paper/summary.py` + panel |
| 7 | **El flotante tampoco pasa del margen.** Una posición abierta cuya marca ya atravesó la liquidación mostraba una pérdida flotante imposible, y el `equity` del panel la incluye: ahora se topa al margen y se dice por qué (`liq_why`), en el servidor y en el cálculo en vivo de la interfaz. | `paper/summary.py` (`positions_of`), `web/src/paper_tables.ts` |
| 8 | **El dinero de un cierre inválido ya no desaparece** (alerta A5 de T106). Un cierre que viola las reglas de la escalera se sigue auditando como violación, pero su PnL **se contabiliza**: antes `_close` salía antes de sumarlo y la operación desaparecía de la cuenta. | `paper/book.py` (`_close`) |

Reordenado para no pasar de 300 líneas por archivo: `book.py` (287 → 259) dejó la contabilidad en
`account.py` (73) y los motivos de rechazo en `vetoes.py` (60). `leverage_for` y `liq_price` viven
ahora en `account.py` y se siguen pudiendo importar desde `book`.

## 2. Diferencias con los números anteriores, una por una

**Con el almacén de hoy no cambia ninguna cifra del panel.** Comprobado sobre las 157 operaciones
cerradas y las 14 posiciones abiertas de la vista en vivo (`/v2/paper/trades` y `/v2/paper`,
2026-10-22 01:58 COT, con el código anterior): **ninguna** habría sido liquidada y **ninguna**
pérdida llega al margen.

| Símbolo · perfil | Ops | Liquidables | Peor pérdida / margen | Diferencia en el PnL |
|---|--:|--:|--:|--:|
| BTCUSDT · Conservador | 10 | 0 | −2,5 % | 0,00 |
| BTCUSDT · Moderado | 31 | 0 | −9,8 % | 0,00 |
| BTCUSDT · Agresivo | 24 | 0 | −13,4 % | 0,00 |
| BTCUSDT · PPP | 10 | 0 | −8,5 % | 0,00 |
| ETHUSDT · Conservador | 10 | 0 | −7,6 % | 0,00 |
| ETHUSDT · Moderado | 42 | 0 | −15,0 % | 0,00 |
| ETHUSDT · Agresivo | 30 | 0 | −25,4 % | 0,00 |

Las 14 abiertas tampoco se topan: la peor va a −12,3 % de su margen y la marca está lejos de su
liquidación (82.484 contra 75.452 en el caso más cercano). Así que las filas del panel de hoy
—BTCUSDT: Conservador 10.003,62 / +0,04 % / 1,24 % de DD; Moderado 9.430,74 / −5,69 % / 6,43 %;
Agresivo 9.429,47 / −5,71 % / 9,06 %— **se mantienen idénticas**, con estos añadidos: cada una
declara su base, el recuento declara su origen, y aparecen `liquidations = 0` y «Estado: operando».

**Lo que sí cambia es el caso que T106 reprodujo** (tres huecos que ejecutaban el stop a 0,10 USDT
con la liquidación en 90,40), fijado en `tests/paper/test_accounting_audit.py`:

| Cifra | Antes (T106) | Ahora (T107) | Por qué |
|---|--:|--:|---|
| PnL de cada operación | −9.990,00 | −1.000,00 | se pierde el margen, no el hueco |
| Capital final | **−19.970,00** | **7.000,00** | suelo de la cuenta |
| Drawdown máximo | **299,70 %** | **30,00 %** | consecuencia directa del anterior |
| `return_pct` | −299,70 % | −30,00 % | misma base (equity), capital creíble |
| Motivo de cierre | `SL` | `LIQUIDACION` | categoría propia; el `SL` original queda en `reason_path` |
| R de la operación | −99,9 (del motor) | −10,0 | margen perdido / riesgo (100 USDT) |

Y el 1204 % del Agresivo que motivó la tarea exigía un capital de ≈ −110.400 USDT, que ahora es
imposible de construir. No es reproducible con este almacén (T106 §2c ya lo documentó: esa fila
venía de otro estado del almacén y la vista no guarda instantánea), así que no hay un «antes y
después» de esa pantalla: lo que queda cerrado es el **mecanismo** que la hacía posible.

Cifras que cambian de nombre, no de valor: «Saldo de la cartera» → **«Saldo realizado (balance)»**
y «Capital (equity)» → **«Capital (equity = saldo + flotante)»**.

Cambio de comportamiento sin efecto medible hoy: con el PnL de las violaciones contabilizado (8),
un perfil en modo escalera suma esas operaciones a su resultado. En la vista actual hay **0
violaciones**, así que ninguna cifra se mueve; la que se movería es la de un futuro con la escalera
en los tres perfiles (T109), que es justo donde el agujero habría importado.

## 3. Lo que NO se hizo (y a quién le toca)

- **Instantánea auditable del panel** (alerta A4 de T106): la vista sigue recalculándose desde todo
  el almacén en cada consulta, así que una pantalla de ayer no se puede volver a ver. Lo que se hizo
  es declararlo en las propias cifras (`counts.scope`) y dejar el libro fijo como único registro
  inmutable. Guardar una instantánea por consulta es otro trabajo (queda en el backlog).
- Parámetros por símbolo (`tick`, `qty_step`), velas de 1 min de ETHUSDT y umbral en R: **T108**.
- La protección progresiva en los tres perfiles: **T108–T109**.
- Rediseñar el panel: fuera de alcance; solo se rotularon y añadieron filas.
- El importe de mantenimiento sigue sin modelarse: la liquidación es la aproximación de siempre
  (`liq_price`, sin margen de mantenimiento escalonado), ahora **aplicada** además de mostrada.

## 4. Pruebas

- `tests/paper/test_account.py` (9): liquidación en largo y en corto (pierde el margen y nada más),
  invariante `capital ≥ margen ≥ 0` en toda la curva, `max_dd_pct ≤ 1`, cuenta agotada que deja de
  abrir y lo dice, flotante topado al margen, coherencia
  `balance` / `upnl` / `equity` / `return_pct` / `available`, procedencia del recuento y las
  funciones puras (`capped`, `exhausted`, `max_dd_pct`).
- `tests/paper/test_accounting_audit.py`: los dos tests que fijaban el defecto pasaron a fijar el
  comportamiento correcto, con las cifras de antes anotadas en su docstring.
- `tests/paper/test_ladder_book.py::test_forged_time_or_tp_close_is_a_violation_but_the_money_is_accounted`:
  la violación se registra y el PnL entra en la cuenta.
- Interfaz: `npx tsc --noEmit` limpio.
