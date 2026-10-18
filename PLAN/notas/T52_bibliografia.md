# T52 — Bibliografía base para los agentes bibliográficos (aprobada por el usuario el 2026-10-18)

Estado: **tengo** = en la carpeta `Books` del usuario · **DP** = dominio público en EE. UU. (publicado antes de 1931; confirmar en el país del usuario antes de descargar) · **abierto** = artículo de acceso libre · **conseguir** = comprar o prestar. Nada se descarga sin el visto bueno del usuario para cada archivo, y nunca copias no autorizadas.

Prioridad para codificar (T53/T54): lo que el autor respalda con cifras y lo que tiene evidencia académica. Lo anecdótico informa, pero no se convierte en estrategia.

## Primer lote: resultado de la ingesta (T52, 2026-10-18)
`python -m eim.library ingest` sobre la carpeta `Books` (índice local en `v2/data/library/index/` del checkout principal; nada de esto se versiona). Páginas = del **archivo** (1 = primera), no las impresas: en Nison el desfase es variable (~14–20), en Murphy +37 en los caps. 4–9 y creciente después.
| id | Págs. | Con texto | Notas |
|---|---|---|---|
| `nison_candles` | 298 | 292 | 6 sin texto (en blanco o figura). |
| `murphy_ta` | 596 | 572 (OCR) | Escaneo CCITT de 1 bit (no JPEG); OCR con Tesseract 5.4 `eng`, ~3 s/página con caché por página; 24 sin texto (en blanco o solo figura). Calidad buena; algún error suelto (p. ej. «Jeader»). |
| `douglas_zone` | 143 | 142 | El texto trae espacios dentro de palabras («ta ke»); la verificación de citas lo tolera. |
| `douglas_disciplined` | 184 | 183 | Igual que el anterior. |
| `steenbarger_coach` | 370 | 370 (2 OCR) | — |
| `schwager_wizards_es` | 203 | 203 | **Traducción al español de procedencia no indicada** (cabecera «ProfitMindFX»; títulos de capítulo sin traducir, parece traducción automática). Las citas y paráfrasis se refieren a ese archivo, no a la edición original. |
| `lefevre_reminiscences` | 269 | 269 | El libro termina hacia la p. 257; **las pp. 258–269 son artículos de revistas añadidos** (TRADERS', Active Trader —M. Covel—, boletín de la MTA), ajenos al libro y con derechos propios: no se citan (BACKLOG T52). Texto con letras separadas («m oney»). |
`3.0 Japanese candelstick.crdownload` (otra copia de Nison) se omite. Fichas: 138 (`eim/library/cards/`), todas `verificada_en_texto` (`python -m eim.library verify`) y **`revisada_usuario`** (◆ 2026-10-18: Nison y Murphy ficha a ficha; conducta y cruces por delegación expresa del usuario; detalle en `PLAN/notas/T52_fichas_revision.md`); 3 de ellas cruzan autores y señalan contradicciones (`cruces.json`). El usuario aprobó también esta bibliografía como lista de trabajo; las obras «DP» y los artículos «abierto» siguen requiriendo su visto bueno **por archivo** antes de descargarse (T52.md, entregable 5).

## A. Análisis técnico clásico (reglas codificables)
| Obra | Por qué sirve | Estado |
|---|---|---|
| Steve Nison, *Japanese Candlestick Charting Techniques*, 2.ª ed. (2001) | Patrones de velas con reglas de confirmación | tengo · catalogado, 43 fichas |
| John J. Murphy, *Technical Analysis of the Financial Markets* (1999) | Manual de referencia: tendencia, niveles, osciladores, divergencias, volumen | tengo · catalogado con OCR, 48 fichas |
| Thomas N. Bulkowski, *Encyclopedia of Chart Patterns* (2.ª ed. 2005; 3.ª ed. 2021) | Estadísticas de acierto y fallo por patrón: lo más comprobable del género | conseguir |
| Robert D. Edwards y John Magee, *Technical Analysis of Stock Trends* (1948; ediciones posteriores) | Origen de los patrones chartistas clásicos | conseguir |
| Martin J. Pring, *Technical Analysis Explained* (5.ª ed. 2014) | Momento, ciclos y confirmación entre marcos | conseguir |
| A. J. Frost y Robert R. Prechter, *Elliott Wave Principle* (1978) | Reglas de conteo; contrasta con el agente `elliott` | conseguir |
| Al Brooks, *Trading Price Action Trends* (2011) | Acción del precio intradía (15 m/1 h) | conseguir |

## B. Volumen, estructura y subasta
| Obra | Por qué sirve | Estado |
|---|---|---|
| Richard D. Wyckoff (como «Rollo Tape»), *Studies in Tape Reading* (1910) | Lectura de oferta y demanda; base del método Wyckoff | DP |
| Richard W. Schabacker, *Stock Market Theory and Practice* (1930) | Primer tratado sistemático de patrones | DP |
| William P. Hamilton, *The Stock Market Barometer* (1922) | Teoría de Dow de primera mano | DP |
| Hank Pruden, *The Three Skills of Top Trading* (2007) | Wyckoff moderno, fases de acumulación/distribución | conseguir |
| James F. Dalton y otros, *Mind Over Markets* (1990; ed. actualizada 2013) | Perfil de mercado y valor | conseguir |

## C. Sistemas, evidencia y validación (alimentan la puerta T49)
| Obra | Por qué sirve | Estado |
|---|---|---|
| David Aronson, *Evidence-Based Technical Analysis* (2006) | Cómo probar reglas técnicas sin engañarse (sesgo de minería de datos) | conseguir |
| Perry J. Kaufman, *Trading Systems and Methods* (6.ª ed. 2019) | Catálogo de sistemas con resultados | conseguir |
| Ernest P. Chan, *Algorithmic Trading* (2013) | Reversión a la media y momento con pruebas estadísticas | conseguir |
| Marcos López de Prado, *Advances in Financial Machine Learning* (2018) | Validación cruzada con purga, etiquetado triple barrera, sobreajuste | conseguir |
| Robert Carver, *Systematic Trading* (2015) | Diseño de sistemas y tamaño de posición | conseguir |
| Andreas F. Clenow, *Following the Trend* (2013) | Seguimiento de tendencia en futuros | conseguir |

## D. Riesgo, tamaño y conducta del operador
| Obra | Por qué sirve | Estado |
|---|---|---|
| Mark Douglas, *Trading in the Zone* (2000) | Pensamiento probabilístico, aceptación del riesgo | tengo · catalogado, 8 fichas |
| Mark Douglas, *The Disciplined Trader* (1990) | Disciplina y conducta | tengo · catalogado, 8 fichas |
| Brett N. Steenbarger, *The Daily Trading Coach* (2009) | Revisión del desempeño; encaja con el ciclo de mejora (T48/T51) | tengo · catalogado, 11 fichas |
| Jack D. Schwager, *Market Wizards* (1989), en español | Principios de gestión del riesgo de operadores reales | tengo · catalogado, 10 fichas (ver nota) |
| Edwin Lefèvre, *Reminiscences of a Stock Operator* (1923) | Principios clásicos de especulación | tengo (además DP) · catalogado, 7 fichas (ver nota) |
| Van K. Tharp, *Trade Your Way to Financial Freedom* (2.ª ed. 2006) | Expectativa y tamaño de posición en R | conseguir |
| Ralph Vince, *The Mathematics of Money Management* (1992) | Fracción óptima y riesgo de ruina | conseguir |

## E. Microestructura y riesgo de colas
| Obra | Por qué sirve | Estado |
|---|---|---|
| Larry Harris, *Trading and Exchanges* (2003) | Microestructura; contrasta con el agente OFI (T23) | conseguir |
| Benoit Mandelbrot y Richard L. Hudson, *The (Mis)Behavior of Markets* (2004) | Colas gruesas: argumento para las bandas de los escenarios | conseguir |

## F. Artículos académicos (evidencia cuantitativa)
| Artículo | Por qué sirve | Estado |
|---|---|---|
| Brock, Lakonishok y LeBaron (1992), «Simple Technical Trading Rules and the Stochastic Properties of Stock Returns», *Journal of Finance* | Medias móviles y rupturas de rango con contraste formal | conseguir / buscar versión abierta |
| Lo, Mamaysky y Wang (2000), «Foundations of Technical Analysis», *Journal of Finance* | Detección algorítmica de patrones chartistas y su contenido informativo | buscar versión abierta (NBER) |
| Park e Irwin (2007), «What Do We Know About the Profitability of Technical Analysis?», *Journal of Economic Surveys* | Revisión de la evidencia | buscar versión abierta |
| Moskowitz, Ooi y Pedersen (2012), «Time Series Momentum», *Journal of Financial Economics* | Momento en futuros | buscar versión abierta |
| Hurst, Ooi y Pedersen (2017), «A Century of Evidence on Trend-Following Investing», *Journal of Portfolio Management* | Tendencia a muy largo plazo | abierto (AQR) |
| Liu y Tsyvinski (2021), «Risks and Returns of Cryptocurrency», *Review of Financial Studies* | Momento en cripto | buscar versión abierta (NBER) |
| Bailey y López de Prado (2014), «The Deflated Sharpe Ratio», *Journal of Portfolio Management* | Ya se usa en T41/T49 (`deflated`) | abierto (SSRN) |
