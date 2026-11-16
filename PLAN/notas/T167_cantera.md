# La cantera: perfiles propios por agente, medidos hacia adelante (fase 27)

Pedido del usuario (2026-11-11): un «criadero, guardería, casa de talentos o campo de
entrenamiento» donde **cada uno de los 19 agentes** desarrolle **sus propios perfiles de inversión**
con su propia información, sus teorías y sus patrones de decisión (el de medias móviles con sus
medias; el técnico con lo suyo), **no un algoritmo genérico igual para todos**, y que esos perfiles
operen en un campo de entrenamiento para ver, como una casa de talentos, cuáles podrían tener éxito
en la vida real, sabiendo que lo más exitoso no tiene por qué ser lo más complejo. Pidió conjugarlo
con todo lo aprendido y con la bibliografía estudiada.

**Modo: SIMULADO.** Cada perfil opera de forma simulada e interna, **sobre el mercado real en
vivo** (el mismo precio de Binance que usa el bróker), y **su efectividad se mide por la
rentabilidad neta que deja** su propia cuenta simulada (aclaración del usuario, 2026-11-11). No hay
dinero real en juego ni se cambia la corrida oficial de T31.

## 1. Lo que hay hoy (y por qué no basta)

- Los agentes entran al bróker simulado de una sola forma, la misma para todos:
  `agente_{id}` en `v2/eim/paper/strategies_ind.py` («sigue al agente si |sesgo| ≥ umbral y
  confianza ≥ umbral; SL 1,5 ATR, TP 2,5 ATR»), y solo 8 de los 19. Es exactamente el algoritmo
  genérico que el usuario no quiere: reduce cada agente a un número (sesgo) y tira lo que sabe.
- El contexto que guarda el bróker por vela solo trae `[sesgo, confianza, estado]` de cada agente
  (`v2/eim/paper/context.py`). Las 44 variables FRM del agente `ema` (pila, compresión, rebotes,
  cruces, elasticidad…) no se guardan, así que hoy ningún perfil podría usarlas.
- Hay estrategias de indicadores (`ind_cruce_ema`, `ind_rsi`…) que calculan sus reglas desde las
  velas, sin pasar por el agente.

## 2. Lo que ya sabemos y la cantera tiene que respetar

1. **No hay ventaja direccional medida.** T27, T137, T139 y la calibración (W45) coinciden; el
   usuario eligió **D, solo análisis** (T145). La búsqueda de entradas en la historia se cerró con
   P1 (T139): la lectura limpia de la historia **ya está gastada**.
2. **Multiplicar intentos sin control es lo que hundió las entradas** (T139; memoria de automejora).
   Una casa de talentos con cientos de perfiles encontraría «campeones» por puro azar.
3. **Los costos se comen lo intradía.** En VIP 0, las reglas horarias pagan del orden de
   0,1–0,3 R por operación (T136/T137); V6 de T49 exige ≤ 0,3 R.
4. **El problema está en la entrada, no en la salida** (fase 22): la cantera no prueba salidas;
   cada perfil usa una plantilla de salida fija y común a su familia.
5. **Precedente de familia propia:** T160 abrió una familia de Holm propia (2 intentos) porque sus
   hipótesis eran de otra naturaleza. Aquí la razón es otra y más fuerte: **los datos son nuevos**
   (solo hacia adelante, posteriores al pre-registro), no la historia ya mirada.
6. **Potencia:** con σ ≈ 1 R por operación, detectar +0,10 R pide ≈ 600 operaciones; +0,25 R,
   ≈ 100. En 6 meses (la regla de plazo de T145) la cantera solo puede **descubrir talentos
   grandes** y, sobre todo, **descartar** con rapidez. Eso hay que decirlo desde el primer día.

## 3. La idea, en una frase

Cada agente propone **pocos perfiles nativos** (≤ 4), escritos desde **su propia teoría y sus
propias variables**, con parámetros **canónicos de la literatura y sin optimizar**; se congelan en
un **pre-registro** y desde ese momento **operan solo hacia adelante**, con el precio real en
vivo, cada uno con **su propia cuenta simulada**, el mismo capital inicial, el mismo riesgo y los
mismos costos. **Se juzgan por la rentabilidad neta que dejan.** Un escalafón fijado de antemano
los asciende o los da de baja, y **a empate gana el más simple**.

### La medida: rentabilidad neta, con una vara contra la suerte

- **Cuenta propia por prospecto:** capital inicial igual para todos (p. ej. 10 000 USDT
  simulados), saldo que crece o se reduce con cada operación cerrada, comisiones, deslizamiento y
  funding descontados. Se publican su **rentabilidad neta acumulada (%)**, su curva de capital, su
  drawdown máximo, el número de operaciones y el % de acierto.
- **Iguales condiciones:** mismo capital, mismo riesgo por operación (1 %) y mismos costos para
  todos; así la diferencia de rentabilidad sale de la regla del perfil y no del tamaño.
- **Por qué no basta el número a secas:** con 40–50 perfiles, varios ganarán un 5–10 % en un mes
  por pura suerte. Por eso la rentabilidad de cada perfil se compara siempre con la que deja, en
  las mismas fechas, el **perfil que opera al azar** y con **comprar y mantener**; un perfil asciende
  cuando su rentabilidad supera a la que el azar explica, no cuando encabeza la tabla una semana.
  Internamente esa vara se calcula en R (ganancia por unidad de riesgo), que es lo que permite las
  pruebas estadísticas; hacia fuera se muestra en rentabilidad.

### Qué es un perfil (un «prospecto»)

`prospecto = agente@versión · regla nativa · marco · plantilla de salida · huella`

- **Regla nativa:** función pura sobre las variables que el agente ya calcula (no sobre su sesgo
  agregado). Sin red, sin disco, sin estado global, como los agentes.
- **Marco y horizonte:** 15 m, 1 h o 4 h, y cada prospecto declara su **banda de horizonte**
  (abajo). Los de 15 m solo siguen si el examen físico demuestra costo ≤ 0,3 R.
- **Plantilla de salida:** una de pocas fijas (stop por ATR con la escalera vigente; salida por
  regla contraria; tiempo máximo). No se prueban salidas: eso ya se cerró.
- **Riesgo:** 1 % fijo del capital de su cuenta por operación (perfil Moderado), para que todos compitan igual. Los estilos
  Conservador/Agresivo/PPP se muestran como **lentes** sobre los graduados (T156), no como
  prospectos nuevos que gasten intentos.
- **Huella:** como las versiones de T49; cambiar una regla o un parámetro = prospecto nuevo, que
  empieza de cero y **suma un intento a la familia**.

### Horizontes: de scalping a semanal

Pedido del usuario (2026-11-11): que la cantera tenga perfiles de **scalping, intradía, tres días y
semanal**, no solo de mediano plazo. Cada horizonte se mide en su propia unidad, porque exigir
30 operaciones a un perfil semanal o 100 a uno de tres días lo condena por construcción.

| Banda | Marco | Tenencia típica | Unidad de medida | Cadencia mínima (T169) | Prospectos |
|---|---|---|---|---|---|
| **Scalping** | 15 m | ≤ 2 h (`max_bars` 4–8) | operación | ≥ 20 al mes y costo medio ≤ 0,3 R | 6 |
| **Intradía** | 15 m–1 h | < 24 h | operación | ≥ 8 al mes | 18 |
| **Tres días** | 1 h–4 h | 1–5 días | operación | ≥ 5 al mes | 11 |
| **Semanal** | 4 h | 1–3 semanas | **día** (rendimiento diario de su cuenta frente al de sus gemelos, con bootstrap por bloques) | en posición ≥ 30 % de los días | 8 |

- La banda sale de la plantilla de salida y del marco; **T169 mide la tenencia mediana real** en
  el banco y reasigna la banda mecánicamente, sin mirar rendimiento.
- «Sin opción a primer equipo» se mide en la unidad de cada banda: ≈ 100 operaciones en el plazo
  para scalping, intradía y tres días; ≥ 120 días con posición para semanal.
- **Scalping de verdad (segundos) no cabe aquí:** su escala es la clase A de T145. `microstructure`
  entra con dos prospectos de 15 m que solo operan con la captura completa (huecos ≤ 30 %). El scalping de la cantera es de velas de 15 m, con salida en
  menos de 2 h, y es la banda con más riesgo de baja por costo.
- **La puerta de costo** de `AUTO_ADAPT` está a 0,15 R en la corrida T143, y 15 m costó 0,158 R en
  T31 (auditoría T159): cerraría la banda de scalping antes de medirla. Se propone que la cantera
  use **0,3 R, el límite V6 de T49**, el mismo con el que T169 descarta; el mecanismo sigue siendo
  automático y el valor se fija en el pre-registro de T170 (◆).

### Reglas de la casa (el antídoto contra el azar)

1. **Presupuesto:** ≤ 4 prospectos por agente, ≤ 3 parámetros libres por prospecto y un techo de
   familia que se fija en el pre-registro (orden de 40–50).
2. **Hermano simple obligatorio:** cada agente inscribe un perfil **base** de 1–2 parámetros. Un
   perfil más complejo solo asciende si supera al base de su agente; a empate estadístico,
   asciende el simple («lo más exitoso no tiene que ser lo más complejo», escrito como regla).
3. **Teoría opuesta cuando exista:** si un agente admite lectura de tendencia y de reversión, se
   inscriben las dos; la cantera también sirve para saber cuál de las dos teorías se sostiene.
4. **Controles fijos, que no cuentan como prospectos:** **gemelos aleatorios pareados** (por cada
   operación real, K = 200 entradas de lado al azar en la misma vela, con la misma plantilla de
   salida y los mismos costos; la vara es la diferencia d_j entre la operación y la media de sus
   gemelos), comprar y mantener **en unidades de riesgo** y con desglose largo/corto, y el
   `agente_{id}` genérico de hoy. La pregunta «¿lo nativo supera a lo genérico?» queda respondida
   por agente (12 comparaciones, con Holm). Hipótesis primaria de cada prospecto: d_j > 0; las
   demás comparaciones son secundarias (§10, rec. 1, 14 y 15).
5. **La historia no asciende a nadie.** Solo se usa para el **examen físico** (T169): que el
   perfil opere, cuánto opera, cuánto le cuesta en R y que no mire el futuro. **No se calcula su
   rendimiento en la historia**, para no volver a gastar la lectura limpia ni sesgar el registro.
6. **Miradas fijadas:** la revisión es mensual con un **e-proceso por prospecto** sobre d_j y
   **e-BH a q = 0,10 sobre la familia** para entrar en Promesa (válido bajo cualquier dependencia y
   con miradas libres); la graduación a primer equipo usa **StepM de Romano-Wolf** en la mirada
   final, y el SPA solo como prueba de humo de toda la familia (§10, rec. 2 y 3).
7. **Nada asciende solo a dinero.** Graduarse permite, con ◆ del usuario, inscribir el perfil en el
   registro de T49 con su historial hacia adelante; T49 decide si se publica como sugerencia, y la
   decisión D (T145) sigue mandando sobre operar.

### Escalafón

| Etapa | Entra cuando | Sale cuando |
|---|---|---|
| **Guardería** | Pasa el examen físico y queda en el pre-registro | Llega a 30 operaciones (o 60 días si es lento) |
| **Cantera** | n ≥ 30 y no es claramente negativo | Asciende o se da de baja |
| **Promesa** | Rentabilidad neta positiva y **rechazado por e-BH (q = 0,10) frente a sus gemelos aleatorios**; ninguna operación aislada explica más del 40 % del beneficio neto (consistencia); si es complejo, supera a su hermano simple, y si su P&L diario tiene correlación > 0,7 con el hermano o con el `agente_{id}` genérico, solo asciende si aporta por encima de ellos | Cumple todo lo de primer equipo o deja de cumplir |
| **Primer equipo** | Criterios `cantera_v1` completos: **StepM de Romano-Wolf** en la mirada final, Sharpe deflactado con el **N efectivo** (prospectos agrupados por correlación) declarado junto al nominal, d_j con signo coherente en ≥ 2 regímenes, **orden persistente** entre los meses 1–3 y 4–6, drawdown y costo como V4–V6. El PBO/CSCV se informa como descriptivo, no decide | ◆ del usuario: **confirma o veta** la salida mecánica (no elige entre candidatos); inscribir en T49 |
| **Baja** | **Futilidad:** la cota superior del R neto frente a los gemelos queda por debajo de μ_mín = +0,10 R (pre-registrado); drawdown de su cuenta por encima del tope **calibrado por simulación** con la ventaja objetivo de +0,25 R (probabilidad de baja injusta fijada de antemano); sin operaciones en 60 días o fecha límite (6 meses) | Definitiva; **sigue contando en la familia** |

### Sensibilidad de los veredictos (decisión del usuario, 2026-11-11)

El usuario pide, el mismo día en que vio cerrarse **T166 y T163 «sin potencia»** (en T163 el MinTRL
pedía 12,62 años de historia y hay 5,85, así que ni se escribió el pre-registro), que los veredictos
de la fase 27 sean **muy sensibles**: que diferencias pequeñas de desempeño entre prospectos se
puedan **notar, evaluar, desarrollar y hacer evolucionar**. Una hipótesis confirmatoria sobre
historia fija y un vivero que mide hacia adelante no se juzgan con la misma vara.

1. **Dos capas, explícitas.** *Dentro* de la cantera, escalafón sensible: e-proceso por prospecto y
   e-BH mensual con **q = 0,10**, R encogido por el modelo jerárquico, persistencia del orden y
   contribución marginal. En la **puerta de ascenso a primer equipo** y en cualquier cosa que toque
   dinero, el criterio estricto ya diseñado (**StepM de Romano-Wolf**, T49) **sin aflojar un punto**.
2. **La sensibilidad se gana reduciendo varianza y subiendo n, no bajando el umbral:** gemelos
   aleatorios pareados sobre el mismo camino (la vara pareada, no una comparación suelta), las bandas
   de horizonte con scalping a 15 m (más operaciones al mes) y evidencia que **se acumula en el
   tiempo** (miradas libres de los e-procesos) en lugar de un n fijo.
3. **Nada de puerta de potencia estilo T163 para la cantera:** no se cierra un prospecto porque «no
   habría n suficiente». Se le deja acumular evidencia, o se le da de baja por **futilidad** frente a
   μ_mín, que es otra cosa: un veredicto con datos, no una negativa antes de empezar.
4. **Declarar el precio:** con q = 0,10 se esperan falsas promesas, así que el informe (T172) dice
   **cuántas se esperan** bajo la nula global, simuladas con los gemelos.

Casi todo esto ya estaba en el diseño (§3 arriba, §10 y `PLAN/T170.md`); la decisión lo confirma como
**intención declarada** y prohíbe endurecer el escalafón interno «por prudencia» en T170.

## 4. Los 19 agentes: expedientes verificados (T167, 2026-11-11)

Cerrado por T167. Cada agente tiene su expediente en `v2/eim/nursery/dossiers/<id>.json` con sus
variables y su fuente, la historia **comprobada** (no supuesta), la cadencia esperada, las obras
del catálogo T151 con su consenso T157 y sus prospectos. La prueba `v2/tests/nursery/test_dossiers.py`
fija la forma y las reglas de la casa. **No se calculó ningún rendimiento.** La historia decide
solo qué se puede **examinar** en T169; el rendimiento se mide siempre hacia adelante.

**Plantillas de salida** (fijas, comunes a la familia; no son parámetros de los prospectos):
`atr_ladder` (SL 1,5 ATR, TP 2,5 ATR y la escalera vigente: la misma salida que el `agente_{id}`
genérico, para que la comparación aísle la entrada), `rule_flip` (sale cuando la condición de
entrada se invierte o desaparece; SL protector 1,5 ATR), `mean_target` (objetivo en la media de
referencia, VWAP o EMA; SL 1,5 ATR; tiempo máximo = horizonte del agente) y `time_stop` (sale a
las velas del horizonte declarado por el agente; SL 1,5 ATR).

| Agente | Estado | Prospectos (**base** en negrita; marco, parámetros) | Historia para T169 |
|---|---|---|---|
| `ema` | inscrito | **ema_pila** (4 h, 1) · ema_resorte (1 h, 2) · ema_retroceso (1 h, 2) · ema_elastico (1 h, 1, opuesta) | banco T131 |
| `technical` | inscrito | **tec_acuerdo_marcos** (1 h, 1) · tec_rsi_rango (1 h, 2, opuesta) · tec_ruptura_volumen (1 h, 1) · tec_compresion_bb (1 h, 2) | banco T131 |
| `vwap` | inscrito | **vwap_reversion** (15 m, 1) · vwap_tendencia (1 h, 1, opuesta) · vwap_semanal (4 h, 1) · vwap_anclado (4 h, 1) | banco T131 |
| `levels` | inscrito | **niveles_rebote** (1 h, 2) · niveles_ruptura (1 h, 1, opuesta) · niveles_canal_extremos (1 h, 1) · niveles_canal_tendencia (4 h, 1) | banco T131 |
| `structure` | inscrito | **estructura_continuacion** (4 h, 1) · estructura_ruptura (1 h, 1) · estructura_cambio (1 h, 1, opuesta) · estructura_retroceso (1 h, 1) | banco T131 |
| `price_action` | inscrito | **pa_bos** (1 h, 1) · pa_choch (1 h, 1, opuesta) · pa_patron_zona (1 h, 2) · pa_bos_patron (1 h, 2) | banco T131 |
| `elliott` | inscrito | **elliott_onda3** (4 h, 1) · elliott_onda5_giro (4 h, 1, opuesta) | banco T131 (probable descarte por cadencia) |
| `regime` | inscrito | **regimen_tramo** (1 h, 2) · regimen_tramo_estable (1 h, 2) | banco T131 |
| `literature` | inscrito | **lit_consenso** (1 h, 1) · lit_regla_4_semanas (4 h, 1) · lit_nison_giro (1 h, 1) · lit_murphy_rsi (1 h, 1, opuesta) | banco T131 |
| `derivatives` | inscrito | **deriv_funding_contrario** (4 h, 1) · deriv_oi_tendencia (1 h, 2, opuesta) · deriv_saturacion (1 h, 2) · deriv_largos_cortos (4 h, 1) | funding: banco; OI y largos/cortos: solo adelante |
| `liquidations` | inscrito | **liq_agotamiento** (15 m, 2) · liq_cascada (15 m, 2, opuesta) · liq_cascada_multibolsa (15 m, 2) | solo adelante |
| `bots` | inscrito | **bots_mayoria** (1 h, 1) · bots_unanimidad (1 h, 1) | señales guardadas desde 2026-04-19 |
| `smart_money` | **excluido** | reserva: sm_consenso, sm_unanimidad | — |
| `microstructure` | inscrito (vuelve por el scalping) | **micro_ofi** (15 m, 1) · micro_absorcion (15 m, 2, opuesta) | solo adelante |
| `seasonality` | **excluido** | reserva: estac_hora_v2 (exige versión 2.0 del agente) | — |
| `calendar` | **excluido** | reserva: cal_deriva_fomc | — |
| `context` | **excluido** | — | — |
| `arbitrage` | **excluido** | — | — |
| `plan` | control | — (como `plan_tp1`/`plan_tp2`) | — |

**Cuenta:** 13 agentes con prospectos, **43 prospectos** (13 base y 30 candidatos; 11 con su
teoría opuesta). **33** se examinan en el banco de T131 (2023-01 → 2026-11), **2** sobre las
señales guardadas de los bots (desde 2026-04-19) y **8** solo hacia adelante (los de OI y
largos/cortos, liquidaciones y microestructura). **Techo de la familia: 50** = 43 inscritos + 7
de reserva para reentradas aprobadas con ◆ (versiones nuevas tras
una baja, §9.2, o los prospectos en reserva si vuelven sus datos).

Decisión del usuario (2026-11-11): «ampliemos a 40 a 50», y después «Apruebo» (◆ de T167 cerrada; T170 congela esta lista). La primera propuesta eran 31 prospectos
con techo 36; se añadieron 9, todos desde variables que el agente ya expone y con parámetros
canónicos o del propio agente (`tec_compresion_bb`, `vwap_anclado`, `niveles_canal_extremos`,
`niveles_canal_tendencia`, `estructura_retroceso`, `pa_bos_patron`, `lit_nison_giro`,
`lit_murphy_rsi`, `deriv_largos_cortos`). El costo, dicho de antemano: la corrección por la familia
se hace sobre 50, así que cada prospecto necesita algo más de ventaja para ascender que con 36.
Los agentes excluidos siguen fuera: más prospectos que no pueden operar no añadirían información.

**Por horizonte** (pedido del usuario, mismo día): 6 de scalping (los tres siguientes, más
`liq_cascada_multibolsa`, `micro_ofi` y `micro_absorcion`, añadidos con plazas de la reserva tras
«Añadir 2–3 más»); antes, 3 de scalping (`vwap_reversion`,
`liq_agotamiento` y `liq_cascada`, pasados de 1 h a 15 m porque su teoría es de minutos), 18
intradía, 11 de tres días y 8 semanales. Cada expediente lleva el campo `horizon`.

### Lo que la verificación cambió del boceto

- **`seasonality` no calcula hora del día ni día de la semana:** su matriz es de **meses del año**
  y en 1 h sale `no_data` el 100 % (500 velas no tienen cierres mensuales). El perfil intradía de
  Heston-Korajczyk-Sadka exigiría una versión 2.0 del agente: va a BACKLOG.
- **`smart_money`, `no_data` el 100 %** de los reportes de 1 h del 2026-10-28 al 2026-11-11: no hay
  líderes aprobados con posición en BTC. Inscribirlo gastaría dos intentos en prospectos que no
  pueden operar.
- **`microstructure`, degradado el 95 %** (velas con huecos 0,39 > 0,3) y con horizonte de 3 velas:
  su escala es la clase A de T145. Se excluyó y luego volvió con dos prospectos de scalping que
  solo operan con la captura completa (pedido del usuario); el riesgo de baja por inactividad es alto.
- **`regime` y `calendar` tienen sesgo siempre 0.** `regime` sí entra porque sus etiquetas
  (`trend_up`/`trend_down`) son direccionales; `calendar` no, porque su única lectura direccional
  (deriva previa al FOMC) da ≈ 4 operaciones en 6 meses.
- **`literature` sale degradado el 100 % en 1 h:** la regla de 4 semanas no cabe en 500 velas de 1 h;
  por eso `lit_regla_4_semanas` va en 4 h.
- **Historia real:** el almacén vivo (`data/`) solo guarda semanas (velas de 1 h desde 2026-08-20,
  OI y largos/cortos desde 2026-10-01, base desde 2026-09-21); la historia larga está en el banco
  de T131 (velas de 1 m a 4 h y funding, 2023-01-01 → 2026-11-03, 100 % sin huecos). Las
  liquidaciones de Binance terminan el 2024-10-14 (otro contrato); la captura propia empieza el
  2026-10-21.
- **Parámetros:** ninguno sale de una calibración por rendimiento. Son canon (Wilder 1978, Bollinger,
  Williams, Murphy, convención del 5 %) o el valor por defecto del agente, heredado y documentado
  como no calibrado (θ de EIM-BRM-001, banda SR-2 de EIM-IRM-001, umbrales de `params.py`).

## 5. Qué hay que construir (y qué no)

- **Contexto con variables nativas** (T168): cada prospecto declara qué variables de su agente
  necesita; el bróker guarda solo esas, compactas, por vela. Nada más pesado.
- **Libro aparte** (T168): la cantera corre dentro del servicio del bróker como una variante
  (patrón `EIM_PAPER_VARIANTS`, `eim/paper/variant.py`), sin servicio nuevo y sin tocar los libros
  de los perfiles de T31. Peso 0 en la síntesis.
- **Examen físico** (T169): por la cola, con 2 procesos como máximo.
- **No** hay optimización de parámetros, ni búsqueda en rejilla, ni bandidos que repartan capital
  (el capital simulado no escasea; los bandidos de Sutton-Barto tendrían sentido para repartir
  capital real entre graduados, y eso no está en juego con D).
- **No** se reabre T139: la cantera no lee la historia para elegir; empieza a contar el día del
  pre-registro.

## 6. La retroalimentación (para qué sirve aunque nadie se gradúe)

Cómo se hace sin romper la regla de automejora (solo costo y riesgo se adaptan solos): §9.

Con D, lo que se publica es análisis. La cantera produce, por agente, **la mejor medida que vamos a
tener de si su información sirve para decidir** y en qué régimen:

- **Al agente:** una baja señala qué variables no llevan información; mejorar el agente crea una
  versión nueva y, con ella, prospectos nuevos que cuentan en la familia (BACKLOG, no automático).
- **A la biblioteca (T155/T157):** cada prospecto cita sus obras; su resultado entra como hecho de
  aprendizaje («esta teoría se sostuvo / no se sostuvo en BTC 2026–2027»). Los pesos de consenso
  no cambian solos.
- **A la síntesis (T150):** la informatividad medida hacia adelante es la evidencia que faltaba
  para los pesos; cambiarlos sigue pasando por pre-registro y ◆ del usuario (regla de automejora).
- **A la auditoría semanal (T159):** lee el resumen de la cantera.
- **A T145:** un graduado con ventaja medida sería un disparador nuevo para revisar D (◆).

## 7. Riesgos conocidos

- **Falsos talentos** por la familia grande → corrección por familia, secuencial, PBO de la
  selección y hermano simple.
- **Muestra escasa** en 6 meses → el panel muestra, por prospecto, cuántos días le faltan para un
  veredicto (MinTRL de T161) en vez de rankings que parezcan conclusiones.
- **Contar dos veces** a `bots` y `smart_money`, que ya se puntúan en T59/T33 → sus prospectos
  usan solo el consenso, no las mismas posturas ya puntuadas como estrategias.
- **Memoria del equipo** (16 GB, servicios 24/7): reglas puras a cierre de vela, sin modelos; el
  examen físico va por la cola con `--min-ram-mb`.

## 8. Decisiones que tomará el usuario (◆)

1. **T167:** la lista de prospectos por agente y el techo de la familia.
2. **T170:** el pre-registro `cantera_v1` (escalafón, método secuencial, corrección por familia,
   fecha límite) en un commit anterior a la primera operación.
3. **T172:** cada graduación a primer equipo (inscribir en T49) y si un graduado reabre D.
4. **T172:** cada reentrada (versión nueva de un prospecto dado de baja, §9.2) y cada adopción
   de una variante de ejecución (§9.3).

## 9. Automejora y retroalimentación de la cantera

Pedido del usuario (2026-11-11): incorporar a la cantera los principios de automejora y
retroalimentación que el proyecto ya tiene. No se inventa nada nuevo. La regla del usuario
(`v2/eim/paper/t143_config.py`) es que **solo se adaptan solos el costo y el riesgo**, con
umbrales escritos que abren, cierran y vuelven solos. **Entradas, salidas y pesos de la síntesis
pasan por un pre-registro y por el usuario.** La cantera aplica esa frontera tal cual: lo que
mejora a un prospecto nunca es un ajuste en caliente, es un prospecto nuevo que se cuenta.

### 9.1 Qué se adapta solo dentro de las cuentas (solo costo y riesgo, por `AUTO_ADAPT`)

Las cuentas de la cantera usan la ejecución de la corrida aparte T143 (◆ del 2026-11-10), la última
aprobada, y de ella **solo** lo que figura en `AUTO_ADAPT`:

| Adaptación (`AUTO_ADAPT`) | Qué hace en la cantera | Por qué no rompe la comparación |
|---|---|---|
| `tf_max_cost_r` (0,15 R, `paper/tf_gate.py`) | Un marco cuyo costo medido llega al umbral deja de abrir operaciones y vuelve solo cuando abarata | Se mide **por marco** con todas las cuentas de ese marco, controles incluidos, y se aplica a todas a la vez. Ningún prospecto escapa ni se libra del cierre por su propia racha |
| `maker_entry_timeframes` (1 h y 4 h) | Entrada límite donde se midió que llena (T143) | Igual para prospectos y controles del mismo marco |
| `risk_includes_costs` | La cantidad se ajusta para que la pérdida al SL inicial sea el 1 % declarado, costos incluidos | Es lo que hace que «mismo riesgo» sea verdad en todas las cuentas |

Lo que **no** se adapta solo en la cantera, aunque exista en el bróker:

- **El peso aprendido de la escalera** (`LadderParams.max_weight`, T109) queda fijo en 1. Esa
  memoria propia multiplica el tamaño tras una racha. En la cantera todas las cuentas arriesgan el
  mismo 1 %, o la rentabilidad dejaría de depender solo de la regla.
- **El freno propio** (`brake`: pérdidas seguidas o drawdown) se apaga en las cuentas de la cantera.
  Frenar las entradas de un prospecto según su propio resultado cambia lo que se mide. Su papel lo
  cumple el **tope de drawdown pre-registrado**, que da de baja (escalafón, §3).
- **La salida adaptativa** (T135) sigue apagada: T134 no aprobó ninguna. Las plantillas de salida
  de §4 son fijas.

**Cada adaptación es un evento en el libro de la cantera**: hora, marco, valor medido, umbral,
estado anterior y nuevo, y las cuentas afectadas. Así el informe de T172 separa lo que hizo la
regla de lo que hizo el costo, y la auditoría (T159) lo ve. El costo que decide la puerta solo
usa operaciones cerradas hasta ese momento (sin mirar el futuro), como en `tf_gate.py`. **Los días
con el marco cerrado por la puerta no cuentan para la baja por «60 días sin operaciones»**: la
inactividad no la decidió el prospecto.

### 9.2 El ciclo de mejora de un prospecto: baja → diagnóstico → versión nueva

1. **Baja** por el escalafón (§3), con su motivo pre-registrado.
2. **Diagnóstico** con lo que ya existe: `library/digital/diagnose.py` (T154) sobre sus operaciones
   (R/B, distancia del stop, costo en R, liquidación) y la cadena de T155 (`learning.py`:
   OPERACIÓN → DIAGNÓSTICO → ESTRATEGIA → LITERATURA → RESULTADO → CONCLUSIÓN), resumida por
   prospecto. Con menos de 30 cierres se dice «muestra insuficiente» (`MIN_N`) y no se concluye.
3. **Hipótesis escrita**: qué variable o qué condición cambia, por qué y con qué obra del catálogo.
   «Perdió dinero» no basta; hace falta una causa nombrada: variable sin información, costo,
   cadencia o la teoría contraria.
4. **Versión nueva = prospecto nuevo**: huella nueva (agente@versión, regla, parámetros), cuenta
   nueva desde el capital inicial y en guardería, **sin heredar operaciones**. **Suma un intento a
   la familia** y ocupa una de las 7 plazas de reserva del techo (50). **Pide ◆** del usuario.

Prohibido, por construcción: reajustar parámetros de un prospecto vivo, reiniciar su cuenta,
cambiarle la plantilla de salida o resucitar una baja con la misma huella. Límites, para que la
reserva no se gaste en perseguir el azar: como mucho **una reentrada por prospecto dado de baja**,
y ninguna cuyo MinTRL (T161) con +0,25 R no quepa en los días que le quedan al plazo de 6 meses.
Si la causa está en las variables del agente, la mejora va al agente (BACKLOG; versión nueva del
agente), y sus prospectos nuevos siguen este mismo ciclo.

### 9.3 Variantes que se prueban aparte (patrón `EIM_PAPER_VARIANTS`)

Lo que cambia **cómo se ejecuta** y no **cuándo se entra** (umbral de la puerta de costo, maker
frente a taker, riesgo 0,5 % frente a 1 %, otra plantilla de salida para toda la familia) se prueba
como una **mesa variante de la cantera**, igual que `paper/variant.py` con T143:

- Lee los mismos contextos y las mismas ideas de los prospectos, sin regenerarlos. Escribe en su
  propia base (`data/paper_cantera_<nombre>.duckdb`) y no toca el libro de la cantera ni los de T31.
- **No suma intentos a la familia**, igual que la variante de T143 no registra intentos en la
  puerta: no crea entradas nuevas.
- Adoptarla exige resultado medido y ◆, y se aplica a **todas** las cuentas a la vez, nunca a un
  prospecto suelto, con su evento en el libro (§9.1).
- Una variante a la vez (equipo de 16 GB con servicios 24/7).

Un cambio de entrada **nunca** es una variante: es un prospecto nuevo (§9.2).

### 9.4 Qué vuelve a dónde, y qué nunca cambia solo

| Destino | Qué recibe | Cómo cambia |
|---|---|---|
| **Biblioteca** (T155/T157) | Cada cierre de un prospecto entra en la cadena de aprendizaje con sus obras; el resultado mensual, como hecho de aprendizaje («esta teoría se sostuvo o no en BTC 2026–2027») | Los pesos del consenso (`LEVEL_W`, `RELIABILITY_W`…) son fijos. Que una postura suba al nivel `validada_eim` solo ocurre con un graduado y con ◆ |
| **Agentes** | Las bajas cuya causa es una variable sin información | BACKLOG → versión nueva del agente → prospectos nuevos (§9.2). Nunca solo |
| **Síntesis** (T150) | La informatividad medida hacia adelante por agente: R neto de su base frente al perfil al azar, con IC | La cantera pesa 0 en la síntesis. Cambiar pesos exige pre-registro y ◆ |
| **Auditoría** (T159) | El resumen de la cantera: n, rentabilidad, etapa, eventos de `AUTO_ADAPT`, días hasta veredicto. Oportunidades con su vía: `auto` (solo lo de §9.1), `variante` (§9.3), `◆` (versiones y graduaciones) y `esperar` (n < 30) | Solo describe. La lectura semanal **no es una mirada** del método secuencial: ascensos y bajas se deciden solo en la revisión mensual pre-registrada |
| **T145** | Un graduado con ventaja medida | Disparador para revisar D, con ◆ |

**Nunca cambia solo:** las reglas de entrada de los prospectos y sus parámetros, las plantillas de
salida, los pesos de la síntesis, los pesos del consenso, el escalafón y sus umbrales, el techo de
la familia, el capital inicial y el riesgo base. Todo eso pasa por pre-registro y por el usuario.

## 10. Lo que cambia tras la investigación sobre los profesionales (2026-11-11)

Informe completo y fuentes: `PLAN/notas/T167_investigacion_incubacion.md` (pedido del usuario:
«cómo hacen los profesionales este tipo de desarrollos»; aplicado con su «Sí, aplícalas»). Las
fábricas profesionales ponen la convicción en el proceso previo (hipótesis escrita, registro de
intentos, umbrales iguales para todos, parsimonia) y usan el periodo en vivo como detector de
averías: Man AHL incuba 2–3 meses y reconoce que no prueba nada. Con 40 prospectos y 6 meses, la
estadística solo detecta ventajas de 0,36–0,72 R corregidas por la familia. **El resultado más
probable de la fase es que nadie llegue a primer equipo**, y el producto principal pasa a ser la
**baja por futilidad** y saber qué teorías se sostienen, agrupadas por tema.

| # | Qué | Dónde queda |
|---|---|---|
| 1 | Gemelos aleatorios pareados (K = 200 por operación) en vez de una cuenta al azar por marco | §3 regla 4; T168; T170 |
| 2–3 | e-proceso por prospecto + e-BH mensual (q = 0,10) para Promesa; StepM en la mirada final; SPA solo de humo | §3 regla 6 y escalafón; T170 |
| 4 | Baja por futilidad frente a μ_mín = +0,10 R, no frente a 0 | Escalafón; T170 |
| 5 | Prueba del control: llega a Promesa con frecuencia ≤ α en ≥ 1 000 semillas | T170 |
| 6 | Cadencia mínima ≥ 5 operaciones/mes; «sin opción a primer equipo» si no llega a ≈ 100 en el plazo | T169 |
| 7 | Hipótesis por tema (tendencia, reversión, derivados, consenso) con modelo jerárquico y estimaciones encogidas | T170; T172 |
| 8 | Panel con R neto encogido junto al bruto y MinTRL corregido por la familia (z ≈ 3,09) | T171 |
| 9 | PBO/CSCV solo descriptivo; decide la persistencia del orden (meses 1–3 frente a 4–6) | Escalafón; T170; T172 |
| 10 | N efectivo por correlación del P&L diario, declarado junto al nominal | T170; T172 |
| 11 | Contribución marginal: correlación > 0,7 con el hermano o el genérico no asciende sin aportar por encima | Escalafón; T170 |
| 12 | Consistencia: ninguna operación aislada > 40 % del beneficio neto para Promesa | Escalafón; T170 |
| 13 | Tope de drawdown calibrado por simulación, no el 5–7,5 % de los pods | Escalafón; T170 |
| 14 | Una hipótesis primaria por prospecto; el resto, secundarias; Holm en «nativo frente a genérico» | §3 regla 4; T170; T172 |
| 15 | Comprar y mantener en unidades de riesgo, con desglose largo/corto y por régimen | §3 regla 4; T171; T172 |
| 16 | Maker conservador (llena solo si el precio atraviesa el límite), markout y funding con su frecuencia real | T168 |
| 17 | Volatilidad y drawdown como señal temprana; mucha más evidencia para el retorno | T171; T172 |
| 18 | Biblioteca con tres veredictos: sostenida, refutada y «no concluyente» por defecto | T172; §9.4 |
| 19 | Un graduado se presenta con su ventaja esperada en vivo tras el recorte de Harvey-Liu, no la bruta | T172 |
| 20 | El pre-registro publica cuántas promesas falsas espera el azar (simulado con los gemelos) | T170; T171 |

**No hacer** (rec. 21–24): objetivos de rentabilidad con plazo al estilo prop firm; que el ◆ del
usuario elija entre candidatos mirando la tabla (solo confirma o veta la salida del escalafón);
bandidos o Kelly durante la medición, o subir el techo por encima de 50; cambiar escalafón o
fórmula a mitad de fase (si hace falta, `cantera_v2` con reloj nuevo, sin recalcular el pasado).
