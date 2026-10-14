# T27 — Puerta de edge (informe de decisión)

Modo: **SIMULADO** (backtest con costos de perpetuo). Fecha: 2026-10-13.

## 1. Criterios (fijados ANTES de calcular los resultados de esta puerta)

Declaración honesta: el agregado fuera de muestra de T26 (BTC/ETH 1h, Sharpe ≈ −2.5) ya se
conocía al escribir estos criterios. Por eso los umbrales NO se ajustan a esos números: son
umbrales estándar y conservadores, y ninguno se modificó después de calcular lo de abajo.

Objeto evaluado: estrategia completa agentes → síntesis → plan (`PlanStrategy`) con los
parámetros **vigentes** (`calibration.space.defaults()`; T26 rechazó la versión calibrada).
Datos: Binance Futures 1h, BTCUSDT y ETHUSDT, 2023-01-01 → 2026-10-13. Ventanas de prueba
disjuntas de 4 380 velas (≈6 meses) desde la vela 504; costos de T25 (comisión taker/maker,
deslizamiento por volatilidad/tamaño, funding real), riesgo 1 % por operación, apalancamiento 5×.

| # | Criterio | Umbral para PASAR |
|---|---|---|
| C1 | Retorno ajustado por riesgo neto | Sharpe agregado neto > 0 **y** > Sharpe de comprar y mantener en el mismo periodo, en BTC y en ETH |
| C2 | Contra entrada aleatoria con el mismo riesgo | Mismas fechas de decisión, mismo SL/TP en distancia y mismos costos, lado al azar (≥ 500 réplicas): p unilateral < 0.05 **tras Holm** en BTC y en ETH |
| C3 | Esperanza por operación | R medio neto > 0 con IC95 % (bootstrap) que excluye 0, en ambos activos |
| C4 | Tamaño de muestra | ≥ 100 operaciones fuera de muestra por activo |
| C5 | Drawdown máximo tolerable | DD máximo agregado ≤ 25 % por activo |
| C6 | Estabilidad | Sharpe > 0 en ≥ 60 % de las ventanas de cada activo y mismo signo de Sharpe agregado en BTC y ETH |
| C7 | Calibración de probabilidades (T19) | Backfill sobre datos reales: Brier skill y pinball skill > +2 % frente a la caminata aleatoria, cobertura terminal 80 % dentro de 80 ± 8 pp |

Pruebas múltiples: la familia {C1-BTC vs B&H, C1-ETH vs B&H, C2-BTC, C2-ETH, C3-BTC, C3-ETH}
se corrige con Holm–Bonferroni (α = 0.05). Además se recuerda que T26 exploró 40 trials × 5
pliegues: cualquier resultado positivo marginal debería descontarse por esa búsqueda.

Regla de veredicto (fijada de antemano):
- **PASA**: C1–C7 se cumplen.
- **PASA CON RESERVAS**: C1–C5 se cumplen y falla solo C6 o C7.
- **NO PASA**: falla cualquiera de C1–C5.


## 2. Cómo se obtuvo la evidencia

`python -m eim.calibration.gate_cli --store data --null 500 --fc-origins 400` (desde `v2/`)
→ `reports/edge/edge_results.json` (semilla 0, reproducible). Código: `eim/backtest/edge.py`
(nulos y pruebas, con tests en `tests/backtest/test_edge.py`) y `eim/calibration/gate_cli.py`.

- 7 ventanas disjuntas por activo (2023-01-22 → 2026-07-22), mismas fechas en BTC y ETH; las
  500 velas previas a cada ventana son solo contexto. Decisión cada 6 velas, ejecución en la
  apertura siguiente, salida por tiempo a las 96 velas.
- Los parámetros vigentes no se ajustaron con estos datos (T26 rechazó la calibración), así que
  todo el periodo es fuera de muestra para ellos.
- Entrada aleatoria: se graban las decisiones reales (instante, cierre, SL, TP) y se reproducen
  con el lado al azar y SL/TP reflejados (misma distancia en R, mismos costos). Control: la
  réplica sin azar reproduce exactamente las operaciones reales (verificado en cada ventana).
- Datos: hash de velas+funding BTC `6d2af63569ccda2c` (fuente `binance-futures-ws`), ETH
  `d1f46cb59f18d07f` (`binance-futures`). Difieren de los de T26 porque el almacén local se
  actualizó desde entonces; las cifras agregadas coinciden en orden de magnitud.

## 3. Resultados contra cada criterio

### Agregado fuera de muestra (neto de costos)

| Métrica | BTCUSDT | ETHUSDT |
|---|---|---|
| Operaciones | 242 | 237 |
| Retorno total | −69.8 % | −71.2 % |
| Sharpe anual (IC95 % bootstrap por bloques) | **−2.39** (−3.42, −1.36) | **−2.80** (−3.85, −1.72) |
| Sortino | −3.02 | −3.57 |
| DD máximo | **69.8 %** | **72.3 %** |
| R medio neto por operación (IC95 %) | **−0.49** (−0.66, −0.29) | **−0.51** (−0.69, −0.33) |
| Acierto | 28.1 % | 27.0 % |
| Factor de beneficio (IC95 %) | 0.52 (0.39, 0.69) | 0.48 (0.34, 0.63) |
| Exposición | 8.7 % | 9.6 % |
| Comprar y mantener: Sharpe / retorno | +0.88 / +188 % | +0.39 / +18 % |
| Entrada aleatoria (500): Sharpe medio [p5, p95] | −2.01 [−2.71, −1.30] | −2.12 [−2.89, −1.38] |
| Entrada aleatoria: R medio neto | −0.43 | −0.42 |

### Por ventana (Sharpe estrategia / Sharpe comprar y mantener)

| Ventana | BTC | ETH |
|---|---|---|
| 2023-01 → 2023-07 | −1.74 / +1.40 | −5.21 / +0.82 |
| 2023-07 → 2024-01 | −2.28 / +1.83 | −1.67 / +1.44 |
| 2024-01 → 2024-07 | −2.99 / +2.14 | −2.25 / +1.45 |
| 2024-07 → 2025-01 | −3.02 / +1.82 | −2.13 / +0.15 |
| 2025-01 → 2025-07 | −2.40 / +0.89 | −3.14 / +0.70 |
| 2025-07 → 2026-01 | −1.91 / −1.33 | −4.44 / −0.41 |
| 2026-01 → 2026-07 | −2.45 / −1.02 | −1.11 / −1.06 |

La estrategia pierde en las 14 ventanas (7 por activo), tanto en mercado alcista como bajista.

### Significancia (unilateral, H1 = la estrategia es mejor) con corrección de Holm

| Hipótesis | p bruto | p Holm |
|---|---|---|
| BTC: Sharpe > comprar y mantener (bootstrap pareado por bloques) | 1.00 | 1.00 |
| ETH: Sharpe > comprar y mantener | 1.00 | 1.00 |
| BTC: Sharpe > entrada aleatoria (permutación, 500) | 0.81 | 1.00 |
| ETH: Sharpe > entrada aleatoria | 0.93 | 1.00 |
| BTC: R medio neto > 0 (bootstrap) | 1.00 | 1.00 |
| ETH: R medio neto > 0 | 1.00 | 1.00 |

Ninguna hipótesis se acerca a α = 0.05; la corrección por pruebas múltiples no cambia nada.

### Calibración de escenarios (T19, backfill sobre BTCUSDT 1h real)

400 pronósticos con horizonte 25 y orígenes **sin solape** (cada 25 velas; ≈ 2025-08 → 2026-10),
así que la muestra efectiva es 400 (el texto automático de T19 dice «≈16» porque asume
orígenes consecutivos; aquí no aplica).

| Métrica | Valor | Umbral C7 |
|---|---|---|
| Cobertura terminal 50 / 80 / 90 % | 53.0 / 80.3 / 91.0 % | 80 % ∈ [72, 88] ✔ |
| Brier skill vs caminata aleatoria | −0.4 % | > +2 % ✘ |
| Pinball skill vs caminata aleatoria | −1.2 % | > +2 % ✘ |
| Acierto direccional (n = 382) | 49.5 % | (azar) |
| Error de calibración esperado | 1.2 % | — |

Las bandas están bien calibradas (miden bien la incertidumbre), pero no aportan información
direccional: equivalen a una caminata aleatoria con la volatilidad correcta.

### Diagnóstico (exploratorio, fuera de la familia de pruebas)

| | BTC | ETH |
|---|---|---|
| R bruto medio (antes de costos) | −0.12 | −0.22 |
| Costo medio por operación en R | 0.36 | 0.30 |
| R bruto medio de la entrada aleatoria | −0.06 | −0.13 |
| p (R bruto > aleatorio) | 0.78 | 0.87 |

Dos problemas independientes: (1) **sin habilidad direccional**: antes de costos la estrategia
no supera a elegir el lado al azar con la misma geometría (incluso queda algo por debajo);
(2) **costos desproporcionados**: comisiones + deslizamiento + funding consumen ≈ 0.3–0.36 R por
operación, porque los SL estructurales quedan cerca del precio en 1h. Aun con R bruto 0
(ni ventaja ni desventaja direccional), la estrategia perdería ≈ 1/3 de R por operación.

### Resumen por criterio

| # | Criterio | BTC | ETH | Resultado |
|---|---|---|---|---|
| C1 | Sharpe neto > 0 y > comprar y mantener | −2.39 vs +0.88 | −2.80 vs +0.39 | ✘ FALLA |
| C2 | Supera entrada aleatoria (p Holm < 0.05) | p = 1.00 | p = 1.00 | ✘ FALLA |
| C3 | R neto > 0 con IC que excluye 0 | IC (−0.66, −0.29) | IC (−0.69, −0.33) | ✘ FALLA (significativamente negativo) |
| C4 | ≥ 100 operaciones | 242 | 237 | ✔ cumple |
| C5 | DD máx ≤ 25 % | 69.8 % | 72.3 % | ✘ FALLA |
| C6 | Sharpe > 0 en ≥ 60 % de ventanas; mismo signo BTC/ETH | 0/7 | 0/7 | ✘ FALLA (signo coherente, pero negativo) |
| C7 | Calibración de escenarios | Brier −0.4 %, pinball −1.2 %, cob80 80 % | — | ✘ FALLA (cobertura ✔, skill ✘) |

## 4. Veredicto: **NO PASA**

Fallan C1, C2, C3, C5, C6 y C7; solo se cumple el tamaño de muestra (C4). El resultado no es
ruido: el IC95 % de la esperanza por operación es negativo en ambos activos, la pérdida es
consistente en 14 de 14 ventanas, y en BTC y ETH por igual. **El sistema, tal como está, no
tiene ventaja estadística fuera de muestra neta de costos.** Tampoco la tiene antes de costos
frente a una entrada al azar con el mismo riesgo.

Consecuencia (según el plan): **no se avanza a T29** (motor de riesgo) ni a testnet/dinero real.
Las hipótesis de mejora están en `PLAN/BACKLOG.md` (no se implementan aquí). **Decisión del
usuario (2026-10-13): acepta el NO PASA.** T29 no se inicia; se vuelve a las hipótesis del BACKLOG.

## 5. Riesgos y limitaciones conocidos de esta evaluación

- **Simulación, no ejecución real**: deslizamiento modelado (no libro de órdenes histórico);
  sin latencia ni rechazos. Afecta poco a la conclusión: el resultado es negativo incluso antes
  de costos.
- **Insumos de structure/levels memoizados** con ventana móvil de 500 velas (fidelidad medida en
  T26: 7/7 entradas idénticas en 720 velas); decisión cada 6 velas, no cada vela.
- **Solo 1h y solo BTC/ETH**; no se probaron otros marcos ni el agente de derivados,
  microestructura, régimen o contexto (no entran en la estrategia `PlanStrategy` de T25).
- **Nulo aleatorio aproximado**: reproduce las decisiones grabadas, de modo que si la réplica
  está en posición cuando la original estaba plana, se omite esa decisión (nº de operaciones
  similar, no idéntico).
- **Criterios no ciegos del todo**: el agregado de T26 ya se conocía (ver §1). Como el
  resultado es negativo con margen amplio, no hay riesgo de que esto haya inflado un «PASA».
- **Calibración de escenarios** solo en BTC y en los últimos ≈14 meses; el motor de proyección
  es la línea base GARCH (Kronos sin evaluar).
