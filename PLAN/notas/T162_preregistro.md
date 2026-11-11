# T162 — Pre-registro: volatilidad del cono (HAR, GARCH estimado, combinación y ACI)

Fijado el 2026-11-11, **antes de calcular ningún resultado**, en un commit propio. Nada de lo que sigue se cambia después de mirar cifras; si un defecto del código obliga a repetir, se declara en el informe.

**Modo: SIMULADO.** Mide; no toca el forecaster en vivo. Aunque pase, no se adopta antes del cierre de T31 (2026-11-27), igual que T160.

## Pregunta

¿Algún pronóstico de la varianza del día siguiente es mejor que el que usa hoy el cono (GARCH(1,1) con α = 0,07 y β = 0,91 fijos, arranque EWMA λ = 0,94 sobre las últimas 1 500 velas de 1 h, `forecast/base_engine.py`)? El cono proyecta 20–30 velas de 1 h, así que el día siguiente es su horizonte natural.

## Datos y objetivo

- BTCUSDT, `backups/t139_banco` (velas de 1 min desde 2019-09-08).
- **Objetivo:** varianza realizada del día UTC, RV5 = Σ de log-retornos de 5 min al cuadrado dentro del día (cierres de 1 min tomados cada 5; el muestreo a 5 min reduce el ruido de microestructura de 1 min).
- **Retorno diario:** log del último cierre de 1 min del día sobre el último del día anterior.
- Un día solo cuenta si tiene ≥ 90 % de sus velas de 1 min.
- **Tramo evaluado:** del 2021-01-01 al último día completo. Antes de esa fecha, solo ajuste. Se informa además el subtramo 2024-01-01 → final por separado.

## Familia (familia de calibración propia, 3 intentos; no se suma a la de trading de 841)

| Id | Modelo | Ajuste (siempre solo con días anteriores) |
|---|---|---|
| M0 | Referencia: el GARCH fijo del cono, agregado a 24 h: Σ_{k=1..24} E[σ²_{t+k}] con la recursión del motor base | Sin ajuste (parámetros fijos) |
| M1 | Log-HAR-RV: ln RV_{t+1} = c + β_d ln RV_t + β_w ln RV̄_t^(5) + β_m ln RV̄_t^(22); pronóstico exp(ŷ + s²/2) | Mínimos cuadrados con todos los días anteriores, reajuste diario |
| M2 | GJR-GARCH(1,1) con t de Student sobre retornos diarios (`arch`) | Reajuste cada 20 días con los días anteriores; entre reajustes, filtro con parámetros fijos |
| M3 | Combinación con pesos iguales de M1 y M2 | — |

## Métricas

- **Principal:** QLIKE diaria, L = RV/ĥ − ln(RV/ĥ) − 1 (robusta a ruido en el objetivo; Patton 2011).
- **Secundarias (descriptivas, no deciden):** MSE de la varianza; CRPS y PIT de la predictiva normal N(0, ĥ) del retorno diario; cobertura de la banda del 80 %.

## Calibración conformal adaptativa (ACI, Gibbs y Candès 2021)

Sobre cada modelo, banda del 80 % del retorno diario: |r_t| ≤ q_t·√ĥ_t, con q_t el cuantil 1 − α_t de los |r|/√ĥ de los 250 días anteriores y α_{t+1} = α_t + γ·(0,20 − fallo_t), γ = 0,005. Se informan la cobertura sin ACI y con ACI, global, en 2024–2026 y la peor ventana de 90 días.

## Regla de adopción (se aplica tal cual)

Un modelo Mk (k = 1, 2, 3) **pasa** si se cumplen las tres:

1. **Model Confidence Set** al 10 % sobre las pérdidas QLIKE de {M0, M1, M2, M3} (bootstrap estacionario, bloque de Politis-White, 5 000 repeticiones, semilla 162): Mk está dentro y **M0 queda fuera**.
2. **Mejora frente a M0:** la diferencia media de QLIKE (Mk − M0) tiene un IC del 95 % por bootstrap estacionario que **excluye 0** por debajo, y su p unilateral **ajustada por Holm en la familia de 3** es < 0,05.
3. **Cobertura con ACI** de la banda del 80 % dentro de **80 % ± 2 pp** en todo el tramo evaluado y también en 2024–2026.

Si pasan varios, se propone el de menor QLIKE media. Si no pasa ninguno, el cono sigue con M0 y el informe lo dice así.

## Lo que esta tarea no hace

- No cambia el forecaster en vivo ni las bandas dibujadas: la adopción, si la hay, es otra entrega tras el cierre de T31.
- Kronos no se mide aquí: necesita torch, que el venv no tiene; queda en BACKLOG con su propio aviso de memoria.
- No toca las probabilidades de escenario (T160, cerrada) ni el σ de las salidas del papel (`paper/exits/harrv.py`).
- Los diagramas de Murphy quedan en BACKLOG.
