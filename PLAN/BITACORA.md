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
- **Abierto:** la importación manual no anota `data/share/state_*.json` (BACKLOG T125 (5)). Con `share_config.json` presente, el primer arranque de la API y de los líderes volverá a unir la misma foto (idempotente: «ya estaban») y exportará cada 6 h; en la portátil el modo automático está apagado. Revisar `share_conflicts` fila a fila (nota T117 §6.6). Este equipo no tiene copia externa ni Freqtrade.
- **En curso:** T31 (portátil), T45, T78, T104, T116, T117, T119.
- **Siguiente paso:** decidir el modo automático en `juanpablo-cpu` antes de abrir la API; la portátil hace su simulacro sobre `machine/juanpablo-cpu`; decidir si `juanpablo-cpu` opera a diario (reactivar la tarea de inicio e instalar `instalar_copia_externa.ps1`).
