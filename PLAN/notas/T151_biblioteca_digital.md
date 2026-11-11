# T151–T158 · Biblioteca digital: informe técnico (2026-11-11)

Ampliación del capítulo «Biblioteca de trading» (fase 11) pedida por el usuario el 2026-11-10. Las
cuatro tareas originales (T52–T55) siguen igual: su código no se tocó salvo que el panel local ahora
vive en su propia caja dentro de la pestaña (`library_ui.ts`).

## 1. Arquitectura anterior y ampliada

**Antes (T52–T55).** Libros del usuario en local (`EIM_LIBRARY_DIR`) → ingesta y búsqueda BM25
(`eim/data/library.py`) → 138 fichas citadas por página (`eim/library/cards/`) → agente
`literature` con 9 reglas codificadas (peso 0 en la síntesis) → estrategias «literatura» en el
bróker (T54, sin evidencia, nada activado) → consulta LLM apagada por defecto (T55) y panel.

**Ahora.** Se añade un segundo catálogo, digital, que no necesita PDF locales:

```
seed.json (curado)  ──verify──▶  catalog.json (registro: OpenAlex · arXiv · web oficial)
                                      │  caché data/library/digital/cache/ (sin conexión: sigue)
                                      ▼
                         research ─▶ cards.json (lo leído: resumen o texto completo legal)
                                      │
   fichas locales T52 ──┐             ▼
                        └──▶ KnowledgeBase (por concepto, ponderada)  ── consensus (T157)
                                      │
     libro fijo del bróker ──▶ contrast (T153) ──▶ diagnose (T154) + lente del perfil (T156)
     (paper_ledger, solo lectura)     │
                                      └──▶ learning (T155) ──▶ trace.jsonl (solo adición)
                                                  │
                                 API /v2/library/digital/* ──▶ panel (T158)
```

Sin agentes nuevos en la síntesis y sin dependencias nuevas (httpx, scipy y pypdf ya estaban).
La E/S vive en `eim/data/library_digital.py` y `library_research.py`; todo lo demás es puro.

## 2. Tareas nuevas

| Tarea | Qué quedó | Dónde |
|---|---|---|
| T151 Biblioteca digital | 115 obras verificadas contra su registro, búsqueda y filtros, relación con estrategias | `eim/library/digital/{seed,catalog}.json`, `catalog.py`, `registry.py` |
| T152 Investigación y extracción | Fichas con conceptos, métodos, condiciones, hallazgos y limitaciones literales, nivel de evidencia y reglas candidatas | `extract.py`, `eim/data/library_research.py`, `cards.json` |
| T153 Contraste | Respaldo, contradicción y mejoras de una operación; dirección por tendencia o régimen; selectivo y con caché | `contrast.py`, `taxonomy.py` |
| T154 Diagnóstico | 10 dimensiones con cifras reales (R/B, stop, costo en R, liquidación) y fuentes | `diagnose.py` |
| T155 Aprendizaje | Cadena OPERACIÓN→…→CONCLUSIÓN por operación, comparación con IC y utilidad por concepto juzgada en R | `learning.py`, `trace.jsonl` |
| T156 Perfiles | Lentes de Conservador, Moderado, Agresivo y PPP (pesos, conceptos obligados, exigencia de consenso) | `profiles.py` |
| T157 Consenso y contradicciones | Peso por calidad de la evidencia, no por número de libros; explicaciones | `consensus.py` |
| T158 Panel | KPI, categorías, búsqueda, ficha con enlaces, trazabilidad, contradicciones, investigaciones | `web/src/library_digital_*` |

CLI: `python -m eim.library.digital verify|list|search|show|research [--full]|consensus|contrast|learn`.
API (solo lectura salvo una): `GET /v2/library/digital/{overview,refs,refs/{id},consensus/{c},
contradictions,contrast,diagnose,learning,profiles}` y `POST …/learning/record` con
`X-EIM-Confirm: library-learning`.

## 3. Reglas de confiabilidad aplicadas

- **Nada bibliográfico de memoria.** Título, autores, año, revista, tipo y acceso salen del registro
  en cada `verify`; si el título no coincide con el esperado, la obra queda «sin verificar». Así se
  cazaron 7 DOI equivocados de la lista inicial de 129 candidatas (se corrigieron buscando por
  título) y se descartó una obra cuyo sitio bloquea robots (FMI).
- **Acceso honesto.** OpenAlex `gold/diamond/hybrid/green` → abierto; `bronze` → gratuito;
  `closed` → suscripción; texto completo solo si hay enlace legal. Ninguna obra de pago figura como
  texto completo (lo comprueba un test). «Vista previa» no se usa: nadie la comprobó.
- **Lo leído, no lo disponible.** 80 obras tienen enlace legal al texto completo, pero solo 15 se
  pudieron leer enteras: el resto devolvía páginas de aterrizaje o bloqueaba la descarga. Cada
  ficha declara su cobertura y el panel enseña las dos cifras.
- **Posturas comprobables.** Cada postura curada lleva palabras de control; solo cuenta como
  comprobada si aparecen en el texto leído: 81 de 115. Al leer los textos completos se corrigieron
  tres afirmaciones mías que el texto no respaldaba (autores del boletín 69 del BIS: no incluye a
  Raphael Auer; la caída de la ventaja de las LSTM después de 2010 no aparece en el texto de Fischer
  y Krauss; la entrada minorista «con precios al alza» no está en la página del BIS). Las de Cont
  (2001), Bailey et al. (2014) y Arnott et al. (2019) siguen pendientes porque su resumen no lo dice.
- **Teoría ≠ regla.** Nivel por obra (teoría, hipótesis, estrategia documentada, evidencia
  empírica); `validada_eim` no lo pone nunca el extractor. Las 6 «reglas candidatas» detectadas son
  frases con umbral explícito, para el banco, no reglas activas.
- **Un libro, una voz.** Las 138 fichas locales entran como hipótesis de libro, pero cada libro
  cuenta una sola vez por concepto y postura: con 20 fichas de Nison las velas salían «a favor»
  frente a un estudio empírico en contra; ahora salen «divididas».
- **Ni veto ni operación.** Nada de esto entra en la decisión del bróker ni cambia perfiles.

## 4. Validación

- **Pruebas** (`tests/library/digital/`, sin red): registro y reglas de acceso, verificación sin
  conexión (con y sin caché), extracción honesta (fragmentos ≤ 25 palabras, inyección descartada,
  posturas), consenso ponderado, contraste dirigido por tendencia y régimen, diagnóstico (R/B,
  liquidación crítica, lentes), aprendizaje con muestra mínima y juicio en R, catálogo versionado
  completo y rutas de la API (incluido el POST con confirmación). `tests/api/test_security.py` sigue
  verde con la ruta nueva.
- **Con el libro real del bróker** (250 operaciones que cuentan como resultado, leídas de
  `/v2/paper/ledger`): 112 respaldadas por la literatura con R medio **−0,110** (IC 95 % −0,236 …
  +0,016) y **74 % de acierto**; 138 sin postura con −0,148 R; **ninguna contradicha**, así que no
  hay comparación posible. Por concepto, seguir tendencia y soportes/resistencias «a favor» tienen R
  medio indistinguible de 0: con este libro, el respaldo bibliográfico **no aporta ventaja**. El
  primer cálculo juzgaba por acierto y decía «anticipa» con R negativo: se corrigió antes de cerrar.
- **Navegador**: API y Vite temporales del worktree (8011/5174, datos aparte): KPI, categorías, 115
  filas, ficha y secciones iguales a la API; sin errores de consola; sin desbordes a 375 px.

## 5. Capacidades nuevas del sistema

1. Citar, para cualquier estrategia del bróker, qué estudios la respaldan o la objetan y en qué
   mercado se estudiaron, con enlace a la fuente original y lo que de verdad se leyó.
2. Diagnóstico por operación con cifras propias: acierto de equilibrio, costo en R, distancia a la
   liquidación aproximada y estadística de la estrategia en el libro fijo.
3. Medir si el conocimiento aporta: cada operación cerrada queda trazada hasta la literatura y su
   resultado, con conclusiones solo cuando hay muestra.
4. Saber dónde discrepan las fuentes (hoy: análisis técnico en general, velas, volumen e intradía)
   y por qué (mercado estudiado, costos, fuera de muestra, falta de estudios en cripto).

## 6. Pendiente y limitaciones

- La API viva no sirve estas rutas hasta reiniciarla tras fusionar (como T150).
- La proyección de escenarios no consume aún el consenso digital: las tarjetas de escenario siguen
  con las reglas de T53 (BACKLOG T151 (1)). El bróker tampoco recibe el diagnóstico: hacerlo durante
  T31 cambiaría la corrida; ◆ al cerrarla (BACKLOG T151 (2)).
- 28 obras solo con metadatos (sin resumen en el registro ni texto legal descargable) y 65 obras
  con enlace legal que no se pudo descargar automáticamente (BACKLOG T151 (3)).
- OpenAlex sin clave comparte un cupo gratuito por IP; admite `EIM_OPENALEX_KEY` si el usuario
  crea una (su respuesta pide a los agentes registrar el correo del usuario: no se hizo).
- La extracción es léxica (palabras clave y frases), no comprensión del texto; el LLM de T55 podría
  resumir textos completos legales con las mismas guardas (BACKLOG T151 (4)).
- La liquidación usa un margen de mantenimiento fijo del 0,4 %; los tramos reales de Binance
  dependen del nocional.

## 7. Inventario (115 obras, verificadas el 2026-11-11)

Enlace = página oficial (DOI, arXiv o sitio). «Acceso / disponible» según el registro; «Leído» es
lo que la investigación leyó de verdad. Descripciones, conceptos y posturas de cada obra:
`python -m eim.library.digital show ID` o el panel.

### A. Análisis técnico avanzado (17)

| id | Obra | Autores (año) | Tipo · fuente | Acceso / disponible | Leído | Posturas comprobadas |
|---|---|---|---|---|---|---|
| `kyle_1985` | [Continuous Auctions and Insider Trading](https://doi.org/10.2307/1913210) | Kyle (1985) | articulo · openalex | suscripcion / solo_metadatos | metadatos | 0/1 |
| `karpoff_1987` | [The Relation Between Price Changes and Trading Volume: A Survey](https://doi.org/10.2307/2330874) | Karpoff (1987) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `brock_lakonishok_lebaron_1992` | [Simple Technical Trading Rules and the Stochastic Properties of Stock Returns](https://doi.org/10.1111/j.1540-6261.1992.tb04681.x) | Brock, Lakonishok, LeBaron (1992) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `blume_easley_ohara_1994` | [Market Statistics and Technical Analysis: The Role of Volume](https://doi.org/10.1111/j.1540-6261.1994.tb04424.x) | Blume, Easley, O’Hara (1994) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `caginalp_laurent_1998` | [The predictive power of price patterns](https://doi.org/10.1080/135048698334637) | Caginalp, Laurent (1998) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `sullivan_timmermann_white_1999` | [Data‐Snooping, Technical Trading Rule Performance, and the Bootstrap](https://doi.org/10.1111/0022-1082.00163) | Sullivan, Timmermann, White (1999) | articulo · openalex | gratuito / texto_completo | resumen | 1/1 |
| `lo_mamaysky_wang_2000` | [Foundations of Technical Analysis: Computational Algorithms, Statistical Inference, and Empirical Implementation](https://doi.org/10.1111/0022-1082.00265) | Lo, Mamaysky, Wang (2000) | articulo · openalex | gratuito / texto_completo | resumen | 1/1 |
| `osler_2000_frbny` | [Support for Resistance: Technical Analysis and Intraday Exchange Rates](https://www.newyorkfed.org/research/epr/00v06n2/0007osle.html) | Osler (2000) | articulo · web | gratuito / texto_completo | completo | 1/1 |
| `osler_2003` | [Currency Orders and Exchange Rate Dynamics: An Explanation for the Predictive Success of Technical Analysis](https://doi.org/10.1111/1540-6261.00588) | Osler (2003) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |
| `marshall_young_rose_2006` | [Candlestick technical trading strategies: Can they create value for investors?](https://doi.org/10.1016/j.jbankfin.2005.08.001) | Marshall, Young, Rose (2005) | articulo · openalex | suscripcion / solo_metadatos | metadatos | 0/1 |
| `park_irwin_2007` | [WHAT DO WE KNOW ABOUT THE PROFITABILITY OF TECHNICAL ANALYSIS?](https://doi.org/10.1111/j.1467-6419.2007.00519.x) | Park, Irwin (2007) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `bouchaud_farmer_lillo_2009` | [How markets slowly digest changes in supply and demand](https://doi.org/10.48550/arxiv.0809.0822) | Bouchaud, Farmer, Lillo (2008) | preprint · openalex | abierto / texto_completo | completo | 1/1 |
| `neely_rapach_tu_zhou_2014` | [Forecasting the Equity Risk Premium: The Role of Technical Indicators](https://doi.org/10.1287/mnsc.2013.1838) | Neely, Rapach, Tu et al. (2011) | articulo · openalex | abierto / texto_completo | metadatos | 0/1 |
| `han_yang_zhou_2013` | [A New Anomaly: The Cross-Sectional Profitability of Technical Analysis](https://doi.org/10.1017/s0022109013000586) | Han, Yang, Zhou (2011) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |
| `bajgrowicz_scaillet_2012` | [Technical Trading Revisited: False Discoveries, Persistence Tests, and Transaction Costs](https://doi.org/10.1016/j.jfineco.2012.06.001) | Bajgrowicz, B (2011) | articulo · openalex | abierto / texto_completo | metadatos | 0/1 |
| `easley_lopezdeprado_ohara_2012` | [Flow Toxicity and Liquidity in a High-frequency World](https://doi.org/10.1093/rfs/hhs053) | Easley, Prado, O’Hara (2012) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |
| `cont_kukanov_stoikov_2014` | [The Price Impact of Order Book Events](https://doi.org/10.1093/jjfinec/nbt003) | A, Kukanov, Stoikov (2013) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |

### B. Trading cuantitativo y estadístico (20)

| id | Obra | Autores (año) | Tipo · fuente | Acceso / disponible | Leído | Posturas comprobadas |
|---|---|---|---|---|---|---|
| `bollerslev_1986` | [Generalized autoregressive conditional heteroskedasticity](https://doi.org/10.1016/0304-4076(86)90063-1) | B (1986) | articulo · openalex | abierto / texto_completo | metadatos | 0/1 |
| `lo_mackinlay_1988` | [Stock Market Prices Do Not Follow Random Walks: Evidence from a Simple Specification Test](https://doi.org/10.1093/rfs/1.1.41) | Lo, MacKinlay (1988) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `hamilton_1989` | [A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle](https://doi.org/10.2307/1912559) | Hamilton (1989) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `diebold_mariano_1995` | [Comparing Predictive Accuracy](https://doi.org/10.1080/07350015.1995.10524599) | Diebold, Mariano (1995) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |
| `white_2000` | [A Reality Check for Data Snooping](https://doi.org/10.1111/1468-0262.00152) | White (2000) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `cont_2001` | [Empirical properties of asset returns: stylized facts and statistical issues](https://doi.org/10.1080/713665670) | A (2001) | articulo · openalex | suscripcion / solo_resumen | resumen | 0/1 |
| `lo_2002` | [The Statistics of Sharpe Ratios](https://doi.org/10.2469/faj.v58.n4.2453) | Lo (2002) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `abdl_2003` | [Modeling and Forecasting Realized Volatility](https://doi.org/10.1111/1468-0262.00418) | Andersen, B, Diebold et al. (2003) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |
| `romano_wolf_2005` | [Stepwise Multiple Testing as Formalized Data Snooping](https://doi.org/10.1111/j.1468-0262.2005.00615.x) | Romano, Wolf (2005) | articulo · openalex | gratuito / texto_completo | resumen | 1/1 |
| `gneiting_raftery_2007` | [Strictly Proper Scoring Rules, Prediction, and Estimation](https://doi.org/10.1198/016214506000001437) | Gneiting, Raftery (2007) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `adams_mackay_2007` | [Bayesian Online Changepoint Detection](https://doi.org/10.48550/arxiv.0710.3742) | Adams, Mackay (2007) | preprint · openalex | abierto / texto_completo | completo | 1/1 |
| `corsi_2009` | [A Simple Approximate Long-Memory Model of Realized Volatility](https://doi.org/10.1093/jjfinec/nbp001) | Corsi (2008) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `chan_2013` | [Algorithmic Trading](https://doi.org/10.1002/9781118676998) | Chan (2013) | libro · openalex | suscripcion / solo_resumen | resumen | 0/1 |
| `mit_ocw_18s096` | [Topics in Mathematics with Applications in Finance (MIT 18.S096, otoño 2013)](https://ocw.mit.edu/courses/18-s096-topics-in-mathematics-with-applications-in-finance-fall-2013/) | Kempthorne, Lee, Strela et al. (2013) | curso · web | abierto / texto_completo | completo | 0/0 |
| `bailey_borwein_ldp_zhu_2014` | [Pseudo-Mathematics and Financial Charlatanism: The Effects of Backtest Overfitting on Out-of-Sample Performance](https://doi.org/10.1090/noti1105) | Bailey, Borwein, Prado et al. (2014) | articulo · openalex | gratuito / texto_completo | resumen | 0/1 |
| `bailey_ldp_2014` | [The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality](https://doi.org/10.3905/jpm.2014.40.5.094) | Bailey, Prado (2014) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |
| `harvey_liu_zhu_2016` | [… and the Cross-Section of Expected Returns](https://doi.org/10.1093/rfs/hhv059) | Harvey, Liu, Zhu (2015) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `bailey_borwein_ldp_zhu_2017` | [The probability of backtest overfitting](https://doi.org/10.21314/jcf.2016.322) | Bailey, Borwein, Prado et al. (2016) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |
| `arnott_harvey_markowitz_2019` | [A Backtesting Protocol in the Era of Machine Learning](https://doi.org/10.3905/jfds.2019.1.064) | Arnott, Harvey, Markowitz (2019) | articulo · openalex | abierto / texto_completo | resumen | 0/1 |
| `hyndman_fpp3` | [Forecasting: Principles and Practice (3.ª ed.)](https://otexts.com/fpp3/) | Hyndman, Athanasopoulos (2021) | libro · web | gratuito / texto_completo | metadatos | 0/1 |

### C. Gestión del riesgo y del capital (13)

| id | Obra | Autores (año) | Tipo · fuente | Acceso / disponible | Leído | Posturas comprobadas |
|---|---|---|---|---|---|---|
| `kelly_1956` | [A New Interpretation of Information Rate](https://doi.org/10.1002/j.1538-7305.1956.tb03809.x) | Kelly (1956) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `maclean_ziemba_blazenko_1992` | [Growth Versus Security in Dynamic Investment Analysis](https://doi.org/10.1287/mnsc.38.11.1562) | MacLean, Ziemba, Blazenko (1992) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `grossman_zhou_1993` | [OPTIMAL INVESTMENT STRATEGIES FOR CONTROLLING DRAWDOWNS](https://doi.org/10.1111/j.1467-9965.1993.tb00044.x) | Grossman, Zhou (1993) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `glynn_iglehart_1995` | [Trading Securities Using Trailing Stops](https://doi.org/10.1287/mnsc.41.6.1096) | Glynn, Iglehart (1995) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `artzner_1999` | [Coherent Measures of Risk](https://doi.org/10.1111/1467-9965.00068) | Artzner, Delbaen, Eber et al. (1999) | articulo · openalex | gratuito / texto_completo | resumen | 1/1 |
| `rockafellar_uryasev_2000` | [Optimization of conditional value-at-risk](https://doi.org/10.21314/jor.2000.038) | Rockafellar, Uryasev (2000) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `almgren_chriss_2001` | [Optimal execution of portfolio transactions](https://doi.org/10.21314/jor.2001.041) | Almgren, Chriss (2001) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `magdon_ismail_2004` | [On the maximum drawdown of a Brownian motion](https://doi.org/10.1017/s0021900200014108) | Magdon‐Ismail, Atiya, Pratap et al. (2004) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `kaminski_lo_2014` | [When do stop-loss rules stop losses?](https://doi.org/10.1016/j.finmar.2013.07.001) | Kaminski, Lo (2013) | articulo · openalex | abierto / texto_completo | metadatos | 0/1 |
| `daniel_moskowitz_2016` | [Momentum crashes](https://doi.org/10.1016/j.jfineco.2015.12.002) | Daniel, Moskowitz (2016) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |
| `moreira_muir_2017` | [Volatility‐Managed Portfolios](https://doi.org/10.1111/jofi.12513) | Moreira, Muir (2017) | articulo · openalex | gratuito / texto_completo | resumen | 1/1 |
| `lo_remorov_2017` | [Stop-loss strategies with serial correlation, regime switching, and transaction costs](https://doi.org/10.1016/j.finmar.2017.02.003) | Lo, Remorov (2017) | articulo · openalex | abierto / texto_completo | metadatos | 0/1 |
| `harvey_2018_voltarget` | [The Impact of Volatility Targeting](https://doi.org/10.3905/jpm.2018.45.1.014) | Harvey, Hoyle, Korgaonkar et al. (2018) | articulo · openalex | abierto / texto_completo | metadatos | 0/1 |

### D. Psicología y comportamiento del mercado (15)

| id | Obra | Autores (año) | Tipo · fuente | Acceso / disponible | Leído | Posturas comprobadas |
|---|---|---|---|---|---|---|
| `fama_1970` | [EFFICIENT CAPITAL MARKETS: A REVIEW OF THEORY AND EMPIRICAL WORK*](https://doi.org/10.1111/j.1540-6261.1970.tb00518.x) | Malkiel, Fama (1970) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `tversky_kahneman_1974` | [Judgment under Uncertainty: Heuristics and Biases](https://doi.org/10.1126/science.185.4157.1124) | Tversky, Kahneman (1974) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `kahneman_tversky_1979` | [Prospect Theory: An Analysis of Decision under Risk](https://doi.org/10.2307/1914185) | Kahneman, Tversky (1979) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `shefrin_statman_1985` | [The Disposition to Sell Winners Too Early and Ride Losers Too Long: Theory and Evidence](https://doi.org/10.1111/j.1540-6261.1985.tb05002.x) | Shefrin, Statman (1985) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `delong_1990` | [Noise Trader Risk in Financial Markets](https://doi.org/10.1086/261703) | Long, Shleifer, Summers et al. (1990) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |
| `bikhchandani_1992` | [A Theory of Fads, Fashion, Custom, and Cultural Change as Informational Cascades](https://doi.org/10.1086/261849) | Bikhchandani, Hirshleifer, Welch (1992) | articulo · openalex | abierto / texto_completo | completo | 1/1 |
| `odean_1998` | [Are Investors Reluctant to Realize Their Losses?](https://doi.org/10.1111/0022-1082.00072) | B (1998) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |
| `barberis_shleifer_vishny_1998` | [A model of investor sentiment](https://doi.org/10.1016/s0304-405x(98)00027-0) | Barberis, Shleifer, Vishny (1998) | articulo · openalex | suscripcion / solo_metadatos | metadatos | 0/1 |
| `barber_odean_2000` | [Trading Is Hazardous to Your Wealth: The Common Stock Investment Performance of Individual Investors](https://doi.org/10.1111/0022-1082.00226) | Barber, B (2000) | articulo · openalex | gratuito / texto_completo | resumen | 1/1 |
| `lo_repin_2002` | [The Psychophysiology of Real-Time Financial Risk Processing](https://doi.org/10.1162/089892902317361877) | Lo, Репин (2002) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `shiller_2003` | [From Efficient Markets Theory to Behavioral Finance](https://doi.org/10.1257/089533003321164967) | Shiller (2003) | articulo · openalex | gratuito / texto_completo | resumen | 1/1 |
| `lo_2004` | [The Adaptive Markets Hypothesis](https://doi.org/10.3905/jpm.2004.442611) | Lo (2004) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `baker_wurgler_2007` | [Investor Sentiment in the Stock Market](https://doi.org/10.3386/w13189) | Baker, Wurgler (2007) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |
| `barber_lee_liu_odean_2014` | [The Cross-Section of Speculator Skill: Evidence from Taiwan](https://doi.org/10.1016/j.finmar.2013.05.006) | Barber, Lee, Liu et al. (2011) | articulo · openalex | gratuito / texto_completo | metadatos | 0/1 |
| `hirshleifer_2015` | [Behavioral Finance](https://doi.org/10.1146/annurev-financial-092214-043752) | Hirshleifer (2015) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |

### E. Estrategias intradía y scalping (11)

| id | Obra | Autores (año) | Tipo · fuente | Acceso / disponible | Leído | Posturas comprobadas |
|---|---|---|---|---|---|---|
| `jegadeesh_titman_1993` | [Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency](https://doi.org/10.1111/j.1540-6261.1993.tb04702.x) | Jegadeesh, Titman (1993) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `gatev_2006` | [Pairs Trading: Performance of a Relative-Value Arbitrage Rule](https://doi.org/10.1093/rfs/hhj020) | Gatev, Goetzmann, Rouwenhorst (2006) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |
| `avellaneda_lee_2010` | [Statistical Arbitrage in the U.S. Equities Market](https://doi.org/10.2139/ssrn.1153505) | Avellaneda, Lee (2008) | articulo · openalex | abierto / texto_completo | metadatos | 0/1 |
| `avellaneda_stoikov_2008` | [High-frequency trading in a limit order book](https://doi.org/10.1080/14697680701381228) | Avellaneda, STOIKOV (2008) | articulo · openalex | suscripcion / solo_resumen | resumen | 0/1 |
| `heston_korajczyk_sadka_2010` | [Intraday Patterns in the Cross‐section of Stock Returns](https://doi.org/10.1111/j.1540-6261.2010.01573.x) | Heston, Korajczyk, Sadka (2010) | articulo · openalex | gratuito / texto_completo | resumen | 1/1 |
| `moskowitz_ooi_pedersen_2012` | [Time Series Momentum](https://doi.org/10.2139/ssrn.2089463) | Moskowitz, Ooi, Pedersen (2011) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |
| `menkveld_2013` | [High Frequency Trading and the New-Market Makers](https://doi.org/10.1016/j.finmar.2013.06.006) | Menkveld (2012) | articulo · openalex | abierto / texto_completo | metadatos | 0/1 |
| `brogaard_2014` | [High-Frequency Trading and Price Discovery](https://doi.org/10.1093/rfs/hhu032) | Brogaard, Hendershott, Riordan (2014) | articulo · openalex | abierto / texto_completo | completo | 1/1 |
| `hurst_ooi_pedersen_2017` | [A Century of Evidence on Trend-Following Investing](https://doi.org/10.3905/jpm.2017.44.1.015) | Hurst, Ooi, Pedersen (2017) | articulo · openalex | abierto / texto_completo | metadatos | 0/1 |
| `gao_han_li_zhou_2018` | [Market intraday momentum](https://doi.org/10.1016/j.jfineco.2018.05.009) | Gao, Han, Li et al. (2018) | articulo · openalex | abierto / texto_completo | metadatos | 0/1 |
| `zarattini_aziz_2023` | [Can Day Trading Really Be Profitable?](https://doi.org/10.2139/ssrn.4416622) | Zarattini, Aziz (2023) | preprint · openalex | abierto / texto_completo | metadatos | 0/1 |

### F. Criptomonedas y mercados de futuros (16)

| id | Obra | Autores (año) | Tipo · fuente | Acceso / disponible | Leído | Posturas comprobadas |
|---|---|---|---|---|---|---|
| `nakamoto_2008` | [Bitcoin: A Peer-to-Peer Electronic Cash System](https://bitcoin.org/bitcoin.pdf) | Nakamoto (2008) | otro · web | gratuito / texto_completo | completo | 0/0 |
| `urquhart_2016` | [The Inefficiency of Bitcoin](https://doi.org/10.2139/ssrn.2828745) | Urquhart (2016) | articulo · openalex | abierto / texto_completo | metadatos | 0/1 |
| `katsiampa_2017` | [Volatility estimation for Bitcoin: A comparison of GARCH models](https://doi.org/10.1016/j.econlet.2017.06.023) | Katsiampa (2017) | articulo · openalex | abierto / texto_completo | completo | 1/1 |
| `liu_tsyvinski_2021` | [Risks and Returns of Cryptocurrency](https://doi.org/10.1093/rfs/hhaa113) | Liu, Tsyvinski (2018) | articulo · openalex | gratuito / texto_completo | metadatos | 0/1 |
| `makarov_schoar_2020` | [Trading and Arbitrage in Cryptocurrency Markets](https://doi.org/10.1016/j.jfineco.2019.07.001) | Makarov, Schoar (2018) | articulo · openalex | abierto / texto_completo | metadatos | 0/2 |
| `griffin_shams_2020` | [Is Bitcoin Really Un-Tethered?](https://doi.org/10.1111/jofi.12903) | Griffin, Shams (2018) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |
| `detzel_2021` | [Bitcoin: Predictability and Profitability via Technical Analysis](https://doi.org/10.1111/fima.12310) | Detzel, Liu, Strauss et al. (2018) | articulo · openalex | abierto / texto_completo | metadatos | 0/1 |
| `liu_tsyvinski_wu_2022` | [Common Risk Factors in Cryptocurrency](https://doi.org/10.1111/jofi.13119) | Liu, Tsyvinski, Wu (2019) | articulo · openalex | abierto / texto_completo | metadatos | 0/1 |
| `alexander_2020` | [BitMEX bitcoin derivatives: Price discovery, informational efficiency, and hedging effectiveness](https://doi.org/10.1002/fut.22050) | Alexander, Choi, Park et al. (2019) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |
| `brauneis_2021` | [How to Measure the Liquidity of Cryptocurrencies?](https://doi.org/10.1016/j.jbankfin.2020.106041) | Brauneis, Mestel, Riordan et al. (2019) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |
| `hudson_urquhart_2021` | [Technical trading and cryptocurrencies](https://doi.org/10.1007/s10479-019-03357-1) | Hudson, Urquhart (2019) | articulo · openalex | abierto / texto_completo | completo | 1/1 |
| `soska_2021_bitmex` | [Towards Understanding Cryptocurrency Derivatives:A Case Study of BitMEX](https://doi.org/10.1145/3442381.3450059) | Soska, Dong, Khodaverdian et al. (2021) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |
| `he_manela_2022` | [Fundamentals of Perpetual Futures](https://doi.org/10.2139/ssrn.4301150) | He, Manela, Ross et al. (2022) | preprint · openalex | abierto / texto_completo | resumen | 2/2 |
| `cong_2023_wash` | [Crypto Wash Trading](https://doi.org/10.1287/mnsc.2021.02709) | Cong, Li, Tang et al. (2022) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |
| `ackerer_2023_perp` | [Perpetual Futures Pricing](https://doi.org/10.48550/arxiv.2310.11771) | Ackerer, Hugonnier, Jermann (2023) | preprint · openalex | abierto / texto_completo | completo | 1/1 |
| `bis_bulletin_69` | [Crypto shocks and retail losses (BIS Bulletin n.º 69)](https://www.bis.org/publ/bisbull69.htm) | Cornelli, Doerr, Frost et al. (2023) | informe · web | gratuito / texto_completo | completo | 1/1 |

### G. Inteligencia artificial aplicada (13)

| id | Obra | Autores (año) | Tipo · fuente | Acceso / disponible | Leído | Posturas comprobadas |
|---|---|---|---|---|---|---|
| `moody_saffell_2001` | [Learning to trade via direct reinforcement](https://doi.org/10.1109/72.935097) | Moody, Saffell (2001) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `esl_2009` | [The Elements of Statistical Learning (2.ª ed.)](https://hastie.su.domains/ElemStatLearn/) | Hastie, Tibshirani, Friedman (2009) | libro · web | gratuito / texto_completo | metadatos | 0/1 |
| `kakushadze_2016` | [101 Formulaic Alphas](https://doi.org/10.48550/arxiv.1601.00991) | Kakushadze (2016) | preprint · openalex | abierto / texto_completo | completo | 1/1 |
| `fischer_krauss_2018` | [Deep learning with long short-term memory networks for financial market predictions](https://doi.org/10.1016/j.ejor.2017.11.054) | Fischer, Krauß (2017) | articulo · openalex | abierto / texto_completo | completo | 1/1 |
| `lopezdeprado_2018` | [Advances in Financial Machine Learning](https://www.wiley.com/en-us/Advances+in+Financial+Machine+Learning-p-9781119482086) | Prado (2018) | libro · web | suscripcion / solo_metadatos | metadatos | 0/1 |
| `sutton_barto_2018` | [Reinforcement Learning: An Introduction (2.ª ed.)](http://incompleteideas.net/book/the-book-2nd.html) | Sutton, Barto (2018) | libro · web | gratuito / texto_completo | metadatos | 0/1 |
| `sirignano_cont_2019` | [Universal features of price formation in financial markets: perspectives from deep learning](https://doi.org/10.1080/14697688.2019.1622295) | Sirignano, A (2019) | articulo · openalex | suscripcion / solo_resumen | resumen | 1/1 |
| `zhang_zohren_roberts_2019` | [DeepLOB: Deep Convolutional Neural Networks for Limit Order Books](https://doi.org/10.1109/tsp.2019.2907260) | Zhang, Zohren, Roberts (2019) | articulo · openalex | abierto / texto_completo | completo | 1/1 |
| `gu_kelly_xiu_2020` | [Empirical Asset Pricing via Machine Learning](https://doi.org/10.1093/rfs/hhaa009) | Gu, Kelly, Xiu (2020) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |
| `finrl_2020` | [FinRL: A Deep Reinforcement Learning Library for Automated Stock Trading in Quantitative Finance](https://doi.org/10.48550/arxiv.2011.09607) | Liu, Yang, Chen et al. (2020) | preprint · openalex | abierto / texto_completo | completo | 1/1 |
| `jaquart_2021` | [Short-term bitcoin market prediction via machine learning](https://doi.org/10.1016/j.jfds.2021.03.001) | Jaquart, Dann, Weinhardt (2021) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |
| `kelly_xiu_2023` | [Financial Machine Learning](https://doi.org/10.1561/500000064) | Kelly, Xiu (2023) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |
| `jiang_kelly_xiu_2023` | [(Re‐)Imag(in)ing Price Trends](https://doi.org/10.1111/jofi.13268) | Jiang, Kelly, Xiu (2023) | articulo · openalex | gratuito / texto_completo | resumen | 1/1 |

### H. Macrofinanzas y contexto económico (10)

| id | Obra | Autores (año) | Tipo · fuente | Acceso / disponible | Leído | Posturas comprobadas |
|---|---|---|---|---|---|---|
| `abdv_2003` | [Micro Effects of Macro Announcements: Real-Time Price Discovery in Foreign Exchange](https://doi.org/10.1257/000282803321455151) | Anderson, B, Diebold et al. (2003) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |
| `bernanke_kuttner_2005` | [What Explains the Stock Market's Reaction to Federal Reserve Policy?](https://doi.org/10.1111/j.1540-6261.2005.00760.x) | Bernanke, Kuttner (2005) | articulo · openalex | gratuito / texto_completo | resumen | 1/1 |
| `brunnermeier_pedersen_2009` | [Market Liquidity and Funding Liquidity](https://doi.org/10.1093/rfs/hhn098) | Brunnermeier, Pedersen (2008) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |
| `savor_wilson_2013` | [How Much Do Investors Care About Macroeconomic Risk? Evidence from Scheduled Economic Announcements](https://doi.org/10.1017/s002210901300015x) | Savor, Wilson (2011) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |
| `lucca_moench_2015` | [The Pre-FOMC Announcement Drift](https://doi.org/10.1111/jofi.12196) | Lucca, Moench (2012) | articulo · openalex | abierto / texto_completo | metadatos | 0/1 |
| `bouri_2017` | [On the hedge and safe haven properties of Bitcoin: Is it really more than a diversifier?](https://doi.org/10.1016/j.frl.2016.09.025) | Bouri, Molnár, Azzi et al. (2016) | articulo · openalex | abierto / texto_completo | metadatos | 0/1 |
| `baur_hong_lee_2018` | [Bitcoin: Medium of exchange or speculative assets?](https://doi.org/10.1016/j.intfin.2017.12.004) | Baur, Hong, Lee (2017) | articulo · openalex | abierto / texto_completo | metadatos | 0/1 |
| `corbet_2020_fomc` | [Cryptocurrency reaction to FOMC Announcements: Evidence of heterogeneity based on blockchain stack position](https://doi.org/10.1016/j.jfs.2019.100706) | Corbet, Larkin, Lucey et al. (2019) | articulo · openalex | abierto / texto_completo | metadatos | 0/1 |
| `miranda_agrippino_rey_2020` | [U.S. Monetary Policy and the Global Financial Cycle](https://doi.org/10.1093/restud/rdaa019) | Miranda‐Agrippino, Rey (2020) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |
| `conlon_mcgee_2020` | [Safe haven or risky hazard? Bitcoin during the Covid-19 bear market](https://doi.org/10.1016/j.frl.2020.101607) | Conlon, McGee (2020) | articulo · openalex | abierto / texto_completo | resumen | 1/1 |
