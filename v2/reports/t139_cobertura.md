# T139 — Cobertura de la historia y muestra, sin ningún R

Modo: **SIMULADO** · BTCUSDT · datos hasta 2026-11-06T03:30+00:00 · pre-registro `prereg_t139_v1` (SHA-256 `f24f72bfc3d8cc92…`, commit `3d396f7`, anterior a la descarga y a todo cálculo) · criterios `validation_v1` sin cambios · calculado con `b56993e` · familia de Holm de 841, 33640 réplicas.

## 1. Cobertura del tramo limpio

Tramo 2020-01-01T00:00:00Z → 2023-01-01T00:00:00Z. Mínimo: 99%.

| Serie | Filas | Esperadas | Cobertura | ¿Cumple? |
|---|--:|--:|--:|---|
| 1m | 1578240 | 1578240 | 100.00% | ✓ |
| 15m | 105216 | 105216 | 100.00% | ✓ |
| 1h | 26304 | 26304 | 100.00% | ✓ |
| 4h | 6576 | 6576 | 100.00% | ✓ |
| funding | 3288 | 3288 | 100.00% | ✓ |
| `taker_buy_v` 1h | 26304 | 26304 | 100.00% | ✓ |
| `taker_buy_v` 4h | 6576 | 6576 | 100.00% | ✓ |

Primera vela de 1 min: 2019-09-08T17:57:00Z.

**Veredicto de P0:** cumple.

## 2. Muestra por clave, sin ningún R

| Clave | Ideas | Cerradas antes de 2023 | Largos | Cortos | Banco | En vivo |
|---|--:|--:|--:|--:|--:|--:|
| `funding_contra@1h` | 1485 | 454 | 252 | 202 | 624 | 0 |
| `funding_contra@4h` | 1485 | 232 | 126 | 106 | 330 | 0 |
| `flujo_sigue@1h` | 3238 | 635 | 330 | 305 | 857 | 0 |
| `flujo_sigue@4h` | 800 | 152 | 74 | 78 | 222 | 0 |
| `flujo_revierte@1h` | 525 | 205 | 96 | 109 | 247 | 0 |
| `flujo_revierte@4h` | 158 | 60 | 29 | 31 | 72 | 0 |
| `cascada_revierte@1h` | 1674 | 451 | 214 | 237 | 651 | 0 |
| `cascada_revierte@4h` | 1336 | 266 | 121 | 145 | 390 | 0 |
| `momento_1d@1d` | 2587 | 121 | 73 | 48 | 151 | 0 |
