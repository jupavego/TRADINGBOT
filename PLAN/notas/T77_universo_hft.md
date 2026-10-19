# T77 — Universo HFT: insumo de la investigación y contraste con el proyecto

Fecha: 2026-10-19. Insumo: investigación de repositorios compartida por el usuario (12 candidatos). Aquí se contrasta con lo que **ya existe** en `v2/` y se fija qué se aprovecha, qué se descarta y qué hay que medir antes de construir. Las cifras de Binance (límites, filtros, comisiones vigentes) **no se verificaron en esta sesión** (sin acceso a `developers.binance.com`): T77 las verifica en la fuente; lo único tomado del código es `CostParams`.

## 1. Qué significa «HFT» en este proyecto
| Escala | Latencia | ¿Aplica? |
|---|---|---|
| A. Institucional (colocación, FPGA/Rust, prioridad de cola) | µs–ms | **No**: requiere infraestructura y acceso que este proyecto no tiene. |
| B. **Microestructura rápida sobre la API pública de Binance** | 100 ms – 60 s | **Sí, es el objetivo**: libro L2 por WebSocket, decisiones deterministas, órdenes por REST/WS API. Sin colocación: se mide la latencia real, no se supone. |
| C. Arbitraje y eventos (funding, base) | s – h | Ya cubierto por `arbitrage` (T38–T45); solo se reutilizan sus datos. |

Regla heredada: **ningún LLM en la ruta de una orden**; los LLM solo informan (`agents/context`). Riesgo y ejecución son código determinista con poder de veto (T29).

## 2. Aritmética de costos (la razón de que la hipótesis nula sea «no hay edge»)
Con `CostParams` (v2/eim/backtest/params.py): taker 5 pb, maker 2 pb → ida y vuelta **taker 10 pb · mixto 7 pb · maker-maker 4 pb**. El spread de BTCUSDT es de ~1 tick, una fracción de pb (a medir). Consecuencias, a verificar con datos propios en T77/T80 (orden de magnitud, no resultado):
- Capturar el spread **no paga** la comisión: un *market maker* en VIP 0 solo gana si su señal/inventario predice movimientos de varios pb; la selección adversa pesa más que el spread.
- Un direccional *taker* necesita que el movimiento esperado del mid supere ~10 pb en el horizonte de la operación.
- Mismo patrón que T27 (costos ≈ 0,2–0,36 R por operación) y BACKLOG T47 (2): **los costos dominan**. Por eso el plan pone una *prueba de techo* barata (T80 ◆) antes de invertir en modelos y estrategias, y criterios pre-registrados antes de mirar resultados (T77).

## 3. Contraste: investigación frente al proyecto real
| Propuesta de la investigación | Proyecto real | Decisión |
|---|---|---|
| Centro visual Streamlit/Dash | Web Vite+TS+Lightweight Charts, API FastAPI, Observatorio (T72–T76) | Pestaña HFT en la web (T86); nada de Streamlit/Dash. |
| **HftBacktest** (MIT, Rust+Python/Numba) | T04 lo dejó «referencia»; T23 citó su diseño de profundidad | **Candidato real para T79** (cola + latencia + Binance Futures). Verificado hoy en el README: MIT, ejemplo de grid en Binance Futures, modelos de latencia de feed/órdenes y de cola, Python ≥ 3.11 (igual que `pyproject.toml`); el bot en vivo es **solo Rust** → no se usa para ejecutar, solo para simular. No pude confirmar versión de release (la página no la muestra): T77/T79 la verifican en PyPI. Riesgos: Numba y 7,9 GB (medir), formato `npz` propio (conversor en T78), mantenimiento. Dependencia **opcional aislada** (extra `hft`), nunca en el núcleo. |
| **NautilusTrader** (LGPL) | T25 ya decidió motor propio (550 MB, núcleo Rust/Cython) | **No ahora.** Se reevalúa solo si T83 necesita el ciclo de vida completo de órdenes y el `Broker` propio no alcanza. |
| **Hummingbot** (Apache-2.0) | Escuadrón de bots (T56–T60): bots sin claves ni poder de operar | **Solo referencia** de Avellaneda–Stoikov/*pure market making* y de gestión de órdenes. El agente HFT tiene su propia ejecución bajo T29; no se mezcla con el escuadrón. |
| **Cryptofeed** (AGPL) | Recolector propio T23 (aggTrade + depth@100ms, reconstrucción con `pu`) | **Descartado**: licencia AGPL y ya existe lo necesario. |
| **Binance Connector Python** (MIT) | `execution/binance_rest.py` propio (HMAC, testnet, ids deterministas) | No se reemplaza. T77 evalúa **solo** si el WS API de órdenes baja la latencia medida; si sí, cliente propio mínimo o SDK acotado a ese módulo. |
| CCXT, Freqtrade (GPL), LEAN, Jesse, Connector Go | T04: Freqtrade GPL = solo referencia | **Descartados** para HFT (velas/otro lenguaje/GPL; sin ventaja medida). |
| Motor en Rust propio / VPS cercano | Equipo de referencia i5-8250U, 7,9 GB; Windows | **Primero medir**: si el p99 del procesamiento Python es < 20 % del presupuesto de latencia, Rust no aporta (decisión en T77). VPS: solo medición comparativa, sin operar. |
| Comparar con «matriz de pruebas de tres motores» | Ya hay motor de velas (T25) y simulador de arbitraje con libros (T43) | No se compara Nautilus; se compara HftBacktest vs motor mínimo propio si T79 lo exige. |

## 4. Lo que ya existe y se reutiliza (no se rehace)
| Pieza | Dónde | Uso en la fase |
|---|---|---|
| Recolector L2 + trades, reconstrucción con `pu`, resync por snapshot | `eim/data/collectors/` (T23) | Base de T78 (se amplía, no se reescribe). |
| OFI/delta/profundidad por vela, `MicroBar` | `eim/data/micro.py`, `agents/microstructure` | Base de features (T80); el agente actual sigue siendo de escala de vela. |
| Costos de perpetuos, margen, liquidación | `eim/backtest/{params,perp}.py` (T25) | Costos y comisiones del simulador (T79). |
| Bootstrap, permutación, Holm, entrada aleatoria | `eim/backtest/edge.py`, `eim/validation/{stats,criteria,gate}.py` (T27, T49) | Marco de evaluación (T80) y puerta (T84, criterios `hft_v1`). |
| Veredicto determinista, kill-switch, sellado HMAC | `eim/risk/` (T29), patrón `arb_*` | Riesgo HFT (T83). |
| `Broker`, `SimBroker`, testnet, reconciliación | `eim/execution/` (T30) | Misma interfaz en simulación y papel (T79/T83/T85). |
| Perfiles de libros reales y deslizamiento por tamaño | `eim/data/arb_*` (T43) | Impacto propio en el simulador. |
| Latido, vigilante, informe semanal | `eim/operation/` (T31), `eim.leaders supervise` | Servicio HFT supervisado (T78, T85). |
| Régimen/BOCPD | agente `regime` (T22) | Selector de estado (T81/T82). |
| Registro de intentos, versiones, puerta | `eim/validation/` (T49) | Torneo (T84). |
| Observatorio (eventos, catálogo) | `eim/observability/` (T72–T76) | Módulo HFT visible y trazable (T86). |

## 5. Catálogo de modelos (qué se implementa, dónde y con qué prioridad)
Todo en `eim/hft/` como funciones puras; un modelo entra solo si mejora su línea base fuera de muestra (IC95 % y Holm); si no, queda archivado con su resultado.
| Familia | Modelos | Prioridad | Tarea |
|---|---|---|---|
| Estado del libro y flujo | microprice (Stoikov), OFI multinivel (Cont–Kukanov–Stoikov), imbalance L1–L5, desequilibrio del flujo de operaciones/CVD, VPIN (Easley–López de Prado–O'Hara) | Muy alta | T80 |
| Predicción | regresión ridge/logit multi-horizonte (1/5/30 s) con calibración; árboles (GBM) solo si hay no linealidad demostrada | Muy alta / media | T80–T81 |
| Procesos puntuales | Hawkes bivariado (compras/ventas agresoras); duraciones ACD (Engle–Russell) | Alta / baja | T81 |
| Cola y llenado | Cont–Stoikov–Talreja / cola reactiva (Huang–Lehalle–Rosenbaum): P(llenado antes de movimiento adverso) | Muy alta | T79, T81 |
| Impacto y selección adversa | λ de Kyle, regresión de impacto (Hasbrouck), spread efectivo/realizado, raíz cuadrada del impacto | Alta | T81 |
| Volatilidad | RV con *two-scale*/*realized kernel*, bipower y saltos (Barndorff-Nielsen–Shephard), HAR-RV, Parkinson/GK (ya en T23), filtro de Kalman del precio eficiente (opcional) | Alta | T81 |
| Control óptimo | Avellaneda–Stoikov, límites de inventario de Guéant–Lehalle–Fernandez-Tapia, sesgo por señal (Cartea–Jaimungal), salida de inventario tipo Almgren–Chriss | Alta | T82 |
| Régimen y toxicidad | HMM 2–3 estados, BOCPD (T22), `stand_down` determinista | Muy alta | T81–T82 |
| Entre mercados | lead-lag perp/spot y BTC–ETH (Hayashi–Yoshida), basis intradía | Media (solo si hay datos de ambos) | T81 |
| Tamaño y degradación | Kelly fraccional en pb, CUSUM/SPRT sobre el edge realizado, *shrinkage* | Media | T82, T85 |
| Evaluación | validación con embargo y purga, bootstrap por bloques, Holm, sensibilidad a latencia/cola/comisión | Obligatoria | T80, T84 |
Fuera de la fase (BACKLOG): aprendizaje profundo sobre el libro (DeepLOB/Transformers), aprendizaje por refuerzo, L3/MBO, GPU (MX130 de 2 GB).

## 6. Puntos que cambian el diseño (honestos)
1. **Testnet no mide fills**: su libro y su flujo no son los de producción. Testnet sirve para la prueba funcional de órdenes (T83); la validación de ejecución se hace con **datos reales + simulador con cola pesimista** (T79, T85).
2. **La latencia se mide, no se supone** (T77): RTT, jitter, deriva de reloj, antigüedad del evento. Define el horizonte mínimo viable y qué estrategias tienen sentido.
3. **Datos primero y desde ya**: T78 acumula días de libro profundo en segundo plano; T80/T84 necesitan 14–30 días contiguos. Es el camino crítico real.
4. **Parada barata (T80 ◆)**: si ni la cota con previsión perfecta ni el IC supera los costos con margen, se archiva con el resultado honesto (como T28), o se redirige (otro horizonte, rebate/VIP, otros símbolos).
5. **Sin dinero real**: el carril termina en simulación con datos reales y, si el usuario lo decide, prueba funcional en testnet; dinero real exige T31 y la puerta de edge, igual que el resto.

## 7. Segunda investigación (auditoría comparativa y cobertura de métodos) — contraste
Insumo del usuario, 2026-10-19. **No la verifiqué en la fuente** (no clono ni leo esos repos en esta etapa): lo que afirma de mmb, MOSAIC, HFT Lab Core y quant-research queda como *declarado* hasta que T77 lo audite con el formato de T04 (clones aislados, sin ejecutar ni instalar).

### 7.1 Repositorios nuevos y decisión provisional
| Repo (según la investigación) | Lo declarado | Decisión en este plan |
|---|---|---|
| **mmb** (Rust, GPL-3.0) | Binance Spot y USDⓈ-M, `core_tests`, commits de 2022 | **Referencia, modo B/C** (GPL contagia; el proyecto ya lo trata así en T56). T77 mira el último commit efectivo de la rama principal; si no hay mantenimiento, se descarta. |
| **MOSAIC** (sin licencia detectada) | OFI, FIFO, ML, simulación de ejecución; pocas operaciones por estrategia en su tabla | **Solo estudio, no se copia código** mientras no haya licencia. Sus métricas no cuentan como evidencia. T77 confirma la ausencia de `LICENSE`. |
| **HFT Lab Core** (MIT declarado, módulos propietarios) | HMM, Hurst, Rough Heston, señales geométricas; sin `tests/` visibles | **Estudio selectivo**: las ideas (Hurst, HMM) se reimplementan con pruebas propias; nada de lo «propietario». |
| **quant-research** (MIT) | Módulos de validación y pruebas, datos de EE. UU. | **Referencia** de validación (purga/embargo, pruebas de hipótesis); T77 comprueba licencia y si algo se porta como lógica pura con aviso en `THIRD_PARTY.md`. |
| HftBacktest · NautilusTrader · Hummingbot | ya decididos en §3 | Sin cambio (ver 7.2). |

### 7.2 Dónde mantengo una posición distinta (con razón)
1. **«NautilusTrader = candidato principal de motor operativo»**: no lo adopto ahora. T25 ya midió su integración (550 MB, núcleo Rust/Cython, LGPL) y el `Broker`/`gateway`/reconciliación propios (T30) ya hacen el ciclo de órdenes con kill-switch y sello de riesgo. Se reevalúa solo si T83 demuestra que el `Broker` no alcanza (parciales, libro). Su aviso sobre versiones de Python **sí aplica**: `pyproject.toml` exige ≥ 3.11, T25 lo instaló en 3.12 y este entorno de trabajo usa 3.13; T77 fija versión publicada y entorno aparte antes de cualquier prueba.
2. **«Libro L3 y prioridad FIFO (B–A)»**: **Binance no publica libro por orden**; solo L2 + operaciones. La posición en cola **no se reconstruye, se estima** (modelos de cola de T79/T81) y por eso el simulador debe ser pesimista y medir su sesgo. L3 queda fuera de la fase.
3. **«Arbitraje de funding / spot–futuros: D o C»**: ya existe y está medido (`arbitrage` T38–T45, `reports/arbitrage_edge.md`: carry a 90 d **Marginal**; pares triangulares de 1 min en T43). No se rehace; el agente HFT solo reutiliza sus datos de funding y base.
4. **«Árbitro determinista de decisiones»** y **«observabilidad»**: ya son síntesis + `RiskDecision` (T20/T29/T44) y el Observatorio (T72–T76); T83 y T86 los extienden, no se construyen otros.
5. **«Biblioteca cuantitativa común»**: de acuerdo, y ya es la forma del plan: funciones puras versionadas en `eim/hft/{features,models}/` que cualquier agente consulta; no se crea un paquete paralelo.
6. **«PBO y Deflated Sharpe: D»**: parcialmente cubierto. El DSR ya está en `copytrading/stats.deflated` y lo usa `validation/stats.py` (T49); **la PBO (CSCV) no existe** y entra en T84.

### 7.3 Bibliotecas de apoyo (decisión)
Dependencias actuales (`pyproject.toml`): numpy, pandas, duckdb; `scipy` **ya se importa** (`agents/regime/bocpd.py`) pero **no está declarada** → se declara en T81. El resto, como extra opcional `hft` (nada entra al núcleo ni a la operación sin necesidad medida), con licencia y versión comprobadas en T77.
| Biblioteca | Decisión |
|---|---|
| NumPy, SciPy | Núcleo (declarar SciPy). |
| statsmodels | Extra `hft`: regresión, ADF, Engle–Granger/Johansen, diagnóstico de residuos. |
| arch | Extra `hft`: GARCH/volatilidad condicional intradía (T81, prioridad media). |
| scikit-learn | Extra `hft`: ridge/logit/GBM con calibración (línea base de T81). |
| hmmlearn | Extra `hft`, solo si un HMM propio en NumPy/SciPy no basta (convergencia medida). |
| ruptures | **No**: BOCPD (T22) ya cubre cambios de régimen; BACKLOG. |
| River (aprendizaje incremental) | **No ahora**: BACKLOG; interesa solo si hay deriva demostrada en T85. |
| MLFinPy | **Referencia** de purga/embargo y PBO; se implementa propio con pruebas (T80/T84). |
| QuantStats | **No**: ya hay métricas y reportes propios (T25/T49). |

### 7.4 Matriz de aceptación por algoritmo (propuesta final de la investigación — se adopta)
Una fila por modelo/estrategia con columnas: **fuente de la implementación · prueba unitaria · prueba con datos de Binance · costo y latencia modelados · validación fuera de muestra (IC, Holm) · criterio de desactivación**. Se crea en T81 (`v2/reports/hft_acceptance_matrix.md`), la completa cada tarea que añade un método y T84 la consume: **un método sin todas las casillas no entra al torneo**. Cobertura de métodos: los niveles A–D de la investigación sirven de guía de «qué hay que desarrollar propio» (casi todo en este plan es C: propio sobre SciPy/statsmodels).
