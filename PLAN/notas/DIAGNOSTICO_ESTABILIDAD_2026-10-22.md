# Diagnóstico de estabilidad e integración — 2026-10-22

Motivo: en siete días (2026-10-15 → 2026-10-22) entraron **281 commits y 773 archivos** (T40–T108,
fases 10 a 19). Antes de que el segundo colaborador actualice su copia conviene saber qué quedó
inestable, qué quedó a medio integrar y qué hay que calibrar. Este diagnóstico es el insumo de la
**Fase 20 (T115–T121)**.

Método: estado de `PLAN/STATUS.md` y `PLAN/BACKLOG.md`, lectura del código citado y una corrida del
gate en el equipo de referencia (2026-10-22). Cada hallazgo dice **cómo se comprobó**.

## Hallazgos

### A. La copia diaria deja fuera dos de las tres bases (riesgo de pérdida de historial)
**Comprobado:** `v2/eim/data/backup.py` copia `reports.duckdb` y, derivado, `obs.duckdb`
(`DB_NAME`/`OBS_NAME`, `create()`); `extra_dbs` solo recibe el observatorio
(`eim/api/main.py:118,209`). En `v2/data` viven **tres** bases: `reports.duckdb`, `paper.duckdb` y
`leaders.duckdb`.

- `paper.duckdb`: contextos del bróker simulado, operaciones simuladas y el **registro inmutable de
  sugerencias publicadas** (`eim/data/suggestion_store.py`, T51). De los contextos salen, de forma
  determinista, las ideas y las operaciones: es la experiencia acumulada.
- `leaders.duckdb`: capturas en vivo de líderes, **irrepetibles** (el exchange solo sirve las 10 000
  ejecuciones más recientes); perderla reinicia la cuenta de 7 días. `OPERACION.md` §3 ya lo admite
  (BACKLOG T40 (5)); de `paper.duckdb` no dice nada.

**Consecuencia:** restaurar desde `backups/` recupera los reportes y **pierde el libro simulado y
los líderes**. Es justo el historial que un colaborador cree estar respaldando. → **T115**.
Mitigación provisional: `v2/scripts/actualizar_colaborador.ps1` copia `v2/data` entera en frío.

### B. El gate falla por una prueba de rendimiento con umbral absoluto
**Comprobado:** `tests/api/test_obs_api.py::test_queries_over_100k_events_stay_within_the_threshold`
falló con `/v2/obs/traces {'limit': 100}: p95 103 ms` contra `QUERY_P95_MS_MAX = 100`
(`eim/observability/thresholds.py`; T72 midió ≤ 32 ms). El p95 se estima con
`statistics.quantiles(lat, n=20)[-1]` sobre **20 muestras sin calentamiento**: una sola llamada
lenta decide el resultado.

**Consecuencia:** el colaborador que vuelve corre `pytest` y ve rojo por algo que no tiene que ver
con su cambio; y la tentación es subir el umbral, que es un requisito de T72. Además la suite
completa tarda **> 25 min** con Ollama y los recolectores activos
(`PLAN/notas/auditoria_modulos_2026-10-19.md`), lo que empuja a no correrla. → **T116**.

### C. Las cifras del bróker simulado no son auditables
**Comprobado:** `PLAN/notas/T106_auditoria_salidas.md` (alerta A4) y
`PLAN/notas/T107_contabilidad.md` (1): la vista se recalcula desde **todo** el almacén en cada
consulta y el capital se re-simula desde 10 000 USDT, así que una captura de ayer no se puede volver
a obtener; las 19 132 operaciones del Agresivo no caben (techo 4 856 cierres). Además, con capital
≤ 0 el rechazo se registra como «tope de riesgo abierto por dirección», que no es el motivo real
(`v2/eim/paper/book.py:168-169`).

**Consecuencia:** dos personas mirando el mismo panel en momentos distintos ven cifras distintas y
no pueden reconciliarlas; y un motivo de rechazo equivocado contamina el aprendizaje por filtro
saltado. → **T118**.

### D. La puntuación de bots en vivo no está verificada contra el informe
**Comprobado:** `PLAN/BACKLOG.md` (bots en datos vivos, 2026-10-21): el recálculo dentro de la API
cayó por memoria (DuckDB `Out of Memory`) con ~0,5 GB libres; se arregló con `query_lean` y topes de
DuckDB **medido con 105 000 posturas sintéticas**, porque la API viva tiene `reports.duckdb`
bloqueada. `GET /v2/bots/scorecard` puede seguir mostrando la medición anterior, mientras la buena
está en `v2/reports/bots_scorecard.md`. NFI sigue sin ciclo en vivo.

**Consecuencia:** la interfaz puede afirmar una puntuación distinta de la del informe, y el
escuadrón vota (o no vota) según cifras no comprobadas en la base real. → **T119**.

### E. Esferas «sin datos» y recolectores: queda abierto el último tramo
**Comprobado:** T104 sigue ◐ (`PLAN/notas/T104_diagnostico.md`): falta la corrida de ≥ 24 h con
captura de la esfera con datos y los ≥ 7 días para la línea base marginal; el corte de red físico no
se provocó. `PLAN/notas/auditoria_modulos_2026-10-19.md` deja además: relanzar los servicios **desde
el checkout principal** (el vigilante de líderes corría desde un worktree), el disco E: que se
desconecta, y el contexto que a veces sale `degraded` por falta de catalizadores con fuente.

**Consecuencia:** el estado que pinta la interfaz depende de dónde y cómo se lanzaron los servicios;
un colaborador nuevo ve «sin datos» sin saber si es su equipo o el sistema. → **T120**.

### F. La experiencia compartida (T61) nunca se ha estrenado entre dos equipos
**Comprobado:** T61 ☑ «construido y probado sin red (39 tests)», con **◆ pendiente: el usuario
revisa el informe de la primera mezcla real**. El regreso del segundo colaborador es la primera
oportunidad real. Riesgos conocidos del diseño: alias `--machine` repetido, dos equipos operando con
el mismo `machine_id` (historiales que chocan, `OPERACION.md` §3.1) y rechazo de la exportación si el
esquema del otro es más nuevo. → **T117**.

### G. Documentación, variables y tablero desfasados respecto al código
**Comprobado:**
- Diez variables en uso **sin documentar** en `OPERACION.md` §2: `EIM_DUCKDB_MEMORY`,
  `EIM_DUCKDB_THREADS`, `EIM_BOT_FREQTRADE_PY`, `EIM_BOT_NFI_DIR`, `EIM_LOCAL_LLM_HOST`,
  `EIM_CONTEXT_LLM`, `EIM_EDGE_RESULTS`, `EIM_OPERATE_EXTRA_TFS`, `EIM_OPERATION_REPORTS`,
  `EIM_LIBRARY_LLM` (comprobado una a una contra el documento).
- `scipy` pasó a dependencia **obligatoria** (`v2/pyproject.toml`, `agents/regime/bocpd.py`) y
  `requirements-lock.txt` bajó versiones a propósito: quien no reinstale no arranca, y no está dicho
  en `ONBOARDING.md`.
- La lista de fases del tablero (`var PHASES` en `PLAN/roadmap.html`) se escribe a mano; por eso
  T105 no se veía. `build_roadmap.py` ya avisa de las huérfanas, pero no las dibuja.
- `v2/EIM_migracion/` (211 MB, paquete de traslado con variables en claro) está **sin ignorar**: un
  `git add -A` lo subiría. (Se corrige ya, no hace falta tarea.)
→ **T121**.

## Lo que NO está roto (comprobado, para no perder tiempo)
- **El almacén no necesita migración.** Los cambios de la semana solo **añaden** tablas
  (`bot_signals`, `bot_scorecard`, `bot_sim_runs`, `copy_*`, `leader_*`, `sug_*`, `val_*`, `share_*`,
  observatorio); todas se crean con `CREATE TABLE IF NOT EXISTS` al abrir la base. Ninguna tabla
  anterior cambió de columnas (revisado el diff de DDL de la semana). Un almacén de hace una semana
  sigue sirviendo.
- `ruff` está limpio en todo `eim` y `tests`.
- Las cifras del capital pueden **verse distintas** tras T107/T108 (liquidación aplicada, suelo y una
  sola base) sin que sea un error: con el almacén actual ninguna de las 157 operaciones cerradas se
  habría liquidado, así que el arreglo no mueve ninguna cifra, cierra un agujero latente.

## Calibraciones pendientes que NO son fallos (quedan en sus fases)
- Escalera y perfiles: `exit_mode` no entra en la huella de versión de T49 y la validación mide la
  sombra con TP, así que **la escalera no pasa hoy por la puerta** (T106 (5)); precedencia entre
  BE+ y escalones (T106 ◆3); `ladder_audit` trata el cierre «BE» como violación. Pertenece a
  **T109–T111**; anotado allí, no se duplica aquí.
- ETHUSDT en la escalera necesita velas de 1 min de ETH y `tick`/`qty_step` por símbolo (T106 ◆2,
  parte resuelta en T108).
- Escuadrón de bots: ningún bot vota ni es publicable (22–24 intentos en Holm); portar más
  estrategias solo sube la vara. Decisión ◆ del usuario pendiente, no es inestabilidad.
- T31 (≥ 4 semanas en papel) y T45 (E2E en testnet real) siguen ◐ por **tiempo de calendario**, no
  por código.
