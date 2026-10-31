# Estado del proyecto (punto de entrada al cambiar de equipo)

**Actualizado:** 2026-10-31 07:18 UTC, desde `juanpablo-cpu` (las tareas en curso siguen aquí). Actualízalo
al cerrar una sesión que cambie algo de esta página; el detalle por tarea sigue en `STATUS.md`,
lo aplazado en `BACKLOG.md` y el registro de sesiones en `BITACORA.md`. Para comprobar un equipo:
`python -m eim.continuity check` (desde `v2/`; procedimientos en `v2/docs/CONTINUIDAD.md`).

## 1. Qué corre y dónde

| Equipo | Identidad | Qué tiene | Verificado |
|---|---|---|---|
| Portátil de Santivego (`LAPTOP-I6PF9OVP`) | `laptop-i6pf9ovp-fce8d9` | Servicio continuo 24/7 desde la carpeta principal (rama `main`): API + operación en papel (corrida de T31) + bróker simulado (15 m/1 h/4 h, solo BTCUSDT), servicio de líderes (7 líderes, copia simulada), recolector de microestructura y captura HFT de BTCUSDT; copia completa diaria a las 00:00 UTC; copia externa diaria en `eim-copias` a las 20:30 hora local (tarea «EIM - copia externa diaria», desde el 2026-10-30); tarea «EIM - vigilancia captura HFT». Sin variables `EIM_*` (sin claves de testnet), sin Ollama, sin Freqtrade | sí, 2026-10-30 |
| Equipo de Juan Pablo (`jupavego`) con Freqtrade | desconocida; **no** es `juanpablo-cpu` (allí no hay `D:/eim-bots`). En el repo viejo `jupavego/eim-shared-data` hay una rama `machine/juanpablo` (última foto 2026-10-22) que `juanpablo-cpu` importó ese día; no está en Santivego | Relleno de 6 meses del escuadrón de bots, Freqtrade en `D:/eim-bots` (FSupertrend, NFI), velas de 5 m (T58–T60) | **no** |
| `DESKTOP-93R810K` (Juan Pablo) | `juanpablo-cpu` | Clon en `C:\Users\jo\Desktop\JP\TRADINGBOT` (`main`). Historial propio: 4 bases, 561 909 filas (copia `eim_20261030-230202` verificada); tras importar la experiencia de la portátil, 10 955 952 filas (`eim_20261030-232849` verificada; `leaders.duckdb` 1,27 GB). En marcha desde el 2026-10-30 23:35 UTC (con permiso del usuario; `servicio_continuo.ps1 -ConWeb`): API + operación en papel propia con identidad `juanpablo-cpu` (aparte de la corrida T31 de la portátil) + bróker simulado + líderes + Ollama (`qwen3:4b`), más el recolector de microestructura y la captura HFT de BTCUSDT. Opera a diario (decisión 2026-10-31): tarea «EIM - servicio continuo (broker simulado)» reactivada y «EIM - copia externa diaria» instalada (20:30 hora local); primera copia externa `eim_20261030-232849` completa (581 MB, 10 955 952 filas); la del 2026-10-31 01:36 UTC falló por la carga de T116 y se repitió a las 07:09 UTC: `eim_20261031-005644` (589 MB en 3 partes, con líderes) y experiencia `20261031T005644Z` (`machine/juanpablo-cpu` = `35cc71e`). Modo automático de experiencia **apagado**, como en la portátil (`share_config.json` apartado a `share_config.json.santivego-20261030`); la experiencia está en `machine/juanpablo-cpu` de Santivego (`35cc71e`). Lleva las tareas en curso (§2). Ethernet 1 Gbps, sin claves de testnet, `EIM_OLLAMA_EXE` y `EIM_DUCKDB_MEMORY=2GB` definidos, sin Freqtrade | sí, 2026-10-31 |

Modo: **SIMULADO** en todo (API: `mode: SIMULADO`). Dinero real imposible: `REAL` prohibido por la
configuración de riesgo; la puerta de edge (T27) **NO PASA**.

## 2. Tareas en curso y su siguiente paso

| Tarea | Estado real | Siguiente paso |
|---|---|---|
| T31 Paper trading | Corrida propia de `juanpablo-cpu` desde el 2026-10-30 23:35 UTC (decisión del usuario 2026-10-31); la de la portátil sigue en paralelo | Seguirla aquí ≥ 4 semanas (→ 2026-11-27) y cerrarla con su informe; los semanales salen solos cada lunes UTC en `v2/reports/operation/` |
| T45 Arbitraje | 3/3 escenarios en el bróker simulado (sin cuenta de Binance, decisión 2026-10-18) | Pendientes en `BACKLOG.md` (T45) |
| T78 Captura HFT | Corrida de 72 h del 24–27 oct en la portátil **NO CUMPLE** (hora 2026-10-25T20, 98,9 %). En `juanpablo-cpu` el #162 ya corre (captura desde el 2026-10-29 16:21 UTC); en las horas comunes rinde mejor que la portátil (6 de 9 completas frente a 0); lo que le resta horas es la carga local | En `juanpablo-cpu`: ventana de 72 h del 2026-10-31T08 al 2026-11-03T07 UTC (72 horas completas: de las 08:00 UTC del 31-oct a las 08:00 UTC del 3-nov), abierta tras los gates de T116 y la copia externa repetida sin trabajos pesados encima (gates, importaciones); aceptación al leer `data/micro_hft/qc/symbol=BTCUSDT/summary.json` al final: criterio estricto, las 72 horas completas (libro utilizable ≥ 99 % en cada una: `hours_complete` 72, `pct_complete` 1); el vigilante `vigilar_hft.py` de la portátil vive en su `data/` y no viaja. Cifras en `STATUS.md` |
| T104 Microestructura | En vivo desde 2026-10-23 (ruta `/public`) | La cierra T120 |
| T116 Gate estable | 6 corridas verdes en la portátil; en `juanpablo-cpu`, 3 con Ollama generando sin parar **no verdes** (2, 1 y 10 fallos, 36–86 min): todos de pruebas con plazo de tiempo o latidos, que pasan aisladas | En `juanpablo-cpu`: decidir si el gate debe aguantar Ollama generando (margen de las pruebas `perf`/latidos) y 3 corridas con el equipo descargado (◆ permiso para parar servicios; fuera de la ventana de T78) |
| T117 Primera mezcla | Mezcla real **aplicada en `juanpablo-cpu`** (2026-10-30 23:25 UTC); idempotencia (0 nuevas) y simulacro en sentido portátil (217 084 nuevas, 0 incompatibles) hechos desde aquí; modo automático apagado en los dos equipos | En `juanpablo-cpu`: revisar `share_conflicts` (1 243 en reports, 3 449 en paper) y cerrar la tarea; aplicar en la portátil es opcional |
| T119 Escuadrón verificado | **Hecha** (☑ 2026-10-31 desde `juanpablo-cpu`): API = CLI sobre copia en caliente, 24 intentos de Holm idénticos | — |
| T125 Continuidad entre equipos | Hecha (PR #171); `juanpablo-cpu` con copia externa diaria propia desde el 2026-10-31 | Huecos encontrados al usarla en BACKLOG T125 (1)–(9) |

Pendientes destacadas: T120 (recolectores sin «sin datos»), T121 (documentación y variables),
T123 (colas acotadas), T124 (instantáneas de datos), T46, T62–T71 (motores locales y video),
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
- Cambios sin confirmar de otras sesiones en los worktrees `t117-mezcla` (notas de T117) y
  `t119-marcar` (cierre de T119); guardados también como parche en
  `v2/backups/proteccion_T125_20261030-0310/` (local).

## 4. Decisiones vigentes del usuario (no reabrir sin preguntar)

- Sin dinero real hasta superar la puerta de edge (T27) y semanas de papel (T31). Todo SIMULADO.
- «Operaciones sugeridas» solo desde estrategias validadas por el bróker simulado (puerta T49);
  si nada cumple, «sin operaciones validadas para sugerir».
- Foco solo BTCUSDT (T122, 2026-10-22); ETH se conserva en el almacén.
- T117: transporte = repo privado `Santivego/eim-shared-data`; identidad de la portátil = su id
  actual; modo automático solo tras revisar los simulacros; segundo colaborador = `jupavego`.
- T78: criterio estricto por hora (≥ 99 % de horas completas).
- Libros de trading: solo uso local, nunca se suben (`17.0 - TRADING\Books`).
- T125: la copia completa externa va a la versión `eim-copias` del mismo repo privado; cada
  equipo con identidad propia; el código público nunca lleva datos ni claves.

## 5. Cómo se opera la portátil (lecciones que no están en el código)

- Desplegar: trabajar en un worktree; tras fusionar, `git merge --ff-only origin/main` en la
  carpeta principal y matar **solo** el proceso Python real que escucha en :8000 (su padre es el
  lanzador del venv y el abuelo el vigilante `eim.operation run`): el vigilante lo relanza con el
  código nuevo (12 s–3 min; mirar `servicio_iniciado` en `data/operation/logs/op-*.jsonl`).
  Líderes: igual con el proceso real de `eim.leaders run`. Pedir permiso antes de reiniciar: la
  corrida de T31 vive ahí.
- Un proceso lanzado desde la herramienta de terminal muere al acabar la llamada: los servicios
  se lanzan con `Invoke-CimMethod Win32_Process Create` (como `servicio_continuo.ps1`).
- Con la API en marcha `reports.duckdb`/`paper.duckdb` están bloqueados: las CLI piden el trabajo a
  la API (`POST` con `X-EIM-Confirm`); la copia la hace la API (`backup create` lo gestiona).
- Varias sesiones de Claude trabajan a la vez en la carpeta principal: revisar `git status` antes
  de commitear y no mezclar cambios ajenos.
- `python -m eim.continuity publish` lanzado por Claude en modo de permisos automático se bloquea
  («exfiltración de datos») aunque el usuario lo autorice en el chat: o lo ejecuta el usuario
  (`v2\scripts\copia_externa.ps1`) o cambia al modo con aprobación y aprueba el comando.
