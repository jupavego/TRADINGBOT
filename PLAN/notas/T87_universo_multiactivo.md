# T87 — Universo multiactivo: insumo, auditoría rápida del repositorio y contraste

Fecha: 2026-10-19. Insumo: plan maestro y investigación de repositorios compartidos por el usuario (LEAN, NautilusTrader, OpenBB, Qlib, vectorbt, PyPortfolioOpt, Riskfolio-Lib, ib_async, QuickFIX, QuestDB, RD-Agent, FinRL, Zipline). **Las licencias y estados de esos repos son lo declarado por la investigación; no los verifiqué en la fuente** (T88 lo hace con el formato de T04). Lo de la sección 2 sí está **leído en el código de `v2/eim/`** en esta sesión (búsquedas por patrón, no una auditoría línea a línea: T87 la completa).

## 1. Cómo se enmarca el pedido
Replicar el modelo a «todo lo que se opera en un exchange» no es repetir Binance con otros símbolos. Tres hechos de estructura mandan:
- **No hay un libro único**: FX es OTC y fragmentado, bonos y repos se negocian por cotización o plataforma, acciones y futuros sí tienen mercado organizado. El registro de instrumentos debe declarar `market_structure` y qué datos existen (velas, cotizaciones, L2, cadena de opciones, curva); **un agente solo corre si el dato que declara necesitar existe** (hoy ya es así por `Agent.requires`).
- **Tres niveles de cobertura**: (1) datos públicos/de investigación, (2) datos operativos con licencia y límites, (3) ejecución autorizada por un intermediario. «Conocer» un instrumento no es poder operarlo; el sistema los distingue y la ejecución real sigue prohibida (CLAUDE.md: sin dinero real hasta T27/T31).
- **Honestidad estadística**: T27 dio NO PASA y T49 no validó ninguna estrategia en BTC/ETH. **Replicar la arquitectura no replica un edge.** Escanear miles de instrumentos con 17 agentes multiplica las hipótesis probadas: sin control de multiplicidad (Holm/FDR, Sharpe deflactado, PBO, control placebo) el escáner produciría falsos descubrimientos por diseño. Por eso T95 es tan importante como el propio escáner.

## 2. Lo que ya está listo y lo que ata a cripto (leído en el código)
**Agentes (17 registrados en `agents/registry.py`), por lo que declaran en `requires`:**
| Grupo | Agentes | Lectura |
|---|---|---|
| Solo `candles` (10) | structure, ema, vwap, price_action, elliott, levels, regime, technical, plan, seasonality | **Portables por construcción** a cualquier serie OHLCV. Ojo con supuestos de tiempo/volumen: `vwap` ancla por día/semana/quincena/mes UTC (en acciones/FX son sesiones), `seasonality` usa meses/días de semana, `technical` usa `taker_buy_v` si existe (degrada sin él), el volumen de FX spot es de ticks o no existe. |
| Genéricos por otra vía (2) | `calendar` (`events`, macro FRED/BLS/BEA), `context` (`headlines`, LLM solo informa) | Útiles para FX, acciones y bonos; el calendario sube de importancia fuera de cripto. |
| Específicos de cripto/derivados (5) | derivatives (funding, OI), liquidations, microstructure (`micro` L2), arbitrage (`arb`), smart_money (`leaders` Hyperliquid) | Se activan solo si el instrumento tiene esos datos (no_data si no). Para otras clases necesitarán **agentes hermanos** (curva, opciones, basis de futuros, carry FX), no adaptación. |

**Contratos:** `MarketSnapshot` ya es agnóstico del símbolo y casi todos los campos son opcionales (`None` → `no_data`); `Candle` trae `v` y `taker_buy_v` opcional. `Store` indexa por `(kind, symbol, timeframe)` (genérico). `Agent` es un `Protocol` con `requires`.

**Ya existe y se reutiliza:** `data/providers/multi_asset.py` (ASSETS: BTC, ETH, XAUUSDT —perpetuo TradFi de Binance—, S&P 500 y Nasdaq vía `yfinance`, solo para el visor y la estacionalidad); `data/calendar*` y `providers/{fred,calendar}.py`; la puerta de evidencia T49 (`validation/`, Holm, Sharpe deflactado); el Observatorio (T72–T76); el motor de backtest (T25) y el bróker simulado (T47/T48); el asignador de capital planeado (T46).

**Acoplamientos reales a cripto/Binance (lo que hay que abstraer):**
1. `data/timeframes.py`: `SYMBOLS = (BTCUSDT, ETHUSDT)` y `TF_MS = {15m, 1h, 4h}` (sin 1d/1w); se importan en ≈ 12 módulos de la API y los servicios. Los literales `BTCUSDT/ETHUSDT/USDT` aparecen en **unos 80 archivos de `eim/`** (api, arbitrage, paper, execution, backtest, analytics).
2. `data/providers/base.py`: el `Provider` mezcla `klines` con `funding_rates`/`open_interest` (conceptos de perpetuos).
3. **Costos, margen y simulación = modelo de perpetuos**: `backtest/{params,perp}.py` (comisión maker/taker, funding cada 8 h, liquidación aislada), `risk/sizing.py` (apalancamiento entero ≤ 3× con distancia de liquidación), `paper/{engine,desk}.py` (`FUNDING_MS`). Acciones (dividendos, splits, préstamo para cortos), FX (swap), futuros (multiplicador, roll, vencimiento) y bonos (cupón, accrued) no caben sin generalizar.
4. **Calendario 24/7**: `find_gaps` del almacén trata un hueco como falta de dato; en acciones/FX un fin de semana no lo es. VWAP/estacionalidad asumen UTC continuo.
5. `execution/`: `Broker` y `gateway` son de futuros USDⓈ-M y spot de Binance (prepare/apalancamiento/`closePosition`).
6. Calibración, validación y bróker simulado se midieron en BTC/ETH 1 h/15 m/4 h.

## 3. Aritmética del escáner (por qué el embudo no es opcional)
T72 midió el ciclo de agentes en ≈ **4,5 s por instrumento** (13 agentes, un marco). 10 000 instrumentos × 4,5 s ≈ **12,5 h** en un núcleo (≈ 3 h con 4 procesos, ya sin margen en un i5-8250U de 7,9 GB). Aplicar todos los agentes a todo, en todos los marcos y en cada actualización, es inviable; hace falta: (a) etapa 3 **vectorizada** y barata sobre todo el universo, (b) agentes profundos solo sobre una lista corta, (c) caché por `(instrumento, marco, hash de datos, versión del agente)`, (d) no escanear mercados cerrados. T87 repite la medición por agente para dimensionar.

## 4. Primer universo sin licencias nuevas
**Todos los perpetuos USDⓈ-M de Binance** (centenares; a contar en T89): mismo proveedor, mismo modelo de costos y misma ejecución ya probados. Sirve para validar el escáner, la caché, el ranking y —sobre todo— el control de multiplicidad antes de comprar datos o abrir cuentas. Binance también lista perpetuos «TradFi» (XAUUSDT ya está en `multi_asset`); T88 verifica cuáles y sus condiciones.

## 5. Contraste de repositorios (provisional, sin verificar)
| Repo | Licencia declarada | Decisión provisional | Motivo |
|---|---|---|---|
| LEAN | Apache-2.0 (C#) | **Referencia arquitectónica** (universo → alfa → cartera → riesgo → ejecución; modelos de comisión, deslizamiento, dividendos, splits) y posible **oráculo** de costos para acciones | Migrar los 17 agentes a C#/pythonnet no compensa; T25 ya decidió motor propio. |
| NautilusTrader | LGPL-3.0 | **Referencia del modelo de `Instrument`** (acciones, pares, futuros, opciones, perpetuos); sin cambio de la decisión de T25 | No se asume cobertura de bonos/repos/FX OTC. Versión publicada compatible con el intérprete (nota T77 §7). |
| OpenBB | Apache-2.0 en V5 (hay procedencia dudosa: T04 alerta 3) | **Reevaluar solo como proveedor detrás de `Provider`**, para macro y fundamentales (T03 lo dejó fuera por peso y trazabilidad del `source`) | Se mide contra proveedores directos; toda cifra conserva su fuente. |
| Qlib | MIT | **Referencia** (datos point-in-time, factores transversales); adopción diferida (BACKLOG) | Pesada; no es motor de ejecución. |
| vectorbt | Apache-2.0 + Commons Clause | **Referencia** para barridos masivos; el embudo de T93 se implementa con NumPy propio | Commons Clause: revisar antes de cualquier uso comercial. |
| PyPortfolioOpt / Riskfolio-Lib | MIT / BSD-3 | **Comparar en T96** con las mismas restricciones (extra `portfolio`); no instalar las dos sin prueba | Cartera, no señales. |
| ib_async | BSD-2 | **Candidato de adaptador de papel** (T103), si el usuario elige Interactive Brokers | Datos y límites dependen de permisos/suscripciones. |
| QuickFIX | licencia propia | **No** (sin contraparte FIX) | Complejidad sin conectividad. |
| QuestDB | Apache-2.0 | **No ahora**: DuckDB + Parquet ya sirven; reevaluar con volumen medido | Un servidor más sin necesidad medida. |
| RD-Agent, FinRL, Zipline-reloaded | — | **Fuera** (BACKLOG) | Automatizar hipótesis antes de tener validación multiactivo es multiplicar el sobreajuste; RL ya excluido en la Fase 16. |

## 6. Decisiones que se le piden al usuario (T87 ◆)
Las cuatro del plan, con la recomendación de partida: (1) **investigación global desde el inicio, ejecución solo simulada**, sin intermediarios nuevos; (2) **horizontes 1 h–1 d** (acciones y bonos en diario; lo intradía rápido queda en cripto/FX); (3) **datos públicos y gratuitos para el prototipo** con la procedencia y la licencia de cada fuente visibles, suscripciones solo si una clase demuestra valor; (4) **orden de clases**: cripto completo de Binance → índices/ETF/acciones líquidas (diario) → FX mayores → materias primas y futuros tradicionales → renta fija/derivados (solo viabilidad). Opciones y repos quedan condicionados a datos y a un modelo propio.

## 7. Reglas heredadas
Agentes puros (sin red/disco); I/O solo en `data/`; archivos ≤ 300 líneas; toda cifra con `source` y cobertura; modo visible (Análisis/Simulado/Testnet); ningún LLM decide órdenes; **sin dinero real** hasta T27/T31; solo claves de papel/testnet sin permiso de retiro; código de terceros con revisión de licencia (T04). La integración **no puede alterar los resultados actuales de BTC/ETH**: toda tarea que toque un agente o el motor se prueba contra los golden de T02/T05 y las suites existentes.
