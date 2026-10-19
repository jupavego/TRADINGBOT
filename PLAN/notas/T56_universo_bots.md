# Universo de bots para el escuadrón (insumo de T56, NO es una auditoría)
Fecha: 2026-10-18 · Fuente: investigación del usuario (24 proyectos) + búsqueda web de contraste + auditorías ya hechas (T04, T33).
**Todo lo marcado «sin verificar» viene de memoria o de listados de terceros; T56 lo comprueba con el `LICENSE` real y clones aislados, sin ejecutar nada.** Ninguna cifra de rentabilidad se acepta de README o de listados.

## 1. Qué es «un bot» en este plan
Un repositorio mezcla tres cosas distintas; el catálogo cuenta la tercera:
1. **Marco** (Freqtrade, Jesse, Hummingbot, Nautilus, Lean…): trae el motor, no una estrategia con ventaja.
2. **Infraestructura** (ccxt, conectores, librerías de backtest): no se puntúa como bot.
3. **Estrategia empaquetada** (`bot@estrategia`): una lógica concreta que se puede ejecutar sobre velas y devolver una postura. **Es la unidad del catálogo** (p. ej. un controlador direccional de Hummingbot, una estrategia de la comunidad de Freqtrade, la evaluación de OctoBot).

Clases de integración (decisión de arquitectura, coherente con F0):
| Clase | Qué produce | Papel en EIM |
|---|---|---|
| **D — direccional** | Postura deseada −1..+1 por vela | Agente `bots`; entra al bróker simulado y a la puerta T49 como familia «bots» |
| **L — liquidez/inventario** (market making, grid, DCA) | No tiene «señal» única: gestiona órdenes e inventario | Carril propio en simulación (como `arbitrage`); nunca vota en la síntesis |
| **IA — LLM/RL** | Hipótesis, escenarios, explicaciones | Solo informa (regla de CLAUDE.md); salida estructurada, sin voto numérico |
| **INFRA** | Datos, conexión, backtest | Fuera del puntaje; se usa o se descarta por T33/T34 |

## 2. Cobertura del trabajo ya hecho (no se repite)
| Del listado del usuario | Ya existe | Consecuencia |
|---|---|---|
| Hummingbot (arbitraje) | T33 «Referencia» (Apache-2.0); arbitraje propio T38–T45 | No se reintegra el arbitraje; solo se evalúan sus controladores direccionales y de market making |
| Freqtrade / FreqAI | T04 «Referencia, no copiar» (**GPL-3.0**) | Solo por proceso aislado y tras decisión ◆ de licencia |
| NautilusTrader | T04 LGPL-3.0; T25 construyó motor propio | No es bot; backlog: contraste del motor T25 |
| CCXT, Binance Connector | T33 «Usar» | INFRA; ya resuelto |
| TradingAgents, AI Hedge Fund, AI-Trader | T04 TradingAgents «Referencia»; T24 agente de contexto | Clase IA: informan, no votan |
| Indicadores (TA-Lib, pandas-ta-classic) | T33/T34 | Hecho |
| Backtrader, vectorbt, backtesting.py, bt, Lean | T25 motor propio | INFRA; solo oráculo de contraste (BACKLOG) |

## 3. Universo ampliado (≥ 45 candidatos a evaluar en T56)
Licencia: **V** = verificada en una tarea previa o en la web el 2026-10-18; **s/v** = sin verificar.
| # | Proyecto | Clase | Licencia | Nota inicial |
|---|---|---|---|---|
| 1 | Freqtrade | D (marco) | GPL-3.0 (V, T04) | 55 k★, versión 2026.9; solo proceso aislado |
| 2 | FreqAI (dentro de Freqtrade) | D/IA | GPL-3.0 (V) | Reentrenamiento incremental; idea ya anotada en T04 |
| 3 | NostalgiaForInfinity (NFI) | D | GPL-3.0 (listado de terceros, s/v en el repo) | La estrategia más conocida de la comunidad Freqtrade; versiones de pago aparte |
| 4 | freqtrade-strategies (repo oficial de ejemplos) | D | s/v | Muchas con sesgo de optimización conocido |
| 5 | Hummingbot — controladores direccionales (V2: MACD+BB, SuperTrend, DMAN, bollinger grid) | D/L | Apache-2.0 (V, T33) | Lógica portable; telemetría por defecto (T33) |
| 6 | Hummingbot — market making (PMM) y arbitraje | L | Apache-2.0 (V) | Arbitraje ya cubierto por T38–T45 |
| 7 | OctoBot (evaluadores, grid, DCA) | D/L | GPL-3.0 (web) | 3.0.0-beta2 (2026-08); arquitectura «tentacles» |
| 8 | OctoBot Market Making | L | GPL-3.0 (s/v en el repo) | |
| 9 | Jesse (estrategias de ejemplo) | D | MIT solo el núcleo (web); resto s/v | Marco con ejemplos; ejecución en vivo es plugin de pago |
| 10 | Passivbot | L | s/v | Grid/inventario en perpetuos; Binance, Bybit, Hyperliquid… |
| 11 | Superalgos | D/L | s/v | Plataforma gráfica; estrategias de la comunidad sin auditar |
| 12 | CryptoSignal (CryptoSignal/Crypto-Signal) | D | s/v | Señales TA + avisos; probable abandono |
| 13 | Binance Trading Bot (chrisleekr) | L | s/v | Grid/trailing sobre Binance; revisar manejo de claves |
| 14 | CCXT Binance Trade Bot (edeng23 y similares) | D | s/v | Muy pequeño; referencia de arquitectura |
| 15 | Gekko / Zenbot | D | s/v | Archivados; solo valor histórico, probable «descartar» |
| 16 | Lean (QuantConnect) — algoritmos | D (marco) | Apache-2.0 (s/v) | Pesado; ejemplos de la comunidad |
| 17 | Nautilus — estrategias de ejemplo | D (marco) | LGPL-3.0 (V, T04) | Ya hay motor propio |
| 18 | bTrader (triangular Rust) | L/arb | s/v | Triangular: T43 «No viable» en Binance |
| 19 | Crypto liquidity detection bot | D | s/v | Experimental; solapa con `microstructure`/`liquidations` |
| 20 | Estrategias grid de Binance (UI) y TWAP/VP de la API de algoritmos de futuros | L / ejecución | oficial | TWAP/VP son algoritmos de **ejecución**, no de señal → BACKLOG de ejecución |
| 21 | TradingAgents | IA | Apache-2.0 (V, T04) | Patrón debate; envío opcional a tercero (alerta T04-6) |
| 22 | AI Hedge Fund (virattt) | IA | s/v | Educativo, no opera |
| 23 | AI-Trader (HKUDS) | IA | s/v | Investigación de agentes |
| 24 | FinRL / FinRL-Meta | IA (RL) | s/v | RL sobre datos de mercado; riesgo alto de sobreajuste |
| 25 | TensorTrade | IA (RL) | Apache-2.0 (web, s/v actividad) | Mantenimiento por confirmar |
| 26 | Qlib (Microsoft) | IA (ML) | s/v | Plataforma de factores; foco acciones |
| 27 | Stable-Baselines3 | INFRA/IA | MIT (s/v) | Solo si algún candidato RL lo exige |
| 28 | FinGPT | IA | s/v | LLM financiero; solo informa |
| 29 | Kronos | IA | MIT (V, T04) | Ya evaluado como motor de proyección (T16) |
| 30 | Optuna | INFRA | MIT (V, T04) | Ya usado en T26 |
| 31–36 | ccxt · binance-connector-python · python-binance · cryptofeed · hftbacktest · crypto_lob_stream | INFRA | V (T04/T33) o s/v | Decididos en T04/T33; no puntúan |
| 37–41 | Backtrader · vectorbt · backtesting.py · bt · PyAlgoTrade | INFRA | s/v (algunas copyleft/restrictivas) | Solo oráculo de contraste; no son bots |
| 42–45 | Hyperliquid_Copy_Trader · copytrading-agent · funding-arb · funding-rate-arbitrage | L/copy | V (T33) | Ya auditados: no se repiten |
| 46+ | Hallazgos de T56 (búsqueda sistemática en GitHub por tema `trading-bot`, `freqtrade-strategy`, `binance-futures-bot`, ordenada por actividad real) | — | — | T56 amplía el universo hasta agotar lo razonable y lo deja en el catálogo con su veredicto |

## 4. Riesgos que el plan ya asume (aprendidos en T27/T43/T44)
- Casi todo bot público pierde tras costos reales: el resultado esperado de la puerta T49 es «ninguno validado» o «pocos». Eso es un resultado válido, no un fallo del módulo.
- Las listas de «bots rentables» tienen sesgo de supervivencia y de optimización sobre los mismos datos; por eso la evidencia de cada bot se mide **fuera de muestra, con costos de perpetuos (T25) y con Holm sobre todos los intentos**.
- Una licencia GPL/AGPL puede obligar a publicar el código que la enlaza; el modo por proceso aislado reduce el riesgo pero no lo elimina: decisión ◆ del usuario con el análisis de T56.
