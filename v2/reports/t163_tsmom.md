# T163 — Cartera de tendencia lenta (TSMOM) con volatilidad objetivo: **SIN POTENCIA**

**Veredicto: la historia de BTCUSDT perpetuo no alcanza para probar esta hipótesis.** Detectar la
ventaja mínima que se propuso probar exige **12,62 años** de historia diaria y hay **5,85** en el
tramo de evaluación (6,83 si se usa toda la vida del instrumento). La tarea se cierra con ese
veredicto: **no se escribió el pre-registro, no se midió ningún Sharpe del tramo de evaluación y
no se gastó el intento de la familia de Holm** (sigue en 841).

Fecha: 2026-11-11 · Modo: **SIMULADO (solo análisis)** · Símbolo: **BTCUSDT**, solo BTC.
Puerta y especificación: [`PLAN/notas/T163_potencia.md`](../../PLAN/notas/T163_potencia.md),
commit `483915b`, **anterior a cualquier cifra**. Cifras: `reports/t163_tsmom.json`, reproducible
con

```
python scripts/t163_tsmom.py --data C:/Users/jo/Desktop/JP/TRADINGBOT/v2/backups/t139_banco
```

(4 s, un proceso, lee solo la copia estática del banco).

## 1. Qué se preguntaba y qué se declaró antes de mirar

La hipótesis es la forma de la literatura que T139 **no** probó: no entradas con stop, sino una
**cartera siempre posicionada** en el perpetuo de BTC, con la señal de tendencia promediada en
lookbacks de 20, 60 y 120 días, **dimensionada por volatilidad objetivo** (30 % anual, tope 3×) y
rebalanceada los lunes a las 00:00 UTC, con los costos de T25 (taker 5 pb, deslizamiento de
`perp.slippage_frac` sobre la vela de 1 h de ejecución y funding cada 8 h del banco).

El usuario abrió la ◆ el 2026-11-11 con una condición: **primero el MinTRL**. Antes de tocar nada
se declaró en un commit propio:

| Qué | Valor declarado |
|---|---|
| Métrica principal | Sharpe neto anualizado de los retornos diarios de la cartera |
| Ventaja mínima a detectar `S_min` | **0,70** |
| Nivel y potencia | α = 0,05 unilateral, potencia 0,80 |
| Tramo de potencia (solo dispersión y dependencia) | 2020-01-06 → 2020-12-31 |
| Tramo de evaluación (el único que decide) | 2021-01-01 → último día completo |
| Subtramo informado por separado | 2024-01-01 → final |
| Puerta | abrir solo si `n_eval ≥ κ · n_apriori(S_min)` |

**De dónde sale `S_min` = 0,70.** El único Sharpe fuera de muestra publicado para esta forma de
estrategia es 1,41 neto de 25 pb en *majors* ([SSRN 7115459][a]), cuyos autores admiten sesgo de
supervivencia y no superar un umbral de pruebas múltiples; el recorte habitual por sesgo de
publicación es de la mitad (Harvey y Liu, *Backtesting*, JPM 2015) → 0,70. Además las cifras
publicadas son de **carteras multiactivo** (1,41 en *majors*; 2,41 sobre más de 150 pares,
[arXiv 2602.11708][b]) y esta es **una sola pata**, sin diversificación transversal, así que 0,70
es ya generoso. Un tercer trabajo sostiene que la ventaja **ha envejecido** y que el bruto depende
de un único dato atípico ([SSRN 7405060][c]).

## 2. Datos (fuente y cobertura reales)

Banco estático `v2/backups/t139_banco`, BTCUSDT `binance-futures`
(`backups/t139_banco/cobertura.md`): velas de 1 min del 2019-09-08T17:57Z al 2026-11-06T03:36Z,
3 766 179 filas, **cobertura 99,70 %**, 1 vela que el proveedor no devolvió; 62 770 velas de 1 h;
**7 842 puntos de funding** desde 2019-09-10. No se leyó nada del almacén vivo (el colector HFT lo
está compactando).

Con la regla de ≥ 90 % de las 1 440 velas de 1 min por día UTC (la de T162 y T166): **2 615 días
válidos**, del 2019-09-09 al 2026-11-05. El calentamiento (120 días de lookback + 60 de σ) consume
los primeros 120, así que hay señal desde el 2020-01-07 y posición desde el **2020-01-08**: en
total **2 494 días con cartera**, que es **toda la vida del instrumento**. No existe más historia
de BTCUSDT perpetuo, y el contado anterior a 2019 no tiene funding ni libro del perpetuo, así que
no se sustituye.

## 3. La cuenta de la puerta

Del tramo de potencia (2020-01-08 → 2020-12-31, **358 retornos diarios**) se leyeron, como estaba
declarado, **solo** dispersión, forma y dependencia serie — ni la media ni el Sharpe:

| Magnitud | Valor |
|---|--:|
| σ diaria | 0,01724 |
| σ anualizada realizada (objetivo 30 %) | **32,94 %** |
| Asimetría | +4,619 |
| Curtosis (no en exceso) | 54,00 |
| Bloque medio de Politis-White | 4,019 días |
| κ de Newey-West (suelo 1) | **1,00** (sin suelo: 0,8397) |
| Autocorrelaciones (retardos 1–4) | −0,149 · +0,059 · −0,029 · +0,078 |

Y con ellas, la aritmética de `validation/power.py` (`n = ((z_0,05 + z_0,20)/S_d)²` con
`S_d = S_min/√365`, por κ):

| Pregunta | Resultado |
|---|--:|
| Días para detectar `S_min` = 0,70 con potencia 0,80 | **4 605 (12,62 años)** |
| Días disponibles en el tramo de evaluación | **2 135 (5,85 años)** |
| Días disponibles usando **toda** la vida del instrumento | 2 494 (6,83 años) |
| Días del subtramo 2024–2026 | 1 040 (2,85 años) |
| Sharpe mínimo detectable — evaluación | **1,028** |
| Sharpe mínimo detectable — toda la historia | 0,951 |
| Sharpe mínimo detectable — subtramo 2024–2026 | **1,473** |
| Potencia real para 0,70 — evaluación / toda / subtramo | **51,9 % / 57,3 % / 32,2 %** |
| MinTRL (significación sin potencia) para 0,70 | 1 711 días (4,69 años) |

> **La puerta falla por un factor 2,2.** Y no por el tramo elegido: incluso evaluando toda la vida
> del instrumento harían falta 12,62 años frente a 6,83, y el subtramo 2024–2026 —el que la nota de
> T161 escribió en la hipótesis— no puede detectar **ni el 1,41 publicado**, porque su mínimo
> detectable es 1,473.

**Significación no es potencia, y aquí la diferencia lo es todo.** El MinTRL (1 711 días) sí cabe
en los 2 135 del tramo de evaluación: con esa muestra, un Sharpe **observado** por encima de 0,680
sería significativo al 5 %. Pero si la ventaja verdadera fuera exactamente 0,70, la probabilidad de
observarlo por encima de ese umbral es **51,9 %**. Una prueba que acierta la mitad de las veces es
una moneda al aire, y es exactamente lo que T161 dejó prohibido y lo que T166 acató esta misma
jornada. Con el subtramo 2024–2026 la moneda está cargada en contra: 32,2 %.

**κ no es la causa del cierre.** La dependencia serie de los retornos diarios de la cartera no
castiga: el factor de Newey-West sin suelo es 0,8397 (la autocorrelación de retardo 1 es −0,149,
los días se compensan), y aun así se aplicó κ = 1 para no premiar a la hipótesis. Si se hubiera
usado 0,84, harían falta 3 867 días: **también más que los disponibles**.

## 4. Cuántos años pide cada Sharpe (aritmética a priori, publicada entera)

Para que se vea qué habría pasado con otro `S_min`, y que el veredicto no depende de haber elegido
el número cómodo:

| Sharpe neto anualizado | Años de historia diaria necesarios (potencia 0,80) | ¿Caben en 5,85? |
|---|--:|---|
| 0,50 | 24,73 | no |
| **0,70** (el declarado) | **12,62** | **no** |
| 1,00 | 6,18 | no (faltan 4 meses) |
| 1,41 (el publicado, sin recorte) | 3,11 | sí |
| 2,00 | 1,55 | sí |
| 2,41 (el otro publicado) | 1,06 | sí |

Dicho sin rodeos: **esta hipótesis solo es comprobable en BTC si se da por bueno el Sharpe
publicado tal cual**, sin recorte por sesgo de publicación, sin descontar que es multiactivo y sin
atender al trabajo que dice que ha envejecido. Eso sería diseñar la prueba para que solo pueda ver
el mejor caso posible.

## 5. Lo que sí se aprendió, y el matiz de T136

- **La volatilidad objetivo controla la dispersión, y en una cartera continua sí hace su trabajo.**
  T136 encontró que dimensionar por volatilidad objetivo salía **peor** en esperanza, dispersión y
  cola, pero allí las ideas tenían stops que **no estaban en unidades de σ**: al escalar la
  cantidad por 1/σ, la distancia al stop quedaba descolocada y el riesgo por operación dejaba de
  ser el declarado. Aquí **no hay stops**: la σ realizada del tramo de potencia fue **32,9 %**
  frente al 30 % pedido, con un rezago de 60 días en la estimación y un tope de 3×. La objeción de
  T136 no aplica a esta forma, y conviene que quede dicho para cualquier trabajo futuro.
- **La cola no desaparece, se concentra.** Con la dispersión bajo control, la distribución diaria
  del tramo de potencia tiene asimetría **+4,6** y curtosis **54**: 2020 incluye el desplome del
  12 de marzo, y una cartera de tendencia con el signo correcto convierte ese día en un dato
  atípico enorme. Es precisamente la fragilidad que señala [SSRN 7405060][c] («el bruto depende de
  un único dato atípico»), y es también la razón estadística del cierre: una serie con esa cola
  necesita más historia, no menos, para distinguir ventaja de suerte.
- **Lo que no se sabe.** No se sabe si esta cartera gana o pierde: no se calculó. Cerrar por
  potencia **no** es un resultado negativo sobre la estrategia; es un resultado sobre la prueba.

## 6. Límites de este informe

- No hay Sharpe, ni drawdown, ni rotación, ni costo anual medidos: la condición de aceptación de la
  ficha pedía esas cifras **con el veredicto de la regla pre-registrada**, y la regla se aplicó
  antes, en el paso 1, con el resultado de no medir. El código para medirlas queda escrito y
  probado (`eim/backtest/tsmom.py`), listo si algún día hay historia o un objetivo con más señal.
- La σ, la asimetría y la curtosis vienen de **un solo año** (2020, 358 retornos) y 2020 fue un año
  atípico. Una cola menos gruesa reduciría algo el MinTRL, pero el `n` a priori de la puerta
  **no depende de la forma** —solo de `S_min` y de κ—, así que el veredicto no cambiaría.
- La puerta es sobre la ventaja **absoluta** frente a no operar. Comparar contra comprar y mantener
  (la pregunta «¿aporta la tendencia algo sobre estar largo?») tiene todavía **menos** potencia,
  porque la diferencia emparejada de dos series con esta volatilidad es más ruidosa.
- Todo es simulado y de solo análisis: nada toca riesgo, ejecución, los perfiles del bróker
  simulado ni la corrida de papel T31.

[a]: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7115459
[b]: https://arxiv.org/abs/2602.11708
[c]: https://papers.ssrn.com/sol3/Delivery.cfm/7405060.pdf?abstractid=7405060&mirid=1
