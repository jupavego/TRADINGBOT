# Retomar el proyecto tras varios días fuera

Para el colaborador que vuelve después de una pausa (días o semanas) y se encuentra con muchos
commits nuevos. Objetivo: **respaldar primero** su versión local (datos de operación, trabajo sin
confirmar, configuración) y **después** actualizar, sin perder historial ni experiencia.

No es lo mismo que `MIGRACION_EQUIPO.md` (trasladar todo a otro equipo) ni que `ONBOARDING.md`
(primera instalación). Aquí el equipo sigue siendo el mismo: solo cambia el código.

Resumen: un comando respalda y actualiza.

```powershell
powershell -ExecutionPolicy Bypass -File v2\scripts\actualizar_colaborador.ps1
```

---

## 1. Antes de nada: respaldo (no opcional)

```powershell
powershell -ExecutionPolicy Bypass -File v2\scripts\actualizar_colaborador.ps1 -SoloRespaldo
```

Deja en `%USERPROFILE%\EIM_respaldos\<fecha-hora>\` todo lo que **no** está en GitHub y no se puede
reconstruir:

| Qué | Dónde queda | Por qué importa |
|---|---|---|
| `v2\data` en frío, verificada (archivos y bytes) | `data\` | Libro simulado, contextos, líderes, sugerencias, puntuaciones de bots: tu historial de operación |
| Copia consistente de `reports.duckdb` + estado + versiones de parámetros | `v2\backups\eim_<fecha>\` (la hace `eim.data.backup`) | Copia con `manifest.json` (SHA-256, filas por tabla, commit); es la que sabe restaurar el RUNBOOK |
| Cambios sin confirmar | `cambios_sin_confirmar.patch`, `archivos_nuevos_sin_seguir.txt`, `estado_git.txt` | Tu trabajo a medias, aplicable con `git apply` |
| Todas tus ramas locales | `ramas_locales.bundle` | Ramas que nunca subiste (`git fetch <bundle> <rama>` las recupera) |
| Variables `EIM_*` del usuario | `env_EIM.json` | Claves de testnet, rutas, `EIM_MACHINE` |
| Claude Code: `settings.local.json` y memoria del proyecto | `settings.local.json`, `memory\` | Permisos y preferencias que no se versionan |

Por defecto **no** copia lo regenerable (velas, funding, interés abierto, microestructura,
observatorio, arbitraje): se vuelve a descargar solo. Con `-Todo` lo incluye (son GB).

> El respaldo contiene las variables `EIM_*` **en claro**. Disco propio; nunca a Git ni a una
> carpeta compartida.

Si algo sale mal después, se vuelve atrás con `v2\scripts\importar_equipo.ps1 -Origen <respaldo>
-Forzar` (restaura `data`, variables y configuración de Claude) o, para solo la base,
`RUNBOOK.md` §5.

## 2. Qué hace el script completo (sin `-SoloRespaldo`)

1. Informa del estado: rama, archivos sin confirmar, ramas locales sin subir y cuántos commits
   trae `origin/main`.
2. Detiene los servicios EIM (API, operación, líderes) para que la copia sea en frío. **No** quita
   el inicio automático: vuelven con el icono o al reiniciar.
3. Hace el respaldo de §1.
4. Actualiza: `git pull --ff-only`. Si hay trabajo sin confirmar **se detiene** (ya respaldado) para
   que decidas: confirmarlo en una rama y subirlo, o repetir con `-Forzar`.
5. Reinstala dependencias: `requirements-lock.txt`, `pip install -e ".[dev]"` y `npm ci`.
6. Corre el gate (`-SinGate` lo salta).

## 3. Dependencias: por qué hay que reinstalar (no es opcional)

- **`scipy` es dependencia obligatoria** desde esta semana (`agents/regime/bocpd.py`). Sin ella la
  API no arranca.
- `requirements-lock.txt` quedó **re-fijado** a las versiones probadas: algunos paquetes *bajan* de
  versión (por ejemplo `fastapi`). Es intencionado; no lo "arregles" subiéndolos.
- Extras opcionales: `[library]` (T52: `pypdf`, `pytesseract`, `Pillow`) solo si trabajas la
  biblioteca; `[kronos]` sigue siendo pesado y opcional.
- `npm ci` (no `npm install`): respeta `package-lock.json`.

## 4. Tus datos y tu experiencia: qué sobrevive

Actualizar el código **no borra ni migra** tu almacén: las bases viven en `v2\data`, que no está en
Git. Los cambios de esta semana solo **añaden** tablas nuevas (bots, líderes, sugerencias,
validación, observatorio), que se crean vacías al abrir la base. Tus operaciones y contextos
anteriores siguen ahí.

Dos cosas sí cambian de lectura, no de datos:
- **Contabilidad del capital (T107/T108)**: liquidación aplicada, suelo de cuenta y una sola base de
  capital. Las mismas operaciones pueden mostrar cifras distintas a las que recordabas. No es un
  error: la vista se re-simula desde el almacén en cada consulta (no hay instantánea auditable; está
  anotado en el BACKLOG).
- **Horas en la interfaz**: ahora en Bogotá (COT, UTC−5). Los datos y registros siguen en UTC.

### Unir tu experiencia con la del otro equipo (T61)

Si no está configurado, hazlo una vez (detalle en `OPERACION.md` §3.1):

```powershell
python -m eim.data.share setup --shared-dir "<carpeta de nube>" --machine <alias-unico>
python -m eim.data.share import          # simulacro: qué traería
python -m eim.data.share import --apply  # con la API y los líderes detenidos
```

Viaja la experiencia (reportes, operaciones simuladas, contextos, líderes, versiones de
validación); **no** viaja el estado de tu máquina (kill-switch, latidos, `risk_decisions`, libro de
la subcuenta) ni las claves. Importar es idempotente y la unión conmutativa: repetirlo no infla la
evidencia. Usa un `--machine` **distinto** del otro colaborador o los historiales chocan.

## 5. Si el gate falla

```powershell
cd v2
python -m ruff check eim tests
python -m pytest -q
```

Antes de dar por mala la actualización, descarta las causas conocidas:

| Síntoma | Causa | Qué hacer |
|---|---|---|
| `ModuleNotFoundError: scipy` (o `eim`) | Entorno virtual sin reinstalar | Repetir el paso 5 del script con el entorno activo |
| `test_queries_over_100k_events_stay_within_the_threshold` falla por milisegundos (p95 ~100 ms) | Prueba de rendimiento con umbral absoluto: depende del equipo y de lo que esté corriendo | Repetir con el equipo descargado. Es una fragilidad conocida del gate (ver la fase de estabilización en `PLAN/STATUS.md`) |
| `test_legacy_db_without_machine_column_is_migrated` falla comparando dos alias de máquina | El test no aísla `EIM_MACHINE`, que `machine_id()` antepone al archivo `data/machine_id` | Conocido y con tarea (T116). Falla si tienes `EIM_MACHINE` definida; no indica nada roto en tu copia |
| Pruebas de bots/validación lentas o con `Out of Memory` | El almacén real es grande y DuckDB toma memoria | `EIM_DUCKDB_MEMORY` / `EIM_DUCKDB_THREADS` acotan el uso; cierra la API antes |
| Falla al leer `PLAN/roadmap.html` | Falta regenerarlo | `python PLAN\build_roadmap.py` |

Si falla otra cosa, no lo arregles en `main`: abre rama y PR como siempre (`ONBOARDING.md` §6).

## 6. Arrancar y comprobar

```powershell
# API (desde v2/)
python -m uvicorn eim.api.main:app --port 8000 --reload
# Web
cd v2\eim\web; npm run dev
```

- Interfaz: `http://127.0.0.1:5173` (con `127.0.0.1`, no `localhost`).
- Salud: `GET http://127.0.0.1:8000/v2/health`; experiencia compartida: `GET /v2/share/status`.
- Comprueba a ojo: precio en vivo cambiando por tick, el libro simulado con tus operaciones
  anteriores, y que las esferas que te interesen no digan «sin datos» (si lo dicen, la skill
  `eim-diagnose-agent` las diagnostica).
- Icono de escritorio y arranque con Windows (nuevos esta semana):
  `v2\scripts\crear_acceso_escritorio.ps1` y `v2\scripts\instalar_inicio_automatico.ps1`.

## 7. Qué cambió mientras estabas fuera

Resumen por temas, con lo que hay que calibrar o integrar:
`PLAN/notas/CAMBIOS_2026-10-15_a_2026-10-22.md`.

Antes de tomar tarea: `PLAN/STATUS.md` (reclama la tarea ☐ → ◐ con tu nombre) y `PLAN/BACKLOG.md`.
