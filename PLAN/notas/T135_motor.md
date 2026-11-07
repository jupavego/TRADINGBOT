# T135 — Motor de gestión de la posición: construido y apagado

**Actualización (2026-11-07):** el usuario reabrió T135 para medir M8, y eso va aparte del motor, que sigue apagado: `PLAN/notas/T135_ab_m8.md`.

**Estado:** ◐. El motor está hecho y probado (entregables 1 a 4 y el cálculo de potencia del 5). **El A/B no ha empezado y no puede empezar:** no hay ninguna salida aprobada que comparar.

## Por qué se hizo sin salida aprobada

La ficha dice «solo si T134 aprueba», y T134 rechazó las 87 variantes. Además, el usuario cerró la línea de apartar el stop tras T137, así que `M8 q=0.95` y `S1` tampoco son candidatas. El 2026-11-06 el usuario pidió empezar T135 de todos modos, siempre que no interrumpiera lo que estaba corriendo. Se resolvió así:

- **Se construye lo que no depende de elegir una salida:** el motor es genérico y sirve para cualquier política que algún día se apruebe.
- **No se enciende nada:** ningún perfil lo usa, y hay una prueba que lo fija.
- **No se empieza el A/B:** su criterio exige una salida aprobada y una potencia calculada con el efecto de esa salida.

Lo único que el motor habilita ya es medir M2–M7 en el libro completo si alguien lo pide, que es lo que BACKLOG T134 (2) dejaba sin medir.

## Qué se comprobó que no cambia

Mirado contra `main` con `PYTHONHASHSEED=0`:

| Huella | Resultado |
|---|---|
| `params_fingerprint` de los 4 perfiles | idéntica |
| Volcado JSON de los 4 perfiles | idéntico |
| Versiones de T49 (111 `estrategia@marco`) | idénticas |

Esto importa porque la solución obvia lo habría roto. Un campo `adaptive` nuevo en `ProfileParams` añade `"adaptive": null` al volcado y cambia la versión de los cuatro perfiles, y meter la salida en `exec_fingerprint` cambia las 111 versiones y parte la evidencia de T49. Por eso `adaptive` se omite del volcado cuando no hay política, y `version_of` solo añade la clave `exit` si se le pasa.

## Cómo está hecho

- **`eim/paper/adaptive_params.py`:** `AdaptiveParams`, con M2, M3, M5, M6 y M7. Sin S1 ni M8: cambian el SL inicial y con él el tamaño que ya decidió la autoridad, además de estar en la línea cerrada.
- **`eim/paper/adaptive.py`:** construye la política, abre la posición y añade lo que el libro lee: stop en USDT, fase, motivo, fuente y versión.
- **`eim/paper/exits/trail.py`:** el motor de T132, el mismo que midió T134. Ahora acepta el suelo del diario con las funciones de `ladder_floor.py`. Sin `guard` no cambia nada.
- **`exit_mode="adaptativo"`, modo `adaptive_stop` en la autoridad de T114.** `TIEMPO` y `HTF` solo cierran en la política que los pre-registra (M6 y M7); en el resto son violación y no se ejecutan.
- **Diario T110 sin columnas nuevas:** fase, motivo, fuente y versión van en el JSON `history` de cada fila. Un arrastre que aún no cruzó la entrada es `abierta`, no `protegida`: con `active=True` el diario la leería como corrupta (`problem()`: «stop protegido en la entrada o peor»).
- **Interfaz:** bloque «Salida adaptativa» en «Perfiles», con modo, fase, stop vigente, motivo, fuente, y σ con su cobertura. No aparece mientras ningún perfil la use.
- **Potencia (E9):** `exits/power.py` y `scripts/t135_potencia.py`. Reproduce las 315 operaciones de T134 y `write_plan` se niega a reescribir un plan confirmado con otro contenido.

## Revisión de código (nivel alto, la que pide la ficha)

Diez hallazgos. **Corregidos, con prueba:** `check_profiles` no cubría a los perfiles adaptativos; `sigma` no se validaba al construir; el peso aprendido no tenía el tope `max_weight` de la escalera; un plan de potencia editado a mano pasaba por bueno; el panel enseñaba σ en M6 y M7, que no la usan, y no decía la fuente de `htf_dir`. **Sin corregir, a propósito:** ver abajo y BACKLOG T135.

## Lo que falta para cerrar T135

1. **Una salida aprobada por los criterios de §5.4.** Hoy no la hay.
2. Con ella: calcular la potencia con el ritmo del libro en vivo y confirmar el plan **antes** de la primera operación.
3. El A/B en papel de ≥ 4 semanas con su informe semanal. No se construyó: sin candidata, sus decisiones serían suposiciones.
4. Conectar `version_of(..., exit_policy=...)` con la evidencia del A/B en `ab_gate.py`. Hoy la función existe y está probada, pero nadie la llama: T49 mide la sombra, que no cambia de salida.

## Limitaciones que hay que saber

- **Sin prueba con datos reales.** El libro se probó con velas sintéticas y costos cero. El motor de arrastre sí corrió sobre datos reales en T134, pero la unión con el libro y el diario no.
- **La captura de la interfaz es con datos de prueba,** porque ningún perfil genera datos reales. El criterio de aceptación pide una captura; esta muestra el panel, no una operación real.
- **Coste por consulta:** con un perfil adaptativo, los rasgos se recalculan en cada vista sobre todo el camino. Hoy no ocurre. Antes de encender uno hay que medirlo en este equipo.
- **Anticipación en las velas ambiguas, heredada de T132:** `_sub_bars` usa σ y swing de una vela que aún no ha cerrado. Corregirlo cambiaría las cifras de T134, así que queda en BACKLOG hasta decidir si se rehace aquella medición.
- **M7 mira un solo marco mayor por camino** (el de 15 m, 1 h), también para ideas de 1 h y 4 h. Es lo mismo que midió el banco.
- **Un A/B de libro contra M0 no tendría las mismas entradas:** el veto `viability` solo existe en la escalera, porque depende de su primer escalón. El tamaño sí es comparable, con el mismo tope de peso. La comparación limpia es la emparejada de `ab_pairs.py`, sobre las mismas ideas.
- **La huella de un perfil cambia entre procesos,** desde antes de T135: `families` es un `frozenset` y su orden depende de `PYTHONHASHSEED`. Por eso la comparación de arriba se hizo con la semilla fija. BACKLOG T135.
- **`REASON.SLD`** dice «SL dinámico (escalón)» en listas como la del libro fijo, aunque el cierre sea de un arrastre. La tabla principal muestra el motivo correcto.
