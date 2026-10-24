# Cota analítica de costos HFT (T77)

BTCUSDT perpetuo, datos del recolector T23: rejilla de 1 s con el último precio negociado (828 930 operaciones `aggTrade`, 81 188 puntos, 22,8 h: 2026-10-22T22:28+00:00 → 2026-10-23T21:17+00:00 UTC). Generado por `python scripts/hft_cost_bound.py`. **Orientativo**: un solo tramo de mercado, ventanas solapadas (los percentiles valen; los errores estándar no). La cota definitiva con features y validación es T80.

Ida y vuelta con `CostParams` (taker 5 pb, maker 2 pb): **taker 10 pb · mixto 7 pb · maker-maker 4 pb**. Spread p50/p95/p99: 0,0123 / 0,0123 / 0,0123 pb (≈ 1 tick: cruzarlo no cambia la cuenta).

| Horizonte | Ventanas | E\|Δmid\| (pb) | p50 | p90 | p95 | p99 | P(>10 pb) | P(>7 pb) | P(>4 pb) | Techo taker | Techo mixto | Techo maker |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 s | 81 169 | 0,16 | 0,01 | 0,61 | 1,01 | 1,97 | 0,00 % | 0,01 % | 0,08 % | 0,000 | 0,000 | 0,001 |
| 2 s | 81 169 | 0,29 | 0,01 | 1,03 | 1,51 | 2,74 | 0,00 % | 0,02 % | 0,24 % | 0,000 | 0,000 | 0,003 |
| 5 s | 81 132 | 0,63 | 0,22 | 1,79 | 2,44 | 4,24 | 0,01 % | 0,12 % | 1,22 % | 0,001 | 0,002 | 0,015 |
| 10 s | 81 042 | 1,05 | 0,66 | 2,62 | 3,47 | 5,87 | 0,12 % | 0,50 % | 3,43 % | 0,003 | 0,011 | 0,056 |
| 30 s | 80 682 | 2,08 | 1,50 | 4,57 | 5,93 | 10,02 | 1,00 % | 2,95 % | 13,49 % | 0,037 | 0,091 | 0,296 |
| 60 s | 80 142 | 3,02 | 2,25 | 6,50 | 8,41 | 13,82 | 3,05 % | 8,27 % | 26,00 % | 0,112 | 0,267 | 0,733 |

**Techo** = E[max(|Δmid| − costo, 0)] por ventana, en pb: lo que ganaría un oráculo que sabe la dirección y solo opera cuando el movimiento paga la comisión, sin selección adversa, sin cola y con llenado seguro. Ninguna estrategia real lo supera; si es ≈ 0 en un horizonte, ese horizonte queda descartado para ese esquema de comisiones.

Contraste con el mid del top del libro (instantáneas ≈ 1/s, sin horizonte de 1 s porque dos instantáneas distan ≥ 1 s): p50 / p99 de |Δmid| en pb.

| Horizonte | Rejilla de operaciones | Top del libro |
|---|---|---|
| 1 s | 0,01 / 1,97 | — |
| 2 s | 0,01 / 2,74 | 0,00 / 1,93 |
| 5 s | 0,22 / 4,24 | 0,01 / 3,71 |
| 10 s | 0,66 / 5,87 | 0,60 / 5,29 |
| 30 s | 1,50 / 10,02 | 1,46 / 9,26 |
| 60 s | 2,25 / 13,82 | 2,18 / 12,46 |
