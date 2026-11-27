# T88 — Auditoría de repositorios y de proveedores de datos (multiactivo)

Fecha: **2026-11-20** · Fase 17 · Formato de T04 y T33 · **Punto de decisión humana**: la lista
cerrada está en `PLAN/notas/T88_decisiones.md` y **no vale sin el visto bueno del usuario**.

Qué hace esta tarea: verificar **en la fuente** lo que la investigación del usuario (T87 §5)
*declaraba* sobre licencias, mantenimiento, pruebas y compatibilidad, y medir qué hay realmente
disponible. Los veredictos ya dados en `PLAN/notas/T04_auditoria.md` y `T33_auditoria.md` no se
repiten; donde esta auditoría los corrige o los cierra, se dice (§4.4, §5.5).

**Método.** Metadatos por la API de GitHub y de PyPI, clones superficiales de **solo lectura y
aislados fuera del proyecto** (`C:\t88clones\`, material desechable), lectura de documentación,
páginas de precios y términos de uso oficiales, y consulta directa de los endpoints públicos de
Binance. **No se instaló ni se ejecutó código de terceros. No se abrió ninguna cuenta, no se pidió
ninguna clave y no se contrató nada. No se sorteó ninguna verificación anti-bot.** Entorno de
referencia: CPython 3.12.10 (`requires-python >=3.11`), numpy 2.4.4, pandas 3.0.2, duckdb 1.5.6.

**Limitación declarada.** El análisis de código es **por patrones y por metadatos**, no línea a
línea, y no cubre dependencias transitivas. Lo que no se pudo confirmar en la fuente aparece como
**no verificado** (§3.6, §5.6, §6), nunca rellenado de memoria.

## 1. 🚩 Alertas (leer primero)

1. **El universo TradFi de Binance no es `XAUUSDT` y cuatro cosas más: son 246 perpetuos vivos**
   (209 acciones y ETF de EE. UU., 15 de Hong Kong, 8 de materias primas, 8 de Corea, 3 pre-OPV, 2
   de China, 1 de FX), con un tipo de contrato propio, `TRADIFI_PERPETUAL`, que `eim/data/` no
   conoce. Mueven 39 250 M USDT en 24 h, casi tanto como los 567 perpetuos de cripto. Corrige el
   supuesto de T87 §4. → §3.1
2. **Ninguno de esos 246 llega a un año de histórico** (mediana **134 días**; solo 52 pasan de 180;
   el más antiguo, `XAUUSDT`, 344). El escáner puede **observar** este universo, pero **no se puede
   validar nada en él** con el marco de T49/T95 sin recalcular la potencia. Es el límite que manda
   en toda la fase 17. → §3.2
3. **El perpetuo TradFi no cierra, pero su subyacente sí, y el precio se sigue formando sin él.**
   Cero huecos y cero velas vacías durante las ~48 h de cierre semanal, con la liquidez al 6-28 % y
   un recorrido medio de 0,7-2,6 %; el salto en la primera hora tras reabrir llega a un p90 de
   **1,63 %** en `CLUSDT`. El registro de instrumentos necesita **dos** calendarios por
   instrumento: el del contrato (24/7) y el del subyacente (`/fapi/v1/tradingSchedule`, 6
   mercados). → §3.3
4. **Las comisiones de los TradFi no se pudieron verificar** y **no se asume que sean las de
   cripto**. Sin cifra con fuente, T92 no puede modelar el costo de esta clase, y sin costo no hay
   veredicto de rentabilidad. Tampoco se verificaron los escalones de margen (exigen clave). → §3.4
5. **`yfinance` es dependencia de producción de EIM hoy y no tiene licencia de datos.** Está en
   `dependencies` de `v2/pyproject.toml`, instalado (v1.6.0) y en uso en
   `eim/data/providers/multi_asset.py`. Funciona, pero los Términos de Yahoo prohíben literalmente
   la recolección automatizada y crear archivos o bases de datos con su contenido. La Apache-2.0
   cubre el código, no los datos. → §5.1
6. **`Riskfolio-Lib` (BSD-3) arrastra `vectorbt` (Commons Clause) como dependencia obligatoria.**
   Instalarlo mete la Commons Clause en el entorno aunque su propia licencia sea limpia; una
   auditoría que solo mire su `LICENSE.txt` lo pasa por alto. → §4.2
7. **«OpenBB es Apache-2.0» es falso sin fijar versión.** La licencia del paquete cambió tres veces:
   MIT (3.x) → **AGPL-3.0-only** (4.2.0-4.7.2) → Apache-2.0 (solo desde 5.0.0, 2026-09-29).
   Cualquier copia anterior a esa fecha se tomó bajo AGPL. Además `eval()` en código de producción
   que **escribe módulos Python en disco**, 250 paquetes en el *lock*, y GitHub ya no reconoce su
   licencia (`NOASSERTION`). → §4.2, §4.3
8. **La alerta 3 de T04 queda aclarada, no empeorada.** `OpenBB-finance/OpenBB` sí redirige a
   `openbq-org`, pero es el **mismo repositorio trasladado** (id 323048702, creado 2020-12-20,
   75 595 estrellas conservadas, commits de mantenedores históricos): fusión o compra OpenBB +
   BrightQuery, no un typosquat. Sigue pendiente confirmar fuera de GitHub quién controla la cuenta
   de PyPI `openbb`. → §4.4
9. **La alerta 10 de T33 queda cerrada: los términos de Binance Vision ya no son borrador.**
   «Version 1.0, Last Updated: August 26, 2026», bajo **CC BY-NC-SA 4.0**, con el *backtesting*
   histórico personal permitido por escrito y **prohibida la ejecución en real y la distribución de
   señales**. EIM, en «solo análisis» (T145 D), está dentro; el día que haya dinero real, los datos
   de Vision no pueden estar en la cadena. → §5.5
10. **No existe fuente gratuita con histórico continuo de futuros y *roll* documentado**, ni tick o
    bid/ask intradía de FX gratis. Stooq da 11 460 sesiones de `CL.F` pero con volumen a 0 y sin
    metodología; los símbolos de Yahoo son el vencimiento más cercano, no una serie empalmada.
    T99 (materias primas y futuros) no es viable como clase todavía. → §5.1, §5.4
11. **El hueco abierto más importante: el ajuste por *splits* y dividendos.** Ningún proveedor de
    acciones documenta en sus páginas si la serie diaria viene ajustada ni si el ajuste es
    retroactivo. Hay que cerrarlo endpoint por endpoint antes de elegir proveedor (T97): sin eso,
    un backtest de acciones mide otra cosa. → §5.1, §5.6
12. **Nasdaq Data Link ha dejado de ser fuente gratuita** (el filtro «Free» devuelve un solo
    conjunto) y **Polygon.io ahora es Massive** (301 a `massive.com`): hay que revisar las
    menciones a ambos en el proyecto. → §5.1
13. **Lo único de nivel 2 limpio y gratis son las fuentes oficiales**: BCE, Frankfurter, FRED/ALFRED
    y US Treasury, todas verificadas respondiendo sin clave. FX y renta fija **en diario** dejan de
    depender de una compra; renta variable no. → §5.2, §5.3
14. **Cuatro de los repos clonados traen `AGENTS.md` o `CLAUDE.md` en la raíz**
    (`nautilus_trader`, `quickfix`, `questdb`, `pandas_market_calendars`). Se leyeron como datos y
    no se obedecieron; el contenido es legítimo. Se anota porque **clonar un repo de terceros
    dentro del árbol de un proyecto le inyecta un `CLAUDE.md` ajeno**: por eso los clones de esta
    auditoría viven fuera de `TRADINGBOT`. → §4.5
15. **La cuenta de papel de Interactive Brokers exige una cuenta real financiada**, y sin
    suscripciones da datos **retrasados 15-20 min** con **100 líneas simultáneas**. Para un escáner
    de cientos de instrumentos, las 100 líneas son el límite que manda. → §6

## 2. Resumen de veredictos

**Modos:** **A usar** (dependencia o código incorporado) · **B proceso aislado** (solo en un venv o
proceso separado, nunca importado en producción) · **C referencia** (leer ideas, no copiar) ·
**D descartar**.

| Candidato | Área | Veredicto | Cómo |
|---|---|---|---|
| `exchange_calendars` | Calendarios | **A usar** | Apache-2.0; autoridad de sesiones, con `start`/`end` explícitos |
| `pandas_market_calendars` | Calendarios | **A usar** | MIT + `NOTICE` Apache-2.0; solo para CME Globex y FOREX 24/5 |
| PyPortfolioOpt | Cartera | **A usar** | MIT; `==1.6.0` en T96 |
| Binance Vision | Datos (archivo) | **A usar** | CC BY-NC-SA 4.0; solo investigación personal sin producción |
| FRED / ALFRED | Macro, tipos, FX | **A usar** | Clave gratuita con atribución obligatoria; *vintages* desde 2006 |
| US Treasury | Renta fija | **A usar** | Curva par diaria sin clave desde 1990; reutilización sin restricción |
| BCE (tipos y Data Portal) | FX, curva euro | **A usar** | Uso libre citando al BCE; SDMX sin clave |
| Frankfurter | FX | **A usar** | Código MIT sobre datos del BCE; sin cuotas ni clave |
| Tiingo | Acciones, ETF | **A usar** (de pago) | 0-30 $/mes; uso interno y personal, sin redistribución |
| EODHD | Acciones, ETF, FX | **A usar** (de pago) | El único que **autoriza por escrito** almacenar en local |
| NautilusTrader | Motor, instrumentos | **B proceso aislado** | LGPL-3.0; 1.231.0 (cp312) sin modificar; la taxonomía, solo leída |
| Riskfolio-Lib | Riesgo de cartera | **B proceso aislado** | BSD-3 pero arrastra Commons Clause: fuera del venv vivo |
| Binance `fapi` | Cripto + TradFi | **B proceso aislado** | Ya en uso; términos de datos **no verificados** |
| Massive (ex Polygon) | Acciones, opciones | **B proceso aislado** | Gratis = EOD y 2 años; borrado obligatorio al cancelar |
| Twelve Data | Multi-bolsa | **B proceso aislado** | Nivel gratuito sin uso comercial; plazo de almacenamiento ilegible |
| Stooq | Multi-clase | **B proceso aislado** | Solo uso personal, sin redistribución, y **exige navegador** |
| LEAN | Motor | **C referencia** | Apache-2.0; C#/.NET con Python 3.11 embebido |
| Qlib | Datos y factores | **C referencia** | MIT; PyPI 0.9.7 sin los parches de seguridad; MLflow/Redis/Mongo |
| vectorbt | Barridos | **C referencia** | Commons Clause: no es OSI; el embudo de T93 con NumPy propio |
| ib_async | Ejecución (papel) | **C referencia** | BSD-2; exige TWS/Gateway Java; `main` parada 11,5 meses |
| CME DataMine | Futuros | **C referencia** | Única vía legítima a tick real; exige cuenta y licencia, precio no público |
| Alpha Vantage | Acciones, FX | **C referencia** | 25 peticiones/día; sin cláusula de almacenamiento |
| SimFin · Sharadar · Nasdaq Data Link · openexchangerates | Fundamentales, FX | **C referencia** | Licencias o precios no públicos |
| QuickFIX | Conectividad | **D descartar** | Licencia propia no OSI, sin ruedas cp312, y EIM no usa FIX |
| QuestDB | Almacén | **D descartar** | Apache-2.0 impecable, pero exige servidor Java; DuckDB ya sirve |
| OpenBB (meta-paquete) | Proveedores | **D descartar** | 250 paquetes, `eval()` que escribe código, tres licencias en tres años |
| yfinance / Yahoo | Acciones, índices | **D descartar** | Sin licencia de datos; Yahoo prohíbe la recolección automatizada |
| FMP | Acciones | **D descartar** | Prohíbe descargar y obliga a borrar la caché |
| exchangerate.host | FX | **D descartar** | 100 peticiones/mes y licencia no legible |
| Futuros continuos gratis · tick/bid-ask FX gratis | Futuros, FX | **No existe** | Ninguna fuente con *roll* documentado ni intradía gratuito |

## 3. Cobertura real de Binance (verificado en el endpoint, 2026-11-20)

Método: `GET /fapi/v1/exchangeInfo`, `/fapi/v1/fundingInfo`, `/fapi/v1/ticker/24hr`,
`/fapi/v1/tradingSchedule`, `/fapi/v1/constituents`, `/fapi/v1/premiumIndex` y `/fapi/v1/klines`,
consultados el **2026-11-20** (`serverTime` 2026-11-20T10:51:39Z; `tradingSchedule.updateTime`
2026-11-20T11:18:33Z). Sin clave: todos son públicos. Las respuestas quedaron en la carpeta
temporal de la sesión, fuera del repositorio y fuera de `v2/data/`.

### 3.1 Inventario
`exchangeInfo` devuelve **956 símbolos**: 705 `PERPETUAL`, **247 `TRADIFI_PERPETUAL`**,
2 `CURRENT_QUARTER` y 2 `NEXT_QUARTER`. En estado `TRADING`: **567 perpetuos de cripto** y
**246 perpetuos TradFi** (el 247.º está en `SETTLING`).

**Esto corrige el supuesto de T87 §4**, que daba por hecho que el universo TradFi de Binance era
poco más que `XAUUSDT`. Hay un tipo de contrato propio, `TRADIFI_PERPETUAL`, que `eim/data/` hoy no
conoce, y 246 instrumentos vivos.

| `underlyingType` | n | Volumen 24 h (USDT) | Mediana 24 h | Alta en Binance | Funding |
|---|---|---|---|---|---|
| EQUITY (acciones y ETF de EE. UU.) | 209 | 29 474 648 276 | 2 093 494 | 2026-01-28 … 2026-11-20 | 8 h (209) |
| COMMODITY | 8 | 7 997 165 618 | 239 277 787 | 2025-12-11 … 2026-04-01 | 4 h (8) |
| KR_EQUITY (Corea) | 8 | 1 499 743 615 | 2 318 600 | 2026-06-02 … 2026-08-14 | 4 h (8) |
| HK_EQUITY (Hong Kong) | 15 | 196 456 727 | 5 939 567 | 2026-07-17 … 2026-09-07 | 4 h (15) |
| CN_EQUITY (China) | 2 | 51 111 091 | 25 555 546 | 2026-08-18 … 2026-08-19 | 4 h (2) |
| PREMARKET (pre-OPV) | 3 | 30 872 329 | 797 803 | 2026-05-26 … 2026-09-23 | 8 h (3) |
| FX | 1 | 1 750 800 | 1 750 800 | 2026-09-21 | 8 h (1) |
| **Total TradFi** | **246** | **39 251 748 455** | **2 521 958** | | 8 h (213) · 4 h (33) |
| *(comparación)* perpetuos de cripto | 567 | 48 196 554 781 | 2 807 192 | 2019-09-08 … 2026-11-16 | — |

- **Materias primas (8):** `XAUUSDT` (oro), `XAGUSDT` (plata), `XPTUSDT` (platino), `XPDUSDT`
  (paladio), `CLUSDT` (WTI), `BZUSDT` (Brent), `NATGASUSDT` (gas natural), `COPPERUSDT` (cobre).
- **FX (1):** `USDBRLUSDT`. Un solo par, y no es un cruce mayor: **Binance no es una fuente de FX**.
- **Índices y ETF**, dentro de EQUITY: `SPYUSDT`, `QQQUSDT`, `IWMUSDT`, `SOXXUSDT`, `GDXUSDT`,
  `XLEUSDT`, `XBIUSDT`, `IGVUSDT`, `SMHUSDT`, `IBITUSDT`, `BITOUSDT`, `EWJUSDT`, `EWYUSDT`,
  `EWZUSDT`, `EWTUSDT`, `EIDOUSDT`, `KODEX200USDT`, entre otros.
  Hay **ETF apalancados e inversos**: `SOXLUSDT`, `SOXSUSDT`, `TQQQUSDT`, `SQQQUSDT`, `TZAUSDT`,
  `TMFUSDT`, `UVXYUSDT`, `TSLLUSDT`, `NVDLUSDT`, `CSOPSAMSUNG2LUSDT`, `CSOPSKHYNIX2LUSDT`. Su serie
  no es el subyacente: arrastra el reajuste diario y el decaimiento. Si entran, entran etiquetados.
  `SOXLUSDT` es, de hecho, el TradFi de mayor volumen (7 249 M USDT/24 h, más que `XAUUSDT`).
- **Pre-OPV (3):** `OPENAIUSDT`, `OURAUSDT`, `MOONSHOTUSDT` (`underlyingSubType` `Pre-IPO`). No hay
  mercado subyacente que los ancle. **Quedan fuera** del universo multiactivo.

### 3.2 Histórico disponible: el límite que manda
`onboardDate` de los 246 TradFi va del **2025-12-11** (`XAUUSDT`) al **2026-11-20** (hoy mismo).

| Días de histórico | mín | p25 | mediana | p75 | máx |
|---|---|---|---|---|---|
| TradFi (246) | 0 | 79 | **134** | 172 | **344** |

**Ninguno llega a un año.** Solo 52 de 246 pasan de 180 días. Los perpetuos de cripto, en
comparación, tienen mediana de 702 días y 493 de 567 pasan de 365.

Consecuencia directa para la fase 17: con una mediana de 4,4 meses no hay walk-forward con purga y
embargo que produzca un veredicto creíble sobre estos instrumentos (T95, T101), ni se puede
reutilizar el marco de T49 sin recalcular su potencia. El escáner puede **observar** este universo;
todavía no puede **validar** nada en él. La serie larga del subyacente (la acción real) no es
sustituto: el perpetuo tiene otro precio, otro horario y otro costo (§3.3–§3.5).

### 3.3 Horarios: el perpetuo no cierra, el subyacente sí
`GET /fapi/v1/tradingSchedule` publica **seis calendarios** (`marketSchedules`): `EQUITY`,
`COMMODITY`, `FX`, `HK_EQUITY`, `KR_EQUITY`, `CN_EQUITY`. Devuelve unas dos semanas de sesiones
(2026-11-11 → 2026-11-28 en la consulta de hoy) y **ignora el parámetro `symbol`**. Tipos de sesión
observados: `REGULAR`, `PRE_MARKET`, `AFTER_MARKET`, `OVERNIGHT` y `NO_TRADING`.

Patrón semanal medido hoy (UTC):

| Mercado | Sesiones | Cierre (`NO_TRADING`) |
|---|---|---|
| EQUITY (EE. UU.) | `OVERNIGHT` 01:00–09:00 · `PRE_MARKET` 09:00–14:30 · `REGULAR` 14:30–21:00 · `AFTER_MARKET` 21:00–01:00 | sáb 01:00 → lun 01:00 |
| COMMODITY | continuo | vie 22:00 → dom 23:00 |
| FX | continuo | vie 22:00 → dom 22:00 |
| HK_EQUITY | 01:30–04:00 y 05:00–08:00 | resto del día y fin de semana |
| KR_EQUITY | 00:00–06:20 | resto del día y fin de semana |
| CN_EQUITY | 01:30–03:30 y 05:00–06:57 | resto del día y fin de semana |

**Pero esas sesiones son las del subyacente, no las del contrato.** Verificado con velas de 1 h
(`/fapi/v1/klines`, 400 velas, 2026-11-03 20:00 → 2026-11-20 11:00): en `AAPLUSDT`, `XAUUSDT`,
`USDBRLUSDT` y `TENCENTUSDT` hay **cero huecos y cero velas con volumen 0**, también dentro de las
ventanas `NO_TRADING`. El sábado 2026-11-14, con el mercado de EE. UU. cerrado, `AAPLUSDT` negoció
entre 1 141 y 6 459 operaciones por hora.

Esto **invierte** el problema que T87 §2 (punto 4) anticipaba: no hay huecos de calendario que
confundir con falta de dato. Lo que hay es precio formándose sin subyacente. Medido sobre 1 500
velas de 1 h (9 cierres semanales por símbolo):

| Símbolo | Mercado | Recorrido medio en el cierre | Salto medio 1.ª hora tras reabrir | Salto p90 | Liquidez cierre/abierto |
|---|---|---|---|---|---|
| AAPLUSDT | EQUITY | 0,84 % | 0,07 % | 0,14 % | 0,14 |
| NVDAUSDT | EQUITY | 2,46 % | 0,46 % | 0,60 % | 0,09 |
| SPYUSDT | EQUITY | 0,71 % | 0,09 % | 0,12 % | 0,21 |
| QQQUSDT | EQUITY | 1,18 % | 0,20 % | 0,19 % | 0,18 |
| TSLAUSDT | EQUITY | 1,86 % | 0,30 % | 0,35 % | 0,10 |
| XAUUSDT | COMMODITY | 0,89 % | 0,21 % | 0,33 % | 0,09 |
| CLUSDT | COMMODITY | 2,58 % | 0,59 % | **1,63 %** | 0,11 |
| XAGUSDT | COMMODITY | 2,00 % | 0,42 % | 1,01 % | 0,06 |
| USDBRLUSDT | FX | 1,32 % | 0,29 % | 0,73 % | 0,28 |
| *BTCUSDT (control)* | *24/7* | *3,20 %* | *0,37 %* | *0,54 %* | *0,42* |

Lectura: durante las ~48 h en que el subyacente está cerrado el contrato **sigue moviéndose**
(0,7–2,6 % de recorrido) con la liquidez caída al **6–28 %** de la de mercado abierto. BTCUSDT, que
no tiene cierre, conserva el 42 % en la misma ventana del calendario: ese 42 % es el efecto fin de
semana puro, y la diferencia es el efecto del cierre. El salto al reabrir es modesto en media pero
tiene cola: el p90 de `CLUSDT` es 1,63 %, por encima de cualquier stop ajustado.

Implicación de diseño para T89: el registro de instrumentos necesita, por instrumento, **dos**
calendarios —el del **contrato** (24/7, sin huecos) y el del **subyacente** (`tradingSchedule`)—,
porque los agentes que suponen sesiones (`vwap`, `seasonality`, `technical`) y el riesgo (ventanas
de evento, stops) tienen que mirar el segundo. Y `find_gaps` del almacén sigue siendo correcto tal
cual para estos contratos: aquí un hueco sí es falta de dato.

### 3.4 Margen, costos y financiación
De `exchangeInfo`, idéntico en los 246 TradFi:

| Campo | Valor |
|---|---|
| `requiredMarginPercent` | 5,0000 % → apalancamiento nominal máximo ×20 |
| `maintMarginPercent` | 2,5000 % |
| `liquidationFee` | 1,5 % |
| `marketTakeBound` | 3 % (244 símbolos), 2 % (`XAUUSDT`), 1 % (1 símbolo) |
| `triggerProtect` | 3 % (`XAUUSDT` 2 %) |
| `orderTypes` | LIMIT, MARKET, STOP, STOP_MARKET, TAKE_PROFIT, TAKE_PROFIT_MARKET, TRAILING_STOP_MARKET |
| `timeInForce` | GTC, IOC, FOK, GTX, GTD |

Los perpetuos de cripto traen el mismo `requiredMarginPercent` 5 % (567 de 567), así que el techo
nominal coincide; los **escalones de margen por tamaño** (`/fapi/v1/leverageBracket`) exigen clave y
**no se verificaron**. El `liquidationFee` de 1,5 % entra en el modelo de T92.

Financiación: intervalo de **8 h en 213** símbolos y de **4 h en 33** (los 8 de materias primas y
los 25 de HK/KR/CN). Tope declarado en `fundingInfo` ±2 %. `premiumIndex` de `XAUUSDT` devolvió
`interestRate: 0.00000000`, frente al 0,01 % por 8 h habitual en cripto: el componente de tipo de
interés está anulado en este contrato.

**Comisiones: no verificadas.** No se pudo leer ninguna tabla de comisiones específica de TradFi; la
página de parámetros de Binance se renderiza por JavaScript y devolvió «No Data». **No se asume que
sean las de cripto** (VIP 0: maker 0,02 % / taker 0,05 %). Hasta que haya cifra con fuente, T92 no
puede modelar el costo de esta clase, y sin costo no hay veredicto de rentabilidad.

### 3.5 De dónde sale el precio: un índice de terceros
`GET /fapi/v1/constituents` descompone el índice. `AAPLUSDT`:

| Proveedor | Símbolo del constituyente | Peso |
|---|---|---|
| `dxfeed` | `AAPL:USLF24//uindex(USDTUSD)` | 28,93 % |
| `kaiko` | `KK_RFR_AAPLUSD//uindex(USDTUSD)` | 28,93 % |
| `pyth_pro` | `AAPL//uindex(USDTUSD)` | 28,93 % |
| `massive` | `FMV.AAPL//uindex(USDTUSD)` | 12,40 % |
| `binance_future` | `AAPLUSDT` | 0,83 % |

`XAUUSDT` reparte entre `dxfeed` (26,72 %), `kaiko` (26,72 %), `pyth_pro` (26,72 %), `massive`
(`C.XAU/USD`, 11,45 %), **`hyperliquid` (`xyz:GOLD`, 7,63 %)** y `binance_future` (0,76 %).

Tres consecuencias: (a) el precio de referencia es un **compuesto de proveedores privados**, no la
cotización del mercado primario, y uno de los componentes (`massive`, `FMV.*`) es un *fair market
value* estimado —el que sostiene el precio cuando el subyacente está cerrado—; (b) el propio precio
de Binance pesa en su índice (0,8 %), así que hay un lazo de realimentación pequeño pero no nulo;
(c) **ninguna de esas fuentes es un dato que EIM pueda obtener ni auditar**: solo se ve el
resultado. Toda cifra de esta clase se etiqueta con `source` = Binance TradFi, nunca con el nombre
de la bolsa de origen.

Lo que sí hay, y es más de lo que tiene el almacén hoy: para los TradFi funcionan los cuatro
marcos probados (`1m`, `1h`, `1d`, `1w` en `/fapi/v1/klines`) y también `markPriceKlines`,
`indexPriceKlines` y `premiumIndexKlines` (comprobado con `XAUUSDT`). Es decir, se puede guardar la
serie del **índice** junto a la del **contrato** y medir el desvío entre ambos sin inventar nada:
esa es la vía para cuantificar el «precio sin subyacente» de §3.3 y, de paso, resuelve el punto (4)
que T43 dejó abierto para la base (la financiación prevista histórica vía `premiumIndexKlines`).

También funcionan en TradFi el interés abierto (`/fapi/v1/openInterest`: `AAPLUSDT` 157 230
contratos, ≈ 54,9 M USDT) y su histórico (`/futures/data/openInterestHist`). **Esto cambia una
conclusión de T87 §2**, que clasificaba `derivatives` (funding, OI) como agente específico de
cripto: sus dos entradas existen para los 246 TradFi, así que es **portable tal cual** a esta
clase. En cambio `liquidations`, `microstructure` (L2) y `smart_money` (líderes de Hyperliquid)
siguen sin fuente aquí, y `arbitrage` no tiene segunda pata: no hay spot ni trimestral de estos
subyacentes en Binance.

### 3.6 Lo que no se pudo verificar en Binance
1. **Comisiones de los TradFi** (§3.4): sin cifra con fuente.
2. **Escalones de margen** por tamaño de posición: `/fapi/v1/leverageBracket` exige clave.
3. **Términos de uso de los datos de la API** (si permiten almacenamiento local y si prohíben la
   redistribución): la página de términos no se pudo extraer. Sigue abierto desde T33 (alerta 10:
   los términos «Non-Commercial», en borrador, de `data.binance.vision`).
4. **Eventos corporativos.** En el *changelog* de la API consta que los dividendos se cobran como
   financiación especial: `GET /fapi/v1/fundingRate` tiene `rateType` con valor `Special` «for the
   additional funding rate generated by stock dividends» (entrada de 2026-07-23) y
   `GET /fapi/v1/income` tiene `incomeType` `SPECIAL_FUNDING_FEE`, «used for Tradfi Dividend funding
   fee» (2026-09-10). **Los *splits* y el resto de eventos corporativos no se verificaron**; existe
   un artículo «Binance Stocks Trading Corporate Actions» (2026-06-01) que no se pudo leer.
5. **Contrato previo obligatorio.** El *changelog* registra `POST /fapi/v1/stock/contract` —«sign
   TradFi-Perps agreement contract» (2025-12-11)— y su equivalente en Portfolio Margin
   (`POST /papi/v1/um/stock/contract`, 2026-04-08). Operar esta clase, incluso en testnet, exigiría
   firmar ese acuerdo: **no se ha firmado nada** y queda para T103.
6. **Disponibilidad por jurisdicción** y si estos contratos están abiertos al usuario: no verificado.

## 4. Auditoría de repositorios

Método, igual que T04 y T33: metadatos por la API de GitHub y de PyPI (`curl`), clones superficiales
de **solo lectura y aislados fuera del proyecto** (`C:\t88clones\`, con `--depth 1
--filter=blob:none` y `sparse-checkout`), y lectura y `grep` de los archivos citados. **No se
instaló ni se ejecutó nada de terceros**; ningún intérprete se lanzó desde dentro de un clon.
Entorno de referencia: CPython **3.12.10**, `requires-python = ">=3.11"`, con numpy 2.4.4,
pandas 3.0.2 y duckdb 1.5.6 instalados hoy en `v2/.venv`.

**Limitación declarada:** es una auditoría **por patrones y metadatos**, no línea a línea. No se
auditaron dependencias transitivas (250 paquetes en el *lock* de OpenBB, el grafo NuGet de LEAN, el
grafo Cargo de NautilusTrader). Lo no cubierto se dice en cada ficha.

### 4.1 Veredictos

| Repo | Licencia verificada | Modo | Motivo |
|---|---|---|---|
| **exchange_calendars** | Apache-2.0 | **A usar** | Única que distingue por excepción «fuera de horizonte» de «no es sesión»: exactamente lo que el almacén necesita. 69 calendarios + alias `24/7`. |
| **pandas_market_calendars** | MIT (+ `NOTICE` Apache-2.0 por su origen en zipline) | **A usar** (complemento) | Aporta CME Globex por sector y un FOREX 24/5 real; ya depende de `exchange-calendars>=3.3`, así que no añade árbol nuevo. |
| **PyPortfolioOpt** | MIT | **A usar** (T96) | Python puro, sin red ni disco ni estado global: el más auditable de los ocho. Fijar `==1.6.0`. |
| **NautilusTrader** | LGPL-3.0 (`or-later` en 1.x, `only` en 2.x) | **B proceso aislado** | Copiar código contagia LGPL; la v2 exige ≥3.13. Para la taxonomía de `Instrument` basta leerla (modo C). |
| **Riskfolio-Lib** | BSD-3 | **B proceso aislado** | Su licencia es limpia, pero arrastra **vectorbt (Commons Clause)** como dependencia obligatoria, más astropy/arch/statsmodels. |
| **LEAN** | Apache-2.0 | **C referencia** | C#/.NET 10 con Python embebido clavado a 3.11: no es dependencia posible. Sus modelos de margen sí son plantilla. |
| **Qlib** | MIT | **C referencia** | PyPI se quedó en 0.9.7 (sin los parches de seguridad de 0.9.8) y las dependencias obligatorias meten MLflow, Redis, MongoDB y Jupyter. |
| **vectorbt** | Apache-2.0 **+ Commons Clause** | **C referencia** | No es software libre OSI. Usable mientras EIM no se venda, pero el embudo de T93 se hace con NumPy propio. |
| **ib_async** | BSD-2 (PyPI dice `Other/Proprietary`) | **C referencia** | Exige TWS/IB Gateway (Java) corriendo; `main` parada 11,5 meses; `tzdata<2026.0` caducado. |
| **QuickFIX** | «The QuickFIX Software License, Version 1.0» (propia, no OSI) | **D descartar** | Sin ruedas cp312/win_amd64 (solo sdist: habría que compilar C++17), PyPI sin metadatos de licencia, y EIM no tiene contraparte FIX. |
| **QuestDB** | Apache-2.0 | **D descartar** | Licencia impecable, pero exige un servidor Java permanente en el equipo de la captura 24/7. DuckDB 1.5.6 ya cubre el caso. |
| **OpenBB** (meta-paquete `openbb`) | Apache-2.0 **solo desde 5.0.0** | **D descartar** | 250 paquetes en el *lock*, `eval()` en código de producción que **escribe módulos Python en disco**, tres licencias en tres años. Un proveedor suelto se podría reevaluar como B. |

Confirma y precisa el contraste provisional de T87 §5: **PyPortfolioOpt y Riskfolio-Lib no son
intercambiables** (el segundo no puede entrar en el venv vivo), **OpenBB baja de «reevaluar» a
descartado**, y los dos paquetes de calendarios —que T87 no había evaluado— son los únicos que
suben a «usar».

### 4.2 Fichas

#### LEAN — QuantConnect/Lean · **C referencia**
| Campo | Dato |
|---|---|
| URL oficial | <https://github.com/QuantConnect/Lean> — la API resuelve a `QuantConnect/Lean` sin redirecciones; `fork = false`, `archived = false` |
| Licencia | Archivo `LICENSE` (191 líneas); GitHub `spdx_id = Apache-2.0`; copyright literal `Copyright 2014 QuantConnect Corporation`; cabecera Apache en cada `.cs`. **Sin discrepancias**; el README no la menciona (hay que citar el archivo, no el README) |
| Mantenimiento | `pushed_at` 2026-11-19; último commit de `master` 2026-11-18 (`53236fa4a234`); 22 628 ★; 327 issues. **Última release etiquetada: `v2.4.0.1` de 2017-08-08** — distribuyen por NuGet y Docker, no es abandono |
| Compatibilidad | C# / .NET 10. El Python es **embebido vía pythonnet y clavado a 3.11** (`DockerfileLeanFoundation`: `PYTHONNET_PYDLL=…libpython3.11.so`, `Miniconda3-py311`). Repo ~590 MB. El `lean` de PyPI es el **CLI**, no el motor. **No importable desde EIM 3.12** |
| Riesgos | Por patrones sobre `Common/Securities` (117 `.cs`) y la raíz: sin `Process.Start`, sin `HttpClient`, sin `BinaryFormatter`, sin claves. Sí `JsonConvert.DeserializeObject<MarketHoursDatabase>` sobre archivo local (tipado, riesgo bajo) y `Expression…Compile().DynamicInvoke()` en el emparejador de estrategias de opciones. **No cubierto**: `Engine/`, `Brokerages/`, `Data/`, `ToolBox/`, el grafo NuGet. Trae conectores de bróker reales |
| Reutilizable | `IBuyingPowerModel` (`Common/Securities/IBuyingPowerModel.cs:21`) con `GetMaximumOrderQuantityForTargetBuyingPower` y `HasSufficientBuyingPowerForOrder`: plantilla directa para el veto determinista de `eim/risk`. `CryptoFutureMarginModel` / `BinanceCryptoFutureMarginModel` y los modelos de tasa de financiación. `IVolatilityModel` como modelo enchufable |

#### NautilusTrader — nautechsystems/nautilus_trader · **B proceso aislado**
| Campo | Dato |
|---|---|
| URL oficial | <https://github.com/nautechsystems/nautilus_trader>, sin redirecciones; rama por defecto `develop` (v2) |
| Licencia | `LICENSE` = texto íntegro de la **LGPL v3**; GitHub `spdx_id = LGPL-3.0`; copyright del titular en las cabeceras: `Copyright (C) 2015-2026 Nautech Systems Pty Ltd`. **Matiz**: 1.231.0 declara `LGPL-3.0-or-later`, la v2 `LGPL-3.0-only` (retira el «or later»). La marca queda fuera de la licencia (`TRADEMARK.md`) |
| Mantenimiento | El más activo del grupo: último commit de `develop` 2026-11-20; 31 701 ★; **127 issues** (la mejor relación issues/estrellas). Última estable `v1.231.0` (2026-08-02); precandidatas `2.0.0rc3`…`rc9` |
| Compatibilidad | **1.231.0: `requires_python >=3.12,<3.15` y sí hay `nautilus_trader-1.231.0-cp312-cp312-win_amd64.whl`** → instalable en el venv de EIM sin compilar. **La v2 exige ≥3.13 y solo publica cp313/cp314**: la compatibilidad actual existe pero **caduca en la próxima mayor** |
| Riesgos | Por patrones sobre `crates/model/src/instruments/` y `python/`: sin `eval`, sin `exec`, sin `requests.post`, sin telemetría. `subprocess` solo en herramientas de desarrollo. Higiene de secretos buena (`api_key_masked()`). **No cubierto**: los ~50 adaptadores de exchange (ahí vive el I/O de red y las claves) ni el grafo Cargo; el proyecto audita su propia cadena (`deny.toml`, `osv-scanner.toml`, `.supply-chain/`). **El clon trae `AGENTS.md`, `CLAUDE.md` y `AI_POLICY.md` en la raíz**: leídos como datos, no obedecidos; contenido legítimo de política de contribución, pero conviene saber que clonar ese repo inyecta un `CLAUDE.md` en el árbol |
| Reutilizable | **El modelo de `Instrument`, que es lo que T87 §5 quería ver.** En 1.231.0 (`nautilus_trader/model/instruments/`): base `Instrument(Data)` (`base.pyx:93`) y 20 clases concretas — `Equity`, `CurrencyPair`, `FuturesContract`, `FuturesSpread`, `OptionContract`, `OptionSpread`, `BinaryOption`, `Cfd`, `Commodity`, `IndexInstrument`, `CryptoPerpetual`, `PerpetualContract`, `CryptoFuture`, `CryptoOption`, `SyntheticInstrument`, `TokenizedAsset`, … En v2, el enum `InstrumentAny` (`crates/model/src/instruments/any.rs:33`). **Dato que decide alcance: no hay clase de renta fija** — lo más cercano es `Cfd`/`Commodity`/`IndexInstrument`. Se copia el **patrón** (base común + variante por tipo, con `price_increment`/`size_increment` y multiplicador en el propio instrumento) a los contratos pydantic de `eim/core`, sin arrastrar código LGPL |

#### OpenBB — openbq-org/OpenBB · **D descartar**
| Campo | Dato |
|---|---|
| URL oficial | <https://github.com/OpenBB-finance/OpenBB> responde **HTTP 301** → `https://api.github.com/repositories/323048702`, hoy **`openbq-org/OpenBB`**. `git ls-remote` con la URL antigua **sigue funcionando por redirección transparente**: cualquier `git clone` guardado en un script apunta hoy a la organización nueva sin avisar. La organización `OpenBB-finance` sigue existiendo con 45 repos, pero ya no contiene `OpenBB` |
| Licencia | `LICENSE` (205 líneas) con `Copyright (c) 2021-2026 OpenBB Inc.` + texto Apache-2.0 completo. **Tres discrepancias**: GitHub la da como `NOASSERTION` (dos líneas de preámbulo antes del texto rompen el detector); el README enlaza a la organización vieja, a la rama `main` (que no es la por defecto) y a un `LICENSE.txt` que no existe; y **la licencia depende de la versión** (§4.3) |
| Mantenimiento | Activo: último commit de `develop` 2026-11-18; **75 595 ★** (el más popular); 131 issues. Última en PyPI: **5.0.0 (2026-09-29)**. Equipo mixto tras el traslado: cuentas nuevas con sufijo `-bq` junto a mantenedores históricos (`piiq`) |
| Compatibilidad | PyPI 5.0.0: `requires_python <4,>=3.10`, rueda `py3-none-any` → compatible sobre el papel (el repo declara `>=3.11`, PyPI `>=3.10`: otra discrepancia). **El problema es el peso**: el meta-paquete arrastra ~25 dependencias obligatorias propias (una por proveedor) y su `uv.lock` fija **250 paquetes**, con Flask/FastAPI, pandas, `pywry` (ventanas nativas) y un CLI interactivo. Inasumible en un equipo de 4 núcleos y 16 GB con captura 24/7 |
| Riesgos | **`eval()` en código de producción, no solo en pruebas**: `openbb_platform/core/openbb_core/app/static/package_builder/method_definition.py:1571,1579` (`eval(param_type)`, `eval(default_str)`) y `cli/openbb_cli/controllers/feature_controller.py:650,975` (`eval(query_str, namespace)` sobre expresiones del usuario). Ese `package_builder` **genera y escribe módulos Python en disco** (`builder.py:152,160,327`): OpenBB materializa su API escribiendo código, patrón incompatible con el estilo determinista de EIM. Credenciales de proveedores **en claro** en `~/.openbb_platform/user_settings.json` y `.env`, que `v2/docs/SEGURIDAD.md` no admitiría sin más. Sin `pickle.load`, sin `requests.post`, sin telemetría en el subconjunto revisado. **No cubierto**: los ~40 paquetes de proveedor, `desktop/` (Tauri) y las 250 transitivas |
| Reutilizable | Solo lectura de diseño: el patrón *standard model* + *fetcher* por proveedor (la misma idea que `PLAN/CONTRATOS.md`); el cargador de configuración en cascada (`config/loader.py`) como contraste para las variables `EIM_*`; y su **catálogo de proveedores públicos sin clave** (CFTC, FINRA, SEC, Fama-French, FRED, ECB, EIA) como lista de fuentes a implementar **directamente contra la API del emisor**, sin la dependencia |

#### Qlib — microsoft/qlib · **C referencia**
| Campo | Dato |
|---|---|
| URL oficial | <https://github.com/microsoft/qlib>, sin redirecciones. **En PyPI el paquete se llama `pyqlib`**, no `qlib` |
| Licencia | `LICENSE` MIT con `Copyright (c) Microsoft Corporation.` (sin año); GitHub `spdx_id = MIT`; clasificador MIT en repo y PyPI. **Sin discrepancias.** Advertencia operativa: `pyproject.toml:125` fija `license-files = []`, así que la rueda puede no incluir el aviso MIT — si se copia código, hay que traerlo a mano |
| Mantenimiento | Último commit de `main` 2026-10-08 (`fix(security): constrain config-driven code execution (#2340)`); 50 445 ★; **516 issues** (la peor relación del grupo). Última release `v0.9.8` (2026-10-08), **pero PyPI se quedó en `pyqlib` 0.9.7 del 2025-08-15**: ~15 meses de desfase |
| Compatibilidad | `requires-python >=3.8.0`; hay `pyqlib-0.9.7-cp312-cp312-win_amd64.whl`, así que instalaría sin compilar. **Dependencias obligatorias, el problema**: mlflow, **redis**, **pymongo**, lightgbm, cvxpy, gym, matplotlib, **jupyter**, nbconvert, pyarrow, dill. Instalarlo metería un servidor de experimentos, un cliente Redis y uno de MongoDB donde hoy hay DuckDB |
| Riesgos | Por patrones sobre `qlib/data/dataset/`, `qlib/workflow/` y `qlib/utils/` (**no** se revisaron `contrib/`, `rl/`, `model/`, `backtest/`). (a) **Ejecución de código dirigida por configuración**, su riesgo estructural: `init_instance_by_config` + `get_module_by_module_path(..., trusted=False)` importan clases arbitrarias nombradas en un YAML. (b) **pickle**: ya usa `restricted_pickle_load`… **pero ese endurecimiento no está en la 0.9.7 de PyPI** (`qlib/utils/pickle_utils.py` da 404 en el tag `v0.9.7` y 200 en `v0.9.8`, y v0.9.8 no está publicada). (c) **`subprocess.check_output(cmd, shell=True)`** en `qlib/workflow/recorder.py:385` ejecuta `git diff`/`git status` en el directorio de trabajo y **vuelca el diff al almacén de MLflow**: fuga potencial de código no publicado si se usara dentro del checkout de EIM. (d) Red: descarga de datasets públicos. Sin `eval`, sin `exec` |
| Reutilizable | `DataHandlerABC` / `DataHandler` / **`DataHandlerLP`** (`qlib/data/dataset/handler.py:25,67,382`): el patrón «crudo / procesado para aprender / procesado para inferir», que encaja con la regla de EIM de exponer `source` y cobertura. `TSDataSampler` y `TSDatasetH` (`dataset/__init__.py:272,642`) para ventanas sin fuga. Los procesadores *point-in-time* de `dataset/processor.py`. Y `restricted_pickle_load` (`utils/pickle_utils.py:224`) como patrón de seguridad portable a `eim/data/backup` |

#### vectorbt — polakowo/vectorbt · **C referencia**
| Campo | Dato |
|---|---|
| URL oficial | <https://github.com/polakowo/vectorbt>, sin redirecciones |
| Licencia | Archivo **`LICENSE.md`** (declarado en `pyproject.toml:10`): **Apache-2.0 + Commons Clause v1.0**, la cláusula en las líneas 1-7 y la cabecera que la ata al paquete en las 9-13; el cuerpo Apache empieza en la 15 y el copyright (`Copyright 2026 Oleg Polakow`) en la 203. **No es una licencia SPDX**: GitHub la da como `NOASSERTION` y **PyPI no declara licencia alguna** (`info.license = None`, cero clasificadores) — la restricción solo es visible en el repo. El README se autodenomina «fair-code» |
| Mantenimiento | Muy activo: último commit de `master` 2026-11-11; 9 899 ★; 132 issues. Última en PyPI: **1.2.1 (2026-11-11)** |
| Compatibilidad | `requires_python <3.15,>=3.11`, rueda `py3-none-any` (el acelerador nativo es el extra opcional `vectorbt-rust==1.2.1`). **Pide `numpy>=2.4.6` y `pandas>=3.0.3`, y el venv vivo tiene numpy 2.4.4 / pandas 3.0.2**: instalarlo obligaría a subir ambas en el entorno de la captura 24/7 (saltos de parche, riesgo técnico bajo, pero no gratis) |
| Riesgos | Arrastra numba, dill y plotly al venv. La edición abierta es la «community edition» de **VectorBT PRO**, producto comercial aparte; solo se auditó la gratuita |
| Reutilizable | Las ideas de barrido masivo vectorizado para el embudo de T93, que se implementa con NumPy propio (T87 §5 ya lo decidía así; esta auditoría lo confirma) |

**Texto literal de la Commons Clause** (de `LICENSE.md`, líneas 1-13; comillas tipográficas y el
espacio de `consulting/ support services` tal cual):

> “Commons Clause” License Condition v1.0
>
> The Software is provided to you by the Licensor under the License, as defined below, subject to
> the following condition.
>
> Without limiting other conditions in the License, the grant of rights under the License will not
> include, and the License does not grant to you, the right to Sell the Software.
>
> For purposes of the foregoing, “Sell” means practicing any or all of the rights granted to you
> under the License to provide to third parties, for a fee or other consideration (including
> without limitation fees for hosting or consulting/ support services related to the Software), a
> product or service whose value derives, entirely or substantially, from the functionality of the
> Software. Any license notice or attribution required by the License must also include this
> Commons Clause License Condition notice.
>
> Software: vectorbt
>
> License: Apache 2.0 with Commons Clause
>
> Licensor: Oleg Polakow

**Qué prohíbe, en práctica.** No impide usar la biblioteca dentro de un sistema propio no comercial:
EIM, que es solo análisis y no cobra, está cubierto por la Apache-2.0. Sí impide **venderlo**, con
una definición amplia: «Sell» incluye ofrecer a terceros, por una tarifa —hosting o soporte
incluidos—, un producto cuyo valor derive «entera o sustancialmente» de su funcionalidad (un EIM de
pago, o un servicio de señales con motor vectorbt, caerían dentro). **No es copyleft**: no contagia
al código propio que no la importa ni obliga a liberar nada. Pero **se transmite por distribución**:
si EIM se distribuyera con vectorbt dentro, el conjunto llevaría la restricción de venta y habría
que reproducir el aviso de la cláusula.

#### PyPortfolioOpt — PyPortfolio/PyPortfolioOpt · **A usar**
| Campo | Dato |
|---|---|
| URL oficial | <https://github.com/robertmartin8/PyPortfolioOpt> **redirige** a `PyPortfolio/PyPortfolioOpt`; el paquete en PyPI es `pyportfolioopt` (minúsculas) |
| Licencia | `LICENSE` MIT, `Copyright (c) 2018 Robert Andrew Martin`; GitHub `spdx_id = MIT`; texto MIT íntegro y clasificador OSI en PyPI. **Sin discrepancias** |
| Mantenimiento | Flojo pero vivo: último commit de `main` 2026-07-07, y es de documentación; 6 173 ★; 117 issues. Última en PyPI **1.6.0 (2026-02-26)** |
| Compatibilidad | **`requires_python` no está declarado** (`null`): pip no bloqueará ninguna versión, la compatibilidad solo consta en los clasificadores (3.10-3.14). Rueda `py3-none-any` |
| Riesgos | **Cero aciertos en los diez patrones de riesgo**: sin red, sin disco, sin estado global, sin `eval`/`exec`/`pickle`/`subprocess`. El más auditable de los ocho |
| Decisión | **A usar** en T96, fijando `pyportfolioopt==1.6.0` y vigilando el tope `scikit-base<0.14.0`. Es cartera, no señales |

#### Riskfolio-Lib — dcajasn/Riskfolio-Lib · **B proceso aislado**
| Campo | Dato |
|---|---|
| URL oficial | <https://github.com/dcajasn/Riskfolio-Lib>, sin redirecciones |
| Licencia | `LICENSE.txt` **BSD 3-Clause**, `Copyright (c) 2020-2026, Dany Cajas`; GitHub `spdx_id = BSD-3-Clause`; PyPI `BSD (3-clause)`. Coherente |
| Mantenimiento | Activo, de un solo autor: último commit de `master` 2026-11-04; 4 612 ★; 17 issues. Última en PyPI **7.4.1 (2026-11-04)** |
| Compatibilidad | `requires_python >=3.10`; extensión nativa con `riskfolio_lib-7.4.1-cp312-cp312-win_amd64.whl` |
| Riesgos | **La dependencia que importa**: `requires_dist` de 7.4.1 incluye **`vectorbt>=0.28.0`** como obligatoria, junto a astropy, arch, statsmodels, cvxpy, scikit-learn, networkx y clarabel. Instalarlo **mete la Commons Clause en el entorno** aunque su propia licencia sea BSD-3 — una auditoría que solo mire su `LICENSE.txt` lo pasa por alto |
| Decisión | **B proceso aislado**: si se quiere su catálogo de medidas de riesgo, va en un venv aparte que escriba resultados, nunca en el venv vivo |

#### ib_async — ib-api-reloaded/ib_async · **C referencia**
| Campo | Dato |
|---|---|
| URL oficial | <https://github.com/ib-api-reloaded/ib_async>; sucesor declarado de `ib_insync` |
| Licencia | `LICENSE` **BSD 2-Clause**, `Copyright (c) 2019 - 2023, Ewald de Wit` y `Copyright (c) 2024, Matt Stancliff`; GitHub `spdx_id = BSD-2-Clause`. **Discrepancia**: `pyproject.toml` pone `license = "BSD"` (no SPDX) y **PyPI publica `License :: Other/Proprietary License`** |
| Mantenimiento | **`main` parada desde 2025-12-06** (~11,5 meses); el `pushed_at` de 2026-11-18 refleja otras ramas, no `main`. 1 794 ★; 33 issues. Última en PyPI **2.1.0 (2025-12-08)** |
| Compatibilidad | `requires-python >=3.10`, clasificador 3.12 explícito, rueda `py3-none-any`. **Tope caducado: `tzdata<2026.0`**. Requiere **TWS o IB Gateway (Java) corriendo en local** con ~4 GB de JVM: no maneja claves de API, se conecta a un socket local |
| Riesgos | **Manda el token de IB en la cadena de consulta de la URL** (`flexreport.py:102,127`, con `urlopen` en 105/128) y guarda `password` en claro al lanzar TWS por `subprocess` (`ibcontroller.py:95,164-179`) |
| Decisión | **C referencia.** Informativo para T103. El alcance de EIM es solo BTC y solo análisis (T145), e IB no da BTC perpetuo; además la JVM choca con el presupuesto del equipo |

#### QuickFIX — quickfix/quickfix · **D descartar**
| Campo | Dato |
|---|---|
| URL oficial | <https://github.com/quickfix/quickfix>; PyPI apunta a `http://www.quickfixengine.org` (HTTP plano) |
| Licencia | `LICENSE` (45 líneas): **«The QuickFIX Software License, Version 1.0»**, propia, estilo Apache-1.1, `Copyright (c) 2001-2020 Oren Miller`. GitHub `spdx_id = NOASSERTION`. **La cláusula 3 exige un reconocimiento literal en la documentación de usuario final** y las 4-5 restringen el uso del nombre. **PyPI no declara licencia ni clasificadores** |
| Mantenimiento | Lento: último commit de `master` 2026-05-20; 2 014 ★; 125 issues. Última en PyPI **1.16.0 (2026-05-09)** |
| Compatibilidad | `requires_python >=3.6`, **ningún clasificador**, y **ninguna rueda**: el único archivo de la 1.16.0 es `quickfix-1.16.0.tar.gz`. Instalarlo en Windows obligaría a compilar **C++17 con SWIG y MSVC** |
| Riesgos | El paquete Python es un envoltorio SWIG sobre una biblioteca C++17 que **no se auditó ni se compiló** |
| Decisión | **D descartar**, por tres motivos independientes: sin ruedas, metadatos de licencia ausentes con atribución obligatoria, y EIM no tiene contraparte FIX. Confirma el veredicto provisional de T87 §5 |

#### QuestDB — questdb/questdb (+ `py-questdb-client`) · **D descartar**
| Campo | Dato |
|---|---|
| URL oficial | Servidor <https://github.com/questdb/questdb>. **El cliente Python vive en otro repo**: `questdb/py-questdb-client`. Son dos proyectos |
| Licencia | Servidor: `LICENSE.txt` **Apache-2.0** (201 líneas, con el apéndice sin rellenar; el copyright real está en las cabeceras Java). Cliente Python: `license_expression = "Apache-2.0"`. **Antecedente: relicenció de AGPLv3 a Apache-2.0 en 2019** (commit `7560895e`), así que conviene fijar versión y conservar copia del `LICENSE`. Lo comercial es QuestDB Enterprise, producto aparte |
| Mantenimiento | Servidor muy activo (último commit 2026-11-19), 17 540 ★, pero **1 576 issues abiertos** (el mayor del grupo). Cliente Python mucho más pequeño: 71 ★, 36 issues |
| Compatibilidad | Cliente `questdb` 6.1.0: `requires_python >=3.10`, hay `cp312`+`win_amd64`, **cero dependencias**. **Pero exige un servidor Java permanente** |
| Decisión | **D descartar**, por recursos y no por licencia: en `juanpablo-cpu` (4 núcleos, 16 GB) ya corren 24/7 la captura y el bróker simulado, y el `CLAUDE.md` del equipo documenta que procesos pesados han dejado la API parada. DuckDB 1.5.6 + Parquet cubren el caso. Igual que decía T87 §5: reevaluar solo con volumen medido |

#### exchange_calendars — gerrymanoim/exchange_calendars · **A usar**
| Campo | Dato |
|---|---|
| URL oficial | <https://github.com/gerrymanoim/exchange_calendars>; PyPI `exchange-calendars` |
| Licencia | `LICENSE` **Apache-2.0** en las tres fuentes (`spdx_id`, `license_expression`, cabeceras). Copyright literal de los fuentes: `# Copyright 2018 Quantopian, Inc.` |
| Mantenimiento | **El mejor del grupo para esta función**: último commit 2026-11-14 y versión **4.13.3 publicada el mismo día**; 688 ★; 49 issues. Para una biblioteca de calendarios, publicar el día que se commitea es el dato que importa |
| Compatibilidad | `requires_python <4,>=3.10`, rueda `py3-none-any`, dependencias moderadas (`numpy`, `pandas>=1.5.0`, `pyluach`, `toolz`, `tzdata`) **sin ningún `==` ni tope superior** |
| Cobertura | **69 calendarios + 31 alias**, más `"24/7"` y `"24/5"`. Cubre nativamente los ocho mercados que importan: XNYS/NASDAQ, CMES, XLON, **XETR**, XTKS/JPX, XHKG, **XKRX** |
| Riesgos | Festivos **codificados a mano**, sin red en ejecución, y **sin ninguna cláusula de exactitud**: solo el «AS IS» de Apache-2.0. **El horizonte por defecto se fija al importar el módulo** (`exchange_calendar.py:61,64`: `now-20y … now+1y`): en servicios de EIM que corren días, la ventana queda congelada en el arranque → hay que pasar `start`/`end` explícitos |
| Decisión | **A usar**, como autoridad de calendarios |

#### pandas_market_calendars — rsheftel/pandas_market_calendars · **A usar** (complemento)
| Campo | Dato |
|---|---|
| URL oficial | <https://github.com/rsheftel/pandas_market_calendars> |
| Licencia | **Dos archivos y los dos importan**: `LICENSE` **MIT** (`Copyright (c) 2016 rsheftel`) y `NOTICE` (11 899 B) que declara la procedencia — es un *fork* con modificaciones extensas de `zipline` (Quantopian), **cuyo núcleo está bajo Apache-2.0**. Al usarlo hay que conservar los dos avisos |
| Mantenimiento | Excelente y con el backlog más limpio: último commit 2026-11-14, versión **5.6.1** del mismo día; 1 010 ★; **5 issues** (el mínimo de los ocho) |
| Compatibilidad | `requires_python >=3.10`, clasificadores hasta **3.15** (el único que ya lo declara), rueda `py3-none-any`. Solo dos dependencias, sin topes: **`exchange-calendars>=3.3`** y `pandas` |
| Cobertura | 32 módulos propios + un espejo de todo `exchange_calendars` (`calendars/mirror.py`). **No tiene XETRA ni KRX nativos**, pero es el único con **CME Globex por sector, cripto incluido**, y un **FOREX 24/5 de verdad** (domingo 17:00 → viernes 17:00 de Nueva York, con el `open` desplazado un día). `sources.py` es metadato inerte con ~30 URLs oficiales (CME, NSE, Cboe, ASX): se imprimen, no se descargan — mejor trazabilidad de origen |
| Decisión | **A usar** solo si se necesitan CME Globex o FOREX 24/5; cuesta poco porque ya depende de la anterior |

**Recomendación de calendarios, y por qué:** `exchange_calendars` como **autoridad** y
`pandas_market_calendars` como **complemento**. El motivo es concreto y encaja con la regla de EIM
de no presentar como dato lo que no lo es: para distinguir «cerrado» de «sin dato», la biblioteca
tiene que **negarse a responder** fuera de lo que sabe, y solo `exchange_calendars` lo hace, con
excepciones diferenciadas en `errors.py` — `DateOutOfBounds` y `RequestedSessionOutOfBounds` =
fuera de horizonte → **falta de dato**; `NotSessionError` = fecha válida que no es sesión →
**mercado cerrado**; más `MinuteOutOfBounds` y `bound_min()`/`bound_max()` para preguntar antes.
`pandas_market_calendars` gira en torno a `schedule(start, end)`, que fuera de rango devuelve un
DataFrame corto o vacío: un hueco silencioso indistinguible de un fin de semana, justo el fallo a
evitar. Plan para T89/T90: (1) base `exchange_calendars` con `start`/`end` explícitos; (2) una capa
en `eim/data` que capture por separado las dos familias de excepciones hacia `no_data` frente a
`closed`; (3) para BTC, el calendario `"24/7"`, que convierte cualquier hueco en falta de dato por
construcción; (4) `pandas_market_calendars` solo si hacen falta CME Globex o FOREX 24/5.

### 4.3 Historia de licencias de OpenBB (lo que obliga a fijar versión)
En PyPI la licencia del paquete `openbb` **cambió tres veces**:

| Versión | Fecha | Licencia declarada |
|---|---|---|
| 3.2.4 | 2023-11-09 | **MIT** |
| 4.1.0 | 2024 | cadena vacía |
| 4.2.0 … 4.7.2 | 2024-05-15 → 2026-05-26 | **AGPL-3.0-only** |
| 5.0.0 | 2026-09-29 | **Apache-2.0** |

Decir «OpenBB es Apache-2.0» sin fijar versión ≥ 5.0.0 es incorrecto, y **cualquier copia de código
hecha antes del 2026-09-29 se tomó bajo AGPL-3.0** (copyleft de red): no se «convierte» en Apache
por la relicencia posterior. EIM no ha copiado nada de OpenBB, así que no hay deuda; queda escrito
para que no se haga.

### 4.4 La alerta 3 de T04, resuelta
T04 dejó abierta la sospecha de que `OpenBB-finance/OpenBB` hubiera sido suplantado por un
typosquat (`openbq-org`). **El hecho queda verificado y la hipótesis refutada**: es el mismo
repositorio trasladado —**mismo id numérico 323048702**, misma fecha de creación (2020-12-20, la
del OpenBB original) y sus 75 595 estrellas conservadas—, con forks de los repos de la organización
antigua y commits de mantenedores históricos de OpenBB junto a cuentas con sufijo `-bq`. La lectura
es una fusión o compra OpenBB + BrightQuery, de ahí la «q». **Sigue pendiente de confirmar fuera de
GitHub** quién controla hoy la cuenta de PyPI `openbb`; con el veredicto **D** eso deja de ser
urgente, pero la alerta de T04 se cierra como aclarada, no como peligro.

### 4.5 Nota de procedencia: archivos dirigidos a agentes de IA
Cuatro de los repos clonados traen archivos de instrucciones para agentes en la raíz:
`nautilus_trader` (`AGENTS.md`, `CLAUDE.md`, `AI_POLICY.md`), `quickfix` (`AGENTS.md`), `questdb`
(`CLAUDE.md`) y `pandas_market_calendars` (`AGENTS.md`). **Se leyeron como datos y no se obedeció
ninguna de sus directivas.** Su contenido es legítimo (política de contribución, guías de
compilación y estilo), sin nada malicioso. Se anota porque **clonar un repositorio de terceros
dentro del árbol de un proyecto inyecta en él un `CLAUDE.md` ajeno**, y eso sí es un vector: por eso
los clones de esta auditoría viven en `C:\t88clones\`, fuera de `TRADINGBOT`. Es material desechable.

## 5. Auditoría de proveedores de datos por clase

Método: lectura de la documentación, las páginas de precios y los **términos de uso** oficiales,
consultados el **2026-11-20**. **No se abrió ninguna cuenta, no se pidió ninguna clave y no se
contrató nada.** No se sorteó ninguna verificación anti-bot. Lo que no se pudo confirmar en la
fuente se dice en §5.6, no se completa de memoria.

**Nivel de cobertura** (el de T87 §1): **1 investigación** — solo para estudiar, no se puede operar
ni publicar con ella · **2 operativa** — licencia y límites claros, sirve para decidir en vivo ·
**3 ejecución** — datos autorizados por un intermediario para operar.

### 5.1 Alertas

1. **`yfinance` es un extractor no oficial de Yahoo, y hoy es dependencia de producción de EIM.**
   Está en `dependencies` de `v2/pyproject.toml` (no en un extra), instalado en el venv (v1.6.0), y
   lo usa `eim/data/providers/multi_asset.py` para `^GSPC` y `^IXIC`. Funciona hoy (comprobado:
   devuelve velas diarias correctas). El problema no es que se rompa, es que **no hay licencia de
   datos**: su propio aviso dice que «yfinance is not affiliated, endorsed, or vetted by Yahoo,
   Inc.», que «the Yahoo! finance API is intended for personal use only» y remite al usuario a
   Yahoo «for details on your rights to use the actual data downloaded». Y los Términos de Yahoo
   prohíben literalmente lo que hace: «access or collect data, or attempt to access or collect
   data, from our Services using any automated means … including but not limited to robots,
   spiders, scrapers, data mining tools» y usar su contenido «to create any database, archive».
   **La Apache-2.0 cubre el código de `yfinance`, no los datos de Yahoo.**
2. **Polygon.io ya es Massive.** `polygon.io/pricing` responde **301 → `massive.com/pricing`**
   (verificado). Hay que revisar cualquier mención a «Polygon» en código y documentos del proyecto.
3. **Nasdaq Data Link (Quandl) ha dejado de ser fuente gratuita de series.** El filtro «Free» de su
   catálogo devuelve hoy **un solo conjunto** (*Carbon Removal Data-CORC™*), y **los futuros
   continuos ya no están en el catálogo**. Quandl como fuente libre está muerto.
4. **No existe fuente gratuita de histórico continuo de futuros con *roll* documentado.** Stooq da
   11 460 sesiones de `CL.F` (≈ desde 1983), pero **con volumen e interés abierto a 0** y sin
   metodología de empalme publicada. Los símbolos de Yahoo (`CL=F`, `GC=F`, `ES=F`) son el
   vencimiento más cercano tal cual, **no una serie empalmada**. Sin regla de *roll* conocida, una
   serie continua no es un dato: es una construcción ajena sin documentar.
5. **Stooq es la fuente gratuita más rica y la más restrictiva, y ya exige navegador.** Términos:
   «This data is intended solely for personal use. Any commercial use is prohibited» y
   «Redistribution of data found on the website is not allowed without the consent of Stooq»; los
   índices de S&P DJI que sirve llevan además licencia propia («The Index data may be used only for
   your own personal, non-commercial purposes»). Y con `curl` devuelve hoy una página de
   verificación JavaScript («This site requires JavaScript to verify your browser»): **verificado
   por mí mismo**. Cualquier ingesta automatizada chocaría con §7.2 de su propio criterio y con la
   regla del proyecto de no sortear verificaciones.
6. **FMP, en plan personal, prohíbe descargar y almacenar**: «The Customer may not copy or download
   any content from the Services except with the prior written approval of FMP» y, al terminar,
   «Customer must delete all Data it has received from FMP … including data cached». Incompatible
   con un almacén local: queda **descartado**.
7. **EODHD es el único proveedor comercial que autoriza por escrito guardar los datos**: sus
   cuentas *Non-Professional* «are permitted to store, manipulate, and analyze the data for
   private, non-commercial purposes».
8. **Twelve Data prohíbe el uso comercial del nivel gratuito** y limita el almacenamiento a los
   «permitted timeframes specified in the Documentation» — **plazos que no se pudieron localizar en
   esa documentación**. Una restricción cuyo contenido no se puede leer no es una restricción que
   se pueda cumplir.
9. **El hueco más importante que queda abierto: el ajuste por *splits* y dividendos.** Ninguna
   página de precios ni de términos de los proveedores de acciones detalla si la serie diaria viene
   ajustada ni si el ajuste es retroactivo. Hay que cerrarlo **endpoint por endpoint** antes de
   elegir proveedor de renta variable (T97). Sin saberlo, cualquier backtest de acciones está
   midiendo otra cosa.
10. **Las fuentes oficiales públicas son las únicas de nivel 2 limpio**: US Treasury («offered
    free, without restriction, and available to copy, adapt, redistribute, or otherwise use»), BCE
    («users of this website may make free use of the information obtained directly from it»,
    citando al BCE como fuente) y FRED con atribución obligatoria.
11. **El volumen de FX spot no existe como dato consolidado**, y no se encontró ninguna fuente
    gratuita de tick ni de bid/ask intradía de FX: lo gratuito es **un punto de referencia al día**.
    Esto confirma lo que T87 §2 anticipaba y cierra la puerta a FX intradía sin pagar.

### 5.2 Resumen por clase

| Fuente | Clase | Entrega | Histórico / resolución | Retraso | Límites | Licencia / almacenamiento | Coste | Nivel | Veredicto |
|---|---|---|---|---|---|---|---|---|---|
| **Binance `fapi`** | Cripto + 246 TradFi | OHLCV, índice, marca, funding, OI, L2 | 2019→ (cripto), 2025-12→ (TradFi); 1 m–1 w | tiempo real | 2 400 *weight*/min por IP (verificado) | **No verificado** (§5.6) | 0 € | — | **B proceso aislado** |
| **Binance Vision** | Archivo histórico | Velas, operaciones, libro | archivo completo | n/a | límites publicados | **CC BY-NC-SA 4.0** (§5.5) | 0 € | 1 | **A usar** |
| **FRED** | Macro, tipos, FX | Series + *vintages* | largo; diaria/mensual | ~1 día hábil | banda «razonable», sin cifra | Gratis con **atribución obligatoria**; series de terceros solo uso personal | 0 € | **2** | **A usar** |
| **ALFRED** (en FRED) | Macro *point-in-time* | `vintage_dates`, `output_type` 2/3/4 | desde 2006 | igual que FRED | igual que FRED | igual que FRED | 0 € | **2** | **A usar** |
| **US Treasury** | Renta fija | Curva par diaria, 14 plazos | desde 1990-01-02 | ~1 día (act. 15:30 ET) | no publicados | Reutilización sin restricción; **sin licencia nombrada** | 0 € | **2** | **A usar** |
| **BCE (tipos de referencia)** | FX | EUR/USD y cruces diarios | desde 1999-01-04 | diario, 16:00 CET | sin clave | Uso libre **citando al BCE** | 0 € | **2** | **A usar** |
| **BCE Data Portal (SDMX)** | Curva AAA euro, macro | Curva Svensson diaria, FX | largo | diario | sin clave | Disclaimer general del BCE | 0 € | **2** | **A usar** |
| **Frankfurter** | FX | Diario, base configurable | desde 1948 | diario | **sin cuotas, sin clave** | Código **MIT**; datos del BCE | 0 € | **2** | **A usar** |
| **Tiingo** | Acciones, ETF, fondos | EOD + fundamentales | 30+ años | EOD | por plan | «internal and personal use only»; **sin redistribución** | 0–30 $/mes | 1 | **A usar** |
| **EODHD** | Acciones, ETF, FX, Treasury | EOD e intradía | largo | EOD | por plan | **Autoriza almacenar en local** (Non-Professional) | gratis / pago | 1 (gratis) · 2 (pago) | **A usar** |
| **Massive** (ex Polygon) | Acciones, opciones, índices, FX | EOD y tiempo real | gratis: **2 años** | EOD en gratis | gratis: **5 req/min** | Borrado en 30 días al cancelar; datos CME a purgar «immediately» | gratis / pago | 1 · 2 (pago) | **B proceso aislado** |
| **Twelve Data** | Acciones, FX, cripto, 250+ bolsas | OHLCV | por plan | por plan | por plan | Prohíbe uso comercial del nivel gratuito; plazo de almacenamiento **ilegible** | gratis / pago | 1 · 2 (pago) | **B proceso aislado** |
| **Stooq** | Acciones, índices, FX, materias primas, futuros | OHLCV diario, horario y 5 min | muy largo (`CL.F` 11 460 sesiones) | EOD | **exige navegador** | «solely for personal use»; sin redistribución | 0 € | 1 | **B proceso aislado** |
| **Alpha Vantage** | Acciones, FX, macro | OHLCV, indicadores | no verificado en el plan gratuito | — | **25 peticiones/día** | Licencia personal no comercial; **sin cláusula de almacenamiento** | 0 € / pago | 1 | **C referencia** |
| **openexchangerates** | FX | Diario, base solo USD | — | diario | 1 000 req/mes | Términos no auditados | 0 € / pago | 1 | **C referencia** |
| **SimFin** | Fundamentales | Estados financieros | — | — | — | **Licencia de datos no publicada** (su página de precios da HTTP 500) | gratis / pago | 1 | **C referencia** |
| **Sharadar** | Fundamentales *point-in-time* | Desde los 90 | largo | — | — | Sin precios ni términos públicos | — | 1 | **C referencia** |
| **CME DataMine** | Futuros y opciones | Tick real | largo | — | — | Exige cuenta y licencia; **precio no público** | — | 3 potencial | **C referencia** |
| **Nasdaq Data Link** | Institucional | — | — | — | — | El filtro «Free» da **1** conjunto | — | 1 | **C referencia** |
| **yfinance / Yahoo** | Acciones, ETF, índices, futuros | OHLCV | largo | ~15 min o EOD | sin publicar; bloqueos por IP | **Sin licencia de datos**; Yahoo prohíbe la recolección automatizada y crear archivos | 0 € | 1 | **D descartar** |
| **FMP** | Acciones, fundamentales | — | — | — | — | Prohíbe descargar y obliga a **borrar la caché** | gratis / pago | 1 | **D descartar** |
| **exchangerate.host** | FX | Diario | — | — | **100 peticiones/mes** | Licencia no legible | 0 € | 1 | **D descartar** |
| **Futuros continuos gratis** | Materias primas, índices | — | — | — | — | — | — | — | **No existe** con *roll* documentado |
| **Tick / bid-ask FX gratis** | FX | — | — | — | — | — | — | — | **No existe** |

### 5.3 Comprobado por mí, no solo leído
De las fuentes que suben a «usar», verifiqué que responden **sin clave** y con el histórico que
declaran:

- **Frankfurter**: `GET /v1/1999-01-04..1999-01-08?base=EUR&symbols=USD` → EUR/USD 1,1789 el
  1999-01-04. Sin clave, sin cuota.
- **BCE (SDMX)**: `data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A` → la misma serie,
  1999-01-04 = 1,1789, en CSV con los metadatos SDMX completos. Las dos coinciden, como debe ser:
  Frankfurter sirve los datos del BCE.
- **US Treasury**: la curva par diaria en CSV y en XML, sin clave, **14 plazos** (1 mes a 30 años),
  actualizada el 2026-11-20 (último dato 2026-11-19: 1 mes 4,20 %, 10 años 5,04 %, 30 años 5,40 %).
- **Stooq**: `curl` recibe la página de verificación JavaScript. Confirmado.
- **Polygon → Massive**: 301 confirmado.

### 5.4 Lo que esto significa para el plan
1. **FX y renta fija tienen fuente de nivel 2 y gratis** (BCE, Frankfurter, FRED, US Treasury): son
   las dos clases que se pueden abordar con licencia limpia y sin pagar, **en diario**. T98 (FX) y
   la parte de curva de T100 dejan de depender de una compra.
2. **Renta variable no tiene fuente limpia gratis.** La única vía sin coste —Yahoo vía `yfinance`—
   no tiene licencia de datos, y las que sí la tienen (Tiingo, EODHD) cuestan 0–30 $/mes y son de
   **uso personal sin redistribución**. T97 empieza con una decisión de gasto, no con código.
3. **Materias primas y futuros tradicionales se quedan sin histórico utilizable.** Sin *roll*
   documentado no hay serie continua; lo único con licencia verificada son los **8 perpetuos de
   materias primas de Binance** (§3.1), con 7,6–11,6 meses de histórico. T99 no es viable como
   «clase» todavía, y conviene decirlo antes de T97, no después.
4. **`yfinance` hay que sustituirlo o acotarlo.** No es un aviso para el futuro: es una dependencia
   declarada hoy. La sustitución natural de `^GSPC`/`^IXIC` en el visor son `SPYUSDT`/`QQQUSDT` de
   Binance (mismo proveedor, misma licencia que ya se usa, 24/7) o una fuente con licencia; la
   decisión va en `PLAN/notas/T88_decisiones.md`.

### 5.5 Binance Vision: términos verificados (cierra la alerta 10 de T33)
T33 dejó anotado que `data.binance.vision` publicaba unos términos marcados `[Draft]` cuyo PDF no
se pudo extraer, y lo pasó a BACKLOG. **Hoy sí se pudo**, y por dos vías independientes (la mía y
la del grupo de proveedores), con el mismo resultado.

- Fuente: <https://data.binance.vision/Binance_Vision-Terms_of_Use.pdf>, enlazado desde
  <https://data.binance.vision/terms-of-use.html>; descargado el 2026-11-20, 4 páginas.
- **«BINANCE VISION DATASET TERMS — Version: 1.0, Last Updated: August 26, 2026».** Ya no es
  borrador. Entidad que los ofrece: NEST EXCHANGE LIMITED (ADGM, Abu Dhabi).

Cláusulas que mandan, citadas:

- §3.1 — los conjuntos se ofrecen bajo la **Creative Commons
  Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)**.
- §4.1 — «Permitted non-commercial uses are limited to academic research, non-monetized open
  educational projects, **algorithmic historical backtesting for purely personal non-production
  research**, and non-commercial open-source data science evaluations.»
- §4.2 — «You shall not use the Datasets for **live proprietary trading execution**, automated
  commercial order generation, or **signal distribution to third parties** for direct or indirect
  compensation.»
- §4.3 y §4.4 — prohibido licenciar, revender o alojar los datos, e integrarlos en productos
  financieros comerciales o en «commercial trading bot platforms».
- §4.5 — **ShareAlike**: todo derivado que se redistribuya debe atribuir a Binance Vision y quedar
  «licensed under the identical CC BY-NC-SA 4.0 terms».
- §7.2 — prohibidos los *scrapers* o consultas automáticas continuas que esquiven los límites.
- §2.1 — el alcance son los datos «made available through data.binance.vision and associated
  endpoints»: **no cubre la API REST `fapi`**, que se rige por los Términos de Uso generales de
  Binance (y esos siguen sin verificar, §5.6).

**Qué significa para EIM.** `v2/eim/data/providers/liquidations.py` usa `data.binance.vision`.
Mientras EIM sea investigación personal sin producción ni dinero real —que es exactamente la
decisión D de T145, «solo análisis»— el uso cae dentro de §4.1. Dos límites quedan escritos:

1. **El día que haya ejecución con dinero real, los datos de Vision no pueden estar en la cadena**
   (§4.2). Es una condición de la puerta de T103, no un aviso.
2. **Si alguna vez se publica un derivado** —una serie, una tabla calculada con Vision, un panel
   abierto a terceros— ese derivado arrastra **CC BY-NC-SA 4.0 y la atribución** (§4.5). Hoy el
   Observatorio y la hoja de ruta son locales, así que no aplica; conviene no olvidarlo si la
   cadena de YouTube (fase 14) llegara a mostrar cifras derivadas de Vision.

### 5.6 Lo que no se pudo verificar (proveedores)
1. **Términos de uso de la API de mercado de binance.com** (almacenamiento local, uso automatizado,
   redistribución): las tres URL legales devuelven HTTP 202 con cuerpo vacío. Lo único verificado
   es el límite de 2 400 *weight*/min por IP. **Sigue abierto desde T33.**
2. **Ajuste por *splits* y dividendos en casi todos los proveedores de acciones** (la alerta 9).
3. Plazos de almacenamiento permitidos en **Twelve Data** (§2.3(g) remite a una documentación que
   no los contiene); y la profundidad y el retraso de su plan Basic.
4. **Precios de CME DataMine** y si existe algún conjunto gratuito o de muestra.
5. **Regla de empalme (*roll*)** de las series continuas de Stooq y tratamiento del *roll* en los
   símbolos de futuros de Yahoo.
6. Que la clave de **FRED** sea explícitamente gratuita (la palabra no aparece en las páginas
   consultadas) y sus **límites numéricos** de peticiones (solo hablan de banda «razonable»).
7. Profundidad del histórico del plan gratuito de **Alpha Vantage**.
8. Tiempo real, noticias y el *feed* IEX en el plan Starter de **Tiingo**.
9. Licencia y condiciones de **exchangerate.host** y de **openexchangerates**.
10. Licencia de datos de **SimFin** (su página de precios da HTTP 500) y términos y precios de
    **Sharadar**.
11. Licencia por conjunto en **Nasdaq Data Link** (es una SPA; no se pudo leer ninguna ficha sin
    cuenta).
12. **Licencia formal de los datos del US Treasury**: declaran reutilización sin restricción pero
    no nombran ninguna licencia (ni dominio público ni CC), y no publican límites de peticiones.
13. Si el *disclaimer* del €STR del BCE añade condiciones distintas al general.

## 6. Intermediarios: cuenta de papel (informativo para T103)

**No se abrió ninguna cuenta, no se rellenó ningún formulario y no se pidió ninguna clave.** Las
páginas de interactivebrokers.com e ibkb devolvieron 403 al lector: parte de los datos de IBKR
viene de fragmentos de búsqueda y está marcado como tal. Lo leído directamente fue
`ibkrguides.com` e `interactivebrokers.github.io`.

| Intermediario | Papel sin cuenta real | Clases | Datos | Líneas simultáneas | API | Límites |
|---|---|---|---|---|---|---|
| **Interactive Brokers** | **No**: exige cuenta real aprobada y financiada | Acciones, ETF, opciones, futuros, FX, bonos | **Sin suscripción, retrasados 15-20 min**; en vivo solo compartiendo la suscripción de la cuenta real | **100 de base**; +100 por paquete (30 $/mes, máx. 10) o por comisiones/capital | TWS API / IB Gateway (socket local, **deben estar corriendo**); Client Portal Web API; FIX no verificado | 50 mensajes/s; histórico 60 peticiones/10 min |
| **Alpaca** | **Sí**: «Paper Only Account» solo con correo, «Anyone globally» | Acciones y ETF de EE. UU., cripto | Papel: **solo IEX en vivo**; SIP exige plan de pago | WebSocket: 30 símbolos en el plan gratuito | REST + WebSocket en la nube | 200 llamadas históricas/min |
| **OANDA** | Demo fxTrade Practice gratis (registro) | FX | Tiempo real, 24 h | no verificado | REST v20 + streaming | 2 conexiones nuevas/s |
| **Tradier** | Sandbox ligado a cuenta | Acciones y opciones de EE. UU. | Retrasados 15 min | no verificado | REST | 60 req/min en sandbox |
| **Binance Futures Testnet** | Entorno de pruebas aparte | **Solo futuros de cripto** | no verificado | no verificado | REST/WS de prueba | Peso por IP |

**Implicación para T103.** El obstáculo no es la API: es que **la cuenta de papel de IBKR exige una
cuenta real financiada** y que, sin suscripciones de datos, lo que da es **retrasado 15-20 minutos**
con **100 líneas simultáneas**. Para un escáner que mira cientos de instrumentos, 100 líneas es el
límite que manda, no la CPU. Alpaca es el único que da papel sin cuenta real, pero solo acciones y
ETF de EE. UU. y con el *feed* IEX, que es una fracción del volumen consolidado. Para un adaptador
de papel que solo necesite **diario y horario**, el dato retrasado basta y el problema se reduce a
abrir la cuenta; para cualquier cosa intradía, no. Nada de esto se decide en T88: queda escrito.

**No verificado en intermediarios:** las condiciones y la duración de una demo de IBKR sin cuenta
real; la lista oficial de clases en papel y si coincide con la real; qué ocurre al exceder las 100
líneas; los reinicios diarios del servidor de papel; el acceso a FIX; si el límite de la Web API es
hoy 10 o 50 req/s (la documentación se contradice); cripto en papel y elegibilidad fuera de EE. UU.
en Alpaca; si el *sandbox* de Tradier exige cuenta de bróker real; y cómo se obtienen las claves del
testnet de Binance.

## 7. Verificado / refutado

Criterio de aceptación de T88: toda afirmación de la investigación del usuario (T87 §5) pasa a
verificada o refutada, con evidencia.

| Afirmación declarada en T87 §5 | Veredicto | Evidencia |
|---|---|---|
| LEAN es **Apache-2.0** | **VERIFICADA** | `spdx_id = Apache-2.0`; `LICENSE` con `Copyright 2014 QuantConnect Corporation`; cabecera Apache en cada `.cs`. Matiz: el README no la menciona |
| NautilusTrader es **LGPL-3.0** | **VERIFICADA, con matiz de variante** | `LICENSE` = texto íntegro LGPL v3; cabeceras `Copyright (C) 2015-2026 Nautech Systems Pty Ltd`. **1.231.0 declara `LGPL-3.0-or-later` y la v2 `LGPL-3.0-only`**: la v2 retira el «or later». La marca queda fuera (`TRADEMARK.md`) |
| NautilusTrader: **versión publicada compatible con el intérprete** (pregunta abierta de T77 §7) | **RESUELTA: sí, hoy; no, mañana** | `nautilus_trader-1.231.0-cp312-cp312-win_amd64.whl` existe y `requires_python >=3.12,<3.15` → instalable en el venv de EIM. Pero la v2 (`2.0.0rc9`) exige **≥3.13** y solo publica cp313/cp314: la compatibilidad **caduca en la próxima mayor** |
| NautilusTrader: **modelo de `Instrument`** cubre acciones, pares, futuros, opciones y perpetuos | **VERIFICADA, y con un hallazgo** | 20 clases concretas sobre `Instrument(Data)` (`base.pyx:93`): `Equity`, `CurrencyPair`, `FuturesContract`/`Spread`, `OptionContract`/`Spread`, `BinaryOption`, `CryptoPerpetual`, `PerpetualContract`, `Cfd`, `Commodity`, `IndexInstrument`, `TokenizedAsset`… **Hallazgo: no hay clase de renta fija.** T87 ya advertía de no suponer cobertura de bonos; queda confirmado |
| OpenBB es **Apache-2.0** | **REFUTADA como afirmación general**; verificada **solo para ≥ 5.0.0** | El `LICENSE` actual es Apache-2.0 (`Copyright (c) 2021-2026 OpenBB Inc.`), pero GitHub la da como `NOASSERTION` y en PyPI la licencia cambia por versión: 3.2.4 MIT, 4.2.0-4.7.2 **AGPL-3.0-only**, 5.0.0 Apache-2.0 (2026-09-29) |
| OpenBB: **procedencia dudosa** (alerta 3 de T04, posible typosquat) | **El hecho VERIFICADO; la hipótesis de typosquat REFUTADA** | La redirección 301 a `openbq-org/OpenBB` existe, pero es el **mismo repositorio** (id 323048702, creado 2020-12-20, 75 595 ★ conservadas), con forks de la organización antigua y commits de mantenedores históricos (`piiq`). Pendiente fuera de GitHub: quién controla la cuenta de PyPI `openbb` |
| Qlib es **MIT** | **VERIFICADA** | `spdx_id = MIT`; `LICENSE` con `Copyright (c) Microsoft Corporation.`; clasificador MIT en repo y PyPI. Advertencia: `license-files = []` puede dejar el aviso fuera de la rueda. **Hallazgo añadido**: PyPI se quedó en 0.9.7 (2025-08-15) y **no trae los endurecimientos de `pickle` de 0.9.8** |
| vectorbt es **Apache-2.0 + Commons Clause** | **VERIFICADA**, con dos matices | Texto literal transcrito en §4.2 (`LICENSE.md` líneas 1-13). **Matiz 1**: no es SPDX, GitHub la da como `NOASSERTION`. **Matiz 2**: **PyPI no declara licencia alguna** — la restricción solo es visible en el repo |
| PyPortfolioOpt es **MIT** | **VERIFICADA** | `LICENSE` MIT, `Copyright (c) 2018 Robert Andrew Martin`; `spdx_id = MIT`; clasificador OSI. Corrección colateral: la URL cambió a `PyPortfolio/PyPortfolioOpt` (301) |
| Riskfolio-Lib es **BSD-3** | **VERIFICADA en su licencia, ENGAÑOSA como conclusión** | `LICENSE.txt` BSD-3, `Copyright (c) 2020-2026, Dany Cajas`. **Pero** `requires_dist` de 7.4.1 incluye `vectorbt>=0.28.0` como **obligatoria**: instalarlo trae la Commons Clause |
| «No instalar las dos» (PyPortfolioOpt y Riskfolio-Lib) sin prueba | **CONFIRMADA y reforzada** | No es solo cuestión de comparar: **no pueden convivir en el venv vivo**, porque una arrastra la otra cadena. PyPortfolioOpt va en el venv; Riskfolio-Lib, aparte |
| ib_async es **BSD-2** | **VERIFICADA en el archivo, REFUTADA en los metadatos publicados** | `LICENSE` BSD-2 (`Ewald de Wit` 2019-2023, `Matt Stancliff` 2024); `spdx_id = BSD-2-Clause`. **Pero PyPI lo clasifica como `License :: Other/Proprietary License`** y `pyproject.toml` pone `license = "BSD"`, que no es SPDX |
| QuickFIX tiene **licencia propia** | **VERIFICADA** | «The QuickFIX Software License, Version 1.0», estilo Apache-1.1, `Copyright (c) 2001-2020 Oren Miller`; la cláusula 3 exige reconocimiento literal en la documentación de usuario final. **Hallazgo añadido**: no hay ruedas, habría que compilar C++17 |
| QuestDB es **Apache-2.0** | **VERIFICADA** | `LICENSE.txt` Apache-2.0 en el servidor y `license_expression = "Apache-2.0"` en el cliente Python. **Contexto**: relicenció de AGPLv3 a Apache-2.0 en 2019; lo comercial es QuestDB Enterprise, producto aparte |
| «DuckDB + Parquet ya sirven; QuestDB no ahora» | **CONFIRMADA** | Nada en la auditoría lo cambia, y el motivo es de recursos: exige un servidor Java permanente en el equipo de la captura 24/7. DuckDB 1.5.6 instalado |
| Binance lista perpetuos «TradFi» y `XAUUSDT` ya está | **VERIFICADA pero muy incompleta** | No son unos cuantos: son **246 vivos** con tipo de contrato propio `TRADIFI_PERPETUAL` y 39 250 M USDT/24 h (§3.1) |
| **Primer universo: todos los perpetuos USDⓈ-M de Binance, «sin licencias nuevas»** (T87 §4) | **VERIFICADA en lo de las licencias, con dos condiciones nuevas** | Son 567 perpetuos de cripto + 246 TradFi, mismo proveedor y misma API: no hace falta ninguna licencia nueva. **Pero** (a) los términos de datos de la API REST siguen **sin verificar** (§5.6) y (b) operar TradFi exigiría firmar un acuerdo propio (`POST /fapi/v1/stock/contract`, §3.6) |
| `agents/derivatives` (funding, OI) es **específico de cripto** (T87 §2) | **REFUTADA** | Sus dos entradas existen para los 246 TradFi: `/fapi/v1/fundingInfo` (8 h en 213, 4 h en 33) y `/fapi/v1/openInterest` + `/futures/data/openInterestHist`. Es **portable tal cual**. Siguen sin fuente `liquidations`, `microstructure` y `smart_money`, y `arbitrage` no tiene segunda pata |
| «En acciones y FX un fin de semana no es falta de dato» (T87 §2, punto 4) | **REFUTADA para los perpetuos de Binance** | Estos contratos **no cierran**: cero huecos y cero velas vacías durante el cierre del subyacente (§3.3). `find_gaps` es correcto tal cual aquí. El problema es el inverso: precio formándose sin subyacente, y hacen falta **dos** calendarios por instrumento |
| yfinance sirve para S&P 500 y Nasdaq «solo para el visor y la estacionalidad» | **FUNCIONA, pero sin licencia de datos** | Comprobado hoy: v1.6.0 devuelve `^GSPC` y `^IXIC` diarios correctos. Lo que no existe es el derecho a esos datos: Yahoo prohíbe la recolección automatizada y crear archivos con su contenido (§5.1) |
| Binance Vision: términos «Non-Commercial» en **borrador** (alerta 10 de T33, sin confirmar) | **CERRADA: ya no es borrador** | «Version 1.0, Last Updated: August 26, 2026», **CC BY-NC-SA 4.0**, con el *backtesting* histórico personal permitido por escrito y la ejecución en real y la distribución de señales prohibidas (§5.5) |
| Calendarios de mercado (`exchange_calendars`, `pandas_market_calendars`) | **EVALUADOS por primera vez** (T87 no los había mirado) | Apache-2.0 y MIT + `NOTICE` Apache-2.0 respectivamente; los dos activos y publicando el mismo día que commitean. **Solo `exchange_calendars` distingue por excepción «fuera de horizonte» de «no es sesión»**, que es lo que el almacén necesita (§4.2) |
| OpenBB «reevaluar solo como proveedor detrás de `Provider`» | **RESUELTA: no** | El meta-paquete queda **descartado** (§4.2). Lo que sí se conserva de él es su **catálogo de proveedores públicos sin clave** (CFTC, FINRA, SEC, Fama-French, FRED, ECB, EIA), para implementar **directamente contra la API del emisor** |
