# Continuidad entre equipos (T125)

Objetivo: pasar de un equipo a otro (portátil de Santivego `laptop-i6pf9ovp-fce8d9`, la otra
portátil, `juanpablo-cpu`) y encontrar el mismo proyecto al día, sin depender de un equipo ni de
la memoria de una conversación. Qué vive dónde: `docs/ALMACENAMIENTO.md`. Primera instalación de
un equipo: `ONBOARDING.md` + `docs/MIGRACION_EQUIPO.md`.

## 1. Tres canales, una fuente oficial cada uno

| Canal | Qué lleva | Fuente oficial | Comando |
|---|---|---|---|
| **Código** | código, documentos, tareas (`PLAN/`), parámetros y perfiles versionados | GitHub `jupavego/TRADINGBOT` (público) | `git pull` · ramas + PR |
| **Experiencia** | historial que se **une** entre equipos (backtests, operaciones simuladas, contextos, intentos de validación, líderes) | rama `machine/<id>` de cada equipo en el repo privado `Santivego/eim-shared-data` | `python -m eim.data.share export/import` (T61/T117) |
| **Copia completa** | las bases tal cual + kill-switch + estado del servicio + extras (cambios sin confirmar, memoria de Claude, estado pequeño) | versión `eim-copias` del mismo repo privado | `python -m eim.continuity publish` · `offsite pull` |

Y dos comandos que los atan (desde `v2/`):
- `python -m eim.continuity check` — **al llegar**: ¿está al día este equipo? No modifica nada.
- `python -m eim.continuity publish` — **al irse** (y cada día solo): copia → verificar → copia
  externa → experiencia → aviso del código sin subir.

Código y datos se sincronizan por separado a propósito: `git pull` nunca toca `v2/data`, y
`share import`/`backup restore` nunca tocan el código.

## 2. Al llegar a un equipo (cada vez)

1. **Entorno y código.** En la carpeta del clon, PowerShell:
   ```powershell
   git fetch
   git status
   ```
   Si hay trabajo sin confirmar o ramas sin subir **de ese equipo**, no las pises: guárdalas
   primero (`v2\scripts\actualizar_colaborador.ps1 -SoloRespaldo`) o súbelas a una rama. Después
   `v2\scripts\actualizar_colaborador.ps1` (respaldo, `git pull --ff-only`, dependencias, gate).
2. **Comprobación** (desde `v2/`, con el Python del entorno virtual):
   ```powershell
   .venv\Scripts\python.exe -m eim.continuity check
   ```
   Recorre entorno, fuente central (git y copia externa), código, datos, copias, tareas y
   seguridad. Veredicto: **LISTO** (0), **CON AVISOS** (2: se puede seguir sabiendo qué falta) o
   **NO SINCRONIZADO** (1: no sigas). Deja registro en `data/continuity/checks.jsonl`.
   Bloquea, entre otras cosas, si no llega a GitHub, si `v2/data` no tiene historial, si los datos
   son más viejos que la copia ya publicada de ese mismo equipo o si otro equipo publica con la
   misma identidad.
3. **Datos**: §3.
4. **Tareas**: `PLAN/ESTADO_PROYECTO.md` (estado, decisiones, errores abiertos, siguiente paso),
   `PLAN/STATUS.md`, `PLAN/BACKLOG.md` y la última entrada de `PLAN/BITACORA.md` (`check` la
   muestra). Claude lo lee solo (protocolo de `CLAUDE.md`).
5. **Arranque**: solo con el veredicto sin BLOQUEO. `eim.operation run` (lo que lanzan el icono y
   `servicio_continuo.ps1`) se niega a arrancar sobre una carpeta sin historial; en una instalación
   nueva a propósito: `servicio_continuo.ps1 -DatosNuevos`.

## 3. Recuperar los datos según el caso

**A. El equipo ya tiene su propio historial** (p. ej. `juanpablo-cpu`, con su relleno de 6 meses
y FSupertrend/NFI): **no restaurar encima**; se une la experiencia de los demás. Es el paso 3 de
`PLAN/notas/T117_primera_mezcla.md` §7: con la API y los líderes detenidos,
```powershell
git ls-remote https://github.com/Santivego/eim-shared-data.git      # alias libres
python -m eim.data.share setup --git-url https://github.com/Santivego/eim-shared-data.git --machine juanpablo-cpu
python -m eim.data.share export        # publica su rama machine/juanpablo-cpu
python -m eim.data.share import        # SIMULACRO: qué traería del resto (no cambia nada)
```
El simulacro se revisa (◆ del usuario, T117) y solo después `import --apply`. Unión sin duplicar
ni pisar: repetirla no cambia nada; una fila con la misma clave y distinto contenido se conserva
la local y queda en `share_conflicts`.

**B. Equipo vacío que va a continuar el trabajo de otro** (la otra portátil, reinstalación):
```powershell
python -m eim.continuity offsite list
python -m eim.continuity offsite pull --machine laptop-i6pf9ovp-fce8d9
python -m eim.data.backup restore "backups\remote\laptop-i6pf9ovp-fce8d9\eim_…"
```
`pull` comprueba el SHA-256 de cada parte, del zip y luego la copia entera (filas por tabla);
`restore` se niega con los servicios en marcha y aparta la base local con sufijo
`.antes-de-restaurar-…` (nunca la borra). El equipo nuevo crea su propia identidad al arrancar:
desde ahí es un equipo más que exporta su experiencia.

**C. Sustituir un equipo que se retira** (se rompe, se vende): como B y además se adopta su
identidad (copiar `data/machine_id` desde los extras de la copia, o `EIM_MACHINE=<id>`) **solo si
el viejo no va a volver a operar nunca**: dos equipos con la misma identidad chocan (§4).

Lo que no viaja y hay que poner a mano: variables `EIM_*` (claves de testnet: solo en un equipo),
tareas de Windows (`instalar_inicio_automatico.ps1`, `instalar_copia_externa.ps1`), Ollama,
Freqtrade (`docs/BOTS.md`) y los libros. Las capturas crudas de microestructura/HFT no viajan.

## 4. Identidad y conflictos

- Cada equipo tiene **una identidad** (`data/machine_id` o `EIM_MACHINE`) y solo escribe en su
  rama `machine/<id>`: nadie pisa la rama de otro. La copia externa también va por identidad
  (`<id>__eim_…`), y cada equipo solo poda lo suyo.
- Dos equipos pueden operar en papel a la vez, **cada uno con su identidad**: sus historiales se
  unen después sin inflar la evidencia (la misma estrategia@marco@versión cuenta una vez).
- Nunca la misma identidad en dos equipos: `check` lo bloquea al ver una copia externa reciente
  de esa identidad publicada desde otro nombre de equipo.
- Código: conflictos de git en el PR, como siempre (`ONBOARDING.md` §6.3). `PLAN/BITACORA.md`
  se une sola (`merge=union`): cada sesión añade su entrada sin chocar.
- Reconciliación de datos: simulacro → revisar `nuevas / ya estaban / conflicto / incompat.` →
  aplicar → `share_conflicts` fila a fila. Cada aplicación deja antes su copia `pre-import_<id>`.

## 5. Al irse de un equipo (publicar)

1. Código: commit en una rama + push + PR (`ONBOARDING.md` §6). `check` lista lo no subido.
2. Bitácora: una entrada en `PLAN/BITACORA.md` (qué se hizo, archivos, pruebas, resultado,
   abierto, siguiente paso) en el mismo PR.
3. Datos:
   ```powershell
   powershell -ExecutionPolicy Bypass -File v2\scripts\copia_externa.ps1
   ```
   (= `python -m eim.continuity publish`). Usa la copia de hoy si existe (si no, la hace en
   caliente pidiéndola a la API), la verifica, sube la copia externa con los extras, exporta la
   experiencia **desde la copia** (nunca toca la carpeta viva ni activa el modo automático) y
   avisa de lo que falte subir. Repetirla no duplica nada. Si la carpeta viva tiene
   `share_config.json` (modo automático de T61), la experiencia la exportan los servicios y
   `publish` no la toca.
4. Automático cada día: `v2\scripts\instalar_copia_externa.ps1` (tarea «EIM - copia externa
   diaria», 20:30 hora local; `-Quitar` la quita). Registro: `data/operation/logs/copia_externa.log`
   y `data/continuity/publish.jsonl`.

## 6. Copias y recuperación ante fallos

| Copia | Dónde | Cuándo | Retención | Verificar |
|---|---|---|---|---|
| Completa local (T115) | `v2/backups/eim_…` (mismo disco) | diaria 00:00 UTC (servicio) + a demanda | 14 completas | `python -m eim.data.backup verify` |
| Completa externa (T125) | repo privado, versión `eim-copias` | diaria (tarea) + `publish` | 7 por equipo (`EIM_OFFSITE_KEEP`) | `offsite list` (completa/incompleta) y `offsite pull` (verifica todo) |
| Experiencia | repo privado, rama `machine/<id>` | `publish` / modo automático | la última foto | `share status` / `share import` (simulacro) |

- **Perder un equipo**: desde otro, §3 B o C con la última copia externa de su identidad. Se
  pierde como mucho un día de datos de ese equipo (o lo transcurrido desde su último `publish`),
  y sus capturas crudas de microestructura/HFT.
- **Restaurar una copia local**: `docs/RUNBOOK.md` §5.
- **Recuperar trabajo sin confirmar de otro equipo**: en los extras de su copia
  (`backups/remote/<id>/eim_….extras/git/`): `git apply <worktree>.patch` sobre el commit de
  `<worktree>.base`; ramas sin subir: `git fetch ramas_solo_locales.bundle <rama>:<rama>`.
- **Memoria de Claude de otro equipo**: `extras/claude/<carpeta>/memory/` → copiar a
  `%USERPROFILE%\.claude\projects\<carpeta de este clon>\memory\` (opcional: lo duradero está en
  `PLAN/ESTADO_PROYECTO.md`).
- **Sincronización interrumpida**: una subida a medias nunca se ve como completa (falta su
  `meta`); el siguiente `publish` la vuelve a subir entera. Una exportación de experiencia rota se
  rechaza al importar («falta …») y se usa la anterior válida. `check` avisa si la copia externa
  propia tiene más de 36 h y bloquea si no llega a la fuente central: nunca presenta lo local
  como lo último.
- **Antes de una migración o restauración**: `python -m eim.data.backup create` + `verify`.

## 7. Procesos: estado, no ejecución

Abrir el proyecto en otro equipo **no** traslada procesos en marcha; traslada su estado.

| Proceso | Qué se recupera | Cómo vuelve |
|---|---|---|
| API + operación en papel (`eim.operation run`) | libro simulado, cursores y kill-switch desde `data/operation` y `reports.duckdb` | arranca de nuevo; analiza solo velas nuevas (no repite operaciones registradas) |
| Bróker simulado | contextos e ideas desde `paper.duckdb`; protección desde su diario (T110) | arranca con la API |
| Líderes / copia simulada | posiciones, PnL y pausas desde `leaders.duckdb` | `eim.leaders supervise`; las pausas solo se levantan a mano |
| Captura de microestructura / HFT | nada: es captura en vivo | arranca una captura nueva; el hueco queda registrado |
| Experiencia automática (T61) | último import/export | si `share_config.json` existe |

- **Una instancia por equipo**: cerrojos (`supervisor.lock`, `collector.lock`), un escritor por
  base (DuckDB) y `servicio_continuo.ps1` no lanza nada si ya escucha el puerto o ya corre.
- **Dinero real imposible**: `REAL` está prohibido por la configuración de riesgo; testnet exige
  `EIM_EXECUTION=testnet` y claves en ese equipo. Cambiar de equipo, restaurar o importar no activa
  ninguna ejecución. Claves de testnet en **un solo** equipo a la vez.

## 8. Lista de comprobación de un equipo que retoma el trabajo

- [ ] `git status` limpio o el trabajo local guardado; `git log origin/main..main` vacío
- [ ] `python -m eim.continuity check` sin BLOQUEO (copia el resumen en la bitácora si hay AVISOS)
- [ ] La rama/commit que muestra `check` es la que esperas (`origin/main` al día)
- [ ] Datos: caso A (simulacro de `share import` revisado) o B/C (`offsite pull` verificado y
      `backup restore` hecho); filas por base parecidas a las de `offsite list`
- [ ] Gate en verde (`python -m ruff check eim tests && python -m pytest -q`)
- [ ] `GET http://127.0.0.1:8000/v2/health` y la interfaz con historial (libro simulado con
      operaciones previas)
- [ ] `PLAN/ESTADO_PROYECTO.md` y la última entrada de `PLAN/BITACORA.md` leídos
- [ ] Copia diaria externa instalada en el equipo que opera (`instalar_copia_externa.ps1`)
- [ ] Claves de testnet solo en un equipo; identidad propia (distinta de los demás)
