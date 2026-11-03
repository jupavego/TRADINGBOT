# Estado del proyecto (punto de entrada al cambiar de equipo)

**Actualizado:** 2026-11-03 06:30 UTC, desde `juanpablo-cpu` (T129: diagnóstico del stop dinámico y fase 22 planificada; antes, 05:15 UTC: fusión de T62). Actualízalo
al cerrar una sesión que cambie algo de esta página; el detalle por tarea sigue en `STATUS.md`,
lo aplazado en `BACKLOG.md` y el registro de sesiones en `BITACORA.md`. Para comprobar un equipo:
`python -m eim.continuity check` (desde `v2/`; procedimientos en `v2/docs/CONTINUIDAD.md`).

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
| T116 Gate estable | 6 corridas verdes en la portátil; en `juanpablo-cpu`, 3 con Ollama generando sin parar **no verdes** (2, 1 y 10 fallos, 36–86 min): todos de pruebas con plazo de tiempo o latidos, que pasan aisladas | En `juanpablo-cpu`: decidir si el gate debe aguantar Ollama generando (margen de las pruebas `perf`/latidos) y 3 corridas con el equipo descargado (◆ permiso para parar servicios; fuera de la ventana de T78) |
| T117 Primera mezcla | Mezcla real **aplicada en `juanpablo-cpu`** (2026-10-30 23:25 UTC); idempotencia (0 nuevas) y simulacro en sentido portátil (217 084 nuevas, 0 incompatibles) hechos desde aquí; modo automático apagado en los dos equipos | En `juanpablo-cpu`: revisar `share_conflicts` (1 243 en reports, 3 449 en paper) y cerrar la tarea; aplicar en la portátil es opcional |
| T119 Escuadrón verificado | **Hecha** (☑ 2026-10-31 desde `juanpablo-cpu`): API = CLI sobre copia en caliente, 24 intentos de Holm idénticos | — |
| T62 Motores locales | Auditoría hecha y lista **aprobada** (2026-10-31, `PLAN/notas/T62_auditoria.md`); instalada en `juanpablo-cpu` (`C:\eim-localai`) y banco medido completo allí (`v2/reports/localai/bench_juanpablo-cpu.md`: `qwen3:4b-instruct` + RapidOCR + faster-whisper small entran; GPU, Pydantic AI y el VLM 2B no) | Correr el banco en la portátil (equipo de referencia, `docs/OPERACION.md` §7); ◆ postura ante YouTube (`v2/docs/SEGURIDAD.md`); muestras de audio reales; después cerrar T62 |
| T125 Continuidad entre equipos | Hecha (PR #171); `juanpablo-cpu` con copia externa diaria propia desde el 2026-10-31 | Huecos encontrados al usarla en BACKLOG T125 (1)–(9) |
| T126 Director de recursos | Fase 1 **desplegada** el 2026-11-01 21:34 UTC (PR #175): recolectores en AboveNormal, servicios en BelowNormal, mantenimiento en Idle; alertas de latido con su cadencia real; T78 por racha | Tarea «EIM - servicio continuo al encender» registrada por el usuario (S4U, 2 min tras arrancar) y probada una vez con los servicios en marcha: salida 0, no lanzó ni tocó nada. Hecha (☑). Siguiente: T127 (registro de consumo y cola de trabajos pesados) y T128 (consolidación), en la fase 21 de la hoja de ruta |
| T129 Stop dinámico (solo lectura) | **Hecha** (☑ 2026-11-03): la escalera deja el stop a menos de un incremento del extremo (27–61 USD de BTC, dentro del ruido de 1 min). Ganadoras de +0,11 R frente a perdedoras de −0,96 R (PF 0,35). Informe `PLAN/notas/T129_sl_dinamico.md` | ◆ resueltas (§4). T130 hecha (MFE/MAE desde el llenado, falso positivo de T110, `/v2/paper/exits`); siguiente: T131 → T131 → T132 ‖ T133 → T134 ◆ |

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
