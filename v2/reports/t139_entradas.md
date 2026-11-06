# T139 — Hipótesis de entrada: la lectura limpia

Modo: **SIMULADO** · BTCUSDT · datos hasta 2026-11-06T03:30+00:00 · pre-registro `prereg_t139_v1` (SHA-256 `f24f72bfc3d8cc92…`, commit `3d396f7`, anterior a la descarga y a todo cálculo) · criterios `validation_v1` sin cambios · calculado con `0d04ab3` · familia de Holm de 841, 33640 réplicas.

## 1. Recomendación

**P1. Parar la búsqueda (P1): ninguna clave sigue ni queda en observación, y no hay segunda ronda.**

Parar no prueba que no exista ventaja: prueba que no la hay por encima de lo detectable con estos datos. Ninguna clave puede salir VALIDADA aún: V5 exige 20 operaciones en vivo, y se fijó antes de calcular.

## 2. La puerta de T49, tal cual

Cuenta lo anterior a 2023 y lo posterior al alta.

| Clave | Veredicto | n | R medio | IC95 % | p bruto | p Holm | DD | Ventanas + | V1 | V2 | V3 | V4 | V5 | V6 |
|---|---|--:|--:|---|--:|--:|--:|--:|---|---|---|---|---|---|
| `funding_contra@1h@v1391` | RECHAZADA | 454 | -0.040 | [-0.15, +0.06] | 0.0187 | 1.0000 | 34% | 13/29 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `funding_contra@4h@v1391` | RECHAZADA | 232 | -0.034 | [-0.17, +0.11] | 0.2083 | 1.0000 | 15% | 10/24 | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ |
| `flujo_sigue@1h@v1391` | RECHAZADA | 635 | -0.080 | [-0.18, +0.02] | 0.0158 | 1.0000 | 49% | 10/32 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `flujo_sigue@4h@v1391` | RECHAZADA | 152 | +0.182 | [+0.00, +0.37] | 0.0016 | 1.0000 | 7% | 13/19 | ✓ | ✓ | ✗ | ✓ | · | ✓ |
| `flujo_revierte@1h@v1391` | RECHAZADA | 205 | -0.273 | [-0.43, -0.11] | 0.9436 | 1.0000 | 44% | 6/23 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `flujo_revierte@4h@v1391` | RECHAZADA | 60 | -0.221 | [-0.51, +0.08] | 0.8359 | 1.0000 | 15% | 0/1 | ✗ | ✗ | ✗ | ✓ | · | ✓ |
| `cascada_revierte@1h@v1391` | RECHAZADA | 451 | -0.103 | [-0.21, +0.01] | 0.3074 | 1.0000 | 41% | 7/31 | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `cascada_revierte@4h@v1391` | RECHAZADA | 266 | -0.010 | [-0.14, +0.12] | 0.1053 | 1.0000 | 15% | 14/27 | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ |
| `momento_1d@1d@v1391` | RECHAZADA | 121 | +0.048 | [-0.15, +0.25] | 0.2165 | 1.0000 | 9% | 0/4 | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ |

## 3. El bruto, frente a lo que haría falta

«Mínimo necesario» es la cuenta de la ficha con σ = 1 R: `max(z_Holm·σ/√n, costo + 1,96·σ/√n)`. El equilibrado es la media simple de largos y cortos: cancela la deriva.

| Clave | n | Bruto | Costo | Mínimo necesario | Largos: n, bruto | Cortos: n, bruto | Equilibrado | Neto costos × 1,5 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| `funding_contra@1h` | 454 | +0.054 | 0.095 | 0.187 | 252, +0.105 | 202, -0.009 | +0.048 | -0.088 |
| `funding_contra@4h` | 232 | +0.007 | 0.041 | 0.253 | 126, +0.106 | 106, -0.112 | -0.003 | -0.055 |
| `flujo_sigue@1h` | 635 | +0.060 | 0.140 | 0.218 | 330, +0.108 | 305, +0.009 | +0.058 | -0.150 |
| `flujo_sigue@4h` | 152 | +0.250 | 0.068 | 0.312 | 74, +0.330 | 78, +0.174 | +0.252 | +0.149 |
| `flujo_revierte@1h` | 205 | -0.093 | 0.180 | 0.317 | 96, +0.011 | 109, -0.184 | -0.087 | -0.363 |
| `flujo_revierte@4h` | 60 | -0.120 | 0.100 | 0.497 | 29, -0.208 | 31, -0.038 | -0.123 | -0.271 |
| `cascada_revierte@1h` | 451 | +0.012 | 0.115 | 0.207 | 214, -0.042 | 237, +0.060 | +0.009 | -0.160 |
| `cascada_revierte@4h` | 266 | +0.059 | 0.069 | 0.236 | 121, -0.015 | 145, +0.121 | +0.053 | -0.044 |
| `momento_1d@1d` | 121 | +0.115 | 0.066 | 0.350 | 73, +0.218 | 48, -0.042 | +0.088 | +0.015 |

## 4. La regla de lectura, condición a condición

| Clave | Estado | Puerta | Equilibrado > costo | Costos × 1,5 | Sobre sustitutas | Banco ≥ 0 | p95 sustitutas | Bruto en el banco |
|---|---|---|---|---|---|---|--:|--:|
| `funding_contra@1h` | fuera | ✗ | ✗ | ✗ | ✗ | ✓ | +0.116 | +0.018 (624) |
| `funding_contra@4h` | fuera | ✗ | ✗ | ✗ | ✗ | ✓ | +0.160 | +0.063 (330) |
| `flujo_sigue@1h` | fuera | ✗ | ✗ | ✗ | ✗ | ✗ | +0.111 | -0.027 (857) |
| `flujo_sigue@4h` | fuera | ✗ | ✓ | ✓ | ✓ | ✓ | +0.165 | +0.113 (222) |
| `flujo_revierte@1h` | fuera | ✗ | ✗ | ✗ | ✗ | ✗ | +0.149 | -0.030 (247) |
| `flujo_revierte@4h` | fuera | ✗ | ✗ | ✗ | ✗ | ✗ | +0.267 | -0.375 (72) |
| `cascada_revierte@1h` | fuera | ✗ | ✗ | ✗ | ✗ | ✗ | +0.088 | -0.019 (651) |
| `cascada_revierte@4h` | fuera | ✗ | ✗ | ✗ | ✗ | ✓ | +0.131 | +0.037 (390) |
| `momento_1d@1d` | fuera | ✗ | ✓ | ✓ | ✗ | ✓ | +0.130 | +0.045 (151) |

## 5. Control con entradas al azar

Antes de 2023, frente a sus series sustitutas: no puede destacar.

| Marco | n | Bruto real | Nulo: media | p95 | p | ¿Pasa? |
|---|--:|--:|--:|--:|--:|---|
| 1h | 2073 | -0.020 | +0.032 | +0.077 | 1.000 | ✓ |
| 4h | 507 | +0.053 | +0.026 | +0.097 | 0.429 | ✓ |

## 6. Línea base: ¿era más fácil ese periodo?

El catálogo vigente que solo pide velas, antes de 2023. Solo lectura: no escribe en el registro.

| Familia | Marco | Estrategias | n | Bruto |
|---|---|--:|--:|--:|
| indicadores | 1h | 8 | 6780 | +0.002 |
| indicadores | 4h | 8 | 1738 | +0.044 |
| base | 1h | 2 | 3913 | +0.030 |
| base | 4h | 2 | 962 | +0.059 |
| control | 1h | 1 | 2073 | -0.020 |
| control | 4h | 1 | 507 | +0.053 |
