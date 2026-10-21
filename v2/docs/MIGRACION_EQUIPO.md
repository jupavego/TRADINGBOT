# Migración a otro equipo (portátil → CPU de escritorio)

Objetivo: que el equipo nuevo quede operando con el mismo código, las mismas versiones y el mismo
estado de operación, sin arrastrar basura. Lo que está en Git viaja con `git clone`; lo que **no**
está en Git (datos, claves, configuración de Claude) se traslada a mano según este documento.

Versiones de referencia: Python 3.12 (≥ 3.11), Node 20 LTS (≥ 20), Git 2.40+, `gh`.
Fijadas en `v2/requirements-lock.txt` (Python) y `v2/eim/web/package-lock.json` (Node).

## A. En el equipo ANTIGUO (antes de apagarlo)

1. **Código al día en GitHub.** Todo lo útil debe estar en `origin`. Comprueba:
   `git fetch && git status` y, por rama, `git log origin/<rama>..<rama>`. Ramas con trabajo sin
   fusionar a `main` se suben (`git push`) o se descartan a propósito. Las carpetas
   `.claude/worktrees/*` **no viajan**: solo cuentan sus ramas en `origin`.
2. **Parar la operación** (icono EIM / servicio continuo, líderes incluidos) para que las bases
   DuckDB queden cerradas y sin `.wal` pendientes.
3. **Copia en frío de los datos no versionados** (todo en `.gitignore`):
   - `v2/data/` completo → es el estado real: `paper.duckdb` (libro simulado), `reports.duckdb`,
     `leaders.duckdb` (historial que **no se puede volver a pedir**), `operation/`, `kill_switch.json`,
     `machine_id`, `share_config.json`. Se pueden omitir por ser regenerables: `candles/`, `funding/`,
     `open_interest/`, `long_short_ratio/`, `liquidations/`, `micro/`, `arbitrage/`, `obs/`,
     `roadmap_live/`, `*.wal.bak`, `obs_corrupto/`.
   - `v2/backups/` (opcional; basta la última copia).
   - Libros de la biblioteca (T52) si `EIM_LIBRARY_DIR` apunta fuera del repo.
   Llévalas a un disco externo o a la nube. Alternativa más limpia: `python -m eim.data.backup create`
   + `python -m eim.data.backup verify`, y exportar líderes con `python -m eim.data.share export`.
4. **Variables de entorno / claves**: anota las `EIM_*` definidas a nivel de usuario
   (`[Environment]::GetEnvironmentVariable(...)` o *Variables de entorno* de Windows): sobre todo
   `EIM_TESTNET_API_KEY/_SECRET`, `EIM_FRED_API_KEY`, `EIM_SHARED_DIR`, `EIM_MACHINE`. Las claves se
   reescriben a mano en el equipo nuevo; **nunca** se suben a Git ni se pegan en chats.
5. **Configuración de Claude Code** (no está en el repo): `.claude/settings.local.json` y la carpeta
   de memoria `C:\Users\<usuario>\.claude\projects\<ruta-del-proyecto>\memory\`. Cópialas.
6. Otros ficheros fuera de Git: `repos/` (referencias; se vuelve a bajar si hace falta) y los `.docx/.xlsx`
   de la raíz sí están versionados.

## B. En el equipo NUEVO

```powershell
winget install Git.Git Python.Python.3.12 OpenJS.NodeJS.LTS GitHub.cli
gh auth login
git clone https://github.com/jupavego/TRADINGBOT.git
cd TRADINGBOT
powershell -ExecutionPolicy Bypass -File v2\scripts\preparar_equipo.ps1
```

`preparar_equipo.ps1` comprueba versiones, crea `v2/.venv` desde `requirements-lock.txt`, hace
`npm ci` y corre el gate (`-SinGate` para saltarlo). Después:

1. Copia `v2/data/` (y `v2/backups/`) al mismo lugar del clon, **con todo detenido**. Verifica con
   `python -m eim.data.backup verify` si usaste copia de seguridad.
2. Define las variables `EIM_*` anotadas y la configuración de Claude (paso A.5). La memoria de
   Claude está ligada a la ruta de la carpeta: colócala en el `…\projects\<nueva-ruta>\memory\`.
3. `powershell -ExecutionPolicy Bypass -File v2\scripts\crear_acceso_escritorio.ps1` (el acceso
   apunta a la ruta del clon) y, si quieres arranque automático, `instalar_inicio_automatico.ps1`.
4. Abre el icono EIM → `http://127.0.0.1:5173`; las velas faltantes se descargan solas.
5. `.claude/launch.json` usa `v2/.venv/Scripts/python.exe`: ya existe tras el paso 1.

## C. Regla para no duplicar el estado

Mientras el equipo nuevo opera, el antiguo debe quedar **apagado** (o con `EIM_PAPER=0`): dos
equipos operando en papel con el mismo `machine_id` generan historiales que luego chocan al
compartir (`docs/OPERACION.md` §3.1). Si quieres que ambos convivan, deja que el nuevo cree su
propio `machine_id`/`EIM_MACHINE` (no copies `data/machine_id`) y trae el historial con
`python -m eim.data.share import --apply`.

## D. Comprobación final

- [ ] `git status` limpio y `git log origin/main..main` vacío en el equipo antiguo
- [ ] Gate en verde en el nuevo (`python -m ruff check eim tests && python -m pytest -q`)
- [ ] `GET http://127.0.0.1:8000/v2/health` responde y la interfaz muestra precio en vivo
- [ ] El libro simulado (`paper.duckdb`) conserva sus operaciones previas
- [ ] Equipo antiguo apagado o con la operación detenida
