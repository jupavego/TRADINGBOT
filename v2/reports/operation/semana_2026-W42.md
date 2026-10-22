# Informe de operación — 2026-W42

**Modo: SIMULADO** (sin dinero real). Periodo 2026-10-12 00:00 UTC → 2026-10-19 00:00 UTC; semanas operadas 0.61. Generado 2026-10-19 00:00 UTC.

> T31 exige ≥ 4 semanas continuas sin incidentes de reconciliación sin resolver. La decisión de capital real la toma el usuario por escrito; este informe no la habilita.

## Resultados

| Símbolo | Operaciones | Con resultado | R medio neto | IC95 % | Acierto | R total |
|---|---|---|---|---|---|---|
| BTCUSDT | 0 | 0 | — | — | — | — |
| TOTAL | 0 | 0 | — | — | — | — |

Capital: 10,000.00 → 10,002.18 USDT (+0.02%), drawdown máx. 0.68%. R neto de comisión estimada, sin funding.

## Comparación con el backtest

- BTCUSDT: backtest 242 operaciones en 182 semanas (1.3/semana), esperanza -0.49 R, DD máx. 23%. Fuente: reports/edge/edge_results.json (T27, ventanas fuera de muestra).

### Desviaciones

- BTCUSDT: 0.0 operaciones/semana vs 1.3 en backtest (0%).
- BTCUSDT: sin operaciones cerradas: no hay R que comparar.

## Calibración de escenarios

- BTCUSDT: 445 pronósticos evaluados (56 pendientes); Brier skill +0.2%, cobertura 80 % 91%.
  - 445 pronósticos evaluados; por solape entre horizontes la muestra efectiva es ≈18 independientes: las diferencias pequeñas no son concluyentes.
  - Bandas fuera de la cobertura nominal (±5 pp) en 50 %: 77% observado; 80 %: 91% observado; 90 %: 97% observado.
  - Las probabilidades de escenario NO superan a la caminata aleatoria (Brier skill +0.2%).
  - La distribución terminal NO supera a la caminata aleatoria (pinball skill -3.1%).
  - Acierto direccional 52.5% (n=444): no distinguible del azar.
  - Calibración imperfecta (error esperado 17.8%).
  - Conclusión: no supera la línea base; usar la proyección solo como rango de incertidumbre, no como señal.

## Incidentes

6 alertas: agentes_degradados 4, desconexion 2.
Reconciliación sin resolver: ninguna.

- 2026-10-16 03:01 UTC · warn · Agentes degradados en BTCUSDT: plan=degraded
- 2026-10-16 22:16 UTC · warn · Agentes degradados en BTCUSDT: arbitrage=degraded
- 2026-10-17 01:59 UTC · warn · Agentes degradados en BTCUSDT: plan=degraded
- 2026-10-18 15:03 UTC · critical · Sin datos de BTCUSDT: 152 s sin respuesta del proveedor de velas
- 2026-10-18 15:37 UTC · critical · Sin datos de BTCUSDT: 152 s sin respuesta del proveedor de velas
- 2026-10-18 20:01 UTC · warn · Agentes degradados en BTCUSDT: plan=degraded

## Riesgo

28 decisiones registradas, 25 vetadas. Motivos más frecuentes: operaciones abiertas (22), vigencia (11), datos (1).
