# T143 — Pre-registro de la medición maker frente a taker (entregable 1)

**Modo: SIMULADO.** Esta medición no cambia ningún perfil, no toca `data/` y no habilita dinero real.

**Escrito antes de calcular nada.** Este archivo se confirma en un commit propio, anterior al commit del script y del informe. Si algo de aquí cambia después de ver una cifra, se declara en el informe con su motivo y la versión anterior queda en el historial de git.

**Por qué existe este pre-registro.** El BACKLOG ya avisa, dos veces, de que las entradas maker **bajan el costo y pueden empeorar el bruto por selección adversa** (T47 (1), T48b (2)), y T139 las excluyó por eso. Una medición sin criterio escrito de antemano acabaría eligiendo la variante que mejor salga. Aquí el criterio y la rejilla están fijados y son los de §3 y §4.

---

## 1. Qué se compara

La **misma decisión**, ejecutada de dos maneras. Nada más cambia: ni la regla de entrada, ni el SL, ni el TP, ni la salida, ni el marco, ni el tamaño.

| Brazo | Entrada | Comisión de entrada | Deslizamiento de entrada |
|---|---|---|---|
| **taker** (hoy) | A mercado, en la apertura de la vela siguiente a la decisión | `taker_fee` = 5 pb | el del modelo de T25 (`_slip`) |
| **maker** | Orden límite en el **cierre de referencia de la vela de decisión** (`idea.entry`, el mismo precio que ya usa `atr_draft`), vigente `fill_h` | `maker_fee` = 2 pb | 0 por construcción: si se llena, se llena a su precio |

**Las salidas no cambian en ningún brazo.** SL, BE y salida por tiempo siguen pagando `taker_fee` y su deslizamiento; el TP ya paga `maker_fee`. Esta medición es solo sobre la entrada.

**Mecánica:** la que ya tiene `eim/paper/engine.py` (`_limit_fill` y `simulate`), sin tocarla. Tres desenlaces posibles del brazo maker que el taker no tiene:

- `fill`: el precio toca `entry` dentro de la vigencia → se entra al precio pedido, sin deslizamiento.
- `NO_LLENADA`: la vigencia expira sin tocar `entry` → **no hay operación**.
- `OBJETIVO_SIN_LLENAR`: el precio alcanza el TP **antes** de volver a `entry` → no hay operación, y es justo el caso que la selección adversa describe: el movimiento ocurrió y nos lo perdimos.

**Universo:** solo las ideas con `kind == "market"`. Las estrategias que ya proponen `limit` de nacimiento (`strategies.py`) no entran en la comparación: no hay nada que convertir. El informe dice cuántas son.

## 2. Las dos lecturas, y cuál decide

**La no ejecución no es gratis.** Una orden que no se llena no es una operación que sale 0: es una decisión que no se ejecutó, y la comparación honesta se hace **por decisión**, no por llenado.

| Lectura | Denominador | Para qué |
|---|---|---|
| **A. Por intento** (decide) | Todas las decisiones del universo, llenadas o no. Las no llenadas cuentan **R = 0** | Es la única comparación emparejada: los dos brazos ven exactamente las mismas decisiones |
| **B. Por llenado** (descriptiva) | Solo las operaciones que existieron en ese brazo | Enseña el precio que se consigue cuando se consigue. **No decide**, porque los dos brazos no tienen el mismo denominador |

**Emparejamiento.** Los dos brazos se simulan sobre el **mismo conjunto de ideas, una a una** (`simulate` por idea), sin la regla de «una viva por estrategia» de `run_shadow`. Es deliberado: si el brazo maker no se llena, la estrategia quedaría libre antes y tomaría ideas distintas, y entonces no habría pareja que comparar. Esta lectura aísla el mecanismo de entrada, que es lo que se está midiendo.

**Lectura secundaria, declarada aquí y descriptiva:** la misma comparación **con** `run_shadow` en cada brazo, que sí respeta una operación viva por estrategia y por tanto cambia el conjunto de ideas tomadas. Enseña qué le pasaría al libro de verdad. **No decide nada**, porque no está emparejada.

## 3. Rejilla, fijada

`fill_h` (vigencia de la orden límite), en **velas del marco de decisión**:

| Valor | Papel |
|---|---|
| 0,5 vela | control de estabilidad |
| **1 vela** | **el valor que decide** |
| 2 velas | control de estabilidad |

Son tres valores y se cuentan como tres. **El veredicto lo da 1 vela**, elegido antes de medir porque es el plazo que no inventa un parámetro nuevo: la orden vive lo que vive la decisión. Los otros dos solo comprueban que el signo no depende del plazo.

El precio límite es `idea.entry` y no se busca ningún desplazamiento pasivo: añadir un offset sería un parámetro más que ajustar.

## 4. Criterio de adopción, fijado

Maker se adopta **solo si se cumplen las tres**, en la lectura A (por intento), sobre el banco de T131:

1. **El costo baja de verdad:** `costo_R(taker) − costo_R(maker) ≥ 0,04 R`.
2. **El bruto no cae más de lo que baja el costo:** `ΔE[R] neto por intento ≥ 0`, es decir, el neto por decisión no empeora.
3. **El signo de ΔE[R] neto no cambia** entre los tres valores de `fill_h`, ni entre los años del banco.

Y además, como control de que no se adopta ruido: **el IC95 % bootstrap emparejado de ΔE[R] neto por intento se informa siempre**, y si incluye 0 el informe lo dice con esas palabras. Un ΔE[R] positivo cuyo IC incluya 0 **no cumple el criterio 2**: se exige el límite inferior del IC ≥ 0.

**Si no se cumple, maker no entra**, se publica igual y se anota como medido. Ese es un resultado válido y es el que el BACKLOG hace esperar.

## 5. Lo que esta medición NO es

- **No es una búsqueda de ventaja.** No pasa por la puerta de T49, no pide V2 ni V3 y no reabre T139 (P1 es vinculante). Mide un costo de ejecución con una regla de decisión escrita antes.
- **No reclama Brier, Sharpe ni edge.** Si el bruto sube, se dirá que subió **y que no se sabe por qué**, porque cambiar el precio de entrada cambia también la geometría en R (el riesgo es `|fill − sl|`) y eso no es ventaja predictiva.
- **Consecuencia que sí hay que decir:** adoptar maker **cambia la huella de versión de todas las estrategias afectadas** (`versioning.py`), y por tanto reinicia la cuenta de operaciones en vivo de V5. El informe lo dice y la decisión es ◆ del usuario.

## 6. Datos y reproducción

- **Banco de T131:** `C:\Users\jo\Desktop\JP\TRADINGBOT\v2\backups\t131_banco` (copia; no se toca el almacén vivo). Marcos 1 h y 4 h: **el banco no tiene 15 m**, así que esta medición **no dice nada de 15 m**, que es justo el marco donde el costo pesa más (T136 §1). El informe lo repite.
- **Libro vivo:** cruce descriptivo del `ledger.csv` comparando las 155 entradas `limit` ya existentes con las 256 `market`. **Está confundido** —cada estrategia elige su tipo, así que no se comparan iguales— y por eso solo sirve de control de realidad, nunca de evidencia. El informe lo dice.
- **Salidas:** `v2/reports/t143_maker.{md,json,csv}`, semilla fija, sin red.
- **Carga del equipo:** la corrida va por la cola de T127, en IDLE y de una en una.
