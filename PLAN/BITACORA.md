# Bitácora de sesiones

Una entrada por sesión de trabajo, **añadida al final** (git une las entradas de varios equipos
sin conflicto: `merge=union` en `.gitattributes`). `python -m eim.continuity check` muestra la
más reciente por fecha y su siguiente paso. Formato:

```
## AAAA-MM-DD HH:MM UTC · <identidad del equipo> · <tarea>
- **Hecho:** …
- **Archivos:** …
- **Pruebas:** … → resultado
- **Abierto:** …
- **En curso:** …
- **Siguiente paso:** …
```

## 2026-10-30 04:00 UTC · laptop-i6pf9ovp-fce8d9 · T125 continuidad entre equipos
- **Hecho:** auditoría de dónde vive cada dato (`v2/docs/ALMACENAMIENTO.md`); copia completa nueva
  y verificada `eim_20261030-030349` (1 000 MB, 4 bases, 6,18 M filas) y la más antigua apartada en
  `v2/backups/archivo/`; parches de los worktrees con cambios ajenos + memoria de Claude guardados en
  `v2/backups/proteccion_T125_20261030-0310/`; `eim.continuity` (`check`, `publish`, `offsite`);
  arranque seguro de `eim.operation run`; tarea diaria de copia externa (scripts).
- **Archivos:** `v2/eim/continuity/*`, `v2/eim/operation/__main__.py`, `v2/eim/data/share_git.py`,
  `v2/scripts/{copia_externa,instalar_copia_externa,servicio_continuo}.ps1`, `v2/tests/continuity/*`,
  `v2/docs/{CONTINUIDAD,ALMACENAMIENTO}.md`, `PLAN/{ESTADO_PROYECTO,BITACORA,T125}.md`, `CLAUDE.md`.
- **Pruebas:** `tests/continuity` (28) + share + copias + operación → 127 verdes; `check` real contra
  la carpeta viva → CON AVISOS (copia externa aún no publicada, cambios sin confirmar de otras
  sesiones); ida y vuelta LOCAL de la copia real (1 000 MB → 326 MB en 2 partes en 64 s; descarga +
  verificación 37 s; `restore` en carpeta limpia) → filas idénticas en las 4 bases (6,18 M); clon
  limpio en otra carpeta: sin datos → NO SINCRONIZADO y `eim.operation run` sale con 3 sin crear
  bases; con los datos restaurados → CON AVISOS, sin bloqueos. Gate: ruff OK, 2 425 pruebas
  pasadas y 7 omitidas en 13 min (servicios en marcha).
- **Abierto:** la subida real a GitHub (copia externa + experiencia) la bloqueó el control de
  permisos de la sesión: la ejecuta el usuario; equipo de Juan Pablo sin verificar.
- **En curso:** T31, T45, T78, T104, T116, T117, T125.
- **Siguiente paso:** el usuario ejecuta `v2\scripts\copia_externa.ps1` en la portátil; fusionar el PR de T125, actualizar la carpeta principal e instalar la tarea diaria; en `juanpablo-cpu`, `docs/CONTINUIDAD.md` §2 y §3 A.

## 2026-10-30 14:05 UTC · laptop-i6pf9ovp-fce8d9 · T125 primera publicación real
- **Hecho:** `publish` contra la carpeta viva (con el modo de permisos con aprobación; el automático
  de Claude la bloqueaba): copia externa `eim_20261030-030349` en la versión `eim-copias` de
  `Santivego/eim-shared-data` (326 MB en 2 partes + extras) y experiencia `20261030T030349Z` en
  `machine/laptop-i6pf9ovp-fce8d9`, en 334 s. PR #171 fusionado. T125 → ☑.
- **Archivos:** `PLAN/{STATUS,BITACORA,ESTADO_PROYECTO}.md`, `PLAN/status.js`.
- **Pruebas:** `offsite list` → completa, 6 183 230 filas; `offsite pull` en una carpeta vacía (36 s,
  partes + zip + copia verificados) + `backup restore` → filas por tabla idénticas a la copia
  original en las 4 bases; extras con los 3 parches, la memoria de Claude y `data/`; `check` en la
  carpeta viva → copia externa OK (CON AVISOS solo por cambios sin confirmar de otras sesiones).
- **Desplegado (14:50 UTC, con permiso):** `git merge --ff-only origin/main` en la carpeta
  principal (sin reiniciar servicios) e `instalar_copia_externa.ps1` → tarea «EIM - copia externa
  diaria» (20:30 hora local); probada con `Start-ScheduledTask` → salida 0 en 54 s (copia ya en
  GitHub, no la vuelve a subir). El registro salía con los acentos rotos (la consola oculta usa
  ibm850): `copia_externa.ps1` fija ahora la salida de la consola a UTF-8 (llega con el PR #172).
- **Abierto:** `juanpablo-cpu` sin verificar.
- **En curso:** T31, T45, T78, T104, T116, T117, T119.
- **Siguiente paso:** fusionar el PR #172 y `--ff-only` en la carpeta principal; en `juanpablo-cpu`,
  `docs/CONTINUIDAD.md` §2 y §3 A.

## 2026-10-30 23:40 UTC · juanpablo-cpu · T125/T117 llegada del equipo, simulacro e importación
- **Hecho:** diagnóstico de `DESKTOP-93R810K`. El clon está en `C:\Users\jo\Desktop\JP\TRADINGBOT`, con `main` 19 commits atrasado y nada sin subir: las ramas locales `t106`/`t107` ya están en `origin/main`, y solo quedan sin seguir `.claude/settings.local.json` y el informe propio `v2/reports/operation/semana_2026-W43.*`. Es el **caso A** (historial propio). El modo automático de T61 apuntaba al repo viejo `jupavego/eim-shared-data` (ramas `machine/juanpablo` y `machine/juanpablo-cpu`). No hay `D:/eim-bots`. Corrían el recolector de microestructura, la captura HFT y Vite; la API, la operación y los líderes estaban parados (último latido de la operación: 2026-10-29 16:31 UTC). La tarea «EIM - servicio continuo (broker simulado)» arrancaba al iniciar sesión.
  - Respaldo en `%USERPROFILE%\EIM_respaldos\20261030-175903`. `-SoloRespaldo` se paró en su verificación (la captura HFT escribe en `micro_hft`, BACKLOG T125 (1)); los mismos pasos, completados a mano, dan 346 archivos y 432 642 449 B idénticos sin `micro_hft`, y el bundle de ramas verificado. Copia del sistema: `eim_20261030-230202` **íntegra**.
  - `git pull --ff-only` (`ebf3900` → `f44cae5`). Locks sin cambios: el simulacro de pip no instala nada, `pip check` y `npm ls` salen bien y se reinstaló el paquete editable; `npm ci` no se ejecutó porque Vite estaba en marcha.
  - Con permiso del usuario: tarea de inicio **desactivada**, `data/share_repo` apartado a `share_repo.jupavego-20261030` (BACKLOG T125 (2)), `share setup --git-url https://github.com/Santivego/eim-shared-data.git --machine juanpablo-cpu`, `export` → rama `machine/juanpablo-cpu` en Santivego (`0105753`, `20261030T231112Z`, 29 s) y `import` en simulacro (100 s).
  - Con el visto bueno del usuario al simulacro: `import --apply --from laptop-i6pf9ovp-fce8d9` con los servicios parados, sobre la misma foto (`730dce4`), en 124 s. Salieron las mismas cifras. Copia previa en `backups/pre-import_20261030T232551Z-juanpablo-cpu`; veredictos recalculados (208 intentos).
- **Archivos:** `PLAN/{BITACORA,ESTADO_PROYECTO,BACKLOG}.md`.
- **Pruebas:**
  - `backup verify` → 4 bases, 561 909 filas (reports 116 631, paper 18 716, leaders 232 639, obs 193 923).
  - `eim.continuity check` → **CON AVISOS**: 2 archivos sin confirmar y sin copia externa propia; datos, copias, código (`main @ f44cae5`) y seguridad OK.
  - `git ls-remote` de Santivego antes del export: solo `machine/laptop-i6pf9ovp-fce8d9` (identidad libre). Después: más `machine/juanpablo-cpu`. La rama del repo viejo no cambió (`a54bc4f`).
  - Simulacro desde `laptop-i6pf9ovp-fce8d9` `20261030T030349Z` (nuevas / ya estaban / conflicto / incompat.): reports 12 517 / 589 / 1 242 / 0 · sim_trades 41 / 3 / 1 / 0 · paper_ctx 35 499 / 8 / 3 449 / 0 · val_versions 0 / 191 / 0 / 0 · val_windows 104 / 87 / 0 / 0 · leaders 15 / 0 / 0 / 0 · leader_fills 2 807 174 · leader_funding 35 772 · leader_leverage 4 · leader_positions 35 444 · leader_follow 2 129 264 · leader_recon 87 924 · leader_gaps 16 623 · copy_journal 33 992 (líderes: todo nuevas). **Total: 5 194 373 nuevas, 878 ya estaban, 4 692 en conflicto, 0 incompatibles.** Las bases y los WAL no cambiaron (mismos bytes y fechas).
  - Gate: ruff OK; 2 425 pruebas pasadas, 7 omitidas y 0 fallidas en 13,4 min, con el recolector y la captura HFT en marcha.
  - Tras aplicar, cada tabla importada creció exactamente en sus «nuevas»: líderes +5 146 212, paper_ctx +35 499, reports +12 517, val_windows +104, sim_trades +41. `share_conflicts` sumó +1 243 (reports) y +3 449 (paper). El recálculo añadió 104 `val_verdicts`, 486 filas de `paper_ledger` y 1 `paper_view_snapshot`. `backup verify` de `eim_20261030-232849` → **íntegra**, 10 955 952 filas (reports 142 992, paper 93 965, leaders 10 525 072, obs 193 923). `leaders.duckdb` pasó de 88 MB a 1,27 GB.
  - Arranque (con permiso, 23:35 UTC). Modo automático **apagado** antes, como en la portátil: `share_config.json` apartado, y `GET /v2/share/status` → `enabled: false`. `servicio_continuo.ps1 -ConWeb` lanzado por WMI. API sana en 8 s (`SIMULADO`, «operando», 19 agentes). El primer ciclo del bróker falló al leer una hora de microestructura que la operación compactaba en ese instante (`micro_compactada`, 23:37:43); el reintento se puso al día con ~31 h de velas en ~17 min, y el cierre de las 00:00 UTC se analizó solo (15m/1h/4h, sin error). Operación: 23 ciclos, 0 fallos. Líderes: 17/17 listos y tablero fresco. Arbitraje: escaneo cada ~11 s. Microestructura y HFT con latido (`dropped` 0). Proyección con 3 escenarios. Operaciones sugeridas: «sin validadas» (89 en observación, 15 rechazadas; puerta T49). La interfaz se dibuja «EN VIVO»; vista del bróker: 38 914 velas (1 105 en vivo) y 270 operaciones, 77 % ganadas. Tras abrir la interfaz se resolvieron los avisos «sin latido» de precio en vivo y difusor. Siguen degradados por datos, como antes del reinicio: liquidaciones (cobertura 54 %), microestructura (huecos de secuencia), VWAP mensual parcial y literatura. Hoja de ruta viva republicada (`build_roadmap.py`: 125 tareas, 79 hechas).
- **Abierto:** la importación manual no anota `data/share/state_*.json` (BACKLOG T125 (5)); con el modo automático apagado no hace falta. Revisar `share_conflicts` fila a fila (nota T117 §6.6). Este equipo no tiene copia externa ni Freqtrade.
- **En curso:** T31 (portátil; aquí corre una operación en papel propia), T45, T78, T104, T116, T117, T119.
- **Siguiente paso:** la portátil hace su simulacro sobre `machine/juanpablo-cpu`; decidir si `juanpablo-cpu` opera a diario (reactivar la tarea de inicio e instalar `instalar_copia_externa.ps1`, que también publica su experiencia).

## 2026-10-31 07:18 UTC · juanpablo-cpu · T31/T78/T116/T117/T119 tareas en curso desde este equipo
- **Hecho:** por decisión del usuario, las tareas que estaban en curso en la portátil siguen desde aquí.
  - **Operación diaria:** la tarea «EIM - servicio continuo (broker simulado)» está reactivada (al iniciar sesión) y se instaló «EIM - copia externa diaria» (20:30 hora local, ~01:30 UTC). La primera copia externa, a mano, es `eim_20261030-232849` (581 MB en 3 partes). La exportación de la experiencia falló con HTTP 408 al subir 243 MB, y el reintento dijo «PUBLICADO» sin subir nada (BACKLOG T125 (6)). Se subió a mano con `http.postBuffer` grande → `machine/juanpablo-cpu` = `87a7426`.
  - **T31:** corrida propia de este equipo desde el 2026-10-30 23:35 UTC hasta el 2026-11-27. La de la portátil sigue en paralelo.
  - **T117:** desde aquí se comprobó la idempotencia y se hizo el simulacro en sentido portátil. La unión es conmutativa.
  - **T119 ☑:** la API y la CLI dan la misma puntuación.
  - **Copias de `leaders.duckdb`:** las copias en caliente `eim_20261031-000042` y `-002221` salieron **sin `leaders.duckdb`**: la instantánea del servicio de líderes se quedó sin memoria con el tope de 1 GB y una base de 1,27 GB. Con permiso: `EIM_DUCKDB_MEMORY=2GB` (variable de usuario) y reinicio solo del servicio de líderes. La API, la operación, el bróker y los recolectores siguieron en marcha y `/v2/health` respondió `ok` todo el rato. Resultado: `eim_20261031-005644` completa (BACKLOG T125 (7)).
  - **T78:** contraste con la QC de la portátil (viaja en su copia externa `eim_20261030-030349`). Aquí rinde mejor; lo que le resta horas es la carga local. Ventana de 72 h: del 2026-10-31T08 al 2026-11-03T07 UTC (72 horas completas: de las 08:00 UTC del 31-oct a las 08:00 UTC del 3-nov), abierta tras los gates de T116 y la copia externa repetida.
  - **T116:** las 3 corridas «con Ollama real» que quedaban pendientes, con `qwen3:4b` generando sin parar y los servicios en marcha. **No salen verdes**, pero todos los fallos son de pruebas con plazo de tiempo o latidos.
  - **Copia diaria del 2026-10-31:** la tarea de las 01:36 UTC falló por la carga de T116: TLS con GitHub agotado, `git ls-remote` a 300 s y `git rev-parse` a 60 s (BACKLOG T125 (8)). La copia local de ese día quedó verificada. Repetida a mano a las 07:09 UTC (la misma copia diaria aprobada): `eim_20261031-005644` subida (589 MB en 3 partes, con líderes) y experiencia `20261031T005644Z` publicada, `machine/juanpablo-cpu` = `35cc71e` (comprobado con `git ls-remote`). Su *bundle* de ramas solo locales falló por una ruta relativa (BACKLOG T125 (9)).
  - **Suspensión:** a petición del usuario se comprobó que no detiene los procesos. Plan «Alto rendimiento»: suspender e hibernar «Nunca», con corriente y con batería; 0 suspensiones, reanudaciones o reinicios en las 24 h previas. Windows Update sin reinicio pendiente (horas activas 8–17 hora local). La app de Claude mantiene el equipo despierto mientras trabaja. No se cambió ningún ajuste del sistema.
- **Archivos:** `PLAN/{BITACORA,STATUS,ESTADO_PROYECTO,BACKLOG}.md` y la hoja de ruta regenerada.
- **Pruebas:**
  - T117, idempotencia: la misma foto sobre la copia posterior da 0 nuevas en las 14 tablas. Sentido portátil (copia `eim_20261030-030349` y exportación `20261030T232849Z`): 217 084 nuevas, 5 195 251 ya estaban (= lo aplicado aquí), los mismos 4 692 conflictos y 0 incompatibles.
  - T119: API viva (`GET /v2/bots/scorecard`, corte 00:00 UTC, `vigente`) frente a la CLI sobre la copia en caliente `eim_20261031-002221` (corte 00:15 UTC). Mismos 24 intentos de Holm (id, veredicto, n, p bruto, p Holm, retirado, control), mismos estados por bot y mismo resumen (11 informan, 0 votan).
  - Copia `eim_20261031-005644`: `backup verify` → **íntegra**, 1 565 MB, líderes 10 589 988 filas. La instantánea de líderes tardó 410 s con el equipo cargado.
  - T78: antes de la ventana, 19 de 32 horas completas (59 %). En las 11 horas en que capturaban los dos equipos (28-oct 23 UTC a 30-oct 01 UTC), la portátil completó 0 (24–122 silencios por hora) y este equipo 6 de las 9 que llevaba capturando. Las 2 horas que fallan en ambos (28-oct 23 y 29-oct 23 UTC, con desconexiones) son eventos de Binance.
  - T116: 3 corridas de 00:32 a 03:38 UTC con 324 generaciones de Ollama. `ruff` limpio en las 3. `pytest`: 2, 1 y 10 fallos, en 63,8, 36,2 y 85,8 min (las de la portátil, 11–20 min). Fallan `test_emit` (sobrecarga del ciclo, las 3; dos procesos), `test_obs_api` (100k eventos), `test_hft_risk` (p99), 3 de `test_service_heartbeats` y 3 de `test_paper_api`. Los 11 casos pasan aislados en 63 s con los servicios en marcha.
- **Abierto:** BACKLOG T125 (6)–(9). T116: decidir si el gate debe aguantar Ollama generando (margen de las pruebas con plazo). T117: revisar `share_conflicts` fila a fila. La copia externa diaria (~01:30 UTC) cae dentro de la ventana de T78. Conviene pausar Windows Update durante la ventana: lo hace el usuario.
- **En curso:** T31 (aquí y en la portátil), T45, T78 (ventana del 2026-10-31T08 al 2026-11-03T07 UTC (72 horas completas: de las 08:00 UTC del 31-oct a las 08:00 UTC del 3-nov), abierta tras los gates de T116 y la copia externa repetida), T104, T116, T117.
- **Siguiente paso:** al cerrar la ventana de T78, leer `data/micro_hft/qc/symbol=BTCUSDT/summary.json` y anotar la aceptación en `STATUS.md`. Después, T104 (corte de red provocado y línea base de 7 días) y T116 con el equipo descargado (◆ permiso para parar servicios).

## 2026-11-01 21:40 UTC · juanpablo-cpu · T126 director de recursos (fase 1)
- **Hecho:** a pedido del usuario, diagnóstico de por qué fallan las corridas de días en este equipo (i5-6400, 4 núcleos, 16 GB) y fase 1 del arreglo en la rama `claude/t126-director-fase1`, **sin desplegar** (los servicios en marcha no se tocaron).
  - **Diagnóstico** (detalle en `PLAN/T126.md`):
    - La ventana de 72 h de T78 se perdió el 31-oct a las 13–14 UTC, cuando el equipo se saturó con la prueba de un modelo de visión de T62.
    - A las 21:46 UTC hubo un apagado forzado: botón de encendido durante una suspensión, con el inicio rápido activo.
    - Después, ~23 h sin servicios: las tareas del EIM solo arrancan al iniciar sesión.
    - La tarea programada dejaba los 26 procesos del EIM en BELOW_NORMAL, captura incluida, por debajo de cualquier programa abierto.
    - 34 alertas falsas de latido al día.
    - Restos de pruebas de juegos (NVIDIA Overlay, FrameView SDK) a decisión del usuario.
  - **Prioridades por nivel** (`eim/operation/priority.py`): captura en vivo en ABOVE_NORMAL, API, líderes y vigilantes en BELOW_NORMAL, mantenimiento, gate, copias y Ollama en IDLE. Se activa solo con `EIM_PRIORITY=on` (lo fija `servicio_continuo.ps1`). Para trabajos a mano: `python -m eim.operation.priority run batch -- <orden>`.
  - **Cadencias reales en el catálogo:** almacén de velas 3600 s y bróker 300 s.
  - **Arranque al encender:** `instalar_inicio_automatico.ps1 -AlEncender` registra una tarea S4U, sin necesidad de iniciar sesión. El lanzador ya no duplica nada con dos arranques a la vez.
  - **T78 por racha:** `hft_ops --streak` y `t78_streak` en el resumen. La mejor racha real es de 9 h (31-oct 04–12 UTC).
- **Archivos:**
  - `v2/eim/operation/priority.py` y los 9 puntos de arranque (`api/main.py`, `collectors/{binance_ws,hft_ws,liq_ws,supervise,hft_supervise}.py`, `leaders/cli.py`, `operation/__main__.py`).
  - `v2/eim/data/collectors/hft_ops.py` y `v2/eim/observability/catalog/components_flow.py`.
  - `v2/scripts/{servicio_continuo,instalar_inicio_automatico}.ps1`.
  - `v2/tests/{operation/test_priority,data/test_hft_streak}.py` y `v2/tests/observability/test_obs_alerts.py`.
  - `v2/docs/OPERACION.md`, `CLAUDE.md`, `PLAN/{T126,STATUS,BACKLOG,ESTADO_PROYECTO,BITACORA}.md` y la hoja de ruta.
- **Pruebas:** gate con la herramienta nueva (`priority run batch`, el intérprete real en IDLE, comprobado en vivo) y los servicios en marcha: ruff limpio; 2 436 pasadas, 7 omitidas y 0 fallidas en 12 min 39 s. Pruebas nuevas: niveles en subprocesos (la captura sube, el mantenimiento baja y se restaura, la API queda en BELOW_NORMAL, `run` deja a los hijos en IDLE), todo papel declarado con nivel, racha de T78 (5) y las dos alertas sin saltar a su ritmo normal. Los dos scripts se analizan sin errores, y la detección del vigilante de la API y de Vite encuentra los procesos reales. Racha calculada sobre los JSON de QC de la carpeta viva (solo lectura): 57 horas auditadas, la mejor de 9 h.
- **Abierto:** ◆ desplegar (reiniciar los servicios con el código nuevo) y registrar la tarea al encender desde una consola de administrador. Ajustes de Windows del usuario: inicio rápido, botón de encendido y, opcionalmente, exclusión de `v2\data` en Defender. Fases 2–3 en BACKLOG T126.
- **En curso:** T31, T45, T78 (sin ventana fija: por racha), T104, T116, T117, T126.
- **Siguiente paso:** con permiso del usuario, fusionar el PR, `git merge --ff-only origin/main` en la carpeta principal, reiniciar los servicios por la tarea y comprobar las clases de prioridad. Después, dejar correr la captura y leer `hft_ops --streak` hasta las 72 h.

## 2026-11-01 21:40 UTC · juanpablo-cpu · T126 despliegue de la fase 1
- **Hecho:** con permiso del usuario se desplegó la fase 1.
  - PR #175 fusionado (`efda32c`) y `git merge --ff-only origin/main` en la carpeta principal.
  - A las 21:34 UTC se detuvieron los 4 vigilantes y luego sus 5 servicios: 18 procesos con su lanzador, ninguno quedó vivo.
  - Se relanzó todo con `Start-ScheduledTask` de la tarea de inicio de sesión (resultado 0). Vite, la hoja de ruta, el icono y «equipo despierto» siguieron en marcha y el script no los duplicó.
- **Archivos:** `PLAN/{BITACORA,STATUS,ESTADO_PROYECTO,BACKLOG}.md`.
- **Pruebas:**
  - Prioridades medidas en los procesos reales: `binance_ws`, `hft_ws` y `liq_ws` en **AboveNormal**; la API, `leaders run`, los vigilantes y `eim.operation run` en **BelowNormal**. Antes estaban los 18 en BelowNormal.
  - La API respondió `ok` en SIMULADO, «operando», con 19 agentes, a los 12 s; 4 ciclos sin error y 0 reinicios.
  - A los 4 min: latidos de líderes 11 s y bróker 51 s, sin error. Captura HFT sincronizada, 0 mensajes perdidos, 0 silencios y 1/1 verificación del libro igual a Binance.
  - Un solo Vite, una sola hoja de ruta y un solo vigilante de la API.
  - Alertas al arrancar: «Precio en vivo» y «Difusor» sin latido, que salen en cada arranque hasta que se abre la interfaz, y «Protección en estado inconsistente: agresivo BTCUSDT», el diario de T110 que se repite en cada arranque desde el 31-oct. Ninguna la causa T126.
- **Abierto:** ◆ registrar `instalar_inicio_automatico.ps1 -AlEncender` desde una consola de administrador. Ajustes de Windows del usuario. Fases 2–3 en BACKLOG T126. La hora 21 UTC del 1-nov saldrá incompleta por el reinicio.
- **En curso:** T31, T45, T78 (por racha desde las 22 UTC del 1-nov), T104, T116, T117, T126.
- **Siguiente paso:** leer `python -m eim.data.collectors.hft_ops --root data --streak` a diario; T78 se cumple en cuanto la racha llegue a 72 h, como pronto el 2026-11-04 22 UTC.

## 2026-11-01 21:55 UTC · juanpablo-cpu · T126 tarea al encender
- **Hecho:** el usuario registró «EIM - servicio continuo al encender» desde una consola de administrador. Comprobado: estado `Ready`, S4U con el usuario `jo`, nivel limitado, disparo al arrancar con 2 min de retraso y la acción de `servicio_continuo.ps1 -ConWeb`. La tarea de inicio de sesión se conserva.
- **Pruebas:** `Start-ScheduledTask` con los servicios en marcha. Salió con código 0 en ~3 s: 23 procesos del EIM antes y 23 después, ninguno nuevo y ninguno parado. El registro operativo del Programador está desactivado (lo normal en Windows 10), así que no hay más rastro de la ejecución.
- **Abierto:** el arranque desde cero sin sesión iniciada solo se verá en el próximo reinicio real. Si Vite no levanta (PATH de `npm` en S4U), la interfaz llega al iniciar sesión. Los ajustes de Windows siguen pendientes del usuario.
- **Siguiente paso:** tras el próximo reinicio, comprobar que los servicios arrancaron antes de iniciar sesión (`proceso_lanzado` en `data/operation/logs/op-*.jsonl` unos 2 min después del arranque).

## 2026-11-01 22:00 UTC · juanpablo-cpu · T126 ajustes de Windows
- **Hecho:** el usuario hizo los ajustes de Windows (Claude no cambia ajustes del sistema; solo los comprobó). Desactivó el inicio rápido: `HiberbootEnabled` 0, leído del registro. Excluyó `C:\Users\jo\Desktop\JP\TRADINGBOT\v2\data` del análisis de Defender, comprobado en su captura de Seguridad de Windows. El botón de encendido sigue en «Apagar» (`PBUTTONACTION` 3), que sin inicio rápido es un apagado completo.
- **Causa del 31-oct confirmada:** con el botón en «Apagar» y el inicio rápido activo, pulsarlo inicia una hibernación del núcleo. Por eso el evento 41 marca `SleepInProgress=1`: esa transición se colgó y la segunda pulsación cortó la corriente.
- **Archivos:** `PLAN/{ESTADO_PROYECTO,T126,BITACORA}.md`.
- **Abierto:** ver el primer reinicio real (servicios ~2 min tras encender, sin iniciar sesión). Restos de juegos en NVIDIA App a decisión del usuario.
- **Siguiente paso:** seguir la racha de T78 con `hft_ops --streak`.

## 2026-11-01 22:15 UTC · juanpablo-cpu · T126 en la hoja de ruta
- **Hecho:** a pedido del usuario, el director de recursos entra en la hoja de ruta con su avance. Nueva fase 21 «Capacidad del equipo y procesos largos» con T126 (fase 1, ☑), T127 (fase 2: registro de consumo y cola de trabajos pesados con pausa, reanudación y puntos de control) y T128 (fase 3: un recolector por fuente, retención de líderes, ganchos fuera de la API, menos ruido; ◆ qué historial de líderes se conserva y qué restos se borran). Los ítems de la línea T126 del BACKLOG quedan repartidos entre las dos.
- **Archivos:** `PLAN/{T126,T127,T128,STATUS,00_MASTER,BACKLOG,ESTADO_PROYECTO,BITACORA}.md`, `PLAN/roadmap.html`, `PLAN/status.js`.
- **Pruebas:** `build_roadmap.py` sin tareas huérfanas (128 tareas, 81 hechas); hoja de ruta viva comprobada en el navegador.
- **Siguiente paso:** T127 y T128 están «Listas»; empezar por T127, antes comprobando el primer reinicio real.

## 2026-11-01 22:45 UTC · juanpablo-cpu · T126 prueba del reinicio y del arranque desde la sesión 0
- **Hecho:**
  - **Reinicio real a pedido del usuario** (arranque a las 22:08:34 UTC). Windows inició sesión solo a los 8 s (inicio de sesión automático tras un reinicio voluntario), así que actuó la tarea de inicio de sesión: vigilante a las 22:09:57 y API a las 22:10:46. La tarea al encender, a las 22:10:10, esperó el cerrojo y no lanzó nada (salida 0). Al arrancar se disparó también la copia externa diaria, que el 31-oct no llegó a correr: `eim_20261101-221145` publicada (622 MB, salida 0, 733 s).
  - **Arranque en frío desde la sesión 0**, simulado con permiso del usuario. Se detuvieron los 25 procesos (servicios, Vite y «equipo despierto») a las 22:25:03 UTC y se lanzó a mano la tarea al encender. En 19 s escuchaban la API y Vite (salida 0), y luego quedaron API `ok`, líderes, captura HFT sincronizada (1/1 verificación) e identidad `juanpablo-cpu`, sin errores en los registros. Todo en la sesión 0, con la prioridad base correcta: 3 procesos en AboveNormal (los recolectores) y 17 en BelowNormal.
  - **Hallazgo:** desde la sesión del usuario no se puede leer la línea de órdenes, la prioridad ni la hora de inicio de los procesos de la sesión 0 (sí la prioridad base por WMI, los puertos y los cerrojos). `servicio_continuo.ps1` detectaba los servicios por la línea de órdenes, así que al iniciar sesión después de un arranque en frío habría lanzado otro recolector de liquidaciones (sin cerrojo: dos escritores) y otro «equipo despierto». El resto lo frenaban sus cerrojos o los puertos, pero tocando sus registros abiertos.
  - **Arreglo:** cerrojo de instancia en `liq_ws` y en `eim.operation run`, cerrojo global en `mantener_despierto.ps1`, y `Ocupado` en el lanzador, que consulta el cerrojo de cada servicio (visible desde cualquier sesión) antes de lanzarlo. Si el cerrojo global del lanzador no se puede abrir, espera 30 s.
- **Archivos:** `v2/eim/data/collectors/liq_ws.py`, `v2/eim/operation/__main__.py`, `v2/scripts/{servicio_continuo,mantener_despierto}.ps1`, `v2/tests/operation/test_instance_locks.py`, `PLAN/{STATUS,ESTADO_PROYECTO,T127,BITACORA}.md`.
- **Pruebas:** la comprobación `Ocupado` contra los cerrojos reales de la sesión 0 da ocupados los 5 que existían y libre un archivo de prueba. 3 pruebas nuevas (vigilante duplicado, liquidaciones duplicadas, y `Ocupado` de PowerShell frente a `instance_lock` de Python) más las relacionadas: 31 pasadas. Los dos scripts se analizan sin errores. Gate en Idle con los servicios en marcha: ruff limpio; 2 439 pasadas, 7 omitidas y 0 fallidas en 14 min 12 s.
- **Abierto:** ◆ desplegar (reiniciar los servicios; hoy corren en la sesión 0 con el código anterior, sin el cerrojo de liquidaciones: no cerrar ni abrir sesión hasta desplegar). La racha de T78 cuenta desde las 23 UTC del 1-nov.
- **Siguiente paso:** fusionar, desplegar y comprobar que una ejecución de la tarea de inicio de sesión con todo en marcha no lanza nada.

## 2026-11-02 02:55 UTC · juanpablo-cpu · T126 despliegue de los cerrojos de instancia (PR #180)
- **Hecho:**
  - Fusionado el PR #180 (`d23d030`) con permiso del usuario, y main actualizada en la carpeta principal.
  - **Detener los servicios de la sesión 0:** desde la sesión del usuario, sin elevar, `Stop-Process` dio «Acceso denegado» en los 25 procesos y no se detuvo ninguno. El usuario ejecutó, en un PowerShell de administrador, un script de un solo uso: detiene los procesos del usuario en la sesión 0 (vigilantes antes que sus hijos), relanza con la tarea al encender y espera a la API.
  - **Relanzado** a las 02:48:07 UTC en la sesión 0: 25 procesos, 3 recolectores en AboveNormal y el resto en BelowNormal; los 5 cerrojos (vigilantes de la API, líderes, microestructura y HFT, y liquidaciones) tomados, y los de la API y las liquidaciones solo existen con el código nuevo. API `ok` (19 agentes, SIMULADO, operando), interfaz y hoja de ruta escuchando.
  - **Prueba sin duplicados:** la tarea de inicio de sesión, lanzada con todo en marcha, terminó en 8 s (salida 0) con los mismos 26 procesos y sin reabrir ningún registro. El lanzador, ejecutado a mano, da «ya corre: no se lanza otro» en cada servicio; el segundo «equipo despierto» sale por su cerrojo global.
- **Archivos:** `PLAN/{STATUS,ESTADO_PROYECTO,T127,BITACORA}.md`, `v2/docs/OPERACION.md`.
- **Pruebas:** las del PR #180 (gate verde: 2 439 pasadas, 7 omitidas) y las comprobaciones de arriba.
- **Abierto:**
  - **Parar los servicios de la sesión 0 sin elevar:** «Parar servicio» del icono no los alcanza (entregable 5 de T127).
  - Avisos tras el arranque, ninguno del despliegue: dos «sin latido» transitorios (precio en vivo y difusor de la API) y la alerta de protección inconsistente de BTCUSDT, que sale en cada arranque desde el 31-oct.
  - El lanzador avisa de que Ollama no está instalado (`Z:\Ollama`, la unidad Z: no existe): el agente de contexto queda «sin datos».
  - **Racha de T78:** iba en 3 h (23 a 01 UTC); el corte de ~1 min deja incompleta la hora de las 02, así que cuenta de nuevo desde las 03 UTC del 2-nov y se cumple como pronto el 5-nov a las 03 UTC.
- **Siguiente paso:** dejar correr la captura; revisar la racha con `hft_ops --streak`.
