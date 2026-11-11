# T161 — Potencia a priori y contraste SPA sobre la familia de T139

**Modo: SIMULADO.** Otra pregunta sobre los mismos números de T139: no gasta ninguna lectura, no añade intentos a Holm (familia 841) y no cambia ningún veredicto.

Datos: `backups/t139_banco` · comando: `python scripts/t161_potencia_spa.py --data backups/t139_banco` · cifras en `reports/t161_potencia_spa.json` · bootstrap estacionario, 5 000 repeticiones, semilla 161.

## En una línea

**T145 se sostiene con SPA.** Ninguna de las 9 claves de T139 supera a no operar una vez se tiene en cuenta que se eligió la mejor: p de SPA de la familia **0,459** en la lectura oficial (2020–2022) y **0,886** en el banco (2023–2026). En el MCS, «no operar» sobrevive en las dos lecturas.

## Reproducción antes de calcular

La simulación se rehízo con el mismo código y los mismos datos, y **coincide con lo publicado en `reports/t139_entradas.json` en las 9 claves** (mismo n y misma media neta, diferencia < 1e-9). Solo después se calculó nada nuevo.

## SPA y MCS

Las claves operan en momentos distintos, así que se alinean por día UTC: R sumado de las operaciones decididas ese día y 0 los días sin operación (no operar es la base). El bloque medio de Politis-White sale ≈ 1 día: la serie diaria no tiene memoria apreciable.

| Lectura | Días | SPA neto (consistente) | Cotas inferior–superior | SPA bruto | Mejor clave (media diaria neta) |
|---|---|---|---|---|---|
| Oficial 2020–2022 | 1 181 | **0,459** | 0,134–0,489 | 0,212 | `flujo_sigue@4h` (+0,023 R/día) |
| Banco 2023–2026 | 1 405 | **0,886** | 0,787–0,994 | 0,649 | `flujo_sigue@4h` (+0,003 R/día) |

- **Ni siquiera el bruto** supera a cero en la familia (p 0,21 y 0,65): no es solo que el costo se coma la ventaja, es que no hay una ventaja bruta distinguible del azar de selección.
- **MCS al 10 %**, oficial: quedan dentro 8 de 9 claves y «no operar» (p 0,349); solo sale `flujo_revierte@1h`. Banco: dentro `flujo_sigue@4h`, `cascada_revierte@4h`, `funding_contra@4h`, `momento_1d@1d` y «no operar» (p 0,985). **Ninguna regla es distinguible de quedarse fuera.**

## El caso de `flujo_sigue@4h`

Es la que T139 dejó «más cercana»: +0,182 R netos con n = 152 en la lectura oficial. Mirada sola, su MinTRL frente a 0 es **110 operaciones**, menos de las 152 que tiene: parecería significativa. Es exactamente el sesgo que el SPA corrige: elegida entre 9, su p de familia es 0,459. Y en el banco cae a +0,018 R con un MinTRL de **11 749** operaciones. La lectura de T139 («con una familia de 9 sí seguiría») queda matizada: con una familia de 9 y la corrección de selección de SPA, tampoco.

## Potencia a priori: cuánta historia haría falta

Con la dispersión observada (σ ≈ 1,10–1,18 R por operación), **detectar una ventaja neta real de +0,10 R** con α = 5 % unilateral y potencia del 80 % exige **≈ 750–850 operaciones** por clave. Al ritmo de disparo de cada clave en la historia, eso son:

| Clave | n oficial | Neto medio | MinTRL frente a 0 | Operaciones para +0,10 R | Días a su ritmo |
|---|---|---|---|---|---|
| `flujo_sigue@1h` | 635 | −0,080 | — | 844 | 1 569 |
| `funding_contra@1h` | 454 | −0,040 | — | 816 | 2 121 |
| `cascada_revierte@1h` | 451 | −0,103 | — | 829 | 2 170 |
| `cascada_revierte@4h` | 266 | −0,010 | — | 756 | 3 353 |
| `funding_contra@4h` | 232 | −0,034 | — | 759 | 3 860 |
| `flujo_revierte@1h` | 205 | −0,273 | — | 809 | 4 656 |
| `flujo_sigue@4h` | 152 | +0,182 | 110 | 845 | 6 560 |
| `momento_1d@1d` | 121 | +0,048 | 1 470 | 799 | 7 793 |
| `flujo_revierte@4h` | 60 | −0,221 | — | 850 | 16 724 |

«—» = la media no supera 0, el MinTRL es infinito. Frente al **costo** (bruto contra costo medio por operación), solo `flujo_sigue@4h` (101) y `momento_1d@1d` (1 416) tienen un MinTRL finito en la lectura oficial; en el banco, solo `flujo_sigue@4h` (10 870).

**Lectura:** al ritmo de estas claves, un veredicto con potencia para +0,10 R tarda **de 4 a 46 años**. Ninguna cabe en la regla de 6 meses de T145. Si esta tabla hubiera existido antes de T139, las 9 se habrían podido declarar inviables sin gastar intentos.

## Lo que implica para T31

El libro oficial de T31 (cuatro perfiles, sin `retro`, T144) cerró 43, 30, 118 y 33 operaciones con peso en W43–W46: del orden de **60 por semana**. Con σ ≈ 1,15 R:

- En las **4 semanas** previstas (≈ 250 operaciones) solo se puede detectar una ventaja de **≥ 0,18 R** por operación con potencia del 80 %.
- Detectar +0,10 R exige ≈ 820 operaciones: **≈ 14 semanas**.
- Las operaciones de los cuatro perfiles salen de las mismas ideas y están correlacionadas, así que la muestra efectiva es menor y estas cifras son una **cota optimista**.

Es decir: T31 puede confirmar que **no hay** una ventaja grande, pero no puede validar una pequeña. Eso no cambia su papel (comprobar que el sistema corre de punta a punta sin fallos), pero conviene que su informe de cierre lo diga.

## Qué se añadió al código

- `eim/validation/power.py`: `min_track_record` (MinTRL), `n_needed` (potencia de una media) y `power_row`. Puro, sin dependencias nuevas. Prueba de definición: en n = MinTRL el PSR vale exactamente 1 − α.
- `eim/validation/spa.py`: `daily_matrix`, `block_length` (Politis-White), `spa_test` y `mcs`, sobre `arch` 8.0.0 (licencia NCSA leída en el paquete instalado; trae statsmodels BSD-3 y patsy BSD-2), en el extra `stats` de `pyproject.toml`. Las pruebas que la usan se omiten si falta.
- `eim/backtest/edge.py`: `bh` (Benjamini-Hochberg, decidido en T95/T129-E7) y la opción `block="auto"` en `sharpe_diff_pvalue`; sin argumento, el bloque sigue siendo √n y el resultado no cambia.

## Límites

- Solo se analizó la familia de T139 (9 claves). La de T137 (520 versiones sobre 2023–2026) exigiría rehacer su simulación entera; dado que su bruto ya era −0,128 R, no se espera otra conclusión.
- La base del SPA es «no operar», no la entrada al azar de V3: responde «¿alguna gana dinero?», no «¿alguna supera al azar con los mismos costos?». Para la segunda ya existe V3.
- MinTRL usa el Sharpe por operación y supone observaciones independientes; los solapes entre operaciones de una misma clave lo hacen optimista.
