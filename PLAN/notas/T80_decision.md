# T80 ◆ — Decisión: el carril HFT se archiva

**Fecha:** 2026-11-20 · **Quién:** Claude, por delegación expresa del usuario («toma tú la mejor
decisión», tras leer el veredicto). **Evidencia:** `v2/reports/hft_ceiling.{md,json}`, pre-registro
`eim/hft/prereg/hft_ceiling_v1.json` (congelado antes de medir, SHA-256 fijado en el código).

## La decisión

**Se archiva el carril de alta frecuencia**, con el resultado honesto, como se hizo con T28. Se
cierran sin hacer **T79** (simulador a nivel de libro), **T81** (modelos), **T82** (estrategias),
**T84** (torneo y puerta `hft_v1`), **T85** (microestructura v2 en vivo) y **T86** (integración).
T83 (riesgo y ejecución de baja latencia) ya estaba hecha y se queda como está: su motor de veto es
genérico y no depende de este carril.

No se redirige. Las tres redirecciones posibles se descartan con razón, no por cansancio:

| Redirección | Por qué no |
|---|---|
| Horizontes de 5–30 min | A esos horizontes ya no es alta frecuencia: es el horizonte que cubren los agentes que ya existen, y el hallazgo útil de T80 va ahí (abajo), no a T81–T85 |
| Comisión VIP con rebate de maker | Exige volumen real y dinero real: choca con la ◆ D de T145 (solo análisis) y con la regla de no operar sin la puerta de edge y semanas de papel |
| Otro símbolo | T78 solo capturó BTCUSDT; empezar de cero, y el alcance del proyecto es BTC |

## Por qué, con los números

El veredicto del informe es NO SUPERA. Lo que lo hace **definitivo** y no un «falta muestra» son
tres cosas del detalle, que miran en la misma dirección:

1. **La mejor señal nunca alcanza el costo.** `depth_imb` es la más sólida: IC de Spearman 0,0618 a
   30 s y 0,0438 a 60 s, las dos con p de Holm < 0,02 sobre los 68 intentos, y el mejor acierto
   balanceado de la tabla (0,524). Hace **cero operaciones en los tres estilos de ejecución**: su
   predicción calibrada no llega a 4 pb ni una vez en 1,33 M de cubos. Esto **no es un problema de
   potencia**: es de magnitud, y más días no agrandan el movimiento previsto.
2. **Donde hay potencia, el neto es negativo.** La señal con más operaciones, `ofi_top_30` a 30 s,
   hace 151 / 254 / 384 operaciones en taker / mixto / maker y pierde **−26,06 / −13,90 / −8,71 pb**
   por operación. El subconjunto mejor medido del experimento pierde dinero.
3. **Lo que parece positivo no tiene de dónde salir.** El mejor neto de la tabla, `spread_bps` a 30 s
   en taker, son **+13,8 pb sobre 18 operaciones en 5 de 12 días**, con IC 95 % de −1,21 a +28,93 y
   **acierto balanceado 0,5017**. Una señal que acierta la dirección el 50,2 % de las veces no puede
   tener un neto real de +13,8 pb: esa media la fabrican dos episodios grandes. Elegirla después de
   ver la tabla es exactamente la pesca que el marco de T80 se construyó para impedir.

De fondo, la aritmética: el edge bruto por operación es de 0,05–0,16 pb (0,1–1,0 pb si solo se opera
el decil de predicción más fuerte) frente a **4 pb** del ida y vuelta maker-maker, el más barato que
existe en VIP 0. El acierto balanceado de la dirección **neta de costos** está entre 0,500 y 0,524 en
toda la tabla. Sí hay movimiento que paga a 30–60 s (28–41 % de las ventanas en maker con previsión
perfecta), pero nada de lo medido sabe **cuáles** son esas ventanas con la antelación suficiente.

## Consecuencia para el disparador de 2027-10

`BACKLOG` T145 (4) decía: «A en 2027-10: con un año de libro L2 propio, valorar abrir T80 con
pre-registro». **Ese disparador queda contestado y se retira como estaba escrito.** La razón es el
punto 1: la restricción que manda es de magnitud, no de muestra, y un año de datos no la mueve. Si
alguna vez se reabre, la condición tiene que ser otra —algo que cambie el cociente costo/bruto, es
decir una estructura de comisiones distinta o un horizonte donde el peaje de 4 pb sea marginal— y no
«más días». La corrida es barata de repetir: una versión nueva del pre-registro y
`python -m eim.hft.ceiling_run`.

## Lo que sobrevive y dónde va

Dos cosas de T80 valen fuera del carril, y van al BACKLOG, no a tareas nuevas (no se amplía alcance):

1. **`depth_imb` y `tilt_bps` baten a la línea base del agente `microstructure` v1 en los cuatro
   horizontes**, con Holm. Más llamativo: la línea base v1 pierde significancia pasados los 5 s
   (IC 0,0116 a 30 s y 0,0078 a 60 s, ninguno significativo) mientras ellas la mantienen (0,062 y
   0,044 a 30 s). Es una mejora medible del agente que ya existe, en el terreno del análisis, que es
   donde T145 D puso al sistema.
2. **El marco y el panel quedan en pie**: `eim/hft/features/`, `eim/hft/evaluation/`, el panel de
   `data/collectors/hft_panel.py` y `book_fast.py` (top-N en tiempo constante, útil a cualquier cosa
   que reproduzca el libro). Nada de esto se borra: es lo que hace barata cualquier remedición.

## La captura de T78: medido el 2026-11-20, se queda como está

Al cerrar el carril, la captura dejó de tener consumidores y quedó la duda de bajar su retención de 45
a 30 días, que es lo que `BACKLOG` T78 (8) había anotado «tras T80, **si hace falta**». El usuario
delegó también esta decisión. Medido antes de decidir: el resumen de QC da **435,5 GB libres** y una
proyección de **51,8 GB a 45 días** (12 %), con 21,8 GB ocupados hoy. El «81 GB libres» que motivaba
la nota ya no es el equipo que hay.

**Decisión: no se toca.** La condición no se cumple, y el cambio no es gratis: reiniciar la captura es
exactamente lo que ha costado ventanas enteras en este proyecto (T147 y T148, de ahí que los
reinicios haya que declararlos con `--maintenance`). Gastar ese riesgo para liberar disco que no falta
es un mal cambio. Y los 45 días son el único libro L2 propio, que es justo lo que querría el único
consumidor que queda: `depth_imb` y `tilt_bps` en el agente `microstructure`. Se revisa solo si
`free_gb` baja de ~100 GB.

**`data/hft_panel/`** (0,1 GB) se puede borrar cuando se quiera: es derivado y se reconstruye en
≈ 1 h 36 min por la cola.

**Observado de paso, sin tarea nueva:** la ventana viva de 72 h está al 86,1 % (62 de 72 horas
completas), lejos del 99,2 % con que T78 cerró; su mejor ventana auditada (148 h al 99,32 %) sigue
siendo la del expediente. El ciclo lento de hoy a las 08:00 UTC ocurrió **con el equipo en reposo**
(top de CPU: System, explorer, svchost; ninguna carga ajena), así que no es presión de trabajos
pesados. Anotado en `BACKLOG` T78; con el carril archivado nada depende de ello.
