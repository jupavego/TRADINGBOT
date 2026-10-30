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
- **Abierto:** la carpeta principal va 6 commits por detrás de `origin/main` (sin `eim/continuity`);
  la tarea diaria no está instalada; `juanpablo-cpu` sin verificar.
- **En curso:** T31, T45, T78, T104, T116, T117, T119.
- **Siguiente paso:** con permiso, `git merge --ff-only origin/main` en la carpeta principal (no
  reinicia nada) y `powershell -ExecutionPolicy Bypass -File v2\scripts\instalar_copia_externa.ps1`;
  en `juanpablo-cpu`, `docs/CONTINUIDAD.md` §2 y §3 A.
