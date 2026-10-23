# T109 — Solo cierra el stop: corrida de aceptación

Datos: copia del almacén local (velas y funding de `v2/data`, 2026-10-22) con contextos reconstruidos para esta corrida: 32 días de 1 h y 4 h y de 15 m muestreado cada hora (la RAM del equipo no daba para 15 m completo con el servicio en vivo corriendo; ver BACKLOG T109) · SIMULADO, sin dinero real. Vista reconstruida con el mismo cálculo que la API (`PaperDesk.view`).

## BTCUSDT

Ideas 2026-09-20 23:15 → 2026-10-22 22:00 UTC (31.9 días, 4999 ideas simuladas) · velas de 1 min: sí (solo donde existen).

| Perfil | Ops | SL ini | SL din | Liquid. | Salvag. | Otros | Rechaz. | Violac. | BE+ cerró | Contrarias | Abiertas | Neto USDT | Acierto | Dur. media h | Dur. máx h |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| conservador | 21 | 4 | 17 | 0 | 0 | 0 | 0 | 0 | 0 | 36 | 0 | -21.58 | 67% | 1.3 | 4.2 |
| moderado | 226 | 42 | 184 | 0 | 0 | 0 | 0 | 0 | 0 | 1237 | 1 | -753.01 | 71% | 4.8 | 53.0 |
| agresivo | 220 | 45 | 175 | 0 | 0 | 0 | 0 | 0 | 0 | 1174 | 2 | -3,547.63 | 62% | 3.2 | 53.0 |
| ppp_btcusdt | 73 | 17 | 56 | 0 | 0 | 0 | 0 | 0 | 0 | 717 | 0 | -517.83 | 63% | 6.6 | 53.5 |

Referencia (no decide nada; la comparación es T111): los mismos perfiles con la salida anterior (SL/TP/BE+/tiempo) sobre el mismo camino.

| Perfil | Ops | Motivos | Neto USDT | Acierto |
|---|--:|---|--:|--:|
| conservador (TP) | 36 | SL 21, TIEMPO 6, TP 9 | -316.17 | 36% |
| moderado (TP) | 106 | BE 13, SL 48, TIEMPO 15, TP 30 | -876.38 | 53% |
| agresivo (TP) | 74 | BE 12, SL 37, TIEMPO 4, TP 21 | -1,795.69 | 45% |

Violaciones: ninguna.

## ETHUSDT

Ideas 2026-09-21 00:00 → 2026-10-22 23:00 UTC (32.0 días, 4914 ideas simuladas) · velas de 1 min: sí (solo donde existen).

| Perfil | Ops | SL ini | SL din | Liquid. | Salvag. | Otros | Rechaz. | Violac. | BE+ cerró | Contrarias | Abiertas | Neto USDT | Acierto | Dur. media h | Dur. máx h |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| conservador | 10 | 0 | 10 | 0 | 0 | 0 | 0 | 0 | 0 | 17 | 0 | 4.05 | 40% | 1.3 | 2.8 |
| moderado | 321 | 60 | 261 | 0 | 0 | 0 | 0 | 0 | 0 | 1131 | 4 | -1,178.23 | 63% | 4.0 | 62.0 |
| agresivo | 252 | 48 | 204 | 0 | 0 | 0 | 0 | 0 | 0 | 1155 | 2 | -3,875.10 | 60% | 2.9 | 31.8 |
| ppp_btcusdt | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00 | — | — | — |

Referencia (no decide nada; la comparación es T111): los mismos perfiles con la salida anterior (SL/TP/BE+/tiempo) sobre el mismo camino.

| Perfil | Ops | Motivos | Neto USDT | Acierto |
|---|--:|---|--:|--:|
| conservador (TP) | 47 | BE 8, SL 20, TIEMPO 7, TP 12 | -43.11 | 45% |
| moderado (TP) | 144 | BE 25, SL 58, TIEMPO 24, TP 37 | -413.50 | 55% |
| agresivo (TP) | 83 | BE 14, SL 32, TIEMPO 13, TP 24 | 481.50 | 55% |

Violaciones: ninguna.

## Control y modo TP frente al código de `main` (mismos datos)

- `ppp_btcusdt`: las **73 operaciones** de BTCUSDT son idénticas con el código de `main` y con el de
  T109 (id, motivo, llenado, salida, cantidad, PnL y escalón); en ETHUSDT no opera (solo BTC).
- Modo `"tp"`: los tres perfiles con `exit_mode="tp"` dan exactamente las cifras que daban en
  `main` (Conservador −316,17 / Moderado −876,38 / Agresivo −1.795,69 USDT en BTC), así que el A/B
  de T111 parte del comportamiento anterior sin cambios.
- Ninguna operación de los tres perfiles se cerró por TP, por tiempo ni por BE fuera del stop;
  cero violaciones y cero cierres rechazados; el BE+ no fue el stop que cerró en ninguna (con
  umbrales de 0,075–0,100 R el escalón siempre protegía más).

## Lectura (no es la decisión de T111)

- Con la escalera los perfiles cierran mucho antes (duración media 3–5 h frente a 10–19 h) y por
  eso abren más operaciones (Moderado BTC 226 frente a 106): sus cupos se liberan antes.
- En este periodo el neto es **peor** con escalera en el Agresivo (BTC −3.548 frente a −1.796;
  ETH −3.875 frente a +482) y en el Moderado de ETH; mejor en el Conservador y el Moderado de BTC.
  Es una sola muestra de 32 días, con 15 m muestreado y con el sesgo de deslizamiento de entrada
  anotado en BACKLOG T109 (1): **no se concluye nada**; lo mide T111.
- Las «contrarias» cuentan señales que llegaron contra una posición abierta: solo informan.
