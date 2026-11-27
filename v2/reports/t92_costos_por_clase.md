# T92 — Backtest de prueba por clase con costos propios

> Series sintéticas de T90 y estrategia de prueba: valida la mecánica de costos, no dice nada de rentabilidad.

| Instrumento | Modelo | Operaciones | Bruto | Comisiones | Deslizamiento | Financiación | Dividendos | Roll | Neto |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| equity.test.ACME | equity_v1 | 2 | 1,727.86 | 4.00 | 113.27 | 0.00 | 86.00 | 0.00 | 1,696.59 |
| fx.test.EURUSD | fx_v1 | 1 | 195.62 | 0.00 | 38.75 | 0.50 | 0.00 | 0.00 | 156.37 |
| future.test.CLX | futures_v1 | 2 | 2,035.85 | 9.00 | 101.67 | 0.00 | 0.00 | 71.91 | 1,853.27 |

## ACME (equity, 1d)

- Datos: fixture T90 (SINTÉTICA, no son datos de mercado); modo SIMULADO.
- Modelo `equity_v1` (huella `4886b450b3eb15f7`), multiplicador 1.
- Anualización: — velas/año (sin anualizar: el calendario 'XNYS' necesita `exchange_calendars` (extra `calendars`: pip install -e .[calendars]). No se adivinan festivos.).
- Salidas: {'end': 1, 'tp': 1}; empalmes: 0; eventos: splits 1, dividendos 1; órdenes que esperaron al mercado abierto: 0.

Supuestos (sin verificar en la fuente):
- `commission_per_share`: supuesto: tarifa fija pública de un intermediario minorista de EE. UU. (0,005 USD/acción), no verificada en la fuente en T92 (no hay intermediario elegido: T103)
- `commission_min`: supuesto: mínimo por orden de esa misma tarifa (1 USD)
- `commission_max_frac`: supuesto: máximo del 1 % del valor negociado de esa tarifa
- `slippage.spread_bps`: supuesto: diferencial típico de un instrumento líquido de la clase; sustituir por el medido (T97/T98/T99)
- `slippage.liquidity_notional`: supuesto: nocional negociado por vela cuando la fuente no declara volumen real (FX, índices)
- `shortable`: supuesto: disponible para préstamo; la disponibilidad real es por valor y por día (sin fuente gratuita, T88)
- `borrow_rate_annual`: supuesto: 0,25 % anual de un valor de préstamo general; los difíciles de prestar pagan mucho más
- `borrow_day_count`: supuesto: base 360 de la convención del préstamo de valores en USD
- `dividend_withholding`: supuesto: sin retención (depende del país del inversor)

## EURUSD (fx, 1h)

- Datos: fixture T90 (SINTÉTICA, no son datos de mercado); modo SIMULADO.
- Modelo `fx_v1` (huella `aab65ce0f0cdecd7`), multiplicador 1.
- Anualización: — velas/año (sin anualizar: el calendario '24/5' necesita `exchange_calendars` (extra `calendars`: pip install -e .[calendars]). No se adivinan festivos.).
- Salidas: {'end': 1}; empalmes: 0; eventos: splits 0, dividendos 0; órdenes que esperaron al mercado abierto: 0.

Supuestos (sin verificar en la fuente):
- `regulation`: supuesto: régimen minorista europeo (ESMA) hasta elegir intermediario
- `commission_per_million`: supuesto: cuenta de solo diferencial, sin comisión aparte
- `slippage.spread_bps`: supuesto: diferencial típico de un instrumento líquido de la clase; sustituir por el medido (T97/T98/T99)
- `slippage.liquidity_notional`: supuesto: nocional negociado por vela cuando la fuente no declara volumen real (FX, índices)
- `spread_bps_by_session`: supuesto: diferencial de un par mayor por franja (UTC); el rollover es la hora más cara
- `rate_base_annual`: supuesto: 0; el tipo real de la divisa base viene de T98 (BCE/FRED)
- `rate_quote_annual`: supuesto: 0; el tipo real de la divisa cotizada viene de T98
- `swap_markup_annual`: supuesto: margen del intermediario sobre el diferencial (0,5 %)
- `swap_day_count`: supuesto: base 365

## CLX (future, 1d)

- Datos: fixture T90 (SINTÉTICA, no son datos de mercado); modo SIMULADO.
- Modelo `futures_v1` (huella `d5157b7ea3b567da`), multiplicador 1000.
- Anualización: — velas/año (sin anualizar: el calendario 'CMES' necesita `exchange_calendars` (extra `calendars`: pip install -e .[calendars]). No se adivinan festivos.).
- Salidas: {'end': 1, 'tp': 1}; empalmes: 1; eventos: splits 0, dividendos 0; órdenes que esperaron al mercado abierto: 0.

Supuestos (sin verificar en la fuente):
- `commission_per_contract`: supuesto: 2,25 USD por contrato y lado (intermediario + mercado + cámara) de un futuro estándar de CME; no verificada en la fuente en T92
- `commission_frac`: supuesto: 0 (solo plazas que cobran sobre nocional la usan)
- `slippage.spread_bps`: supuesto: diferencial típico de un instrumento líquido de la clase; sustituir por el medido (T97/T98/T99)
- `slippage.liquidity_notional`: supuesto: nocional negociado por vela cuando la fuente no declara volumen real (FX, índices)
- `spread_ticks`: supuesto: diferencial de 1 tick en un contrato líquido
- `initial_margin_frac`: supuesto: 10 % del nocional; el real es por contrato y lo publica la cámara (SPAN)
- `maintenance_margin_frac`: supuesto: 9 % del nocional (90 % del inicial, la proporción habitual en CME)
- `roll_days_before_expiry`: supuesto: roll 5 días antes del vencimiento (antes del aviso de entrega)
