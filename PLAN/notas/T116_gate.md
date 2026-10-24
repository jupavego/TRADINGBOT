# T116 — Gate estable y reproducible: cierre (2026-10-24)

Equipo de las mediciones: el del colaborador (Windows 11, 8 hilos, 16 GB, ~4 GB libres) con los
servicios continuos en marcha (API + operación en papel de T31, líderes, recolectores de
microestructura, HFT y liquidaciones, `vite`). **Sin Ollama** (no está instalado aquí): su carga se
sustituyó por 4 procesos al 100 % de CPU (la mitad de los hilos).

## Qué hacía inestable el gate

1. **La suite usaba la red.** El ciclo de operación real (`eim/operation/cycle.py::_sync_extras`)
   sincroniza por su cuenta liquidaciones (30 descargas diarias de `data.binance.vision`) y
   titulares RSS. Cada prueba que construye un `Rig` y da un paso las descargaba de nuevo: ~20 s por
   prueba (perfilado: `liquidations._download_day` ×30 = 20 s de 45 s), un tiempo que dependía de la
   conexión del equipo. Es la causa principal de los «> 25 min».
2. **El p95 del observatorio se medía con 20 muestras sin calentamiento**: `quantiles(n=20)[-1]`
   es casi la máxima, y una sola llamada lenta decidía. En la corrida base falló otra vez
   (`/v2/obs/health`: p95 122 ms con los servicios en marcha).
3. **Las pruebas heredaban el entorno del equipo**: `EIM_MACHINE` (la prueba de migración de
   líderes), y en general cualquier `EIM_*` (`EIM_CONTEXT_LLM=local` llamaría a Ollama,
   `EIM_DUCKDB_*`, `EIM_OBS`, carpetas de datos…). `EIM_NOTIFY` sin fijar hacía que los supervisores
   de prueba lanzaran avisos de escritorio reales en Windows.

## Qué se cambió (solo `tests/` y `pyproject.toml`; ningún umbral)

- `tests/conftest.py`: antes de importar ninguna prueba retira **todas** las `EIM_*` del equipo y
  fija `EIM_OBS=off`, `EIM_NOTIFY=0`, `EIM_DUCKDB_MEMORY=1GB`, `EIM_DUCKDB_THREADS=2` (los de
  producción). Las variables que activan a propósito una prueba opcional (motores reales de
  Freqtrade/Passivbot, `EIM_LEGACY_DIR`) se copian antes en `tests/opt_in.py`, para que esas pruebas
  sigan activándose igual que antes.
- `tests/offline.py`: la suite **no tiene red** salvo el bucle local; resolver o conectar a otro host
  falla al instante, como en un equipo desconectado (el código ya trata «red caída»).
- `tests/perf.py` (`measure`): llamadas de calentamiento descartadas, ≥ 100 muestras y el mismo índice
  de percentil `int(q·n)` que usaban las pruebas (ni la máxima ni más laxo); el fallo trae
  p50/p95/p99/máx. Usado en el observatorio (100 000 eventos), `emit()`, el sobrecosto del ciclo y el
  coste de decisión HFT.
- Marca `perf` (registrada en `pyproject.toml`) en las 10 pruebas que comparan tiempo de reloj contra
  un umbral; **siguen en el gate**: `-m "not perf"` solo sirve para aislarlas al diagnosticar.
- `tests/share/test_leaders.py`: aísla `EIM_MACHINE` (`monkeypatch.delenv`), además del conftest.
- `tests/test_suite_env.py`: fija lo anterior (sin `EIM_*` del equipo, red rechazada, bucle local ok).

Barrido: ninguna prueba usa rutas absolutas ni `USERPROFILE`; las que leen el reloj real lo hacen
siempre relativo a «ahora» (`T0 = ahora − 1 h`, `old = ahora − retención − margen`); las fechas que
formatea el código son UTC. Las que leían `EIM_*` del entorno eran las opcionales (ahora vía
`tests/opt_in.py`) y la de migración de líderes.

## Mediciones (gate completo: `ruff` + `pytest -q`, 2373 pruebas, 7 saltadas = opcionales/POSIX)

| Corrida | Condición | Resultado | Tiempo |
|---|---|---|---|
| base (código anterior) | servicios en marcha | **1 fallo** (p95 122 ms) | 25 min 29 s |
| cargada-1 | servicios + 4 procesos al 100 % + `EIM_*` hostiles¹ | verde | 20 min 22 s |
| cargada-2 | ídem | verde | 19 min 12 s |
| cargada-3 | ídem | verde | 19 min 19 s |
| servicios-1 | servicios en marcha, sin carga añadida | verde | 11 min 05 s |
| servicios-2 | ídem | verde | 11 min 18 s |
| servicios-3 | ídem | verde | 11 min 30 s |

¹ `EIM_MACHINE=juanpablo-cpu`, `EIM_CONTEXT_LLM=local`, `EIM_OBS=on`, `EIM_DATA_DIR` inexistente,
`EIM_DUCKDB_MEMORY=64MB`, `EIM_NOTIFY=1`, `EIM_OPERATE=1`, `EIM_EXECUTION=testnet`,
`EIM_SHARED_DIR` inexistente: el resultado no cambió.

Las 10 más lentas (servicios-1 · cargada-2):

| Prueba | Sin carga | Cargada |
|---|---|---|
| `legacy/test_golden::test_matches_golden[frm_brm_irm]` | 37,7 s | 77,2 s |
| `backtest/test_backtest_e2e::test_full_pipeline_report_is_reproducible` | 36,2 s | 71,9 s |
| `backtest/test_vrm::test_metrics_match_legacy` | 34,0 s | 75,6 s |
| `legacy/test_golden::test_frm_reproduces_csv_historical_columns` | 33,6 s | 65,4 s |
| `api/test_obs_api::test_queries_over_100k_events_stay_within_the_threshold` | 25,2 s | 36,2 s |
| `bots/test_jesse_examples::test_no_lookahead_truncating_future_candles_keeps_the_stance` | 14,4 s | 41,9 s |
| `agents/calendar/test_event_study::test_report_cli` | 13,4 s | 18,1 s |
| `calibration/test_calibration::test_nested_optimizes_only_on_training` | 9,8 s | 20,1 s |
| `bots/test_scorer::test_compute_persists_and_latest_reads_without_recomputing` | 9,7 s | 17,2 s |
| `api/test_paper_api::test_backtest_requires_confirm_and_runs` | 9,5 s | — |

Antes, la más lenta era `observability/test_instrument::test_cycle_survives_broken_emitter` (75 s,
casi todo descargas); ahora 4 s.

**Más de un minuto:** ninguna sin carga. Con la CPU a medias, las cuatro primeras pasan de 60 s:
son el oráculo del legado (T02: FRM/BRM/IRM sobre el CSV de 1000 velas, que es lo que se compara
contra el golden) y la reproducibilidad del backtest de extremo a extremo; su coste es cálculo puro
(no red ni disco) y escala con la CPU libre. Recortarlas exige otro fixture: queda en
`PLAN/BACKLOG.md` (T116 (4)), igual que `pytest-xdist` (fuera de alcance sin medir antes).

## Lo que queda

- **Equipo descargado y Ollama real** (entregable 6, segunda condición): no se pudo aquí. Ollama no
  está instalado, y parar los servicios rompe la corrida de 4 semanas de T31 y la de 72 h de T78
  (hasta el 2026-10-27 07:23 UTC). Se hicieron 3 corridas cargadas (carga sintética) y 3 con solo los
  servicios. Falta: tres corridas seguidas con los servicios parados y tres con Ollama generando, en
  el equipo de referencia.
- El corte de red no alcanza a los subprocesos (hoy ninguno usa la red) y el ciclo no permite
  inyectar los fetchers de liquidaciones/titulares → `PLAN/BACKLOG.md` T116 (2)(3).
