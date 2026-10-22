# Guía de incorporación — desarrollo colaborativo del proyecto EIM

Para quien se une al proyecto: cómo preparar el equipo, clonar el repositorio, trabajar una tarea con Claude Code y subir los avances sin pisar el trabajo del otro desarrollador.

Repositorio: <https://github.com/jupavego/TRADINGBOT> (rama principal: `main`).

> Qué es el proyecto: un agente multiagente de trading de futuros (BTC/ETH). Los documentos `F0`–`F6` son la especificación vinculante (`F0/MSI-META-001.md` es la constitución). El código nuevo vive solo en `v2/`. Todo el trabajo está dividido en tareas `PLAN/T01…T46`.

---

## 1. Requisitos (instalar una sola vez)

| Herramienta | Versión | Para qué | Comprobar |
|---|---|---|---|
| Git | 2.40+ | Control de versiones | `git --version` |
| Python | **3.11 o superior** (el proyecto se probó con 3.12) | API, agentes, tests | `python --version` |
| Node.js | **20 LTS o superior** (incluye `npm`) | Interfaz web (Vite + TypeScript) | `node --version` |
| GitHub CLI (`gh`) | reciente | Abrir y gestionar PR desde la terminal | `gh --version` |
| Claude Code | reciente (app de escritorio o CLI) | Ejecutar las tareas con IA | `claude --version` |

Notas para Windows:
- Instala Git for Windows, Python (marca **Add python.exe to PATH**) y Node desde sus sitios oficiales o con `winget install Git.Git Python.Python.3.12 OpenJS.NodeJS.LTS GitHub.cli`.
- Si el proyecto queda en una ruta con espacios o en otra unidad y Git dice `dubious ownership`, ejecuta una vez: `git config --global --add safe.directory "*"`.
- Si `python` abre la Microsoft Store, desactiva los alias en *Configuración → Aplicaciones → Alias de ejecución de aplicaciones*.

> ¿Cambias de equipo (no es un colaborador nuevo)? Sigue `v2/docs/MIGRACION_EQUIPO.md` y usa `v2/scripts/preparar_equipo.ps1`, que automatiza la sección 3.
>
> ¿Vuelves tras una pausa de días o semanas, con el repo ya instalado? No sigas esta guía: usa
> `v2/docs/RETOMAR_COLABORADOR.md` y `v2/scripts/actualizar_colaborador.ps1`, que **respalda primero**
> tus datos de operación, tu trabajo sin confirmar y tu configuración, y después actualiza, reinstala
> dependencias y corre el gate. Qué cambió mientras no estabas:
> `PLAN/notas/CAMBIOS_2026-10-15_a_2026-10-22.md`.

## 2. Acceso a GitHub

1. Crea (o usa) tu cuenta de GitHub y pásale tu usuario al dueño del repositorio.
2. El dueño te invita en **Settings → Collaborators → Add people** (o a la organización). Acepta la invitación por correo.
3. Configura tu identidad (aparecerá en tus commits):
   ```bash
   git config --global user.name "Tu Nombre"
   git config --global user.email "tu-correo-de-github@ejemplo.com"
   ```
4. Autentícate: `gh auth login` (elige GitHub.com → HTTPS → navegador). Verifica con `gh auth status`.

## 3. Clonar e instalar

```bash
git clone https://github.com/jupavego/TRADINGBOT.git
cd TRADINGBOT
```

**Backend (Python)** — desde `v2/`:

```bash
cd v2
python -m venv .venv
# Windows (PowerShell):  .venv\Scripts\Activate.ps1
# Windows (Git Bash):    source .venv/Scripts/activate
# macOS/Linux:           source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

`[dev]` instala `pytest`, `ruff` y `pyright`. El extra `[kronos]` (torch, etc.) es **opcional y pesado**: instálalo solo si tu tarea trabaja con el motor Kronos (`pip install -e ".[dev,kronos]"`).

**Frontend (Node)**:

```bash
cd v2/eim/web
npm install
```

**Verifica que todo quedó bien** (desde `v2/`, con el entorno virtual activo). Este es el *gate* del proyecto y debe pasar antes de cada commit:

```bash
python -m ruff check eim tests && python -m pytest -q
```

Los tests **no usan red**: trabajan con fixtures en `v2/tests/fixtures/`.

## 4. Ejecutar la aplicación en local

```bash
# Terminal 1 — API (desde v2/)
python -m uvicorn eim.api.main:app --port 8000 --reload

# Terminal 2 — Web
cd v2/eim/web && npm run dev
```

- Abre **`http://127.0.0.1:5173`** (usa `127.0.0.1`, no `localhost`: en el navegador integrado de Claude `localhost` falla).
- La API se conecta al WebSocket de Binance Futures. Si tu red lo bloquea, usa el spot: `EIM_WS_URL=wss://stream.binance.com:9443/ws` (ver backlog T09).
- Variables de entorno opcionales: tabla completa en `v2/docs/OPERACION.md` §2.
- Operación continua en papel, copias de seguridad e incidentes: `v2/docs/OPERACION.md` y `v2/docs/RUNBOOK.md`.
- Los datos descargados (`*.parquet`, `*.duckdb`) **no se versionan**: cada quien tiene su propio almacén local y se rellena solo al usar la API.
- `.claude/launch.json` ya define los servidores de vista previa (`eim-v2-web`) para la app de escritorio de Claude.

## 5. Reglas de seguridad (no negociables)

- **Nunca** subas claves, tokens ni archivos `.env`. Si algún día se usan claves del exchange: **solo testnet y sin permiso de retiro**.
- Sin dinero real hasta superar la puerta de edge (T27) y semanas de paper trading (T31).
- Antes de copiar código de terceros, revisa licencia y seguridad (resultado de la auditoría en `PLAN/notas/T04_auditoria.md`).
- `legacy/F7/` es código legado archivado (T32): no se edita; solo sirve de oráculo de regresión. La carpeta `repos/` no se versiona.
- La API es **solo local** (rechaza otros equipos y cabeceras `Host` ajenas); no la expongas con `--host 0.0.0.0`. Detalle: `v2/docs/SEGURIDAD.md`.

## 6. Flujo de trabajo colaborativo

Una tarea = una rama = una sesión de Claude = un Pull Request.

### 6.1 Reparto de tareas (evita pisarse)
1. Acuerden por chat quién toma qué. Reglas de dependencia: `PLAN/STATUS.md` y `PLAN/00_MASTER.md` (hay tareas paralelizables: T06‖T07, T09‖T16, T12‖T21‖T22‖T23, T34‖T36‖T38).
2. **Reclama la tarea antes de empezar**: en un commit pequeño a `main` (o por PR rápido) cambia en `PLAN/STATUS.md` su estado ☐ → ◐ y escribe tu nombre en *Notas de cierre* (ej. `◐ en curso — Ana`). Así el otro ve que está tomada.
3. No toquen la misma tarea ni el mismo módulo a la vez.

### 6.2 Ciclo de una tarea
```bash
git switch main && git pull
git switch -c tNN-descripcion-corta        # ej. t19-calibracion-escenarios
```
1. Abre Claude Code en la carpeta del repo y escribe: **`Ejecuta PLAN/TNN.md`**. Nada más: `CLAUDE.md` se carga solo y contiene el protocolo (leer solo esa tarea, no ampliar alcance, pasar el gate, actualizar el estado).
2. La sesión implementa, corre el gate y actualiza `PLAN/STATUS.md` (◐ → ☑ con 2–3 líneas de qué quedó y dónde).
3. Lo que quede fuera del alcance → una línea en `PLAN/BACKLOG.md`.
4. Revisa el diff tú mismo: `git diff` / `git status`.
5. Commit y subida:
   ```bash
   git add -A
   git commit -m "TNN: resumen corto de lo hecho"
   git push -u origin tNN-descripcion-corta
   gh pr create --fill
   ```
6. El otro desarrollador revisa el PR (idealmente con la skill `code-review`); se fusiona a `main` con *Squash and merge* o *Merge*. **No** se hace push directo a `main` salvo el reclamo de tarea de 6.1.
7. Tras fusionar, todos actualizan: `git switch main && git pull`.

Frecuencia: suban avances con regularidad (mínimo un PR por tarea terminada; si una tarea es larga, PR parciales). Antes de empezar cada sesión, haz `git pull`.

### 6.3 Archivos que generan conflictos (y cómo resolverlos)
- `PLAN/STATUS.md`: ambos editan la tabla. Conflicto típico en filas distintas → conserva ambas filas.
- `PLAN/roadmap.html` y `PLAN/status.js`: **son generados**. Si hay conflicto, resuelve `STATUS.md` primero y regenera, nunca los edites a mano:
  ```bash
  python PLAN/build_roadmap.py
  git add PLAN/roadmap.html PLAN/status.js
  ```
- `PLAN/BACKLOG.md`: solo se añaden líneas; conserva las de ambos.
- Mantén tu rama al día: `git fetch origin && git merge origin/main` antes de abrir el PR.

## 7. Configuración de Claude Code (para conservar la eficiencia)

### 7.1 Qué viene dentro del repositorio (se hereda al clonar)
| Elemento | Dónde | Efecto |
|---|---|---|
| `CLAUDE.md` | raíz | Instrucciones fijas: arquitectura, reglas de código, protocolo de sesión y comandos. Se carga automáticamente. |
| Skill `eim-new-agent` | `.claude/skills/eim-new-agent/` | Checklist y plantilla para crear agentes analizadores. Se usa al implementar cualquier agente nuevo. |
| `launch.json` | `.claude/` | Servidores de vista previa del navegador integrado. |
| Plan de tareas | `PLAN/` | `T01…T46`, `STATUS.md`, `CONTRATOS.md`, `UI_SPEC.md`, `BACKLOG.md`, `roadmap.html`. |

### 7.2 Qué NO viene y debes configurar tú
Estos elementos son **locales de cada cuenta/equipo** (no se versionan):

1. **Skills integradas de Claude Code** (ya disponibles sin instalar nada): `run`, `simplify`, `code-review`, `dataviz`, `claude-api`, `update-config`, `fewer-permission-prompts`, `skill-creator`. Cuándo usarlas (resumen de `PLAN/00_MASTER.md`):
   - `run`: levantar la app y comprobarla (tareas con API/UI).
   - `simplify`: limpieza al cerrar cada tarea.
   - `code-review` (nivel low/medium): revisión barata del diff, sobre todo en T05, T16, T25, T29, T30.
   - `dataviz`: colores y diseño coherentes de gráficos (T09–T19).
   - `claude-api`: llamadas a Claude con caché y salida estructurada (T24).
2. **Plugin `frontend-design`** (Anthropic): recomendado para tareas de UI (T09–T19 y siguientes). Instálalo desde el catálogo de plugins de Claude Code.
3. **No instalar `TradingCalc` (MCP remoto)**: envía datos a un tercero; la aritmética se escribe y prueba localmente.
4. **Permisos**: en tus primeras 2–3 sesiones Claude pedirá confirmación para comandos como `python -m pytest`, `git`, `gh`. Después ejecuta la skill `fewer-permission-prompts` para generar una lista de permitidos en tu `.claude/settings.local.json` (archivo personal, ignorado por Git). Comandos que conviene permitir:
   - `python -m ruff check *`, `python -m pytest *`, `python PLAN/build_roadmap.py`, `npm run *`, `git status/diff/log/add/commit/push/fetch`, `gh pr *`.
5. **Hook opcional** (skill `update-config`): ejecutar `ruff` + `pytest` automáticamente tras editar código, para detectar fallos antes del commit.
6. **Memoria de Claude**: la memoria automática es por cuenta y no se comparte. Las preferencias del proyecto que el dueño ya fijó están reflejadas abajo; si quieres que tu Claude las recuerde, pídele *«recuerda esto»* al iniciar:
   - El código nuevo va en carpeta aparte (`v2/`), separado del legado F0–F7.
   - La UI debe mostrar el **precio en tiempo real**, cambiando por tick.
   - Regenerar `PLAN/roadmap.html` (`python PLAN/build_roadmap.py`) en cada tarea y tras fusionar.

### 7.3 Buenas prácticas de sesión (ahorran tokens)
- Una tarea por sesión nueva; el prompt es solo `Ejecuta PLAN/TNN.md`.
- No pidas explorar el repo entero; la tarea lista los archivos que importan.
- Archivos grandes del legado (`legacy/F7/eim_engine.py`, `legacy/F7/web/index.html`): buscar con Grep/offset, nunca leer completos.
- Verifica gráficos con datos renderizados o captura de pantalla, no solo «sin errores en consola».

## 8. Reglas de código (resumen de `CLAUDE.md`)

- Identificadores en inglés; docstrings, textos de la UI y documentos en español.
- Los agentes son **funciones puras** sobre el snapshot (sin red, disco ni estado global). Todo I/O vive en `eim/data/`.
- Archivos ≤ 300 líneas; un agente = un paquete con `agent.py`, `params.py` y tests.
- Tests sin red; regresión contra el legado cuando se migra algo.
- Toda cifra expone su `source` y su cobertura real; nunca presentar datos asumidos como reales.
- La proyección de precio siempre es probabilística (3 escenarios con probabilidad + bandas); las velas proyectadas se etiquetan «simuladas».
- Los LLM solo informan; riesgo y ejecución son código determinista con poder de veto.
- Toda vista de plan/operación muestra el modo: Análisis, Simulado o Testnet.

## 9. Checklist de primer día

- [ ] Git, Python ≥ 3.11, Node ≥ 20, `gh` y Claude Code instalados
- [ ] Invitación a GitHub aceptada y `gh auth status` correcto
- [ ] Repo clonado, entorno virtual creado, `pip install -e ".[dev]"` y `npm install` hechos
- [ ] Gate en verde: `python -m ruff check eim tests && python -m pytest -q`
- [ ] API + web corriendo en `http://127.0.0.1:5173`
- [ ] Leídos: `CLAUDE.md`, `PLAN/00_MASTER.md`, `PLAN/STATUS.md`, `v2/docs/ARQUITECTURA.md` y `v2/docs/OPERACION.md`
- [ ] Tarea acordada con el otro desarrollador y reclamada en `STATUS.md` (◐)
- [ ] Primera rama creada y primer PR abierto

## 10. Problemas frecuentes

| Síntoma | Solución |
|---|---|
| `dubious ownership` en Git | `git config --global --add safe.directory "*"` |
| `python` no encontrado / abre Microsoft Store | Reinstalar con *Add to PATH* y desactivar alias de Store |
| `ModuleNotFoundError: eim` | Activar el entorno virtual y repetir `pip install -e ".[dev]"` desde `v2/` |
| Pantalla en blanco con `localhost:5173` | Usar `http://127.0.0.1:5173` |
| La UI dice «Sin conexión» | Comprobar que la API corre en el puerto 8000; si Binance Futures está bloqueado, usar `EIM_WS_URL` del spot |
| Conflicto en `roadmap.html` / `status.js` | Resolver `STATUS.md` y ejecutar `python PLAN/build_roadmap.py` |
| `pytest` falla por archivos de datos | Los tests usan `v2/tests/fixtures/`; ejecútalos desde `v2/` |
