# Banco de latencia HFT (T77)

Generado por `python scripts/hft_latency.py report` con 3 corrida(s), 181 min en total, horas de inicio UTC: 21, 22, 23. Fuente: Binance USDⓈ-M **producción**, solo flujos públicos (`/public`: `depth@100ms`, `bookTicker`; `/market`: `aggTrade`, `markPrice@1s`), `GET /fapi/v1/time` y el WS API de órdenes **solo con `ping`/`time`** (sin claves; ninguna orden). Repetible en otro equipo o VPS con `python scripts/hft_latency.py run --minutes 60 --label <equipo>`.

Definiciones: antigüedad = reloj local corregido con `serverTime` − `E` (emisión) o − `T` (transacción); su valor absoluto tiene la incertidumbre de la columna «Incertidumbre» (RTT/2: no se sabe si la ida y la vuelta son simétricas), pero su dispersión (jitter) no. `E − T` usa solo relojes de Binance. Proceso Python = `json.loads` + aplicar el diff al libro local (`depth`) o leer el mensaje (resto).

## Corridas

| Corrida | Inicio (UTC) | Min | Equipo | REST RTT p50/p95/p99 (ms) | WS API `ping` p50/p95/p99 (ms) | Desfase ini→fin (ms) | Deriva (ppm) | Incertidumbre (±ms) | Reconexiones | Bucle p99 (ms) |
|---|---|---|---|---|---|---|---|---|---|---|
| 20261023T2100Z_equipo-local | 2026-10-23T21:00 | 60 | equipo-local | 256 / 380 / 410 | 236 / 250 / 276 | 9,9 → 4,1 | -0,7 | 121,5 | 0 | 21,5 |
| 20261023T2200Z_equipo-local | 2026-10-23T22:00 | 60 | equipo-local | 254 / 380 / 424 | 238 / 246 / 284 | 11,5 → 12,8 | -0,1 | 120,2 | 0 | 22,2 |
| 20261023T2300Z_equipo-local | 2026-10-23T23:00 | 60 | equipo-local | 254 / 374 / 406 | 238 / 250 / 262 | 12,0 → 7,0 | -1,0 | 121,1 | 0 | 21,8 |

## Flujos (todas las corridas fusionadas)

| Flujo | msg/s | Antigüedad `E` p50/p95/p99 (ms) | Antigüedad `T` p50/p95/p99 (ms) | `E − T` p50/p99 (ms) | Entre llegadas p50/p99 (ms) | Jitter p95−p50 (ms) | Proceso Python p50/p99 (µs) | Silencios ≥ 5 s |
|---|---|---|---|---|---|---|---|---|
| `depth` | 9,8 | 112 / 122 / 144 | 114 / 124 / 144 | 2 / 4 | 102 / 118 | 9 | 1 244 / 5 342 | 0 |
| `bookTicker` | 325,5 | 118 / 270 / 2 110 | 118 / 270 / 2 112 | 0 / 2 | 0 / 74 | 151 | 10 / 88 | 0 |
| `aggTrade` | 10,7 | 114 / 128 / 152 | 120 / 264 / 268 | 2 / 152 | 0 / 1 196 | 13 | 12 / 102 | 9 |
| `markPrice` | 1,0 | 156 / 170 / 180 | — / — / — | — / — | 1 000 / 1 024 | 14 | 30 / 114 | 0 |

## Antigüedad por corrida y hora

| Corrida | Hora UTC | `depth` edad E p50/p95/p99 | `bookTicker` edad E p50/p95/p99 | `aggTrade` edad E p50/p95/p99 | `markPrice` edad E p50/p95/p99 |
|---|---|---|---|---|---|
| 20261023T2100Z_equipo-local | 21 h | 112 / 122 / 128 | 114 / 156 / 198 | 114 / 126 / 178 | 156 / 170 / 178 |
| 20261023T2200Z_equipo-local | 22 h | 112 / 122 / 374 | 122 / 746 / 2 570 | 114 / 124 / 140 | 158 / 172 / 180 |
| 20261023T2300Z_equipo-local | 23 h | 112 / 120 / 132 | 118 / 168 / 238 | 116 / 132 / 152 | 156 / 170 / 180 |

## Presupuesto de reacción derivado (ms)

Evento del libro en Binance → orden de vuelta en Binance = antigüedad `T` del flujo + proceso Python (`depth`) + retraso del bucle asyncio + ida de la orden (RTT del WS API / 2). No incluye la cola del motor de emparejamiento (no medible sin enviar órdenes). Suma de percentiles: conservadora. Dos vistas de los datos: `bookTicker` pondera por evento (las ráfagas, cuando más importa reaccionar, pesan mucho); `depth` llega 10 veces por segundo pase lo que pase y pondera ≈ por tiempo. «Silencios» = 5 s sin mensajes del flujo (las reconexiones se cuentan aparte).

| Vista | Nivel | Datos | Proceso | Bucle | Orden (ida) | **Total** |
|---|---|---|---|---|---|---|
| `bookTicker` | p50 | 118,5 | 1,24 | 0,2 | 118,2 | **238,1** |
| `bookTicker` | p95 | 269,5 | 3,54 | 16,1 | 124,2 | **413,3** |
| `bookTicker` | p99 | 2 111,5 | 5,34 | 21,9 | 138,2 | **2 276,9** |
| `depth` | p50 | 113,5 | 1,24 | 0,2 | 118,2 | **233,1** |
| `depth` | p95 | 123,5 | 3,54 | 16,1 | 124,2 | **267,3** |
| `depth` | p99 | 144,5 | 5,34 | 21,9 | 138,2 | **309,9** |

Regla Python vs Rust: proceso + bucle p99 = 27,2 ms = **8,8 %** del menor presupuesto p99 (309,9 ms; umbral 20 %): **no** lo supera → Python basta; Rust no aporta en esta ruta.
