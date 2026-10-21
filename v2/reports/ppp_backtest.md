# Backtest PPP — BTCUSDT

Datos: `C:\Users\ASUSVI~1\AppData\Local\Temp/ppp_data` · ideas 2026-09-10 20:00 → 2026-10-20 19:00 UTC · 6002 ideas simuladas · camino de 15m hasta 2026-10-20 19:45 · SIMULADO, sin dinero real.

Desarrollo: antes de 2026-10-04 22:00 (3600 ideas) · fuera de muestra: desde esa fecha (2402 ideas), capital reiniciado a 10,000 USDT.

## Configuración de referencia (+10 / +5) — todo el periodo

| Config | Ops | Neto USDT | Esperanza/op | PF | Acierto | DD máx | SL ini / SL din | Abiertas | Devuelto vs máx. |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| referencia | 86 | -537.23 | -6.25 | 0.54 | 73 % | 5.56 % | 21 / 65 | 0 | 14.87 |

- Escalones alcanzados: +10: 65, +15: 9, +20: 3, +25: 2, +30: 1
- Violaciones de reglas: 0 · incidencias: 0 · pérdidas seguidas máx.: 3
- Máximo flotante medio 9.27 USDT · realizado medio -6.25 USDT · duración media 7.6 h

## Orden de los precios dentro de la vela de 15 m

Velas ambiguas resueltas con velas de 1 min: 67. Referencia con 1 min y con solo la regla conservadora (mismo periodo):

| Config | Ops | Neto USDT | Esperanza/op | PF | Acierto | DD máx | SL ini / SL din | Abiertas | Devuelto vs máx. |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| con velas de 1 min | 86 | -537.23 | -6.25 | 0.54 | 73 % | 5.56 % | 21 / 65 | 0 | 14.87 |
| solo regla conservadora | 85 | -604.69 | -7.11 | 0.50 | 66 % | 6.22 % | 21 / 64 | 0 | 18.24 |

## Cobertura del funding

Operaciones con funding supuesto (no real): 0 de 86.

## Entradas propias frente al resto (desarrollo y fuera de muestra)

Desarrollo:

| Config | Ops | Neto USDT | Esperanza/op | PF | Acierto | DD máx | SL ini / SL din | Abiertas | Devuelto vs máx. |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| solo entradas propias (ppp) | 8 | 19.99 | 2.50 | 1.38 | 88 % | 0.52 % | 1 / 7 | 0 | 7.88 |
| sin entradas propias | 50 | -155.52 | -3.11 | 0.72 | 80 % | 2.32 % | 10 / 40 | 0 | 13.20 |
| todas (perfil) | 54 | -178.59 | -3.31 | 0.71 | 80 % | 2.72 % | 11 / 43 | 0 | 13.35 |

Fuera de muestra:

| Config | Ops | Neto USDT | Esperanza/op | PF | Acierto | DD máx | SL ini / SL din | Abiertas | Devuelto vs máx. |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| solo entradas propias (ppp) | 1 | 11.17 | 11.17 | — | 100 % | 0.00 % | 0 / 1 | 0 | -0.07 |
| sin entradas propias | 33 | -348.41 | -10.56 | 0.38 | 64 % | 4.25 % | 10 / 23 | 0 | 17.23 |
| todas (perfil) | 32 | -357.95 | -11.19 | 0.36 | 62 % | 4.25 % | 10 / 22 | 0 | 17.76 |

Estrategia propia en la configuración completa: ppp_tendencia@4h: 2 ops, -43.05 USDT, ppp_tendencia@1h: 3 ops, +30.69 USDT

## Rejilla — desarrollo

| Config | Ops | Neto USDT | Esperanza/op | PF | Acierto | DD máx | SL ini / SL din | Abiertas | Devuelto vs máx. |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| +10 / +5 (referencia) | 54 | -178.59 | -3.31 | 0.71 | 80 % | 2.72 % | 11 / 43 | 0 | 13.35 |
| +8 / +3 | 57 | -132.46 | -2.32 | 0.76 | 82 % | 2.42 % | 10 / 47 | 0 | 11.18 |
| +8 / +5 | 57 | -134.85 | -2.37 | 0.76 | 82 % | 2.41 % | 10 / 47 | 0 | 11.47 |
| +10 / +3 | 54 | -170.19 | -3.15 | 0.72 | 80 % | 2.70 % | 11 / 43 | 0 | 13.21 |
| +10 / +7 | 54 | -180.16 | -3.34 | 0.71 | 80 % | 2.73 % | 11 / 43 | 0 | 13.38 |
| +12 / +5 | 49 | -190.04 | -3.88 | 0.72 | 76 % | 3.08 % | 12 / 37 | 0 | 15.94 |
| +12 / +7 | 49 | -185.12 | -3.78 | 0.72 | 76 % | 3.02 % | 12 / 37 | 0 | 15.90 |

## Rejilla — fuera de muestra

| Config | Ops | Neto USDT | Esperanza/op | PF | Acierto | DD máx | SL ini / SL din | Abiertas | Devuelto vs máx. |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| +10 / +5 (referencia) | 32 | -357.95 | -11.19 | 0.36 | 62 % | 4.25 % | 10 / 22 | 0 | 17.76 |
| +8 / +3 | 32 | -356.62 | -11.14 | 0.30 | 62 % | 4.29 % | 9 / 23 | 0 | 15.64 |
| +8 / +5 | 32 | -358.73 | -11.21 | 0.29 | 62 % | 4.33 % | 9 / 23 | 0 | 15.65 |
| +10 / +3 | 32 | -366.19 | -11.44 | 0.35 | 62 % | 4.30 % | 10 / 22 | 0 | 17.79 |
| +10 / +7 | 32 | -372.70 | -11.65 | 0.34 | 62 % | 4.32 % | 10 / 22 | 0 | 18.09 |
| +12 / +5 | 32 | -457.14 | -14.29 | 0.32 | 62 % | 4.70 % | 12 / 20 | 0 | 21.91 |
| +12 / +7 | 32 | -453.17 | -14.16 | 0.33 | 62 % | 4.66 % | 12 / 20 | 0 | 21.98 |

## Sensibilidad a comisiones y deslizamiento (configuración de referencia)

| Config | Ops | Neto USDT | Esperanza/op | PF | Acierto | DD máx | SL ini / SL din | Abiertas | Devuelto vs máx. |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| costos ×0.5 | 89 | -324.49 | -3.65 | 0.69 | 76 % | 3.84 % | 19 / 70 | 0 | 12.86 |
| costos ×1 | 86 | -537.23 | -6.25 | 0.54 | 73 % | 5.56 % | 21 / 65 | 0 | 14.87 |
| costos ×2 | 81 | -861.52 | -10.64 | 0.39 | 70 % | 8.62 % | 24 / 57 | 0 | 17.94 |
| costos ×3 | 74 | -908.42 | -12.28 | 0.37 | 69 % | 9.08 % | 23 / 51 | 0 | 18.63 |

## Cómo leerlo

- Una muestra pequeña NO demuestra rentabilidad: no se declara rentable el perfil.
- La rejilla es informativa; no cambia la configuración. Elegir por el mayor beneficio de un periodo sería sobreajuste: se exige estabilidad entre desarrollo y fuera de muestra.
- Camino de 15 m: dentro de una vela manda el SL vigente y el avance sube el SL desde la siguiente (conservador).