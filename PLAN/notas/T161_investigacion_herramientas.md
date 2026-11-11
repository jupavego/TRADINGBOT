# Medir mejor antes de buscar más señales

Lo que le falta a EIM no es otro indicador. Le faltan piezas de validación y de pronóstico de volatilidad, y dos o tres formas de estrategia que T139 todavía no ha probado en la forma en que las estudia la literatura. Varias de estas piezas son baratas. El núcleo de López de Prado y Bailey ya está en el código: PSR, Sharpe deflactado, PBO por CSCV, Romano-Wolf, purga y embargo. **Faltan MinTRL, el contraste SPA de Hansen, Benjamini-Hochberg, el bloque óptimo del bootstrap y la CPCV propiamente dicha.** En pronóstico, la evidencia más sólida apunta a la volatilidad y no a la dirección. Llevar el **Log-HAR-RV**, que ya existe para las salidas del papel, al cono de `forecast`, y envolver sus bandas con **conformal adaptativo (ACI)**, rinde más que cualquier modelo fundacional, porque estos **no superan al paseo aleatorio** en retornos. En estrategias quedan tres hipótesis con evidencia fuera de muestra:

- **Momentum de series temporales** como cartera lenta con volatilidad objetivo. T139 lo midió como entrada con stop, que es otra cosa.
- **Factores transversales**, incluido el **carry de funding transversal**, sobre muchos perps (T93–T96).
- La **prima de varianza** de opciones, como agente informativo.

En datos, el **DVOL de Deribit** es gratuito y no pide clave. Los netflows de USDT hacia exchanges tienen un único preprint a su favor. Casi todo lo demás (flujos de ETF, COT, Fear&Greed) va detrás del precio en lugar de anticiparlo. Hay que decirlo claro: **la mayoría de estas herramientas gestionan el riesgo o validan, no crean ventaja**. Su mejor uso tras T145 es cerrar con rigor las hipótesis inviables y evitar falsos descubrimientos si se reabre algún disparador. Todo lo que sigue son hipótesis de investigación, no asesoramiento financiero.

## El inventario: qué existe, qué está planeado y qué se descartó

Para separar lo nuevo de lo ya hecho, las notas contrastaron cada herramienta con el código (`grep` sobre `v2/eim` y `PLAN/`, commit 61cbcd3).

Ya hay código con pruebas para:

- PSR y Sharpe deflactado (`copytrading/stats.py`, usado por la puerta T49).
- PBO por CSCV y Romano-Wolf con bootstrap por días (`paper/exits/stats.py`, T131, que midió **PBO 0,46**).
- Holm y un p-valor de diferencia de Sharpe con bloque fijo √n (`backtest/edge.py`).
- Purga y embargo en el walk-forward de salidas y en el pre-registro de entradas.
- GARCH(1,1) con α y β fijos como motor del cono (`forecast/base_engine.py`).
- HAR-RV solo para el σ de las salidas (`paper/exits/harrv.py`).
- BOCPD en `agents/regime`.
- Pinball, cobertura y Brier en `forecast/eval.py` y `forecast/calibration.py`.
- Liquidaciones agregadas de Binance, Bybit y OKX (`data/collectors/liq_ws.py`).
- Carry de funding y base trimestral (`arbitrage/`).

Están planeados pero sin hacer:

- Benjamini-Hochberg (T95, T129-E7).
- Triple barrera para HFT (T80).
- CUSUM como vigilancia de degradación (T85).
- HMM para HFT (T77).
- Escáner y cartera transversal (T93–T96).
- Opciones e IV, de forma genérica (T100, BACKLOG).
- El reescalado heterocedástico de σ (BACKLOG T28 (1), con una mejora de pinball de ≈0,9 %).

Ya se descartaron o se aplazaron, con razones registradas:

- vectorbt, solo como oráculo.
- backtesting.py, por su licencia AGPL.
- Qlib, FinGPT y RD-Agent.
- DeepLOB y Transformers sobre el libro, por falta de GPU.
- River, que solo entraría si T85 demuestra deriva.
- La clase C de creación de mercado: a VIP0, las comisiones son ≈325 veces el diferencial.
- La reversión tras cascadas de liquidación y el funding a la contra, ambos con neto negativo en T139.

Este inventario importa porque buena parte de lo que se recomienda en abstracto (DSR, PBO, Romano-Wolf, Kelly con cota inferior) **EIM ya lo tiene**. Lo genuinamente nuevo es más estrecho y casi siempre más barato de lo que parece.

## Cinco piezas de validación por menos de 200 líneas

El aporte de mayor valor por línea de código es **MinTRL**, la longitud mínima de historial de Bailey y López de Prado. Indica cuántas observaciones hacen falta para rechazar que el Sharpe real esté por debajo de un umbral, ajustando por asimetría y curtosis ([Risk.net](https://risk.net/node/2223785); fórmula en [Portfolio Optimizer](https://portfoliooptimizer.io/blog/the-probabilistic-sharpe-ratio-bias-adjustment-confidence-intervals-hypothesis-testing-and-minimum-track-record-length/)). Son unas diez líneas sobre `psr` y `sharpe_se`, que ya existen. Con el veredicto T145 (bruto de +0,012 a +0,060 R frente a los 0,19–0,50 R necesarios), MinTRL permite declarar inviable una hipótesis **antes** de gastar un intento de la familia de Holm, y fija con criterio la duración mínima del paper trading de T31.

La segunda pieza es el **contraste SPA de Hansen**, la versión con más potencia del Reality Check de White. Responde a la pregunta exacta de T137 y T145: si alguna de las N entradas probadas supera a la base una vez se tiene en cuenta que se eligió la mejor. El paquete `arch` incluye SPA, StepM (Romano-Wolf), el Model Confidence Set, el bootstrap estacionario y `optimal_block_length` de Politis-White ([arch SPA](https://arch.readthedocs.io/en/latest/multiple-comparison/generated/arch.bootstrap.SPA.html), [optimal_block_length](https://arch.readthedocs.io/en/latest/bootstrap/generated/arch.bootstrap.optimal_block_length.html)). Es la única dependencia nueva de esta lista que se justifica, porque reimplementar bien SPA y MCS es delicado. Su licencia es NCSA, permisiva, según la nota T77 y PyPI ([PyPI arch](https://pypi.org/pypi/arch/json)), aunque GitHub no la detecta automáticamente y conviene leer el archivo LICENSE.

El **bloque óptimo** del bootstrap corrige un punto concreto: `edge.sharpe_diff_pvalue` usa hoy un bloque fijo de √n, el mismo valor por defecto que la documentación de `arch` desaconseja ([StepM](https://bashtage.github.io/arch/multiple-comparison/generated/arch.bootstrap.StepM.html)). El **MCS** sirve para `forecast/eval.py`: en lugar de declarar un ganador por una diferencia de pinball ruidosa, devuelve el conjunto de motores que no son peores que el mejor. **Benjamini-Hochberg** ya está decidido y falta codificarlo.

La **CPCV** completa el banco. Hoy el walk-forward de T131 produce una sola trayectoria fuera de muestra; la CPCV produce varias y, con ellas, una distribución del Sharpe. Aplica sobre todo a la calibración con optuna, donde el riesgo de sobreajuste es mayor. Un estudio en entorno sintético halló menor PBO y mayor DSR con CPCV que con walk-forward ([Arian et al., resumen](https://bohrium.dp.tech/paper/arxiv/324dfd175c19894198c6e870b5d6427eec1a3ff441baa75b0dbd5e856e73e5f8)), pero la evidencia es solo sintética. `skfolio` la implementa con licencia BSD-3 ([código](https://skfolio.org/_modules/skfolio/model_selection/_combinatorial.html)). Arrastra cvxpy, scikit-learn y plotly ([PyPI](https://pypi.org/pypi/skfolio/json)), así que conviene portar la lógica, ya que la purga y el embargo existen, y usar skfolio como mucho de oráculo en un venv aparte.

El **Haircut Sharpe** de Harvey y Liu penaliza poco los Sharpe altos y mucho los marginales ([PDF Duke](https://people.duke.edu/~charvey/Research/Published_Papers/P120_Backtesting.PDF)). Sería redundante con DSR y Holm, útil solo como verificación cruzada en los informes.

Del bloque de López de Prado, el método con más encaje es el **meta-labeling** ([Joubert 2022, vía Wikipedia](https://en.wikipedia.org/wiki/Meta-Labeling)). El modelo primario, las señales de T137 o la síntesis, fija el lado; un meta-modelo determinista decide solo si se toma la operación y con qué tamaño. La advertencia es seria: **no encontré evidencia revisada por pares con datos reales y netos de costos** a su favor. Además, solo ayuda si existe un subconjunto condicional (por régimen, funding o volatilidad) con E[R] mayor que el costo, y cada rasgo cuenta como un intento.

La triple barrera generalizada con `CostParams`, como etiqueta común de `analytics/event_study.py`, los pesos por unicidad y el filtro CUSUM de eventos son baratos, pero secundarios. Las librerías de AFML en Python tienen licencia BUSL o un mantenimiento incierto ([pymlfinance](https://pypi.org/project/pymlfinance/), [mlfinpy](https://mlfinpy.readthedocs.io/en/latest/UserGuide.html)), lo que refuerza la norma de T129 de reutilizar métodos y no código. Ni la diferenciación fraccional, ni las barras de dólar o de desequilibrio, ni las GAN sintéticas atacan el problema central, que el costo supera al edge bruto.

Para las señales hay un análisis que falta y que es casi gratuito: la **curva de decaimiento IC(h) con su vida media**, sobre `analytics/technical_ic.py`, que ya mide varios horizontes. Separa dos diagnósticos que T145 no distingue. Si el IC existe pero se apaga en horas, el problema es de horizonte y de costo de rotación. Si es plano y cercano a cero, la señal no tiene información. alphalens-reloaded (Apache-2.0) está diseñado para sección cruzada de muchos activos y arrastra dependencias de gráficos ([PyPI](https://pypi.org/pypi/alphalens-reloaded/json)). Con dos activos bastan las fórmulas.

## Solo tres familias de estrategia nuevas tienen evidencia fuera de muestra

**El momentum de series temporales que midió T139 no es el de la literatura.** `momento_1d@1d` evaluó cada operación en R contra un stop (n = 121, +0,048 R netos). La literatura mide otra cosa: una cartera siempre posicionada, dimensionada por volatilidad, con rebalanceo semanal o mensual y rotación baja. En futuros tradicionales, reducir la rotación es lo que mejora el neto ([CME/Imperial](https://www.cmegroup.com/education/files/improving-time-series-momentum-strategies.pdf)).

La evidencia en cripto es de preprints recientes y viene dividida:

- **A favor.** Un trabajo informa de un Sharpe fuera de muestra de **1,41 neto de 25 pb** en *majors*, aunque los autores admiten sesgo de supervivencia y que no superan un umbral de pruebas múltiples ([SSRN 7115459](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7115459)). Otro, con señales de 6 h sobre más de 150 pares entre 2022 y 2024, reporta un Sharpe de 2,41 ([arXiv 2602.11708](https://arxiv.org/abs/2602.11708)).
- **En contra.** Un tercero sostiene que es **una ventaja publicada que ha envejecido**: el retorno bruto depende de un único dato atípico y la escala por volatilidad no ayuda en el régimen actual ([SSRN 7405060](https://papers.ssrn.com/sol3/Delivery.cfm/7405060.pdf?abstractid=7405060&mirid=1)).

Las cifras de los dos trabajos de SSRN proceden de resúmenes, porque el texto completo devolvió 403. La forma honesta de probarlo es **pre-registrar una sola especificación**, por ejemplo promediando lookbacks de 20, 60 y 120 días, y evaluar el tramo 2024–2026 por separado. Con unos 10 pb por ida y vuelta y de 10 a 25 cambios de signo al año, la carga de costo es de pocos puntos porcentuales frente a una volatilidad del 50–80 %, mucho menor que en 15 min o 1 h. Este cálculo es propio y debe verificarse con los costos de T48b y T137.

**El momentum transversal de corto plazo es el factor más robusto de la literatura académica cripto.** Liu, Tsyvinski y Wu explican la sección cruzada con tres factores: mercado, tamaño y momentum ([Journal of Finance 2022](https://econpapers.repec.org/RePEc:bla:jfinan:v:77:y:2022:i:2:p:1133-1177)). La actualización, que incluye 29 230 monedas deslistadas, encuentra un momentum de dos semanas de **+2,6 % semanal (t 3,89), y de +2,1 % (t 3,70) después de 2020**. El tamaño se debilita. Pero ese trabajo **no analiza costos** ([arXiv 2510.14435](https://arxiv.org/html/2510.14435v4)), y un estudio de 2026 sobre perps concluye que la alta rotación hace que el neto dependa de la implementación ([Physica A](https://www.sciencedirect.com/science/article/abs/pii/S0378437126006473)).

La extensión más directa de lo único que dio neto positivo en EIM (la clase B, +102,5 pb por operación) es el **carry de funding transversal**. Siempre hay perps con funding extremo, así que no hace falta esperar a que BTC o ETH vuelvan a pagar un 4 % anual o más. La única evidencia es informal: un análisis de 6,1 M liquidaciones de funding en el que la señal funding/volatilidad tiene un **IC de +0,041 (t 12,9)** ([GitHub funding-rate-alpha](https://github.com/OctopusTakopi/funding-rate-alpha)). Todo depende del universo multiactivo de T93–T96, que no está construido. El trabajo del BIS añade un matiz útil como condicionante y no como operación: un **carry alto predice caídas futuras de precio** ([BIS WP 1087](https://www.bis.org/publ/work1087.htm)). También confirma lo que midió EIM: el carry se comprimió desde 2024 y fue **negativo en 2025** ([arXiv 2510.14435](https://arxiv.org/html/2510.14435v4)).

**La prima de varianza de BTC es positiva, persistente y mayor que la del S&P 500** ([Almeida et al., arXiv 2410.15195](https://arxiv.org/pdf/2410.15195)), y las straddles vendidas con cobertura delta destacan en Deribit ([ResearchGate](https://www.researchgate.net/publication/404913556_What_Do_Crypto_Options_Tell_Us_Risk_Premia_Implied_by_BTC_Option_Prices)). Explotarla exige otro venue, griegas y gestión de colas. En un EIM de solo análisis encaja como agente informativo (VRP, skew, vol de la vol), no como estrategia.

Lo demás tiene poco recorrido:

- **Reversión tras liquidaciones.** Ya dio negativo en EIM y no hay estudio que la respalde ([AEA 2026](https://www.aeaweb.org/conference/2026/program/paper/ByyFEfr4)).
- **Efectos horarios.** El de 21 a 23 UTC es un backtest dentro de muestra ([Quantpedia](https://quantpedia.com/the-seasonality-of-bitcoin/?a=6080)), con 365 idas y vueltas al año: el perfil que T137 ya mostró inviable. Sirve como mucho de filtro horario.

El dimensionamiento redistribuye riesgo y no crea ventaja. La volatilidad objetivo reduce de forma constante las colas y el drawdown, pero solo sube el Sharpe en activos de riesgo ([Harvey et al. 2018](https://people.duke.edu/~charvey/Research/Published_Papers/P135_The_impact_of.pdf)). HRP supera a otras carteras en riesgo de cola sobre cripto ([Burggraf 2021](https://ideas.repec.org/a/eee/finlet/v38y2021ics154461232030177x.html)), pero con BTC y ETH, muy correlacionados, apenas se distingue de la inversa de volatilidad. Kelly con cota inferior, que `kelly_view` ya tiene, da un tamaño cercano a cero con las entradas actuales, y eso es lo correcto. En ejecución, un experimento en vivo con 232 897 órdenes maker sobre BTCUSDT muestra que **no es fácil conseguir a la vez una alta probabilidad de llenado y un retorno posterior positivo** ([arXiv 2502.18625](https://arxiv.org/pdf/2502.18625)). Ejecutar como maker con paso a taker solo es plausible para rebalanceos lentos.

## La volatilidad sí se predice; los modelos fundacionales no aportan dirección

El contexto lo fija el BACKLOG (T28): el cono **no tiene habilidad direccional** (Brier −0,4 %, pinball −1,2 %), pero sus bandas están calibradas. Por eso el valor está en la volatilidad y en la distribución.

En BTC, los modelos HAR con varianza realizada intradía superan a GARCH sobre datos diarios, sobre todo a corto plazo ([UiS](https://uis.brage.unit.no/uis-xmlui/handle/11250/2980915)). Modelar los saltos solo ayuda en horizontes largos ([Hu, Härdle y Kuo](https://arxiv.org/abs/1912.05228)). Ninguno de estos estudios se leyó completo. Aun así, EIM tiene HAR-RV en el lugar equivocado: lo usa para las salidas del papel, mientras el cono sigue con un GARCH(1,1) de parámetros fijos. **Llevar Log-HAR-RV al cono**, reutilizando `harrv.py`, y evaluarlo con QLIKE y pinball en la misma puerta es la mejora de pronóstico más barata y mejor respaldada. Un GARCH estimado (EGARCH o GJR con t de Student, mediante `arch`) y la **combinación de ambos con pesos iguales** son los siguientes pasos.

Los modelos fundacionales (Chronos-2, TimesFM-2.5, TiRex, Moirai) están casi empatados en benchmarks generales ([Chronos-2](https://arxiv.org/html/2510.15821v1)), pero eso no se traslada a finanzas:

- **Retornos de acciones de 94 países.** Sin ajuste previo (cero-shot) dan **R² negativo**: −1,37 % Chronos y −2,80 % TimesFM ([arXiv 2511.18578](https://arxiv.org/html/2511.18578v1)).
- **Volatilidad realizada en 50 activos.** Casi ninguno supera a Log-HAR. La excepción es TTM, con menos de 1 M de parámetros (ratio QLIKE 0,982), y **el promedio TTM + Log-HAR entra en el MCS en el 98–100 % de los activos** ([Brini, arXiv 2607.05291](https://arxiv.org/html/2607.05291v1)).
- **BTC a 1 minuto.** El único test cripto directo es un repositorio individual. Ningún modelo bate al paseo aleatorio en RMSE. Las bandas de TimesFM mejoran **≈1,4 % el pinball**, y las bandas del 80 % de **Kronos solo cubrieron entre el 58 y el 68 %** ([TFMBT](https://github.com/rickyegl/TFMBT)).

Las cifras favorables de Kronos son de sus propios autores ([arXiv 2508.02739](https://arxiv.org/html/2508.02739v1)). La conclusión práctica: **medir Kronos con la puerta de calibración y probablemente archivarlo**. Un modelo fundacional entraría como mucho como fuente alternativa de cuantiles. Su mejora esperada, de alrededor del 1 %, es la misma que da el reescalado de T28 (1), que es más barato y no requiere torch.

La capa que falta sobre las bandas es la **calibración conformal adaptativa (ACI de Gibbs y Candès)**. El intervalo se ensancha cuando el valor real cae fuera y se estrecha cuando cae dentro, lo que garantiza la cobertura a largo plazo incluso con cambios de régimen ([MAPIE](https://mapie.readthedocs.io/en/stable/generated/mapie.regression.TimeSeriesRegressor.html)). Son unas veinte líneas de NumPy, sin scikit-learn, y encajan con la regla de que toda proyección es probabilística. La acompañan tres métricas:

- **CRPS**: una puntuación única de toda la distribución.
- **Energy score**: para trayectorias de varios pasos y la dependencia entre BTC y ETH ([scoringrules](https://github.com/frazane/scoringrules)). Este paquete exige Python 3.12 o superior ([PyPI](https://pypi.org/pypi/scoringrules/json)) y no se comprobó la versión del venv. El CRPS de ensamble se puede escribir con NumPy.
- **Diagramas de Murphy**: indican si un motor domina a otro bajo **todas** las funciones de puntuación consistentes ([Ehm et al. 2016](https://rdrr.io/cran/murphydiagram)).

En régimen, los **modelos de salto estadísticos** de Nystrup y de Shu, Yu y Mulvey dan estados más persistentes que un HMM. En índices de acciones entre 1990 y 2023, **fuera de muestra, con costos y retardo**, reducen la volatilidad y el drawdown y mejoran el Sharpe frente al HMM y a comprar y mantener ([arXiv 2402.05272](https://arxiv.org/abs/2402.05272)). No hay prueba en BTC. Complementan a BOCPD, que detecta cambios en línea, con un etiquetado persistente, y su costo de CPU es trivial (paquete `jumpmodels` ([PyPI](https://pypi.org/project/jumpmodels)), con licencia sin verificar). Su penalización se elige por validación, así que cuenta como intento. Según esta evidencia, dominan al HMM planeado en T77 y al Markov switching que T133 dejó sin abrir: conviene compararlos en el banco de T133 antes de construir más de uno.

El boosting para el signo del retorno no cambia el veredicto. En BTC, entre 1 y 60 minutos, **no compensa los costos** ([J. Finance & Data Science 2021](https://publikationen.bibliothek.kit.edu/1000150665/149388567)). Solo tiene sentido con objetivo cuantílico o sobre la volatilidad.

## DVOL es gratis; casi todos los demás datos alternativos siguen al precio

El dato nuevo con mejor encaje es el **DVOL de Deribit**. El método `public/get_volatility_index_data` es público, no pide clave y devuelve velas de 60 minutos ([Deribit docs](https://docs.deribit.com/api-reference/market-data/public-get_volatility_index_data)). Una llamada REST por hora es trivial en este equipo.

La evidencia lo justifica como insumo de **volatilidad** y no de dirección. La IV aporta información incremental sobre la volatilidad realizada ([vLex](https://eu.vlex.com/vid/forecasting-the-volatility-of-1049450990)), pero por sí sola es **menos precisa que un HAR** ([vLex](https://law-journals-books.vlex.com/vid/forecasting-bitcoin-volatility-evidence-855595395)). Por eso debe entrar en `regime`, en las bandas y en el tamaño de los stops, no como voto.

El skew de 25Δ, o risk reversal, predijo retornos de BTC entre 2021 y 2025 según una tesis que además informa de que **la señal se atenúa desde enero de 2024**, cuando llegaron los ETF ([SMU](https://ink.library.smu.edu.sg/etd_coll/887)). Merece una medición de IC fuera de muestra con la sospecha a priori de que ya no funciona. La gamma de los dealers es una heurística mal identificada ([Glassnode](https://research.glassnode.com/gamma-exposure/)) y no debe usarse.

En on-chain, el hallazgo más útil es un preprint: los **netflows de USDT hacia exchanges predicen positivamente los retornos de BTC y ETH a 1–6 h**, mientras que los netflows de BTC no lo hacen ([Chi, Chu y Hao, arXiv 2411.06327](https://arxiv.org/abs/2411.06327)). Además, su resumen y su conclusión se contradicen en parte. El obstáculo práctico es el dato: los flujos por exchange dependen del etiquetado de direcciones, que es de pago. CoinMetrics Community es gratuito, sin clave, con un límite de 10 peticiones cada 6 s ([docs](https://docs.coinmetrics.io/packages/coin-metrics-community-data)), pero no se verificó si ofrece resolución horaria. La oferta total de stablecoins de DefiLlama sirve como variable lenta de liquidez y no de *timing*. Para MVRV y SOPR no hay evidencia revisada por pares a horizontes diarios.

Las señales entre plataformas decepcionan:

- **Flujos de ETF.** Correlacionan 0,54 con los cinco días anteriores y solo 0,03 con los cinco siguientes ([Cointelegraph/DWF Labs](https://cointelegraph.com/news/bitcoin-etf-flows-follow-price-trends-dwf-labs)): confirman el movimiento, no lo predicen.
- **COT de la CME.** Está contaminado por el basis trade ([NYDIG](https://nydig.com/research/futures-data-highlights-trader-positioning)).
- **Spreads entre exchanges.** Makarov y Schoar muestran que predicen el retorno **relativo** de cada exchange, no el del mercado ([LSE](https://personal.lse.ac.uk/makarov1/index_files/CryptocurrencyMarkets.pdf)).

El Coinbase premium y el OI y funding de Bybit y OKX son baratos de añadir, porque ya hay conexiones con esos exchanges, pero solo como contexto mientras su IC no esté medido. La atención en Google predice retornos **dentro de muestra** ([Liu y Tsyvinski, NBER](https://www.nber.org/system/files/working_papers/w24877/w24877.pdf)). Fuera de muestra, su efecto se nota en la varianza más que en la media ([Figà-Talamanca y Patacca](https://springerlink.bibliotecabuap.elogim.com/content/pdf/10.1007/s10203-019-00258-7.pdf)). El Fear&Greed solo tiene estudios con muestras cortas.

En infraestructura, el hallazgo más relevante es de licencia, no de código. Los datos de **data.binance.vision**, que EIM ya usa, se publican bajo CC BY-NC-SA 4.0. Sus términos permiten la investigación personal pero **prohíben usarlos para «live proprietary trading execution»** ([TERMS](https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md)). Es compatible con el modo de solo análisis, pero bloquearía cualquier paso a operación real y debería figurar como criterio de la puerta T27.

**Tardis.dev** regala el primer día de cada mes, de cualquier exchange y tipo de dato ([FAQ](https://docs.tardis.dev/faq/billing-and-subscriptions)). Incluye el libro L2 de Binance USD-M desde 2019, con un límite: `forceOrder` publica solo una liquidación por segundo y símbolo ([docs](https://docs.tardis.dev/historical-data-details/binance-futures)). Esos días gratuitos sirven de **banco de validación sin costo** para el colector propio.

**pandera** (MIT) ofrece esquemas declarativos para validar los Parquet de `data/` ([GitHub](https://github.com/unionai-oss/pandera)), en línea con la regla de que toda cifra exponga su fuente y su cobertura, aunque las comprobaciones SQL en DuckDB pueden bastar. Las notas también detectan una incoherencia: T77 fijó un extra `hft` con statsmodels, arch y scikit-learn, pero ese extra **no existe** en `pyproject.toml`.

Se descartan, con motivos:

- **vectorbt 1.x.** Tiene motor Rust, pero el apalancamiento y los contratos de futuros siguen siendo solo de la versión PRO ([PyPI](https://pypi.org/project/vectorbt/)).
- **ArcticDB**, por su licencia BSL.
- **MLflow, DVC y Great Expectations**, por pesados o redundantes.
- **tsfresh y featuretools**, que multiplican rasgos y pruebas.
- **RD-Agent**, que solo corre en Linux y necesita Docker ([GitHub](https://github.com/microsoft/RD-Agent)).

## Clasificación por impacto esperado y fuerza de la evidencia

| # | Herramienta | Qué resuelve | Evidencia | Crea ventaja | Costo en este PC |
|---|---|---|---|---|---|
| 1 | MinTRL + potencia a priori | Descartar hipótesis inviables antes de probarlas; duración del papel (T31) | Fuerte (teoría publicada) | No | Trivial |
| 2 | Hansen SPA + MCS + bloque óptimo (`arch`) | Contraste global de la familia T137; elección de motores | Fuerte (estándar econométrico) | No | Ligero |
| 3 | Log-HAR-RV en el cono + combinación con GARCH | Mejor σ para las bandas y los stops | Fuerte en BTC y en 50 activos | No (mejor riesgo) | Trivial |
| 4 | ACI conformal + CRPS/PIT/Murphy | Cobertura garantizada; métrica de toda la distribución | Media-fuerte (teoría; sin prueba cripto) | No | Trivial |
| 5 | Cartera TSMOM lenta con volatilidad objetivo (pre-registrada) | Forma de la literatura que T139 no probó | Media, dividida (preprints) | Posible | Ligero |
| 6 | Carry de funding transversal + momentum transversal (T93–T96) | Extiende la clase B sin depender del funding de BTC/ETH | Media (académica bruta; funding informal) | Posible | Medio (universo multiactivo) |
| 7 | DVOL/VRP de Deribit como insumo de volatilidad | Régimen y bandas con información implícita | Media (incremental sobre HAR) | No | Trivial |
| 8 | Modelo de saltos frente a HMM y BOCPD (banco T133) | Regímenes persistentes | Media (acciones con costos; sin BTC) | Indirecto | Trivial |
| 9 | Curva IC(h), vida media y neutralización | Distinguir «sin información» de «demasiado costo» | Método estándar | No (diagnóstico) | Trivial |
| 10 | Benjamini-Hochberg, CPCV y Haircut Sharpe | Completar el banco de validación | Media (CPCV solo sintética) | No | Ligero |
| 11 | Meta-labeling bajo la puerta existente | Filtrar el subconjunto condicional con E[R] > costo | Débil (sin datos reales netos) | Posible | Ligero |
| 12 | Netflow de USDT y skew 25Δ (medición de IC) | Posibles señales de 1–6 h | Débil (un preprint; una tesis que se atenúa) | Posible | Ligero si el dato es gratuito |

Lista corta propuesta como futuras tareas del PLAN. Son hipótesis de investigación y no asesoramiento financiero. El número de tarea lo asigna STATUS, comprobando antes el remoto.

| Propuesta | Hipótesis por contrastar | Criterio de cierre |
|---|---|---|
| **Txx-A Potencia y SPA** | Ninguna entrada de T137/T139 supera a la base tras SPA, y el MinTRL de las mejores supera la historia disponible | p de SPA de la familia y tabla MinTRL por hipótesis en `validation/` |
| **Txx-B Cono HAR + conformal** | Log-HAR (o HAR+GARCH) con ACI mejora el QLIKE y el pinball del cono y mantiene la cobertura del 80 % ±2 pp | MCS de motores, CRPS y PIT en `forecast/eval.py` |
| **Txx-C Cartera TSMOM pre-registrada** | Una cartera BTC+ETH de tendencia diaria con volatilidad objetivo tiene un Sharpe neto mayor que 0 en 2024–2026 con una sola especificación | Puerta T49 + PBO + MinTRL; resultado negativo publicado si falla |
| **Txx-D Carry de funding transversal** | Ordenar perps por funding/volatilidad da un carry neto positivo con beta de mercado ≈0 | Requiere T93; puerta T95 con BH y Holm |
| **Txx-E DVOL/VRP en régimen** | El DVOL mejora el pronóstico de σ a 1 día sobre HAR solo | Colector en `data/`; ganancia de QLIKE en el MCS |
| **Txx-F Régimen JM frente a HMM frente a BOCPD** | El modelo de saltos da estados más estables y mejor condicionamiento que BOCPD | Banco T133; penalización contada como intento |

Restricción operativa común: todo barrido de SPA, CPCV, bootstrap o calibración va por la cola `eim.operation.jobs`, con **2 procesos como máximo**, en prioridad IDLE y con un `--min-ram-mb` realista. Si entra torch (Kronos o un modelo fundacional), cada corrida necesita de 1.500 a 2.500 MB y debe avisarse antes de lanzarla, porque la memoria, no la CPU, es lo que perjudica a la captura.

## Conclusión

La investigación cambia el diagnóstico de qué le falta a EIM. Encontrar una ventaja requiere hoy menos herramientas de las que parece, y casi todas son de rigor. Las únicas hipótesis de retorno con evidencia fuera de muestra tienen algo en común: la ventaja se cobra a horizontes de días o semanas, no de horas, y es relativa o es una prima de riesgo, no una predicción de dirección. La cartera de tendencia lenta, el carry transversal y la prima de varianza cumplen esas condiciones. Es el perfil opuesto al de las entradas intradía que T137 y T139 cerraron. Si alguna existe para EIM, aparecerá en el universo de T93–T96 o en la cartera lenta, no en un indicador más sobre BTCUSDT a 1 h.

La mayor parte del resto vale más como freno que como motor. MinTRL y SPA convierten el «no hay ventaja» de T145 en una afirmación con número y fecha de caducidad. HAR, ACI y DVOL hacen que el producto de solo análisis sea mejor en lo que ya hace bien, la incertidumbre calibrada. Tampoco hay que olvidar la licencia de data.binance.vision: cualquier reapertura hacia la operación real debe empezar por resolver de dónde salen legalmente los datos con los que se decide.
