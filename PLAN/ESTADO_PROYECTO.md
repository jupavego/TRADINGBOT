# Estado del proyecto (punto de entrada al cambiar de equipo)

**Actualizado:** 2026-10-30 04:00 UTC, desde `laptop-i6pf9ovp-fce8d9` (sesión T125). Actualízalo
al cerrar una sesión que cambie algo de esta página; el detalle por tarea sigue en `STATUS.md`,
lo aplazado en `BACKLOG.md` y el registro de sesiones en `BITACORA.md`. Para comprobar un equipo:
`python -m eim.continuity check` (desde `v2/`; procedimientos en `v2/docs/CONTINUIDAD.md`).

## 1. Qué corre y dónde

| Equipo | Identidad | Qué tiene | Verificado |
|---|---|---|---|
| Portátil de Santivego (`LAPTOP-I6PF9OVP`) | `laptop-i6pf9ovp-fce8d9` | Servicio continuo 24/7 desde la carpeta principal (rama `main`): API + operación en papel (corrida de T31) + bróker simulado (15 m/1 h/4 h, solo BTCUSDT), servicio de líderes (7 líderes, copia simulada), recolector de microestructura y captura HFT de BTCUSDT; copia completa diaria a las 00:00 UTC; tarea «EIM - vigilancia captura HFT». Sin variables `EIM_*` (sin claves de testnet), sin Ollama, sin Freqtrade | sí, 2026-10-30 |
| Equipo de Juan Pablo (`jupavego`) | por definir (no puede ser la de arriba) | Relleno de 6 meses del escuadrón de bots, Freqtrade en `D:/eim-bots` (FSupertrend, NFI), velas de 5 m (T58–T60) | **no** (no accesible desde la portátil) |
| `juanpablo-cpu` / otra portátil | por definir | Desconocido desde aquí | **no** |

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
| T117 Primera mezcla | Mitad de la portátil hecha; #165 fusionado y desplegado (2026-10-29); modo automático **apagado** (no hay `data/share_config.json`) | Juan Pablo: aceptar la invitación a `Santivego/eim-shared-data` **antes del 2026-11-01 ~20:14 UTC** (caduca), publicar su rama y enviar su simulacro (instrucciones en el PR #165 y en `notas/T117_primera_mezcla.md` §7); ◆ el usuario revisa los dos simulacros; después aplicar |
| T119 Escuadrón verificado | Hecha el 2026-10-29 (relleno en la base viva, PR #167 desplegado); la marca ☑ está **sin confirmar** en el worktree `t119-marcar` | Confirmar esa marca (otra sesión); queda en BACKLOG la comparación API ↔ CLI sobre una copia en caliente |
| T125 Continuidad entre equipos | Código, pruebas y documentos hechos (rama `claude/t125-continuidad-equipos`); copia local nueva verificada | ◆ Primera publicación externa (bloqueada en la sesión por permisos: la ejecuta el usuario), fusionar el PR, actualizar la carpeta principal e instalar la copia diaria; repetir la prueba de recuperación desde un clon limpio contra GitHub |

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
- La carpeta principal está 2 commits por detrás de `origin/main` (solo `BACKLOG.md`, #170).
- Cambios sin confirmar de otras sesiones en los worktrees `t117-mezcla` (notas de T117) y
  `t119-marcar` (cierre de T119); guardados también como parche en
  `v2/backups/proteccion_T125_20261030-0310/` (local).
- La experiencia publicada de la portátil es del 2026-10-25 (la primera `publish` la pone al día).

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
