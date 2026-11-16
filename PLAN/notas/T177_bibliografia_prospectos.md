# T177 — 50 obras nuevas y 16 prospectos de reemplazo (2026-11-16)

Protocolo fijado antes de buscar: `PLAN/T177.md`. Modo **SIMULADO**, y **sin rendimiento**: ni la
búsqueda, ni la formulación, ni el examen calculan R neto, acierto o PF en la historia.

## 1. Cómo se buscó

- **Sin repetir.** Ninguna obra está entre las 115 de `seed.json` ni entre los 7 libros locales;
  `test_catalog_data` lo comprueba por DOI y por título.
- **Verificadas en su registro, no de memoria.** Las 165 obras pasan
  `python -m eim.library.digital verify` (OpenAlex/arXiv). De 73 candidatas quedaron 50:
  - 4 no verificaron con el DOI de partida. 1 se corrigió buscando por título (Savin et al.), 1 se
    cambió por otra obra del mismo tema (Kato 2014 en lugar de Madhavan 2002) y 2 quedaron fuera.
  - 18 quedaron fuera porque no tienen un resumen legible en ningún registro abierto (SSRN devuelve
    403). Entre ellas estaban Kim-Tse-Wald, Taylor, Lesmond-Schill-Zhou y Hsu-Hsu-Kuan.
  - 3 quedaron fuera por el reparto entre preguntas.
- **Leídas.** De las 50 se leyó el resumen:
  - 39 salen de OpenAlex. `research` comprueba sus posturas en el texto; las 39 quedan verificadas.
  - 10 salen de Semantic Scholar y 1 del repositorio de la Universidad de Florida Central (la de Leigh y otros). Estas se marcan así en su
    descripción, y su ficha queda en «metadatos», que es lo honesto: el registro no las trae.
- **Con la contraria.** 21 de las 50 obras objetan o condicionan la idea a la que acompañan; el
  mínimo era 1 de cada 4.
- **Efecto en el consenso de T157.** Con 50 obras más, algunos conceptos que estaban «a favor
  (+1,00)» con pocas fuentes pasan a «dividido». Los expedientes guardan el consenso nuevo
  (`consensus_at`).

## 2. Qué dice la bibliografía, por pregunta

| Pregunta | A favor | En contra o condiciona | Lo que cambia en la formulación |
|---|---|---|---|
| **Tendencia y medias** (10) | Lempérière et al. 2014: dos siglos de tendencia, t ≈ 5. Glabadanidis 2015. Levine y Pedersen 2016: los cruces de medias equivalen al momentum de series. Shen et al. 2022 y Caporale y Plastun 2020: momentum intradía en BTC | Huang et al. 2020: el momentum de series es débil activo por activo. Grobys y Sapkota 2019: sin momentum transversal en cripto. Kosc et al. 2019: a corto plazo domina la reversión en cripto. Lempérière: **las tendencias cortas se han debilitado** | Tendencia **lenta** (EMA 200 en 4 h, cruce 21/55). Inscribir también la contraria. La vara contra la deriva es el gemelo aleatorio |
| **Análisis técnico en cripto** (8) | Corbet et al. 2019: medias en BTC de alta frecuencia. Gerritsen et al. 2020: ruptura de rango en BTC. Chong y Ng 2008, y Wong et al. 2003: RSI | Grobys et al. 2020: la media de 20 días funciona **salvo en Bitcoin**. Resta et al. 2020: en intradía gana comprar y mantener. Lento 2007: Bollinger solo en lectura contraria. Neely et al. 2009: las ventajas desaparecen con el tiempo | RSI de giro sin el filtro que lo dejaba sin cadencia. Bollinger con una salida que no la lleve a scalping |
| **Sesión intradía y VWAP** (6) | Berkowitz et al. 1988: el VWAP como precio justo. Kato 2014: la ejecución al VWAP es óptima. Baltussen et al. 2021: momentum intradía en 60 futuros | Baur et al. 2019: las anomalías horarias de BTC no persisten. Eross et al. 2019 y Petukhina et al. 2021: el volumen y la volatilidad cambian por hora | Reversión al VWAP en 1 h, no en 15 m (en 15 m cuesta 0,337 R). Ningún prospecto de «hora del día» |
| **Soportes y números redondos** (5) | Donaldson y Kim 1993: barreras en múltiplos de 100. Bhattacharya et al. 2012: desequilibrios en números redondos. Mbanga 2019: BTC se agrupa en enteros. Chung y Bellotti 2021: más toques, más rebotes | Zapranis y Tsinaslanidis 2012: los niveles horizontales no dan rendimientos anormales | Zona que contiene un número redondo. Las zonas viejas pesan menos |
| **Estructura y oscilaciones** (5) | Brown et al. 1998: la teoría de Dow funcionó. Leigh et al. 2002: la bandera alcista | Elliott en NFT y cripto (2024): **no hay ondas de Elliott**. Chang y Osler 1999: el patrón pierde frente a una regla simple. Savin et al. 2007: predice, pero no paga solo | El agente `elliott` deja el conteo de ondas y usa solo sus pivotes, como oscilaciones de Dow |
| **Velas y reglas de libro** (4) | Lu et al. 2012: velas de dos días, manteniendo la posición | Duvinage et al. 2013: tras costos y SSPA, ninguna regla de velas intradía gana. Tharavanij 2017: depende del horizonte y del filtro | Las fichas, en 4 h y con tenencia de 48 h, donde el costo pesa menos |
| **Regímenes** (5) | Ang y Timmermann 2012: el régimen nuevo **persiste** varios periodos. Ardia et al. 2019 y Koki et al. 2022: regímenes reales en BTC. Kritzman et al. 2012 | — | Sostener la posición un tiempo fijo tras el cambio, en lugar de salir con cada parpadeo de la etiqueta |
| **Lecciones transversales** (7) | Novy-Marx y Velikov 2016, y Korajczyk y Sadka 2004: el costo manda en las reglas de rotación alta. Nagel 2012: revertir es dar liquidez. McLean y Pontiff 2016: tras publicarse, las ventajas caen un 58 %. Chordia et al. 2020: sin corregir, un 45 % de los hallazgos son falsos | — | Mirar el costo en R y la rotación. Esperar ventajas menores que las publicadas. Corregir por la familia |

La lista entera, con su postura, sus condiciones y su mercado, está en `v2/eim/library/digital/seed.json`;
lo bibliográfico verificado está en `catalog.json` y lo leído en `cards.json`.

## 3. Lo aprendido en T169 que manda

| Causa del descarte en T169 | Prospectos | Lo que hace el reemplazo |
|---|---|---|
| `atr_ladder` en 1 h cierra en 1,2–1,6 h y la regla cae en **scalping** (≥ 20 al mes) | `ema_retroceso`, `tec_compresion_bb`, `estructura_cambio` | La misma idea con `time_stop` (12 h): banda intradía (≥ 8) |
| El umbral nunca se alcanza | `estructura_ruptura` (convicción ≥ 60; el agente da 47–50) | SC-02 sin umbral. Son 35 pasos al mes |
| La variable no existe | `tec_acuerdo_marcos` (el marco 1 d no existe a 1 h, ni en vivo) | Los marcos que sí existen: 15 m, 1 h y 4 h |
| La etiqueta no varía | `elliott_onda3/5_giro` (el último pivote es siempre «C») | El tipo de pivote (H/L) sí varía: hay 27 al mes en 4 h |
| Costo > 0,3 R en 15 m | `vwap_reversion` (0,337 R) | La misma regla en 1 h |
| La etiqueta parpadea y casi nunca marca tendencia | `regimen_tramo` y `regimen_tramo_estable` (2 h en posición) | `regime` excluido; sus plazas van a `elliott` y `bots` (§5) |
| Cadencia intrínseca baja | `ema_pila`, `ema_resorte`, `niveles_canal_tendencia`, `lit_regla_4_semanas`, `vwap_anclado`, `tec_rsi_rango` | Ideas nuevas, estimadas antes con los cierres o con las variables del banco |

Además, en T169 **no quedó ningún superviviente en las bandas de tres días ni semanal**: los 16
quedaron en scalping (3) o intradía (13). Por eso 9 de los 16 reemplazos se formulan para la banda
de tres días.

**La banda semanal no se alcanza con las plantillas vigentes.**
- `time_stop` sale como mucho a las 24 velas del agente: 96 h en 4 h.
- `rule_flip` lleva un SL de 1,5 ATR.
- Ninguno de los 32 examinados en T169 pasó de 62 h de tenencia mediana, y la banda semanal pide más de 120 h.

Cambiar las plantillas es una decisión de familia, de T170 o de una versión 2.

## 4. Los 16 reemplazos

| Agente | Descartado | Reemplazo | Marco · salida · banda | Idea y obras |
|---|---|---|---|---|
| `ema` | `ema_pila` (base) | **`ema_precio_200`** (base) | 4 h · rule_flip · tres días | La regla 1/200: Brock et al. 1992, Glabadanidis 2015, Lempérière 2014. En contra: Huang et al. 2020. Unos 6 cruces al mes |
| `ema` | `ema_resorte` | `ema_cruce_21_55` | 1 h · rule_flip · tres días | Cruce de medias como filtro de tendencia: Levine y Pedersen 2016, Corbet et al. 2019. Unos 13 al mes |
| `ema` | `ema_retroceso` | `ema_retroceso_12h` | 1 h · time_stop · intradía | La misma regla con salida a 12 h. Bandera y pausa en tendencia: Leigh et al. 2002 |
| `technical` | `tec_acuerdo_marcos` (base) | **`tec_acuerdo_tres_marcos`** (base) | 1 h · rule_flip · intradía | Acuerdo de 15 m, 1 h y 4 h, los marcos que el agente sí evalúa |
| `technical` | `tec_rsi_rango` | `tec_rsi_giro` (opuesta) | 1 h · time_stop · intradía | El RSI sale de un extremo, sin filtro ADX: Chong y Ng 2008, Kosc et al. 2019, Nagel 2012 |
| `technical` | `tec_compresion_bb` | `tec_compresion_bb_12h` | 1 h · time_stop · intradía | La misma regla con salida a 12 h. La tendencia paga en la expansión: Fung y Hsieh 2001 |
| `vwap` | `vwap_reversion` (base) | **`vwap_reversion_1h`** (base) | 1 h · mean_target · intradía | La misma regla en 1 h, por el costo: Berkowitz et al. 1988, Kato 2014, Nagel 2012 |
| `vwap` | `vwap_anclado` | `vwap_quincenal` | 4 h · rule_flip · tres días | VWAP de 15 días con su pendiente: tendencia lenta (Lempérière 2014) |
| `elliott` | `elliott_onda3` (base) | **`elliott_oscilacion`** (base) | 4 h · rule_flip · tres días | Sigue la oscilación confirmada por el zigzag, sin ondas (Elliott en cripto: no). Unos 27 al mes |
| `elliott` | `elliott_onda5_giro` | `elliott_dow` | 4 h · rule_flip · tres días | Solo mínimos crecientes o máximos decrecientes: Brown et al. 1998 |
| `structure` | `estructura_ruptura` | `estructura_ruptura_sc02` | 1 h · time_stop · intradía | SC-02 sin el umbral no calibrado: Gerritsen et al. 2020, Donaldson y Kim 1993 |
| `structure` | `estructura_cambio` | `estructura_cambio_sc04` (opuesta) | 1 h · time_stop · intradía | SC-04 sin el umbral (unos 77 al mes): patrones de giro (Savin 2007, Chang y Osler 1999) |
| `levels` | `niveles_canal_tendencia` | `niveles_redondos` | 1 h · time_stop · tres días | Soporte o resistencia que contiene un múltiplo de 1 000 USD: Donaldson y Kim 1993, Bhattacharya 2012, Mbanga 2019 |
| `literature` | `lit_regla_4_semanas` | `lit_consenso_4h` | 4 h · time_stop · tres días | Consenso de fichas con tenencia de 48 h: Lu et al. 2012; en contra en intradía, Duvinage 2013 |
| `regime` → `elliott` | `regimen_tramo` (base) | `elliott_tendencia_dow` (opuesta de `elliott_oscilacion`) | 4 h · time_stop · tres días | Dow a favor de la tendencia, en el retroceso: tras un máximo más alto compra, y tras un mínimo más bajo vende. Brown et al. 1998, Leigh et al. 2002 |
| `regime` → `bots` | `regimen_tramo_estable` | `bots_contrario` (opuesta de `bots_unanimidad`) | 1 h · time_stop · intradía | Entra contra la unanimidad recién formada: DeLong et al. 1990, Bikhchandani et al. 1992, Kosc et al. 2019. Solo hacia adelante |

**Duplicados con T170 (resuelto el 2026-11-16).** En la sesión de T170 se habían rediseñado en su
sitio `estructura_ruptura` (sin filtro de convicción) y `tec_acuerdo_marcos` (marcos de 1 h y 4 h).
T177 formula esas mismas dos reglas con id nuevo: `estructura_ruptura_sc02` y
`tec_acuerdo_tres_marcos`, esta con 15 m, 1 h y 4 h. Si entraban las dos versiones, la familia
pasaba a 45. El usuario eligió en esa sesión las de T177. Por eso:
- T170 devuelve sus archivos al estado de T169.
- Las dos originales quedan como bajas de T169, con sus huellas (`1d4c4f294f59`, `61b1b609e29f`).
- La familia queda en 43, y T177 es la única fuente de reglas y expedientes de la cantera.

**Cuatro reemplazos repiten la regla de su descartado** con otra salida o en otro marco:
`ema_retroceso_12h`, `tec_compresion_bb_12h`, `vwap_reversion_1h` y `lit_consenso_4h`. La lección
de T169 era física, no de rendimiento. Cada uno es un prospecto nuevo, con su huella propia, y suma
un intento a la familia.

**Lo demás:**
- **Supervivientes intactos.** Las huellas de los 16 supervivientes no cambian (comprobado contra
  el plan de T169).
- **Descartados a la vista.** Los descartados no se borran: pasan a `discarded` en su expediente,
  con su huella, su motivo y el id de su reemplazo.
- **Opuestas reapuntadas.**
  - `ema_elastico` y `vwap_tendencia` apuntan ahora a las bases nuevas.
  - `lit_murphy_rsi` se queda sin opuesta: su opuesta era la regla de 4 semanas, y ninguna ficha de tendencia cabe en 1 h ni opera bastante en 4 h.

## 5. `regime` queda excluido

La sonda `t177-sonda-regimen` corrió por la cola, sin rendimiento, sobre la copia del banco. Contó
cuántas veces la etiqueta pasa a `trend_up` o `trend_down`:

| Marco | Muestra | Pasos a tendencia al mes | Tramo mediano |
|---|---|--:|--:|
| 15 m | 28 días (2 700 contextos) | 5,3 | 2 velas |
| 1 h | 447 días (muestra de T169) | 4,6 | — |
| 4 h | 250 días (1 500 contextos) | 1,1 | 3 velas |

El agente ve «rango» o «volátil» casi siempre. Ninguna regla direccional sobre su etiqueta llega a la cadencia
mínima de su banda: 20 al mes en scalping, 8 en intradía y 5 en tres días. Sostener la posición
más tiempo no ayuda, porque la cadencia la ponen las entradas.

`regime` pasa a «excluido», con este motivo en su expediente. Sus dos plazas se repartieron así:
- **Plaza base → `elliott`.** Es el agente con más respaldo bibliográfico entre los que tienen
  hueco: masa a favor 8,26 en el consenso de T157, frente a 2,36 o menos en `bots`,
  `microstructure` y `liquidations`. Es además el único de ellos que se puede examinar en la
  historia. Su segunda idea posible, el conteo válido, cambia solo 1,4 veces al mes en 4 h y no
  sostiene un prospecto.
- **Segunda plaza → `bots_contrario`** (decisión del usuario, 2026-11-16). Es la teoría opuesta que
  le faltaba a `bots`.

## 5 bis. Examen previo (orientativo)

Antes de la generación larga, 9 reemplazos cuyas variables ya estaban en el `nat` de T169 se
midieron con la misma física y el mismo veredicto (`t177-examen-previo`, por la cola). Los 9 pasan:

| Prospecto | Operaciones al mes | Tenencia mediana | Costo medio | Banda medida |
|---|--:|--:|--:|---|
| `vwap_reversion_1h` | 67,4 | 2,0 h | 0,105 R | scalping |
| `estructura_cambio_sc04` | 36,2 | 12,0 h | 0,163 R | intradía |
| `tec_rsi_giro` | 33,2 | 12,0 h | 0,153 R | intradía |
| `niveles_redondos` | 17,5 | 11,4 h | 0,139 R | intradía |
| `estructura_ruptura_sc02` | 17,5 | 10,5 h | 0,167 R | intradía |
| `elliott_oscilacion` | 14,9 | 8,0 h | 0,070 R | intradía |
| `tec_compresion_bb_12h` | 13,8 | 8,6 h | 0,187 R | intradía |
| `lit_consenso_4h` | 9,8 | 48,0 h | 0,081 R | tres días |
| `ema_retroceso_12h` | 9,5 | 11,8 h | 0,175 R | intradía |

`niveles_redondos` declaraba tres días y pasa a declarar intradía, que es lo que dan su plantilla y
su marco (lección 1). Su regla y su huella no cambian.

## 6. Examen

Pendiente: `v2/reports/t177_examen_fisico.md`.
