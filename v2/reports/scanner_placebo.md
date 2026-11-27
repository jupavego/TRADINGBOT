# T95 — Control placebo del escáner global

Generado 2026-11-26T21:11:41+00:00 · corte 2026-11-26T00:00:00+00:00 (última vela guardada) · universo de 564 perpetuos que pasan las etapas 1–2 · lista corta 25 · 20 agentes (huella `5408dfe063b8`) · pesos `9e2456710c6e` (iguales (0,25 cada una), sin calibrar: pre-registro T95) · semilla 95.
Pre-registro `PLAN/notas/T95_preregistro.md` (SHA-256 `102572d1bfbafc753265fc0a13ea6646e9f842d928cf8169b39e63c84c56b4e5`), anterior a esta corrida. Modo ANÁLISIS: nada de esto es una orden ni una validación.

## Respuesta a la ◆

**No: el escáner no muestra nada que supere el azar** en el universo de Binance. Con el umbral 0.669, 0 candidata(s) reales lo superan (el azar daría 0.07 por pasada) y el p global de «el mejor hallazgo real supera al mejor del azar» es 0.1613 (α = 0.05). Un «no» es un resultado válido (T95).

Aunque saliera «sí», ninguna candidata queda **validada**: eso solo lo da la puerta v1 de T49, y el registro de intentos hacia adelante empieza hoy (0 resultados maduros: p ajustado = 1 para todas hasta que maduren ≥ 10 observaciones por intento).

## Real frente a placebo

| | Réplicas | Candidatas (media) | Máx. prioridad | Umbral | Reales ≥ umbral | Falsos por pasada | FDR estimada | p global |
|---|---|---|---|---|---|---|---|---|
| Real | — | 25 | 0.664 | — | — | — | — | — |
| Permutada (vinculante) | 30 | 22.6 | 0.632 (mediana) | 0.669 | 0 | 0.07 | — | 0.1613 |
| Gaussiana (sensibilidad) | 10 | 22.8 | 0.664 (mediana) | 0.693 | 0 | 0.10 | — | 0.5455 |

Umbral: cuantil 95% (método «higher») del máximo por réplica. Tasa de falsos por candidata con ese umbral: 0.0030.

## Candidatas reales por prioridad

| # | Instrumento | Lado | Prioridad | ≥ umbral | Ventaja neta (σ) | Ventaja (R) | Incertidumbre (σ) | Señal | Viabilidad | Riesgo/costos |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | VVVUSDT | largo | 0.664 | no | 0.39 | 0.91 | 1.11 | 0.36 | 0.93 | 0.72 |
| 2 | MSTRUSDT | corto | 0.590 | no | -0.16 | -0.21 | 0.97 | 0.24 | 0.94 | 0.75 |
| 3 | PAXGUSDT | corto | 0.586 | no | -0.22 | -0.32 | 1.12 | 0.25 | 0.98 | 0.71 |
| 4 | OPGUSDT | largo | 0.585 | no | 0.10 | 0.17 | 1.16 | 0.36 | 0.70 | 0.73 |
| 5 | COINUSDT | corto | 0.575 | no | -0.12 | -0.18 | 0.94 | 0.24 | 0.89 | 0.72 |
| 6 | MONUSDT | corto | 0.574 | no | -0.06 | -0.07 | 1.08 | 0.25 | 0.82 | 0.75 |
| 7 | BMNRUSDT | corto | 0.572 | no | -0.04 | -0.05 | 1.02 | 0.24 | 0.81 | 0.75 |
| 8 | XAUTUSDT | corto | 0.572 | no | -0.08 | -0.12 | 0.99 | 0.24 | 0.87 | 0.72 |
| 9 | OUSDT | largo | 0.564 | no | 0.18 | 0.26 | 0.98 | 0.24 | 0.66 | 0.79 |
| 10 | BANKUSDT | corto | 0.558 | no | 0.03 | 0.06 | 1.16 | 0.23 | 0.77 | 0.72 |
| 11 | REZUSDT | corto | 0.550 | no | -0.10 | -0.17 | 0.85 | 0.25 | 0.75 | 0.75 |
| 12 | SYRUPUSDT | corto | 0.550 | no | -0.18 | -0.16 | 1.14 | 0.22 | 0.78 | 0.77 |
| 13 | BNCUSDT | corto | 0.549 | no | 0.02 | 0.02 | 0.99 | 0.25 | 0.69 | 0.75 |
| 14 | MUBARAKUSDT | corto | 0.544 | no | -0.25 | -0.40 | 1.20 | 0.29 | 0.80 | 0.69 |
| 15 | XPDUSDT | corto | 0.540 | no | -0.14 | -0.21 | 0.94 | 0.24 | 0.78 | 0.69 |

## Límites (dichos tal cual)

- Es **una** pasada real frente a réplicas: dice si la prioridad del escáner distingue el universo real de uno sin estructura temporal, no si una candidata paga. Eso lo mide el registro de intentos hacia adelante (Holm/BH sobre la familia completa) y, al final, la puerta v1 de T49.
- La permutación conserva volatilidad, distribución y correlación contemporánea, y destruye también la agrupación de la volatilidad; la gaussiana no conserva colas.
- Con 30 réplicas el p global más pequeño posible es 0.032; el umbral es una estimación con esa resolución.
- Las cifras de prioridad y ventaja salen de la proyección existente (deriva de la síntesis), no de resultados: son lecturas comparables, no rentabilidades.
