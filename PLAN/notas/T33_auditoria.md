# T33 — Auditoría de repos y fuentes (copy trading, arbitraje, calendario, indicadores)
Fecha: 2026-10-13 · Método: metadatos vía API de GitHub y PyPI, clones superficiales aislados fuera del proyecto (`C:\t33clones`; hummingbot y ccxt en checkout parcial) y lectura de documentación oficial y términos. **No se ejecutó ni instaló código de terceros**: solo `grep` y lectura. Las releases binarias (APK) no se descargaron.
Limitación: el análisis de código es por patrones (pickle/eval/exec/subprocess/telemetría/red/claves) más la lectura de los módulos citados; no es una auditoría línea a línea. La investigación previa del usuario se trató como hipótesis y se contrastó con el código.

## 🚩 Alertas (leer primero)
1. **`Hype-W/app-hyperliquid-copy-trading` — patrón de señuelo de malware.** El repo solo contiene `README.md` y un `LICENSE` de 81 KB con **2068 líneas `<!-- Updated: … -->`** (relleno para simular actividad). Tiene un único commit, una cuenta creada el mismo día del repo (2026-06-21) y 1 repo público, y lo único que ofrece es un **APK de 98,8 MB** en releases que pide "connect your wallet". No hay código fuente que auditar. **Descartar; no descargar el APK.**
2. **`incorebot/binance-scrape2trade` usa endpoints privados de Binance con la sesión del navegador.** Concretamente `bapi/asset/v1/private/future/smart-money/profile/query-positions` y `…/friendly/…/chart-data` (`scraper/binance_scraper.py:5,65,92`). La extensión MV3 captura el `csrftoken` de las cabeceras con `webRequest` y recarga pestañas de Binance (`extension/background.js:14-58`). La variante CDP conecta un Chrome con `--remote-debugging-port=9222` y lee sus cookies (`scraper/cdp_session.py`). Para operar usa además la clave API de Binance en `config.py`. Proyecto de 2★ y 4 meses de antigüedad, con comentarios en turco. **`robots.txt` de binance.com: `Disallow: */bapi/`** para todos los agentes. **Descartar** (detalle en §2).
3. **Hyperliquid NO tiene endpoint oficial de leaderboard.** La documentación de `/info` lista 29 tipos y ninguno es `leaderboard` ni `vaultSummaries`. Lo que usan los sitios de seguimiento (`stats-data.hyperliquid.xyz`) no está documentado. Para el descubrimiento de líderes hay que construir el universo de direcciones con fuentes oficiales (ver §3).
4. **Hummingbot envía telemetría activada por defecto.** `anonymized_metrics_mode` tiene por defecto `AnonymizedMetricsEnabledMode()` (`hummingbot/client/config/client_config_map.py:845-846`), que manda el volumen operado a `https://api.coinalpha.com/reporting-proxy-v2` (`hummingbot/connector/connector_metrics_collector.py:29,147`). Solo sirve como referencia; si alguna vez se ejecuta, desactivarlo.
5. **`MaxIsOntoSomething/Hyperliquid_Copy_Trader` firma mal las órdenes.** `_sign_action` firma siempre el mismo mensaje EIP-712 con `connectionId = 0x00…0` en lugar del hash de la acción (`src/copy_engine/executor.py:72-121`). Las órdenes reales no pueden validarse, y el programa pide la **clave privada principal** de la wallet (`HYPERLIQUID_PRIVATE_KEY`), no una *agent wallet*. Además deja `executor_old.py` como código muerto y no tiene tests. Solo referencia de la parte de monitorización.
6. **`Gajesh2007/copytrading-agent` SIN `LICENSE`** (GitHub: ninguna). Su README dice "This code is not audited" y "No automated tests are bundled", aunque `package.json` declara un script `test` sobre `tests/` y esa carpeta no existe. Lo usaron para gestionar vaults con depósitos de terceros (nof1.ai). **No copiar código**; la idea de reconciliación (≈87 líneas en `src/services/reconciler.ts`) se reimplementa.
7. **pandas-ta (twopirllc) ya no es fiable.** El repo de GitHub devuelve **404**. En PyPI quedan solo 2 versiones beta (`0.4.67b0` y `0.4.71b0`, 2025-09), **sin licencia declarada**, con `requires_python>=3.12` (EIM admite 3.11) y `numba==0.61.2` fijado. **Descartar.** El sucesor activo es `pandas-ta-classic` (fork MIT, ver la tabla).
8. **`counterfactual5/funding-arb` mueve fondos entre exchanges.** Tiene `scripts/transfer/cross_venue_router.py` y flujos de *withdraw*/*deposit* en `orchestrate_funding.py`, lo que exige claves con permiso de retiro y choca con la regla del proyecto. Proyecto joven (creado 2026-06, 9★). Es MIT, tiene 31 tests y sus llamadas a `subprocess` son benignas (cifrado de credenciales con `systemd-creds`/`age`). Opcionalmente publica *snapshots* en GitHub Pages. Solo referencia.
9. **Arbitraje triangular = no viable.** El README de `MfaXyz` admite que la ejecución "does not work properly and you will most likely lose money", es de KuCoin y tiene las claves en el código. `rayguang` no tiene licencia, está muerto desde 2019 y usa `apikeys.py` con las claves en un archivo. Ambos **Descartar**.
10. **Hallazgo colateral (fuera de T33): Binance Vision.** `data.binance.vision` publica unos términos "Binance Vision – Terms of Use (Non-Commercial)" marcados **[Draft]**. Fuentes secundarias dicen que limitan el uso a investigación o backtesting personal no productivo y excluyen la ejecución en vivo y la distribución de señales. No pude extraer el texto del PDF para confirmarlo. EIM los usa en `v2/eim/data/providers/liquidations.py` → anotado en BACKLOG para verificarlo antes de pasar a dinero real.
11. **Binance ya ha baneado cuentas por "herramientas de terceros no autorizadas"** (más de 600 en oct-2025, The Block). Es otro motivo para no automatizar contra endpoints web no documentados con la sesión del usuario.
12. **Binance**: `binance-futures-connector-python` está **DEPRECATED** (lo dice su README). El oficial vigente es el monorepo modular `binance/binance-connector-python` (paquete `binance-sdk-derivatives-trading-usds-futures` 17.6.0, 2026-10-06, MIT). Su cliente oficial `copy_trading` solo expone *tu propio* estado de lead trader y la *whitelist* de símbolos: **no hay API oficial para leer posiciones de otros traders.**

## Resumen de veredictos
| Candidato | Área | Veredicto | Cómo |
|---|---|---|---|
| API pública de Hyperliquid (`/info` + WS) | Copy | **Usar** | Fuente base de líderes y posiciones; sin claves para leer |
| `hyperliquid-dex/hyperliquid-python-sdk` | Copy/Arb | **Usar** (T45/T46) | Dependencia pip MIT para firmar en testnet; para leer basta con `requests`/WS en `data/` |
| `Gajesh2007/copytrading-agent` | Copy | **Referencia (no copiar)** | Sin LICENSE; idea de reconciliación líder→seguidor |
| `MaxIsOntoSomething/Hyperliquid_Copy_Trader` | Copy | **Referencia** | MIT; firma rota; solo patrón de monitor/WS |
| `incorebot/binance-scrape2trade` | Copy | **Descartar** | Endpoints privados + sesión robada al navegador; `robots.txt` lo prohíbe |
| `Hype-W/app-hyperliquid-copy-trading` | Copy | **Descartar** | Señuelo: solo APK, sin código |
| `binance/binance-connector-python` | Arb/Exec | **Usar** | Conector oficial MIT (preferido a CCXT en Binance) |
| `binance-futures-connector-python` | Arb/Exec | **Descartar** | Deprecado por Binance |
| `ccxt/ccxt` | Arb | **Usar (solo 2.º venue)** | MIT, muy activo (commit 2026-10-13); solo donde no haya conector oficial |
| `hummingbot/hummingbot` | Arb | **Referencia** | Apache-2.0; `spot_perpetual_arbitrage` y `arbitrage_executor`; telemetría por defecto |
| `counterfactual5/funding-arb` | Arb | **Referencia** | MIT; escáner de funding multi-venue útil como idea; transfiere fondos |
| `aoki-h-jp/funding-rate-arbitrage` | Arb | **Referencia** | MIT; sin actividad desde 2023-11; comisiones fijas de 2023 en código |
| `MfaXyz/Crypto-Triangular-Arbitrage-Bot` | Arb | **Descartar** | Pierde dinero según su README; KuCoin |
| `rayguang/…triangulararbitragebot` | Arb | **Descartar** | Sin licencia; abandonado 2019 |
| TA-Lib (`ta-lib-python`) | Ind | **Usar** | BSD-2; wheels Windows cp311–cp315 con la librería C incluida; referencia de precisión |
| `pandas-ta-classic` | Ind | **Usar (opcional)** | MIT; activo; tests comparan contra TA-Lib; numba opcional |
| `ta` (bukosabino) | Ind | **Referencia** | MIT; puro pandas; última versión PyPI 2023-11 |
| pandas-ta (twopirllc) | Ind | **Descartar** | Repo eliminado; PyPI sin licencia, solo betas |
| tulipy | Ind | **Descartar** | LGPL-3.0; sin versiones desde 2019; compila C |
| FRED API (releases) | Cal | **Usar** | Fechas oficiales; sin hora ni previsiones; aviso de atribución obligatorio |
| federalreserve.gov (FOMC) | Cal | **Usar** | Fechas FOMC oficiales (RSS); 2026 restante: 27-28 oct, 8-9 dic |
| BLS (`bls.ics`) | Cal | **Usar** | ICS oficial con hora ET (CPI y empleo 08:30 ET) |
| BEA (`release_dates.json` + ICS) | Cal | **Usar** | JSON/ICS oficial (PIB, PCE) 08:30 |
| Finnhub (calendario) | Cal | **Pendiente (no verificado)** | La documentación no confirma campos ni plan gratuito; probar con clave antes de decidir |
| Trading Economics | Cal | **Referencia / pago** | Consenso y real; precio a medida (sin tarifa pública) |
| Feeds comunitarios (p. ej. espejos ForexFactory) | Cal | **Descartar** | Sin licencia ni ToS claros |
| HyperStats/HyperTracker/HyprSwarm/HyperX | Copy | **Referencia de métricas** | No se integran; usan datos no documentados |

## Detalle por área

### 1. Copy trading
| Campo | Hyperliquid oficial | copytrading-agent (Gajesh) | Copy_Trader (Max) | scrape2trade (incorebot) | Hype-W |
|---|---|---|---|---|---|
| Licencia (archivo real) | SDK: `LICENSE.md` MIT © Hyperliquid Labs | **Ninguna** | `LICENSE` MIT 2026 | `LICENSE` MIT 2026 | `LICENSE` MIT relleno de 2068 líneas |
| Última actividad | SDK 2026-06-04 (v0.24.0), 1,85k★ | 2025-12-25, 52★ | 2026-06-03, 44★ | 2026-07-08, 2★ | 2026-07-17 (solo LICENSE) |
| Tests | `tests/` con *cassettes* (info, signing) | No (el script apunta a una carpeta inexistente) | No | 2 (`tests/test_engine.py`, `test_tracker.py`) | — |
| Claves | Firma local con `eth-account`; admite `approve_agent` (agent wallet sin retiro) | `FOLLOWER_PRIVATE_KEY` en `.env` | Clave privada principal en `.env` | Clave API de Binance + cookie/CSRF de sesión | "Connect your wallet" en un APK |
| Red / telemetría | Solo `api.hyperliquid.xyz` / testnet | `api.hyperliquid.xyz`, `nof1.ai`, `eigencloud.xyz` (front) | `api.hyperliquid.xyz`, Telegram | `binance.com/bapi`, Telegram, `127.0.0.1:8777` | Desconocida (binario) |
| exec/pickle | No | No | No | No (pero CDP + `webRequest`) | — |

**Datos oficiales útiles** ([docs `/info`](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint), [límites](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits), [WS](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions)):
- Posiciones: `clearinghouseState` (peso 2). Historial: `userFills` (los últimos 2000), `userFillsByTime` (2000 por respuesta, últimos 10 000), `portfolio` (rendimiento por periodo), `vaultDetails`, `historicalOrders`.
- Límites por IP: 1200 de peso por minuto en REST. En WS: **10 usuarios únicos como máximo** en suscripciones de usuario, 1000 suscripciones y 10 conexiones.
- **Descubrimiento de direcciones sin leaderboard**: el WS `trades` incluye `users: [buyer, seller]` en cada operación. Así se puede muestrear el universo de traders activos de forma oficial y luego puntuarlos con `portfolio`/`userFills`. Los vaults se leen con `vaultDetails`.
- Implicación de diseño para T40/T42: seguir en tiempo real a ≤10 líderes por WS y al resto por *polling* de `clearinghouseState`.

### 2. Términos de Binance (leaderboard y endpoints no documentados)
- **Hechos verificados:** `robots.txt` de binance.com contiene `Disallow: */bapi/` (y `*/api/`, `*/fapi/`) para `User-agent: *`. Los endpoints de smart-money/leaderboard están bajo `/bapi/`. No existen en ninguna API oficial: el cliente oficial `copy_trading` solo da el estado propio y la whitelist. El propio README de incorebot reconoce que "Binance shut down its public leaderboard API". Su acceso exige cookie de sesión y `csrftoken`, es decir, autenticarse como el usuario con un cliente no oficial. Binance ha baneado cuentas por herramientas de terceros no autorizadas ([The Block, 2025-10-20](https://www.theblock.co/post/375278/binance-bans-more-than-600-accounts-over-unauthorized-third-party-tools)).
- **No verificado:** el texto exacto de la cláusula de uso prohibido de los Términos de binance.com (la página no se pudo extraer).
- **Conclusión:** el permiso no está claro, como mínimo, y las señales apuntan a que no se permite. Según el criterio de T33, **no se automatiza.** Binance queda solo para **uso manual/analítico**: el usuario mira un perfil y, si quiere, introduce a mano una dirección o idea. Nunca hay *scraping* ni extensión ni CDP.

### 3. Arbitraje
| Campo | binance-connector-python | ccxt | hummingbot | funding-arb (cf5) | funding-rate-arbitrage (aoki) |
|---|---|---|---|---|---|
| Licencia | MIT | `LICENSE.txt` MIT © Igor Kroitor | `LICENSE` Apache-2.0 | MIT 2026 | `LICENSE.md` MIT 2023 |
| Última actividad | 2026-10-12 | 2026-10-13 (4.5.87) | 2026-09-22; 20k★ | 2026-08-21 | 2023-11-05 |
| Tests | Por cliente | Amplios (no clonados) | 691 archivos en `test/` | 31 | 0 |
| Claves | API key/secret (testnet admitido) | Ídem | Cifradas en su cliente | keyring/systemd-creds/age; incluye retiro | No (solo lectura vía ccxt) |
| Red / telemetría | Solo Binance | Solo exchanges | **Métricas por defecto → coinalpha.com** | Exchanges + Telegram + GitHub Pages opcional | Exchanges |
| exec/pickle | — | No (`base/exchange.py`) | No en los módulos revisados; Cython | `subprocess` benigno | No |

Fragmentos a estudiar (idea, no copia): `hummingbot/strategy/spot_perpetual_arbitrage/{arb_proposal.py,spot_perpetual_arbitrage.py}` (845 líneas en total), `hummingbot/strategy_v2/executors/arbitrage_executor/arbitrage_executor.py`, el escáner `scripts/cli/scan_funding_arbitrage.py` de cf5 y `frarb.py:get_large_divergence_dataframe_*` de aoki.

### 4. Indicadores técnicos
| Campo | TA-Lib | pandas-ta-classic | ta | pandas-ta | tulipy |
|---|---|---|---|---|---|
| Licencia | `LICENSE` BSD-2 | `LICENSE` MIT | `LICENSE` MIT | PyPI sin licencia; repo 404 | `LICENSE` LGPL-3.0 |
| Mantenimiento | 0.8.2 (2026-10-12), 12k★ | 0.8.32 (2026-09-14), commit 2026-10-13, 455★; contribuidores xgboosted y twopirllc (autor original) | PyPI 0.11.0 (2023-11); repo 2026-03 | Betas 2025-09 | 0.4.0 (2019) |
| Windows | Wheels `win_amd64` cp311–cp315 con la librería C incluida | Puro Python (numba opcional) | Puro Python | numba fijado | Compila C |
| Tests / precisión | 7 módulos de test | 60 archivos; `assert_talib` contra TA-Lib | `test/unit`, `test/integration` | — | 2 |
| Red / pickle | No | `multiprocessing` (pickle interno); extras `data` opcionales con yfinance (no instalar) | No | — | No |

Recomendación: TA-Lib como **referencia de precisión** en los tests y pandas-ta-classic **opcional**. Los agentes siguen siendo puros (las librerías solo calculan sobre el snapshot).

### 5. Calendario económico
| Fuente | Licencia / ToS | Previsto / real / revisado | Hora y zona | Coste |
|---|---|---|---|---|
| FRED `fred/releases/dates` ([ToS](https://fred.stlouisfed.org/docs/api/terms_of_use.html), [doc](https://fred.stlouisfed.org/docs/api/fred/releases_dates.html)) | Clave gratuita; atribución obligatoria ("This product uses the FRED® API…"); las series con copyright de terceros solo para uso personal | Solo fechas (las futuras con `include_release_dates_with_no_data=true`); los valores reales vía series/ALFRED (con revisiones) | **Sin hora** | Gratis |
| Fed FOMC ([calendario](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)) | Dominio público EE. UU. | Fechas; decisión 14:00 ET (convención, no en la página) | Fechas | Gratis; RSS, sin ICS |
| BLS ([ICS](https://www.bls.gov/schedule/news_release/bls.ics)) | Dominio público EE. UU. | Fechas y hora; valores vía API pública BLS | **ET explícito** (CPI/NFP 08:30) | Gratis |
| BEA ([JSON](https://apps.bea.gov/API/signup/release_dates.json), ICS) | Dominio público EE. UU. | Fechas y hora | 08:30 (zona no indicada, ET de facto) | Gratis |
| Finnhub | No verificado | No verificado | — | Probablemente premium |
| Trading Economics ([API](https://tradingeconomics.com/api/calendar.aspx)) | Comercial; precio a medida | Real, consenso y previsión propia | Sí | De pago |

Ninguna fuente oficial gratuita da el **consenso**. Sin pagar, el agente de calendario puede marcar *ventanas de evento* (fecha y hora, impacto alto) y el valor real con revisión, pero no la "sorpresa" frente al consenso. Esa cifra debe mostrarse como no disponible y nunca inventarse.

## Propuesta de alcance (decisión del usuario; sin su visto bueno T40 no empieza)
1. **Fuente de líderes:** la API pública oficial de Hyperliquid (`/info` + WS) como única fuente automatizada. El universo de direcciones sale de muestrear el WS `trades` (`users`) y de los vaults (`vaultDetails`), y se puntúa con `portfolio`/`userFills`. **Binance: solo manual/analítico** (sin scraping, extensión ni CDP). Los sitios de seguimiento solo se usan para comparar métricas.
2. **Modo, por etapas:** (a) **señales y alertas** sin órdenes (T40–T42), luego (b) **simulación** con el motor de backtest/paper, y después (c) **testnet** de Hyperliquid con *agent wallet* (`approve_agent`, sin permiso de retiro) tras T30 (T46). Seguimiento en tiempo real de ≤10 líderes por WS.
3. **Calendario:** fuentes oficiales gratuitas (FOMC + BLS ICS + BEA JSON + FRED con atribución), normalizadas a UTC. Consenso marcado como "no disponible". Finnhub o Trading Economics solo si el usuario decide pagar (evaluar con clave en una tarea aparte).
4. **Arbitraje:** solo funding/basis entre perpetuos (sin triangular ni transferencias entre exchanges). Conector oficial de Binance, más ccxt o el SDK de Hyperliquid para la segunda pata. Cada pata con su capital, sin retiros automáticos.
5. **Indicadores:** TA-Lib (referencia y tests) y, opcionalmente, pandas-ta-classic.
