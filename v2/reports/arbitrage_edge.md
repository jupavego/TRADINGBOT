# Arbitraje en Binance: ¿deja dinero neto? (T43)

**Modo: ANÁLISIS** — simulación histórica; no se envió ninguna orden. Generado 2026-10-17 (UTC). Período de decisiones: 2023-01-08 → 2026-10-16 (4132 decisiones cada 8 h, 1 h antes de cada liquidación de funding). Las cifras son netas de comisiones, deslizamiento por profundidad, funding, rebalanceo, liquidaciones y costo esperado de pata incompleta.

Cómo se obtuvo: en cada decisión se reconstruye la fotografía que habría visto el escáner (T38) y se valora y selecciona con **el mismo código del motor** (`scan_*` + `select`); cada oportunidad se simula después vela a vela hasta su salida (`eim/arbitrage/sim/`). Política: una posición a la vez por estrategia y activo.

## Veredicto (caso base: VIP 0, sin BNB, 10 000 USD por operación)

| Estrategia | Veredicto | Anual neto (período) | Últimos 12 meses | Neto medio/op | IC95 % | Operaciones | Peor op. | Motivos |
|---|---|---|---|---|---|---|---|---|
| Carry de funding | **Marginal** | +4,08 % | +1,17 % | +102,5 pb | [+57,7; +157,6] pb | 30 | -0,0 pb | últimos 12 meses 1,17% < umbral (régimen actual) |
| Base (cash-and-carry trimestral) | **Marginal** | +3,50 % | +2,44 % | +131,0 pb | [+59,0; +208,6] pb | 20 | -95,2 pb | rentabilidad anual 3,50% < umbral de referencia 4% (supuesto); últimos 12 meses 2,44% < umbral (régimen actual) |
| Perpetuos relacionados USDT-M/USDC-M | **No viable** | +0,00 % | — | — | — | 0 | — | el selector T38 no tomó ninguna operación en todo el período |
| Triangular spot | **No viable** | — | — | — | — | — | — | ticker (optimista, cierres de 1 min no simultáneos): 81 minutos con neto > 0 en 30 días con VIP 0, cota superior no ejecutable; libros reales (26 fotografías): 0 de 256 ciclos con neto > 0; mejor -27,7 pb |

Reglas: *No viable* = el selector no toma nada o el neto medio ≤ 0; *Viable* = neto medio > 0 con IC95 % > 0, anual del período y de los últimos 12 meses ≥ 4% (umbral de referencia **supuesto**, no un dato de mercado), sin liquidaciones y ≥ 10 operaciones; *Marginal* = el resto. El carry se juzga en su mejor tenencia; la base, con sus variantes no desactivadas. Anual = neto / capital comprometido (spot + margen) por año, con el capital ocioso incluido.

## Datos y cobertura

| Serie | Fuente | Desde | Hasta |
|---|---|---|---|
| candles:BTCUSDC | binance-futures | 2024-01-04 | 2026-10-16 |
| candles:BTCUSDT | binance-futures-ws | 2023-01-01 | 2026-10-16 |
| candles:ETHUSDC | binance-futures | 2024-01-04 | 2026-10-16 |
| candles:ETHUSDT | binance-futures | 2023-01-01 | 2026-10-16 |
| funding:BTCUSDC | binance-futures | 2024-01-02 | 2026-10-16 |
| funding:BTCUSDT | binance-futures | 2023-01-01 | 2026-10-17 |
| funding:ETHUSDC | binance-futures | 2024-01-02 | 2026-10-16 |
| funding:ETHUSDT | binance-futures | 2023-01-01 | 2026-10-16 |
| spot:BNBBTC:1m | binance-spot | 2026-09-16 | 2026-10-16 |
| spot:BNBETH:1m | binance-spot | 2026-09-16 | 2026-10-16 |
| spot:BNBUSDT:1m | binance-spot | 2026-09-16 | 2026-10-16 |
| spot:BTCUSDT | binance-spot | 2023-01-01 | 2026-10-16 |
| spot:BTCUSDT:1m | binance-spot | 2026-09-16 | 2026-10-16 |
| spot:ETHBTC:1m | binance-spot | 2026-09-16 | 2026-10-16 |
| spot:ETHUSDT | binance-spot | 2023-01-01 | 2026-10-16 |
| spot:ETHUSDT:1m | binance-spot | 2026-09-16 | 2026-10-16 |
| spot:SOLBNB:1m | binance-spot | 2026-09-16 | 2026-10-16 |
| spot:SOLBTC:1m | binance-spot | 2026-09-16 | 2026-10-16 |
| spot:SOLETH:1m | binance-spot | 2026-09-16 | 2026-10-16 |
| spot:SOLUSDT:1m | binance-spot | 2026-09-16 | 2026-10-16 |
| spot:USDCUSDT | binance-spot | 2023-03-11 | 2026-10-16 |
| spot:XRPBTC:1m | binance-spot | 2026-09-16 | 2026-10-16 |
| spot:XRPETH:1m | binance-spot | 2026-09-16 | 2026-10-16 |
| spot:XRPUSDT:1m | binance-spot | 2026-09-16 | 2026-10-16 |

Trimestrales (velas 1 h desde el listado; liquidación = precio real):

| Contrato | Vencimiento | Liquidación | Fuente |
|---|---|---|---|
| BTCUSDT_230331 | 2023-03-31 | 27 807,8 | binance-futures: vela plana tras el vencimiento |
| BTCUSDT_230630 | 2023-06-30 | 30 661,0 | binance-futures: vela plana tras el vencimiento |
| BTCUSDT_230929 | 2023-09-29 | 27 108,4 | binance-futures: vela plana tras el vencimiento |
| BTCUSDT_231229 | 2023-12-29 | 42 374,0 | binance-futures: vela plana tras el vencimiento |
| BTCUSDT_240329 | 2024-03-29 | 69 819,7 | binance-futures: vela plana tras el vencimiento |
| BTCUSDT_240628 | 2024-06-28 | 61 440,0 | binance-futures: vela plana tras el vencimiento |
| BTCUSDT_240927 | 2024-09-27 | 65 426,0 | binance-futures: vela plana tras el vencimiento |
| BTCUSDT_241227 | 2024-12-27 | 95 104,9 | binance-futures: vela plana tras el vencimiento |
| BTCUSDT_250328 | 2025-03-28 | 85 200,0 | binance-futures: último precio tras el vencimiento (aprox., sin vela plana) |
| BTCUSDT_250627 | 2025-06-27 | 107 051,2 | binance-futures: vela plana tras el vencimiento |
| BTCUSDT_250926 | 2025-09-26 | 109 001,0 | binance-futures: vela plana tras el vencimiento |
| BTCUSDT_251226 | 2025-12-26 | 88 721,0 | binance-futures: vela plana tras el vencimiento |
| BTCUSDT_260327 | 2026-03-27 | 69 260,0 | binance-futures: vela plana tras el vencimiento |
| BTCUSDT_260626 | 2026-06-26 | 59 681,2 | binance-futures: vela plana tras el vencimiento |
| BTCUSDT_260925 | 2026-09-25 | 83 981,8 | binance-futures: vela plana tras el vencimiento |
| BTCUSDT_261225 | 2026-12-25 | — | sin precio |
| BTCUSDT_270326 | 2027-03-26 | — | sin precio |
| ETHUSDT_230331 | 2023-03-31 | 1 790,3 | binance-futures: vela plana tras el vencimiento |
| ETHUSDT_230630 | 2023-06-30 | 1 880,8 | binance-futures: vela plana tras el vencimiento |
| ETHUSDT_230929 | 2023-09-29 | 1 669,0 | binance-futures: vela plana tras el vencimiento |
| ETHUSDT_231229 | 2023-12-29 | 2 350,6 | binance-futures: vela plana tras el vencimiento |
| ETHUSDT_240329 | 2024-03-29 | 3 548,4 | binance-futures: vela plana tras el vencimiento |
| ETHUSDT_240628 | 2024-06-28 | 3 445,0 | binance-futures: vela plana tras el vencimiento |
| ETHUSDT_240927 | 2024-09-27 | 2 658,3 | binance-futures: vela plana tras el vencimiento |
| ETHUSDT_241227 | 2024-12-27 | 3 340,1 | binance-futures: vela plana tras el vencimiento |
| ETHUSDT_250328 | 2025-03-28 | 1 911,4 | binance-futures: vela plana tras el vencimiento |
| ETHUSDT_250627 | 2025-06-27 | 2 442,0 | binance-futures: vela plana tras el vencimiento |
| ETHUSDT_250926 | 2025-09-26 | 3 917,0 | binance-futures: vela plana tras el vencimiento |
| ETHUSDT_251226 | 2025-12-26 | 2 966,0 | binance-futures: vela plana tras el vencimiento |
| ETHUSDT_260327 | 2026-03-27 | 2 068,0 | binance-futures: vela plana tras el vencimiento |
| ETHUSDT_260626 | 2026-06-26 | 1 572,8 | binance-futures: vela plana tras el vencimiento |
| ETHUSDT_260925 | 2026-09-25 | 2 673,5 | binance-futures: vela plana tras el vencimiento |
| ETHUSDT_261225 | 2026-12-25 | — | sin precio |
| ETHUSDT_270326 | 2027-03-26 | — | sin precio |

Profundidad: **26 capturas reales** de libros (100 niveles, REST) entre 2026-10-16 y 2026-10-17; claves: `spot:BNBBTC` ×26, `spot:BNBETH` ×6, `spot:BNBUSDT` ×26, `spot:BTCUSDT` ×26, `spot:ETHBTC` ×6, `spot:ETHUSDT` ×6, `spot:SOLBNB` ×26, `spot:SOLBTC` ×26, `spot:SOLETH` ×6, `spot:SOLUSDT` ×26, `spot:USDCUSDT` ×26, `spot:XRPBTC` ×26, `spot:XRPETH` ×6, `spot:XRPUSDT` ×26, `usdcm:BTCUSDC` ×26, `usdcm:ETHUSDC` ×6, `usdm:BTCUSDT` ×26, `usdm:BTCUSDT_Q1` ×26, `usdm:BTCUSDT_Q2` ×26, `usdm:ETHUSDT` ×6, `usdm:ETHUSDT_Q1` ×6, `usdm:ETHUSDT_Q2` ×6. No hay libros históricos: el libro de hoy se aplica al pasado adelgazado por volumen (volumen medio 24 h / el de la captura, recortado a [mín., 1]: nunca más grueso).

Faltantes declarados: `settle:BTCUSDT_250328`: liquidación aproximada con el último precio

Faltas por estrategia en las fotografías: related_perps: perpetuo BTC USDC-M no disponible ×897; related_perps: perpetuo ETH USDC-M no disponible ×897; related_perps: libro spot USDCUSDT ×186

Oportunidades no simulables: basis: BTCUSDT_261225: sin precio de liquidación (aún no vence o falta) ×674; basis: ETHUSDT_261225: sin precio de liquidación (aún no vence o falta) ×674; basis: a menos de los días mínimos del vencimiento ×458; basis: BTCUSDT_270326: sin precio de liquidación (aún no vence o falta) ×128; basis: ETHUSDT_270326: sin precio de liquidación (aún no vence o falta) ×128; funding_carry: la tenencia sale del histórico ×6; related_perps: la tenencia sale del histórico ×6

## Supuestos (declarados; no son datos)

- Comisiones: tabla pública Binance (VIP 0 verificado 2026-10-15; otros niveles de referencia; USDC-M sin verificar → igual que USDⓈ-M) · configurable. Rol tomador; liquidación del trimestral = tomador.
- Funding previsto en cada decisión = **última tasa realizada** (el `premiumIndex` histórico no existe); resto de la tenencia = media de las últimas 21 realizadas (igual que el motor en vivo). Lo realizado usa las tasas reales en cada liquidación, a la apertura del perpetuo como marca.
- Ejecución: decisión con el cierre de la vela previa; entrada y salida a la apertura de la vela siguiente ± deslizamiento del perfil. Índice ≈ spot.
- Margen: futuros a ×2; spot + futuro corto con margen aislado y rebalanceo al caer al 50% del objetivo (vende spot y recompra futuro); futuro/futuro en margen cruzado (Multi-Assets para USDC-M). Liquidación con el máximo de la vela: se pierde el margen restante (regla de T25).
- Pata incompleta: probabilidad 1% por ejecución de dos patas; un incidente cuesta deshacer la pata ejecutada (ida y vuelta) y queda expuesta 250 ms (escalado √t de rendimientos reales de 15 min).
- Sin préstamo spot (sin histórico de tasas): no se evalúan el carry inverso ni la base en descuento.

## Resultados por estrategia

### Carry de funding

| Tenencia | Operaciones | Anual (período) | Anual (invertido) | Neto medio/op | IC95 % media | p (media ≤ 0) | Peor op. | Caída máx. |
|---|---|---|---|---|---|---|---|---|
| 24 h | 0 | — | — | — | — | — | — | — |
| 72 h | 15 | +0,06 % | +3,59 % | +3,0 pb | [-2,1; +7,3] pb | 0,123 | -9,1 pb | 0,1 % |
| 168 h | 30 | +0,56 % | +7,38 % | +14,1 pb | [+6,6; +24,4] pb | 0,000 | -11,3 pb | 0,1 % |
| 720 h | 76 | +2,72 % | +3,29 % | +27,0 pb | [+13,5; +44,2] pb | 0,000 | -17,3 pb | 0,1 % |
| 2160 h | 30 | +4,08 % | +4,16 % | +102,5 pb | [+57,7; +157,6] pb | 0,000 | -0,0 pb | 0,0 % |

El motor en vivo usa 24 h. Desglose y distribución siguientes: mejor tenencia (2160 h).

Desglose (USD, suma): precio/base -38,01 USD · funding 5 613,92 USD · −comisiones 949,94 USD · −deslizamiento 1,80 USD · −pata incompleta (esperado) 12,69 USD · −liquidación 0,00 USD. Rebalanceos: 27; liquidaciones: 0; ocupación del capital: 98%.

Distribución por operación (sobre capital): p1 +0,1 pb, p5 +0,7 pb, p10 +10,5 pb, p25 +43,7 pb, p50 +72,1 pb, p75 +126,8 pb, p90 +222,1 pb, p95 +294,7 pb, p99 +356,4 pb; con incidentes de pata sorteados: p1 -0,0 pb, p5 +0,8 pb, peor -13,4 pb.

Por año de entrada: 2023: 8 op., 1 442 USD (+4,91 % anual); 2024: 9 op., 2 299 USD (+7,65 % anual); 2025: 9 op., 660 USD (+2,20 % anual); 2026: 4 op., 211 USD (+0,92 % anual)

Estimado por el motor vs realizado (seleccionadas, n=6617): +125,0 pb → +108,8 pb (desvío -16,2 pb).

### Base (cash-and-carry trimestral)

| Caso | Operaciones | Anual (período) | Anual (invertido) | Neto medio/op | IC95 % media | p (media ≤ 0) | Peor op. | Caída máx. |
|---|---|---|---|---|---|---|---|---|
| activas | 20 | +3,50 % | +3,56 % | +131,0 pb | [+59,0; +208,6] pb | 0,000 | -95,2 pb | 0,8 % |
| ambas variantes (sin desactivar) | 20 | +3,48 % | +3,59 % | +128,2 pb | [+54,7; +208,7] pb | 0,000 | -95,2 pb | 0,8 % |
| spot/trimestral | 20 | +3,50 % | +3,56 % | +131,0 pb | [+59,0; +208,6] pb | 0,000 | -95,2 pb | 0,8 % |
| perpetuo/trimestral | 18 | -0,26 % | -0,30 % | -12,8 pb | [-155,9; +104,9] pb | 0,556 | -505,3 pb | 7,9 % |

- spot/trimestral: estimado +120,7 pb → realizado +90,5 pb (n=11837 decisiones seleccionadas)
- perpetuo/trimestral: estimado +86,0 pb → realizado -18,3 pb (n=5805 decisiones seleccionadas)

Desglose (USD, suma): precio/base 4 708,38 USD · funding 0,00 USD · −comisiones 656,06 USD · −deslizamiento 56,63 USD · −pata incompleta (esperado) 5,03 USD · −liquidación 0,00 USD. Rebalanceos: 24; liquidaciones: 0; ocupación del capital: 98%.

Distribución por operación (sobre capital): p1 -88,5 pb, p5 -61,4 pb, p10 -34,3 pb, p25 +42,7 pb, p50 +108,0 pb, p75 +185,2 pb, p90 +373,8 pb, p95 +390,5 pb, p99 +393,4 pb; con incidentes de pata sorteados: p1 -95,3 pb, p5 -73,8 pb, peor -108,5 pb.

Por año de entrada: 2023: 8 op., 351 USD (+1,18 % anual); 2024: 6 op., 2 665 USD (+8,78 % anual); 2025: 4 op., 870 USD (+2,87 % anual); 2026: 2 op., 105 USD (+0,47 % anual)

Estimado por el motor vs realizado (seleccionadas, n=17642): +109,3 pb → +54,7 pb (desvío -54,6 pb).

### Perpetuos relacionados USDT-M/USDC-M

| Caso | Operaciones | Anual (período) | Anual (invertido) | Neto medio/op | IC95 % media | p (media ≤ 0) | Peor op. | Caída máx. |
|---|---|---|---|---|---|---|---|---|
| base | 0 | — | — | — | — | — | — | — |

### Triangular spot — optimista (solo ticker: cierres de 1 min, sin profundidad histórica)

| Ciclo | Minutos | Bruto p50 | Bruto p99 | Bruto máx. | ½ diferencial (perfil) | Min. neto > 0 · VIP 0 | Min. neto > 0 · VIP 9 + BNB |
|---|---|---|---|---|---|---|---|
| USDT→BNB→BTC→USDT | 43 201 | +0,08 pb | +4,60 pb | +17,3 pb | +0,64 pb | 0 (0 USD) | 130 (149 USD) |
| USDT→BTC→BNB→USDT | 43 201 | -0,08 pb | +4,49 pb | +9,5 pb | +1,66 pb | 0 (0 USD) | 34 (29 USD) |
| USDT→BNB→ETH→USDT | 43 201 | +0,24 pb | +7,33 pb | +21,6 pb | +4,68 pb | 0 (0 USD) | 72 (185 USD) |
| USDT→ETH→BNB→USDT | 43 201 | -0,24 pb | +6,51 pb | +18,2 pb | +1,83 pb | 0 (0 USD) | 267 (462 USD) |
| USDT→BNB→SOL→USDT | 43 201 | +0,54 pb | +19,92 pb | +42,1 pb | +7,45 pb | 4 (8 USD) | 2048 (9 113 USD) |
| USDT→SOL→BNB→USDT | 43 201 | -0,54 pb | +19,59 pb | +37,7 pb | +7,51 pb | 1 (0 USD) | 1803 (8 395 USD) |
| USDT→BTC→ETH→USDT | 43 201 | -0,20 pb | +4,78 pb | +11,0 pb | +1,71 pb | 0 (0 USD) | 20 (20 USD) |
| USDT→ETH→BTC→USDT | 43 201 | +0,20 pb | +4,97 pb | +10,8 pb | +1,71 pb | 0 (0 USD) | 47 (30 USD) |
| USDT→BTC→SOL→USDT | 43 201 | -0,26 pb | +7,58 pb | +18,5 pb | +4,40 pb | 0 (0 USD) | 150 (305 USD) |
| USDT→SOL→BTC→USDT | 43 201 | +0,26 pb | +7,96 pb | +19,5 pb | +2,07 pb | 0 (0 USD) | 551 (1 011 USD) |
| USDT→BTC→XRP→USDT | 43 201 | -0,12 pb | +12,50 pb | +29,0 pb | +7,07 pb | 0 (0 USD) | 435 (1 428 USD) |
| USDT→XRP→BTC→USDT | 43 201 | +0,12 pb | +12,87 pb | +35,3 pb | +3,51 pb | 1 (2 USD) | 1502 (4 689 USD) |
| USDT→ETH→SOL→USDT | 43 201 | -0,20 pb | +6,60 pb | +18,9 pb | +5,41 pb | 0 (0 USD) | 7 (24 USD) |
| USDT→SOL→ETH→USDT | 43 201 | +0,20 pb | +6,81 pb | +20,6 pb | +2,61 pb | 0 (0 USD) | 169 (292 USD) |
| USDT→ETH→XRP→USDT | 43 201 | -0,11 pb | +19,34 pb | +47,2 pb | +5,96 pb | 24 (96 USD) | 2010 (10 689 USD) |
| USDT→XRP→ETH→USDT | 43 201 | +0,11 pb | +20,49 pb | +57,5 pb | +2,55 pb | 51 (254 USD) | 4297 (23 331 USD) |

Pares sin perfil de profundidad (sin medio diferencial: aún más optimista): ninguno.

Con libros reales capturados (26 fotografías, 2026-10-16 → 2026-10-17; motor T38 `scan_triangular` sin cambios): VIP 0: 0 de 256 ciclos con neto > 0, mediana -33,7 pb, mejor -27,7 pb; VIP 9 + BNB: 0 de 256 ciclos con neto > 0, mediana -9,1 pb, mejor -3,1 pb. Con VIP 0 ningún ciclo real sale positivo: lo que el ticker marca como positivo son desfases entre cierres de pares poco líquidos, no precios ejecutables a la vez.

## Riesgo de pata incompleta (una pata ejecuta y la otra no)

BTC: deshacer la pata spot de 10 000 USD cuesta +20,0 pb (ida y vuelta); pérdida por incidente según la latencia:

| Latencia | Media | p95 | p99 | Máx. | Esperado/ejecución (p=1%) | Desv. 2.ª pata |
|---|---|---|---|---|---|---|
| 50 ms | +20,0 pb | +20,3 pb | +20,5 pb | +23,2 pb | +0,20 pb | +0,19 pb |
| 250 ms | +20,0 pb | +20,6 pb | +21,2 pb | +29,3 pb | +0,20 pb | +0,42 pb |
| 1000 ms | +20,0 pb | +21,2 pb | +22,4 pb | +56,3 pb | +0,20 pb | +0,83 pb |
| 5000 ms | +20,0 pb | +22,6 pb | +25,2 pb | +62,2 pb | +0,20 pb | +1,86 pb |
| 30000 ms | +20,0 pb | +26,3 pb | +32,8 pb | +118,8 pb | +0,20 pb | +4,56 pb |

ETH: deshacer la pata spot de 10 000 USD cuesta +20,0 pb (ida y vuelta); pérdida por incidente según la latencia:

| Latencia | Media | p95 | p99 | Máx. | Esperado/ejecución (p=1%) | Desv. 2.ª pata |
|---|---|---|---|---|---|---|
| 50 ms | +20,0 pb | +20,4 pb | +20,7 pb | +26,5 pb | +0,20 pb | +0,24 pb |
| 250 ms | +20,0 pb | +20,8 pb | +21,6 pb | +36,2 pb | +0,20 pb | +0,55 pb |
| 1000 ms | +20,0 pb | +21,5 pb | +23,1 pb | +65,1 pb | +0,20 pb | +1,10 pb |
| 5000 ms | +20,0 pb | +23,4 pb | +26,8 pb | +92,1 pb | +0,20 pb | +2,45 pb |
| 30000 ms | +20,0 pb | +28,3 pb | +37,2 pb | +177,7 pb | +0,20 pb | +6,00 pb |

Carry de funding — neto por operación con incidentes sorteados: 50 ms: p5 +0,7 pb, peor -13,2 pb; 250 ms: p5 +0,8 pb, peor -13,4 pb; 1000 ms: p5 +0,7 pb, peor -13,6 pb; 5000 ms: p5 +0,7 pb, peor -19,2 pb; 30000 ms: p5 +0,6 pb, peor -48,8 pb. Prob. de incidente: 0% → +102,8 pb/op; 1% → +102,5 pb/op; 5% → +101,4 pb/op.

Base (cash-and-carry trimestral) — neto por operación con incidentes sorteados: 50 ms: p5 -73,7 pb, peor -108,4 pb; 250 ms: p5 -73,8 pb, peor -108,5 pb; 1000 ms: p5 -73,9 pb, peor -108,8 pb; 5000 ms: p5 -74,3 pb, peor -109,4 pb; 30000 ms: p5 -77,1 pb, peor -111,0 pb. Prob. de incidente: 0% → +131,2 pb/op; 1% → +131,0 pb/op; 5% → +130,3 pb/op.

## Sensibilidad (decisión cada 24 h; celda = operaciones · anual período · neto medio)

### Comisiones (nivel VIP / BNB)

| Caso | Carry de funding | Base (cash-and-carry trimestral) | Perpetuos relacionados USDT-M/USDC-M |
|---|---|---|---|
| VIP 0 | 30 op. · +4,06 % · +102,1 pb/op · 12 m +1,16 % | 20 op. · +3,51 % · +131,4 pb/op · 12 m +2,44 % | 0 op. |
| VIP 0 + BNB | 30 op. · +4,24 % · +106,6 pb/op · 12 m +1,32 % | 20 op. · +3,61 % · +135,3 pb/op · 12 m +2,53 % | 1 op. · +0,03 % · +21,1 pb/op · 12 m +0,11 % |
| VIP 3 + BNB | 30 op. · +4,52 % · +113,6 pb/op · 12 m +1,57 % | 21 op. · +3,66 % · +130,9 pb/op · 12 m +2,25 % | 2 op. · +0,06 % · +22,4 pb/op · 12 m +0,22 % |
| VIP 9 + BNB | 30 op. · +4,75 % · +119,3 pb/op · 12 m +1,77 % | 21 op. · +3,82 % · +136,7 pb/op · 12 m +2,36 % | 20 op. · +0,01 % · +0,5 pb/op · 12 m -0,01 % |

### Nocional por operación (capacidad)

| Caso | Carry de funding | Base (cash-and-carry trimestral) | Perpetuos relacionados USDT-M/USDC-M |
|---|---|---|---|
| 1 000 USD | 30 op. · +4,06 % · +102,1 pb/op · 12 m +1,16 % | 20 op. · +3,51 % · +131,5 pb/op · 12 m +2,45 % | 0 op. |
| 10 000 USD | 30 op. · +4,06 % · +102,1 pb/op · 12 m +1,16 % | 20 op. · +3,51 % · +131,4 pb/op · 12 m +2,44 % | 0 op. |
| 100 000 USD | 30 op. · +4,06 % · +102,0 pb/op · 12 m +1,16 % | 20 op. · +3,44 % · +128,7 pb/op · 12 m +2,38 % | 0 op. |
| 1 000 000 USD | 0 op. | 0 op. | 0 op. |

### Profundidad (libro × escala)

| Caso | Carry de funding | Base (cash-and-carry trimestral) | Perpetuos relacionados USDT-M/USDC-M |
|---|---|---|---|
| ×1 | 30 op. · +4,06 % · +102,1 pb/op · 12 m +1,16 % | 20 op. · +3,51 % · +131,4 pb/op · 12 m +2,44 % | 0 op. |
| ×0.5 | 30 op. · +4,06 % · +102,1 pb/op · 12 m +1,16 % | 20 op. · +3,50 % · +131,2 pb/op · 12 m +2,44 % | 0 op. |
| ×0.1 | 30 op. · +4,04 % · +101,5 pb/op · 12 m +1,14 % | 20 op. · +3,44 % · +129,0 pb/op · 12 m +2,39 % | 0 op. |

### Apalancamiento de las patas de futuros

| Caso | Carry de funding | Base (cash-and-carry trimestral) | Perpetuos relacionados USDT-M/USDC-M |
|---|---|---|---|
| ×1 | 30 op. · +3,19 % · +80,1 pb/op · 12 m +0,91 % | 20 op. · +2,67 % · +99,7 pb/op · 12 m +2,03 % | 0 op. |
| ×2 | 30 op. · +4,06 % · +102,1 pb/op · 12 m +1,16 % | 20 op. · +3,51 % · +131,4 pb/op · 12 m +2,44 % | 0 op. |
| ×3 | 30 op. · +4,48 % · +112,7 pb/op · 12 m +1,25 % | 20 op. · +3,82 % · +143,5 pb/op · 12 m +2,74 % | 0 op. |

## Oportunidades reales y significancia

Por umbral de neto estimado por el motor: lo realizado de todas las decisiones que lo superan (se solapan: IC por bootstrap en bloques del largo de la tenencia) y la política de una posición a la vez con ese umbral.

**Carry de funding (tenencia del motor en vivo, 24 h)**: 4132 decisiones, 8264 valoradas, 0 seleccionadas por el motor (0 con realizado > 0); descartes: below_min 8264.

| Umbral neto estimado | n | Estimado medio | Realizado medio | IC95 % | p ≤ 0 | % > 0 | Política: op. | Política: anual |
|---|---|---|---|---|---|---|---|---|
| todas | 8258 | -18,7 pb | -19,0 pb | [-19,1; -18,9] pb | 1,000 | 0 % | 2754 | -69,39 % |

**Carry de funding (tenencia 2160 h)**: 4132 decisiones, 8264 valoradas, 7131 seleccionadas por el motor (6385 con realizado > 0); descartes: below_min 1133. Puntuación del selector de las seleccionadas (pb/día ajustados por riesgo, la de las alertas T39): p50 0,88, p90 2,11, p99 7,51.

| Umbral neto estimado | n | Estimado medio | Realizado medio | IC95 % | p ≤ 0 | % > 0 | Política: op. | Política: anual |
|---|---|---|---|---|---|---|---|---|
| todas | 7724 | +101,7 pb | +99,4 pb | [+67,4; +133,3] pb | 0,000 | 92 % | 30 | +4,04 % |
| +0 pb | 6671 | +124,0 pb | +108,6 pb | [+75,4; +146,9] pb | 0,000 | 96 % | 30 | +4,09 % |
| +2 pb | 6617 | +125,0 pb | +108,8 pb | [+75,3; +147,4] pb | 0,000 | 96 % | 30 | +4,08 % |
| +5 pb | 6539 | +126,5 pb | +109,2 pb | [+75,6; +147,1] pb | 0,000 | 97 % | 30 | +4,08 % |
| +10 pb | 6428 | +128,5 pb | +109,9 pb | [+76,5; +147,6] pb | 0,000 | 97 % | 30 | +4,08 % |
| +20 pb | 6134 | +134,0 pb | +111,9 pb | [+77,8; +151,0] pb | 0,000 | 97 % | 29 | +3,97 % |
| +50 pb | 5155 | +152,6 pb | +119,4 pb | [+79,6; +165,3] pb | 0,000 | 97 % | 28 | +3,86 % |
| +100 pb | 3088 | +204,7 pb | +152,0 pb | [+98,8; +212,6] pb | 0,000 | 100 % | 23 | +3,80 % |
| +200 pb | 804 | +386,6 pb | +213,9 pb | [+143,9; +294,0] pb | 0,000 | 100 % | 9 | +2,50 % |

**Base (cash-and-carry trimestral)**: 4132 decisiones, 30354 valoradas, 18654 seleccionadas por el motor (13464 con realizado > 0); descartes: below_min 11700. Puntuación del selector de las seleccionadas (pb/día ajustados por riesgo, la de las alertas T39): p50 0,64, p90 1,66, p99 3,36.

| Umbral neto estimado | n | Estimado medio | Realizado medio | IC95 % | p ≤ 0 | % > 0 | Política: op. | Política: anual |
|---|---|---|---|---|---|---|---|---|
| todas | 28292 | +44,9 pb | +5,1 pb | [-19,8; +30,6] pb | 0,336 | 62 % | 20 | +3,48 % |
| +0 pb | 17985 | +107,2 pb | +53,0 pb | [+25,0; +79,3] pb | 0,000 | 76 % | 20 | +3,48 % |
| +2 pb | 17642 | +109,3 pb | +54,7 pb | [+25,5; +80,8] pb | 0,000 | 76 % | 20 | +3,48 % |
| +5 pb | 17208 | +112,0 pb | +57,0 pb | [+29,1; +83,6] pb | 0,001 | 77 % | 20 | +3,49 % |
| +10 pb | 16545 | +116,2 pb | +60,1 pb | [+29,9; +88,9] pb | 0,000 | 78 % | 20 | +3,49 % |
| +20 pb | 15283 | +124,5 pb | +65,7 pb | [+31,3; +96,4] pb | 0,000 | 79 % | 20 | +3,55 % |
| +50 pb | 11433 | +154,9 pb | +83,6 pb | [+42,1; +125,2] pb | 0,000 | 81 % | 19 | +3,63 % |
| +100 pb | 6971 | +207,2 pb | +117,0 pb | [+51,1; +179,3] pb | 0,000 | 83 % | 16 | +3,30 % |
| +200 pb | 2924 | +297,9 pb | +196,2 pb | [+114,5; +277,6] pb | 0,000 | 89 % | 14 | +3,93 % |

**Perpetuos relacionados USDT-M/USDC-M**: 4132 decisiones, 6098 valoradas, 0 seleccionadas por el motor (0 con realizado > 0); descartes: below_min 6098.

| Umbral neto estimado | n | Estimado medio | Realizado medio | IC95 % | p ≤ 0 | % > 0 | Política: op. | Política: anual |
|---|---|---|---|---|---|---|---|---|
| todas | 6092 | -18,7 pb | -19,3 pb | [-19,4; -19,3] pb | 1,000 | 0 % | 5383 | -138,40 % |
| +0 pb | 1 | +0,4 pb | +19,1 pb | — | — | 100 % | 1 | +0,03 % |

## Capital mínimo

Técnico (mínimos de orden de Binance, `exchangeInfo`, al último precio): la mayor orden mínima de las patas más el margen de cada pata de futuros (× 1/2). Por encima, comisiones y funding son proporcionales al nocional (el % neto no mejora con más capital) hasta que el libro se agota: ver «Nocional por operación (capacidad)».

| Estrategia · activo | Orden mínima (USD) | Capital mínimo (USD) |
|---|---|---|
| basis perpetuo/trimestral · BTC | 81,78 | 81,78 |
| basis perpetuo/trimestral · ETH | 20,00 | 20,00 |
| basis spot/trimestral · BTC | 81,78 | 122,67 |
| basis spot/trimestral · ETH | 5,00 | 7,50 |
| funding_carry · BTC | 81,78 | 122,67 |
| funding_carry · ETH | 20,00 | 30,00 |
| related_perps · BTC | 81,78 | 81,78 |
| related_perps · ETH | 20,00 | 20,00 |

## Calibración de riesgos

| Medida | Activo | p50 | p90 | p99 |
|---|---|---|---|---|
| Movimiento \|rend. 24 h\| | BTC | 1,15 % | 3,83 % | 7,97 % |
| Movimiento \|rend. 24 h\| | ETH | 1,52 % | 5,14 % | 10,46 % |
| \|Δ base perp−spot\| en 2160 h | BTC | 1,5 pb | 9,5 pb | 14,4 pb |
| \|Δ base perp−spot\| en 2160 h | ETH | 1,6 pb | 10,1 pb | 14,3 pb |
| \|funding realizado (90 liq.) − extrapolado (21)\| por liquidación | BTC | 0,0022 % | 0,0070 % | 0,0239 % |
| \|funding realizado (90 liq.) − extrapolado (21)\| por liquidación | ETH | 0,0023 % | 0,0071 % | 0,0240 % |

## Parámetros del selector (T38) fijados con esta evidencia

| Parámetro | Antes | Después | Evidencia |
|---|---|---|---|
| selectable | ('funding_carry', 'basis', 'related_perps') | ('funding_carry', 'basis') | se desactiva toda estrategia con veredicto No viable |
| carry_horizon_h | 24.0 | 2160.0 | tenencia del carry con mayor rentabilidad anual sobre el período (tabla de horizontes) |
| min_net_bps | 2.0 | 2.0 | umbral con realizado significativo (IC95 % > 0, ≥ 30 decisiones) y rentabilidad de la política dentro del ruido de la mejor; se mantiene si la evidencia no lo distingue; el más exigente entre las seleccionables |
| perp_leverage | 2.0 | 3.0 | apalancamiento de las patas de futuros con mayor rentabilidad anual sin liquidaciones (sensibilidad) |
| disabled_variants | () | ('corto perpetuo / largo trimestral', 'largo perpetuo / corto trimestral') | variantes con veredicto No viable en el backtest (neto medio ≤ 0) aunque su estrategia siga activa |
| daily_move | 0.04 | 0.0514 | p90 medido en el histórico (ver «Calibración de riesgos») |
| basis_floor_bps | 5.0 | 10.1 | p90 medido en el histórico (ver «Calibración de riesgos») |
| funding_shock_rate | 0.0001 | 7.1e-05 | p90 medido en el histórico (ver «Calibración de riesgos») |

Sin calibrar (sin evidencia suficiente): `risk_aversion`, `risk_weights`, `max_liquidity_risk` (ver BACKLOG T43).

