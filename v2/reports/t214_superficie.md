# T214 — Superficie de volatilidad implícita de BTC: potencia, pre-registro y agente informante

**Modo: ANÁLISIS.** Nada de esto toca el cono, las bandas, el tamaño de los stops, la síntesis, el
plan, el riesgo ni el bróker. Fuente: cadenas de Deribit de T213 (nivel 1, **solo uso personal**:
este informe no se publica ni se comparte fuera del proyecto).

- **Pre-registro:** `PLAN/notas/T214_preregistro.md`, SHA-256 (contenido con fin de línea LF)
  `a3d88d800f2cca3467ceede1bc7eb756436e09fe48b30795fd2e580bbc15fb1f`, en un commit propio
  **anterior** al del código y a cualquier resultado. Lo único mirado antes: que los rasgos se
  calculan sobre la primera toma (una sola toma: ninguna pérdida, ningún pronóstico).
- **Estado vivo de la muestra:** `python scripts/t214_superficie.py --data data --out
  reports/t214_superficie.json` (cuenta tomas, días válidos y proyecta la revisión de potencia).

## Respuesta para la ◆ (lo que hay hoy)

**Con la regla que fija la tarea, la superficie no se puede evaluar en un plazo útil.** El
contraste es hacia adelante (no hay histórico de cadenas con dos lados verificado, T213 §1.5) y
la corrección de Holm sobre la **familia ampliada** de T95 (1 141 hipótesis con estos 3 intentos)
exige p < 0,05/1 141 al mejor intento. Con la s que publicó T165 para modelos anidados del mismo
tipo (0,12–0,27) y una mejora mínima del 5 % sobre A2, hacen falta entre **1 615 y 7 808 días
puntuados**, más 250 de calentamiento: la primera evaluación caería entre **2032 y 2048**. El
pre-registro pone un tope en **2029-11-27**; para caber haría falta s ≤ 0,090, por debajo de
toda s publicada.

**Lo que decide de verdad** es la **revisión de potencia** que fija el pre-registro: cuando haya
250 días válidos (no antes del **2027-08-05**) se mide **solo la dispersión** de las diferencias
de pérdida (nunca su media) y se fija la fecha de evaluación o se cierra SIN POTENCIA sin gastar
los 3 intentos. Hasta entonces el agente `vol_surface` corre **en sombra, como informante**.

**Recomendación:** que el agente quede **como contexto** en la interfaz y que solo pase a ser
insumo de volatilidad si la evaluación pre-registrada lo aprueba (como T165 con A2, tras su ◆).
Con lo que se sabe hoy, lo más probable es que la revisión de potencia cierre la pregunta sin
potencia: la superficie se ve, pero no se puede demostrar que mejore a A2.

## Qué se construyó

| Pieza | Dónde | Qué hace |
|---|---|---|
| Rasgos | `eim/options/surface.py` (1.0.0, puro) | σ ATM 7 y 30 d (varianza total entre vencimientos, sin extrapolar), pendiente ln(σ7²/σ30²), sesgo 25Δ y 90/110 a 30 d, prima por plazo y calidad propia de la toma |
| Realizada | `eim/options/realized.py` | σ cierre a cierre de las velas del snapshot (solo para la prima que muestra el agente) |
| Potencia | `eim/options/surface_power.py` | la aritmética de esta página (método de T163) |
| Lectura | `eim/data/options_read.py` | última toma con `taken_ms ≤ asof` (≤ 26 h) para el snapshot, sin mirar el futuro ni rellenar |
| Agente | `eim/agents/vol_surface` (0.1.0) | informante: sesgo 0 siempre, no direccional en la síntesis, nunca `degraded`, fuente y antigüedad a la vista |
| Estado | `scripts/t214_superficie.py` | tomas, días válidos y fecha estimada de la revisión de potencia |

El escáner **no** considera a `vol_surface` (`scanner/jobs.OUT_OF_SCANNER`): ningún perpetuo del
universo tiene cadena de opciones y, si contara, cambiaría las huellas de agentes y capacidades,
dejaría desactualizado el umbral del placebo de T95 y abriría intentos nuevos de la síntesis.

## La primera toma (descriptiva, no es un resultado)

Toma de BTC del **2026-11-27 16:37 UTC** (956 opciones, 13 vencimientos), rasgos de
`surface.py` 1.0.0:

| Rasgo | Valor | Lectura |
|---|--:|---|
| σ ATM 7 días | 48,5 % | |
| σ ATM 30 días | 47,4 % | |
| Pendiente ln(σ7²/σ30²) | +0,045 | estructura algo invertida (el vencimiento del 11-dic paga 51,5 %) |
| Sesgo 25Δ a 30 días | +7,6 puntos | las puts cuestan más que las calls |
| Sesgo 90/110 a 30 días | +8,7 puntos | idem en moneyness |
| Calidad | **ok** | 4 vencimientos usados (6,6 · 13,6 · 27,6 · 62,6 días); marca y medio a ≤ 0,14 puntos en el dinero |

El estado por vencimiento que guarda T213 marca `degradado` 12 de los 13 vencimientos de esa
misma toma por una sola mariposa negativa de un tick en las alas. Por eso el pre-registro define
una calidad propia **en el dinero**, donde se miden los rasgos, y no usa ese estado como filtro.

## Potencia a priori

Días puntuados para detectar la mejora con potencia 0,80 (α = 0,05, Holm), más 250 de
calentamiento desde el 2026-11-28. **Vinculante: familia ampliada (1 141).** La familia propia de
3 (la de T165) se muestra solo como sensibilidad: la tarea fija la ampliada.

| s (de T165) | Mejora | Familia 1 141: días | Primera evaluación | Familia 3: días | Primera evaluación |
|---|--:|--:|---|--:|---|
| 0,2731 (A1 vs M1) | 5 % | 7 808 | 2048-12-20 | 3 034 | 2035-11-25 |
| 0,2405 (A2 vs M1) | 5 % | **6 055** | **2044-03-03** | 2 353 | 2034-01-13 |
| 0,1242 (A3 vs M1) | 5 % | 1 615 | 2032-01-06 | 628 | 2029-04-24 |
| 0,2405 | 10 % | 1 514 | 2031-09-27 | 589 | 2029-03-16 |
| 0,1242 | 10 % | 404 | 2028-09-12 | 157 | 2028-01-09 |

La mejora mínima declarada es el **5 %** de la QLIKE de A2 en T165 (δ = 0,0147). A2 mejoró a M1
un 6,7 %: pedir a la superficie que añada otro 5 % sobre A2 ya es generoso; con un 3 % todas las
filas pasan de 2039. Tabla completa (3 s × 2 familias × 3 mejoras) en el JSON.

## Límites

1. **Solo hacia adelante y solo en la portátil.** Las tomas no se pueden volver a descargar; si
   el colector se para, esos días faltan y retrasan la revisión. La copia diaria las guarda.
2. **La regla de Holm sobre la familia ampliada es lo que hace inalcanzable la potencia.** Con la
   familia propia (precedente de T165) la fecha seguiría siendo 2029 o más. Cambiar de familia
   sería otra decisión, y tendría que tomarse **antes** de la revisión de potencia.
3. **La s a priori es prestada** (T165, sobre DVOL); la verdadera se mide en la revisión, solo
   su dispersión.
4. **El objetivo diario** (QLIKE del σ a 1 día) lo fija la tarea; un objetivo intradía daría más
   observaciones, pero muy dependientes entre sí y no es lo que se pidió.
5. **Términos de Deribit**: si Deribit contesta que no a la confirmación escrita (◆ de T213), se
   retira el colector y T214 se cierra con lo que haya.
6. **La prima que muestra el agente** es cierre a cierre con las velas del snapshot; la del
   pre-registro usa la RV5 diaria. Son el mismo concepto con otra medida: la del agente no decide.

## Qué sigue

- **◆ del usuario:** ¿el agente queda como contexto (recomendado) o, si la evaluación algún día
  pasa, entra como insumo de volatilidad al estilo de T165?
- Antes del **2027-08-05**: escribir y probar el código de la revisión de potencia (A2 y C1–C3
  recursivos, solo s y κ) y dejarla programada (BACKLOG T214).
- Reiniciar la API de la portátil para que la esfera `vol_surface` aparezca con su lectura (en
  `juanpablo-cpu` saldrá «sin datos»: allí no hay tomas).

## Reproducir

```
python scripts/t214_superficie.py --data data --out reports/t214_superficie.json
python -m pytest -q tests/options tests/agents/vol_surface tests/data/test_options_read.py
```
