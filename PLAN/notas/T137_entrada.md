# T137 — La entrada: SL inicial más amplio y tope de costo, por la puerta de T49

**Modo: SIMULADO. Nada de esta tarea habilita dinero real ni cambia lo que abren los perfiles.**
Fase 23. Pre-registro `v2/eim/validation/prereg/prereg_t137_v1.json` (commit `213247f`, anterior a
todo cálculo); informe `v2/reports/t137_entrada.{md,json,csv}`, reproducible con una orden en unos
6 minutos:

```
python scripts/t137_entrada.py --data backups/t131_banco
```

## 1. Resultado

**Ninguna versión validada, y ninguna justifica seguir.** De 520 versiones, en la lectura oficial:
484 EN OBSERVACIÓN, 36 RECHAZADA y 0 VALIDADA. Ninguna cumple tampoco la regla de lectura que el
pre-registro fijó para proponer un seguimiento prospectivo.

**Apartar el stop no crea ventaja: abarata el costo en R.** Es el hallazgo que queda. En la lectura
del banco, 1 h y 4 h, la ventana más favorable y la de más muestra:

| Variante | n | E[R] | Costo R | Bruto R | PF |
|---|--:|--:|--:|--:|--:|
| padre, sin cambios | 29 828 | −0,152 | 0,152 | **−0,000** | 0,731 |
| `m8` | 23 389 | −0,093 | 0,097 | +0,005 | 0,811 |
| `s1` | 27 610 | −0,121 | 0,130 | +0,009 | 0,778 |
| `tope` | 4 175 | −0,117 | 0,070 | −0,047 | 0,768 |
| `m8_tope` | 9 004 | −0,060 | 0,054 | −0,005 | 0,859 |
| `s1_tope` | 4 964 | −0,083 | 0,066 | −0,017 | 0,829 |

El bruto se queda en torno a cero en todas: de padre a `m8_tope` el neto mejora 0,092 R y el costo
baja 0,098 R. La mejora de T134 y T136 era real, pero toda ella es costo que se diluye al medir en
un R más grande. Las entradas no tienen ventaja que un stop distinto pueda sacar a la luz. Y filtrar
por costo bajo no selecciona mejores entradas: `tope` tiene peor bruto que el padre.

En datos donde no se eligió nada (la reserva) la foto es peor: padre −0,371 R, `m8` −0,291 R, `s1`
−0,257 R, `m8_tope` −0,143 R con 256 operaciones, todas con bruto negativo.

## 2. Por qué tres lecturas

Es la decisión de diseño de la tarea, y quedó fijada en el pre-registro antes de ver una cifra.

T49 define ventana de ajuste como «datos que se miraron para elegirla o ajustarla». `M8 q=0.95`,
`S1 d_min=3 atr14` y el tope de 0,08 R se eligieron mirando T134 y T136, así que **esa ventana
entera, 2023-01-11 → 2026-07-11, es ajuste de estas versiones**. Puntuarlas ahí como fuera de
muestra sería medirlas con los datos que las eligieron. Y además heredan las ventanas de su padre:
las 104 versiones vigentes tienen una automática hasta 2026-10-22T22:36Z.

| Lectura | Datos | ¿Da veredicto? | Para qué sirve |
|---|---|---|---|
| **Oficial** | 2026-10-22 → 2026-11-03, ≈ 11 días | **Sí** | Es la regla de T49 tal cual la aplica el código |
| Reserva | 2026-07-11 → 08-16 y 2026-10-16 → 11-03 | No | Datos donde no se eligió la geometría ni se ajustaron las reglas |
| Banco | 2024-01-11 → 2026-07-11, sin 15 m | No | Cota optimista: lo que falla aquí no pasaría en limpio, lo que pasa no prueba nada |

Las tres pasan por la misma `gate.measure`, con la misma familia de Holm. Las descriptivas solo le
dan otras ventanas, y por eso no hay una segunda definición de «fuera de muestra».

Lo que esto implica, y se escribió antes de calcular:

- **Ninguna versión podía salir VALIDADA en esta corrida.** V5 exige un tramo en vivo, y una
  operación solo cuenta como `vivo` si su decisión es posterior al alta de la versión. Hay 0. El
  máximo posible era EN OBSERVACIÓN.
- **V1 no se alcanza en la lectura oficial.** Se confirmó: 0 de 520. Tampoco en la reserva: 0 de 520.
- Por eso «qué criterio falla más» en la oficial (V1, 520 de 520) no dice nada de las estrategias.
  Lo informativo está en el banco: V3 falla en 310 de las 310 versiones con operaciones (ninguna
  pasa Holm), V2 en 296, V5 en 148 y V4 en 85.

## 3. Lo que se midió

**Intentos.** Las 104 estrategia@marco del catálogo, sin elegir ninguna, por cinco variantes = 520.
La familia de Holm pasa de 312 a 832 claves y las réplicas de V3 a 33 280. Cuentan todas, también
las inertes y las que no tienen operaciones.

**Lo que deja fuera el tope.** Se mide sobre el SL de la versión, ya apartado, porque es el stop que
pagaría. Frente a su gemela sin tope, en el banco: `tope` deja fuera el **86,0 %** de las
operaciones (T136 midió el 89 % sobre la escalera y el SL de la idea), `s1_tope` el 82,0 % y
`m8_tope` el 61,5 %. **En 15 m deja fuera el 100 %:** un SL de 15 m casi nunca llega al 2 % del
precio que pide un tope de 0,08 R. Llegan a V1 en el banco, de 73 versiones: `m8` 25, `s1` 26,
`m8_tope` 21, `s1_tope` 16 y `tope` 14. El tope baja la muestra, pero no es lo que impide validar.

**Inertes.** `m8` no movió ni un SL en 57 de sus 104 versiones (37 de 73 en el banco): esas
estrategias no llegan a 30 ganadoras en el tramo de ajuste y «sin muestra no se aprieta». `s1` en 18,
porque su stop ya estaba más lejos. Se marcan en el CSV. Son su padre con otro nombre.

**Las mejores, y por qué no valen.**

- Con ≥ 100 operaciones en el banco solo dos tienen R > 0: `contra_sintesis@1h@v1373` (`tope`,
  n = 146, +0,059 R, IC [−0,125, +0,251], p bruto 0,025, Holm 1,0, 7 de 13 ventanas positivas) y
  `ppp_tendencia@1h@v1371` (`m8`, n = 237, +0,005 R).
- V2 solo se cumple en seis filas del banco, que son dos estrategias repetidas por tres variantes:
  `base_retroceso@4h` (n = 33, +0,366 R, y −0,432 R en la reserva con n = 7) e `ind_adx@4h` (n = 2).
- En la reserva, la mejor con ≥ 20 operaciones es `sugerencia_3@4h@v1371` (n = 26, +0,418 R), y **la
  tercera es el propio control aleatorio**: `control_aleatorio@4h@v1372`, n = 20, +0,376 R. En esa
  muestra, 0,4 R no se distingue del azar.
- `m8_tope` sale con +0,068 R en la lectura oficial, pero con 76 operaciones, y −0,143 R en la
  reserva que la contiene.

**Control (cierra BACKLOG T134 (1)).** Ahora sí pone a prueba la geometría: el cuantil de
`control_aleatorio` se toma de `consenso_sintesis@marco`, que tiene sus mismas salidas (SL 1,5 ATR,
TP 2,5 ATR), y M8 mueve el SL en el 92 % de las ideas de control y S1 en el 41 %. Ninguna variante
destaca sobre las 20 series sustitutas (p entre 0,38 y 0,86), así que no hay indicio de anticipación
ni de un defecto. Las entradas al azar se sortean con la geometría real del control y la σ de la
propia sustituta: con el 1 % fijo de T134, el tope las habría vetado todas.

**15 m (cierra BACKLOG T136 (1)).** Se pudo medir: 4 712 operaciones del padre desde 2026-09-16. El
costo ex ante de la idea media es **0,490 R**, frente al 0,173 R que T136 midió como cota por abajo
en 1 h y 4 h; realizado, 0,38 R. E[R] −0,401 R. Eso es la idea media, no lo que abren los perfiles:
su veto de costo (0,12–0,20 R, y 0,30 R para el mínimo de abiertas) deja fuera las más caras. `s1` es
lo que más ayuda aquí: mueve el SL en el 98,8 % de las ideas, baja el costo a 0,175 R y deja E[R] en
−0,172 R, con bruto +0,003 R. Sigue siendo costo, no ventaja. Son solo siete semanas y una parte está
en la ventana de T48b: es descriptivo.

## 4. Comprobaciones de que se midió lo que se dice

Cinco regresiones contra lo publicado, todas exactas al sexto decimal y con el mismo n:

| Caso | n | E[R] | Contra |
|---|--:|--:|---|
| `M0 first_r=0.1` | 29 828 | −0,153823 | T134 |
| `M8 q=0.95` con M0 | 29 841 | −0,104489 | T134 |
| `S1 d_min=3 atr14` con M0 | 29 841 | −0,134444 | T134 |
| tope 0,08 con M0 | 3 216 | −0,055692 | T136 |
| padre por el camino de las versiones | 29 828 | −0,152490 | M1 de T134 |

La última prueba el camino entero: de todas las ideas, por la regla y por `run_shadow`, sin tocar
nada, se llega a las mismas operaciones que el banco midió con su propia salida.

**La corrida se repitió dos veces,** y lo que cambió se dice. La primera mezclaba
`control_aleatorio` en las tablas agregadas, y T134 lo mide aparte: se vio porque el padre daba
−0,155 R en vez de los −0,152 R de T134, y esa comprobación quedó como la quinta regresión. La
última sale del código ya revisado (`f569129`, `code-review` de la ficha). Los recuentos de
veredictos son los mismos en las tres: ninguna cifra de las tablas de veredictos cambió por repetir.

## 5. Tres cosas encontradas por el camino

1. **Las unidades de M8 no coinciden desde T134.** El cuantil del MAE se estima en σ de Parkinson
   (`t134_exits_ab._ratio_of` con `SIGMAS[1]`) y se aplica multiplicando por σ ATR14 (`grid._policy`
   toma el primer estimador). La mediana de ATR14/Parkinson es **1,377**, así que «M8 q=0.95» pone el
   stop un 38 % más lejos de lo que dice su nombre. Se conservó a propósito, y consta en el
   pre-registro: es la geometría que dio la señal. Corregirla es otra variante y otros intentos.
2. **Una versión de T137 podía envenenar a una viva.** `ValidationStore.ensure`, sin versión vigente,
   toma de padre a la última de la familia. Un intento registrado le habría pasado sus ventanas de
   ajuste, y la versión viva se habría quedado sin evidencia. Lo atrapó la prueba del servicio;
   `ensure` ahora no ve los intentos, y hay pruebas de ello.
3. **S1 con tope es casi igual que el tope a secas** en los tramos recientes (n = 18 y n = 65,
   idénticas): 3 ATR de 15 m rara vez llegan al 2 % del precio. Con baja volatilidad, S1 no alcanza
   lo que el tope pide.

## 6. Cómo llega al registro sin tocar T31

T137 no escribe en `data/paper.duckdb`: lo tiene abierto la API, DuckDB admite un solo escritor y
parar la API tocaría la corrida. Los 520 intentos quedan en un archivo versionado,
`v2/eim/validation/attempts_t137.json`, y el `Validator` de la API los da de alta la primera vez que
calcula tras cargar este código. **Hasta el próximo reinicio de la API, el archivo es el registro.**

Nacen retirados, no se evalúan, no se publican y `ensure` no los ve, así que:

- **No cambia lo que abren los perfiles.** Ni `eim/paper` ni el catálogo se tocaron, las huellas de
  las estrategias son las mismas y una prueba impide importar T137 desde `eim/paper`.
- **Lo único que cambia al reiniciar** es la Puerta de T49: su familia de Holm pasa de ~300 a ~830
  claves, solo más exigente, y V3 hace unas tres veces más réplicas. Con la muestra viva de hoy son
  segundos cada 4 h.

## 7. Lo que T137 no hace

- **No valida ni descarta para siempre una estrategia.** La lectura oficial no tiene muestra.
- **No puntúa la escalera:** `validation_v1` se define sobre operaciones sombra. M0 solo está en la
  regresión. Con M0 las cifras de T134 y T136 eran algo mejores en E[R] (−0,104 y −0,056 R) pero con
  la misma forma (PF 0,475 y 0,632). Puntuarla exigiría `validation_v2`.
- **No mide ETHUSDT:** solo hay unos 10 días de contextos.
- **No mide el libro de los perfiles:** cupos, pesos y capital.

## 8. ◆ Pregunta al usuario

**¿Se cierra esta línea de trabajo?**

Lo que sostiene la evidencia: **sí.** Es lo que el pre-registro fijó para este caso («si ninguna
cumple, se propone no seguir con esta línea»). Apartar el stop y filtrar por costo reducen la
pérdida, pero el bruto sigue en cero: tocar la geometría no va a crear una ventaja que las entradas
no tienen. El trabajo siguiente sería buscar entradas con bruto positivo, y eso es una tarea nueva.

Si se quiere una última comprobación, es barata: repetir esta misma orden al cerrar T31
(2026-11-27), con el banco refrescado (`scripts/t131_history.py`) y las mismas huellas. Los
contextos desde el alta son los primeros que cuentan como `vivo`, y es la única vía por la que una
de estas versiones podría llegar a VALIDADA. No se espera que cambie la conclusión.
