# Backtest PPP — BTCUSDT

Datos: `C:\Users\ASUSVI~1\AppData\Local\Temp/ppp_data` · ideas 2026-09-10 20:00 → 2026-10-20 19:00 UTC · 5992 ideas simuladas · camino de 15m hasta 2026-10-20 19:45 · SIMULADO, sin dinero real.

Desarrollo: antes de 2026-10-04 22:00 (3591 ideas) · fuera de muestra: desde esa fecha (2401 ideas), capital reiniciado a 10,000 USDT.

## Configuración de referencia (+10 / +5) — todo el periodo

| Config | Ops | Neto USDT | Esperanza/op | PF | Acierto | DD máx | SL ini / SL din | Abiertas | Devuelto vs máx. |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| referencia | 82 | -564.26 | -6.88 | 0.51 | 67 % | 5.81 % | 20 / 62 | 0 | 17.90 |

- Escalones alcanzados: +10: 62, +15: 17, +20: 11, +25: 5, +30: 4, +35: 2, +40: 1, +45: 1, +50: 1, +55: 1, +60: 1, +65: 1, +70: 1, +75: 1, +80: 1, +85: 1
- Violaciones de reglas: 0 · incidencias: 0 · pérdidas seguidas máx.: 3
- Máximo flotante medio 11.69 USDT · realizado medio -6.88 USDT · duración media 7.3 h

## Rejilla — desarrollo

| Config | Ops | Neto USDT | Esperanza/op | PF | Acierto | DD máx | SL ini / SL din | Abiertas | Devuelto vs máx. |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| +10 / +5 (referencia) | 49 | -163.67 | -3.34 | 0.72 | 71 % | 2.30 % | 10 / 39 | 0 | 16.71 |
| +8 / +3 | 52 | -149.40 | -2.87 | 0.72 | 71 % | 2.35 % | 9 / 43 | 0 | 14.37 |
| +8 / +5 | 52 | -155.02 | -2.98 | 0.71 | 71 % | 2.35 % | 9 / 43 | 0 | 14.56 |
| +10 / +3 | 49 | -194.20 | -3.96 | 0.67 | 71 % | 2.53 % | 10 / 39 | 0 | 16.36 |
| +10 / +7 | 49 | -203.41 | -4.15 | 0.65 | 71 % | 2.54 % | 10 / 39 | 0 | 16.56 |
| +12 / +5 | 45 | -211.54 | -4.70 | 0.66 | 69 % | 2.73 % | 11 / 34 | 0 | 18.85 |
| +12 / +7 | 45 | -183.38 | -4.08 | 0.71 | 69 % | 2.43 % | 11 / 34 | 0 | 19.27 |

## Rejilla — fuera de muestra

| Config | Ops | Neto USDT | Esperanza/op | PF | Acierto | DD máx | SL ini / SL din | Abiertas | Devuelto vs máx. |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| +10 / +5 (referencia) | 33 | -410.82 | -12.45 | 0.30 | 61 % | 4.70 % | 10 / 23 | 0 | 20.14 |
| +8 / +3 | 33 | -385.37 | -11.68 | 0.28 | 58 % | 4.48 % | 9 / 24 | 0 | 17.74 |
| +8 / +5 | 33 | -387.37 | -11.74 | 0.28 | 58 % | 4.50 % | 9 / 24 | 0 | 17.80 |
| +10 / +3 | 33 | -409.92 | -12.42 | 0.30 | 61 % | 4.70 % | 10 / 23 | 0 | 20.11 |
| +10 / +7 | 33 | -415.96 | -12.60 | 0.29 | 61 % | 4.73 % | 10 / 23 | 0 | 20.29 |
| +12 / +5 | 32 | -441.85 | -13.81 | 0.31 | 59 % | 4.87 % | 11 / 21 | 0 | 23.70 |
| +12 / +7 | 32 | -443.06 | -13.85 | 0.31 | 59 % | 4.88 % | 11 / 21 | 0 | 23.74 |

## Sensibilidad a comisiones y deslizamiento (configuración de referencia)

| Config | Ops | Neto USDT | Esperanza/op | PF | Acierto | DD máx | SL ini / SL din | Abiertas | Devuelto vs máx. |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| costos ×0.5 | 86 | -353.56 | -4.11 | 0.64 | 72 % | 3.97 % | 18 / 68 | 0 | 15.28 |
| costos ×1 | 82 | -564.26 | -6.88 | 0.51 | 67 % | 5.81 % | 20 / 62 | 0 | 17.90 |
| costos ×2 | 75 | -753.61 | -10.05 | 0.40 | 63 % | 7.54 % | 21 / 54 | 0 | 19.86 |
| costos ×3 | 70 | -832.73 | -11.90 | 0.38 | 63 % | 8.33 % | 21 / 49 | 0 | 21.23 |

## Cómo leerlo

- Una muestra pequeña NO demuestra rentabilidad: no se declara rentable el perfil.
- La rejilla es informativa; no cambia la configuración. Elegir por el mayor beneficio de un periodo sería sobreajuste: se exige estabilidad entre desarrollo y fuera de muestra.
- Camino de 15 m: dentro de una vela manda el SL vigente y el avance sube el SL desde la siguiente (conservador).