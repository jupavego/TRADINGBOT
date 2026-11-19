# Pre-registro `direccion_v1` — el acierto de la entrada (T190–T193)

**Congelado el 2026-11-18, antes de calcular ningún acierto por informante con los reportes en vivo.**
Lo único conocido de antemano: la síntesis direccional acierta el 46,1 % en el banco de T131
(`reports/t150_calibracion.md`) y el acierto de la sombra del bróker ronda el 46–49 %.
Las reglas viven en código en `v2/eim/direction/params.py` (`DirectionParams`, `PREREG_ID`).
Cambiar cualquier número de esta nota es una versión nueva (`direccion_v2`) con su propia nota; nunca
un ajuste mirando resultados.

## Relación con T139 (P1) y T145 (D)
La clase «predecir la dirección con indicadores sobre velas» está **medida y cerrada**: T27, T137,
T139 (veredicto P1, vinculante) y la calibración (46,5 %) lo dicen, y T145 eligió D (solo
análisis). Esta línea **no reabre la búsqueda de entradas** ni gasta la lectura limpia de T139:
- No prueba hipótesis nuevas ni reglas nuevas en la historia. Mide, hacia adelante y sin parar,
  lo que los informantes que **ya existen** dijeron en vivo; es control y retroalimentación (D:
  medir honestamente y decirlo).
- Familia propia `direccion_v1` (≈ 60 informante × marco + 6 sombra × marco), separada de las 841
  de la búsqueda cerrada porque usa datos nuevos, emitidos en vivo después de T139. Se declara aquí
  para que nadie la sume a escondidas.
- La hipótesis nula, fijada antes de medir, es la de P1: **ningún informante tiene ventaja y las
  sombras no superan a la síntesis v1**. Pasar la puerta en sombra solo abre una ◆ del usuario para
  reabrir P1 con una variante emparejada; nunca cambia nada por sí sola.

## Pregunta
¿Algún informante del cerebro, o alguna forma de combinarlos, acierta la **dirección** del precio
mejor que una moneda y mejor que la síntesis v1 que hoy decide las entradas?

## Qué se mide (T190, boleta de dirección)
- **Universo.** Los `AgentReport` que el sistema ya guardó en vivo (`reports.duckdb`), del foco
  (`FOCUS`, hoy BTCUSDT) en 15m, 1h y 4h. No se reconstruye historia ni se recalcula ningún agente:
  se califica lo que cada agente dijo en su momento.
- **Informantes.** Todos los agentes salvo los que no opinan de dirección por su papel: `calendar`,
  `arbitrage`, `plan` (deriva de structure/levels) y `regime` (modula pesos). Los de peso 0 en la
  síntesis (`technical`, `literature`, `bots`, `intermarket`, `smart_money`…) **sí** se califican:
  la pregunta es si saben algo, no si hoy votan. La síntesis v1 se califica como `sintesis_v1`,
  recalculada con la función pura `synthesize` sobre los reportes guardados de cada instante.
- **Voto.** Estado distinto de `no_data`, confianza > 0 y |sesgo| ≥ **0,05**. Signo = signo del sesgo.
- **Resultado.** Signo del log-retorno entre el cierre de la última vela cerrada en `asof` y el
  cierre `h` velas después. Horizontes **1, 4 y 12 velas**; el **principal es 4**. Un retorno exactamente
  0 no cuenta. Lo que aún no ocurrió queda pendiente.
- **Régimen** (descriptivo y para la sombra, nunca para el veredicto): volatilidad realizada de las
  últimas **24** velas frente a su propia distribución en las **500** anteriores, en terciles `baja`,
  `media`, `alta`. Solo usa velas ya cerradas.
- **Muestra sin solape.** Por informante, se cuenta un voto solo si dista ≥ `h` velas del anterior
  contado. El IC (Wilson 95 %) y las pruebas usan solo esa muestra.

## Veredicto por informante (horizonte principal, todos los regímenes)
- `sin_veredicto`: menos de **100** votos sin solape.
- `ventaja`: ≥ **250** votos sin solape **y** binomial de una cola (acierto > 50 %) con **Holm** sobre
  la familia de todos los informantes × marcos, p ajustado < **0,05**.
- `contraria`: ≥ 250 sin solape y el IC 95 % entero por debajo del 50 %. Se informa; usar una señal al
  revés exige su propio pre-registro.
- `sin_ventaja`: el resto.

## Control (T191, vigía de dirección)
Cada **6 h** por marco: `alerta` si la síntesis v1 tiene ≥ 100 votos sin solape y su IC 95 % entero
está por debajo del 50 %; dos alertas seguidas = `alerta_sostenida` (pinta el mapa en ámbar).
`vigilar` si ningún informante del marco tiene `ventaja`. `ok` si alguno la tiene y la síntesis no
está en alerta. Historial solo de añadir en `data/direction/watch.jsonl`.

## Sombras (T192 abstención, T193 síntesis ponderada por acierto)
Walk-forward estricto: en cada instante solo se usan resultados ya resueltos (el horizonte principal
cerrado antes de ese instante). Nada de esto toca el bróker, la síntesis ni T31.
- **Estadística viva por (informante, régimen)**: aciertos y votos sin solape ya resueltos.
- **T192 · Abstención.** Un informante califica en un régimen con ≥ **100** votos resueltos sin solape
  y límite inferior de Wilson 95 % > 50 %. La sombra entra solo si **≥ 2** calificados coinciden en
  el signo y ninguno calificado se opone; si no, **no opera**.
- **T193 · Pesos por acierto medido.** Acierto encogido hacia la moneda,
  `(aciertos + 50) / (votos + 100)` (fuerza del previo **100**), peso = máx(0, 2·acierto − 1). Sin
  pesos negativos. Dirección = signo de Σ peso · signo del sesgo; si todos los pesos son 0, no opera.
- **Comparación.** Contra la síntesis v1 en los mismos instantes (ambas con dirección y resultado
  resuelto), muestra sin solape cada `h` velas. McNemar exacto de una cola sobre los pares
  discordantes; **Holm** sobre la familia {T192, T193} × marcos (6).
- **Puerta en sombra.** Pasa ⇔ ≥ **250** pares, p ajustado < 0,05, mejora ≥ **+3 pp** y límite
  inferior de Wilson del acierto de la sombra > 50 %. **Sostenida** = dos revisiones seguidas.
  También se publica la cobertura (qué fracción de instantes opera) y el acierto de la síntesis en
  los instantes en que la sombra se abstuvo (lo que la abstención habría evitado).

## Lecturas y decisión
- Nada se adopta antes del cierre de T31 (2026-11-27). Primera lectura formal: **2026-11-28**;
  después **2026-12-26** y **2027-01-23**. Cierre de la línea: **2027-02-20** si nada pasó.
- Pasar la puerta en sombra **no** cambia nada solo: abre una ◆ del usuario para llevar la regla al
  bróker como variante emparejada (T175), con la contabilidad de T144. La regla del usuario sigue:
  entradas y pesos de la síntesis no se adaptan solos (`AUTO_ADAPT` es solo costo y riesgo).
- Se publica todo, también si es desfavorable. Lo más probable, por T44, T139, T145 y T150, es que
  ningún informante pase: eso también es un resultado útil (dice dónde no buscar).
