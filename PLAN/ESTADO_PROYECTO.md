# Estado del proyecto (punto de entrada al cambiar de equipo)

**Actualizado:** 2026-10-30 23:40 UTC, desde `juanpablo-cpu` (llegada del equipo, T117/T125). Actualízalo
al cerrar una sesión que cambie algo de esta página; el detalle por tarea sigue en `STATUS.md`,
lo aplazado en `BACKLOG.md` y el registro de sesiones en `BITACORA.md`. Para comprobar un equipo:
`python -m eim.continuity check` (desde `v2/`; procedimientos en `v2/docs/CONTINUIDAD.md`).

## 1. Qué corre y dónde

| Equipo | Identidad | Qué tiene | Verificado |
|---|---|---|---|
| Portátil de Santivego (`LAPTOP-I6PF9OVP`) | `laptop-i6pf9ovp-fce8d9` | Servicio continuo 24/7 desde la carpeta principal (rama `main`): API + operación en papel (corrida de T31) + bróker simulado (15 m/1 h/4 h, solo BTCUSDT), servicio de líderes (7 líderes, copia simulada), recolector de microestructura y captura HFT de BTCUSDT; copia completa diaria a las 00:00 UTC; copia externa diaria en `eim-copias` a las 20:30 hora local (tarea «EIM - copia externa diaria», desde el 2026-10-30); tarea «EIM - vigilancia captura HFT». Sin variables `EIM_*` (sin claves de testnet), sin Ollama, sin Freqtrade | sí, 2026-10-30 |
| Equipo de Juan Pablo (`jupavego`) con Freqtrade | desconocida; **no** es `juanpablo-cpu` (allí no hay `D:/eim-bots`). En el repo viejo `jupavego/eim-shared-data` hay una rama `machine/juanpablo` (última foto 2026-10-22) que `juanpablo-cpu` importó ese día; no está en Santivego | Relleno de 6 meses del escuadrón de bots, Freqtrade en `D:/eim-bots` (FSupertrend, NFI), velas de 5 m (T58–T60) | **no** |
| `DESKTOP-93R810K` (Juan Pablo) | `juanpablo-cpu` | Clon en `C:\Users\jo\Desktop\JP\TRADINGBOT` (`main`). Historial propio: 4 bases, 561 909 filas (copia `eim_20261030-230202` verificada); tras importar la experiencia de la portátil, 10 955 952 filas (`eim_20261030-232849` verificada; `leaders.duckdb` 1,27 GB). En marcha: recolector de microestructura y captura HFT de BTCUSDT. **Parados**: API, operación en papel y líderes. Tarea «EIM - servicio continuo (broker simulado)» **desactivada** el 2026-10-30 con permiso (arrancaba la operación en papel al iniciar sesión). Experiencia en `machine/juanpablo-cpu` de Santivego; `share_config.json` → Santivego (modo automático: al arrancar, la API y los líderes vuelven a unir la foto de la portátil, sin cambios, y exportan cada 6 h). Sin copia externa, sin claves de testnet, `EIM_OLLAMA_EXE` definido, sin Freqtrade | sí, 2026-10-30 |

Modo: **SIMULADO** en todo (API: `mode: SIMULADO`). Dinero real imposible: `REAL` prohibido por la
configuración de riesgo; la puerta de edge (T27) **NO PASA**.

## 2. Tareas en curso y su siguiente paso

| Tarea | Estado real | Siguiente paso |
|---|---|---|
| T31 Paper trading | Corrida continua en la portátil; informes semanales en `v2/reports/operation/` (el de la semana 43 está sin versionar en la carpeta principal) | Seguir la corrida (≥ 4 semanas) y cerrarla con su informe; espera tiempo de calendario |
| T45 Arbitraje | 3/3 escenarios en el bróker simulado (sin cuenta de Binance, decisión 2026-10-18) | Pendientes en `BACKLOG.md` (T45) |
| T78 Captura HFT | Corrida de 72 h del 24–27 oct **NO CUMPLE** el criterio estricto (hora 2026-10-25T20, 98,9 %; decisión del usuario 2026-10-25). PR #162 fusionado pero **no desplegado** | ◆ Desplegar #162 (reiniciar el árbol HFT tras un volcado, con permiso) y arrancar una corrida nueva de 72 h (mejor con cable de red); actualizar `PID, STARTED, FIRST_HOUR, LAST_HOUR, END` de `v2/data/micro_hft/vigilancia/vigilar_hft.py` y anotar las cifras finales en `STATUS.md` |
| T104 Microestructura | En vivo desde 2026-10-23 (ruta `/public`) | La cierra T120 |
| T116 Gate estable | 6 corridas verdes (11–20 min con servicios) | 3 corridas con el equipo descargado y 3 con Ollama real en el equipo de referencia |
| T117 Primera mezcla | Mitad de la portátil hecha; #165 fusionado y desplegado (2026-10-29); en la portátil, modo automático **apagado** (no hay `data/share_config.json`). Juan Pablo aceptó la invitación (permiso WRITE); `juanpablo-cpu` publicó `machine/juanpablo-cpu` (`0105753`, exportación `20261030T231112Z`) y su simulacro de lo de la portátil está en `BITACORA.md` (2026-10-30 23:40). Con el visto bueno del usuario, la importación de la portátil quedó **aplicada en `juanpablo-cpu`** (2026-10-30 23:25 UTC, a mano con los servicios parados: 5 194 373 filas nuevas, 4 692 conflictos, 0 incompatibles) | La portátil hace su simulacro sobre `machine/juanpablo-cpu` (§6.4 de la nota) → ◆ → aplicar allí. En `juanpablo-cpu`: revisar `share_conflicts` (1 243 en reports, 3 449 en paper) y decidir el modo automático antes de abrir la API |
| T119 Escuadrón verificado | Hecha el 2026-10-29 (relleno en la base viva, PR #167 desplegado); la marca ☑ está **sin confirmar** en el worktree `t119-marcar` | Confirmar esa marca (otra sesión); queda en BACKLOG la comparación API ↔ CLI sobre una copia en caliente |
| T125 Continuidad entre equipos | Hecha y desplegada el 2026-10-30 (PR #171): primera copia externa y experiencia publicadas y recuperadas desde GitHub en una carpeta vacía con filas idénticas; tarea diaria instalada y probada | `juanpablo-cpu` revisado el 2026-10-30 (`check` CON AVISOS, §3 A hasta el simulacro); le falta su copia externa (`copia_externa.ps1` + `instalar_copia_externa.ps1`) si va a operar a diario |

Pendientes destacadas: T120 (recolectores sin «sin datos»), T121 (documentación y variables),
T123 (colas acotadas), T124 (instantáneas de datos), T46, T62–T71 (motores locales y video),
T79–T86 (HFT), T87–T103 (multiactivo). Orden sugerido en `00_MASTER.md` (fase 20).

## 3. Problemas conocidos sin resolver

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
