# T139 — Comprobación del camino: regresión, control y banco

Modo: **SIMULADO** · BTCUSDT · datos hasta 2026-11-06T03:30+00:00 · pre-registro `prereg_t139_v1` (SHA-256 `f24f72bfc3d8cc92…`, commit `3d396f7`, anterior a la descarga y a todo cálculo) · criterios `validation_v1` sin cambios · calculado con `b56993e` · familia de Holm de 841, 33640 réplicas.

Este tramo ya está contaminado y **no aprueba nada**. Las reglas están congeladas, así que verlo solo autoriza a corregir defectos, declarándolos.

## 1. Regresión contra T137

`control_aleatorio@1h`, publicado: n = 1810, bruto -0.009823.

- Con los contextos guardados: n = 1810, bruto -0.009823. ✓
- Con contextos mínimos: n = 1810, bruto -0.009823. ✓
- ATR propio frente al de los 33399 contextos: diferencia relativa mediana 0.0000000, máxima 0.0013231; 0 instantes sin vela.

## 2. Control en el banco

| Marco | n | Bruto real | Nulo: media | p95 | p | ¿Pasa? |
|---|--:|--:|--:|--:|--:|---|
| 1h | 2439 | +0.003 | +0.036 | +0.082 | 0.810 | ✓ |
| 4h | 603 | +0.028 | +0.027 | +0.120 | 0.524 | ✓ |

## 3. Las claves en el banco

| Clave | Veredicto | n | R medio | IC95 % | p bruto | p Holm | DD | Ventanas + | V1 | V2 | V3 | V4 | V5 | V6 |
|---|---|--:|--:|---|--:|--:|--:|--:|---|---|---|---|---|---|
| `funding_contra@1h@v1391` | RECHAZADA | 624 | -0.139 | [-0.22, -0.05] | 0.1421 | 1.0000 | 63% | 15/39 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `funding_contra@4h@v1391` | RECHAZADA | 330 | -0.017 | [-0.14, +0.11] | 0.1610 | 1.0000 | 19% | 16/32 | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ |
| `flujo_sigue@1h@v1391` | RECHAZADA | 857 | -0.236 | [-0.31, -0.16] | 0.4262 | 1.0000 | 88% | 5/47 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `flujo_sigue@4h@v1391` | EN OBSERVACIÓN | 222 | +0.018 | [-0.14, +0.17] | 0.0380 | 1.0000 | 12% | 14/27 | ✗ | ✗ | ✗ | ✓ | ✗ | ✓ |
| `flujo_revierte@1h@v1391` | RECHAZADA | 247 | -0.275 | [-0.42, -0.13] | 0.4856 | 1.0000 | 52% | 6/28 | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `flujo_revierte@4h@v1391` | RECHAZADA | 72 | -0.506 | [-0.73, -0.27] | 0.9986 | 1.0000 | 31% | 0/0 | ✗ | ✗ | ✗ | ✗ | · | ✓ |
| `cascada_revierte@1h@v1391` | RECHAZADA | 651 | -0.170 | [-0.26, -0.08] | 0.5300 | 1.0000 | 69% | 11/43 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `cascada_revierte@4h@v1391` | RECHAZADA | 390 | -0.051 | [-0.16, +0.07] | 0.3001 | 1.0000 | 24% | 20/40 | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ |
| `momento_1d@1d@v1391` | EN OBSERVACIÓN | 151 | -0.007 | [-0.18, +0.16] | 0.2803 | 1.0000 | 10% | 4/7 | ✗ | ✗ | ✗ | ✓ | ✗ | ✓ |

| Clave | n | Bruto | Costo | Mínimo necesario | Largos: n, bruto | Cortos: n, bruto | Equilibrado | Neto costos × 1,5 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| `funding_contra@1h` | 624 | +0.018 | 0.157 | 0.236 | 410, +0.007 | 214, +0.040 | +0.023 | -0.218 |
| `funding_contra@4h` | 330 | +0.063 | 0.079 | 0.212 | 218, +0.093 | 112, +0.004 | +0.048 | -0.056 |
| `flujo_sigue@1h` | 857 | -0.027 | 0.209 | 0.276 | 445, +0.034 | 412, -0.093 | -0.030 | -0.340 |
| `flujo_sigue@4h` | 222 | +0.113 | 0.095 | 0.258 | 125, +0.256 | 97, -0.072 | +0.092 | -0.030 |
| `flujo_revierte@1h` | 247 | -0.030 | 0.245 | 0.370 | 122, +0.118 | 125, -0.174 | -0.028 | -0.397 |
| `flujo_revierte@4h` | 72 | -0.375 | 0.131 | 0.454 | 26, -0.361 | 46, -0.382 | -0.372 | -0.572 |
| `cascada_revierte@1h` | 651 | -0.019 | 0.152 | 0.229 | 325, +0.022 | 326, -0.059 | -0.019 | -0.246 |
| `cascada_revierte@4h` | 390 | +0.037 | 0.088 | 0.195 | 214, +0.166 | 176, -0.119 | +0.024 | -0.095 |
| `momento_1d@1d` | 151 | +0.045 | 0.052 | 0.313 | 92, +0.148 | 59, -0.117 | +0.016 | -0.033 |
