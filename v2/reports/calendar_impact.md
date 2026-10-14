# Impacto histórico del calendario en BTC/ETH (T37)

Generado por `python -m eim.analytics.event_report` el 2026-10-14 21:33 UTC. Velas 15m de Binance USDⓈ-M (almacén local).

## Método

- Ventana por evento: [−60 min, +240 min] alrededor de la hora oficial de publicación.
- **Normal** = misma hora UTC en hasta 20 días hábiles previos (≤ 60 d) sin eventos medio/alto a ±4 h. Se compara con la mediana de esos controles → descuenta la estacionalidad intradía.
- Medida: log(rango del evento / rango normal). Se da la distribución completa (p10…p90) y la fracción de eventos por encima de lo normal, no solo la media.
- Significancia: bootstrap (4000 remuestreos, H0 media = 0), Holm sobre todas las pruebas de ventana (tipo × activo × ventana); por vela, Holm dentro de cada tipo × activo. Efecto relevante: cociente ≥ 1.25. Mínimo para fijar ventana: n ≥ 12.
- Ventana recomendada = velas contiguas antes/después de t0 con rango significativamente elevado; se toma el máximo entre activos (el veto aplica a ambos).

## Datos

- BTCUSDT: velas 2023-01-01 → 2026-10-14
- ETHUSDT: velas 2023-01-01 → 2026-10-14
- FOMC: 30 eventos 2023-02-01 → 2026-09-16; 0 coinciden a la misma hora con otra publicación medio/alto
- Vencimiento: 13 eventos 2023-03-31 → 2026-09-25; 0 coinciden a la misma hora con otra publicación medio/alto
- Comercio: 22 eventos 2025-01-07 → 2026-10-06; 1 coinciden a la misma hora con otra publicación medio/alto
- JOLTS: 21 eventos 2025-01-07 → 2026-09-29; 0 coinciden a la misma hora con otra publicación medio/alto
- NFP: 21 eventos 2025-01-10 → 2026-10-02; 1 coinciden a la misma hora con otra publicación medio/alto
- PPI: 20 eventos 2025-01-14 → 2026-09-10; 0 coinciden a la misma hora con otra publicación medio/alto
- CPI: 21 eventos 2025-01-15 → 2026-10-14; 0 coinciden a la misma hora con otra publicación medio/alto
- GDP: 20 eventos 2025-01-30 → 2026-09-30; 10 coinciden a la misma hora con otra publicación medio/alto
- ECI: 7 eventos 2025-01-31 → 2026-07-31; 4 coinciden a la misma hora con otra publicación medio/alto
- PCE: 20 eventos 2025-01-31 → 2026-09-30; 11 coinciden a la misma hora con otra publicación medio/alto
- Fuentes: Fed (FOMC, histórico desde 2021), BLS y BEA (sus calendarios públicos solo traen desde 2025), vencimientos Binance por regla. Lista exacta en `reports/calendar/events.csv`.

## Ventanas recomendadas

| Tipo | n (BTC/ETH) | Pre | Post | Veredicto |
|---|---|---|---|---|
| FOMC | 30/30 | 30 | 225 | pausa −30 min / +225 min |
| Vencimiento | 13/13 | 60 | 0 | pausa −60 min / +0 min |
| Comercio | 22/22 | 0 | 0 | **no mueve el mercado** de forma detectable (ninguna vela ni ventana significativa) |
| JOLTS | 21/21 | 0 | 15 | pausa −0 min / +15 min |
| NFP | 21/21 | 0 | 45 | pausa −0 min / +45 min |
| PPI | 20/20 | 0 | 30 | pausa −0 min / +30 min |
| CPI | 21/21 | 15 | 30 | pausa −15 min / +30 min |
| GDP | 20/20 | 0 | 15 | pausa −0 min / +15 min |
| ECI | 7/7 | — | — | muestra insuficiente: no se fija ventana por evidencia |
| PCE | 20/20 | 0 | 15 | pausa −0 min / +15 min |

## Conclusiones

- **Mueven el mercado** (rango por encima de lo normal, significativo tras Holm): FOMC, Vencimiento, JOLTS, NFP, PPI, CPI, GDP, PCE. Duración = columnas Pre/Post de la tabla anterior; el detalle vela a vela está en «Perfil por vela».
- **No mueven el mercado** de forma detectable: Comercio → sin ventana de pausa.
- **Muestra insuficiente**: ECI → se mantiene la ventana por impacto del agente, marcada como «sin evidencia».
- **Dirección**: el evento no anticipa el signo del movimiento. Significativo tras Holm: ETHUSDT NFP (-1.35 %, p Holm 0.050) — marginal, muestra pequeña, no es una estrategia (operar eventos queda fuera de alcance).

### Limitaciones

- BLS/BEA solo publican su calendario desde 2025 → n≈20 por tipo: se detectan efectos grandes (×1.4 o más en la vela), no efectos pequeños; ausencia de significancia ≠ ausencia de efecto.
- PIB y PCE se publican a menudo a la misma hora: su efecto no se puede separar.
- Velas de 15 min: la resolución mínima de la ventana es 15 min.
- Régimen 2023–2026; recalcular periódicamente (`--fetch`) y revisar `params.py`.

## Rango realizado frente a lo normal

Cociente = exp(log-cociente). `>1` = más movimiento que un día normal a la misma hora.

| Activo | Tipo | Ventana | n | mediana | p10 | p90 | % >normal | media IC95 % | p | p Holm |
|---|---|---|---|---|---|---|---|---|---|---|
| BTCUSDT | FOMC | −60…0 min | 30 | 1.09 | 0.62 | 1.71 | 57 | 0.93–1.25 | 0.332 | 1.000 |
| BTCUSDT | FOMC | 0…+15 min | 30 | 2.90 | 1.45 | 5.77 | 97 | 2.46–3.55 | <0.001 | 0.020 ✱ |
| BTCUSDT | FOMC | 0…+1 h | 30 | 2.66 | 1.57 | 4.11 | 100 | 2.13–2.84 | <0.001 | 0.020 ✱ |
| BTCUSDT | FOMC | 0…+4 h | 30 | 2.25 | 1.41 | 3.31 | 100 | 1.94–2.55 | <0.001 | 0.020 ✱ |
| BTCUSDT | Vencimiento | −60…0 min | 13 | 1.37 | 0.94 | 3.13 | 85 | 1.24–2.06 | <0.001 | 0.020 ✱ |
| BTCUSDT | Vencimiento | 0…+15 min | 13 | 1.13 | 0.81 | 1.86 | 62 | 0.98–1.38 | 0.109 | 1.000 |
| BTCUSDT | Vencimiento | 0…+1 h | 13 | 1.03 | 0.77 | 1.97 | 62 | 0.91–1.38 | 0.290 | 1.000 |
| BTCUSDT | Vencimiento | 0…+4 h | 13 | 0.89 | 0.54 | 1.65 | 38 | 0.75–1.19 | 0.603 | 1.000 |
| BTCUSDT | Comercio | −60…0 min | 22 | 0.96 | 0.59 | 1.67 | 45 | 0.84–1.16 | 0.921 | 1.000 |
| BTCUSDT | Comercio | 0…+15 min | 22 | 0.91 | 0.57 | 2.47 | 45 | 0.87–1.47 | 0.445 | 1.000 |
| BTCUSDT | Comercio | 0…+1 h | 22 | 1.05 | 0.54 | 1.78 | 55 | 0.83–1.23 | 0.897 | 1.000 |
| BTCUSDT | Comercio | 0…+4 h | 22 | 1.01 | 0.59 | 1.66 | 55 | 0.86–1.24 | 0.859 | 1.000 |
| BTCUSDT | JOLTS | −60…0 min | 21 | 0.84 | 0.55 | 1.33 | 33 | 0.72–1.06 | 0.159 | 1.000 |
| BTCUSDT | JOLTS | 0…+15 min | 21 | 1.30 | 0.86 | 2.58 | 67 | 1.14–1.68 | <0.001 | 0.044 ✱ |
| BTCUSDT | JOLTS | 0…+1 h | 21 | 1.46 | 0.68 | 2.24 | 67 | 1.04–1.63 | 0.018 | 0.900 |
| BTCUSDT | JOLTS | 0…+4 h | 21 | 1.05 | 0.63 | 1.80 | 67 | 0.93–1.34 | 0.292 | 1.000 |
| BTCUSDT | NFP | −60…0 min | 21 | 0.80 | 0.53 | 2.30 | 38 | 0.76–1.20 | 0.649 | 1.000 |
| BTCUSDT | NFP | 0…+15 min | 21 | 3.11 | 1.83 | 5.76 | 100 | 2.61–3.93 | <0.001 | 0.020 ✱ |
| BTCUSDT | NFP | 0…+1 h | 21 | 2.03 | 1.42 | 3.23 | 95 | 1.78–2.51 | <0.001 | 0.020 ✱ |
| BTCUSDT | NFP | 0…+4 h | 21 | 1.13 | 0.65 | 2.17 | 67 | 0.97–1.42 | 0.100 | 1.000 |
| BTCUSDT | PPI | −60…0 min | 20 | 0.95 | 0.50 | 1.52 | 45 | 0.79–1.16 | 0.684 | 1.000 |
| BTCUSDT | PPI | 0…+15 min | 20 | 1.92 | 0.77 | 4.79 | 85 | 1.52–3.00 | <0.001 | 0.020 ✱ |
| BTCUSDT | PPI | 0…+1 h | 20 | 1.38 | 0.75 | 2.92 | 75 | 1.14–1.89 | 0.004 | 0.243 |
| BTCUSDT | PPI | 0…+4 h | 20 | 0.92 | 0.64 | 1.44 | 35 | 0.80–1.09 | 0.356 | 1.000 |
| BTCUSDT | CPI | −60…0 min | 21 | 1.19 | 0.71 | 1.85 | 71 | 0.95–1.32 | 0.153 | 1.000 |
| BTCUSDT | CPI | 0…+15 min | 21 | 3.15 | 1.98 | 6.09 | 100 | 2.81–4.11 | <0.001 | 0.020 ✱ |
| BTCUSDT | CPI | 0…+1 h | 21 | 2.08 | 0.95 | 3.52 | 86 | 1.55–2.32 | <0.001 | 0.020 ✱ |
| BTCUSDT | CPI | 0…+4 h | 21 | 1.29 | 0.73 | 1.76 | 67 | 1.05–1.46 | 0.011 | 0.598 |
| BTCUSDT | GDP | −60…0 min | 20 | 0.75 | 0.59 | 1.44 | 40 | 0.74–1.06 | 0.163 | 1.000 |
| BTCUSDT | GDP | 0…+15 min | 20 | 1.52 | 0.84 | 3.76 | 75 | 1.30–2.24 | <0.001 | 0.044 ✱ |
| BTCUSDT | GDP | 0…+1 h | 20 | 1.43 | 0.58 | 1.93 | 65 | 0.94–1.53 | 0.150 | 1.000 |
| BTCUSDT | GDP | 0…+4 h | 20 | 0.95 | 0.62 | 1.32 | 45 | 0.80–1.15 | 0.624 | 1.000 |
| BTCUSDT | ECI | −60…0 min | 7 | 0.70 | 0.56 | 1.46 | 29 | 0.61–1.15 | 0.210 | 1.000 |
| BTCUSDT | ECI | 0…+15 min | 7 | 0.91 | 0.57 | 2.02 | 29 | 0.70–1.45 | 0.978 | 1.000 |
| BTCUSDT | ECI | 0…+1 h | 7 | 0.59 | 0.45 | 1.65 | 29 | 0.53–1.21 | 0.291 | 1.000 |
| BTCUSDT | ECI | 0…+4 h | 7 | 0.67 | 0.43 | 1.30 | 43 | 0.52–1.05 | 0.086 | 1.000 |
| BTCUSDT | PCE | −60…0 min | 20 | 1.09 | 0.60 | 1.71 | 60 | 0.84–1.26 | 0.814 | 1.000 |
| BTCUSDT | PCE | 0…+15 min | 20 | 1.74 | 0.72 | 4.14 | 70 | 1.29–2.37 | 0.001 | 0.071 |
| BTCUSDT | PCE | 0…+1 h | 20 | 1.34 | 0.55 | 2.35 | 75 | 0.95–1.56 | 0.110 | 1.000 |
| BTCUSDT | PCE | 0…+4 h | 20 | 0.93 | 0.55 | 2.20 | 45 | 0.83–1.27 | 0.858 | 1.000 |
| ETHUSDT | FOMC | −60…0 min | 30 | 1.28 | 0.60 | 2.29 | 70 | 1.02–1.41 | 0.027 | 1.000 |
| ETHUSDT | FOMC | 0…+15 min | 30 | 3.49 | 2.06 | 6.49 | 100 | 2.90–4.19 | <0.001 | 0.020 ✱ |
| ETHUSDT | FOMC | 0…+1 h | 30 | 2.82 | 1.72 | 4.05 | 100 | 2.41–3.11 | <0.001 | 0.020 ✱ |
| ETHUSDT | FOMC | 0…+4 h | 30 | 2.06 | 1.39 | 3.30 | 97 | 1.79–2.38 | <0.001 | 0.020 ✱ |
| ETHUSDT | Vencimiento | −60…0 min | 13 | 1.33 | 0.66 | 2.68 | 77 | 1.06–2.13 | 0.025 | 1.000 |
| ETHUSDT | Vencimiento | 0…+15 min | 13 | 1.11 | 0.76 | 2.03 | 69 | 0.96–1.45 | 0.147 | 1.000 |
| ETHUSDT | Vencimiento | 0…+1 h | 13 | 1.14 | 0.78 | 1.87 | 69 | 0.96–1.51 | 0.131 | 1.000 |
| ETHUSDT | Vencimiento | 0…+4 h | 13 | 0.98 | 0.62 | 2.12 | 46 | 0.82–1.41 | 0.641 | 1.000 |
| ETHUSDT | Comercio | −60…0 min | 22 | 0.90 | 0.61 | 1.54 | 36 | 0.81–1.12 | 0.585 | 1.000 |
| ETHUSDT | Comercio | 0…+15 min | 22 | 1.12 | 0.52 | 3.03 | 55 | 0.87–1.52 | 0.335 | 1.000 |
| ETHUSDT | Comercio | 0…+1 h | 22 | 0.97 | 0.61 | 1.64 | 45 | 0.86–1.23 | 0.761 | 1.000 |
| ETHUSDT | Comercio | 0…+4 h | 22 | 1.03 | 0.50 | 1.98 | 55 | 0.83–1.23 | 0.992 | 1.000 |
| ETHUSDT | JOLTS | −60…0 min | 21 | 0.91 | 0.66 | 2.14 | 48 | 0.84–1.32 | 0.765 | 1.000 |
| ETHUSDT | JOLTS | 0…+15 min | 21 | 1.30 | 0.94 | 2.91 | 71 | 1.21–1.75 | <0.001 | 0.020 ✱ |
| ETHUSDT | JOLTS | 0…+1 h | 21 | 1.25 | 0.65 | 2.38 | 62 | 1.02–1.63 | 0.042 | 1.000 |
| ETHUSDT | JOLTS | 0…+4 h | 21 | 1.22 | 0.57 | 2.31 | 52 | 0.88–1.35 | 0.453 | 1.000 |
| ETHUSDT | NFP | −60…0 min | 21 | 1.10 | 0.50 | 1.64 | 57 | 0.84–1.25 | 0.822 | 1.000 |
| ETHUSDT | NFP | 0…+15 min | 21 | 3.14 | 2.14 | 5.84 | 100 | 2.90–4.10 | <0.001 | 0.020 ✱ |
| ETHUSDT | NFP | 0…+1 h | 21 | 1.92 | 1.44 | 2.90 | 100 | 1.83–2.44 | <0.001 | 0.020 ✱ |
| ETHUSDT | NFP | 0…+4 h | 21 | 1.20 | 0.78 | 1.94 | 67 | 1.07–1.54 | 0.010 | 0.517 |
| ETHUSDT | PPI | −60…0 min | 20 | 0.98 | 0.66 | 1.59 | 50 | 0.82–1.17 | 0.726 | 1.000 |
| ETHUSDT | PPI | 0…+15 min | 20 | 2.16 | 1.13 | 4.17 | 90 | 1.69–2.94 | <0.001 | 0.020 ✱ |
| ETHUSDT | PPI | 0…+1 h | 20 | 1.43 | 0.88 | 3.23 | 85 | 1.23–2.01 | 0.001 | 0.071 |
| ETHUSDT | PPI | 0…+4 h | 20 | 1.08 | 0.71 | 1.53 | 55 | 0.89–1.19 | 0.684 | 1.000 |
| ETHUSDT | CPI | −60…0 min | 21 | 1.28 | 0.70 | 1.96 | 76 | 1.04–1.43 | 0.015 | 0.778 |
| ETHUSDT | CPI | 0…+15 min | 21 | 3.49 | 1.86 | 7.35 | 100 | 2.94–4.58 | <0.001 | 0.020 ✱ |
| ETHUSDT | CPI | 0…+1 h | 21 | 2.38 | 0.97 | 3.76 | 86 | 1.79–2.79 | <0.001 | 0.020 ✱ |
| ETHUSDT | CPI | 0…+4 h | 21 | 1.48 | 0.90 | 2.17 | 76 | 1.25–1.79 | <0.001 | 0.020 ✱ |
| ETHUSDT | GDP | −60…0 min | 20 | 0.95 | 0.65 | 1.45 | 40 | 0.82–1.24 | 0.949 | 1.000 |
| ETHUSDT | GDP | 0…+15 min | 20 | 1.84 | 0.73 | 4.00 | 70 | 1.31–2.41 | <0.001 | 0.020 ✱ |
| ETHUSDT | GDP | 0…+1 h | 20 | 1.27 | 0.63 | 2.51 | 65 | 1.03–1.62 | 0.023 | 1.000 |
| ETHUSDT | GDP | 0…+4 h | 20 | 1.02 | 0.62 | 1.45 | 50 | 0.82–1.19 | 0.891 | 1.000 |
| ETHUSDT | ECI | −60…0 min | 7 | 0.86 | 0.65 | 1.56 | 43 | 0.77–1.31 | 0.991 | 1.000 |
| ETHUSDT | ECI | 0…+15 min | 7 | 1.10 | 0.65 | 2.33 | 57 | 0.78–1.71 | 0.530 | 1.000 |
| ETHUSDT | ECI | 0…+1 h | 7 | 1.00 | 0.48 | 1.91 | 43 | 0.62–1.49 | 0.912 | 1.000 |
| ETHUSDT | ECI | 0…+4 h | 7 | 0.88 | 0.62 | 1.13 | 43 | 0.72–1.05 | 0.176 | 1.000 |
| ETHUSDT | PCE | −60…0 min | 20 | 1.00 | 0.65 | 1.77 | 45 | 0.85–1.21 | 0.948 | 1.000 |
| ETHUSDT | PCE | 0…+15 min | 20 | 1.67 | 0.73 | 3.69 | 75 | 1.33–2.32 | <0.001 | 0.020 ✱ |
| ETHUSDT | PCE | 0…+1 h | 20 | 1.51 | 0.63 | 2.37 | 70 | 1.11–1.69 | 0.003 | 0.151 |
| ETHUSDT | PCE | 0…+4 h | 20 | 1.11 | 0.65 | 1.51 | 55 | 0.91–1.29 | 0.403 | 1.000 |

## Dirección (retorno 0…+4 h)

| Activo | Tipo | n | media % | p10 % | p90 % | % al alza | p | p Holm |
|---|---|---|---|---|---|---|---|---|
| BTCUSDT | FOMC | 30 | -0.16 | -2.90 | 2.03 | 50 | 0.684 | 1.000 |
| BTCUSDT | Vencimiento | 13 | -0.19 | -1.62 | 0.63 | 62 | 0.490 | 1.000 |
| BTCUSDT | Comercio | 22 | -0.56 | -2.58 | 0.84 | 41 | 0.102 | 1.000 |
| BTCUSDT | JOLTS | 21 | -0.50 | -3.25 | 0.75 | 38 | 0.200 | 1.000 |
| BTCUSDT | NFP | 21 | -0.84 | -2.31 | 0.59 | 24 | 0.009 | 0.166 |
| BTCUSDT | PPI | 20 | -0.24 | -2.26 | 1.00 | 50 | 0.446 | 1.000 |
| BTCUSDT | CPI | 21 | 0.16 | -2.00 | 1.85 | 57 | 0.660 | 1.000 |
| BTCUSDT | GDP | 20 | -0.48 | -1.72 | 0.16 | 35 | 0.010 | 0.166 |
| BTCUSDT | ECI | 7 | -0.12 | -1.28 | 0.68 | 57 | 0.760 | 1.000 |
| BTCUSDT | PCE | 20 | -0.15 | -1.68 | 1.10 | 45 | 0.602 | 1.000 |
| ETHUSDT | FOMC | 30 | -0.24 | -2.95 | 2.02 | 53 | 0.594 | 1.000 |
| ETHUSDT | Vencimiento | 13 | -0.37 | -2.02 | 0.82 | 46 | 0.313 | 1.000 |
| ETHUSDT | Comercio | 22 | -1.10 | -3.35 | 0.61 | 18 | 0.011 | 0.176 |
| ETHUSDT | JOLTS | 21 | -0.52 | -3.85 | 1.18 | 43 | 0.362 | 1.000 |
| ETHUSDT | NFP | 21 | -1.35 | -3.76 | 1.17 | 24 | 0.002 | 0.050 ✱ |
| ETHUSDT | PPI | 20 | -0.44 | -2.76 | 1.93 | 45 | 0.288 | 1.000 |
| ETHUSDT | CPI | 21 | 0.58 | -3.10 | 4.01 | 62 | 0.392 | 1.000 |
| ETHUSDT | GDP | 20 | -0.66 | -2.07 | 0.64 | 30 | 0.005 | 0.104 |
| ETHUSDT | ECI | 7 | -0.14 | -1.54 | 1.11 | 43 | 0.750 | 1.000 |
| ETHUSDT | PCE | 20 | -0.08 | -1.46 | 1.96 | 35 | 0.838 | 1.000 |

## Perfil por vela (cociente de rango, ✱ = significativo tras Holm)

| Activo | Tipo | -60 | -45 | -30 | -15 | +0 | +15 | +30 | +45 | +60 | +75 | +90 | +105 | +120 | +135 | +150 | +165 | +180 | +195 | +210 | +225 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTCUSDT | FOMC | 0.85 | 0.93 | 1.09 | 1.30✱ | 2.97✱ | 1.60✱ | 2.91✱ | 2.45✱ | 2.06✱ | 2.19✱ | 1.77✱ | 1.48✱ | 1.65✱ | 1.48✱ | 1.69✱ | 1.60✱ | 1.33 | 1.56✱ | 1.28✱ | 1.27 |
| BTCUSDT | Vencimiento | 1.25 | 1.19 | 1.87✱ | 1.42 | 1.15 | 1.02 | 1.05 | 1.13 | 1.04 | 0.96 | 0.93 | 0.97 | 1.01 | 0.88 | 0.96 | 1.07 | 0.82 | 1.05 | 0.95 | 0.84 |
| BTCUSDT | Comercio | 0.97 | 1.09 | 0.85 | 0.92 | 1.11 | 1.06 | 0.86 | 0.92 | 0.90 | 1.04 | 1.25 | 1.13 | 1.21 | 1.18 | 0.98 | 0.94 | 0.92 | 1.03 | 1.01 | 0.95 |
| BTCUSDT | JOLTS | 1.11 | 1.00 | 0.98 | 0.93 | 1.37✱ | 1.16 | 1.26 | 1.25 | 1.16 | 0.91 | 0.99 | 0.98 | 0.99 | 1.08 | 1.11 | 1.12 | 0.98 | 0.91 | 0.91 | 0.96 |
| BTCUSDT | NFP | 1.03 | 1.11 | 0.96 | 1.02 | 3.21✱ | 1.85✱ | 1.63✱ | 1.14 | 0.99 | 1.03 | 1.25 | 1.31 | 1.19 | 1.31 | 1.18 | 1.16 | 1.11 | 0.94 | 1.08 | 1.06 |
| BTCUSDT | PPI | 0.97 | 1.00 | 0.79 | 1.05 | 2.12✱ | 1.53✱ | 1.19 | 1.15 | 1.02 | 0.96 | 0.99 | 0.91 | 0.84 | 0.85 | 0.95 | 0.97 | 0.97 | 1.00 | 1.08 | 0.94 |
| BTCUSDT | CPI | 0.90 | 0.89 | 1.03 | 1.40✱ | 3.39✱ | 1.62✱ | 1.29 | 1.27 | 1.08 | 1.13 | 1.16 | 0.93 | 1.03 | 0.99 | 1.01 | 0.96 | 0.95 | 1.19 | 1.15 | 0.96 |
| BTCUSDT | GDP | 0.98 | 1.12 | 0.80 | 1.08 | 1.70✱ | 1.18 | 1.04 | 1.10 | 1.08 | 1.00 | 1.08 | 1.11 | 1.15 | 1.02 | 0.84 | 1.01 | 0.91 | 0.94 | 1.04 | 0.87 |
| BTCUSDT | ECI | 0.88 | 0.91 | 0.70 | 0.88 | 1.00 | 0.73 | 0.71 | 0.86 | 1.03 | 0.83 | 1.09 | 0.92 | 0.96 | 0.79 | 0.84 | 0.87 | 0.80 | 0.64 | 0.70 | 0.70 |
| BTCUSDT | PCE | 1.07 | 1.13 | 0.98 | 1.15 | 1.75✱ | 1.20 | 1.13 | 1.07 | 1.21 | 0.97 | 1.27 | 1.22 | 1.05 | 0.93 | 0.88 | 1.01 | 1.02 | 0.91 | 1.02 | 0.90 |
| ETHUSDT | FOMC | 0.92 | 0.98 | 1.28✱ | 1.62✱ | 3.50✱ | 1.73✱ | 2.98✱ | 2.44✱ | 2.16✱ | 2.32✱ | 1.73✱ | 1.58✱ | 1.77✱ | 1.56✱ | 1.65✱ | 1.56✱ | 1.36✱ | 1.46✱ | 1.26✱ | 1.22✱ |
| ETHUSDT | Vencimiento | 1.18 | 1.23 | 1.76 | 1.47 | 1.17 | 1.07 | 1.10 | 1.22 | 1.00 | 1.07 | 1.02 | 0.88 | 1.05 | 0.88 | 1.06 | 1.02 | 0.93 | 1.37 | 0.90 | 0.84 |
| ETHUSDT | Comercio | 1.03 | 1.00 | 0.84 | 0.90 | 1.15 | 1.05 | 0.91 | 1.06 | 0.96 | 1.13 | 1.25 | 1.16 | 1.21 | 1.12 | 1.00 | 0.99 | 0.87 | 1.03 | 0.98 | 0.94 |
| ETHUSDT | JOLTS | 1.20 | 1.20 | 1.00 | 0.94 | 1.44✱ | 1.23 | 1.17 | 1.24 | 1.14 | 1.03 | 0.99 | 1.07 | 1.02 | 1.03 | 1.09 | 1.10 | 0.90 | 0.96 | 0.90 | 0.97 |
| ETHUSDT | NFP | 0.98 | 1.00 | 0.99 | 1.08 | 3.40✱ | 1.76✱ | 1.46✱ | 1.16 | 1.02 | 1.07 | 1.28 | 1.19 | 1.12 | 1.21 | 1.14 | 1.08 | 1.01 | 0.88 | 1.17 | 1.00 |
| ETHUSDT | PPI | 1.00 | 1.13 | 1.00 | 0.95 | 2.19✱ | 1.39 | 1.32 | 1.19 | 0.98 | 0.94 | 1.10 | 0.94 | 0.99 | 0.91 | 0.97 | 1.09 | 0.97 | 0.98 | 1.13 | 1.07 |
| ETHUSDT | CPI | 1.04 | 0.97 | 1.17 | 1.51✱ | 3.68✱ | 1.89✱ | 1.30 | 1.47✱ | 1.15 | 1.23 | 1.20 | 1.03 | 1.04 | 1.05 | 1.08 | 1.07 | 1.04 | 1.19 | 1.12 | 1.00 |
| ETHUSDT | GDP | 0.93 | 0.95 | 0.85 | 1.31 | 1.79✱ | 1.19 | 1.01 | 1.35 | 1.04 | 0.99 | 1.12 | 1.06 | 1.01 | 0.97 | 0.84 | 1.03 | 0.96 | 0.94 | 0.97 | 0.87 |
| ETHUSDT | ECI | 1.04 | 0.95 | 1.02 | 1.23 | 1.14 | 0.97 | 0.90 | 1.07 | 1.06 | 0.93 | 1.01 | 1.09 | 0.90 | 0.82 | 0.86 | 0.81 | 0.88 | 0.95 | 0.74 | 0.73 |
| ETHUSDT | PCE | 1.07 | 0.99 | 1.04 | 1.21 | 1.76✱ | 1.15 | 1.17 | 1.24 | 1.07 | 1.00 | 1.24 | 1.17 | 1.01 | 0.90 | 0.90 | 0.97 | 1.00 | 0.99 | 1.08 | 0.87 |

## Sorpresa

No medible: las fuentes oficiales gratuitas no publican consenso (T33) y sin `EIM_FRED_API_KEY` tampoco hay valores reales. `event_study.by_surprise` está listo (terciles de |sorpresa|) para cuando exista una fuente de consenso.
