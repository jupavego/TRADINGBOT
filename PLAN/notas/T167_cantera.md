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
- **Marco:** 1 h o 4 h (15 m solo si el examen físico demuestra costo ≤ 0,3 R); los perfiles
  lentos (diarios, siempre posicionados) se miden por rendimiento diario, como T163.
- **Plantilla de salida:** una de pocas fijas (stop por ATR con la escalera vigente; salida por
  regla contraria; tiempo máximo). No se prueban salidas: eso ya se cerró.
- **Riesgo:** 1 % fijo del capital de su cuenta por operación (perfil Moderado), para que todos compitan igual. Los estilos
  Conservador/Agresivo/PPP se muestran como **lentes** sobre los graduados (T156), no como
  prospectos nuevos que gasten intentos.
- **Huella:** como las versiones de T49; cambiar una regla o un parámetro = prospecto nuevo, que
  empieza de cero y **suma un intento a la familia**.

### Reglas de la casa (el antídoto contra el azar)

1. **Presupuesto:** ≤ 4 prospectos por agente, ≤ 3 parámetros libres por prospecto y un techo de
   familia que se fija en el pre-registro (orden de 40–50).
2. **Hermano simple obligatorio:** cada agente inscribe un perfil **base** de 1–2 parámetros. Un
   perfil más complejo solo asciende si supera al base de su agente; a empate estadístico,
   asciende el simple («lo más exitoso no tiene que ser lo más complejo», escrito como regla).
3. **Teoría opuesta cuando exista:** si un agente admite lectura de tendencia y de reversión, se
   inscriben las dos; la cantera también sirve para saber cuál de las dos teorías se sostiene.
4. **Controles fijos, que no cuentan como prospectos:** lado aleatorio (mismas fechas y costos),
   comprar y mantener, y el `agente_{id}` genérico de hoy. La pregunta «¿lo nativo supera a lo
   genérico?» queda respondida por agente.
5. **La historia no asciende a nadie.** Solo se usa para el **examen físico** (T169): que el
   perfil opere, cuánto opera, cuánto le cuesta en R y que no mire el futuro. **No se calcula su
   rendimiento en la historia**, para no volver a gastar la lectura limpia ni sesgar el registro.
6. **Miradas fijadas:** la revisión es mensual, con método secuencial elegido en el pre-registro
   (secuencias de confianza válidas en cualquier momento o gasto de alfa por mirada). Mirar cada
   día con una prueba de n fijo inflaría los falsos talentos.
7. **Nada asciende solo a dinero.** Graduarse permite, con ◆ del usuario, inscribir el perfil en el
   registro de T49 con su historial hacia adelante; T49 decide si se publica como sugerencia, y la
   decisión D (T145) sigue mandando sobre operar.

### Escalafón

| Etapa | Entra cuando | Sale cuando |
|---|---|---|
| **Guardería** | Pasa el examen físico y queda en el pre-registro | Llega a 30 operaciones (o 60 días si es lento) |
| **Cantera** | n ≥ 30 y no es claramente negativo | Asciende o se da de baja |
| **Promesa** | Rentabilidad neta positiva y por encima de la del perfil al azar con la vara secuencial (cota inferior del R neto > 0) y, si es complejo, por encima de su hermano simple | Cumple todo lo de primer equipo o deja de cumplir |
| **Primer equipo** | Criterios `cantera_v1` completos: corrección por la familia (Romano-Wolf o SPA, T161), Sharpe deflactado, ≥ 2 regímenes, drawdown y costo como V4–V6, PBO de la selección (CSCV sobre la matriz de la familia) bajo | ◆ del usuario: inscribir en T49 |
| **Baja** | Pierde dinero de forma clara (cota superior del R neto < 0), drawdown de su cuenta por encima del tope pre-registrado, sin operaciones en 60 días o fecha límite (6 meses) | Definitiva; **sigue contando en la familia** |

## 4. Los 19 agentes: datos propios, historia y perfiles candidatos

Boceto para T167 (que lo verifica agente por agente y lo cierra). «Historia» decide solo qué se
puede **examinar** en la historia; el rendimiento se mide siempre hacia adelante.

| Agente | Datos propios | Historia | Perfil base (simple) | Otros candidatos | Literatura (id del catálogo T151) |
|---|---|---|---|---|---|
| `ema` | 44 variables FRM (pila, pendientes, compresión, rebotes, cruces, elasticidad) | Larga (velas) | **Pila alineada:** EMA 9>21>55>100>200 y precio sobre la 200 (inverso en corto); sale al romperse la pila | Resorte (compresión larga → ruptura en la dirección de las pendientes); retroceso a la 21/55 en tendencia; elasticidad extrema (reversión: teoría opuesta) | `brock_lakonishok_lebaron_1992`, `moskowitz_ooi_pedersen_2012`, `hurst_ooi_pedersen_2017`, `sullivan_timmermann_white_1999` |
| `technical` | RSI, MACD, BB, ADX… en varios marcos | Larga | Acuerdo de marcos (1 h = 4 h = 1 d) | RSI extremo solo con ADX bajo (rango); ruptura con volumen | `lo_mamaysky_wang_2000`, `park_irwin_2007`, `blume_easley_ohara_1994` |
| `vwap` | VWAP diario/semanal/anclado y bandas σ | Larga | Reversión al VWAP diario desde ±2σ | Ruptura del VWAP semanal con persistencia | `zarattini_aziz_2023` |
| `levels` | Soportes/resistencias por pivotes | Larga | Rebote en nivel fuerte | Ruptura confirmada | `osler_2000_frbny`, `osler_2003` |
| `structure` | Máximos/mínimos, rupturas de estructura | Larga | Seguir la ruptura de estructura | Retroceso tras la ruptura | `lo_mamaysky_wang_2000` |
| `price_action` | Patrones de vela | Larga | Patrón de giro en extremo de rango | — | `marshall_young_rose_2006` (en contra: se espera baja) |
| `elliott` | Conteos de ondas | Larga | Onda 3 en curso | — | Sin respaldo académico (se espera baja) |
| `seasonality` | Hora del día, día de la semana | Larga | Sesgo estacional por ventana móvil **solo pasada** (procedimiento fijo, no parámetros elegidos en la historia) | — | `heston_korajczyk_sadka_2010` |
| `regime` | Régimen de tendencia/rango | Larga | Seguir la tendencia solo en régimen de tendencia | Reversión solo en rango | `daniel_moskowitz_2016` |
| `literature` | Fichas de los libros evaluadas sobre el mercado | Larga si es puro sobre velas (verificar) | Escenario con más apoyo | — | (T53, T157) |
| `derivatives` | Funding, OI, largos/cortos, base | Funding larga; OI y L/S cortas | Funding extremo, contrario | OI sube mientras el precio diverge | `he_manela_2022`, `ackerer_2023_perp`, `soska_2021_bitmex`, `liu_tsyvinski_2021` |
| `liquidations` | Liquidaciones forzadas | Corta (desde la captura) | Agotamiento tras cascada (contrario) | — | `brunnermeier_pedersen_2009` |
| `microstructure` | OFI, profundidad | Corta (oct-2026) | OFI persistente → dirección a corto plazo | — | `cont_kukanov_stoikov_2014`, `easley_lopezdeprado_ohara_2012` (costo: probable baja) |
| `smart_money` | Tablero de líderes y sus pesos | Corta (desde la captura de líderes) | Consenso ponderado de líderes | — | (T33–T44) |
| `bots` | Posturas de los bots públicos | Las guardadas | Consenso de los bots de categoría A | — | (T59; evitar contar dos veces su puntuación) |
| `calendar` | Eventos macro | Verificar | No direccional: perfil de **abstención** (el base del mercado sin ±2 h de evento) | Deriva previa al FOMC | `corbet_2020_fomc` |
| `context` | LLM sobre noticias | No reproducible | Solo hacia adelante y **solo con motor activo** (hoy sin LLM: queda fuera hasta que vuelva) | — | — |
| `plan` | Plan entrada/SL/TP desde `structure` y `levels` | Larga | Ya existe como estrategia (`plan_*`); entra como control, no como prospecto, salvo que T167 vea algo propio | — | — |
| `arbitrage` | Diferenciales entre mercados | — | **Fuera:** neutral al mercado, no direccional (T45 aparcada) | — | — |

Cuenta orientativa: 15–16 agentes con prospectos, 2–4 cada uno → **40–50 prospectos**.

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
