# T142 — Las 5 posiciones fantasma: comprobación y efecto medido (2026-11-06)

Hecho desde `juanpablo-cpu`, solo leyendo: copia `v2/backups/eim_20261106-000006`, velas de `data/candles`, trades de `data/micro_hft/trades` y registro `data/obs/spool`. No se escribió en `data/paper.duckdb`.

**Ya no queda ninguna congelada.** Las 5 se reconciliaron a las 20:07 UTC del 2026-11-06 y una sexta, que esa reconciliación congeló y §4 no había previsto, a las 02:33 UTC del 2026-11-07, todas con permiso del usuario. El efecto real está en §5. §1 a §4 se escribieron antes, con la medida hasta las 00:00 UTC de esa copia.

## Resumen

- **Las 5 son falsos positivos.** El recálculo las cierra con ganancia y coincide con los trades capturados. Suman +22,22 USDT.
- **El libro fijo ya tiene esos 5 cierres, con el mismo precio.** Se grabaron antes de congelarlas, porque `_record_ledger` corre antes que la pasada del diario. Son los libros recalculados los que aún las ven abiertas.
- **Lo que falta son 16 entradas que no se tomaron por ellas,** con un resultado de −189,32 USDT, incluido su efecto en el tamaño de las demás. **La congelación no perjudicó a estos libros: los favoreció en 167,10 USDT,** sobre todo a Agresivo. Es suerte de esta muestra y no dice nada a favor del fallo.
- **Causa arreglada** en `v2/eim/paper/protection_settle.py`, con `_never_lower` intacto. Desplegarlo y reconciliar piden permiso.

## 1. Las 5, una por una

El stop guardado salió de la regla conservadora, al cierre de la vela de 15 m. Con las velas de 1 min el orden real es otro: la operación cerró antes de que el precio llegara a ese stop.

| Operación | Lado | Entrada | Stop guardado (t) | Stop real (activo desde) | Salida real | Neto | R |
|---|---|---|---|---|---|---|---|
| `agresivo…4h:1793750400000:consenso_fuerte` | corto | 77 440,83 | 77 043,5 (00:30) | 77 212,4 (00:19) | 77 243,4 a las 00:19 | +6,55 | +0,08 |
| `moderado…4h:1793750400000:consenso_fuerte` | corto | 77 440,83 | 77 043,5 (00:30) | 77 223,6 (00:19) | 77 243,4 a las 00:19 | +1,83 | +0,08 |
| `ppp_btcusdt…4h:1793736000000:agente_levels` | corto | 77 584,82 | 77 116,6 (00:30) | 77 232,8 (00:19) | 77 243,4 a las 00:19 | +9,55 | +0,20 |
| `moderado…15m:1793806200000:base_tendencia` | largo | 80 629,81 | 80 911,7 (22:45) | 80 863,1 (22:41) | 80 841,0 a las 22:41 | +1,91 | +0,09 |
| `moderado…15m:1793806200000:sugerencia_2` | largo | 80 507,85 | 80 882,7 (22:45) | 80 724,4 (22:36) | 80 724,4 a las 22:36 | +2,38 | +0,11 |

Horas UTC del 2026-11-04. La salida va al inicio del minuto cuando ya abre más allá del stop: es lo que hace `_sub_bars`. En el diario el cierre consta al terminar ese minuto (`exit_t` 00:20, 22:42 y 22:37).

**Velas de 1 min y trades coinciden:**

| Hecho | Trades de la captura |
|---|---|
| Grupo 00:30, primer trade del minuto en que se activa el stop real | 00:19:00 a 77 243,4, por encima de los tres stops: es la salida |
| Un corto llega a 77 043,5 y lo vuelve a tocar | 00:20:41,661 y 00:20:41,662 (77 050,1), **ya cerrado** |
| PPP llega a 77 116,6 y lo vuelve a tocar | 00:20:34,750 y 00:20:34,753 (77 118,6), **ya cerrado** |
| Entre las 00:30:00 y su grabación (00:31:20) | de 77 176,7 a 77 253,6, **por encima de los dos stops guardados:** «viva a las 00:30» ya era imposible |
| `base_tendencia`: primer trade tras activarse su stop real | 22:41:00,001 a 80 841,0, por debajo de 80 863,1: es la salida |
| `sugerencia_2`: toca su stop real | 22:36:58,406 (80 724,3) |
| Los largos llegan a sus stops guardados y los pierden | 80 882,7 y 80 911,7 en el mismo milisegundo: 22:41:24,599 y 22:41:24,675 |
| Primer trade de las 22:45:00 | 80 908,0, ya por debajo de 80 911,7 |

**Cómo se llegó a guardarlos** (registro de observabilidad, UTC):

| Grupo | 15 m llega | 1 min trae la última vela | Pasada que guarda | Pasada que congela |
|---|---|---|---|---|
| 00:30 | 00:30:05 | 00:30:42 | 00:31:20 | 00:32:09 |
| 22:45 | no consta | 22:45:40 | 22:45:58 | 22:46:54 |

La pasada que guarda termina **después** de que llegara la última vela de 1 min, pero usa lo que había al empezar a calcular, y calcular lleva decenas de segundos. Eso se deduce: el registro no guarda cuándo empezó. Lo que sí es seguro es que el escalón guardado solo sale de la regla conservadora, y la prueba `test_without_the_gate_it_saves_the_real_premature_step` lo reproduce con 14 de 15 velas: mismo escalón, mismo stop y misma hora en los 8 casos.

**Control:** `ppp_btcusdt…4h:1793750400000:consenso_fuerte` siguió el mismo camino y no se congeló. Guardó 77 030,9 a las 00:30 y cerró en la pasada siguiente a 77 128,7 (+9,81 USDT): `early` lo aceptó y su stop no bajaba, porque el real era el mismo.

## 2. La distorsión

**Método:** reconstruir los 4 libros con el código real (`generate_ideas`, `run_shadow`, `run_profile`) sobre copias recortadas al corte, dos veces: **A** tal como están y **B** como si las 5 se hubieran reconciliado. Se comparan desde el 2026-11-04 00:00 UTC. A reproduce el libro fijo: cuadra al céntimo salvo por las 5 de arriba (Moderado −161,25 + 6,13 ≈ −155,13; Agresivo −300,04 + 6,55 = −293,49; PPP −72,11 + 9,55 = −62,56). El Conservador no cambia.

| Perfil | Capital A | Capital B | B − A | Cierres de las 5 | Entradas no tomadas | Su resultado | Otras cambian de tamaño |
|---|---|---|---|---|---|---|---|
| Moderado | 9 275,05 | 9 292,34 | **+17,30** | +6,13 (3) | 7 | +11,17 | — |
| Agresivo | 8 147,10 | 7 975,84 | **−171,26** | +6,55 (1) | 5 | −177,49 | −0,32 (14 operaciones) |
| PPP | 9 587,30 | 9 574,16 | **−13,14** | +9,55 (1) | 4 | −22,69 | — |
| **Total** | | | **−167,10** | **+22,22 (5)** | **16** | **−189,01** | **−0,32** |

**Rechazos desde el 2026-11-04** por motivos que dependen de lo abierto:

| Perfil | Motivo | En A | Se habrían abierto sin las congeladas, en ese instante | En B |
|---|---|---|---|---|
| Agresivo | `tope_direccion` (3 %) | 33 | 32 | 27 |
| Moderado | `cupo` (6 abiertas) | 22 | 22 | 14 |
| PPP | `cupo` | 5 | 5 | 0 |
| PPP | `cobertura` | 6 | 6 | 0 |
| PPP | `duplicada` | 16 | 0 | 22 |

Los demás rechazos, en su mayoría `costo`, no cambian entre A y B: 459 en total en Agresivo frente a 453, 429 en Moderado frente a 421 y 399 en PPP frente a 394.

**Cómo leer las dos columnas:** «se habrían abierto» quita las congeladas en ese instante y deja todo lo demás igual, así que cuenta de más: cada entrada que entra consume el hueco de las siguientes. Por eso los 32 de Agresivo son solo 5 entradas nuevas en B, y **la cifra a usar es la de B**.

**Por qué el efecto es negativo:** casi todo viene de dos cortos de Agresivo que no se tomaron, `sugerencia_3` a las 03:15 (−97,26) y a las 04:30 (−91,73), los dos con cierre por su SL inicial. Son pocas operaciones y no permiten concluir nada sobre el perfil.

**Límites:** es una reconstrucción y no algo operado; usa las reglas y costos de hoy; y B no incluye lo decidido tras el corte. Al reconciliar, esa parte también cambiará.

**También llega al informe de T31:** `v2/eim/operation/distortions.py` lo añade a los informes de este equipo cuyo periodo se solape, en «Distorsiones conocidas de los libros».

## 3. El arreglo

`eim/paper/protection_settle.py`: la pasada del diario guarda de cada operación el alta y los cambios hasta el primero que dependa de una vela de 15 m sin sus 15 velas de 1 min. El resto, y el cierre, los guarda una pasada posterior ya con el orden real.

- **`_never_lower` no cambia:** una prueba comprueba que lo ya guardado mal sigue retenido, también con el código nuevo.
- **Los libros no cambian:** la vista se calcula igual; solo se retrasa lo que se escribe en el diario. Las reconstrucciones A y B dan lo mismo con `main` y con la rama.
- **Huellas idénticas a `main` (`7fee338`) con `PYTHONHASHSEED=0`:** los 4 perfiles (`conservador` `0ef1f2fab0d9`, `moderado` `321c03c5c18c`, `agresivo` `ce9652084ef1`, `ppp_btcusdt` `f1ab1a96029f`), sus volcados, la mecánica y las versiones de T49. Se comparan 104 `estrategia@marco`, las que da hoy `runs_in`; T135 citó 111.
- **Cuánto se retrasa:** hasta el siguiente recálculo. El sello de la vista no incluye el 1 min, así que puede tardar hasta la próxima vela de 15 m. En los casos reales fue menos de un minuto. No se pierde nada, porque un reinicio recalcula lo mismo.
- **Sin plazo si la cola del 1 min no llega:** se ve en `waiting_fine` y, pasada 1 h, en el aviso `proteccion_espera_1m`.
- **Un hueco interior** se da por definitivo cuando la cola lo rebasa en 1 h, porque Binance puede no tener ese minuto. Si aun así se rellenara después, puede repetirse el fallo. `_never_lower` lo retendría, con su alerta.

**Sigue abierto, en BACKLOG:**
- El libro fijo no pasa por la espera. Puede grabar un cierre conservador que el 1 min cambie después, y su primera escritura es la que queda. No se ha visto: las 91 filas grabadas desde el 2026-11-01 coinciden con el recálculo.
- Una operación congelada sigue subiendo su stop en la vista, sin guardarlo: en A, el de Agresivo llega a 75 162,9 (escalón 63).

## 4. Pendiente de permiso (◆)

1. **Reconciliar las 5**, con la API respondiendo:

```bash
python -m eim.paper proteccion reconciliar "agresivo|BTCUSDT|BTCUSDT:4h:1793750400000:consenso_fuerte" --decision recalculo --nota "falso positivo T142: escalon guardado sin sus velas de 1 min"
```

Igual para las otras 4. **Qué cambiará:** los tres libros se recalculan desde el 2026-11-04. Las 16 entradas de arriba, más las que cambie lo decidido tras el corte, aparecerán como operaciones cerradas y el libro fijo las añadirá marcadas `retro`, porque se graban más de 2 h después de cerrar. Las 14 operaciones de Agresivo que cambian de tamaño seguirán con su fila original y saldrán en la conciliación con otro PnL. El capital de Agresivo bajará unos 171 USDT, según lo medido.

2. **Reiniciar la API** para cargar el arreglo. Sin ello pueden congelarse más.
3. **Al reconciliar:** poner `t1` en `distortions.py`, repetir la medida con la copia de ese día y actualizar las cifras.

## 5. Lo que pasó al desplegar y reconciliar (2026-11-06, con permiso del usuario)

| UTC | Hecho |
|---|---|
| 20:03:59 | PR #217 fusionado (`b1a0a11`), por detrás de T140 (#215) |
| 20:04:33 | Se detiene solo la hija de `uvicorn`; el vigilante la relanza. Puerto y `/v2/health` a los 61 s, `/v2/paper` a los 134 s |
| 20:07:00 | Foto antes de reconciliar: 390 operaciones, **las mismas que con el código viejo**, con el mismo PnL. El despliegue no cambió los libros |
| 20:07:28 → 20:07:36 | Las 5 reconciliadas con `--decision recalculo` |
| 20:08:25 | Pasada siguiente: las 5 cerradas en el diario, al precio de §1 y sus 5 alertas resueltas. **Se congela una sexta** |
| 22:02 (11-06) | El precio toca el stop de la sexta (máximo 76 182,5). Sigue abierta, porque una congelada no se cierra sola |
| 02:33 (11-07) | La sexta, reconciliada con permiso del usuario. El permiso llegó antes, pero la sesión se cortó y se hizo al retomarla |
| 02:34:12 | Pasada siguiente: la sexta cerrada en el diario y su alerta resuelta. **0 congeladas y 0 alertas de protección activas** |

**Efecto medido en los libros reales,** comparando las fotos de antes y después por la API. Es mejor que §2, porque incluye lo decidido hasta las 20:07 UTC:

| Perfil | Capital realizado antes → después | Cambio | Con flotante, antes → después |
|---|---|---|---|
| Moderado | 9 290,59 → 9 308,38 | **+17,79** | 9 121,47 → 9 308,38 |
| Agresivo | 8 206,27 → 8 058,76 | **−147,51** | 8 304,34 → 7 987,96 |
| PPP | 9 616,76 → 9 603,62 | **−13,14** | 9 691,63 → 9 603,62 |
| Conservador | 9 839,97 → 9 839,97 | 0 | igual |
| **Total** | | **−142,86** | |

- **El cambio se compone de:** +22,22 de los 5 cierres, −164,53 de 18 entradas que antes no estaban y −0,56 de 24 operaciones que cambian de tamaño (21 de Agresivo y 3 de Moderado).
- **Las 18 entradas** son 7 de Moderado, 7 de Agresivo y 4 de PPP. Agresivo gana 2 respecto a §2 por lo decidido tras el corte. Ninguna operación desaparece.
- **El flotante cambia mucho más que el capital,** porque desaparece el de las posiciones fantasma: en Agresivo, +147,81 de su corto.
- **Libro fijo:** de 300 a 318 filas de perfil en BTCUSDT, y las 18 nuevas van marcadas `retro`. **Para T31 esas 18 no son operaciones que se vivieran en su momento: se decidieron al recalcular.** Hay que leerlas así. Las 24 que cambian de tamaño conservan su fila original y salen en la conciliación con otro PnL.

**La sexta operación:** `agresivo|BTCUSDT|BTCUSDT:15m:1793981700000:agente_technical`, corto abierto el 2026-11-06 a las 16:15 UTC a 75 504,34, con stop inicial en 76 159,55 y escalón 0.

- **Por qué:** es una cascada que §4 no vio. Reconciliar bajó el capital de Agresivo, así que esta posición, ya abierta, se recalcula con 0,122 BTC frente a los 0,125 guardados. `ladder_floor.mismatch` la retiene por no cuadrar («cantidad guardada 0.125 ≠ recalculada 0.122»). La salvaguarda hace lo que debe. **No es el escalón prematuro** y no toca `_never_lower`.
- **Efecto:** como cualquier congelada, no se cierra sola aunque el precio toque su stop.
- **Por qué solo una:** era la única operación del diario que seguía abierta al reconciliar.
- **Resultado:** cerró en su stop, 76 159,55, con **−93,75 USDT (−1,17 R)**. El camino de 15 m fecha el cierre a las 22:15 UTC, al terminar la vela en que se tocó.
- **Coste de esperar:** la pérdida estuvo fuera del capital de Agresivo 4 h 18 min. Ninguna decisión de ese rato cambió: la foto de antes y la de después solo difieren en esta operación.
- **A diferencia de las 18 de arriba, esta sí se vivió en su momento,** aunque en el libro fijo salga como `retro` porque se grabó más de 2 h después de cerrar.
- **Sin más cascadas:** `agente_ema`, la otra abierta, se dimensionó a las 17:45 UTC, antes de este cierre, y conserva su cantidad.

**Capital realizado de Agresivo en total:** 8 206,27 → 7 965,01 (−241,26). De eso, −147,51 por las 5 y sus entradas no tomadas y −93,75 por la sexta.

**«Sin alertas al arrancar» comprobado:** la sesión de T140 reinició el vigilante y la API a las 02:35:48 UTC, para desplegarla (`--loop …selector_loop`). A las 02:37:08 `/v2/paper` respondía con 0 congeladas, sin recuperaciones, 0 alertas desde el arranque y ninguna activa; el capital de los 4 perfiles, igual que antes del reinicio. El gate completo de T140 y T142 juntas salió verde: `gate-t142-cierre`, rc 0, 3 129 pasadas, 8 omitidas, 0 fallos, 1 100 s, sin pausas.

