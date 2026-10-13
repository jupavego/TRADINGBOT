# T04 — Auditoría de repos candidatos (licencia y seguridad)
Fecha: 2026-10-12 · Método: metadatos vía API de GitHub/HuggingFace, clones locales en `repos/` (solo lectura) y clones superficiales aislados fuera del proyecto (`C:\t04clones`: Kronos, TradingAgents, circuit-framework, QuantDinger). **No se ejecutó ni instaló código de terceros**; solo `grep` y lectura.
Limitación: el análisis de código es por patrones (pickle/eval/exec/subprocess/telemetría/red/claves) + lectura de los módulos citados; no es una auditoría línea a línea. Nautilus, Freqtrade y OpenBB (muy grandes) se auditaron solo a nivel de licencia/metadatos/estructura.

## 🚩 Alertas rojas / amarillas (leer primero)
1. **market-regime (kangchengX) — SIN LICENCIA.** Sin `LICENSE` ni licencia detectada en GitHub → todos los derechos reservados. **No se puede copiar código.** Solo reimplementar la idea (matriz de transición + entropía es matemática estándar).
2. **limit-order-book (mansoor-mamnoon) — licencia ambigua.** El README muestra un badge "MIT" pero **no existe archivo `LICENSE`** y GitHub no detecta licencia. Tratar como sin licencia → no copiar. Además es un proyecto personal (3★, 48 commits, último 2025-08). OFI se reimplementa con la fórmula pública (Cont-Kukanov-Stoikov); como referencia MIT verificada existe `Kautenja/limit-order-book`.
3. **OpenBB — el repo "oficial" redirige a otra organización.** `OpenBB-finance/OpenBB` resuelve hoy a `openbq-org/OpenBB` (org creada 2026-09-11, 8 repos; la org original sigue con 45 repos). Los commits son de mantenedores conocidos (Danglewood, dlee-bq) y el LICENSE es Apache-2.0 "OpenBB Inc.", así que parece una migración legítima, **pero no se pudo verificar fuera de GitHub**. Confirmar en openbb.co antes de depender de él; el nombre `openbq` parece typosquat: al instalar usar solo el paquete `openbb`.
4. **circuit-framework — fork joven de TradingAgents, no proyecto independiente.** `EthanXiang777/circuit-framework` creado 2026-07-16, último commit 2026-07-11, 281★ en <3 meses; su README admite ser fork de TradingAgents (paquete interno aún `tradingagents`). Procedencia dudosa y sin historial → **Descartar** como dependencia.
5. **Freqtrade/FreqAI = GPL-3.0 y Nautilus = LGPL-3.0.** Copiar/importar código de Freqtrade contagia GPL a EIM → solo referencia. Nautilus (LGPL) permite usarlo como dependencia, pero vendorizar/modificar obliga a publicar los cambios.
6. **TradingAgents puede enviar texto a un tercero.** `tradingagents/agents/post_screen.py` manda posts de Reddit/StockTwits a `https://api.typesafe.ai` ("Jev") **solo si existe `TYPESAFE_API_KEY`** (opt-in, sin clave no corre). No activar; eliminarlo si se reutiliza algo. QuantDinger promociona el mismo servicio.
7. **QuantDinger:** solo el backend es Apache-2.0; frontend/móvil con licencia "source-available" aparte; nombre/logo con política de marca. Ejecuta código de estrategias de usuario con `exec()` (`utils/safe_exec.py`; un sandbox Python no es frontera de seguridad), más billing/pagos multi-tenant e instaladores `install.sh/.ps1`. **Solo referencia; no ejecutar.**
8. **Kronos tiene ~6.8k forks.** Usar únicamente `shiyu-coder/Kronos` y los pesos `NeoQuasar/Kronos-*` (HuggingFace, MIT, formato `safetensors` sin pickle, paper arXiv:2508.02739). Fijar la revisión (SHA) al descargar. Último commit del repo: 2026-04-13. Los `examples/` y `finetune/` usan `pickle.load` y `pip install` por subprocess → **no importarlos**; usar solo `model/`.
9. **Kats pina dependencias antiguas** (`numpy<1.22`, `pandas<=1.3.5`, `statsmodels==0.12.2`, `packaging<22`): instalar el paquete completo es inviable. El BOCPD en sí solo necesita numpy/scipy/pandas/matplotlib + `kats.consts`/`kats.detectors.detector`.
10. **Claves:** ningún repo necesita claves para lo que EIM requiere. `hftbacktest/connector` (Rust) maneja `api_key`/`secret` de Binance Futures para trading en vivo → fuera de alcance. Regla del proyecto: solo claves de testnet sin permiso de retiro.

## Resumen de veredictos
| Repo | Veredicto | Cómo |
|---|---|---|
| Optuna | **Usar** | Dependencia pip (MIT) |
| Kronos (oficial) | **Usar (opcional, T16)** | Paquete `model/` + pesos fijados por SHA; MIT |
| hftbacktest | **Referencia** | MIT; ideas de cola/latencia; instalable si T26 lo pide |
| Kats (BOCPD) | **Referencia / copia puntual** | MIT: portar `bocpd.py` con aviso o reimplementar; no instalar `kats` |
| crypto_lob_stream_pypi | **Referencia** | MIT; proyecto joven (6★); adaptar patrones |
| TradingAgents | **Referencia** | Apache-2.0; patrón de orquestación |
| Nautilus Trader | **Referencia** | LGPL-3.0; dependencia solo si se adopta su motor |
| OpenBB | **Referencia** (verificar procedencia) | Apache-2.0 |
| Freqtrade/FreqAI | **Referencia (no copiar)** | GPL-3.0 |
| QuantDinger | **Referencia** | Apache-2.0 backend |
| circuit-framework | **Descartar** | Fork joven y dudoso |
| limit-order-book | **Referencia (no copiar)** | Sin LICENSE real |
| market-regime | **Referencia (no copiar)** | Sin licencia |

## Detalle por repo

### Optuna — USAR
| Campo | Dato |
|---|---|
| URL oficial | https://github.com/optuna/optuna (remoto del clon verificado) |
| Licencia | MIT (© 2018 Preferred Networks) + `LICENSE_THIRD_PARTY` |
| Mantenimiento | Push 2026-10-10; último commit local 2026-08-13; 21 issues; 14.9k★ |
| Decisión | Dependencia pip; no copiar código |
| Riesgos | Sin telemetría ni red en el núcleo (solo con storage RDB/Journal remoto). No cargar estudios de fuentes no confiables. Instalar solo el núcleo (integraciones opcionales aparte) |
| Reutilizable | `optuna.create_study()` + `objective(trial)` para calibrar umbrales (T27/T28); `samplers/_base.py` solo si se crea un sampler propio |

### Kronos — USAR (opcional)
| Campo | Dato |
|---|---|
| URL oficial | https://github.com/shiyu-coder/Kronos · pesos https://huggingface.co/NeoQuasar (mini/small/base; large no público) |
| Licencia | MIT (repo y pesos) |
| Mantenimiento | Último commit 2026-04-13; 281 issues; 40.6k★; pesos actualizados 2025-09 |
| Decisión | Usar `model/kronos.py` + `model/module.py` (vendorizar con aviso MIT o instalar desde commit fijado). Deps núcleo: `torch>=2`, `einops`, `huggingface_hub==0.33.1`, `safetensors`, `pandas`, `numpy` |
| Riesgos | Descarga de pesos por red (fijar `revision=<sha>`, caché local, cero red en tests); sin `trust_remote_code`; excluir `finetune/` y `examples/`. Su salida es una trayectoria muestreada: pasar por el wrapper probabilístico de EIM (N muestras → 3 escenarios + bandas, etiqueta "simulada"). Sin garantía de edge: se valida en el backtest (T27) |
| Fragmento reutilizable | `model/kronos.py`: `KronosTokenizer`, `Kronos`, `KronosPredictor.predict(df, x_timestamp, y_timestamp, pred_len, T, top_k, top_p, sample_count)` (l.519), `auto_regressive_inference` (l.389). `max_context` 512 (small/base), 2048 (mini) |

### hftbacktest — REFERENCIA
| Campo | Dato |
|---|---|
| URL oficial | https://github.com/nkaz001/hftbacktest |
| Licencia | MIT (© 2022 nkaz001) |
| Mantenimiento | Último commit 2025-12-23 (~10 meses); 24 issues; 4.9k★ |
| Decisión | Referencia de diseño; pip posible si T26/T29 lo piden (Rust+Numba, pesado) |
| Riesgos | `connector` gestiona `api_key`/`secret` de Binance Futures (trading en vivo): no usar; `collector` solo streams públicos |
| Fragmento reutilizable (concepto) | `hftbacktest/src/backtest/models/queue.rs` y `latency.rs` (fills realistas); `src/depth/mod.rs` (`trait MarketDepth`) |

### Kats (BOCPD) — REFERENCIA / COPIA PUNTUAL
| Campo | Dato |
|---|---|
| URL oficial | https://github.com/facebookresearch/Kats |
| Licencia | MIT (© Facebook) |
| Mantenimiento | Último commit 2026-07-27 (automático, "Pyre upgrade"); 66 issues; 6.5k★; desarrollo funcional estancado |
| Decisión | **No instalar `kats`.** Portar `kats/detectors/bocpd.py` (~1800 líneas; dividir en módulos ≤300) conservando el aviso MIT, o reimplementar Adams-MacKay con modelo normal |
| Riesgos | Sin red/pickle/eval en `bocpd.py` (grep). Hay que sustituir `kats.consts.TimeSeriesData` (1387 líneas) y `Detector` por arrays numpy |
| Fragmento reutilizable | `BOCPDetector` (l.258), `_BayesOnlineChangePoint` (l.681), `_NormalKnownPrec` (l.1206), `_BayesianLinReg` (l.1444) |

### crypto_lob_stream_pypi — REFERENCIA
| Campo | Dato |
|---|---|
| URL oficial | https://github.com/Goodie-Goody/crypto_lob_stream_pypi |
| Licencia | MIT (LICENSE + `license = "MIT"`) |
| Mantenimiento | Creado 2026-06-03; último commit 2026-07-02; 6★; un autor; tests por módulo |
| Decisión | Referencia; copiar solo fragmentos pequeños con aviso MIT tras revisarlos. No como dependencia de producción (sin historial) |
| Riesgos | Red solo vía `websockets.connect` a feeds públicos y REST de snapshots; sin pickle/eval/subprocess/telemetría (grep). Deps: `websockets`, `pyarrow`, `aiohttp`, `python-dotenv`. Extra opcional `[gcs]` requiere credenciales: no habilitar |
| Fragmento reutilizable | `reconstruct.py` (`BookReconstructor`, poda anti "ghost-level"); `streamer.py` `_check_gap` y reconexión con backoff; `schemas.py` (esquemas Arrow) |

### TradingAgents — REFERENCIA
| Campo | Dato |
|---|---|
| URL oficial | https://github.com/TauricResearch/TradingAgents |
| Licencia | Apache-2.0 |
| Mantenimiento | Push 2026-10-03; 106 issues; 110k★ |
| Decisión | Solo patrón (debate bull/bear → gestor → riesgo). Dependencias pesadas (langchain, langgraph, yfinance, redis) y orientado a acciones |
| Riesgos | Ver alerta 6. Fuentes de red: Reddit, StockTwits, SEC, FRED, Polymarket, Alpha Vantage (públicas o con clave propia). Sin eval/exec/pickle/telemetría fuera de tests (grep) |
| Reutilizable | Estructura `agents/` + `graph/` + `memory/` como inspiración para el agente de contexto LLM; no su código |

### circuit-framework — DESCARTAR
| Campo | Dato |
|---|---|
| URL | https://github.com/EthanXiang777/circuit-framework (fork, no hay repo "oficial" independiente) |
| Licencia | Apache-2.0 (heredada) |
| Mantenimiento | Creado 2026-07-16; 85 commits importados; 281★ (popularidad sospechosa para su edad) |
| Riesgos | Procedencia dudosa; paquete interno sigue llamándose `tradingagents` (colisión de nombre); `requirements.txt` solo contiene "." El README afirma que nunca llama al endpoint de Exchange de Hyperliquid; en `dataflows/hyperliquid.py` solo se ve `POST /info` (no verificado el resto) |
| Reutilizable (ideas) | snapshot inmutable de mercado, gate de riesgo determinista, paper trading en SQLite: se reimplementan en EIM |

### Nautilus Trader — REFERENCIA
| Campo | Dato |
|---|---|
| URL oficial | https://github.com/nautechsystems/nautilus_trader |
| Licencia | LGPL-3.0 |
| Mantenimiento | Muy activo (push diario; release v1.231.0 de 2026-08-02; 125 issues; 29.9k★); tiene SECURITY.md, deny.toml, osv-scanner, CLA |
| Decisión | Referencia. Dependencia pip solo si se adopta su motor (T29+); no vendorizar ni modificar. Hay `MIGRATION_V2.md` → API en transición |
| Riesgos | Adaptadores con manejo de claves; núcleo Rust/Cython; no revisado línea a línea |
| Reutilizable | Patrón de ciclo de vida de órdenes (T29); no código |

### OpenBB — REFERENCIA (verificar procedencia)
| Campo | Dato |
|---|---|
| URL | https://github.com/OpenBB-finance/OpenBB → redirige a `openbq-org/OpenBB` (alerta 3) |
| Licencia | Apache-2.0 según LICENSE ("OpenBB Inc."); GitHub la marca NOASSERTION |
| Mantenimiento | Push 2026-10-12; 100 issues; 74k★ |
| Decisión | Referencia de la capa de proveedores; no instalar hasta confirmar la migración. Cada extensión tiene dependencias/licencias propias |
| Riesgos | Ecosistema grande de proveedores con claves de terceros |

### Freqtrade / FreqAI — REFERENCIA (no copiar)
| Campo | Dato |
|---|---|
| URL oficial | https://github.com/freqtrade/freqtrade |
| Licencia | **GPL-3.0** |
| Mantenimiento | Release 2026.9 (2026-09-29); 31 issues; 55k★ |
| Decisión | Solo leer ideas (FreqAI: reentrenamiento incremental, `data_drawer`/`data_kitchen`). Prohibido copiar o importar |
| Riesgos | Licencia copyleft; ejecución con claves reales de exchange |

### QuantDinger — REFERENCIA
| Campo | Dato |
|---|---|
| URL oficial | https://github.com/OpenByteInc/QuantDinger |
| Licencia | Apache-2.0 (backend); frontend/móvil "source-available"; marca restringida (`TRADEMARKS.md`) |
| Mantenimiento | Push 2026-10-09; 12.7k★; creado 2025-12-28 |
| Riesgos | Alerta 7 |
| Reutilizable | Solo ideas de producto |

### limit-order-book (mansoor-mamnoon) — REFERENCIA (no copiar)
| Campo | Dato |
|---|---|
| URL | https://github.com/mansoor-mamnoon/limit-order-book (paquete `orderbook-lob` 0.1.0) |
| Licencia | **Sin LICENSE**; README dice MIT (no vinculante sin texto) |
| Mantenimiento | Último commit 2025-08-29; 3★; 90 issues; binarios y CSV dentro del repo |
| Riesgos | `subprocess` en `analyze.py`/`cli.py` (invoca binarios C++ locales) |
| Reutilizable (solo idea) | `python/olob/microstructure.py`: `_infer_trade_sign`, `_compute_imbalance_from_depth`, `_parkinson_sigma`, `_garman_klass_sigma`. Reimplementar |

### market-regime (kangchengX) — REFERENCIA (no copiar)
| Campo | Dato |
|---|---|
| URL | https://github.com/kangchengX/market-regime |
| Licencia | **Ninguna** |
| Mantenimiento | Último commit 2024-12-20; 0★; 3 issues |
| Riesgos | `main.py` lanza `subprocess.run` de scripts propios; código de investigación sin tests |
| Reutilizable (solo idea) | `stats.py`: `calculate_transition_matrix` (l.222), `calculate_transition_matrix_entropy` (l.262), `calculate_regime_durations`. Reimplementar (~30 líneas numpy) |

## Recomendaciones para tareas siguientes
- T16: Kronos vía wrapper con muestreo múltiple, pesos fijados por SHA, tests offline con fixture mínimo.
- Detector de régimen: BOCPD propio (normal) o port MIT de `bocpd.py`; validar con matriz de transición + entropía reimplementada.
- Microestructura (T23): OFI/signo de trade reimplementados con tests propios; patrones de `crypto_lob_stream` (gaps/reconexión) sin copiar el paquete.
- `optuna` como extra opcional cuando lleguen T27/T28.
- Todo código MIT/Apache copiado conserva su aviso y se registra en un `THIRD_PARTY.md`.
