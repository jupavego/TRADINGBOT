# T56 — Auditoría ampliada de bots y catálogo del escuadrón
Fecha: 2026-10-19 · Método: clones superficiales aislados (`--depth 1`, sin submódulos ni hooks, fuera del proyecto) de 47 repositorios y lectura de metadatos de PyPI; **no se ejecutó ni instaló nada de terceros**, solo `git clone`, `grep`, lectura y un escáner propio de solo lectura (patrones `pickle`/`eval`/`exec`/`subprocess`/retiros/telemetría/Binance USDⓈ-M, conteo de pruebas, hash de licencias). Formato y criterios como T04/T33; **lo ya dictaminado allí no se repite** (se enlaza).
Fichas: [`v2/eim/bots/registry/`](../../v2/eim/bots/registry/) (50 archivos + [`SCHEMA.md`](../../v2/eim/bots/registry/SCHEMA.md), con las reglas de puntuación escritas **antes** de puntuar). Cada ficha fija el SHA del commit auditado y enlaza la evidencia a ese commit.

**Estado: auditoría completa y lista aprobada por el usuario el 2026-10-19 (sección 8).**

## Limitaciones (leer)
1. **La API de GitHub no estuvo disponible** en esta sesión (403 fuera del repo del proyecto). No hay estrellas, forks, archivado oficial ni fecha de creación de cuenta. «Última actividad» = fecha del último commit del clon; «archivado/abandonado» se infiere de esa fecha y de lo que declara el README. T56 **no asevera popularidad**.
2. **La búsqueda sistemática por temas fue parcial** (sección 2): las páginas de temas de GitHub (`/topics/…`) devolvieron 404 o una sola entrada. Los hallazgos nuevos salen de búsquedas web y de los repos que esas fuentes citan, no de un barrido ordenado por actividad. Queda en BACKLOG repetirlo con la API.
3. El análisis de código es **por patrones y lectura de los módulos citados, no línea a línea** (igual que T04/T33). Donde una coincidencia de patrón no se leyó, la regla S3 la cuenta como **no cumplida** (conservador).
4. Ninguna cifra de rentabilidad de README, listado o commit se acepta (regla del universo); no se midió nada: eso es T59.
5. Los textos de licencia son los **archivos reales** del commit fijado (hash SHA-256 en cada ficha). Un badge del README no cuenta.

## 🚩 Alertas (leer primero)
1. **`fearfulincid/Grid-Trading-Bot` — señuelo (R1).** El repo no contiene código: solo `README.md`, `CHANGELOG.md` y un `LICENSE` MIT. El README es publicidad («Free download… 5.3 M+ downloads», insignias de «Status: Working») con botones que apuntan a un dominio externo para bajar un ejecutable de Windows. Un único commit de una cuenta con ese README; mismo patrón que `Hype-W/app-hyperliquid-copy-trading` (T33 alerta 1). **Descartar. No se visitó el enlace ni se descargó nada.** Apareció en la página del tema `crypto-grid-bot` precisamente por estar «actualizado» (2026-08-28): ordenar por actividad sin filtrar trae señuelos.
2. **Hummingbot depende de `pandas-ta >= 0.4.71b`** (`setup.py:66`, `setup/environment.yml:40`): es el paquete que T33 descartó (repo borrado, solo betas en PyPI, **sin licencia declarada**). Los controladores direccionales usan `df.ta.*` de ese paquete. Para el modo A **no se hereda**: las reglas se reimplementan con `eim.indicators` (T34). Si alguna vez se ejecutara Hummingbot, instala ese paquete.
3. **Hummingbot sigue enviando métricas por defecto** (`client_config_map.py:437-456`, `connector_metrics_collector.py`) — T33 alerta 4 vigente en el commit `9af100d6`. No afecta al código portado; sí a cualquier ejecución del programa.
4. **Superalgos ejecuta código de terceros en su propio proceso (R5).** 204 usos de `eval`/`new Function` en la aplicación y estrategias de la comunidad sin auditar; 1,5 GB. Tiene licencia Apache-2.0 y aun así **queda deshabilitado por seguridad** (la seguridad no se compensa).
5. **Sin licencia real (R2): `HKUDS/AI-Trader`, `ben-hampson/tradebot`, `webclinic017/strategies-freqtrade-`.** AI-Trader enseña un badge MIT en el README pero no tiene `LICENSE` (mismo caso que `limit-order-book` en T04). `webclinic017` es una copia sin licencia del trabajo de `nateemma` (GPL-3.0). Todos los derechos reservados: no se copia ni se integra.
6. **Jesse: la ejecución en vivo es un plugin de pago** que `jesse/services/installer.py` descarga con `LICENSE_API_TOKEN`; el repo «MIT» es solo el núcleo. Además vendoriza SDK ajenos en `jesse/modes/import_candles_mode/drivers/Apex/omni_files`. Solo se aprovechan sus estrategias de ejemplo (ficha aparte), y varias declaran otro origen (p. ej. Donchian → `gabrielweich/jesse-strategies`): la procedencia se revisa estrategia por estrategia en T58.
7. **`freqtrade-strategies` incluye una carpeta `lookahead_bias/`** (DevilStra, GodStraNew, Zeus, wtc): el propio repo las marca con sesgo de anticipación. Quedan **excluidas** del escuadrón; a las demás se les aplica la prueba de no anticipación de T57. Su README admite que la mayoría salió de hyperopt sobre periodos concretos.
8. **Passivbot envía códigos de bróker con las órdenes** (`broker_codes.hjson`: comisión de referido a su autor) y guarda claves en `api-keys.json`. En modo B (señal, sin claves, sin órdenes) ninguna de las dos cosas ocurre; se documenta como riesgo y se prueba en T58. Es dominio público (Unlicense), exige Python 3.12 o 3.14 (no 3.13) y compilar el orquestador en Rust.
9. **Freqtrade exige Python ≥ 3.12** y EIM admite 3.11 → entorno propio obligatorio (ya implícito en el modo B). Su fork `ft-pandas-ta` es MIT (PyPI, 2026-10-19) y **no** es el pandas-ta descartado.
10. **NFI opera en 5 min con informativos 15m/1h/4h/1d**, `can_short` y reajuste de posición (rebuy/grind = promediado a la baja). El almacén de EIM no sirve 5 m por la API (el marco `1m` es solo de almacén) y una «postura por vela» pierde esa parte del comportamiento. Por eso queda **opcional**.
11. **TradingAgents sigue pudiendo enviar publicaciones de Reddit/StockTwits a un tercero** si existe `TYPESAFE_API_KEY` (opt-in; `agents/post_screen.py`) — T04 alerta 6 vigente en `e8f5503e`.
12. **Casi todo bot público pierde tras costos** (T27/T43/T44 y el propio autor de `nateemma/strategies`, que concluye que ninguna estrategia con predicción de señal es rentable en exchanges de EE. UU.). El resultado esperado de T59 sigue siendo «ninguno» o «pocos»; este catálogo no lo cambia.

## 1. Resumen de veredictos y puntuación
Leyenda: **Modo** A portar · B proceso aislado sin claves · C referencia · D descartar. **Operativa** y **Seguridad** son sumas de la lista de control de `SCHEMA.md` (0–100). **Habilitado** = sin alerta roja y seguridad ≥ 70; no compensable. **Propuesta** es lo que T56 recomienda llevar a T58, no una aprobación. Ordenado por propuesta y puntuación operativa.

| Ficha | Clase | Modo | Licencia | Último commit | Veredicto | Propuesta | Operativa | Seguridad | Habilitado | Alertas |
|---|---|---|---|---|---|---|---|---|---|---|
| [hummingbot-directional](../../v2/eim/bots/registry/hummingbot-directional.json) | D | A | Apache-2.0 | 2026-09-22 | usar | propuesto | 95 | 80 | sí | — |
| [freqtrade](../../v2/eim/bots/registry/freqtrade.json) | INFRA | B | GPL-3.0 | 2026-10-19 | usar | propuesto | 93 | 100 | sí | — |
| [passivbot](../../v2/eim/bots/registry/passivbot.json) | L | B | Unlicense | 2026-10-18 | usar | propuesto | 88 | 100 | sí | — |
| [freqtrade-strategies](../../v2/eim/bots/registry/freqtrade-strategies.json) | D | B | GPL-3.0 | 2026-09-08 | usar | propuesto | 73 | 95 | sí | — |
| [nostalgia-for-infinity](../../v2/eim/bots/registry/nostalgia-for-infinity.json) | D | B | GPL-3.0 | 2026-10-19 | usar | opcional | 88 | 100 | sí | — |
| [jesse-example-strategies](../../v2/eim/bots/registry/jesse-example-strategies.json) | D | A | MIT | 2024-03-21 | usar | opcional | 50 | 95 | sí | — |
| [trendrider-strategy](../../v2/eim/bots/registry/trendrider-strategy.json) | D | A | MIT | 2026-04-21 | usar | opcional | 48 | 95 | sí | — |
| [hummingbot-arbitrage](../../v2/eim/bots/registry/hummingbot-arbitrage.json) | L | D | Apache-2.0 | 2026-09-22 | descartar | no | 80 | 80 | sí | — |
| [hummingbot-market-making](../../v2/eim/bots/registry/hummingbot-market-making.json) | L | C | Apache-2.0 | 2026-09-22 | referencia | no | 80 | 80 | sí | — |
| [lean](../../v2/eim/bots/registry/lean.json) | INFRA | C | Apache-2.0 | 2026-10-16 | referencia | no | 80 | 100 | sí | — |
| [freqai](../../v2/eim/bots/registry/freqai.json) | IA | C | GPL-3.0 | 2026-10-19 | referencia | no | 75 | 100 | sí | — |
| [jesse](../../v2/eim/bots/registry/jesse.json) | INFRA | C | MIT | 2026-10-17 | referencia | no | 75 | 75 | sí | — |
| [chrisleekr-binance-trading-bot](../../v2/eim/bots/registry/chrisleekr-binance-trading-bot.json) | L | D | Apache-2.0 | 2026-10-18 | descartar | no | 70 | 65 | **no** | — |
| [banbot](../../v2/eim/bots/registry/banbot.json) | INFRA | D | AGPL-3.0 | 2026-10-15 | descartar | no | 68 | 90 | sí | — |
| [octobot](../../v2/eim/bots/registry/octobot.json) | INFRA | D | GPL-3.0 | 2026-10-07 | descartar | no | 68 | 90 | sí | — |
| [haehnchen-crypto-trading-bot](../../v2/eim/bots/registry/haehnchen-crypto-trading-bot.json) | D | D | MIT | 2026-08-02 | descartar | no | 66 | 90 | sí | — |
| [nateemma-strategies](../../v2/eim/bots/registry/nateemma-strategies.json) | D | D | GPL-3.0 | 2026-09-13 | descartar | no | 65 | 85 | sí | — |
| [stable-baselines3](../../v2/eim/bots/registry/stable-baselines3.json) | INFRA | C | MIT | 2026-10-13 | referencia | no | 65 | 100 | sí | — |
| [backtesting-py](../../v2/eim/bots/registry/backtesting-py.json) | INFRA | C | AGPL-3.0 | 2026-08-05 | referencia | no | 63 | 100 | sí | — |
| [qlib](../../v2/eim/bots/registry/qlib.json) | IA | D | MIT | 2026-10-08 | descartar | no | 60 | 85 | sí | — |
| [tradingagents](../../v2/eim/bots/registry/tradingagents.json) | IA | C | Apache-2.0 | 2026-10-16 | referencia | no | 60 | 100 | sí | — |
| [alpha-rptr](../../v2/eim/bots/registry/alpha-rptr.json) | D | C | MIT | 2026-06-19 | referencia | no | 58 | 80 | sí | — |
| [bt](../../v2/eim/bots/registry/bt.json) | INFRA | C | MIT | 2026-10-17 | referencia | no | 58 | 100 | sí | — |
| [finrl](../../v2/eim/bots/registry/finrl.json) | IA | C | MIT | 2026-10-14 | referencia | no | 58 | 85 | sí | — |
| [octobot-tentacles](../../v2/eim/bots/registry/octobot-tentacles.json) | D | C | LGPL-3.0 | 2026-01-18 | referencia | no | 58 | 100 | sí | — |
| [finrl-meta](../../v2/eim/bots/registry/finrl-meta.json) | IA | D | MIT | 2026-09-28 | descartar | no | 56 | 75 | sí | — |
| [ai-hedge-fund](../../v2/eim/bots/registry/ai-hedge-fund.json) | IA | C | MIT | 2026-10-02 | referencia | no | 55 | 100 | sí | — |
| [fingpt](../../v2/eim/bots/registry/fingpt.json) | IA | D | MIT | 2026-09-23 | descartar | no | 55 | 75 | sí | — |
| [solie](../../v2/eim/bots/registry/solie.json) | INFRA | D | GPL-3.0 | 2026-08-14 | descartar | no | 55 | 85 | sí | — |
| [vectorbt](../../v2/eim/bots/registry/vectorbt.json) | INFRA | C | Apache-2.0 + Commons Clause | 2026-10-18 | referencia | no | 53 | 100 | sí | — |
| [ai-trader](../../v2/eim/bots/registry/ai-trader.json) | IA | C | NONE | 2026-06-11 | referencia | no | 50 | 85 | **no** | R2 |
| [backtrader](../../v2/eim/bots/registry/backtrader.json) | INFRA | C | GPL-3.0 | 2023-04-19 | referencia | no | 50 | 85 | sí | — |
| [cassandre-trading-bot](../../v2/eim/bots/registry/cassandre-trading-bot.json) | INFRA | D | GPL-3.0 | 2024-11-07 | descartar | no | 50 | 90 | sí | — |
| [tradebot-hampson](../../v2/eim/bots/registry/tradebot-hampson.json) | D | D | NONE | 2024-03-27 | descartar | no | 48 | 75 | **no** | R2 |
| [tensortrade](../../v2/eim/bots/registry/tensortrade.json) | IA | D | Apache-2.0 | 2026-02-09 | descartar | no | 45 | 100 | sí | — |
| [octobot-market-making](../../v2/eim/bots/registry/octobot-market-making.json) | L | D | GPL-3.0 | 2026-03-30 | descartar | no | 43 | 100 | sí | — |
| [pyalgotrade](../../v2/eim/bots/registry/pyalgotrade.json) | INFRA | D | Apache-2.0 | 2023-03-05 | descartar | no | 40 | 90 | sí | — |
| [btrader](../../v2/eim/bots/registry/btrader.json) | L | D | GPL-3.0 | 2021-05-30 | descartar | no | 38 | 90 | sí | — |
| [crypto-signal](../../v2/eim/bots/registry/crypto-signal.json) | D | D | MIT | 2022-08-09 | descartar | no | 38 | 95 | sí | — |
| [pycryptobot](../../v2/eim/bots/registry/pycryptobot.json) | D | D | Apache-2.0 | 2024-03-04 | descartar | no | 38 | 80 | sí | — |
| [superalgos](../../v2/eim/bots/registry/superalgos.json) | INFRA | D | Apache-2.0 | 2026-05-07 | descartar | no | 38 | 85 | **no** | R5 |
| [edeng23-binance-trade-bot](../../v2/eim/bots/registry/edeng23-binance-trade-bot.json) | D | D | GPL-3.0 | 2025-02-19 | descartar | no | 35 | 85 | sí | — |
| [zenbot](../../v2/eim/bots/registry/zenbot.json) | D | D | MIT | 2022-02-14 | descartar | no | 35 | 80 | sí | — |
| [webclinic017-strategies-freqtrade](../../v2/eim/bots/registry/webclinic017-strategies-freqtrade.json) | D | D | NONE | 2024-03-29 | descartar | no | 33 | 70 | **no** | R2 |
| [onchainvibe-freqtrade-strategies](../../v2/eim/bots/registry/onchainvibe-freqtrade-strategies.json) | D | D | GPL-3.0 | 2018-02-01 | descartar | no | 30 | 95 | sí | — |
| [pandianmn-freqtrade-strategies](../../v2/eim/bots/registry/pandianmn-freqtrade-strategies.json) | D | D | GPL-3.0 | 2023-07-16 | descartar | no | 30 | 95 | sí | — |
| [gekko](../../v2/eim/bots/registry/gekko.json) | D | D | MIT | 2020-02-16 | descartar | no | 28 | 75 | sí | — |
| [autotrader](../../v2/eim/bots/registry/autotrader.json) | INFRA | D | GPL-3.0 | 2025-05-04 | descartar | no | 25 | 80 | sí | — |
| [fearfulincid-grid-trading-bot](../../v2/eim/bots/registry/fearfulincid-grid-trading-bot.json) | L | D | MIT | 2026-08-28 | descartar | no | 20 | 0 | **no** | R1 |
| [krypto-trading-bot](../../v2/eim/bots/registry/krypto-trading-bot.json) | L | D | ISC + MIT | 2024-12-15 | descartar | no | 15 | 95 | sí | — |

Descartados de entrada por el filtro del entregable 1 (archivado, sin licencia o de pago): se **clonaron igualmente** para dejar la evidencia, y quedaron con veredicto `descartar` y motivo en su ficha. Bots de pago o de nube sin código auditable (3Commas, Cryptohopper, Pionex…) ya están fuera de alcance en el BACKLOG.

## 2. Búsqueda sistemática (registro)
Fecha: 2026-10-19. Consultas y resultado real:
| Consulta | Resultado |
|---|---|
| `github.com/topics/freqtrade-strategy?o=desc&s=updated` | 1 repo: `darkvolg/trendrider-strategy` (2026-04-21) → ficha `trendrider-strategy` |
| `github.com/topics/crypto-grid-bot?o=desc&s=updated` | 1 repo: `fearfulincid/Grid-Trading-Bot` (2026-08-28) → **señuelo (R1)** |
| `github.com/topics/binance-futures-bot`, `…/trading-bot`, `…/algorithmic-trading` (mismo orden) | HTTP 404: no se pudo listar |
| Búsqueda web «open source crypto futures trading bot Binance USDT-M active 2026» | `enarjord/passivbot`, `TheFourGreatErrors/alpha-rptr`, `ben-hampson/tradebot`, `banbox/banbot`, `cunarist/solie` → fichas |
| Búsqueda web «freqtrade strategy repository 2026 community» | `freqtrade/freqtrade-strategies`, `iterativv/NostalgiaForInfinity`, `nateemma/strategies`, `pandianmn/…`, `OnChainVibe/…`, `webclinic017/…` → fichas |
| Búsqueda web «crypto grid bot perpetual futures Passivbot alternatives» | Passivbot es la única opción dedicada de grid en perpetuos; el resto son marcos (Freqtrade, OctoBot, Jesse, Gainium comercial) |
| Búsqueda web «bTrader triangular arbitrage Rust» | `gabriel-milan/btrader` (último commit 2021) → ficha |
| Conocimiento previo + universo | Hummingbot, OctoBot (3 repos), Jesse (2), Superalgos, Crypto-Signal, chrisleekr, edeng23, Gekko, Zenbot, Lean, IA/RL (6), INFRA de backtest (5), Haehnchen, pycryptobot, Krypto-trading-bot, Cassandre, AutoTrader |

**Cobertura honesta:** 50 fichas de 47 repositorios, **ordenadas por lo que las fuentes accesibles mostraron, no por un barrido exhaustivo por temas**. Más candidatos «agotando lo razonable» exigen la API de GitHub (BACKLOG). Nada en lo encontrado cambia la conclusión: los candidatos activos con soporte real de futuros USDⓈ-M y licencia compatible son pocos (Freqtrade y sus estrategias, Hummingbot, Passivbot, Jesse).

## 3. El universo (`T56_universo_bots.md`) fila por fila
| # universo | Proyecto | Resultado en T56 |
|---|---|---|
| 1 | Freqtrade | GPL-3.0 **verificada** en el `LICENSE` · [freqtrade](../../v2/eim/bots/registry/freqtrade.json): ejecutor en modo B, propuesto |
| 2 | FreqAI | [freqai](../../v2/eim/bots/registry/freqai.json): C, referencia |
| 3 | NFI | GPL-3.0 **verificada en el repo** · [nostalgia-for-infinity](../../v2/eim/bots/registry/nostalgia-for-infinity.json): B, opcional |
| 4 | freqtrade-strategies | «s/v» → GPL-3.0 · [freqtrade-strategies](../../v2/eim/bots/registry/freqtrade-strategies.json): B, propuesto |
| 5 | Hummingbot direccionales | Apache-2.0 re-verificada · [hummingbot-directional](../../v2/eim/bots/registry/hummingbot-directional.json): A, propuesto |
| 6 | Hummingbot MM y arbitraje | [hummingbot-market-making](../../v2/eim/bots/registry/hummingbot-market-making.json) C · [hummingbot-arbitrage](../../v2/eim/bots/registry/hummingbot-arbitrage.json) D (cubierto por T33/T38–T45) |
| 7 | OctoBot | «web» → GPL-3.0 verificada · [octobot](../../v2/eim/bots/registry/octobot.json) D · [octobot-tentacles](../../v2/eim/bots/registry/octobot-tentacles.json) **LGPL-3.0** C |
| 8 | OctoBot Market Making | GPL-3.0 verificada · [octobot-market-making](../../v2/eim/bots/registry/octobot-market-making.json): D |
| 9 | Jesse | MIT (núcleo; en vivo de pago) · [jesse](../../v2/eim/bots/registry/jesse.json) C · [jesse-example-strategies](../../v2/eim/bots/registry/jesse-example-strategies.json) MIT A, opcional |
| 10 | Passivbot | «s/v» → **Unlicense** (dominio público) · [passivbot](../../v2/eim/bots/registry/passivbot.json): L, B, propuesto |
| 11 | Superalgos | Apache-2.0 · [superalgos](../../v2/eim/bots/registry/superalgos.json): D, **R5** |
| 12 | Crypto-Signal | MIT; 2022 · [crypto-signal](../../v2/eim/bots/registry/crypto-signal.json): D |
| 13 | chrisleekr/binance-trading-bot | Apache-2.0; solo spot · [chrisleekr-binance-trading-bot](../../v2/eim/bots/registry/chrisleekr-binance-trading-bot.json): D |
| 14 | edeng23 | GPL-3.0; spot · [edeng23-binance-trade-bot](../../v2/eim/bots/registry/edeng23-binance-trade-bot.json): D |
| 15 | Gekko / Zenbot | MIT; 2020 / 2022 · [gekko](../../v2/eim/bots/registry/gekko.json), [zenbot](../../v2/eim/bots/registry/zenbot.json): D |
| 16 | Lean | Apache-2.0 · [lean](../../v2/eim/bots/registry/lean.json): C (oráculo de contraste, BACKLOG) |
| 17 | Nautilus (ejemplos) | Cubierto: T04 («Referencia», LGPL-3.0); T25 construyó motor propio. No se re-audita |
| 18 | bTrader | GPL-3.0; 2021 · [btrader](../../v2/eim/bots/registry/btrader.json): D (T43 triangular «No viable») |
| 19 | «Crypto liquidity detection bot» | **No identificable**: el universo no da URL y la búsqueda no halló un repo con ese nombre. Descartado como candidato; el tema lo cubren los agentes `microstructure` y `liquidations` |
| 20 | Grid de Binance / TWAP·VP de futuros | Oficial, sin repo: algoritmos de **ejecución**; ya en BACKLOG (ejecución). No es un candidato del escuadrón |
| 21 | TradingAgents | Apache-2.0 re-verificada · [tradingagents](../../v2/eim/bots/registry/tradingagents.json): C |
| 22 | AI Hedge Fund | MIT; no opera · [ai-hedge-fund](../../v2/eim/bots/registry/ai-hedge-fund.json): C |
| 23 | AI-Trader | **Sin LICENSE (R2)** · [ai-trader](../../v2/eim/bots/registry/ai-trader.json): C, no copiar |
| 24 | FinRL / FinRL-Meta | MIT · [finrl](../../v2/eim/bots/registry/finrl.json) C · [finrl-meta](../../v2/eim/bots/registry/finrl-meta.json) D |
| 25 | TensorTrade | Apache-2.0; último commit 2026-02-09 · [tensortrade](../../v2/eim/bots/registry/tensortrade.json): D |
| 26 | Qlib | MIT · [qlib](../../v2/eim/bots/registry/qlib.json): D |
| 27 | Stable-Baselines3 | MIT · [stable-baselines3](../../v2/eim/bots/registry/stable-baselines3.json): INFRA, C |
| 28 | FinGPT | MIT · [fingpt](../../v2/eim/bots/registry/fingpt.json): D |
| 29–30 | Kronos · Optuna | Cubiertos: T04 (Usar). No puntúan |
| 31–36 | ccxt · binance-connector · python-binance · cryptofeed · hftbacktest · crypto_lob_stream | Cubiertos: T04/T33. INFRA, no puntúan |
| 37–41 | Backtrader · vectorbt · backtesting.py · bt · PyAlgoTrade | «s/v» → verificadas: [backtrader](../../v2/eim/bots/registry/backtrader.json) **GPL-3.0**, [vectorbt](../../v2/eim/bots/registry/vectorbt.json) **Apache-2.0 + Commons Clause**, [backtesting-py](../../v2/eim/bots/registry/backtesting-py.json) **AGPL-3.0**, [bt](../../v2/eim/bots/registry/bt.json) MIT, [pyalgotrade](../../v2/eim/bots/registry/pyalgotrade.json) Apache-2.0 (abandonado) |
| 42–45 | Hyperliquid_Copy_Trader · copytrading-agent · funding-arb · funding-rate-arbitrage | Cubiertos: T33. No se repiten |
| 46+ (hallazgos) | alpha-rptr · trendrider-strategy · banbot · solie · tradebot (hampson) · Krypto-trading-bot · Haehnchen · pycryptobot · Cassandre · AutoTrader · nateemma · pandianmn · OnChainVibe · webclinic017 · fearfulincid | 15 fichas nuevas (ver tabla de la sección 1) |

No queda ninguna fila «sin verificar»: todas pasaron a verificadas, descartadas o cubiertas por T04/T33.

## 4. Fichas propuestas y opcionales (evidencia)
### hummingbot-directional — modo A, propuesto · [`ficha`](../../v2/eim/bots/registry/hummingbot-directional.json)
| Campo | Dato |
|---|---|
| Repo / commit | `hummingbot/hummingbot` @ `9af100d6` (2026-09-22) |
| Licencia | `LICENSE` Apache-2.0 (T33 y de nuevo aquí) |
| Qué se porta | La **regla de señal** de `controllers/directional_trading/`: `bollinger_v1` (%B bajo/alto un umbral), `bollinger_v2` (igual con TA-Lib y rango no nulo), `macd_bb_v1` (%B + histograma + línea MACD), `supertrend_v1` (supertrend con distancia máxima), `dman_v3` (señal %B; la parte DCA es ejecución y no se porta). `bollingrid` y `ai_livestream` no (grid de ejecución / señal externa por MQTT) |
| Por qué es modo A | Cada `update_processed_data` es una función sobre un DataFrame de velas que devuelve +1/−1/0 (`df["signal"].iloc[-1]`); son ≈10 líneas por controlador |
| Cómo | Reimplementar con `eim.indicators` (T34) y pruebas propias; paridad contra la salida de Hummingbot sobre las mismas velas (fixture) en T58; aviso Apache-2.0 y NOTICE en `THIRD_PARTY.md` si se copia texto |
| Límites | Reglas de manual; ya hay Bollinger/MACD/Supertrend en EIM (T34): el aporte distinto lo mide T59. La postura es ternaria (+1/−1/0), `confidence = None` (el bot no la da; no se inventa) |
| Seguridad 80/100 | Pierde S4 y S6 por Hummingbot completo (métricas por defecto; `pandas-ta` beta sin licencia), **ninguno se hereda** al código portado |

### freqtrade + freqtrade-strategies — modo B, propuestos · [`freqtrade`](../../v2/eim/bots/registry/freqtrade.json), [`freqtrade-strategies`](../../v2/eim/bots/registry/freqtrade-strategies.json)
| Campo | Dato |
|---|---|
| Commits | `freqtrade/freqtrade` @ `3ce38b58` (2026-10-19) · `freqtrade/freqtrade-strategies` @ `f3340ce1` (2026-09-08) |
| Licencia | `LICENSE` **GPL-3.0** (ambos). Obliga a modo B (sección 5) |
| Qué expone | 7 de futuros (`FSupertrend`, `FAdxSma`, `FOtt`, `FReinforced`, `TrendFollowing`, `VolatilitySystem` y la de muestra `FSample`), las 27 genéricas de `user_data/strategies/` y 30 clásicas de `berlinguyinca/`; **excluidas** las 4 de `lookahead_bias/` |
| Cómo correría | Entorno propio (Python ≥ 3.12, TA-Lib, `ft-pandas-ta`), **sin claves**, velas entregadas por archivo; se leen las columnas de entrada/salida (`enter_long`, `exit_long`, `enter_short`, `exit_short`) que produce la estrategia, o `freqtrade backtesting --export signals` sobre datos locales. El shim que importe `freqtrade` vive en la carpeta aislada (es GPL) y nunca se importa desde `eim/` |
| Riesgo a resolver en T58 | El backtesting de Freqtrade carga los mercados del exchange (ccxt, red): probar un modo con mercados en caché o aceptar solo esa lectura pública; si no es viable, el veredicto cambia a descartar. Paridad: las posturas del adaptador = las del bot nativo sobre las mismas velas |
| Límites | Sin suite de pruebas en el repo de estrategias (pierde S9: 95/100); sesgo de optimización declarado; T58 aplica no anticipación a cada una |

### passivbot — clase L, modo B, propuesto · [`ficha`](../../v2/eim/bots/registry/passivbot.json)
| Campo | Dato |
|---|---|
| Commit | `enarjord/passivbot` @ `772abadc` (2026-10-18), 338 archivos de prueba |
| Licencia | `LICENSE` **Unlicense** (dominio público): sin condiciones; el modo B se elige por el entorno (Python 3.12/3.14, orquestador en Rust, dependencias pesadas), no por licencia |
| Estrategias | `trailing_martingale` (por defecto), `ema_anchor`; `trailing_grid_v7` obsoleta |
| Qué produce | Clase L: **órdenes e inventario**, no una postura. Va al **carril de simulación** (libro y fills simulados con costos de T25), como `arbitrage`; **nunca vota** |
| Revisado | `pickle` del optimizador = checkpoints propios (`src/optimize.py`, `pymoo_backend.py`); `subprocess` en herramientas de mantenimiento; códigos de bróker en `broker_codes.hjson` (solo con órdenes) |
| Pendiente en T58 | Alimentar el backtester con velas locales (hoy descarga archivos públicos de exchanges); medir riesgo de inventario (martingala con límites) |

### nostalgia-for-infinity — modo B, opcional · [`ficha`](../../v2/eim/bots/registry/nostalgia-for-infinity.json)
`iterativv/NostalgiaForInfinity` @ `d14d4de5` (2026-10-19), GPL-3.0, 25 archivos de prueba. Siete generaciones (`NostalgiaForInfinityX…X8`, 14 000 a 80 000 líneas cada una). Base 5 m + informativos, `can_short`, `position_adjustment_enable`. Ver alerta 10. **Recomendación: opcional**; si el usuario la aprueba, va en la oleada 2 después de las de Freqtrade y con datos 5 m.

### Opcionales de modo A (MIT)
- [`jesse-example-strategies`](../../v2/eim/bots/registry/jesse-example-strategies.json) @ `7c91e0a3` (2024-03-21): 11 estrategias de manual (Donchian, RSI2, Turtle, KDJ…). Sin pruebas ni mantenimiento; procedencia mixta. Aporte esperado bajo.
- [`trendrider-strategy`](../../v2/eim/bots/registry/trendrider-strategy.json) @ `621b0c86` (2026-04-21): 1 archivo de 745 líneas, solo largos, README promocional con «estadísticas en vivo» que no se aceptan. Aporte esperado bajo.

### Descartados que merecen una línea
- **Referencia sin integrar:** `hummingbot-market-making` (C; carril L, se reimplementa la idea), `octobot-tentacles` (LGPL-3.0 acoplada a OctoBot GPL-3.0), `alpha-rptr` (MIT, 161 menciones de Binance Futures, pero la señal está dentro de la clase `Bot` acoplada al exchange, Gmail y Discord; dependencias deprecadas), `freqai`, `lean`, `jesse`, `tradingagents` y el resto de IA/RL.
- **Abandonados:** Crypto-Signal (2022), Gekko (2020), Zenbot (2022), bTrader (2021), AutoTrader (archivado), pyalgotrade (2023), K (2024-12).
- **Spot sin futuros ni ventaja:** `chrisleekr` (el autor lo declara no apto para fondos reales), `edeng23`, `Haehnchen` («no listo para producción»), `pycryptobot`.
- **Marcos sin estrategias empaquetadas:** `banbot` (AGPL, Go), `solie` (GPL, GUI), `cassandre` (Java, GPL), `octobot` (GPL; tracker y métricas de comunidad).

## 5. Licencias: qué obliga el modo B con GPL-3.0 / AGPL-3.0
*Esto es un análisis de riesgo para decidir, no asesoría legal. Si el proyecto va a distribuirse o comercializarse, consultar a un abogado.*

Afecta a: Freqtrade, freqtrade-strategies, NFI, OctoBot y OctoBot-MM (GPL-3.0), banbot y backtesting.py (AGPL-3.0), backtrader y los demás GPL (solo referencia).

| Uso | GPL-3.0 | AGPL-3.0 |
|---|---|---|
| **Personal/privado** (ejecutarlo, estudiarlo, modificarlo y usarlo en tu equipo) | **No obliga a publicar nada.** Las obligaciones nacen al *distribuir* copias | Igual, salvo §13 |
| **Distribuir** el bot a otros (incluido empaquetarlo en un instalador de EIM) | Hay que ofrecer el **código fuente completo del bot** (con tus cambios) bajo GPL-3.0 y conservar avisos | Igual |
| **Ofrecer a terceros por red** una versión **modificada** | No es «distribución»: no obliga | **§13 obliga** a ofrecer el código fuente de esa versión a quienes interactúan con ella por red |
| **EIM llamando al bot como proceso aparte** (archivos o REST local) | Según el criterio habitual (FSF: comunicación entre programas separados por pipes, sockets o argumentos), **no convierte a EIM en obra derivada** mientras no compartan estructuras de datos íntimas ni se enlacen en un proceso | Igual |
| **Importar el código del bot desde `eim/`** (modo A con GPL) | EIM + bot serían probablemente **una sola obra** → todo EIM bajo GPL-3.0 si se distribuye. **Prohibido en este plan** | Ídem y, además, §13 si se usa por red |
| **Traducir/portar línea a línea** una estrategia GPL a Python propio | Es una obra derivada: hereda la GPL. La **idea** o regla de manual (cruce de medias, Bollinger) no está protegida; la **expresión** del código sí → por eso es modo C (reimplementar con pruebas propias), no A | Ídem |

Consecuencias para este plan:
1. Los bots GPL/AGPL corren **solo por proceso aislado, sin claves**, intercambiando velas y posturas por **archivos simples** (Parquet/JSON). El shim que importa `freqtrade` es GPL y se queda en su carpeta aislada, marcada, no se importa desde `eim/`.
2. **No distribuir los bots GPL junto con EIM.** Se instalan desde su origen con el SHA fijado de la ficha (instrucciones, no copia): así no hay «conveyance». Si algún día EIM se distribuye o se ofrece como servicio, esta decisión se reabre (AGPL fuera del servicio).
3. Lo licenciado permisivo (Hummingbot Apache-2.0, Jesse/trendrider/alpha-rptr MIT, Passivbot Unlicense) puede portarse con su aviso en `THIRD_PARTY.md`; Apache-2.0 pide además conservar `NOTICE` y marcar los cambios.
4. Casos especiales: OctoBot-Tentacles es **LGPL-3.0** pero depende de OctoBot (GPL-3.0) → en la práctica GPL; **vectorbt** lleva *Commons Clause* (no es código abierto: prohíbe vender el software o servicios que sean sustancialmente él); sin `LICENSE` = todos los derechos reservados (R2).
5. Las **posturas que el bot produce son datos**; la licencia del programa no los cubre. Aun así se guardan con el SHA y la licencia del bot que las generó (`BotSignal.version`).

## 6. Propuesta para la decisión del usuario (◆) — qué entra a T58
T56 recomienda esta lista; **nada de esto está aprobado** (`approval.state = pendiente` en las 50 fichas). El usuario puede aprobarla, recortarla o ampliarla **por escrito**; el estado de cada ficha lo cambia solo esa decisión.

| Oleada T58 | Ficha | Modo | Recomendación | Motivo corto |
|---|---|---|---|---|
| 1 | `hummingbot-directional` | A | **Aprobar** | Licencia Apache-2.0, lógica separable, activa, futuros USDⓈ-M |
| 1 | `jesse-example-strategies` | A | Opcional | MIT pero sin mantenimiento ni pruebas; aporte esperado bajo |
| 1 | `trendrider-strategy` | A | Opcional | MIT, un archivo, origen promocional, solo largos |
| 2 | `freqtrade` (ejecutor) + `freqtrade-strategies` | B | **Aprobar** | Activos, futuros, pruebas; exige aceptar GPL-3.0 por proceso aislado y entorno Python 3.12 |
| 2 | `nostalgia-for-infinity` | B | Opcional | La más usada de la comunidad, pero 5 m, promediado y 400 000 líneas |
| 3 | `passivbot` | L / B | **Aprobar** | Dominio público, activo, único grid/inventario dedicado a perpetuos; no vota |
| 4 (IA) | — | — | **Ninguna ahora** | TradingAgents/AI Hedge Fund/AI-Trader/FinRL no aportan postura reproducible; los LLM ya informan por T24; reevaluar tras T59 |

**Decisiones que se piden:**
1. ¿Apruebas la lista de arriba (o cuál)? Es la condición para que T58 empiece.
2. ¿Aceptas el **riesgo de licencia GPL-3.0 en modo B** (uso personal/privado, bots instalados desde su origen y **sin distribuirlos con EIM**)? Si no, Freqtrade/NFI pasan a «solo referencia» y la oleada 2 desaparece.
3. ¿Aceptas un **segundo entorno de Python 3.12** (y toolchain de Rust para Passivbot en Windows) solo para el modo B?
4. ¿NFI sí o no? (Exige velas de 5 min, que hoy el almacén guarda solo como almacén.)
5. Expectativa: **«ninguno validado» es un resultado válido** de T59; los costos de perpetuos y Holm sobre todos los intentos (incluidos los descartados) harán que casi ninguno vote.

## 7. Cómo se verificó y cómo repetirlo
- Clon: `git -c core.hooksPath=/dev/null clone --depth 1 --no-tags --no-recurse-submodules` en un directorio aislado fuera del proyecto; sin `pip`, `npm`, `cargo` ni ejecución de scripts.
- Escáner de solo lectura (Python `-I`): cuenta archivos de código, pruebas, patrones de `pickle`/`eval`/`exec`/`subprocess`/retiros/telemetría/Binance USDⓈ-M, dominios citados, hash de licencias. Las cifras de patrones son **aproximadas** y las coincidencias relevantes se leyeron a mano (retiros: campos de datos y SDK ajenos, no flujos de fondos; `pickle` de Passivbot/Freqtrade: archivos propios).
- Fichas: se regeneran de los escaneos; `tests/bots/test_registry_cards.py` valida el esquema, recalcula las sumas con las reglas de `SCHEMA.md`, exige modo B para GPL/AGPL propuestos y que ninguna ficha propuesta esté deshabilitada por seguridad, y que **ninguna aprobación esté marcada** hasta que el usuario decida.
- Para repetir un SHA: `git clone <repo> && git checkout <commit_sha>` y `git diff` contra el estado actual antes de adaptar nada (T57/T58 fijan esa versión).

## 8. Decisión del usuario (◆), 2026-10-19
Respuesta escrita: «Sí a 1, 2 y 3; en la 4 acepto la más recomendada».
1. **Lista aprobada para T58:** `hummingbot-directional` (A, oleada 1), `freqtrade` + `freqtrade-strategies` (B, oleada 2) y `passivbot` (L, B, oleada 3). Oleada 4 (IA): ninguna.
2. **Riesgo de licencia GPL-3.0 en modo B aceptado** (uso personal/privado; bots instalados desde su origen con el SHA de la ficha; no se distribuyen con EIM). Se reabre si EIM se distribuye o se ofrece como servicio.
3. **Segundo entorno de Python 3.12 aceptado** para el modo B (y toolchain de Rust para Passivbot en Windows).
4. **NFI:** se sigue la recomendación (opcional) → **no entra ahora**. Tampoco `jesse-example-strategies` ni `trendrider-strategy` (opcionales). Quedan en `pendiente`: se pueden aprobar más adelante sin repetir la auditoría.
Las 4 fichas aprobadas llevan `approval = {aprobada, usuario, 2026-10-19}`; el resto sigue `pendiente`.

### Decisión del usuario (◆), 2026-10-20 — ampliación del escuadrón
Aprobación escrita de los tres opcionales que la decisión del 2026-10-19 dejó fuera: `nostalgia-for-infinity` (B, GPL-3.0, velas de 5 min, promedia a la baja; mismo riesgo de licencia aceptado en el punto 2: uso privado, sin distribuir, entorno Python 3.12 aparte), `jesse-example-strategies` (A, MIT) y `trendrider-strategy` (A, MIT). Sus fichas pasan a `approval = {aprobada, usuario, 2026-10-20}` y `squad_proposal = propuesto`. Siguen sujetos a la misma puerta de T49 (T59): aprobar no es validar. El punto 4 de arriba queda reemplazado para estos tres.
