# Migración a otro equipo (portátil → CPU de escritorio)

Objetivo: que el equipo nuevo quede operando con el mismo código, las mismas versiones y el mismo
estado de operación, sin arrastrar basura. Lo que está en Git viaja con `git clone`; lo que **no**
está en Git (datos, claves, configuración de Claude) se traslada a mano según este documento.

Versiones de referencia: Python 3.12 (≥ 3.11), Node 20 LTS (≥ 20), Git 2.40+, `gh`.
Fijadas en `v2/requirements-lock.txt` (Python) y `v2/eim/web/package-lock.json` (Node).

## A. En el equipo ANTIGUO (antes de apagarlo)

1. **Código al día en GitHub.** Todo lo útil debe estar en `origin` (`git fetch && git status`; por
   rama, `git log origin/<rama>..<rama>`). Las carpetas `.claude/worktrees/*` **no viajan**: solo
   cuentan sus ramas en `origin`.
2. **Un solo comando** empaqueta todo lo que no está en Git:
   ```powershell
   powershell -ExecutionPolicy Bypass -File v2\scripts\exportar_equipo.ps1 -Destino D:\EIM_migracion
   ```
   Detiene el vigilante, la API, los líderes y el inicio automático; copia `v2\data` en frío y la
   verifica (nº de archivos y bytes); guarda las variables `EIM_*` del usuario, `.claude\settings.local.json`
   y la memoria de Claude. Por defecto omite lo regenerable (velas, funding, OI, obs…); `-Todo` lo
   incluye. `-ConservarMiIdentidad` no copia `machine_id`/`EIM_MACHINE` (ver §C).
3. **El paquete contiene las claves en claro.** Disco externo propio; bórralo al terminar. Nunca a
   Git ni a carpetas compartidas.

## B. En el equipo NUEVO

```powershell
winget install Git.Git Python.Python.3.12 OpenJS.NodeJS.LTS GitHub.cli
gh auth login
git clone https://github.com/jupavego/TRADINGBOT.git
cd TRADINGBOT
powershell -ExecutionPolicy Bypass -File v2\scripts\preparar_equipo.ps1
powershell -ExecutionPolicy Bypass -File v2\scripts\importar_equipo.ps1 -Origen D:\EIM_migracion -InicioAutomatico
```

- `preparar_equipo.ps1`: comprueba versiones, crea `v2/.venv` desde `requirements-lock.txt`, `npm ci` y
  gate (`-SinGate` lo salta).
- `importar_equipo.ps1`: restaura `v2\data` (verificada), las `EIM_*` de usuario, `settings.local.json`
  y la memoria de Claude en la ruta correspondiente a ESTE clon, y crea el acceso del escritorio
  (`-InicioAutomatico` registra además el arranque con Windows; `-Forzar` sobrescribe un `data` existente).
- Abre una terminal nueva (para ver las variables) y el icono EIM → `http://127.0.0.1:5173`; las
  velas omitidas se descargan solas.

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
