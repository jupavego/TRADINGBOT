# T136 — Riesgo por operación con costos y control de drawdown gradual

Fase 22 · hecha el 2026-11-04 desde `juanpablo-cpu` · informe `v2/reports/t136_riesgo.{md,json}`
y `v2/reports/t136_deslizamiento.json` · reproducible con dos órdenes:

```
python scripts/t136_riesgo.py --data backups/t131_banco
python scripts/t136_deslizamiento.py --root data
```

Se hace **después de la ◆ de T134** y sin adoptar ninguna salida: T134 rechazó las 87 variantes,
así que aquí no se elige nada de salida. Lo que T136 toca es **cuánto se arriesga**, que es la
otra palanca de §2.3 («el tamaño es la principal palanca de riesgo, más que el stop»).

**Todo lo nuevo sale apagado.** `risk_includes_costs`, `dd_steps`, `cvar_limit_r` y el Kelly son
parámetros con valor por defecto neutro, igual que los `caps` cuando se introdujeron: ningún
perfil cambia, la corrida de T31 sigue igual y el A/B de T130 no se rompe. Encender cualquiera de
ellos es decisión ◆ del usuario, y esta nota es para tomarla con cifras.

## Resumen: cuatro cosas medidas y una conclusión que ya conocíamos

1. **El riesgo por operación miente en un 17,3 %.** Dimensionando con la distancia al SL a secas,
   al saltar el stop inicial no se pierde el riesgo declarado sino **×1,1734**: el Conservador
   dice 0,50 % y arriesga 0,587 %. Incluir el costo multiplica la cantidad por 0,8522 y deja la
   pérdida al stop **exactamente** en lo declarado. Es un defecto de veracidad, no de rendimiento.
2. **El tope de costo debería ser 0,08 R y no 0,12–0,20 R.** Es monótono: apretando el tope,
   E[R] va de −0,118 R (0,20) a −0,056 R (0,08) y el PF de 0,44 a 0,63. Pero deja fuera el 89 %
   de las operaciones, y **es el mismo hallazgo de T134** por otro camino: un costo bajo en R es
   un stop lejano, así que «tope más apretado» dice lo mismo que `M8` y `S1` (apartar el SL).
3. **El freno gradual funciona y el de hoy no.** Por pliegue de tres meses, el Agresivo sin
   frenos pierde el 100 % (10 de 10 pliegues arruinados); con el freno todo o nada de hoy pierde
   el 96,5 % (el freno reinicia el máximo y vuelve a operar); con el gradual pierde el 9,7 % y no
   arruina ningún pliegue. El gradual no es mejor por operar mejor: es mejor **porque deja de
   operar** y, al no reiniciar el máximo, no vuelve.
4. **El Kelly sobre el límite inferior del IC da 0 %.** E[R] = −0,1538 R con error estándar
   agrupado por día 0,0052 → límite inferior **−0,1640 R**. Los cuatro perfiles reciben tamaño 0.

La conclusión es la misma de la fase: **el problema está en la entrada.** Dos protecciones
independientes —Kelly y el freno de drawdown— llegan por caminos distintos a la misma respuesta,
que es apagar el sistema. Ninguna crea ventaja; las dos impiden que la falta de ventaja se cobre
la cuenta.

## 1. Riesgo presupuestado con costos (entregable 1)

`eim/paper/risk_budget.py`, con **una sola** definición del costo en R (`cost_r`) que ahora usa
también el veto de `vetoes.py`: dos definiciones del mismo número son la forma más fácil de que
el presupuesto y el veto se contradigan (es E11 aplicado a los costos, como ya se pedía para σ).

| | Costo ex ante medio | Se arriesga de más |
|---|--:|--:|
| Todo (29 828 ops fuera de muestra) | 0,1734 R | 17,3 % |
| 1 h (28 689) | 0,1767 R | 17,7 % |
| 4 h (1 139) | 0,0900 R | 9,0 % |

**La cifra es una cota por abajo.** El banco de T131 se pre-registró con marcos 1 h y 4 h, así que
aquí no hay ni una operación de **15 m**, que es donde el stop está más cerca y el costo pesa más
(T48b lo midió en 0,48 R con 4 034 ops). Los perfiles **sí** operan 15 m en vivo. Medirlo exige un
banco con 15 m, es decir una versión nueva del pre-registro → BACKLOG.

Encenderlo (`risk_includes_costs=True`) reduce todas las cantidades un 14,8 %. No mejora la
esperanza en R —no toca la geometría— y hace verdadero lo que el perfil declara.

## 2. El tope de costo en R (entregable 2)

| Tope | Entra | n | E[R] | Acierto | PF | CVaR 95 % |
|--:|--:|--:|--:|--:|--:|--:|
| 0,08 R | 10,8 % | 3 216 | −0,0557 | 85,0 % | 0,632 | −1,1337 |
| 0,10 R | 21,6 % | 6 434 | −0,0650 | 84,1 % | 0,596 | −1,1429 |
| 0,12 R | 33,5 % | 9 980 | −0,0798 | 82,7 % | 0,546 | −1,1620 |
| 0,15 R | 50,9 % | 15 195 | −0,0977 | 80,8 % | 0,492 | −1,1845 |
| 0,20 R | 72,3 % | 21 561 | −0,1183 | 78,9 % | 0,444 | −1,2176 |

Hoy: Conservador 0,12 · Moderado 0,15 · Agresivo 0,20 · PPP 0,15. Apretar a 0,08 R es la única
palanca de esta tarea que mejora E[R], y **no basta**: a 0,08 R sigue perdiendo 0,056 R por
operación. Es un filtro, no una ventaja.

## 3. Frenos y límite de CVaR (entregable 4)

El freno gradual (`caps.dd_steps`) recorta el riesgo por tramos; el límite de CVaR
(`caps.cvar_limit_r`) lo recorta cuando la cola realizada es peor que el límite. Los dos se miden
simulando el capital del perfil con **el mismo código que corre en el libro** (`caps.Brake`), no
con una reimplementación.

Retorno **mediano por pliegue** (tres meses, capital nuevo cada vez):

| Caso | Conservador | Moderado | Agresivo |
|---|--:|--:|--:|
| hoy (sin frenos) | −89,2 % | −98,9 % (4/10 ruinas) | −100,0 % (10/10 ruinas) |
| todo o nada dd=5 % | −72,7 % | −80,1 % | −85,4 % |
| **gradual dd=5 %** | **−4,9 %** | **−4,8 %** | **−4,4 %** |
| todo o nada dd=10 % | −82,1 % | −93,2 % | −96,5 % |
| **gradual dd=10 %** | **−9,9 %** | **−9,8 %** | **−9,7 %** |
| CVaR ≥ −0,30 R | −68,2 % | −89,9 % | −99,0 % (5/10 ruinas) |

Tres cosas que hay que decir de esta tabla:

- **El banco no es el libro en vivo.** Toma TODAS las ideas de TODAS las estrategias, sin los
  vetos del perfil, sin pesos de retroalimentación, sin cupos y con tamaño por geometría
  declarada: 2 883 operaciones por pliegue frente a las 346 que el libro en vivo lleva cerradas.
  Es la cota superior de actividad, no una previsión de la corrida de T31. Y la simulación del
  capital es **secuencial**: una operación detrás de otra en orden de cierre, sin posiciones
  solapadas ni margen. Vale para comparar frenos entre sí, que sufren todos la misma
  aproximación, no para pronosticar la curva de un perfil.
- **El freno gradual con tramo 0 es en la práctica un interruptor de apagado**, no un freno: el
  máximo solo sube, y si la cuenta no recupera no se vuelve a operar. Con un sistema de E[R] < 0
  eso es lo correcto, y por eso sale mejor que el de hoy; pero hay que llamarlo por su nombre.
  El freno de hoy sigue perdiendo precisamente porque **reinicia el máximo** y reanuda.
- **Los dos límites de CVaR pre-registrados son inalcanzables.** El CVaR 95 % real es −1,3499 R y
  la rejilla de S3 pide −0,30 y −0,50 R, así que el límite está activo siempre y se convierte en
  un recorte fijo del tamaño. Se informa tal como se pre-registró; corregirlo exige una **versión
  nueva** del pre-registro (E12), no un ajuste aquí → BACKLOG.

### Comprobación del ES (E12, Acerbi y Székely)

`eim/paper/exits/es_check.py` con su contraste **Z2**: se estima VaR y ES 95 % en el tramo de
ajuste y se contrasta con la cola del tramo de prueba. Z2 negativo = la cola real es peor que la
prevista. Nulo por bloques de día del propio tramo de ajuste, no la distribución predictiva del
artículo: es menos exigente y se declara.

**En 2 de los 10 pliegues el ES se queda corto** (pliegues 5 y 6, p = 0,0002: previsto −1,32 R,
realizado −1,40 y −1,43 R). Es decir: un límite de CVaR calibrado con el pasado da falsa
seguridad en uno de cada cinco trimestres. Es justo lo que E12 quería saber antes de fiarse de un
límite de cola.

## 4. Kelly fraccionado sobre el límite inferior del IC (entregable 5, E10)

`eim/paper/kelly.py`. Para apuestas pequeñas, maximizar E[log(1 + f·R)] da `f* ≈ E[R]/E[R²]`;
aquí E[R] se sustituye por su **límite inferior** y se multiplica por ¼ (Kelly fraccionado).

| | Valor |
|---|--:|
| n (fuera de muestra) | 29 828 |
| E[R] | −0,1538 R |
| error estándar agrupado por día | 0,0052 |
| **límite inferior (z = 1,96)** | **−0,1640 R** |
| E[R²] | 0,3203 |
| **riesgo por operación** | **0,0000 %** |

La prueba que pide la aceptación de la ficha está en
`tests/paper/test_kelly.py::test_zero_whenever_the_lower_bound_is_not_positive`, con la escalera y
con la mejor variante de T134 entre los casos, **y con una media positiva pero sin evidencia**
(+0,004 R con error 0,011), que es el caso que justifica E10: Kelly sobre la media habría dado
tamaño; sobre el límite inferior da 0.

## 5. Tamaño por volatilidad objetivo (entregable 3, opcional): medido y NO adoptado

Con la σ versionada de T132 (`harrv_1m`, cobertura 94,8 %):

| Caso | Peso mediano | E[R] | Desv. típica de R | CVaR 95 % |
|---|--:|--:|--:|--:|
| sin escalar | 1,00 | −0,1538 | 0,5446 | −1,3499 |
| objetivo 0,5 y 1,0 (pre-registrados) | 4,00 | −0,6153 | 2,1785 | −5,3998 |
| objetivo = σ mediana (sin parámetro libre) | 1,00 | −0,1581 | 0,5619 | −1,5669 |

Dos hallazgos:

- **Los objetivos pre-registrados no están en las unidades de esta σ.** La σ versionada es
  relativa por vela (mediana 0,00247) y los objetivos de la rejilla son 0,5 y 1,0, así que el
  multiplicador se queda en el tope (×4) en el 100 % de las operaciones y la fila no mide nada.
  Corregir las unidades exige una versión nueva del pre-registro → BACKLOG.
- **Con el único objetivo sin parámetro libre, escalar por volatilidad empeora las tres cifras**
  (esperanza, dispersión y cola). Tiene sentido: los stops de las ideas no están puestos en
  unidades de σ, así que dividir el tamaño por σ añade varianza en vez de quitarla. La práctica
  institucional de §2.3 supone que la distancia al stop ya va en σ, y aquí no va. **No se adopta.**

## 6. Deslizamiento del stop medido contra el libro capturado (entregable 6, E4b)

`eim/paper/slip_check.py` + `scripts/t136_deslizamiento.py`. Es **prospectivo**: solo mide stops
posteriores al inicio de la captura HFT. Para cada stop del bróker simulado con cobertura, busca
en el `bbo` guardado el primer instante de su vela en que la punta del libro alcanzó el nivel del
stop, y compara el deslizamiento que supuso el modelo con el que daba el libro. Convenio:
**positivo = peor para el operador**; un largo cierra vendiendo y se cruza contra el bid.

**Cobertura.** La captura va de 2026-10-28T23 a 2026-11-04T18 (122 h). De las 346 operaciones
cerradas en vivo, todas por stop, 129 caen en horas con captura: **114 se midieron** y en las otras
15 el libro no llegó al nivel del stop.

| pb (positivo = peor) | Mediana | Media | p90 |
|---|--:|--:|--:|
| Real, según el libro | 2,08 | 5,02 | 14,35 |
| Modelo de costos | 5,70 | 6,10 | — |

**Veredicto con la regla declarada** (falla si se queda corto en más de la mitad de los stops):
**el modelo aguanta.** Se queda corto en 32 de 114 (28 %), y la diferencia mediana, real menos
modelo, es −2,53 pb.

**La cola no la cubre.** El peor caso son **77,4 pb reales frente a 17,1 del modelo** (Moderado,
BTCUSDT 1 h, `base_tendencia`), y 17,1 es además el máximo del modelo en toda la muestra. En
promedio el modelo sigue cubriendo el costo, pero un stop concreto puede costar 4,5 veces lo
supuesto.

**Parte de la muestra es cota por abajo.** En el 17 % de los medidos (19 de 114) la mejor punta no
aguantaba la cantidad, así que esos stops costaron más de lo medido. Saber cuánto exige recorrer
`depth`, y no se hizo.

**La hora incompleta no afecta al resultado.** La hora 18 UTC del 2026-11-04 salió incompleta
(libro útil 98,39 %, 18 silencios): coincide con la primera versión de `t136_deslizamiento.py`, que
llevó la memoria a 10,2 GB antes de arreglarse. Ninguno de los 114 stops medidos cae en esa hora.

**No se cambia el modelo de costos.**

## Lo que T136 no hace, y se dice

- **No cambia ningún perfil.** Todos los interruptores salen apagados y hay una prueba que lo fija
  (`test_off_by_default_in_every_profile`, `test_off_by_default_everywhere`).
- **No elige salidas.** Eso lo cerró T134; aquí la salida es la vigente y nada más.
- **No crea ventaja.** Ninguna de las cinco palancas vuelve rentable al sistema: la mejor deja la
  esperanza en −0,056 R. Lo que hacen es que el riesgo declarado sea verdad y que la falta de
  ventaja no se coma la cuenta.
- **No mide 15 m**, que es donde el costo pesa más, porque el banco de T131 no lo lleva.
- **El Kelly y el freno gradual no se encienden** aunque la evidencia los respalde: encender el
  Kelly dejaría a los perfiles sin abrir una sola operación y pararía la corrida de T31 y el A/B
  de T130. Esa es la ◆ del usuario.

## ◆ Preguntas al usuario

1. **¿Se enciende `risk_includes_costs`?** Hace verdadero el riesgo declarado (−14,8 % de tamaño).
   Cambia todas las entradas de una corrida en marcha, así que conviene decidir si se hace ahora o
   al cerrar T31 (2026-11-27).
2. **¿Se aprieta el tope de costo a 0,08 R?** Mejora E[R] de −0,118 a −0,056 R y deja fuera el
   89 % de las operaciones. Es el mismo hallazgo que el SL inicial de T134, visto desde el costo.
3. **¿Se cambia el freno de hoy por el gradual?** El de hoy reinicia el máximo y reanuda; el
   gradual, con tramo 0, apaga y no vuelve. Es la diferencia entre perder el 96 % y el 10 % por
   trimestre en el Agresivo.

Lo que **no** se pregunta: encender el Kelly. Con el sistema de hoy equivale a parar la operación
en papel, y eso es una decisión sobre T31, no sobre T136.

## Siguiente paso

La fase 22 queda cerrada: T130–T134 y T136 hechas, T135 aparcada por la ◆ de T134. El frente
siguiente es la **entrada** —T27 (puerta de edge) y T49 (versiones de estrategia, donde encaja el
SL inicial más amplio de T134)—, que es donde cinco mediciones independientes de esta fase dicen
que está el problema.
