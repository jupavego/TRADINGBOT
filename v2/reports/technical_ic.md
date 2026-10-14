# Valor predictivo de los indicadores del agente `technical` (T35)

- BTCUSDT 1h: 33171 velas (2023-01-01 → 2026-10-14); prueba desde 2024-11-22; velas de prueba con taker_buy_v: 2/16586; fuente binance-futures-ws
- BTCUSDT 4h: 1501 velas (2026-02-05 → 2026-10-13); prueba desde 2026-06-10; velas de prueba con taker_buy_v: 0/751; fuente binance-futures-ws
- ETHUSDT 1h: 33166 velas (2023-01-01 → 2026-10-13); prueba desde 2024-11-21; velas de prueba con taker_buy_v: 0/16583; fuente binance-futures
- ETHUSDT 4h: sin velas en el almacén

Pruebas con dato: 189; corrección de Holm, α = 0.05.

**Veredicto: 20 de 189 pruebas son significativas tras Holm; el sesgo agregado no supera el azar.** Un IC significativo de magnitud pequeña no implica operabilidad tras costos (T27).

- IC positivo (el voto acierta): BOLL (BTCUSDT 1h, h=1), BOLL (ETHUSDT 1h, h=1), CCI (BTCUSDT 1h, h=1), KDJ (BTCUSDT 1h, h=1), KDJ (ETHUSDT 1h, h=1), RSI (BTCUSDT 1h, h=1), StochRSI (BTCUSDT 1h, h=1), WR (BTCUSDT 1h, h=1), WR (ETHUSDT 1h, h=1).
- IC negativo (el voto apunta al revés): DMI (ETHUSDT 1h, h=1), EMA (BTCUSDT 1h, h=1), EMA (ETHUSDT 1h, h=1), MA (BTCUSDT 1h, h=1), MA (ETHUSDT 1h, h=1), OBV (BTCUSDT 1h, h=1), VOL (BTCUSDT 1h, h=1), VWAP (BTCUSDT 1h, h=1), VWAP (ETHUSDT 1h, h=1), WMA (BTCUSDT 1h, h=1), WMA (ETHUSDT 1h, h=1).

## Lectura (manual, 2026-10-13; regenerar el informe la borra)

- **Lo único significativo es a 1 vela de 1h** y con signo de **reversión de corto plazo**: los votos de
  seguimiento de tendencia (MA/EMA/WMA, VWAP, DMI, OBV, VOL) tienen IC ≈ −0.03 y los osciladores
  en sobrecompra/sobreventa (WR, KDJ, BOLL, RSI, CCI, StochRSI) IC ≈ +0.03..+0.05. Magnitud muy
  pequeña (explica < 0.3 % de la varianza del retorno) y en parte puede ser rebote bid-ask del cierre.
- **A 6 y 24 velas ningún indicador supera el azar**, en ningún activo/marco. El sesgo agregado del
  agente no es significativo en ninguna prueba (IC negativo pequeño: hereda la reversión de 1 vela).
- BTC 4h solo tiene ~8 meses (751 velas de prueba): poca potencia. ETH 4h no está en el almacén.
- **Familia flujo sin medir:** el histórico no trae `taker_buy_v` (BACKLOG T34-4).
- Conclusión: el agente es **descriptivo** (resume qué dicen los indicadores), no una señal con edge.
  Se mantiene fuera de la síntesis (`SynthesisParams.excluded`) hasta que T44 lo decida; invertir el
  signo de las reglas de tendencia a h=1 sería sobreajuste y además no sobreviviría a los costos (T27).

| Activo | Indicador | h | IC | n | p | p Holm | Sig. |
|---|---|---|---|---|---|---|---|
| BTCUSDT 1h | WR | 1 | +0.0471 | 16585 | 0.0000 | 0.0000 | sí |
| BTCUSDT 1h | VWAP | 1 | -0.0386 | 16585 | 0.0000 | 0.0001 | sí |
| BTCUSDT 1h | KDJ | 1 | +0.0384 | 16585 | 0.0000 | 0.0001 | sí |
| BTCUSDT 1h | BOLL | 1 | +0.0368 | 16585 | 0.0000 | 0.0004 | sí |
| BTCUSDT 1h | WMA | 1 | -0.0355 | 16585 | 0.0000 | 0.0009 | sí |
| BTCUSDT 1h | StochRSI | 1 | +0.0347 | 16585 | 0.0000 | 0.0014 | sí |
| BTCUSDT 1h | MA | 1 | -0.0335 | 16585 | 0.0000 | 0.0028 | sí |
| BTCUSDT 1h | OBV | 1 | -0.0335 | 16585 | 0.0000 | 0.0029 | sí |
| BTCUSDT 1h | CCI | 1 | +0.0320 | 16585 | 0.0000 | 0.0067 | sí |
| BTCUSDT 1h | EMA | 1 | -0.0318 | 16585 | 0.0000 | 0.0073 | sí |
| BTCUSDT 1h | VOL | 1 | -0.0307 | 16585 | 0.0001 | 0.0135 | sí |
| BTCUSDT 1h | RSI | 1 | +0.0297 | 16585 | 0.0001 | 0.0226 | sí |
| BTCUSDT 1h | DMI | 1 | -0.0266 | 16585 | 0.0006 | 0.1018 | no |
| BTCUSDT 1h | TRIX | 1 | -0.0263 | 16585 | 0.0007 | 0.1154 | no |
| BTCUSDT 1h | MACD | 1 | -0.0260 | 16585 | 0.0008 | 0.1351 | no |
| BTCUSDT 1h | technical (agregado) | 1 | -0.0260 | 16585 | 0.0008 | 0.1357 | no |
| BTCUSDT 1h | EMV | 1 | -0.0257 | 16585 | 0.0009 | 0.1485 | no |
| BTCUSDT 1h | MTM | 1 | -0.0249 | 16585 | 0.0013 | 0.2130 | no |
| BTCUSDT 1h | SUPER | 1 | -0.0248 | 16585 | 0.0014 | 0.2258 | no |
| BTCUSDT 1h | MFI | 1 | +0.0247 | 16585 | 0.0015 | 0.2385 | no |
| BTCUSDT 1h | SAR | 1 | -0.0152 | 16585 | 0.0504 | 1.0000 | no |
| BTCUSDT 1h | BS.Vol | 1 | — | 0 | — | — | no |
| BTCUSDT 1h | Delta | 1 | — | 0 | — | — | no |
| BTCUSDT 1h | TakerRatio | 1 | — | 0 | — | — | no |
| BTCUSDT 1h | CVD | 1 | — | 0 | — | — | no |
| BTCUSDT 1h | MA | 6 | -0.0410 | 2764 | 0.0310 | 1.0000 | no |
| BTCUSDT 1h | technical (agregado) | 6 | -0.0410 | 2764 | 0.0311 | 1.0000 | no |
| BTCUSDT 1h | WMA | 6 | -0.0406 | 2764 | 0.0330 | 1.0000 | no |
| BTCUSDT 1h | SUPER | 6 | -0.0404 | 2764 | 0.0335 | 1.0000 | no |
| BTCUSDT 1h | EMA | 6 | -0.0386 | 2764 | 0.0427 | 1.0000 | no |
| BTCUSDT 1h | TRIX | 6 | -0.0383 | 2764 | 0.0438 | 1.0000 | no |
| BTCUSDT 1h | CCI | 6 | +0.0365 | 2764 | 0.0548 | 1.0000 | no |
| BTCUSDT 1h | VOL | 6 | -0.0346 | 2764 | 0.0692 | 1.0000 | no |
| BTCUSDT 1h | BOLL | 6 | +0.0331 | 2764 | 0.0818 | 1.0000 | no |
| BTCUSDT 1h | VWAP | 6 | -0.0322 | 2764 | 0.0901 | 1.0000 | no |
| BTCUSDT 1h | DMI | 6 | -0.0319 | 2764 | 0.0933 | 1.0000 | no |
| BTCUSDT 1h | MTM | 6 | -0.0318 | 2764 | 0.0945 | 1.0000 | no |
| BTCUSDT 1h | OBV | 6 | -0.0312 | 2764 | 0.1007 | 1.0000 | no |
| BTCUSDT 1h | SAR | 6 | -0.0280 | 2764 | 0.1408 | 1.0000 | no |
| BTCUSDT 1h | MACD | 6 | -0.0276 | 2764 | 0.1472 | 1.0000 | no |
| BTCUSDT 1h | StochRSI | 6 | +0.0252 | 2764 | 0.1855 | 1.0000 | no |
| BTCUSDT 1h | EMV | 6 | -0.0245 | 2764 | 0.1980 | 1.0000 | no |
| BTCUSDT 1h | RSI | 6 | +0.0219 | 2764 | 0.2497 | 1.0000 | no |
| BTCUSDT 1h | WR | 6 | +0.0174 | 2764 | 0.3607 | 1.0000 | no |
| BTCUSDT 1h | KDJ | 6 | +0.0172 | 2764 | 0.3648 | 1.0000 | no |
| BTCUSDT 1h | MFI | 6 | +0.0096 | 2764 | 0.6143 | 1.0000 | no |
| BTCUSDT 1h | BS.Vol | 6 | — | 0 | — | — | no |
| BTCUSDT 1h | Delta | 6 | — | 0 | — | — | no |
| BTCUSDT 1h | TakerRatio | 6 | — | 0 | — | — | no |
| BTCUSDT 1h | CVD | 6 | — | 0 | — | — | no |
| BTCUSDT 1h | CCI | 24 | -0.0650 | 691 | 0.0875 | 1.0000 | no |
| BTCUSDT 1h | SAR | 24 | +0.0603 | 691 | 0.1133 | 1.0000 | no |
| BTCUSDT 1h | StochRSI | 24 | -0.0549 | 691 | 0.1493 | 1.0000 | no |
| BTCUSDT 1h | OBV | 24 | +0.0540 | 691 | 0.1559 | 1.0000 | no |
| BTCUSDT 1h | VOL | 24 | +0.0539 | 691 | 0.1568 | 1.0000 | no |
| BTCUSDT 1h | EMV | 24 | +0.0455 | 691 | 0.2317 | 1.0000 | no |
| BTCUSDT 1h | BOLL | 24 | -0.0434 | 691 | 0.2543 | 1.0000 | no |
| BTCUSDT 1h | WR | 24 | -0.0408 | 691 | 0.2843 | 1.0000 | no |
| BTCUSDT 1h | MTM | 24 | +0.0304 | 691 | 0.4242 | 1.0000 | no |
| BTCUSDT 1h | MACD | 24 | +0.0240 | 691 | 0.5282 | 1.0000 | no |
| BTCUSDT 1h | RSI | 24 | -0.0234 | 691 | 0.5383 | 1.0000 | no |
| BTCUSDT 1h | DMI | 24 | +0.0222 | 691 | 0.5595 | 1.0000 | no |
| BTCUSDT 1h | technical (agregado) | 24 | -0.0189 | 691 | 0.6197 | 1.0000 | no |
| BTCUSDT 1h | MFI | 24 | -0.0170 | 691 | 0.6545 | 1.0000 | no |
| BTCUSDT 1h | SUPER | 24 | +0.0164 | 691 | 0.6660 | 1.0000 | no |
| BTCUSDT 1h | TRIX | 24 | +0.0158 | 691 | 0.6781 | 1.0000 | no |
| BTCUSDT 1h | VWAP | 24 | +0.0140 | 691 | 0.7138 | 1.0000 | no |
| BTCUSDT 1h | EMA | 24 | -0.0047 | 691 | 0.9019 | 1.0000 | no |
| BTCUSDT 1h | WMA | 24 | +0.0042 | 691 | 0.9130 | 1.0000 | no |
| BTCUSDT 1h | MA | 24 | -0.0007 | 691 | 0.9845 | 1.0000 | no |
| BTCUSDT 1h | KDJ | 24 | +0.0005 | 691 | 0.9885 | 1.0000 | no |
| BTCUSDT 1h | BS.Vol | 24 | — | 0 | — | — | no |
| BTCUSDT 1h | Delta | 24 | — | 0 | — | — | no |
| BTCUSDT 1h | TakerRatio | 24 | — | 0 | — | — | no |
| BTCUSDT 1h | CVD | 24 | — | 0 | — | — | no |
| BTCUSDT 4h | technical (agregado) | 1 | -0.0675 | 750 | 0.0647 | 1.0000 | no |
| BTCUSDT 4h | SAR | 1 | -0.0659 | 750 | 0.0712 | 1.0000 | no |
| BTCUSDT 4h | VWAP | 1 | -0.0597 | 750 | 0.1022 | 1.0000 | no |
| BTCUSDT 4h | EMA | 1 | -0.0583 | 750 | 0.1104 | 1.0000 | no |
| BTCUSDT 4h | MA | 1 | -0.0542 | 750 | 0.1380 | 1.0000 | no |
| BTCUSDT 4h | WMA | 1 | -0.0541 | 750 | 0.1387 | 1.0000 | no |
| BTCUSDT 4h | KDJ | 1 | +0.0499 | 750 | 0.1719 | 1.0000 | no |
| BTCUSDT 4h | SUPER | 1 | -0.0489 | 750 | 0.1807 | 1.0000 | no |
| BTCUSDT 4h | TRIX | 1 | -0.0486 | 750 | 0.1835 | 1.0000 | no |
| BTCUSDT 4h | WR | 1 | +0.0451 | 750 | 0.2174 | 1.0000 | no |
| BTCUSDT 4h | DMI | 1 | -0.0437 | 750 | 0.2316 | 1.0000 | no |
| BTCUSDT 4h | BOLL | 1 | +0.0433 | 750 | 0.2358 | 1.0000 | no |
| BTCUSDT 4h | MTM | 1 | -0.0377 | 750 | 0.3027 | 1.0000 | no |
| BTCUSDT 4h | OBV | 1 | -0.0364 | 750 | 0.3192 | 1.0000 | no |
| BTCUSDT 4h | MFI | 1 | -0.0339 | 750 | 0.3533 | 1.0000 | no |
| BTCUSDT 4h | VOL | 1 | -0.0289 | 750 | 0.4283 | 1.0000 | no |
| BTCUSDT 4h | MACD | 1 | -0.0264 | 750 | 0.4693 | 1.0000 | no |
| BTCUSDT 4h | EMV | 1 | -0.0219 | 750 | 0.5487 | 1.0000 | no |
| BTCUSDT 4h | RSI | 1 | -0.0114 | 750 | 0.7551 | 1.0000 | no |
| BTCUSDT 4h | CCI | 1 | +0.0100 | 750 | 0.7834 | 1.0000 | no |
| BTCUSDT 4h | StochRSI | 1 | -0.0002 | 750 | 0.9958 | 1.0000 | no |
| BTCUSDT 4h | BS.Vol | 1 | — | 0 | — | — | no |
| BTCUSDT 4h | Delta | 1 | — | 0 | — | — | no |
| BTCUSDT 4h | TakerRatio | 1 | — | 0 | — | — | no |
| BTCUSDT 4h | CVD | 1 | — | 0 | — | — | no |
| BTCUSDT 4h | EMA | 6 | -0.1814 | 125 | 0.0434 | 1.0000 | no |
| BTCUSDT 4h | MA | 6 | -0.1795 | 125 | 0.0456 | 1.0000 | no |
| BTCUSDT 4h | SAR | 6 | -0.1248 | 125 | 0.1645 | 1.0000 | no |
| BTCUSDT 4h | technical (agregado) | 6 | -0.1194 | 125 | 0.1838 | 1.0000 | no |
| BTCUSDT 4h | VOL | 6 | -0.1154 | 125 | 0.1989 | 1.0000 | no |
| BTCUSDT 4h | BOLL | 6 | +0.1134 | 125 | 0.2067 | 1.0000 | no |
| BTCUSDT 4h | SUPER | 6 | -0.1109 | 125 | 0.2170 | 1.0000 | no |
| BTCUSDT 4h | CCI | 6 | +0.1058 | 125 | 0.2386 | 1.0000 | no |
| BTCUSDT 4h | EMV | 6 | -0.1042 | 125 | 0.2458 | 1.0000 | no |
| BTCUSDT 4h | WMA | 6 | -0.1032 | 125 | 0.2505 | 1.0000 | no |
| BTCUSDT 4h | DMI | 6 | -0.0945 | 125 | 0.2929 | 1.0000 | no |
| BTCUSDT 4h | MACD | 6 | -0.0929 | 125 | 0.3009 | 1.0000 | no |
| BTCUSDT 4h | MTM | 6 | -0.0815 | 125 | 0.3641 | 1.0000 | no |
| BTCUSDT 4h | TRIX | 6 | -0.0620 | 125 | 0.4900 | 1.0000 | no |
| BTCUSDT 4h | WR | 6 | +0.0480 | 125 | 0.5933 | 1.0000 | no |
| BTCUSDT 4h | MFI | 6 | -0.0453 | 125 | 0.6138 | 1.0000 | no |
| BTCUSDT 4h | KDJ | 6 | -0.0251 | 125 | 0.7800 | 1.0000 | no |
| BTCUSDT 4h | VWAP | 6 | +0.0181 | 125 | 0.8400 | 1.0000 | no |
| BTCUSDT 4h | StochRSI | 6 | +0.0176 | 125 | 0.8444 | 1.0000 | no |
| BTCUSDT 4h | OBV | 6 | -0.0176 | 125 | 0.8448 | 1.0000 | no |
| BTCUSDT 4h | RSI | 6 | +0.0064 | 125 | 0.9430 | 1.0000 | no |
| BTCUSDT 4h | BS.Vol | 6 | — | 0 | — | — | no |
| BTCUSDT 4h | Delta | 6 | — | 0 | — | — | no |
| BTCUSDT 4h | TakerRatio | 6 | — | 0 | — | — | no |
| BTCUSDT 4h | CVD | 6 | — | 0 | — | — | no |
| BTCUSDT 4h | MA | 24 | -0.4995 | 31 | 0.0062 | 0.9517 | no |
| BTCUSDT 4h | WMA | 24 | -0.3972 | 31 | 0.0296 | 1.0000 | no |
| BTCUSDT 4h | VOL | 24 | -0.3091 | 31 | 0.0904 | 1.0000 | no |
| BTCUSDT 4h | BOLL | 24 | +0.2928 | 31 | 0.1087 | 1.0000 | no |
| BTCUSDT 4h | EMA | 24 | -0.2911 | 31 | 0.1109 | 1.0000 | no |
| BTCUSDT 4h | MACD | 24 | -0.2612 | 31 | 0.1526 | 1.0000 | no |
| BTCUSDT 4h | WR | 24 | +0.2604 | 31 | 0.1537 | 1.0000 | no |
| BTCUSDT 4h | CCI | 24 | +0.2431 | 31 | 0.1831 | 1.0000 | no |
| BTCUSDT 4h | DMI | 24 | -0.2218 | 31 | 0.2245 | 1.0000 | no |
| BTCUSDT 4h | technical (agregado) | 24 | -0.2185 | 31 | 0.2313 | 1.0000 | no |
| BTCUSDT 4h | VWAP | 24 | -0.2113 | 31 | 0.2471 | 1.0000 | no |
| BTCUSDT 4h | EMV | 24 | -0.2107 | 31 | 0.2485 | 1.0000 | no |
| BTCUSDT 4h | TRIX | 24 | -0.2053 | 31 | 0.2607 | 1.0000 | no |
| BTCUSDT 4h | SUPER | 24 | -0.2029 | 31 | 0.2664 | 1.0000 | no |
| BTCUSDT 4h | SAR | 24 | -0.2021 | 31 | 0.2684 | 1.0000 | no |
| BTCUSDT 4h | OBV | 24 | -0.1363 | 31 | 0.4552 | 1.0000 | no |
| BTCUSDT 4h | KDJ | 24 | -0.1309 | 31 | 0.4732 | 1.0000 | no |
| BTCUSDT 4h | RSI | 24 | +0.1041 | 31 | 0.5686 | 1.0000 | no |
| BTCUSDT 4h | MFI | 24 | -0.1032 | 31 | 0.5717 | 1.0000 | no |
| BTCUSDT 4h | MTM | 24 | -0.0987 | 31 | 0.5888 | 1.0000 | no |
| BTCUSDT 4h | StochRSI | 24 | +0.0458 | 31 | 0.8019 | 1.0000 | no |
| BTCUSDT 4h | BS.Vol | 24 | — | 0 | — | — | no |
| BTCUSDT 4h | Delta | 24 | — | 0 | — | — | no |
| BTCUSDT 4h | TakerRatio | 24 | — | 0 | — | — | no |
| BTCUSDT 4h | CVD | 24 | — | 0 | — | — | no |
| ETHUSDT 1h | WR | 1 | +0.0388 | 16582 | 0.0000 | 0.0001 | sí |
| ETHUSDT 1h | WMA | 1 | -0.0371 | 16582 | 0.0000 | 0.0003 | sí |
| ETHUSDT 1h | VWAP | 1 | -0.0364 | 16582 | 0.0000 | 0.0005 | sí |
| ETHUSDT 1h | BOLL | 1 | +0.0358 | 16582 | 0.0000 | 0.0007 | sí |
| ETHUSDT 1h | MA | 1 | -0.0349 | 16582 | 0.0000 | 0.0013 | sí |
| ETHUSDT 1h | EMA | 1 | -0.0337 | 16582 | 0.0000 | 0.0025 | sí |
| ETHUSDT 1h | KDJ | 1 | +0.0284 | 16582 | 0.0003 | 0.0438 | sí |
| ETHUSDT 1h | DMI | 1 | -0.0284 | 16582 | 0.0003 | 0.0444 | sí |
| ETHUSDT 1h | MACD | 1 | -0.0280 | 16582 | 0.0003 | 0.0532 | no |
| ETHUSDT 1h | TRIX | 1 | -0.0280 | 16582 | 0.0003 | 0.0536 | no |
| ETHUSDT 1h | RSI | 1 | +0.0269 | 16582 | 0.0005 | 0.0905 | no |
| ETHUSDT 1h | MTM | 1 | -0.0239 | 16582 | 0.0020 | 0.3229 | no |
| ETHUSDT 1h | OBV | 1 | -0.0227 | 16582 | 0.0035 | 0.5542 | no |
| ETHUSDT 1h | StochRSI | 1 | +0.0226 | 16582 | 0.0036 | 0.5666 | no |
| ETHUSDT 1h | SUPER | 1 | -0.0219 | 16582 | 0.0047 | 0.7340 | no |
| ETHUSDT 1h | CCI | 1 | +0.0217 | 16582 | 0.0053 | 0.8171 | no |
| ETHUSDT 1h | EMV | 1 | -0.0204 | 16582 | 0.0086 | 1.0000 | no |
| ETHUSDT 1h | technical (agregado) | 1 | -0.0161 | 16582 | 0.0382 | 1.0000 | no |
| ETHUSDT 1h | VOL | 1 | -0.0161 | 16582 | 0.0388 | 1.0000 | no |
| ETHUSDT 1h | SAR | 1 | -0.0129 | 16582 | 0.0964 | 1.0000 | no |
| ETHUSDT 1h | MFI | 1 | +0.0105 | 16582 | 0.1771 | 1.0000 | no |
| ETHUSDT 1h | BS.Vol | 1 | — | 0 | — | — | no |
| ETHUSDT 1h | Delta | 1 | — | 0 | — | — | no |
| ETHUSDT 1h | TakerRatio | 1 | — | 0 | — | — | no |
| ETHUSDT 1h | CVD | 1 | — | 0 | — | — | no |
| ETHUSDT 1h | TRIX | 6 | -0.0504 | 2763 | 0.0081 | 1.0000 | no |
| ETHUSDT 1h | EMA | 6 | -0.0503 | 2763 | 0.0082 | 1.0000 | no |
| ETHUSDT 1h | WMA | 6 | -0.0497 | 2763 | 0.0090 | 1.0000 | no |
| ETHUSDT 1h | MA | 6 | -0.0462 | 2763 | 0.0152 | 1.0000 | no |
| ETHUSDT 1h | SUPER | 6 | -0.0418 | 2763 | 0.0279 | 1.0000 | no |
| ETHUSDT 1h | VWAP | 6 | -0.0392 | 2763 | 0.0391 | 1.0000 | no |
| ETHUSDT 1h | DMI | 6 | -0.0356 | 2763 | 0.0613 | 1.0000 | no |
| ETHUSDT 1h | BOLL | 6 | +0.0336 | 2763 | 0.0778 | 1.0000 | no |
| ETHUSDT 1h | OBV | 6 | -0.0298 | 2763 | 0.1179 | 1.0000 | no |
| ETHUSDT 1h | technical (agregado) | 6 | -0.0253 | 2763 | 0.1828 | 1.0000 | no |
| ETHUSDT 1h | CCI | 6 | +0.0247 | 2763 | 0.1949 | 1.0000 | no |
| ETHUSDT 1h | VOL | 6 | -0.0224 | 2763 | 0.2390 | 1.0000 | no |
| ETHUSDT 1h | MFI | 6 | -0.0221 | 2763 | 0.2449 | 1.0000 | no |
| ETHUSDT 1h | MACD | 6 | -0.0216 | 2763 | 0.2569 | 1.0000 | no |
| ETHUSDT 1h | MTM | 6 | -0.0150 | 2763 | 0.4292 | 1.0000 | no |
| ETHUSDT 1h | SAR | 6 | -0.0139 | 2763 | 0.4661 | 1.0000 | no |
| ETHUSDT 1h | WR | 6 | +0.0136 | 2763 | 0.4760 | 1.0000 | no |
| ETHUSDT 1h | KDJ | 6 | +0.0090 | 2763 | 0.6359 | 1.0000 | no |
| ETHUSDT 1h | StochRSI | 6 | -0.0077 | 2763 | 0.6840 | 1.0000 | no |
| ETHUSDT 1h | EMV | 6 | +0.0050 | 2763 | 0.7924 | 1.0000 | no |
| ETHUSDT 1h | RSI | 6 | -0.0026 | 2763 | 0.8934 | 1.0000 | no |
| ETHUSDT 1h | BS.Vol | 6 | — | 0 | — | — | no |
| ETHUSDT 1h | Delta | 6 | — | 0 | — | — | no |
| ETHUSDT 1h | TakerRatio | 6 | — | 0 | — | — | no |
| ETHUSDT 1h | CVD | 6 | — | 0 | — | — | no |
| ETHUSDT 1h | MA | 24 | -0.0700 | 690 | 0.0663 | 1.0000 | no |
| ETHUSDT 1h | EMA | 24 | -0.0599 | 690 | 0.1156 | 1.0000 | no |
| ETHUSDT 1h | TRIX | 24 | -0.0559 | 690 | 0.1422 | 1.0000 | no |
| ETHUSDT 1h | MFI | 24 | -0.0534 | 690 | 0.1609 | 1.0000 | no |
| ETHUSDT 1h | technical (agregado) | 24 | -0.0516 | 690 | 0.1754 | 1.0000 | no |
| ETHUSDT 1h | SUPER | 24 | -0.0464 | 690 | 0.2232 | 1.0000 | no |
| ETHUSDT 1h | BOLL | 24 | +0.0448 | 690 | 0.2400 | 1.0000 | no |
| ETHUSDT 1h | OBV | 24 | -0.0428 | 690 | 0.2611 | 1.0000 | no |
| ETHUSDT 1h | WR | 24 | -0.0415 | 690 | 0.2766 | 1.0000 | no |
| ETHUSDT 1h | MACD | 24 | -0.0379 | 690 | 0.3197 | 1.0000 | no |
| ETHUSDT 1h | WMA | 24 | -0.0375 | 690 | 0.3249 | 1.0000 | no |
| ETHUSDT 1h | VWAP | 24 | -0.0331 | 690 | 0.3849 | 1.0000 | no |
| ETHUSDT 1h | DMI | 24 | -0.0312 | 690 | 0.4134 | 1.0000 | no |
| ETHUSDT 1h | KDJ | 24 | +0.0272 | 690 | 0.4759 | 1.0000 | no |
| ETHUSDT 1h | EMV | 24 | -0.0261 | 690 | 0.4929 | 1.0000 | no |
| ETHUSDT 1h | SAR | 24 | -0.0241 | 690 | 0.5268 | 1.0000 | no |
| ETHUSDT 1h | VOL | 24 | -0.0225 | 690 | 0.5555 | 1.0000 | no |
| ETHUSDT 1h | StochRSI | 24 | -0.0146 | 690 | 0.7012 | 1.0000 | no |
| ETHUSDT 1h | RSI | 24 | -0.0142 | 690 | 0.7088 | 1.0000 | no |
| ETHUSDT 1h | CCI | 24 | -0.0058 | 690 | 0.8782 | 1.0000 | no |
| ETHUSDT 1h | MTM | 24 | +0.0021 | 690 | 0.9561 | 1.0000 | no |
| ETHUSDT 1h | BS.Vol | 24 | — | 0 | — | — | no |
| ETHUSDT 1h | Delta | 24 | — | 0 | — | — | no |
| ETHUSDT 1h | TakerRatio | 24 | — | 0 | — | — | no |
| ETHUSDT 1h | CVD | 24 | — | 0 | — | — | no |
