# Estado del proyecto (punto de entrada al cambiar de equipo)

**Actualizado:** 2026-11-04 17:40 UTC, desde `juanpablo-cpu` (**fase 22 cerrada**: T131–T134 hechas y el **gate completo verde** por la cola, 2 778 pruebas y 0 fallos; la única cosa abierta es la decisión ◆ de T134, aquí abajo. Antes: traspaso a otra cuenta de Claude, §0, y despliegue de T129/T130). Actualízalo
al cerrar una sesión que cambie algo de esta página; el detalle por tarea sigue en `STATUS.md`,
lo aplazado en `BACKLOG.md` y el registro de sesiones en `BITACORA.md`. Para comprobar un equipo:
`python -m eim.continuity check` (desde `v2/`; procedimientos en `v2/docs/CONTINUIDAD.md`).

## 0. Traspaso a otra cuenta de Claude (2026-11-03 16:30 UTC, `juanpablo-cpu`)

El usuario sigue con **otra cuenta de Claude en este mismo PC**. Las sesiones de la cuenta anterior pierden su contexto, pero el disco no cambia: repo, worktrees, `v2/data/`, servicios y tareas programadas siguen igual. La memoria local de Claude (`~/.claude/projects/…/memory`) puede no ser visible desde la otra cuenta: **lo que manda es este archivo**.

**Al empezar con la cuenta nueva**, desde `v2/`:
1. `.\.venv\Scripts\python.exe -m eim.continuity check`. Hay que usar el python del `.venv`: el del sistema no tiene pydantic.
2. Leer este archivo, las últimas entradas de `BITACORA.md` y `STATUS.md`.
3. `git -C .. worktree list` para ver lo que hay a medias (tabla de abajo).

**Estado de git al traspasar:** `main` = el commit que fusiona este traspaso (justo después de `6372e46`, que contiene T129, T130 y su despliegue). Sin PR abiertos: el #199 (mejoras de la fase 22) se fusionó en `382d423`. Carpeta principal en `main`, sin cambios rastreados (sin versionar: `.claude/settings.local.json`, `.claude/worktrees/` y `v2/reports/operation/`, los semanales de T31; versionarlos es decisión del usuario).

| Worktree / rama | Estado al traspasar | Qué hacer |
|---|---|---|
| `.claude/worktrees/fase22-mejoras` · `claude/fase22-mejoras-estudio` → **PR #199 fusionado** (`382d423`) | Hecho por la sesión «Biblioteca del proyecto»: mejoras E1–E12 en §8 de `PLAN/notas/T129_sl_dinamico.md`. Criterios de §5.4 más estrictos: el 1 con Romano-Wolf; el 7 con potencia calculada y un IC que contenga la estimación de T134; un criterio 8 nuevo con el deslizamiento ×1,5. T131–T136 actualizadas; una viñeta en §4 de este archivo. Sin cambios de código | Ya integrado. T131 se empieza sobre las fichas resultantes; su pre-registro congela esos criterios |
| `.claude/worktrees/t129-proteccion-falso-positivo` · `claude/t129-proteccion-falso-positivo` (bloqueado, sin remoto) | «T129» duplicada (fase 18) del falso positivo del 31-oct, sin confirmar. **Superada por T130**; su diagnóstico se conservó como `PLAN/notas/T130_anexo_falso_inconsistente.md` | Descartar con permiso del usuario: `git worktree unlock` + `git worktree remove --force` y borrar la rama local |
| `wt-t128f`, `wt-t62` (scratchpads de sesiones de la cuenta anterior) | Fusionadas (#190, #193) y limpias | Quitados en el traspaso |

**Servicios:** Windows se reinició el 2026-11-03 a las 15:56 UTC y la tarea de inicio de sesión relanzó todo a las 15:57 (sesión 1). La API se redesplegó a las 16:08 UTC con T130 (`GET /v2/paper/exits`, `python -m eim.paper salidas`). La racha de T78 volvió a 0 con el reinicio: comprobar con `python -m eim.data.collectors.hft_ops --root data --streak`.

**Siguiente tarea:** **la decisión ◆ del usuario de T134**, que está abierta: ¿qué salida y qué tamaño adoptan los perfiles? **T134 está hecha y su veredicto es que 87 de 87 variantes se rechazan: no hay nada que adoptar.** Los perfiles siguen con la escalera, que es lo que ◆1 de T129 ya decidió, y para eso no hay que hacer nada. Lo único con señal es **apartar el SL inicial** (`M8 q=0.95`: ΔE[R] +0,049 frente a M0, Romano-Wolf 0,0002, aguanta el estrés de costos ×1,5, baja el drawdown de 4 591 a 3 121 R), pero falla el cociente (0,11 frente a 0,50), el PF, el año 2023 y la meseta, y sigue perdiendo −0,105 R: es indicación para **T136** (riesgo por operación con costos) y **T49** (versiones con stops más amplios), no una salida que adoptar. T135 solo tiene sentido si se adopta algo. Nota `PLAN/notas/T134_experimento_salidas.md`, informe `v2/reports/exits_ab.md`. El nulo del control quedó arreglado y validado (cierra BACKLOG T131 (8)) y el PBO bajó a 0,129. **T132 está hecha**: todas las candidatas implementadas como `ExitPolicy` puras, con σ (ATR, HAR-RV de 1 min, Parkinson, Garman–Klass, Yang–Zhang), `ExitFeatures` v1 y el MAE de las ganadoras sin fuga; cobertura de rasgos ≥ 94,8 % en 3,5 años (`v2/reports/t132_smoke.md`). **T133 está hecha y su veredicto es que M4 se descarta**: ni conociendo el régimen con certeza cumpliría los criterios 1–3 de §5.4 (el oráculo por día mejora la esperanza de −0,154 a −0,093 R y sigue perdiendo; falla el cociente y el CVaR frente a M0 y el PF frente a M1). Nota `PLAN/notas/T133_regimen_ex_ante.md`. Antes de juzgar las candidatas de T132 hay que rehacer el nulo del control (BACKLOG T131 (8)). **T131 está hecha** (banco de salidas `v2/eim/paper/exits/`, pre-registro inmutable y la historia desde 2023 reconstruida en `v2/backups/t131_banco/` con cobertura del 100 %; nota `PLAN/notas/T131_banco_salidas.md`). Las ◆ de la fase 22 ya están resueltas (§4 y §6 de `PLAN/notas/T129_sl_dinamico.md`). Resultado vivo a tener en cuenta: en este periodo lateral la escalera supera a la sombra A en los cuatro perfiles y las dos pierden; T133 (régimen ex ante) es la pieza clave.

## 1. Qué corre y dónde

| Equipo | Identidad | Qué tiene | Verificado |
|---|---|---|---|
| Portátil de Santivego (`LAPTOP-I6PF9OVP`) | `laptop-i6pf9ovp-fce8d9` | Servicio continuo 24/7 desde la carpeta principal (rama `main`): API + operación en papel (corrida de T31) + bróker simulado (15 m/1 h/4 h, solo BTCUSDT), servicio de líderes (7 líderes, copia simulada), recolector de microestructura y captura HFT de BTCUSDT; copia completa diaria a las 00:00 UTC; copia externa diaria en `eim-copias` a las 20:30 hora local (tarea «EIM - copia externa diaria», desde el 2026-10-30); tarea «EIM - vigilancia captura HFT». Sin variables `EIM_*` (sin claves de testnet), sin Ollama, sin Freqtrade | sí, 2026-10-30 |
| Equipo de Juan Pablo (`jupavego`) con Freqtrade | desconocida; **no** es `juanpablo-cpu` (allí no hay `D:/eim-bots`). En el repo viejo `jupavego/eim-shared-data` hay una rama `machine/juanpablo` (última foto 2026-10-22) que `juanpablo-cpu` importó ese día; no está en Santivego | Relleno de 6 meses del escuadrón de bots, Freqtrade en `D:/eim-bots` (FSupertrend, NFI), velas de 5 m (T58–T60) | **no** |
| `DESKTOP-93R810K` (Juan Pablo) | `juanpablo-cpu` | Clon en `C:\Users\jo\Desktop\JP\TRADINGBOT` (`main`). Historial propio: 4 bases, 561 909 filas (copia `eim_20261030-230202` verificada); tras importar la experiencia de la portátil, 10 955 952 filas (`eim_20261030-232849` verificada; `leaders.duckdb` 1,27 GB). En marcha desde el 2026-10-30 23:35 UTC (con permiso del usuario; `servicio_continuo.ps1 -ConWeb`): API + operación en papel propia con identidad `juanpablo-cpu` (aparte de la corrida T31 de la portátil) + bróker simulado + líderes + Ollama (`qwen3:4b`), más el recolector de microestructura y la captura HFT de BTCUSDT. Opera a diario (decisión 2026-10-31): tarea «EIM - servicio continuo (broker simulado)» reactivada y «EIM - copia externa diaria» instalada (20:30 hora local); primera copia externa `eim_20261030-232849` completa (581 MB, 10 955 952 filas); la del 2026-10-31 01:36 UTC falló por la carga de T116 y se repitió a las 07:09 UTC: `eim_20261031-005644` (589 MB en 3 partes, con líderes) y experiencia `20261031T005644Z` (`machine/juanpablo-cpu` = `35cc71e`). Modo automático de experiencia **apagado**, como en la portátil (`share_config.json` apartado a `share_config.json.santivego-20261030`); la experiencia está en `machine/juanpablo-cpu` de Santivego (`35cc71e`). Lleva las tareas en curso (§2). Ethernet 1 Gbps, sin claves de testnet, `EIM_DUCKDB_MEMORY=2GB` definido (`EIM_OLLAMA_EXE` se quitó el 2026-11-02, T128), sin Freqtrade. Motores locales de T62 en `C:\eim-localai` (2026-10-31): Ollama 0.40.11 con los modelos aprobados, parado y sin uso por EIM mientras no se defina `EIM_OLLAMA_EXE` | sí, 2026-10-31 |

Modo: **SIMULADO** en todo (API: `mode: SIMULADO`). Dinero real imposible: `REAL` prohibido por la
configuración de riesgo; la puerta de edge (T27) **NO PASA**.

## 2. Tareas en curso y su siguiente paso

| Tarea | Estado real | Siguiente paso |
|---|---|---|
| T31 Paper trading | Corrida propia de `juanpablo-cpu` desde el 2026-10-30 23:35 UTC (decisión del usuario 2026-10-31); la de la portátil sigue en paralelo | Seguirla aquí ≥ 4 semanas (→ 2026-11-27) y cerrarla con su informe; los semanales salen solos cada lunes UTC en `v2/reports/operation/` |
| T45 Arbitraje | 3/3 escenarios en el bróker simulado (sin cuenta de Binance, decisión 2026-10-18) | Pendientes en `BACKLOG.md` (T45) |
| T78 Captura HFT | Corrida de 72 h del 24–27 oct en la portátil **NO CUMPLE** (hora 2026-10-25T20, 98,9 %). En `juanpablo-cpu` la ventana del 2026-10-31T08 UTC se perdió: horas 13–14 UTC por saturación del equipo (prueba de un modelo de visión de T62) y apagado forzado a las 21:46 UTC, con ~23 h sin servicios hasta iniciar sesión (T126). Mejor racha: 9 h (31-oct 04–12 UTC) | Sin ventana fija (T126): dejar la captura corriendo y leer `python -m eim.data.collectors.hft_ops --root data --streak` (o `t78_streak` en `data/micro_hft/qc/symbol=BTCUSDT/summary.json`); T78 se cumple en cuanto una racha llegue a 72 horas completas seguidas (mismo criterio estricto por hora). La racha del 2026-11-01T23 llegó a 23 h y se rompió en la hora 2026-11-02T22: silencios de red de 3–8 s en todos los flujos entre 22:04 y 22:10 UTC (libro útil 98,2 %, marca 98,5 %; la conexión de liquidaciones de OKX también cayó; la captura tuvo su CPU de siempre). Con la racha en cero se desplegaron #185–#191 (2026-11-02 23:13 UTC, 49 s sin captura): la nueva cuenta desde las 00 UTC del 2026-11-03 y se cumple como pronto al cerrar la hora 23 UTC del 2026-11-05 |
| T104 Microestructura | En vivo desde 2026-10-23 (ruta `/public`) | La cierra T120 |
| T116 Gate estable | 6 corridas verdes en la portátil; en `juanpablo-cpu`, 3 con Ollama generando sin parar **no verdes** (2, 1 y 10 fallos, 36–86 min): todos de pruebas con plazo de tiempo o latidos, que pasan aisladas. **El 2026-11-04 sí salió verde** una corrida completa en `juanpablo-cpu` con los servicios en marcha y **Ollama parado**, lanzada por la cola de T127 (prioridad `batch`): 2 778 pasadas, 8 omitidas, 0 fallos en 945 s | En `juanpablo-cpu`: decidir si el gate debe aguantar Ollama generando (margen de las pruebas `perf`/latidos) y 3 corridas con el equipo descargado (◆ permiso para parar servicios; fuera de la ventana de T78) |
| T117 Primera mezcla | Mezcla real **aplicada en `juanpablo-cpu`** (2026-10-30 23:25 UTC); idempotencia (0 nuevas) y simulacro en sentido portátil (217 084 nuevas, 0 incompatibles) hechos desde aquí; modo automático apagado en los dos equipos | En `juanpablo-cpu`: revisar `share_conflicts` (1 243 en reports, 3 449 en paper) y cerrar la tarea; aplicar en la portátil es opcional |
| T119 Escuadrón verificado | **Hecha** (☑ 2026-10-31 desde `juanpablo-cpu`): API = CLI sobre copia en caliente, 24 intentos de Holm idénticos | — |
| T62 Motores locales | Auditoría hecha y lista **aprobada** (2026-10-31, `PLAN/notas/T62_auditoria.md`); instalada en `juanpablo-cpu` (`C:\eim-localai`) y banco medido completo allí (`v2/reports/localai/bench_juanpablo-cpu.md`: `qwen3:4b-instruct` + RapidOCR + faster-whisper small entran; GPU, Pydantic AI y el VLM 2B no) | Correr el banco en la portátil (equipo de referencia, `docs/OPERACION.md` §7); ◆ postura ante YouTube (`v2/docs/SEGURIDAD.md`); muestras de audio reales; después cerrar T62 |
| T125 Continuidad entre equipos | Hecha (PR #171); `juanpablo-cpu` con copia externa diaria propia desde el 2026-10-31 | Huecos encontrados al usarla en BACKLOG T125 (1)–(9) |
| T126 Director de recursos | Fase 1 **desplegada** el 2026-11-01 21:34 UTC (PR #175): recolectores en AboveNormal, servicios en BelowNormal, mantenimiento en Idle; alertas de latido con su cadencia real; T78 por racha | Tarea «EIM - servicio continuo al encender» registrada por el usuario (S4U, 2 min tras arrancar) y probada una vez con los servicios en marcha: salida 0, no lanzó ni tocó nada. Hecha (☑). Siguiente: T127 (registro de consumo y cola de trabajos pesados) y T128 (consolidación), en la fase 21 de la hoja de ruta |
| T129 Stop dinámico (solo lectura) | **Hecha** (☑ 2026-11-03): la escalera deja el stop a menos de un incremento del extremo (27–61 USD de BTC, dentro del ruido de 1 min). Ganadoras de +0,11 R frente a perdedoras de −0,96 R (PF 0,35). Informe `PLAN/notas/T129_sl_dinamico.md` | ◆ resueltas (§4). T130 hecha y **desplegada** el 2026-11-03 16:08 UTC (MFE/MAE desde el llenado, falso positivo de T110, `/v2/paper/exits`). A/B en vivo: en este periodo lateral la escalera supera a la sombra A en los cuatro perfiles (Δ +0,13…+0,46 R/op) y las dos pierden; siguiente: T132 ‖ T133 → T134 ◆ |
| T131 Banco de salidas | **Hecha** (☑ 2026-11-03): banco `v2/eim/paper/exits/`, pre-registro inmutable (107 intentos, huella en el código) e historia desde 2023 en `v2/backups/t131_banco/` con cobertura 100 % y 0 huecos. Nota `PLAN/notas/T131_banco_salidas.md`, informe `v2/reports/t131_banco.md` | Nada tocado en vivo. **Tres cosas que T132 y T134 tienen que tener presentes:** (1) la escalera queda confirmada fuera de muestra en 3,5 años (acierto 76,1 %, cociente 0,12, PF 0,39) y **las once variantes de M0 y M1 pierden**: el problema está en la entrada; (2) ese **PBO 0,46** frente al 0,2 pre-registrado **estaba mal medido** y T134 lo deja en **0,129** con 89 variantes (el CSCV de T131 solo tenía once casi idénticas entre las que elegir): al citarlo, usar el 0,129; el Sharpe deflactado 0,000 sigue en pie; (3) **el nulo del control aleatorio está mal especificado** para salidas con arrastre sobre la serie real y hay que rehacerlo antes de juzgar las candidatas (BACKLOG T131 (8)) |

Pendientes destacadas: fase 22 (T130–T136, gestión dinámica del riesgo de la posición), T120 (recolectores sin «sin datos»), T121 (documentación y variables),
T123 (colas acotadas), T127–T128 (director de recursos: consumo, cola de trabajos y consolidación; fase 21), T124 (instantáneas de datos), T46, T62–T71 (motores locales y video),
T79–T86 (HFT), T87–T103 (multiactivo). Orden sugerido en `00_MASTER.md` (fase 20).

## 3. Problemas conocidos sin resolver

- **`juanpablo-cpu`, copia en caliente de `leaders.duckdb`**: tras importar la experiencia de la
  portátil la base pesa 1,27 GB y la instantánea del servicio de líderes se queda sin memoria
  (tope DuckDB de 1 GB, `EIM_DUCKDB_MEMORY`): las copias del 2026-10-31 `000042` y `002221`
  salieron **sin líderes**. Mitigado ese día con permiso: variable de usuario
  `EIM_DUCKDB_MEMORY=2GB` y reinicio solo del servicio de líderes → `eim_20261031-005644`
  completa e íntegra (líderes 10 589 988 filas; instantánea en 410 s con el equipo cargado).
  La portátil tendrá lo mismo si importa. Arreglo de código: BACKLOG T125 (7).
- **Servicio de líderes**: se atascaba sin latido (~900 s) con hasta 13,5 GB de memoria; PR #169
  (evaluación incremental) desplegado el 2026-10-30 02:26 UTC lo bajó a ~0,9 GB. Vigilar. Visto el
  mismo día: caídas «código 1» cuando la copia diaria copió `leaders.duckdb` en frío mientras el
  servicio se reiniciaba (la API retenía el archivo).
- Copia simulada de `0x0fac…` en pausa por «divergencia no explicada: NEAR» (antigua); las pausas
  solo se levantan a mano (`python -m eim.leaders --root <data> copy-resume 0x…`).
- El `summary.json` de la captura HFT está congelado con el vigilante viejo (compactación de horas
  pesadas); se calcula a demanda con el código nuevo (ver T78).
- Memoria del sistema de la portátil al límite (34,3 de 35,8 GB confirmados el 2026-10-29).
- En `juanpablo-cpu` el Ollama de la unidad de red `Z:` (`\\DESKTOP-TVD562Q\USB`) dejó
  de cargar modelos el 2026-10-31 y `EIM_OLLAMA_EXE` se quitó el 2026-11-02 (T128): Contexto
  queda sin LLM. Hay uno local en `C:\eim-localai` (T62, `docs/OPERACION.md` §7); ◆ activarlo
  tras T78 midiendo la RAM. `servicio_continuo.ps1` aún lanza `serve` sin `OLLAMA_NO_CLOUD=1`
  (consulta `ollama.com` cada 4 h; BACKLOG T62 (1)).
- En `juanpablo-cpu`, el VLM `qwen3-vl:2b` (8,8 GB de memoria privada) junto a los servicios dejó
  el equipo sin memoria (consultas de 1 min) y cortó la racha de T78 (31-oct, horas 13–14 UTC);
  no cargarlo con los servicios en marcha.
- Cambios sin confirmar de otras sesiones en los worktrees `t117-mezcla` (notas de T117) y
  `t119-marcar` (cierre de T119); guardados también como parche en
  `v2/backups/proteccion_T125_20261030-0310/` (local).

- **`juanpablo-cpu`, corridas largas (diagnóstico T126, 2026-11-01; mitigado el mismo día):** apagado forzado el 31-oct 21:46 UTC (botón de encendido durante una suspensión; inicio rápido activo); las tareas del EIM solo arrancan al iniciar sesión; desde T126 (2026-11-01 21:34 UTC) la captura corre en ABOVE_NORMAL y el resto del EIM en BELOW_NORMAL, y la tarea al encender está registrada. Ajustes de Windows hechos por el usuario (2026-11-01): inicio rápido **desactivado** (`HiberbootEnabled` 0, comprobado), botón de encendido en «Apagar» (ahora apagado completo) y `v2\data` excluida del análisis en tiempo real de Defender. Probado el 2026-11-01: tras un reinicio voluntario Windows inicia sesión solo y la tarea de inicio de sesión devuelve todo en ~1,5 min; con los servicios parados, la tarea al encender los levanta desde cero en la sesión 0 en 19 s, con las prioridades correctas. Desde la sesión del usuario no se ve la línea de órdenes de los procesos de la sesión 0: el lanzador consulta los cerrojos de instancia (la API y las liquidaciones ya lo tienen; desplegado el 2026-11-02 02:48 UTC, y con todo en marcha la tarea de inicio de sesión ya no lanza nada). Para los servicios de la sesión 0 todavía hace falta un PowerShell de administrador o reiniciar. Desde T127, cada servicio da permiso a su usuario al arrancar, y `scripts\detener_servicio.ps1` (o «Parar servicio») los para sin elevar, pero solo cuando arranquen con ese código: ◆ reiniciar los servicios cuando se cumpla T78. Desde el 2026-11-02 03:38 UTC corre el registro de consumo (T127, `data/usage/`; `python -m eim.operation.usage summary`). Los trabajos pesados van por la cola: `python -m eim.operation.jobs submit --name N -- <orden>` los pausa si la captura sufre.

- **El gate rompe la racha de T78; las descargas y los bancos no** (medido el 2026-11-03 con T131). Hora a hora (UTC): la 16 (banco sin velas finas) y la 17 (descarga de 2 M velas de 1 m **más** el banco con velas finas) salieron completas con libro 1,0000; la **18, la del gate, salió incompleta** (libro 0,9164) y rompió la racha. La cola se pausó dos veces y se reanudó sola, pero su umbral salta con RAM libre < 1 GB y para entonces la captura ya llevaba minutos degradada. Mientras no se ajuste (BACKLOG T127 (3)), **no correr el gate completo con una racha de T78 en juego**: la cola protege de las descargas y del cálculo, no del `pytest` entero.
  **Gate completo corrido y verde (2026-11-04 17:13–17:28 UTC).** Se corrió desde `main` @ 2dba569 y por la cola (`jobs submit --name gate-fase22 --retry-paused 1 -- python -m pytest -q`) aprovechando que la racha de T78 estaba en su **primera** hora, que es cuando rompérsela cuesta casi nada. Resultado: `ruff` limpio y **2 778 pruebas pasadas, 8 omitidas, 0 fallos** en 945 s, **sin ninguna pausa de la cola** — T132, T133 y T134 quedan avaladas por la suite entera y no solo por los paquetes afectados, y con esto la fase 22 no deja ningún gate pendiente. **Lo que todavía no se sabe:** el gate cayó entero dentro de la hora 17 UTC, que al escribir esto aún no era auditable (la racha iba por la hora 16, `hft_ops --streak`); si la 17 sale incompleta, la racha vuelve a 0 y se confirma otra vez lo medido arriba. La regla **sigue en pie**: no correr el gate completo con una racha de T78 ya avanzada mientras no se ajuste el umbral de la cola (BACKLOG T127 (3)).

## 4. Decisiones vigentes del usuario (no reabrir sin preguntar)

- Sin dinero real hasta superar la puerta de edge (T27) y semanas de papel (T31). Todo SIMULADO.
- «Operaciones sugeridas» solo desde estrategias validadas por el bróker simulado (puerta T49);
  si nada cumple, «sin operaciones validadas para sugerir».
- Foco solo BTCUSDT (T122, 2026-10-22); ETH se conserva en el almacén.
- T117: transporte = repo privado `Santivego/eim-shared-data`; identidad de la portátil = su id
  actual; modo automático solo tras revisar los simulacros; segundo colaborador = `jupavego`.
- T78: criterio estricto por hora (≥ 99 % de horas completas).
- Libros de trading: solo uso local, nunca se suben (`17.0 - TRADING\Books`).
- T129 (2026-11-03, «hacer todo lo recomendado»):
  - La escalera queda como referencia provisional hasta T134, sin cambiar la salida en vivo; el A/B en vivo sale de la sombra.
  - Cierres parciales y SL inicial con piso de volatilidad, solo en el banco hasta que T134 los apruebe (el SL nuevo crea versiones en T49).
  - Agentes solo como selectores discretos validados por `ExitFeatures`; nunca escriben stops; LLM fuera.
  - Sin dependencias nuevas salvo statsmodels si T133 lo exige, tras T04.
  - Mejoras de método E1–E12 del estudio de la bibliografía (2026-11-03, `PLAN/notas/T129_sl_dinamico.md` §8): purga y embargo, Romano-Wolf además de Holm, objetivo de selección pre-registrado, estrés de costos, cota del oráculo antes de T133, prueba en papel con potencia calculada (sustituye a «mismo signo») y Kelly sobre el límite inferior de E[R].
- T125: la copia completa externa va a la versión `eim-copias` del mismo repo privado; cada
  equipo con identidad propia; el código público nunca lleva datos ni claves.

## 5. Cómo se opera la portátil (lecciones que no están en el código)

- Desplegar: trabajar en un worktree; tras fusionar, `git merge --ff-only origin/main` en la
  carpeta principal y matar **solo** el proceso Python real que escucha en :8000 (su padre es el
  lanzador del venv y el abuelo el vigilante `eim.operation run`): el vigilante lo relanza con el
  código nuevo (12 s–3 min; mirar `servicio_iniciado` en `data/operation/logs/op-*.jsonl`).
  Líderes: igual con el proceso real de `eim.leaders run`. Pedir permiso antes de reiniciar: la
  corrida de T31 vive ahí.
- En `juanpablo-cpu` (4 núcleos), todo trabajo pesado con los servicios en marcha (gate, importaciones, pruebas de modelos de T62) va con `python -m eim.operation.priority run batch -- <orden>`: a la misma prioridad, la captura HFT pierde horas (T126).
- Un proceso lanzado desde la herramienta de terminal muere al acabar la llamada: los servicios
  se lanzan con `Invoke-CimMethod Win32_Process Create` (como `servicio_continuo.ps1`).
- Con la API en marcha `reports.duckdb`/`paper.duckdb` están bloqueados: las CLI piden el trabajo a
  la API (`POST` con `X-EIM-Confirm`); la copia la hace la API (`backup create` lo gestiona).
- Varias sesiones de Claude trabajan a la vez en la carpeta principal: revisar `git status` antes
  de commitear y no mezclar cambios ajenos.
- `python -m eim.continuity publish` lanzado por Claude en modo de permisos automático se bloquea
  («exfiltración de datos») aunque el usuario lo autorice en el chat: o lo ejecuta el usuario
  (`v2\scripts\copia_externa.ps1`) o cambia al modo con aprobación y aprueba el comando.
