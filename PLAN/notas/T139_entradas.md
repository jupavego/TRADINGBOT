# T139 — Una ronda de hipótesis de entrada, por la puerta de T49

**Modo: SIMULADO. Nada de esta tarea habilita dinero real ni cambia lo que abren los perfiles.**
Fase 23. Pre-registro `v2/eim/validation/prereg/prereg_t139_v1.json` (commit `3d396f7`, anterior a la descarga y a todo cálculo); informe `v2/reports/t139_entradas.{md,json,csv}`, calculado con `0d04ab3`. Reproducible con tres órdenes: la descarga, cerca de una hora, y unos 13 minutos cada etapa:

```
python scripts/t131_history.py --out backups/t139_banco --from 2019-09-01 --paper backups/t131_banco/paper.duckdb
python scripts/t139_entradas.py --data backups/t139_banco --stage banco
python scripts/t139_entradas.py --data backups/t139_banco --stage limpia --repeat-reason "reproducir"
```

## 1. Resultado

**P1: ninguna clave sigue ni queda en observación. La regla de parada, vinculante por decisión del usuario, recomienda parar la búsqueda.** Las 9 claves salen RECHAZADA con la puerta de T49 y ninguna cumple las cinco condiciones de la regla de lectura. Ninguna podía salir VALIDADA en esta corrida: V5 pide 20 operaciones en vivo, y se fijó antes de calcular.

Parar no prueba que no exista ventaja. Prueba que no la hay por encima de lo detectable con estos datos.

| Clave | n | R neto | Bruto | Mínimo necesario | Equilibrado | Costo | Banco: bruto (n) |
|---|--:|--:|--:|--:|--:|--:|--:|
| `funding_contra@1h` | 454 | −0,040 | +0,054 | 0,187 | +0,048 | 0,095 | +0,018 (624) |
| `funding_contra@4h` | 232 | −0,034 | +0,007 | 0,253 | −0,003 | 0,041 | +0,063 (330) |
| `flujo_sigue@1h` | 635 | −0,080 | +0,060 | 0,218 | +0,058 | 0,140 | −0,027 (857) |
| **`flujo_sigue@4h`** | **152** | **+0,182** | **+0,250** | **0,312** | **+0,252** | **0,068** | **+0,113 (222)** |
| `flujo_revierte@1h` | 205 | −0,273 | −0,093 | 0,317 | −0,087 | 0,180 | −0,030 (247) |
| `flujo_revierte@4h` | 60 | −0,221 | −0,120 | 0,497 | −0,123 | 0,100 | −0,375 (72) |
| `cascada_revierte@1h` | 451 | −0,103 | +0,012 | 0,207 | +0,009 | 0,115 | −0,019 (651) |
| `cascada_revierte@4h` | 266 | −0,010 | +0,059 | 0,236 | +0,053 | 0,069 | +0,037 (390) |
| `momento_1d@1d` | 121 | +0,048 | +0,115 | 0,350 | +0,088 | 0,066 | +0,045 (151) |

Ocho de nueve están lejos: como mucho un tercio del mínimo, y dos con bruto negativo. El control no destaca sobre sus sustitutas en 1 h (p = 1,00) ni en 4 h (p = 0,43).

## 2. La clave que hay que mirar: `flujo_sigue@4h`

**Es el único resultado de todo el proyecto que se acerca, y aun así no pasa.** Compra agresora persistente, a favor, en 4 h: +0,182 R netos con IC [+0,0002, +0,366], +0,250 R brutos con los dos lados positivos (largos +0,330, cortos +0,174), DD 7 %, 13 de 19 ventanas positivas y aguanta los costos × 1,5 (+0,149 R). Cumple cuatro de las cinco condiciones. **Solo falla V3 con Holm:** p bruto 0,0016 (z = 2,95) frente a los 5,9·10⁻⁵ (z = 3,85) que exige una familia de 841.

**Lo que hay que decir de la ◆4.** La ficha decía que contar solo la familia de T139 «apenas ayudaría» y que solo lo haría con poca muestra. Este es justo ese caso: con una familia de 9, p × 9 = 0,014, y la clave **sí** seguiría a la fase en vivo. La decisión de mantener Holm sobre las 841 claves cambia el estado de esta clave. No se reabre aquí: cambiar la vara después de ver el resultado es lo que el pre-registro impide, y el usuario lo decidió antes de calcular.

**Por qué no cambia la recomendación, aun sabiendo eso:**

- **Se debilita en el tramo reciente.** En el banco da +0,018 R netos, IC [−0,136, +0,167], y ahí los cortos pierden (−0,072 R), así que el equilibrado (+0,092 R) ya no cubre el costo (0,095 R). El banco solo descarta y esta clave no la descarta (bruto ≥ 0), pero lo que queda de ventaja reciente es cero dentro del error. El IC de la lectura limpia roza el 0 por dos diezmilésimas.
- **Ese periodo era algo más fácil en 4 h:** antes de 2023 la línea base da +0,044 (indicadores) y +0,059 R (base), y el control +0,053 R. Tampoco explica +0,25 R, pero rebaja la cifra.
- **Es la mejor de nueve.** Al azar, la mejor de nueve llega a ese p una vez de cada 70 (1,4 %). Es llamativo, no concluyente, y solo cuenta si se olvidan las 832 claves anteriores.
- **No se podría validar a tiempo.** Con ese mismo bruto, V3 pide n ≈ 237: faltan 85 operaciones, unos 18 meses a 0,16 al día. En los 6 meses de la fecha límite solo entrarían unas 29, que tendrían que dar **+0,48 R brutos**, el doble que en el tramo limpio y cuatro veces lo del banco. Con 20 operaciones en vivo (4 meses) el error estándar es de 0,22 R: no distingue nada.

**Lo que queda, sin hacer nada:** las reglas están congeladas y el alta fue 2026-11-06T05:00Z, así que el tramo en vivo se acumula solo. Si algún día se quiere mirar, basta refrescar las velas y recalcular: no hace falta tener nada corriendo ni decidirlo hoy.

## 3. Cómo se sabe que se midió lo que se dice

**Orden, comprobable en git:** pre-registro (`3d396f7`) → reglas y pruebas (`8a599e7`) → revisión de código (`b56993e`) → cobertura y banco, con los intentos ya confirmados (`0d04ab3`) → lectura limpia, una sola vez. Ninguna regla, parámetro o clave cambió tras el pre-registro.

**Regresión exacta contra T137,** por los dos caminos: `control_aleatorio@1h` da n = 1 810 y bruto −0,009823, con los contextos guardados y con los mínimos. El ATR propio coincide con el de 33 399 contextos (diferencia mediana 0, máxima 0,13 %). Es lo que permite usar las reglas antes de 2023, donde no hay contextos.

**Cobertura del tramo limpio (2020–2022): 100 %** en 1 min, 15 min, 1 h, 4 h, funding y `taker_buy_v`. La historia empieza el 2019-09-08T17:57Z, lo que la ficha daba por sin verificar.

**Pruebas:** señales causales (reescribir el futuro no cambia ninguna decisión), funding en su valor base sin señal, huecos sin señal, bruto ≈ 0 en paseo aleatorio sin costos, ninguna clave en `CATALOG` y ninguna importación desde `eim/paper`. La revisión de código encontró que la guarda de la lectura limpia no exigía la regresión con contextos mínimos: se corrigió antes de gastarla.

## 4. Lo que se aprendió por el camino

1. **El error de la primera ficha:** leí el p95 de +0,096 R del control de T137 como si fuera con n ≈ 1 800. Son 300 ideas por serie, y no hay ninguna dispersión de 2,4 veces. Corregido antes del pre-registro.
2. **El costo en R depende del periodo.** Antes de 2023 la volatilidad era mayor y el costo baja frente a lo medido en T137 (1 h: 0,10–0,18 R; 4 h: 0,04–0,10 R). En 1 d son 0,066 R, no los 0,03–0,04 R que estimaba la ficha.
3. **Las reglas nuevas son más lentas que el catálogo,** como avisaba la ficha: 0,05–0,58 operaciones al día, frente a las 1,0 (1 h) y 0,24–0,8 (4 h) medidas.
4. **La ronda confirma la idea de partida.** Funding, cascadas forzadas y flujo en contra no dan nada detectable; la única señal, el flujo a favor en 4 h, es un marco lento y se debilita en el tramo reciente.

## 5. Lo que T139 no hace

- **Deja la etapa en vivo sin implementar.** P2, P3 y el recálculo mensual solo hacen falta si alguna clave sigue, y ninguna sigue. El pre-registro ya los fija.
- **No mide ETHUSDT** (T122), **ni el libro de los perfiles**, **ni entradas maker** (BACKLOG T139).
- **No toca T31:** nada escribe en `data/paper.duckdb`. Los 9 intentos quedan en `v2/eim/validation/attempts_t139.json` y entran en el registro vivo al próximo reinicio de la API, con la familia en 841. Solo la hace más exigente.

## 6. ◆ Resuelta: se cierra la búsqueda con P1

El usuario delegó la decisión (2026-11-06, «toma tu la mejor decision»), y **Claude decidió cerrar**, aplicando la regla de parada que el usuario hizo vinculante antes de calcular. Seguir `flujo_sigue@4h` habría sido una excepción a esa regla justo cuando salió un resultado cercano, que es lo que la regla existe para impedir. Tampoco habría servido de mucho: se debilita en el tramo reciente y no podría validarse antes de la fecha límite (§2).

**Qué significa:** no se abren más tareas de búsqueda de entradas direccionales con estos datos. La línea solo se reabre con una fuente con al menos un año de historia propia, evaluada en vivo y con claves nuevas. T31 cierra como está previsto y los perfiles no cambian. La etapa en vivo se queda sin implementar.

**Lo que sigue siendo del usuario:** para qué sirve entonces el sistema (análisis, arbitraje, HFT tras T78). Es otra decisión, posterior a esta, y no se tomó aquí.
