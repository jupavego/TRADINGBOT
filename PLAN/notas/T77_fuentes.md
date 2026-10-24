# T77 — Verificación en la fuente (Binance) y veredicto de repositorios

Fecha de consulta: **2026-10-23** (UTC). Método: la propia API de Binance (`exchangeInfo`, tabla pública de comisiones), la documentación oficial completa (`https://developers.binance.com/en/docs/llms-full.txt`, `Last-Modified` 2026-10-23 12:19 UTC; los documentos se citan por su ruta), PyPI (API JSON), GitHub (API y clones superficiales aislados en la carpeta temporal de la sesión, **sin ejecutar** código de terceros) y dos entornos virtuales aparte para las pruebas de importación (nada se instaló en el proyecto). Evidencia guardada: `v2/reports/hft_fuentes/exchangeinfo_2026-10-23.json` y `comisiones_usdm_2026-10-23.json`. Lo que no se pudo verificar queda marcado **(sin verificar)**.

## 1. Binance USDⓈ-M

| Tema | Verificado | Fuente | Frente al proyecto |
|---|---|---|---|
| Peso por IP (REST) | `REQUEST_WEIGHT` 2400/min; cabecera `X-MBX-USED-WEIGHT-1M`; 429 → 418 (bloqueo de 2 min a 3 días); límites por IP, no por clave | `GET /fapi/v1/exchangeInfo`; `/products/derivatives-trading-usds-futures/general-info` | A las 21:00 UTC la IP ya gastaba **291/2400** (servicio continuo, recolectores, líderes): el carril HFT debe usar WebSocket y no sondear por REST. |
| Órdenes | `ORDERS` 1200/min y **300/10 s** por cuenta, compartido entre REST y WS API | `exchangeInfo`; `websocket-api-general-info` | Techo duro para cualquier esquema de cotización: ≤ 30 órdenes/s sostenidas. |
| WS API (órdenes) | `wss://ws-fapi.binance.com/ws-fapi/v1` (testnet `wss://testnet.binancefuture.com/ws-fapi/v1`); peso por IP propio (no compartido con REST salvo órdenes); el *handshake* cuesta 5; ≤ 5 ping/pong por s; conexión de 24 h; `session.logon` **solo con claves Ed25519**; métodos `order.place/modify/cancel/status`, `userDataStream.*` | `websocket-api-general-info`; catálogo «Futures (USDⓈ-M) WebSocket API» de `llms.txt` | **No existe `order.test` en el WS API de futuros**: solo REST `POST /fapi/v1/order/test` (firmado, permiso TRADE). `ping` y `time` no figuran en el catálogo de futuros pero respondieron `200` en la prueba (con `rateLimits`). |
| Flujos de mercado | Raíz partida: `/public` (`depth`, `bookTicker`), `/market` (`aggTrade`, `markPrice`, `kline`, `forceOrder`…), `/private` (`listenKey`); una conexión sin ruta solo recibe lo de `/public`; retiro de las URL sin ruta anunciado para **2026-04-23**; 10 mensajes entrantes/s por conexión, 1024 flujos, 24 h, ping cada 3 min y pong en ≤ 10 min | `websocket-market-streams/Important-WebSocket-Change-Notice`, `/Connect` | Probado hoy: `/stream` sin ruta aún entrega `bookTicker` pero **ya no `markPrice`**. El recolector T23 (`binance_ws.py`, `WS_DEPTH`) sigue en la URL sin ruta → BACKLOG. `liq_ws` y la API ya usan `/market`. |
| Libro y RPI | Las órdenes RPI (post-only, solo casan con órdenes de App/Web) **no aparecen** en `depth`, `bookTicker` ni `GET /fapi/v1/depth`; `aggTrade.nq` excluye operaciones RPI (desde 2025-12-31) | `change-log` 2025-11-18 y 2025-12-29 | El L2 que vemos no es todo el libro: el simulador (T79) debe tratarlo como cota y medir su sesgo. |
| BTCUSDT (filtros) | tick **0,10**; paso **0,001**; mín. 0,001 / máx. 1000 (límite) y 120 (mercado); **nocional mínimo 50 USDT**; `PERCENT_PRICE` ±3 %; 200 órdenes abiertas; `timeInForce` GTC, IOC, FOK, **GTX**, GTD; `marketTakeBound` 0,03; comisión de liquidación 1,25 % | `exchangeInfo` (21:00:59 UTC) | Coincide con `SymbolSpec` de T108 (0,1/0,001/0,001); el nocional mínimo de 50 USDT no estaba en la ficha. |
| Comisiones | VIP 0: **maker 0,0200 %, taker 0,0500 %** (= `CostParams` 2/5 pb). VIP 1: 0,018/0,050 · VIP 2: 0,016/0,040 · VIP 3: 0,012/0,032 · … · VIP 9: 0,000/0,017 % | API pública de `https://www.binance.com/en/fee/futureFee` (`/bapi/composite/v1/public/commission/futures-trade-level/get`) | Ida y vuelta VIP 0: taker 10 pb, mixto 7, maker-maker 4 (confirmado). |
| Descuento BNB | **10 %** sobre la comisión estándar de USDⓈ-M si se paga con BNB en la cuenta de futuros → 1,8/4,5 pb (ida y vuelta 9 · 6,3 · 3,6 pb) | FAQ «Binance Futures Fee Structure & Fee Calculations» (`/en/support/faq/360033544231`, actualizada 2026-05-01) | Sensibilidad, no supuesto base: exige mantener BNB (riesgo de precio aparte). |
| Tipos de orden útiles | `GTX` = post-only; `reduceOnly`; `priceMatch` = OPPONENT, OPPONENT_5, QUEUE, QUEUE_5/10/20 (**OPPONENT_10/20 retirados** de alta/modificación desde 2025-10-23); STP `EXPIRE_TAKER/MAKER/BOTH`; condicionales por el Algo Service (`/fapi/v1/algoOrder`, desde 2025-12) | `common-definition`; `change-log` | El bróker de testnet (T30) ya usa `algoOrder` para SL/TP. |
| Errores ambiguos | HTTP 503 «Unknown error…» = **estado desconocido** (reconciliar antes de reintentar); `-1008` = sobrecarga, con *reduce-only*/cierre exentos | `general-info` | Coincide con `NetworkError` = «resultado desconocido» de `binance_rest.py`. |
| `listenKey` | Vale 60 min; `PUT` lo extiende 60 min (`-1125` = recrear); `POST` con uno activo devuelve el mismo; flujo en `wss://fstream.binance.com/private/ws/<listenKey>`; orden estricto por tipo de evento; usar `E` para ordenar entre tipos | `user-data-streams` | Para T83: estado de órdenes por el flujo de usuario, no por REST. |
| `countdownCancelAll` | `POST /fapi/v1/countdownCancelAll` (TRADE): cancela las órdenes abiertas del símbolo al vencer la cuenta atrás; se llama como latido | `change-log` 2020-05-11; catálogo REST | Parámetros exactos (**sin verificar**: la ficha del endpoint no está en `llms-full.txt`): T83 los confirma. Encaja con el kill-switch de T29. |
| `recvWindow` | por defecto 5000 ms; recomendado ≤ 5000 | `general-info` | Con desfase medido de ±decenas de ms, holgado. |
| Uso de datos | **(sin verificar en el texto)**: `binance.com/en/terms` no renderiza el texto desde este equipo; según el resumen del buscador, licencia de uso personal no comercial o interno, y los términos regionales de EE. UU. prohíben sin consentimiento los *feeds* o servicios basados en datos de Binance | `https://www.binance.com/en/terms` (no legible); resultados del buscador | Regla: uso interno, sin redistribuir ni publicar datos crudos. ◆ el usuario confirma con los términos de su cuenta. |

## 2. Veredicto de repositorios (formato T04)

| Repo | Veredicto | Cómo |
|---|---|---|
| HftBacktest | **Usar solo aislado** (o motor propio; ver decisiones) | Entorno aparte; nunca en el núcleo ni en la operación |
| SDK oficial de Binance | **Referencia** | No mejora la latencia; cliente propio |
| NautilusTrader | **No ahora** | Exige Python ≥ 3.12 |
| Hummingbot | **Referencia** | Avellaneda–Stoikov, gestión de órdenes |
| Cryptofeed | **Descartar** | AGPL-3.0 |
| mmb | **Descartar** | GPL-3.0 y sin mantenimiento |
| MOSAIC | **Sin identificar** | Falta el enlace; no copiar |
| HFT Lab Core | **Estudio selectivo** | Reimplementar ideas con pruebas propias |
| quant-research | **Sin identificar** | Falta el enlace; nada se porta |

### HftBacktest — USAR SOLO AISLADO
| Campo | Dato |
|---|---|
| URL / versión | https://github.com/nkaz001/hftbacktest · PyPI **2.4.4** (2025-12-10) |
| Licencia | MIT (clasificador de PyPI y GitHub) |
| Mantenimiento | Último push 2025-12-23 (**~10 meses**); 4 968★; 23 issues |
| Python | `>=3.11`; ruedas cp311–cp314 (Windows incluido) |
| Prueba de importación | Venv aparte con Python 3.12.10: importa en 3,3 s. Arrastra **`numpy<2.3`** (el proyecto usa 2.4.4), `numba~=0.61` (instaló 0,68 + llvmlite), polars, matplotlib, holoviews/bokeh/panel: **714 MB** |
| Formato de datos | Arrays estructurados `event_dtype` de 64 B (`ev, exch_ts, local_ts, px, qty, order_id, ival, fval`), en `.npz`; necesita `local_ts` (hora de recepción) por evento |
| Riesgos | Conflicto de numpy: no puede compartir entorno con `v2/`; el recolector T23 **no guarda la hora de recepción** (solo `E`/`T`); el bot en vivo es Rust y maneja claves (fuera de alcance) |

### SDK oficial de Binance — REFERENCIA
| Campo | Dato |
|---|---|
| URL / versión | https://github.com/binance/binance-connector-python (`clients/derivatives_trading_usds_futures`) · PyPI `binance-sdk-derivatives-trading-usds-futures` **18.1.0** (2026-10-23) |
| Licencia | MIT |
| Mantenimiento | Push 2026-10-23; **49 versiones, mayor 18**: mucha rotación de API. El conector anterior (`binance-futures-connector-python`) está marcado **DEPRECATED** |
| Dependencias | requests, urllib3, aiohttp, pycryptodome, pydantic, `binance-common==4.7.0` (fijada): segunda pila HTTP junto a httpx/websockets |
| ¿Mejora `binance_rest.py`? | **No en latencia**: los mismos servidores; RTT medido REST ≈ WS API (banco). Lo único nuevo útil es el WS API con `session.logon` Ed25519, implementable en un módulo propio pequeño sobre `websockets` (ya en el núcleo) |

### NautilusTrader — NO AHORA
| Campo | Dato |
|---|---|
| Versión | PyPI **1.231.0** (2026-08-02): `>=3.12,<3.15`, ruedas cp312–cp314; 2.0.0rc7 (2026-10-15) exige `>=3.13`; la última que admite 3.11 es **1.221.0** (2025-10-26) |
| Licencia / mantenimiento | LGPL-3.0; push 2026-10-23; 30,6 k★ |
| Compatibilidad | `pyproject.toml` declara `>=3.11` y el venv es 3.12.10: la versión estable solo entra subiendo el piso a 3.12. Sin cambio frente a T25 |

### Hummingbot — REFERENCIA
Apache-2.0 · PyPI 20260922 (2026-10-07), ruedas solo cp312 (sin rueda para Windows) · push 2026-10-20 · 20,7 k★. Solo lectura de Avellaneda–Stoikov y del ciclo de órdenes.

### Cryptofeed — DESCARTAR
PyPI 3.0.1 (2026-09-27), `>=3.13`; `LICENSE` = **AGPL-3.0 o posterior** (GitHub lo muestra como NOASSERTION). Ya existe el recolector propio.

### mmb — DESCARTAR
https://github.com/purefinance/mmb · GPL-3.0 · **último commit 2022-11-17** («stop-loss orders for Binance»), sin actividad en ~4 años; 617★. Rust, con `exchanges/binance` y `core_tests`. Ninguna línea se copia.

### MOSAIC — SIN IDENTIFICAR
Sin URL en el insumo; búsquedas en GitHub (`mosaic` + hft, orderbook, trading, market making) y en la web sin resultado. Regla mientras tanto: sin licencia verificada no se copia nada y sus métricas no cuentan. **Pendiente: el usuario aporta el enlace.**

### HFT Lab Core — ESTUDIO SELECTIVO
| Campo | Dato |
|---|---|
| URL | https://github.com/ThotDjehuty/hft-lab-core (el único resultado para «HFT Lab Core») |
| Licencia | MIT («HFThot Research Lab», 2026) |
| Mantenimiento | Creado 2026-02-20; **un único commit público** (v3.0.0, 2026-07-07); 1★, 0 forks |
| Pruebas visibles | No hay carpeta `tests/`, pero sí **130 `#[test]` en 19 archivos Rust** y CI con `cargo test` (la investigación decía «sin tests») |
| Público / propietario | Público: HMM (`optimization`), Hurst (`portfolio`), Rough Heston (`pricing`), señales geométricas, Uniswap. **Propietario**: `meanrev` y `sparse_meanrev` tras la bandera `proprietary`; la plataforma comercial se movió a un crate privado (`hfthot-lab-platform`) |
| Decisión | Reimplementar ideas (Hurst, HMM) con pruebas propias; no depender (un autor, sin historia pública) |

### quant-research — SIN IDENTIFICAR
Nombre ambiguo: homónimos como `letianzj/QuantResearch` (MIT, sin push desde 2023-08-26) o `bloomberg/quant-research` (sin licencia). Ninguno coincide con lo declarado («validación y pruebas, datos de EE. UU.»). **Pendiente: enlace del usuario**; nada se porta hasta entonces.

### Bibliotecas del extra `hft`
| Paquete | Versión (fecha) | Licencia | Python / ruedas | Nota |
|---|---|---|---|---|
| statsmodels | 0.15.0 (2026-08-30) | BSD-3 | ≥ 3.10; cp310–cp315 | — |
| arch | 8.0.0 (2025-10-21) | Tipo NCSA (permisiva, `LICENSE.md`) | ≥ 3.10; cp310–cp314 | GitHub la muestra como NOASSERTION |
| scikit-learn | 1.9.1 (2026-09-10) | BSD-3 | ≥ 3.11; cp311–cp315 | — |
| hmmlearn | 0.3.3 (2024-10-31) | BSD-3 | ≥ 3.8; cp38–cp313 | **«limited-maintenance mode»** (README); sin rueda para 3.14 |

Prueba en venv aparte (Python 3.12.10) con **numpy 2.4.4** (la del proyecto) + scipy 1.18.1: los cuatro importan y ajustan un caso mínimo (HMM de 2 estados, GARCH, OLS, ridge). Ocupan 404 MB con sus dependencias.
