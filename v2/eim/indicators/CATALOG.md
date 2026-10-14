# Catálogo de indicadores técnicos (T34)

Fecha de la revisión: **2026-10-13**. Binance **no sirve indicadores calculados por API**: todos se calculan
localmente (`eim.indicators`) a partir de sus velas (`/fapi/v1/klines`) y series propias.

## Fuentes de la lista (y su grado de verificación)

| Grupo | Fuente | Verificación |
|---|---|---|
| A — Gráfico de futuros (18) | Binance Square, *“18 main indicators of Binance. Complete guide”* (binance.com/en/square/post/18387404490937): MA, EMA, BOLL, SAR, AVL, VOL, MACD, RSI, KDJ, OBV, WR, StochRSI, O.I., LS Acco, LS Posit, LS Ratio, BS. Vol, Basis | Publicación de la comunidad en el dominio de Binance; no es documentación oficial y no da parámetros |
| B — Resto del gráfico “Original” | WMA, VWAP, TRIX, SUPER, MFI, CCI, DMI, MTM, EMV | Lista del menú de indicadores del gráfico “Original” de Binance tal como la conocía el autor. **No se pudo confirmar en la interfaz**: el 2026-10-13, binance.com/es/futures/BTCUSDT redirigió a accounts.binance.com y devolvió 400 (CloudFront) en el navegador integrado |
| C — Datos propios | Campos de klines (`taker_buy_v` = campo 9, `trades` = campo 8), klines de índice/marca | Formato de `/fapi/v1/klines` y del stream `kline` (`V`, `n`) |

**Parámetros por defecto:** los de las funciones son los habituales del gráfico “Original” (MA/EMA/WMA 7-25-99,
RSI 6-12-24, VOL 5-10, KDJ 9-3-3, BOLL 20-2, SAR 0.02/0.02/0.2, MACD 12-26-9). Los de DMI, CCI, MTM, EMV, TRIX,
SUPER y StochRSI son convenciones estándar **pendientes de confirmar** en la interfaz (todos son parámetros
de la función, no constantes). Pendiente en `PLAN/BACKLOG.md`.

## Catálogo

Estado: ☑ implementado con función + test de referencia + test de truncado; ✗ descartado (motivo).

| Id | Grupo | Familia | Función | Parámetros por defecto | Fuente de datos | Estado |
|---|---|---|---|---|---|---|
| `MA` | A | tendencia | `trend.ma` | 7, 25, 99 (SMA) | velas: close | ☑ |
| `EMA` | A | tendencia | `trend.ema_lines` | 7, 25, 99; siembra en el primer dato | velas: close | ☑ |
| `WMA` | B | tendencia | `trend.wma_lines` | 7, 25, 99 | velas: close | ☑ |
| `SAR` | A | tendencia | `trend.sar` | inicio 0.02, paso 0.02, máx 0.2 | velas: high, low | ☑ |
| `SUPER` | B | tendencia | `trend.supertrend` | ATR 10, factor 3 | velas: HLC | ☑ |
| `DMI` | B | tendencia | `trend.dmi` | DI 14, ADX 6 (PDI, MDI, ADX, ADXR) | velas: HLC | ☑ |
| `MACD` | A | momentum | `momentum.macd` | 12, 26, 9 (DIF, DEA, hist = DIF−DEA) | velas: close | ☑ |
| `RSI` | A | momentum | `momentum.rsi_lines` | 6, 12, 24 (Wilder, siembra SMA) | velas: close | ☑ |
| `KDJ` | A | momentum | `momentum.kdj` | 9, 3, 3 (K, D sembrados en 50) | velas: HLC | ☑ |
| `StochRSI` | A | momentum | `momentum.stochrsi` | RSI 14, estocástico 14, K 3, D 3 | velas: close | ☑ |
| `WR` | A | momentum | `momentum.wr` | 14 (escala −100..0) | velas: HLC | ☑ |
| `CCI` | B | momentum | `momentum.cci` | 14 | velas: HLC | ☑ |
| `MTM` | B | momentum | `momentum.mtm` | 12, MA 6 | velas: close | ☑ |
| `TRIX` | B | momentum | `momentum.trix` | 12, MA 9 | velas: close | ☑ |
| `BOLL` | A | volatilidad | `volatility.boll` | 20, 2σ (poblacional) | velas: close | ☑ |
| `ATR` | — | volatilidad | `volatility.atr` | 14 (Wilder); base de SUPER, usado por FRM/levels | velas: HLC | ☑ |
| `VOL` | A | volumen | `volume.vol` | MA 5, 10 | velas: volume | ☑ |
| `OBV` | A | volumen | `volume.obv` | MAOBV 30; acumulado desde el inicio de la serie | velas: close, volume | ☑ |
| `MFI` | B | volumen | `volume.mfi` | 14 | velas: HLCV | ☑ |
| `EMV` | B | volumen | `volume.emv` | 14, MA 9 (fórmula de gráficos chinos) | velas: HLV | ☑ |
| `VWAP` | B | volumen | `volume.vwap` | reinicio diario UTC; precio típico | velas: HLCV + t | ☑ |
| `AVL` | A | volumen | `volume.avl` | precio medio Σ(TP·V)/ΣV desde la primera vela cargada | velas: HLCV | ☑ |
| `BS.Vol` | A | flujo | `flow.taker_volume` | compra/venta agresora | velas: `taker_buy_v` | ☑ |
| `TakerRatio` | C | flujo | `flow.taker_ratio` | n = 1 | velas: `taker_buy_v` | ☑ |
| `Delta` | C | flujo | `flow.delta` | — | velas: `taker_buy_v` | ☑ |
| `CVD` | C | flujo | `flow.cvd` | acumulado desde el inicio de la serie | velas: `taker_buy_v` | ☑ |
| `TradeSize` | C | flujo | `flow.avg_trade_size` | MA 20 | velas: `trades` | ☑ |
| `Basis` | A | flujo | `flow.basis` | (precio − índice)/índice·100 | close + klines de índice (ingesta pendiente, BACKLOG); Binance también sirve `/futures/data/basis` (~30 días, ya en T21) | ☑ |
| O.I. | A | flujo | — | — | `/futures/data/openInterestHist` (T21) | ✗ serie directa del proveedor, no se calcula desde velas; ya la consume el agente `derivatives` |
| LS Acco | A | flujo | — | — | `globalLongShortAccountRatio` (T21) | ✗ serie directa del proveedor (T21) |
| LS Posit | A | flujo | — | — | `topLongShortPositionRatio` | ✗ serie directa del proveedor; ingesta no implementada → BACKLOG |
| LS Ratio | A | flujo | — | — | `topLongShortAccountRatio` | ✗ serie directa del proveedor; ingesta no implementada → BACKLOG |
| Indicadores de la pestaña TradingView | — | — | — | — | — | ✗ fuera de alcance (T34): propietarios de TradingView |

## Convenciones (ver `_core.py`)

- Funciones puras sobre arreglos numpy; salida del mismo largo, NaN durante el calentamiento.
- **Sin look-ahead:** el valor en `t` usa solo datos ≤ `t` (test de truncado para cada indicador).
- Ventana > datos → todo NaN. NaN en la entrada → NaN en ese punto; los filtros recursivos conservan el estado.
- Divisiones por cero (rango 0, volumen 0, sin ventas agresoras) → NaN. RSI sin movimiento → 50.
- Acumulativos (OBV, CVD, AVL): su nivel depende del inicio de la serie; comparar variaciones, no niveles.
- Las ventanas móviles están vectorizadas (`sliding_window_view`); los filtros recursivos (EMA, Wilder, SAR,
  SuperTrend, KDJ) son bucles O(n) porque su definición es secuencial.

## Validación

`tests/indicators/test_reference.py` compara cada indicador con `tests/fixtures/indicators/reference.json`
(tolerancia rtol = atol = 1e-9) y comprueba la EMA contra el golden heredado de F7 y contra pandas.
**Límite:** las fixtures se generaron antes del veredicto de T33 (que eligió TA-Lib + pandas-ta-classic). Por eso las fixtures salen de una implementación ingenua propia (`tests/indicators/_reference.py`):
detecta errores de vectorización, ventanas y NaN, pero **no** errores de definición compartidos con la biblioteca.
Falta contrastarlas con esas librerías (BACKLOG). Las entradas de flujo
(`taker_buy_v`, `trades`, índice) de las fixtures son sintéticas porque el CSV de referencia no las trae.
