# Backtest PPP — BTCUSDT

Datos: `C:\Users\ASUSVI~1\AppData\Local\Temp/ppp_data` · ideas 2026-09-10 20:00 → 2026-10-20 19:00 UTC · 5992 ideas simuladas · camino de 15m hasta 2026-10-20 19:45 · SIMULADO, sin dinero real.

Desarrollo: antes de 2026-10-04 22:00 (3591 ideas) · fuera de muestra: desde esa fecha (2401 ideas), capital reiniciado a 10,000 USDT.

## Configuración de referencia (+10 / +5) — todo el periodo

| Config | Ops | Neto USDT | Esperanza/op | PF | Acierto | DD máx | SL ini / SL din | Abiertas | Devuelto vs máx. |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| referencia | 84 | -500.22 | -5.95 | 0.55 | 68 % | 5.17 % | 19 / 65 | 0 | 17.15 |

- Escalones alcanzados: +10: 65, +15: 17, +20: 11, +25: 5, +30: 4, +35: 2, +40: 1, +45: 1, +50: 1, +55: 1, +60: 1, +65: 1, +70: 1, +75: 1, +80: 1, +85: 1
- Violaciones de reglas: 0 · incidencias: 0 · pérdidas seguidas máx.: 3
- Máximo flotante medio 11.88 USDT · realizado medio -5.95 USDT · duración media 6.7 h

## Rejilla — desarrollo

| Config | Ops | Neto USDT | Esperanza/op | PF | Acierto | DD máx | SL ini / SL din | Abiertas | Devuelto vs máx. |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| +10 / +5 (referencia) | 51 | -93.97 | -1.84 | 0.82 | 73 % | 2.30 % | 9 / 42 | 0 | 15.32 |
| +8 / +3 | 52 | -157.92 | -3.04 | 0.70 | 71 % | 2.47 % | 9 / 43 | 0 | 14.70 |
| +8 / +5 | 52 | -166.89 | -3.21 | 0.68 | 71 % | 2.47 % | 9 / 43 | 0 | 14.96 |
| +10 / +3 | 51 | -122.61 | -2.40 | 0.77 | 73 % | 2.30 % | 9 / 42 | 0 | 14.96 |
| +10 / +7 | 51 | -131.42 | -2.58 | 0.75 | 73 % | 2.33 % | 9 / 42 | 0 | 15.15 |
| +12 / +5 | 48 | -239.21 | -4.98 | 0.65 | 71 % | 3.06 % | 12 / 36 | 0 | 19.23 |
| +12 / +7 | 48 | -224.74 | -4.68 | 0.67 | 71 % | 2.79 % | 12 / 36 | 0 | 19.66 |

## Rejilla — fuera de muestra

| Config | Ops | Neto USDT | Esperanza/op | PF | Acierto | DD máx | SL ini / SL din | Abiertas | Devuelto vs máx. |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| +10 / +5 (referencia) | 33 | -351.30 | -10.65 | 0.33 | 64 % | 4.29 % | 9 / 24 | 0 | 18.43 |
| +8 / +3 | 33 | -388.82 | -11.78 | 0.27 | 58 % | 4.49 % | 9 / 24 | 0 | 17.96 |
| +8 / +5 | 33 | -391.36 | -11.86 | 0.27 | 58 % | 4.51 % | 9 / 24 | 0 | 18.04 |
| +10 / +3 | 33 | -350.83 | -10.63 | 0.33 | 64 % | 4.28 % | 9 / 24 | 0 | 18.42 |
| +10 / +7 | 33 | -357.84 | -10.84 | 0.32 | 64 % | 4.32 % | 9 / 24 | 0 | 18.63 |
| +12 / +5 | 33 | -446.75 | -13.54 | 0.30 | 61 % | 4.88 % | 11 / 22 | 0 | 23.45 |
| +12 / +7 | 33 | -447.95 | -13.57 | 0.30 | 61 % | 4.89 % | 11 / 22 | 0 | 23.49 |

## Sensibilidad a comisiones y deslizamiento (configuración de referencia)

| Config | Ops | Neto USDT | Esperanza/op | PF | Acierto | DD máx | SL ini / SL din | Abiertas | Devuelto vs máx. |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| costos ×0.5 | 87 | -366.47 | -4.21 | 0.63 | 71 % | 4.10 % | 18 / 69 | 0 | 15.57 |
| costos ×1 | 84 | -500.22 | -5.95 | 0.55 | 68 % | 5.17 % | 19 / 65 | 0 | 17.15 |
| costos ×2 | 77 | -741.89 | -9.63 | 0.41 | 62 % | 7.42 % | 21 / 56 | 0 | 19.86 |
| costos ×3 | 73 | -852.65 | -11.68 | 0.37 | 63 % | 8.53 % | 21 / 52 | 0 | 20.99 |

## Cómo leerlo

- Una muestra pequeña NO demuestra rentabilidad: no se declara rentable el perfil.
- La rejilla es informativa; no cambia la configuración. Elegir por el mayor beneficio de un periodo sería sobreajuste: se exige estabilidad entre desarrollo y fuera de muestra.
- Camino de 15 m: dentro de una vela manda el SL vigente y el avance sube el SL desde la siguiente (conservador).