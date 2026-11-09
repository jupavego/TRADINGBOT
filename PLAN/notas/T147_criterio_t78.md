# T147 — El criterio de T78: qué se cambió, qué se midió y qué dice el veredicto

**2026-11-09, `juanpablo-cpu`.** Modo SIMULADO. Esta nota es el entregable 5 de `PLAN/T147.md`:
la recalificación de todas las horas auditadas con la regla corregida y el veredicto que sale,
sin maquillar.

## 1. Qué se cambió

| | Antes (T126 + T138) | Ahora (T147) |
|---|---|---|
| Hora completa | libro útil ≥ 99 % **y** `bbo` ≥ 99 % **y** cadencia de `mark` ≥ 99 % **y** 0 huecos sin detectar | libro útil ≥ 99 % **y** 0 huecos sin detectar **y** top-10 ≥ 99 % |
| Aceptación | 72 horas completas **seguidas**; una hora al 98,x % la mandaba a cero | **ventana** contigua de ≥ 72 h con ≥ 99 % de horas completas, 0 huecos sin detectar y ≥ 99 % de top-10 |
| Despliegue | reiniciar costaba la corrida entera | horas de **mantenimiento declarado**: no cuentan ni cortan |
| Causa | no se distinguía | cada hora incompleta queda en «nuestra», «ajena», «mantenimiento» o «sin causa» |

Dos cosas que conviene leer juntas. La primera: **el top-10 entra ahora en la regla por hora, y
antes no estaba.** El documento lo pedía desde el principio y el código solo lo miraba al final,
sobre la racha entera; ahora una hora cuyo libro no coincida con el snapshot REST es incompleta por
sí sola. La segunda: **`bbo` y la cadencia de `mark` dejaron de vetar.** Miden presencia de
mensajes por segundo —actividad del mercado y silencios del exchange—, no si nuestra captura
funcionó, y §Aceptación de `T78.md` nunca los pidió. Se siguen calculando y publicando igual.

**Lo que no se tocó:** ningún hueco sin detectar y ≥ 99 % de coincidencia top-10. Son las dos
condiciones que garantizan que el dato sirve y en 233 horas no han fallado ni una vez.

## 2. La recalificación

`python -m eim.data.collectors.hft_ops --root data --requalify 2026-10-28T23 --apply`, 9 s.
**233 horas recalificadas, las 233 en versión 3** (antes: 217 en versión 1 y 15 en versión 2, con
la recalificación de T138 pendiente desde el 5 de noviembre). Cada JSON conserva su veredicto
anterior en `requalified.complete_before`, así que se puede auditar el cambio hora a hora.

**Tres horas cambian de veredicto**, y las tres son las que la regla vieja tiraba por `bbo` o por
`mark` teniendo el libro y el top-10 intactos:

| Hora | Libro útil | `bbo` | `mark` (cadencia) | top-10 | Huecos sin detectar | Antes → ahora |
|---|---|---|---|---|---|---|
| 2026-11-06T00 | 100,00 % | 100,00 % | 95,92 % (medida vieja) | 100 % | 0 | incompleta → completa |
| 2026-11-06T14 | 99,17 % | 98,53 % | 98,63 % | 100 % | 0 | incompleta → completa |
| 2026-11-08T01 | 99,86 % | 98,31 % | 99,39 % | 100 % | 0 | incompleta → completa |

Ninguna otra hora se mueve: las 36 restantes que estaban incompletas lo siguen estando, con la
misma cifra de libro útil. La recalificación **no salva** ninguna hora caída.

## 3. El veredicto: T78 todavía NO se cumple

```
rule: ventana (T147) · need_h: 72 · passed: false · remaining_h: 20
best = current: 52 h, 2026-11-07T06 → 2026-11-09T09
  horas completas 52 de 52 (100 %) · top-10 100 % · huecos sin detectar 0
  libro útil agregado 99,973 % · peor hora 2026-11-08T02 (99,36 %)
```

**Faltan 20 horas.** Si la ventana viva aguanta, T78 se cumple al cerrar la hora **2026-11-10T06
UTC**. Es una fecha creíble, no como las anteriores: la ventana lleva 52 horas sin una sola hora
incompleta, y ya no hace falta que las 72 sean perfectas, solo el 99 % de ellas.

Con la regla vieja la lectura de hoy era de 31 h. La corregida da 52 h: 21 horas más, que son
exactamente las que destrabaron las tres horas recalificadas al unir tramos. La racha de T126 y la
ventana coinciden ahora mismo (52 h las dos) porque el tramo vivo no tiene ninguna hora incompleta;
en cuanto haya una, la racha volverá a cero y la ventana seguirá contando. Ese es el cambio.

## 4. De quién es cada hora perdida

| Desde | Nuestra | Ajena | Sin causa |
|---|---|---|---|
| 2026-10-28T23 (todo) | **53** | 27 | 1 |
| 2026-11-02T00 | 8 | 11 | 0 |
| 2026-11-06T00 | 0 | **3** | 0 |

Las 53 horas «nuestras» están casi todas antes del 2 de noviembre: el apagado forzado del 31 de
octubre, las horas sin ningún JSON porque no había servicios y la saturación del equipo. Eso es lo
que arreglaron T126, T140, T141 y T142, y se nota: **desde el 6 de noviembre no hay ni una hora
perdida por causa nuestra.** Las 14 horas incompletas desde el 2 de noviembre son, salvo tres con
un reinicio de por medio, silencios y desconexiones de Binance (`silencio`, `desconexion`), con
hasta 74 tramos marcados en una sola hora (2026-11-05T07).

La tasa de horas incompletas va bajando sola: 16,7 % en todo lo auditado, 8,1 % desde el 2 de
noviembre, 6,9 % desde el 4, 3,7 % desde el 6 y **1,7 % desde el 7** (1 hora de 58).

## 5. Lo que este cambio deja expuesto

**Una pérdida prolongada de `bbo` o de `mark`, ella sola, ya no hace incompleta la hora.** Hoy no
hay ningún caso así: entre las horas que ahora cuentan como completas, la peor cobertura de `bbo`
es 98,31 % (2026-11-08T01) y la peor cadencia de `mark`, 98,63 % (2026-11-06T14). La exposición
real es de 1,7 puntos, no de un flujo caído. Pero la regla, tal como quedó, aceptaría una hora con
media hora sin `mark` si el libro y el top-10 estuvieran intactos. Poner un suelo bajo (del orden
del 95 %, que veta la caída y no el roce) es una línea de código y **no se hizo porque no es lo que
T147 aprobó**: queda en `BACKLOG` T147 (1) como ◆ del usuario.

## 6. La lectura alternativa, medida y no adoptada

El tramo vivo tiene un **libro útil agregado del 99,973 %** con la peor hora en 99,36 %. Si T78 se
juzgara por cobertura agregada con un suelo por hora —en vez de por recuento de horas completas—,
ya estaría cumplida y lo estaría desde hace días. **No se adopta.** Cambiar el criterio para que dé
el resultado que uno quiere es lo que el F0 prohíbe, y la ventana del entregable 2 es la lectura
del documento, no una elegida por su resultado. Queda escrito aquí porque es una cifra real y
porque la decisión, si alguna vez se toma, es del usuario y no de esta tarea.

## 7. Qué hacer ahora

- **No marcar T78 ☑**: faltan 20 horas. Se lee con
  `python -m eim.data.collectors.hft_ops --root data --window`.
- **Antes de desplegar T123 y T124**, declarar sus horas:
  `--maintenance <desde> <hasta> --nota "despliegue de T123 y T124"`. Ya no cuesta la ventana.
  Declararlo después de un corte imprevisto, para salvar una ventana, sería falsearla: la
  declaración guarda el instante en que se hizo.
- **El vigilante sigue con el código viejo** y escribirá sus JSON en la versión anterior hasta que
  se reinicie. Mientras tanto, recalificar antes de leer (es idempotente y no necesita los crudos).
