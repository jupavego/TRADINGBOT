# Guía de operación

Todo se ejecuta desde `v2/` con el entorno virtual activo. Instalación desde cero: `ONBOARDING.md`
(raíz del repositorio). Incidentes: `docs/RUNBOOK.md`. Seguridad: `docs/SEGURIDAD.md`.

## 1. Levantar el sistema (de cero a funcionando)
```bash
cd v2
python -m venv .venv && .venv/Scripts/activate        # macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m ruff check eim tests && python -m pytest -q   # gate: debe pasar
cd eim/web && npm install && cd ../..
```
Entorno idéntico al probado: `python -m pip install -r requirements-lock.txt && python -m pip install -e . --no-deps`.

| Qué | Comando (desde `v2/`) | Notas |
|---|---|---|
| Solo análisis (API + UI) | `python -m uvicorn eim.api.main:app --port 8000` y `cd eim/web && npm run dev` | UI en `http://127.0.0.1:5173` |
| Operación en papel (servicio continuo) | `python -m eim.operation run --execution paper` | API + ciclo + vigilante que relanza el proceso; copia diaria automática |
| Historia de velas al tramo histórico (T111) | `python -m eim.data.import_history --from <carpeta con la historia> [--symbol BTCUSDT] [--tf 1m]` | Cada serie del almacén tiene un tramo vivo (`data.parquet`, el que reescribe cada vela nueva) y uno histórico congelado (`history.parquet`). La orden copia al histórico solo lo anterior a la primera vela viva: puede correr con la API encendida y repetirse sin duplicar. El servicio pasa al histórico el 1 min vivo con más de 7 días cuando supera 30 días (`Store.compact`) |
| Operación en testnet | `EIM_TESTNET_API_KEY=… EIM_TESTNET_API_SECRET=… python -m eim.operation run --execution testnet` | Antes: `python -m eim.execution.smoke` (BACKLOG T30/T31) |
| Arbitraje en testnet (T45) | Prueba E2E primero: `python -m eim.execution.arb_smoke` (carry abierto→mantenido→cerrado, pata fallida deshecha, corte de red sin huérfanas). Después `EIM_ARB_EXECUTION=testnet` + claves y reiniciar la API | Solo spot + futuros testnet; pestaña «Arbitraje» → «Ejecución automática»; estado y bitácora en `data/arb_exec/` |
| Pruebas del arbitraje en papel (T45, sin cuenta) | `python -m eim.paper.arb_cli [--hold 48]` o «Bróker simulado» → «Arbitraje» → «Ejecutar pruebas» | Modo Simulado: exchange en memoria con velas 1 h y funding reales del almacén (spot 1 h: `python -m eim.arbitrage.sim sync`); informe en `data/paper/arb_tests.json` |
| Informe del periodo | `python -m eim.operation report [--from AAAA-MM-DD] [--to AAAA-MM-DD]` | Lo genera la API en marcha |
| Puerta de validación (T49) | `python -m eim.validation [informe]` → `reports/validation/validation_v1_<fecha>.md` + `.json`; `GET /v2/validation` (veredictos vigentes); `python -m eim.validation versiones` | La API la recalcula al cierre de cada vela de 4 h (tablas `val_*` en `data/paper.duckdb`). Al cambiar una estrategia o `ExecParams`, declarar ANTES de reiniciar la API las ventanas de datos que se miraron: `python -m eim.validation declarar --origin … --desde … --hasta … --nota …` (sin declaración, todo lo anterior al alta cuenta como ajuste) |
| Versiones de entrada (T137) | `python scripts/t137_entrada.py --data backups/t131_banco` (≈ 6 min, por la cola, con `PYTHONPATH=.` desde un worktree) → `reports/t137_entrada.{md,json,csv}` y `eim/validation/attempts_t137.json` | Sobre una copia temporal: nunca toca el almacén vivo. `--sample-only` solo cuenta la muestra por lectura. Reglas en `eim/validation/prereg/prereg_t137_v1.json`, inmutable |
| Literatura con evidencia (T54) | `python -m eim.literature ctx` (completa los contextos con `lit`) · `python -m eim.literature report` → `reports/literature/lit_v1_<fecha>.md` + `.json` | Con la API detenida (DuckDB admite un solo proceso escritor). El ajuste de escenarios está apagado (`eim/forecast/lit_tilt_state.json`; definición inmutable en `versions/lit_tilt_v1.json`); encenderlo = commit con `enabled: true` tras un informe que cumpla T1–T6 |
| Copy trading: líderes (T40, solo lectura) | `python -m eim.leaders discover --seconds 300` → `watch 0x…` → `run [--minutes M]` → `report --minutes 60`; con el servicio apagado, `prune [--days 7]` (T128) | Hyperliquid público, sin claves; ≤ 10 líderes por WS y el resto por REST; base `data/leaders.duckdb` (proceso propio) |
| Copy trading: evaluación (T41) | `run` evalúa cada 5 min y escribe `data/leaders/board_*.json` (pestaña «Líderes», agente `smart_money`); con el vigilante apagado: `score [--portfolio]` | El veredicto (aprobado/vigilancia/descartado) lo fija el scorecard; solo aprueba con ≥ 30 operaciones y ≥ 7 d observados adelante; `unwatch` deja de capturar |
| Copy trading: servicio continuo | `python -m eim.leaders supervise` (lo lanza `scripts/servicio_continuo.ps1`, §6) | `run` sin fin bajo vigilante de proceso: lo relanza si cae o si su latido se detiene; uno solo por carpeta de datos |
| Captura HFT (T78) | Servicio: `python -m eim.data.collectors.hft_supervise BTCUSDT --root data` (lo lanza `scripts/servicio_continuo.ps1`, §6). A mano: `python -m eim.data.collectors.hft_ops --root data` (QC + compactación + retención + resumen), `python -m eim.data.collectors.hft_verify --root data --all [--out carpeta]` (ida y vuelta y `.npz` del simulador) | Escribe `data/micro_hft/` (no toca `data/micro/` de T23): todos los diffs de `depth@100ms`, `bookTicker`, `aggTrade`, `markPrice@1s` y `forceOrder` con la hora de Binance y la de llegada; snapshot REST cada 5 min para verificar el libro (top-10 exacto). QC por hora en `data/micro_hft/qc/` y resumen en `qc/symbol=BTCUSDT/summary.json` (horas completas, coincidencia top-10, huecos no detectados, MB/día, proyección a 30 días, y el veredicto de T78 por ventana y por racha). Una hora es completa si ≥ 99 % de sus segundos tienen libro utilizable, no tiene huecos sin detectar y su top-10 coincide; la cobertura por segundo de `bbo` y de `mark` se publica pero no decide (T147). Medido en la corrida de aceptación (10 h del 2026-10-24, 07–17 UTC): ≈ 830 MB/día (≈ 410 bookTicker + 390 profundidad; 70–84 MB/h en la apertura de EE. UU., ≈ 15 MB/h de madrugada) → ≈ 25 GB en 30 días, ≈ 37 GB con la retención de 45 días; la compactación ahorra poco disco (≈ 5–10 %) pero deja un archivo por hora |
| Copia de seguridad a demanda | `python -m eim.data.backup create` | Las tres bases (`reports`, `paper`, `leaders`) + observatorio y estado. Si la API está en marcha, se la pide a ella; `leaders.duckdb`, al servicio de líderes. La CLI usa `EIM_DATA_DIR`, `EIM_BACKUP_DIR` y `EIM_BACKUP_KEEP` como la API |
| Ver las colas entre etapas (T123) | `GET http://127.0.0.1:8000/v2/obs/queues` o, en la mesa, «Mapa del sistema» → «Colas entre etapas» | Por frontera de la tubería: tope, qué hace al llenarse y, por proceso, descartes, esperas, ocupación máxima y última causa, con su fuente. Cada proceso informa al cambiar algo y, si no, cada 10 min; sin informe sale «sin datos» con el motivo. Inventario y políticas: `PLAN/notas/T123_colas.md`. Medir la memoria con un productor 10×: `python -I scripts/t123_carga.py --secs 20` (desde `v2/`, ≈ 1,5 min, un proceso de hasta `--tope-mb`) |
| Verificar la traza de una vela (T74) | `python scripts/obs_verify_traces.py` (desde `v2/`; `--provider spot` si `fapi.binance.com` da 451; `--wait` segundos; `--keep` conserva los datos) | Arranca la API real en papel con carpeta temporal (no toca tus datos ni envía nada a un exchange), espera un ciclo y comprueba la traza más reciente en `/v2/obs/traces`: fuente y cobertura de datos, una señal por agente, síntesis, pronóstico, plan, riesgo y —solo si el riesgo aprobó— la cadena de órdenes. Código de salida 0 si todo lo obligatorio pasa |

**Nunca** lances la API con `--host 0.0.0.0`: además de quedar en la red, el middleware de
`eim/api/security.py` rechazará a los clientes remotos (403) y los `Host` ajenos (400).

## 2. Variables de entorno
Todas son opcionales: sin ninguna, el sistema arranca en modo Análisis con los defectos de la tabla.
La tabla nombra **cada** variable `EIM_*` que lee el código (`eim/`, `scripts/` y las opcionales de
las pruebas en `tests/opt_in.py`); `tests/docs/test_env_vars.py` falla en el gate si aparece una
que no esté aquí. Al añadir una variable, añade su fila con el nombre completo.

| Variable | Defecto | Uso |
|---|---|---|
| `EIM_DATA_DIR` | `data` | Almacén (parquet, DuckDB, estado) |
| `EIM_REPORTS_DB` | `EIM_DATA_DIR/reports.duckdb` | Ruta de la base de reportes, si se quiere fuera de la carpeta de datos |
| `EIM_DUCKDB_MEMORY`, `EIM_DUCKDB_THREADS` | `1GB`, `2` | Tope de memoria e hilos de cada conexión DuckDB persistente (`eim/data/duck.py`); lo que no cabe se derrama a disco en vez de morir con `Out of Memory`. En `juanpablo-cpu` está en `2GB` por la copia en caliente de `leaders.duckdb` (`PLAN/ESTADO_PROYECTO.md` §3) |
| `EIM_EXECUTION` | `off` | `paper` / `testnet` |
| `EIM_OPERATE`, `EIM_OPERATE_TF`, `EIM_OPERATE_POLL_S` | `0`, `1h`, `60` | Servicio continuo (lo fija `eim.operation run`) |
| `EIM_OPERATE_EXTRA_TFS` | `4h` | Marcos que el servicio continuo analiza además de `EIM_OPERATE_TF`, separados por comas; vacía (`""`) los quita |
| `EIM_OPERATION_REPORTS` | `reports/operation` | Carpeta de los informes semanales de la operación (T31) |
| `EIM_EDGE_RESULTS` | `reports/edge/edge_results.json` | Resultados de la puerta de edge (T27) que la API lee para el informe del periodo |
| `EIM_BACKUP_DIR`, `EIM_BACKUP_KEEP` | `backups`, `14` | Copias; se conservan las N completas más recientes (§3) |
| `EIM_ALLOWED_HOSTS` | `127.0.0.1,localhost,::1` | Cabeceras `Host` aceptadas |
| `EIM_API_TOKEN` | — | Sin él, ningún cliente remoto entra. Con él: `Authorization: Bearer <token>`; en WebSocket, subprotocolo `eim-token.<token>` (los navegadores no admiten cabeceras ahí) |
| `EIM_CORS_ORIGINS` | `http://127.0.0.1:5173,http://localhost:5173` | Orígenes del navegador (también para el WebSocket) |
| `EIM_WS_URL` | `wss://fstream.binance.com/market/ws` | Flujo de velas en vivo; si la red bloquea Binance Futures, `wss://stream.binance.com:9443/ws` (spot) |
| `EIM_HEARTBEAT_S`, `EIM_SNAPSHOT_BARS`, `EIM_AUTO_HISTORY`, `EIM_RECON_S` | `15`, `500`, `1`, `30` | Latido del WebSocket de la interfaz (s), velas por instantánea de análisis, relleno automático de historia al arrancar (`0` lo apaga) y segundos entre reconciliaciones con el bróker |
| `EIM_TESTNET_API_KEY`, `EIM_TESTNET_API_SECRET` | — | Claves de la testnet de futuros. Solo testnet y sin permiso de retiro |
| `EIM_TESTNET_URL`, `EIM_TESTNET_WS_API_URL` | `https://testnet.binancefuture.com`, `wss://testnet.binancefuture.com/ws-fapi/v1` | REST y API WebSocket de la testnet de futuros; el bróker rechaza cualquier host que no sea de testnet (en REST también vale `demo-fapi.binance.com`) |
| `EIM_CALENDAR`, `EIM_CALENDAR_S` | `1`, `21600` | Calendario económico (Fed/BLS/BEA): consulta al arrancar y cada 6 h en `data/calendar/` (T36). `0` lo apaga |
| `EIM_OBS` | `on` | Observatorio (T72): `off` apaga la emisión de eventos (JSONL en `data/obs/spool/`). Emitir nunca rompe ni frena el ciclo; los descartes se cuentan. T73: la API indexa esos JSONL cada 5 s en `data/obs/obs.duckdb` (derivado, entra en la copia diaria, no viaja entre equipos) y lo sirve en solo lectura en `/v2/obs/*`; estado y retraso en `/v2/obs/health`. Retención: spool 7 d, eventos 30 d, `runs`/`decisiones` 180 d. Si se pierde la base, se reconstruye indexando el spool |
| `EIM_ARBITRAGE`, `EIM_ARBITRAGE_S` | `1`, `60` | Escáner de arbitraje Binance (REST público, solo lectura): fotografía cada minuto en `data/arbitrage/` (últimas 20; cada 10 s con `EIM_ARB_EXECUTION=testnet`, T128), pestaña «Arbitraje» y mensaje WS `arbitrage` (T39). `0` lo apaga. Modo Análisis: no ejecuta |
| `EIM_ARB_ASSETS`, `EIM_ARB_TRI_ASSETS` | `BTC`, `USDT,BTC,BNB,SOL,XRP` | Foco actual (T122, 2026-10-22: solo BTC): activos del escáner de arbitraje (funding, base, perpetuos relacionados) y de sus ciclos triangulares; sin ETH. `BTC,ETH` lo devuelve |
| `EIM_ARB_EXECUTION`, `EIM_ARB_EXEC_S` | `off`, `60` | `testnet`: ejecución automática de arbitraje (T45) en spot testnet + futuros testnet con la fotografía del escáner; ciclo cada N s. Riesgo `eim/risk/versions/risk_arb_v1.json` (cuenta total: margen y exposición de toda la cuenta de futuros; kill-switch compartido) |
| `EIM_SPOT_TESTNET_API_KEY`, `EIM_SPOT_TESTNET_API_SECRET` | — (usa las de futuros) | Clave de la testnet spot; en la cuenta demo de Binance la de futuros vale para ambas. Sin permiso de retiro |
| `EIM_SPOT_TESTNET_URL` | `https://testnet.binance.vision` | REST de la testnet spot (también vale `demo-api.binance.com`); otro host se rechaza |
| `EIM_ARB_ALERT_SCORE`, `EIM_ARB_ALERT_S` | `3`, `60` | Alerta de arbitraje: puntuación del selector ≥ umbral (pb/día ajustados por riesgo) sostenida N segundos de escaneos seguidos (T39) |
| `EIM_VAL_ATTEMPTS` | `1` | La API da de alta en el registro de T49 los intentos de `eim/validation/attempts_t137.json` (T137). Nacen retirados y solo hacen más exigente Holm; no cambian lo que abren los perfiles |
| `EIM_PAPER`, `EIM_PAPER_S` | `1`, `60` | Bróker simulado (T47/T48): cada ciclo trae velas de 15 m/1 h/4 h y funding de BTCUSDT y analiza las velas cerradas nuevas de los tres marcos → `data/paper.duckdb`. Tras cada ciclo, sus ganchos (validación al cierre de 4 h, libro fijo cada hora, puntuación de bots, setups) corren en su propio hilo a nivel batch y laten como `paper.hooks`; el ciclo no los espera (T128; estado en `/v2/paper` → `live.hooks`). `0` lo apaga. Siempre SIMULADO |
| `EIM_MICRO_IGNORE_LIQ_GAPS` | vacío | `1` = la microestructura no cuenta como huecos del flujo las reconexiones del recolector de liquidaciones (`liq:*` en `micro/gaps`, T150): 38,9 % → 25,2 % de velas incompletas en 1 h. Apagado hasta el cierre de T31 porque también cambia lo que lee el bróker simulado; encenderlo entonces |
| `EIM_PAPER_VARIANTS` | vacío | Corridas aparte en papel (T143, ◆ 2026-11-10), separadas por comas; hoy solo `t143`: la misma decisión que la mesa principal (reutiliza sus contextos; no corre agentes) con otra ejecución —entrada maker en 1 h/4 h, puerta de marcos a 0,15 R y riesgo con costo— y su propia base `data/paper_t143.duckdb`, que entra en la copia. Sin intentos de validación, sin Observatorio y sin `op_alerts`. Solo lectura: `GET /v2/paper/variant/t143` y `.../ledger.csv`. T31 sigue con los valores por defecto hasta su cierre |
| `EIM_COPY_SIM` | `tracked` | Copia simulada de líderes en el servicio de líderes (T42): `tracked` copia a todos los capturados como medición, `approved` solo a los aprobados por el scorecard, `off` la apaga |
| `EIM_SHARED_DIR`, `EIM_SHARE_GIT_URL`, `EIM_MACHINE` | — | Experiencia compartida entre equipos (T61, §3.1): carpeta de nube compartida o repo git de transporte, y alias único de esta máquina (también `python -m eim.data.share setup`) |
| `EIM_SHARE_AUTO`, `EIM_SHARE_IMPORT_S`, `EIM_SHARE_EXPORT_S`, `EIM_SHARE_KEEP` | `1`, `3600`, `21600`, `3` | Modo automático de la experiencia compartida (solo si hay carpeta o repo configurados): `0` lo apaga; cadencias de importación y exportación (s) y exportaciones propias que se conservan por tipo |
| `EIM_OFFSITE_REPO`, `EIM_OFFSITE_KEEP` | `Santivego/eim-shared-data`, `7` | Copia externa (T125, `docs/CONTINUIDAD.md`): repo privado de GitHub cuyas versiones guardan las copias completas, y cuántas conserva cada equipo |
| `EIM_PRIORITY` | apagada | `on`: cada servicio fija al arrancar la prioridad de su papel (recolectores, servicios, mantenimiento; T126, `eim/operation/priority.py`). La pone `scripts/servicio_continuo.ps1`; las pruebas y las órdenes a mano no cambian de prioridad |
| `EIM_NOTIFY` | `1` | Avisos de escritorio de Windows desde `eim/operation/notify.py`; `0` los apaga. `servicio_continuo.ps1` la pone en `0` porque los avisos salen por el icono de la bandeja |
| `EIM_FRED_API_KEY` | — | Opcional (gratuita): valores real/anterior/revisado de IPC, NFP, PCE, PIB, IPP desde FRED. Sin ella los eventos salen sin valores |
| `EIM_YOUTUBE_API_KEY`, `EIM_YOUTUBE_API_KEY_FILE` | —, `~/.eim/youtube_api_key.txt` | Opcional (T64): clave de la YouTube Data API v3 del proyecto de Google del usuario. Si no está, se lee del archivo `EIM_YOUTUBE_API_KEY_FILE` (por defecto `~/.eim/youtube_api_key.txt`, fuera del repo; así está en `juanpablo-cpu` desde el 2026-11-10). Solo metadatos (`python -m eim.video discover`); gasto acotado por `quota_units_per_day` de `eim/video/versions/watchlist_vN.json`. Nunca se registra ni entra a git |
| `EIM_VIDEO` | — | `1` = `servicio_continuo.ps1` lanza el servicio de video (`python -m eim.video run`, una pasada por hora, latido en `data/video/heartbeat.json`). Sin clave de YouTube el latido dice `sin_fuente` |
| `EIM_LOCALAI_DIR` | — (el banco usa `data/localai`) | Motores de IA locales (T62, §7): carpeta **fuera del repo y en disco local** (no en una unidad de red) con el entorno aparte (`venv`), los binarios y los pesos. En la portátil de referencia `E:\eim-localai` (C: tiene 6 GB libres) |
| `EIM_LLAMACPP_SERVER`, `EIM_WHISPERCPP` | `EIM_LOCALAI_DIR\llama.cpp\llama-server.exe`, `…\whisper.cpp\whisper-cli.exe` | Binarios de llama.cpp y whisper.cpp para el banco de T62 (opcionales) |
| `EIM_OLLAMA_EXE` | — (`servicio_continuo.ps1` prueba `E:\Ollama\ollama.exe`) | Ollama que lanza `servicio_continuo.ps1` si existe; definida y sin acceso, la API lo avisa («LLM local no disponible», T128) |
| `EIM_CONTEXT_LLM` | — (`local` si el script lanzó Ollama) | `local` pone el agente de contexto sobre el LLM local (T24); sin ella, el contexto usa `ANTHROPIC_API_KEY` si existe o queda «sin datos» |
| `EIM_LOCAL_LLM_HOST`, `EIM_LOCAL_LLM_MODEL` | `http://127.0.0.1:11434`, `qwen3:4b` | Servidor y modelo del LLM local (contexto y banco de T62) |
| `EIM_LOCALAI_LLM`, `EIM_LOCALAI_VISION`, `EIM_LOCALAI_ASR`, `EIM_LOCALAI_OCR`, `EIM_LOCALAI_EMBED` y sus modelos `EIM_LOCALAI_LLM_MODEL`, `EIM_LOCALAI_VISION_MODEL`, `EIM_LOCALAI_ASR_MODEL`, `EIM_LOCALAI_OCR_MODEL`, `EIM_LOCALAI_EMBED_MODEL` | `off` (modelos: `qwen3:4b-instruct`, `qwen3-vl:2b-instruct-q4_K_M`, `small`, `rapidocr-3.10.0`, `qwen3-embedding:0.6b`) | Motor de cada etapa de la capa `eim/localai` (T63): `ollama`, `llamacpp`, `claude` (solo LLM, sale del equipo), `faster-whisper`, `rapidocr`, `off`. Solo modelos de la lista aprobada (`localai/catalog.py`) |
| `EIM_LOCALAI_OLLAMA_HOST`, `EIM_LOCALAI_LLAMACPP_HOST`, `EIM_LOCALAI_LLAMACPP_KEY`, `EIM_LOCALAI_LLAMACPP_GGUF` | `http://127.0.0.1:11434` (o `EIM_LOCAL_LLM_HOST`), — | Servidores de la capa (solo 127.0.0.1; llama-server exige clave y el GGUF para verificar sus pesos) |
| `EIM_LOCALAI_TIMEOUT_S`, `EIM_LOCALAI_WAIT_S`, `EIM_LOCALAI_RETRIES`, `EIM_LOCALAI_RAM_MARGIN_MB`, `EIM_LOCALAI_CPU_S_PER_DAY` | `900`, `1800`, `1`, `1024`, `0` (sin tope) | Recursos de la capa (T63): tope por llamada, espera en cola, reintentos ante motor caído, RAM libre que debe quedar además del pico del modelo (si no, la etapa se aplaza) y presupuesto de cómputo por día UTC |
| `EIM_LOCALAI_DB` | `<EIM_DATA_DIR>/localai/localai.duckdb` | Registro de salud `localai_calls` (T63) |
| `EIM_LIBRARY_DIR`, `EIM_LIBRARY_INDEX`, `EIM_TESSERACT` | `data/library/books`, `data/library/index`, autodetección | Biblioteca de trading (T52): carpeta de los libros del usuario (fuera del repo), índice local (catálogo, texto por página, caché de OCR) y ruta de `tesseract.exe` si no está en el PATH |
| `EIM_LIBRARY_LLM` | apagada | `1` (con `ANTHROPIC_API_KEY`) enciende las preguntas a la biblioteca con Claude (`python -m eim.library ask`); solo informa |
| `EIM_OPENALEX_KEY` | sin clave | Clave propia de OpenAlex para la biblioteca digital (T151, `python -m eim.library.digital verify`); sin ella se comparte el cupo gratuito por IP. Nunca se envía un correo. Caché y textos legales en `data/library/digital/` |
| `EIM_BOT_FREQTRADE_PY`, `EIM_BOT_FREQTRADE_ENGINE` | — | Escuadrón de bots (`docs/BOTS.md`): intérprete del entorno aparte de Freqtrade y versión fijada del motor (p. ej. `2026.9`; si la instalada difiere, la salida se rechaza). Sin ellas, los bots de Freqtrade no producen posturas |
| `EIM_BOT_NFI_DIR` | `data/bots/nostalgia-for-infinity` | Checkout de NostalgiaForInfinity en el SHA de su ficha (solo relleno histórico) |
| `EIM_BOT_PASSIVBOT_PY`, `EIM_BOT_PASSIVBOT_DIR` | — | Carril de simulación de Passivbot (`python -m eim.bots.sim_lane`): intérprete de su entorno y checkout en el SHA de la ficha; sin ellas no corre |
| `EIM_BOT_FREQTRADE_DIR`, `EIM_LEGACY_DIR` | —, `legacy/F7` | Solo pruebas opcionales (`tests/opt_in.py`): checkout de Freqtrade para la prueba con el motor real, y copia del legado para la comprobación de sensibilidad de la regresión |

## 3. Copias de seguridad
Qué se copia (`eim/data/backup.py`, T32 + T115): **las tres bases con historial** —`reports.duckdb`
(reportes, decisiones de riesgo, libro de planes, alertas, capital, pronósticos), `paper.duckdb`
(bróker simulado: contextos, operaciones, validación y el registro inmutable de sugerencias de T51)
y `leaders.duckdb` (capturas en vivo de líderes y la copia simulada, irrepetibles: el exchange solo
sirve las 10 000 ejecuciones más recientes)— más `obs.duckdb` (observatorio, derivado), kill-switch,
estado y registros del servicio, QC de la captura HFT, versiones de parámetros (`eim/risk/versions`,
`eim/calibration/versions`) y un `manifest.json` con SHA-256 por archivo, filas por tabla de cada
base, camino y segundos de cada copia, bases ausentes y commit de git. Las velas solo con
`--with-market` (se pueden volver a descargar). **Nunca** se copian claves.

**Cada base por su camino** (`eim/data/backup_dbs.py`):
| Base | En marcha la tiene | Copia en caliente |
|---|---|---|
| `reports.duckdb` | la API | su conexión, entre dos ciclos de operación (coherente con el estado del servicio) |
| `paper.duckdb`, `obs.duckdb` | la API | su conexión, sin frenar el ciclo |
| `leaders.duckdb` | el servicio de líderes | se le pide una instantánea (`eim/data/leader_snapshot.py`: un archivo `data/leaders/snapshot_request-<t>.json` por pedido, atendidos en orden; la hace en una tarea aparte, sin parar la captura ni su bucle) |

Si nadie la usa, cada base se copia **en frío**. La copia en caliente es una sola sentencia
`COPY FROM DATABASE` en un cursor propio: una transacción, coherente aunque los escritores sigan
(no se les retiene el cerrojo). Una base **en uso que no se puede pedir** (servicio de líderes
colgado, API caída con la base retenida) o dañada **no rompe la copia**: queda *ausente con motivo*
en el manifiesto (`absent`), la copia sale como «incompleta» y `verify` la distingue de una copia
dañada (salida 2 = íntegra pero incompleta; 1 = dañada).

- **Automática:** con el servicio de operación, una copia por día UTC en `EIM_BACKUP_DIR`, en un hilo
  aparte: el ciclo solo espera el tramo de `reports.duckdb` + estado (`held_s` en el manifiesto y en
  el registro `copia_seguridad`). Si falla, alerta `copia_seguridad` (una vez) y se reintenta cada
  hora sin detener la operación; si sale incompleta, alerta «Copia de seguridad incompleta» con el
  motivo y no se repite ese día (corregir y lanzar `create` a mano).
- **A demanda:** `python -m eim.data.backup create [--with-market]` o `POST /v2/backup` (cabecera
  `X-EIM-Confirm: backup`). La CLI copia en frío; si una base de la API está en uso, se la pide a la
  API (que pide a su vez la de líderes a su servicio); si la API no responde, copia en frío lo que
  esté libre y deja el resto ausente con motivo. Salida 0 = completa, 2 = incompleta.
- **Verificar:** `python -m eim.data.backup verify [carpeta]` (por defecto la última): hashes, filas por
  tabla de cada base y bases ausentes. Hazlo tras cada copia manual.
- **Listar:** `python -m eim.data.backup list` (marca las incompletas).
- **Retención:** `EIM_BACKUP_KEEP` (14) cuenta copias **completas**: se conservan las N completas más
  recientes y, aparte, las N más recientes de cualquier tipo (una racha de copias incompletas nunca
  borra la última completa). Una copia a medias (`.eim_….partial`, proceso interrumpido) nunca cuenta
  y se borra en la siguiente poda (pasada 1 h, por si es una copia en curso).
- **Restaurar:** ver `docs/RUNBOOK.md` §5.
- **Fuera del equipo (T125):** `backups/` está en `.gitignore` y vive en el mismo disco. La copia
  externa la sube `python -m eim.continuity publish` (o `scripts/copia_externa.ps1`, cada día con
  `scripts/instalar_copia_externa.ps1`) a la versión `eim-copias` del repo privado de datos
  (`EIM_OFFSITE_REPO`, por defecto `Santivego/eim-shared-data`), en partes con SHA-256, con los
  extras (cambios sin confirmar, memoria de Claude, estado pequeño); se recupera con
  `offsite pull` + `backup restore`. Una subida cortada retoma desde la última parte subida, y cada
  parte se reintenta 3 veces (T127). El script pasa por la cola de trabajos pesados, así que se pausa
  si la captura HFT sufre. Detalle: `docs/CONTINUIDAD.md`.
- **Captura HFT (T78):** la copia lleva solo los JSON de calidad (`state/micro_hft_qc/`), nunca los crudos de `data/micro_hft/` (≈ 830 MB/día; se podan a los 45 días). Para conservar más tiempo un tramo para T80/T84, copiarlo a otro disco a mano.
- **Tamaño y tiempo** (medido en vivo el 2026-10-24 16:17 UTC, servicios en marcha): copia completa
  de 672,5 MB en 41 s (53 archivos): `reports` 1,4 s, `paper` 2,5 s y `obs` 2,1 s en caliente;
  `leaders` (12 tablas, 3,26 M filas) 22 s como instantánea del servicio de líderes (con el servicio
  anterior a T115, que la hacía dentro de su bucle y con el archivo sin compactar, llegó a 278 s).
  El ciclo de operación quedó retenido **1,5 s** (`held_s`) y siguió en hora. Con
  `EIM_BACKUP_KEEP=14`, ≈ 9–10 GB; la base de líderes crece ≈ 50 MB/día. La espera de la
  instantánea sigue mientras avance (la nuestra o la que va delante en la cola): 120 s sin que el
  servicio atienda ni haya nada en curso, o 300 s parada, = ausente con motivo.
- **Al desplegar cambios del protocolo de instantáneas** (`eim/data/leader_snapshot.py`), reiniciar
  **la API y el servicio de líderes** a la vez (§6): los dos lados deben hablar la misma versión.

### 3.1 Experiencia compartida entre colaboradores (T61)
Las bases (`data/*.duckdb`, `*.parquet`) **no viajan por git** (`.gitignore`): cada equipo acumula su
propio historial (contextos del bróker simulado, registro de intentos de validación, capturas y
bitácora de líderes). T61 los une **por exportación**: cada máquina exporta lo suyo a una carpeta de
nube compartida (Drive/OneDrive) y un comando importa lo de las demás **sin duplicar, sin pisar y sin
inflar la evidencia**. Todo en modo SIMULADO; nunca viajan claves.

**Transporte.** Dos opciones; ambas dejan el mismo formato (`<máquina>/<fecha>/` con Parquet + manifest):
- **Repo git PRIVADO aparte** (si no hay nube compartida): `setup --git-url <repo>`. Cada máquina publica
  **solo su rama** `machine/<id>` (un único commit raíz sobrescrito con `push --force`: el servidor guarda
  solo la última foto y la historia no crece) y lee las ramas de las demás con clones superficiales en
  `data/share_repo/view/`. Nadie escribe en la rama de otro: sin conflictos. Usa las credenciales de git del
  equipo (gestor de credenciales / `gh auth`); cada colaborador necesita acceso de escritura al repo. Una
  tabla de más de 64 MB viaja en partes (`<tabla>.partNNN.parquet`, formato 2 del manifest, T117), así
  que ningún archivo llega al límite de GitHub (un archivo > 90 MB se rechaza igualmente). **Nunca**
  apuntes esto al repo del código. Repo del proyecto: `https://github.com/Santivego/eim-shared-data`
  (privado). Medido el 2026-10-25: una exportación completa pesa ~160 MB, subirla lleva ~3 min y la
  primera bajada en un equipo nuevo, ~1,5 min.
- **Carpeta de nube** (Drive/OneDrive): `setup --shared-dir <carpeta>`.

**Automático (lo normal).** Configura una vez y el sistema hace el resto:

```bash
python -m eim.data.share setup --git-url https://github.com/<usuario>/eim-shared-data.git --machine juan-portatil
python -m eim.data.share setup --shared-dir "C:\Users\...\OneDrive\EIM_compartido" --machine juan-portatil
```
(`--machine` es un alias **único** de tu equipo; no lo cambies después: es tu carpeta/rama y la
procedencia de tus filas. También sirven las variables `EIM_SHARE_GIT_URL`, `EIM_SHARED_DIR` y
`EIM_MACHINE`.) Reinicia la API y
el servicio de líderes (`servicio_continuo.ps1`). Desde entonces, **dentro de esos procesos**:
- cada hora (`EIM_SHARE_IMPORT_S`) miran la nube: si otra máquina tiene una exportación nueva la **unen
  en vivo** (bajo el cerrojo de la base, en una transacción, con copia previa en caliente en
  `EIM_BACKUP_DIR/pre-import_…`; se conservan las 3 últimas), y si llegaron contextos o versiones nuevos
  recalculan los veredictos de la puerta de validación sobre la **unión** de intentos;
- cada 6 h (`EIM_SHARE_EXPORT_S`) exportan lo propio **solo si cambió** (la API: `reports`+`paper`; el
  servicio de líderes: `leaders`; en `EIM_SHARED_DIR/<máquina>/<fecha>-api|-leaders/`), y podan sus
  exportaciones antiguas (`EIM_SHARE_KEEP`, 3 por tipo);
- un fallo (nube sin sincronizar, exportación corrupta, esquema más nuevo) se anota y se reintenta en 10 min,
  sin tocar la operación. Estado y último error: `GET /v2/share/status`; informes de cada importación en
  `data/share/import_<id>.json`. `EIM_SHARE_AUTO=0` lo apaga.
Los líderes importados empiezan a capturarse en el siguiente reinicio del servicio de líderes.

**Manual (equipo nuevo, o sin servicios en marcha).** Los comandos de abajo hacen lo mismo a mano.
Variables (PowerShell: `$env:NAME='…'`; para que persistan, variables de usuario de Windows):

| Variable | Qué es |
|---|---|
| `EIM_SHARED_DIR` | Carpeta de la nube compartida (p. ej. `…\EIM_compartido`). Cada máquina escribe **solo** en `EIM_SHARED_DIR/<su_id>/`: la nube no genera conflictos. |
| `EIM_MACHINE` | Alias legible y **único** de tu equipo (`juan-portatil`). Sin él se crea un id estable en `data/machine_id`. |
| `EIM_SHARE_AUTO`, `EIM_SHARE_IMPORT_S`, `EIM_SHARE_EXPORT_S`, `EIM_SHARE_KEEP` | Modo automático: `0` lo apaga; cadencias (3600 s, 21600 s) y exportaciones propias que se conservan (3) |

**Rutina manual.**
1. **Importar** (con API y servicio de líderes **detenidos**, ver §6):
   `python -m eim.data.share import` → simulacro: por tabla y por máquina de origen, filas
   *nuevas / ya estaban / en conflicto / incompatibles*. No escribe nada. Si el informe es el
   esperado: `python -m eim.data.share import --apply` (copia previa en `EIM_BACKUP_DIR/pre-import_…`,
   una transacción por base, `import_log`, informe en `data/share/import_<id>.json` y recálculo de los
   veredictos; `--no-recompute` lo omite).
2. **Exportar:** `python -m eim.data.share export` (puede correr con el servicio en
   marcha: si una base está en uso pide una copia coherente a la API —`POST /v2/share/snapshot`— y al
   servicio de líderes). `python -m eim.data.share status` lista la última exportación de cada máquina.
3. Importar es **idempotente** (repetirlo no cambia nada) y la unión es **conmutativa** (A∪B = B∪A).

**Qué viaja y qué no.**
- *Viaja* (unión por clave natural): `reports`, `sim_trades`, `paper_ctx` (de los contextos salen,
  deterministas, las ideas y operaciones), `leaders`, `leader_fills/funding/leverage/positions/follow`,
  `leader_recon/gaps` (con columna `machine`), `copy_journal` (se reasigna su `seq`).
- *Versiones de validación* (`val_versions`, `val_windows`): se unen por `(estrategia@marco, huella)`;
  se reasignan `n` y `parent` locales (los `n` que ya tenías no cambian) y las ventanas de ajuste se
  **unen** (más ventanas = más datos descartados de «fuera de muestra», nunca menos). Las versiones
  importadas entran retiradas: la vigente la decide el código de tu máquina. Holm cuenta la unión de intentos.
- *No viaja*: velas, funding, calendario y biblioteca (cada máquina los descarga); veredictos,
  pronósticos y tableros (derivados: se recalculan); **kill-switch, latidos, `copy_state`, libro de la
  subcuenta simulada, `op_*`, `risk_decisions`, diario de la protección `paper_protection*` (T110)**
  (estado de la máquina: el kill-switch de una máquina nunca apaga ni enciende el de otra);
  **claves y `.env`** (nunca).

**Sin inflar la evidencia.** El bróker es determinista: la misma `estrategia@marco@versión` en la misma
vela es **la misma operación** en cualquier máquina. Dos equipos corriendo lo mismo no suman `n`; la
experiencia nueva viene de versiones/estrategias distintas, de tramos de tiempo no cubiertos y de
capturas en vivo no reproducibles (líderes). Los «días adelante» de líderes se cubren por **unión de
intervalos** entre fotos, no por suma. La procedencia (cuántas filas aportó cada máquina y cuántas
se descartaron por duplicadas) sale en `GET /v2/validation` (campo `provenance`) y en el informe de validación.

**Conflictos.** Misma clave y contenido distinto (p. ej. dos reportes del mismo agente en la misma vela
con cifras distintas, por velas descargadas en momentos distintos): **se conserva lo local**, se cuenta
en el informe y queda en `share_conflicts` (columnas que difieren y la fila remota en JSON). Revísalos
con `SELECT * FROM share_conflicts` (DuckDB); si el otro equipo tiene razón, corrige allí y exporta de nuevo.
Un manifest alterado, un archivo con hash distinto, o un esquema más nuevo que el de tu código
**rechaza** esa exportación entera con un mensaje claro (si es lo último: `git pull`). Una exportación
que la nube aún está sincronizando se rechaza por «falta archivo»: espera y repite.

**Colaborador nuevo (primera importación completa).** Clona el repo, ejecuta `python -m eim.data.share
setup …`, luego `python -m eim.data.share import` (simulacro) y `--apply` con la API detenida: crea las
bases vacías y trae todo el historial de los demás. Después arranca normalmente (las velas se descargan
solas) y todo sigue automático.

**Límites.** La importación manual requiere las bases libres (si no, falla con el mensaje «detén la API y
el servicio de líderes» y no cambia nada; la automática corre dentro de los procesos que las tienen); la atomicidad es por base (de ahí la copia previa). No hay
sincronización en vivo ni autenticación entre colaboradores. Nunca pongas una base DuckDB viva dentro de
la carpeta compartida: solo viajan Parquet + `manifest.json` (SHA-256 por archivo, commit, esquema).
En modo automático, la unión retiene la base mientras dura: medido (T117) con datos reales, ~10 s en
`leaders.duckdb` aunque no llegue nada nuevo y ~30 s con ~140 000 filas nuevas (la captura espera; el
bucle sigue). Si un equipo trae mucho historial de golpe (su primera mezcla), aplícalo a mano.

**Rutina de cada colaborador (T117).**
- *Una vez por equipo:* alias `--machine` **distinto** del de los demás y fijo para siempre. Antes del
  primer `setup`, mira `git ls-remote <repo>`: si ya existe la rama `machine/<tu-alias>` es de otro
  equipo (el código no lo impide y dos equipos con el mismo id se pisarían la rama). La primera mezcla
  con un equipo nuevo: simulacro en los dos sentidos, revisión y, después, `--apply` (o el arranque con
  el modo automático). Detalle y protocolo: `PLAN/notas/T117_primera_mezcla.md`.
- *Al empezar la jornada:* actualizar el código (`git pull`; los dos equipos deben leer el mismo
  formato, y uno más nuevo se rechaza con «actualiza el código») y arrancar el servicio
  (`abrir_interfaz.ps1`). Comprobar en `GET /v2/share/status` (o `python -m eim.data.share status`) que
  `error` está vacío y que `imported` tiene la última foto del otro equipo. Si el otro publicó algo,
  la API y el servicio de líderes lo unen en ≤ 1 h.
- *Durante y al terminar:* nada obligatorio. Cada 6 h se exporta solo lo que cambió. Si vas a apagar el
  equipo varios días, publica antes lo último con `python -m eim.data.share export` (en caliente; en
  git publica tu rama).
- *Si algo no cuadra:* el informe de cada importación está en `data/share/import_<id>.json`, los
  conflictos en `share_conflicts` (DuckDB) y la copia previa en `backups/pre-import_…` (3 últimas). La
  procedencia está en `GET /v2/validation` → `provenance` (duplicadas = de la última foto de cada
  máquina, las que ya estaban).
- *Qué NO viaja nunca* (cada equipo conserva lo suyo aunque se mezcle todo lo demás): kill-switch y
  estado de la operación (`kill_switch.json`, `operation/`, latidos), `risk_decisions`, `op_*`, libro de
  la subcuenta simulada y `copy_state`, diario de la protección (T110), el observatorio, velas, funding,
  calendario y biblioteca (cada equipo los descarga), los derivados (veredictos, pronósticos y tableros:
  se recalculan) y **las claves y el `.env`**.

**Pendiente ◆ (T61, vía T117):** el usuario revisa los dos simulacros de la primera mezcla real con el
segundo equipo antes de dar T61 por cerrada (estado en `PLAN/notas/T117_primera_mezcla.md`).

## 4. Versionado de parámetros
- Un conjunto de parámetros publicado es **inmutable**: cambiar límites de riesgo = `risk_v2.json`
  nuevo en `eim/risk/versions/` (el campo `version` debe coincidir con el nombre); calibraciones en
  `eim/calibration/versions/` con estado (aceptado/rechazado) y hash de datos.
- `tests/test_param_versions.py` guarda el SHA-256 de cada versión publicada: editar una rompe el gate.
  Al añadir una versión, registra su hash en ese test en el mismo PR.
- Cada `RiskDecision` lleva `config_version` y `config_sha256`; el hash ignora el fin de línea
  (`.gitattributes` fija LF) para que sea igual en todos los equipos.
- Parámetros de agentes (`eim/agents/<id>/params.py`): modelos pydantic con valores por defecto
  versionados con el código; un cambio que altere la salida sube la `version` del agente.

### Biblioteca de trading (T52)
Dependencias opcionales: `python -m pip install -e ".[library]"` y, para PDF escaneados, Tesseract (`winget install UB-Mannheim.TesseractOCR`, pide permisos de administrador; idioma `eng` incluido).
```bash
set EIM_LIBRARY_DIR=C:\ruta\a\Books        # PowerShell: $env:EIM_LIBRARY_DIR = '...'
python -m eim.library ingest               # cataloga; reutiliza lo ya extraído si la huella no cambió (OCR ~3 s/pág., con caché)
python -m eim.library list                 # catálogo: páginas con texto, OCR, motivo si falta texto
python -m eim.library search "hanging man confirmation" --book nison_candles
python -m eim.library show nison_candles 49
python -m eim.library cards                # resumen de las fichas versionadas (guardas)
python -m eim.library verify               # cada cita contra el texto local (términos y citas textuales)
python -m eim.library mark revisada_usuario <id|libro> ...   # tras la revisión del usuario
```
Los libros y el índice no se versionan ni se suben a ningún servicio; el texto de un libro es dato, nunca instrucción.

### Seguimiento de sugerencias y ciclo de mejora (T51)
- **Registro inmutable** (`eim/data/suggestion_store.py`, `data/paper.duckdb`): cada oportunidad que
  publica `GET /v2/setups` se guarda la primera vez (id = id de la idea; repetirla no la cambia) con
  precios, `estrategia@marco@versión`, veredicto/evidencia y hora; los intervalos sin sugerencia
  (`sin_validadas`, `sin_senal`, `datos_viejos`) se guardan con su motivo. Lo registra el bróker en
  cada ciclo (~1 min), aunque nadie mire el panel; un hueco > 10 min sin observar abre otro intervalo.
- **Resolución**: `eim/suggestions/tracking.py` vuelve a simular lo publicado con `paper/engine` sobre
  las velas de 15 m que abren DESPUÉS de publicar (sin anticipación; la orden límite conserva su
  vencimiento): llenada o no, R neto de costos, MFE/MAE y `Outcome.cause`. Nada pasa a «ejecutada».
- **Señal contra resultado** (`GET /v2/setups/history`): por versión, R realizado frente al IC95 % de
  su evidencia fuera de muestra (dentro / debajo / encima; sin opinar con < 5 cerradas) y tasa de
  llenado real frente a la simulada por el bróker.
- **Degradación**: si el R medio de las últimas 20 publicadas cerradas queda bajo el límite inferior
  del IC95 % de su evidencia, la versión pasa a «en revisión» y el publicador la excluye. Sale solo
  con un veredicto NUEVO de T49 que la valide y que ya absorba la caída (la media ya no queda por
  debajo); una versión nueva tiene otro id y arranca EN OBSERVACIÓN.
- **Ciclo de mejora** (lo ejecuta una persona o una tarea; nada se ajusta solo): 1) *diagnóstico*:
  causas de pérdida (`Outcome.cause`), contextos del `Learner` (pausas estrategia@marco × régimen ×
  lado), `paper/insights` y el criterio de T49 que falla (`most_failed` de `/v2/validation`) o la
  degradación de arriba; 2) *versión nueva*: cambiar reglas/parámetros cambia la huella y registra un
  intento en `eim/validation/lineage.json` con su **ventana de ajuste** (los datos usados para
  ajustar); 3) *observación*: arranca EN OBSERVACIÓN y solo cuenta la evidencia fuera de esa ventana
  (y de las de sus ancestros): ninguna versión se valida con los datos con que se ajustó; 4) se
  publica solo si T49 la valida, y el seguimiento vuelve a medirla.

### Instantáneas de datos y `repetir` (T124)
Un número que no se puede volver a producir no es un número. El almacén se rellena y se corrige
con el tiempo, así que cada resultado dice **qué datos vio**, además de con qué código y con qué
parámetros:
- **Instantánea** (`eim/data/snapshots.py`, tabla `data_snapshots` de `data/snapshots/snapshots.duckdb`):
  una serie (velas de un símbolo y marco, más su funding) cortada en `[inicio, fin)`. Solo entran
  velas cerradas a `fin`. Guarda el rango, el nº de velas y huecos, el hash del contenido, el
  momento de creación, el proveedor y la versión del formato. El id sale del contenido y nunca se
  reescribe: con otros datos sale otra instantánea. **Congelada** = con copia Parquet en
  `data/snapshots/frozen/<id>/`. **Ligera** = solo identidad y hash; la usa la puntuación de bots,
  que se recalcula cada 4 h.
- **Resultados** (`eim/data/results.py`, tablas `data_results` y `repro_checks`): la puerta de edge
  (cada ventana), `eim.backtest.cli`, `eim.calibration.cli` y la puntuación de bots registran sus
  cifras con los ids de sus instantáneas, la huella del código (commit y hash de `eim/*.py`) y los
  parámetros. Los tres primeros **calculan desde la instantánea** (`SnapshotView`), no desde el
  almacén, y el id va al JSON y al informe. Un resultado sin instantánea dice **«No reproducible
  (T124)»** en el informe y en la interfaz: en la tabla del escuadrón y en «Backtest / VRM», que
  calcula a la carta sobre el almacén vivo.
- **Revisiones** (`eim/data/revisions.py`): si una escritura cambia una vela o un funding ya
  guardados, queda anotado en `data/snapshots/revisions/AAAAMMDD.<pid>.jsonl` (antes, después, momento,
  fuente). Rellenar un hueco o volver a escribir lo mismo no cuenta como revisión. Anotar nunca
  tumba la escritura.
- **Freno al lookahead**: `SnapshotView` corta en su fecha. Pedir una vela posterior lanza
  `LookaheadError` y pedir otra serie o algo anterior al inicio lanza `SnapshotScopeError`, así que
  nunca se devuelve en silencio menos de lo pedido.

```bash
python -m eim.repro resultados                       # qué hay registrado y su último repetir
python -m eim.repro repetir rs_65d0ef5e25bb262a      # 0 = se repite, 1 = no (con causa), 2 = error
python -m eim.repro revisiones --dias 30             # velas cambiadas e instantáneas/resultados afectados
python -m eim.repro instantanea --symbol BTCUSDT --tf 1h --desde 2026-01-01   # fijar una serie a mano
python -m eim.repro adoptar-t27 --store backups/t131_banco --asset BTCUSDT    # ventanas de T27, a posteriori
```
`repetir` recalcula con los datos de la instantánea, los parámetros grabados y el código de hoy, y
separa las causas cambiando un factor cada vez:
- **código**: esa base ya no da la cifra;
- **datos**: la copia congelada ya no da su hash, o el almacén ya no tiene lo que fijó la instantánea
  y con lo que tiene la cifra cambia. Las velas distintas se cuentan como anotadas o sin anotar
  (estas últimas, cambios hechos por fuera del sistema);
- **parámetros**: los vigentes no son los grabados y con ellos la cifra cambia.

Si el almacén cambió pero la cifra no, se avisa y no cuenta como causa. La calibración y la
puntuación de bots solo comprueban los datos, sin recalcular: la calibración tarda horas y la
puntuación lee bases que la API tiene abiertas (BACKLOG T124). Recalcular una ventana de T27 tarda
unos 90 s: lánzalo por la cola de trabajos.

**Por qué no ArcticDB.** La idea (versiones inmutables de series, instantáneas con nombre) viene de
ArcticDB (Man Group), pero **no se instala bajo ninguna forma**: está bajo Business Source License
1.1, y su documentación limita el uso gratuito a fines no comerciales, personales o académicos. El
EIM es un sistema de trading, así que esto se hizo sobre DuckDB + Parquet, que ya estaban. No
volver a proponerlo salvo que cambie su licencia.

**Límites.** `data/snapshots/` todavía no entra en la copia diaria: reorganizar las copias es T115
(BACKLOG T124). Una instantánea ligera detecta el cambio pero no reconstruye la cifra vieja. En la
API la huella del código es la del arranque: el código que de verdad corre, aunque luego se traiga
`main`.

## 5. Dependencias: política de actualización
- **Rangos** en `pyproject.toml` / `package.json`; **versiones probadas** en `requirements-lock.txt` y
  `eim/web/package-lock.json`.
- **Cada mes** (y antes de pasar a testnet o de cualquier cambio de modo):
  ```bash
  python -m pip_audit                    # vulnerabilidades Python (paquete [dev])
  cd eim/web && npm audit                # vulnerabilidades del frontend
  ```
- **Actualizar** en una rama propia (`deps-AAAA-MM`): `python -m pip install -U <paquete>` /
  `npm update`, pasar el gate + `npm run build`, regenerar `requirements-lock.txt`
  (`python -m pip freeze --exclude-editable`, conservando la cabecera) y abrir PR. Nunca mezclar con
  funcionalidad.
- **Mayores** (p. ej. pandas 3→4, Vite 6→7): PR dedicado con nota de cambios; Vite 7+ exige Node ≥ 20.19.
- Vulnerabilidad **alta** en algo que corre en la API → se corrige antes de seguir operando.
- Código de terceros nuevo: licencia y seguridad antes de copiar (ver `PLAN/notas/T04_auditoria.md`).

## 6. Rutina
- **Diario:** pestaña «Operación» de la UI (estado, alertas activas, kill-switch, reconciliación).
- **Acceso directo:** `powershell -ExecutionPolicy Bypass -File v2\scripts\crear_acceso_escritorio.ps1` crea «EIM» en el escritorio con el icono de la esfera (`-Quitar` lo borra). Doble clic → `abrir_interfaz.ps1`: asegura **todo el servicio** con `servicio_continuo.ps1 -ConWeb` (vigilante, API en papel, bróker simulado, líderes, interfaz, hoja de ruta en `http://127.0.0.1:8765/roadmap.html` y modo «equipo despierto»; no duplica lo que ya corre), espera a que respondan y abre la interfaz `http://127.0.0.1:5173` y la hoja de ruta. Apunta a la carpeta donde se creó: si se mueve el repositorio, volver a crearlo.
- **Equipo despierto:** `scripts/mantener_despierto.ps1` (lo lanza `servicio_continuo.ps1`, oculto) pide a Windows con `SetThreadExecutionState` no suspender por **inactividad** mientras la API escuche en el puerto 8000; no cambia el plan de energía y se libera sola si la API lleva > 3 min caída o al cerrar el proceso. La pantalla sí puede apagarse. **No impide** la suspensión manual ni el cierre de la tapa del portátil (ajustar «Al cerrar la tapa: no hacer nada» en Opciones de energía). Para quitarlo: terminar el proceso `powershell` que ejecuta `mantener_despierto.ps1`.
- **Servicio continuo (T48):** `powershell -ExecutionPolicy Bypass -File v2\scripts\servicio_continuo.ps1 -ConWeb` deja corriendo el vigilante (API + operación en papel + bróker simulado en 15 m, 1 h y 4 h), el servicio de líderes (abajo) y la interfaz; no duplica si ya están arriba. `v2\scripts\instalar_inicio_automatico.ps1` lo registra al iniciar sesión (`-Quitar` lo borra); la tarea llama al script por su ruta, así que lo añadido al script entra sin reinstalarla. El equipo no debe suspenderse. Latido del bróker: `data/paper/heartbeat.json`; la vista muestra «Servicio en vivo · último ciclo hace …». Salidas de consola: `data/operation/logs/` (`vigilante.*`, `lideres.*`, `web.*`). Cada línea de `vigilante.*` y del stderr de los demás servicios bajo vigilante (líderes y captura) lleva su hora UTC, y al relanzar el vigilante de la API se conservan los 10 últimos `vigilante.*` con la fecha de su última escritura (T140). El vigilante también reinicia la API si pierde el puerto: `RUNBOOK.md` §16.
- **Repetir tras una pausa (T116):** con `--retry-paused N`, un trabajo que falla después de haber estado pausado se repite hasta N veces. En la pausa el trabajo queda congelado y no lo sabe, así que un plazo de reloj puede caducar (2026-11-02: una prueba con 120 s de plazo y 185 s congelada). El gate se lanza con `--retry-paused 1`.
- **Cola de trabajos pesados (T127):** `python -m eim.operation.jobs submit --name <nombre> [--tier batch|service] [--min-ram-mb N] [--retry-paused N] -- <orden>` encola, espera a que termine y devuelve su código de salida (`list` muestra los recientes y `cancel <id>` cancela). Un solo ejecutor (cerrojo `data/jobs/runner.lock`) corre un trabajo a la vez; si no hay ninguno, lo hace quien encola, y si el ejecutor muere toma el relevo el siguiente que espera. Se admite con RAM libre ≥ 2 GB, CPU del equipo ≤ 80 % y la captura HFT sin presión. Se **pausa con todo su árbol** si la captura sufre (cola > 1 000 mensajes, escritura atrasada > 200, huecos o descartes nuevos, reinicio) o la RAM libre baja de 1 GB, y se reanuda tras 90 s sin presión (a los 15 min, aunque siga: no viene de él). Va dentro de un objeto de Windows: si el ejecutor muere, el trabajo muere con él, y nunca queda congelado. **Si la RAM que falta la retiene el propio trabajo (T149)**, pausarlo no sirve: se mata y vuelve al final de la cola pidiendo su pico × 1,25 + 1 GB (como mucho 2 h de espera; tras 2 reencolados sin crecer, o si no cabe en el equipo, queda fallido diciendo qué `--min-ram-mb` pedir). Nunca más de 2 pausas por memoria seguidas sin salida. El registro anota la memoria del trabajo en cada pausa, su pico al terminar y `pidio_menos_ram` si usó más de 1,5 × lo pedido. `usage incidents` y el aviso temprano nombran el trabajo de la cola, no el `submit` que lo aloja. Cada paso queda en `data/jobs/log/AAAA-MM-DD.jsonl` y la salida en `data/jobs/out/<id>.log`; se conservan 14 días.
- **Registro de consumo (T127):** el script lanza `python -m eim.operation.usage run --data-dir <datos>` (cerrojo `data/usage/usage.lock`, nivel `service`). Cada 30 s escribe en `data/usage/AAAA-MM-DD.jsonl` la CPU de cada parte del EIM (en % del equipo entero: con 4 núcleos, un hilo lleno es el 25 %), su RAM privada y su prioridad; los 5 programas ajenos que más CPU gastan y los 3 de más RAM; la CPU y la RAM libre del equipo, y la cola de la captura HFT. Lee la lista de procesos del sistema sin abrir ninguno, así que también mide los de la sesión 0; el papel de cada proceso sale de su archivo de observabilidad (`obs/spool/<papel>.<día>.<pid>.jsonl`) o del puerto que escucha. Comprime los días cerrados y conserva 30. Una muestra a mano: `python -m eim.operation.usage run --once`. Resumen por día, cruzado con las horas incompletas de la captura HFT (cuáles coincidieron con el equipo saturado y cuáles no tienen registro): `python -m eim.operation.usage summary --days 7`; también va al informe semanal, en la sección «Consumo del equipo».
- **Quién carga el equipo y aviso temprano (T141):** de cada árbol de `python.exe`, `blender.exe` o `node.exe` ajeno al EIM que pasa del 5 % de CPU o de 300 MB de RAM, el registro guarda su línea de órdenes, recortada y sin secretos, y su carpeta de trabajo, además de los fallos de página de cada parte del EIM y la edad del latido de la API. **Todo se queda en `data/usage`.** Cada ciclo lento, reinicio y arranque lento, cruzado con todo eso: `python -m eim.operation.usage incidents --days 7 [--slow 120]`. El mismo servicio avisa (notificación de Windows y registro de operación) si, durante 3 muestras seguidas, la memoria comprometida llega a 36 GB, la API baja de 200 MB de RAM, la CPU del equipo está al 95 % con la API por debajo del 0,3 %, o su latido lleva 300 s parado. Termina con 10 muestras limpias. Lo que se lanza desde las sesiones de Claude va por la cola y con 2 procesos como máximo (`~/.claude/CLAUDE.md`, decisión del usuario). Los umbrales y las opciones de prioridad, en `PLAN/notas/T141_carga_ajena.md`.
- **Prioridades y arranque al encender (T126):** el script fija `EIM_PRIORITY=on` y cada servicio toma su nivel al arrancar (`eim/operation/priority.py`): recolectores en vivo por encima de lo normal (ABOVE_NORMAL); API, líderes y vigilantes por debajo de los programas del usuario (BELOW_NORMAL, como antes); su mantenimiento, Ollama y los trabajos pesados al fondo (IDLE). Los recolectores suben además su prioridad de memoria y de E/S a las normales (T141): lo que nace de una tarea programada hereda memoria 2 y E/S baja, y es la memoria lo que ha dañado a la captura. Para verlas: `python -m eim.operation.priority_memory show`; para subir a los recolectores en marcha, sin reiniciarlos: `... apply`. La API y los demás servicios siguen en 2 y baja, a propósito: subirlos es otra decisión (◆C). Un trabajo pesado a mano (gate, importación, prueba de un modelo) se lanza por debajo de los servicios con `python -m eim.operation.priority run batch -- <orden>`. Con ese mismo nivel corre el **colector del DVOL de Deribit** (T165), que no es un servicio sino una tarea horaria: `v2\scripts\dvol_colector.ps1 -Instalar` la registra (minuto 10 de cada hora, `-Quitar` la borra) y cada pasada es incremental y deja una línea en `data\operation\logs\dvol.log`. Solo BTC, que es el alcance del trabajo; otra moneda se pide a mano con `-Monedas`. Instalarla desde la carpeta principal, no desde un worktree. Para que todo arranque tras un corte o un reinicio sin esperar a que alguien inicie sesión: `v2\scripts\instalar_inicio_automatico.ps1 -AlEncender` desde una consola de administrador (tarea S4U, 2 min tras encender; sin unidades de red ni credenciales: la copia externa sigue en su tarea). Las dos tareas pueden coincidir: la segunda espera a la primera y solo completa lo que falte (cada servicio tiene un cerrojo de instancia que el lanzador consulta, visible desde cualquier sesión). Los servicios que lanzó la tarea al encender corren en la sesión 0. Desde T127, cada servicio Python da permiso a su usuario al arrancar (`eim/operation/proc_access.py`), así que `scripts\detener_servicio.ps1` (o «Parar servicio» del icono, que lo usa) los para sin administrador desde cualquier sesión: primero los vigilantes, después los servicios. Con `-Todo` para también la captura, el registro de consumo y la hoja de ruta. Lo que no se deja ver lo lista al final: servicios arrancados antes de T127, Vite y la hoja de ruta. Para eso hace falta un PowerShell de administrador o reiniciar. Aceptación de T78: `python -m eim.data.collectors.hft_ops --root data --window` (solo lectura, T147; `--streak` da la racha de T126, ya informativa). Antes de un despliegue que reinicie la captura, declarar sus horas con `--maintenance DESDE HASTA --nota "…"`: no cuentan ni cortan la ventana (`docs/RUNBOOK.md` §17).
- **Microestructura del agente (T128):** sale de la captura HFT. Con su libro verificado, `hft_ws` guarda cada segundo una foto top-10 en `data/micro/top` (el formato de siempre) y escribe `data/micro/heartbeat.json` para el panel (`micro_feed.py`). `eim/data/micro.py` lee los trades y los huecos de `data/micro_hft/`, o de `data/micro/` en los tramos sin captura HFT. Los huecos que rompen el libro o pierden trades dejan incompletas todas las velas que tocan; los silencios, no. El recolector T23 (`binance_ws` + `supervise`) ya no se lanza para BTCUSDT, porque abría dos conexiones más y llevaba otro libro, con un ~11 % de CPU. `data/micro/{trades,depth,gaps}` dejan de crecer.
- **Menos ruido (T128):**
  - **Ollama:** el script solo lanza Ollama (`EIM_OLLAMA_EXE`, por defecto `E:\Ollama\ollama.exe`) si la ruta existe en su sesión. Si la variable está puesta y la ruta no existe, la API avisa «LLM local no disponible» en sus alertas y Contexto dice por qué no tiene datos. La tarea al encender (sesión 0) no ve las unidades de red: la variable debe apuntar a una copia local.
  - **Vigilancia con cliente:** «Precio en vivo» (`data.live_ticks`) y «Difusor de la API» (`api.hub`) solo emiten con la interfaz abierta, así que no avisan «sin latido» hasta que alguien se conecta en ese arranque.
  - **Interfaz:** `-ConWeb` sigue lanzando Vite en modo desarrollo. Medido el 2026-11-02, gasta 0,001 % de CPU y ~170 MB de memoria reservada, así que servirla compilada no compensa.
- **Captura HFT (T78):** el mismo script lanza `python -m eim.data.collectors.hft_supervise BTCUSDT --root <datos>` (vigilante de T104: cerrojo `data/micro_hft/supervisor.lock`, latido `data/micro_hft/heartbeat.json`, reinicio con espera creciente, aviso si se apaga, se queda sin flujo o el disco baja de 5 GB). Cada 10 min audita las horas cerradas (QC), compacta las de más de 2 h, poda los crudos de más de 45 días (`--keep-days`) y reescribe el resumen; registro en `data/micro_hft/logs/` (`mantenimiento_hft`, `qc_hft_aviso`). El informe semanal trae la sección «Captura HFT (calidad de datos)». Para detenerla: matar el vigilante y luego `hft_ws` (el vigilante solo deja la captura huérfana). T80/T84 piden 14–30 días contiguos: el resumen trae la mejor ventana de T78 (`t78_window`, T147) y, como lectura informativa, la racha contigua más larga (`t78_streak`, T126).
- **Base de líderes (T128):** al arrancar, el vigilante de líderes (`supervise`) compacta `leaders.duckdb` si más del 30 % del archivo está libre: DuckDB reutiliza los bloques libres pero nunca encoge el archivo (`eim/data/duck_compact.py`; ~76 s para 1,3 GB, en lote). Copia, comprueba las filas tabla a tabla y solo entonces cambia el archivo; si falla, arranca con la base de siempre. El vigilante sigue también las ejecuciones de órdenes TWAP (`userTwapSliceFills` por WS y `userTwapSliceFillsByTime` por REST), que `userFills` no trae.
  - **Retención de los rechazados:** de los líderes `rejected` (el grupo de control de T41) se conservan 7 días de detalle crudo (`leader_fills` y `leader_follow`). Lo anterior se archiva ya plegado, moneda a moneda (`eim/data/leader_prune.py`). El corte es el último instante ≤ ahora − 7 d en que la posición quedó plana y sin cotizaciones pendientes. Se guardan los viajes cerrados con su seguidor, las latencias en vivo (histograma de milisegundos), las tomadoras y el número de ejecuciones (`leader_archive`, `leader_archive_trips`: columnas y JSON con versión, sin pickle). El archivo se escribe y el detalle se borra en la misma transacción. Al final de cada líder se borra también la procedencia de la unión T61 de lo que ya no está (`share_origin`, la tabla más grande de la base: si no, quedaría huérfana para siempre).
  - **Mismas cifras:** la evaluación arranca del archivo y aplica solo lo posterior. Da los mismos veredictos, razones y cifras que con todo el historial; el funding se reparte de nuevo desde `leader_funding`. Medido el 2026-11-02 sobre una copia de la copia de la noche (17 líderes, 16 rechazados), con 7 días y con un corte artificial de 1 día: tablero idéntico bit a bit, antes y después de compactar. Con 7 días se archivan 590 617 ejecuciones (571 649 del líder de alta frecuencia), 510 237 cotizaciones y 1,09 M claves de `share_origin`, en 15 936 viajes (4 MB). La base compactada pasa de 1 343 a 1 161 MB (937 MB con 1 día); durante la poda el archivo crece hasta ~1,8 GB con bloques libres que el compactado devuelve. La poda tarda 139 s y el compactado 65 s. Lo que sigue creciendo sin poda (fotos de posiciones, reconciliaciones, huecos, bitácora de la copia) son unos pocos MB al día, frente a ~110 MB. Unas dos terceras partes del archivo son índices de claves primarias, la mayor `share_origin`.
  - **Qué no se toca:** aprobados y `watch`, funding, fotos de posiciones (dan los días observados), reconciliaciones y huecos. Si un rechazado vuelve a `watch` o se aprueba, su archivo se queda y deja de podarse.
  - **Cuándo corre:** el servicio poda una vez al día, la primera 30 min después de arrancar, en lotes de 200 000 ejecuciones por transacción para no frenar la captura. El vigilante poda también antes del compactado, así el primer arranque ya devuelve el espacio. A mano, con el servicio apagado: `python -m eim.leaders --root data prune [--days 7]` poda y compacta. Lo borrado deja bloques libres que DuckDB reutiliza: la base deja de crecer y encoge en el siguiente arranque.
  - **Quién deja de ver lo viejo:** `history` y `gather` (la referencia de las pruebas) solo ven lo no podado. La reproducción `copy-sim` (T42) de un rechazado empieza en la primera foto posterior a su último corte y lo dice en `warnings`. `report` (última hora), la copia simulada en vivo y la puesta al día tras reiniciar leen solo lo reciente.
  - **Límites:** una ejecución anterior al corte que reaparezca (unión T61, que hoy está apagada) se ignora y la poda siguiente la borra. Lo archivado queda con los parámetros de entonces: cambiar `avg_down_tol`, `live_max_latency_ms`, `quote_timeout_ms`, `follower_taker_fee` o `allmids_half_spread` no lo rehace, y el registro lo avisa. El detalle podado sigue en las copias diarias (14) y en la copia externa.
- **Servicio de líderes (T41):** el mismo script lanza `python -m eim.leaders --root <datos> supervise`, en un proceso propio porque es el único que puede abrir `data/leaders.duckdb` (DuckDB admite un solo proceso). El vigilante lanza `run` (captura de Hyperliquid + tablero cada 5 min en `data/leaders/`) y lo relanza si termina o si su latido (`data/leaders/heartbeat.json`, cada ≤ 30 s mientras terminan tareas) no avanza en 15 min, con espera creciente (10 s… máx. 5 min). Reinicios en `data/leaders/logs/op-AAAA-MM-DD.jsonl` (`proceso_reiniciado`) y aviso de Windows «Líderes: servicio reiniciado». No se lanza otro si ya corre `supervise` o un `run` a mano (el script lo detecta por la línea de órdenes y el cerrojo `data/leaders/supervisor.lock` lo impide de todos modos). Sale sin vigilar, y el script lo dice («Servicio de líderes NO lanzado: …»), si no hay líderes en seguimiento o si la base está en uso.
  - **Para `watch`/`unwatch`/`list`/`score`** (necesitan la base): detener el servicio, ejecutar la orden y volver a lanzar el script. Detener (vigilante y captura):
    `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ? CommandLine -match 'eim\.leaders' | % { Stop-Process -Id $_.ProcessId -Force }`.
    Matar el vigilante solo deja la captura huérfana (sin relanzamiento): el script ya no la duplica, pero tampoco la vigila; detén ambos.
  - **Si se apaga** (equipo suspendido, proceso detenido): a los 10 min el tablero queda viejo; la pestaña «Líderes» lo marca y `build_snapshot`/la API dejan sin líderes al agente `smart_money` → `no_data`. El tiempo sin captura no cuenta como días adelante (cada salto entre fotos cuenta como mucho 15 min): la aprobación (≥ 7 d y ≥ 30 operaciones) se retrasa lo que dure el apagado. Las ejecuciones de ese periodo no tienen precio del seguidor (solo se graba en vivo).
  - **Memoria (tope < 2 GB):** la evaluación es incremental (`eim/data/leader_fold_io.py`): al arrancar lee el historial de cada líder una vez, moneda a moneda y en tandas, y después solo lo nuevo; no guarda ejecuciones ni cotizaciones, solo un viaje sin patas por operación y las latencias (8 B c/u). `leaders.duckdb` va con `EIM_DUCKDB_MEMORY` (1 GB por defecto) y 2 hilos. Medido 2026-10-29 sobre una copia (2,4 M ejecuciones, 1,9 M cotizaciones, 7 líderes; equipo con 0,6 GB libres): primera evaluación 52 s con pico de 0,75 GB, después ≤ 6 s cada una con 0,65 GB estables; en 15 min con escrituras al triple del ritmo real y rehaciendo monedas en casi cada vuelta, pico de 0,93 GB, vuelta más larga 44 s y escrituras de la captura frenadas ≤ 2 s. Antes releía todo cada 5 min (≈ 4 KB por ejecución y 3 KB por cotización en Python): 10–13,5 GB y evaluaciones de más de 15 min, que el vigilante cortaba por «latido detenido».
  - **Tras un apagado largo:** al volver, cada líder pide sus ejecuciones desde la última guardada, como mucho de las últimas 24 h y con tope de 10 000 (5 páginas; el exchange tampoco sirve más). En billeteras de alta frecuencia quedan huecos: esos viajes salen parciales y fuera de las métricas (BACKLOG T41 (7)). La primera vuelta tarda más (≈ 1 min por cada 8 000 ejecuciones a rellenar, por el presupuesto REST).
- **Copia simulada (T42):** el mismo `run` del servicio de líderes lleva una subcuenta virtual por líder (modo SIMULADO, 10 000 USDC, sin órdenes reales ni de testnet). `EIM_COPY_SIM` = `tracked` (por defecto: todos los capturados, como medición mientras no haya aprobados), `approved` (solo abre con aprobados) u `off`. Estado en `leaders.duckdb` (`copy_state`, bitácora `copy_journal`) y resumen cada 10 s en `data/leaders/copy_sim.json` (pestaña «Líderes» → «Copia simulada», `GET /v2/leaders/copy`). Desde `v2/`:
  - `python -m eim.leaders copy-status` — capital, resultado, órdenes y pausas de cada subcuenta.
  - `python -m eim.leaders copy-sim` — reproduce la copia sobre todo el historial capturado (mismo motor) y escribe `reports/copytrading_sim.md` (+ bitácora en `data/copytrading/replay_journal.jsonl`). Con el servicio en marcha le pide una instantánea de la base (`data/leaders/snapshot-<hora>.duckdb`, un archivo por pedido; se copia en una transacción aparte, sin frenar la captura); pide `meta` y velas de 1 min de Hyperliquid (caché en `data/cache/hl_candles/`; el exchange solo sirve ≈ 3,5 días de velas de 1 min). `--offline` usa solo la caché.
  - `python -m eim.leaders copy-resume 0x…` (o `--all`) — reanuda a mano una subcuenta en pausa (ver `docs/RUNBOOK.md` §11).
- **Bróker simulado (T47):** botón «Bróker simulado» arriba a la derecha. Historial inicial o ampliación:
  `python -m eim.paper backtest --symbol BTCUSDT --days 60 [--tf 15m,1h,4h]` (si la API está en marcha le delega el trabajo;
  ≈1,5 s por vela y por proceso, en paralelo) o el botón «Ejecutar» de la vista. Resumen por consola:
  `python -m eim.paper resumen`. Para empezar de cero: detener la API y borrar `data/paper.duckdb`.
  - **Cómo leer las cifras de la cuenta (T107).** Hay dos capitales y uno solo manda:
    «Saldo realizado (balance)» = solo lo cerrado; **«Capital (equity)» = saldo + PnL no realizado**, y
    la rentabilidad y el drawdown máximo se miden SIEMPRE sobre la curva de equity con el capital
    inicial (10 000 USDT) como base. El panel dice la base y la ventana de cada una.
  - **Margen aislado:** ninguna posición pierde más que su margen. Si el precio atraviesa el precio
    de liquidación (un hueco que deja el stop atrás), la posición se cierra como **«Liquidación»**:
    se pierde el margen entero, se registra con su categoría propia en la bitácora y nunca se
    presenta como un cierre ordinario de la estrategia. Por eso el capital no puede quedar negativo
    ni el drawdown pasar del 100 % (si alguna vez lo hace, es un error de contabilidad).
  - **Cuenta agotada:** con el capital realizado por debajo del 1 % del inicial (`min_equity_frac`)
    el perfil queda «agotada»: deja de abrir, mantiene lo abierto hasta su cierre y lo dice en la
    tarjeta y en el resumen. **No hay recargas de capital**, ni silenciosas ni automáticas.
  - **Recuento de operaciones:** no tiene ventana. La vista se recalcula desde todos los contextos
    guardados del símbolo, así que el número solo crece y, si la experiencia compartida (T61) importó
    contextos de otras máquinas, también los cuenta (el almacén no los distingue). El único registro
    inmutable es el libro fijo (`/v2/paper/ledger`), que guarda solo cierres en vivo.
  - **Instantánea y alcance (T118):** cada cálculo de la vista guarda la foto de lo que muestra el
    panel (tabla `paper_view_snapshot` de `paper.duckdb`, solo adición) y la franja de arriba del
    panel enseña su identificador. Para auditar una cifra vista antes: `GET /v2/paper/snapshot/<id>`
    devuelve exactamente esas cifras, con el almacén y las versiones de entonces, e `intact` dice si
    la fila sigue sin alterar (`GET /v2/paper/snapshots?symbol=…` las lista). Las instantáneas son de
    la máquina que las calculó: para auditar una captura de otro colaborador, pedírsela a él. La
    misma franja dice el tramo que ve la vista, su techo (cierres posibles por perfil con este
    almacén) y lo que deja fuera: operaciones del libro fijo que ya no reproduce o reproduce con
    otro PnL, e instantáneas anteriores que contaban más. El Historial avisa cuando lista solo las
    más recientes.
- **Semanal (lunes UTC):** leer `reports/operation/semana_AAAA-Www.md` (se genera solo).
- **Mensual:** auditoría de dependencias (§5) y `python -m eim.data.backup verify` sobre una copia
  antigua (prueba de restauración en una carpeta temporal: `restore <copia> --data-dir <tmp>`).

## 7. Motores locales (T62)
Auditoría y lista aprobada propuesta: `PLAN/notas/T62_auditoria.md` (◆ el usuario decide qué entra);
reglas de seguridad: `docs/SEGURIDAD.md` § «Motores de IA locales». Nada de esto lo exige el gate ni
la API: la integración en EIM es T63. **Estado (2026-10-31):** instalado en `juanpablo-cpu`
(`C:\eim-localai`, lista aprobada por el usuario); su Ollama solo corrió en el puerto 11435 durante
el banco y EIM no lo usa mientras no se defina `EIM_OLLAMA_EXE` (T128 quitó la que apuntaba a la
unidad de red `Z:`; activarlo tras T78, midiendo la RAM). Falta el equipo de referencia.

**Dónde.** Todo en `EIM_LOCALAI_DIR` (disco local con ≥ 20 GB libres, fuera del repo, nunca en
una unidad de red):
```
%EIM_LOCALAI_DIR%\ollama\          ollama-windows-amd64.zip descomprimido (sin la app de bandeja)
%EIM_LOCALAI_DIR%\ollama\models\   modelos (OLLAMA_MODELS)
%EIM_LOCALAI_DIR%\llama.cpp\       llama-server.exe (opcional, plan B)
%EIM_LOCALAI_DIR%\models\faster-whisper\<modelo>\   pesos de faster-whisper (revisión fijada)
%EIM_LOCALAI_DIR%\tesseract\       Tesseract extraído del instalador, con tessdata\ eng/spa/osd
%EIM_LOCALAI_DIR%\venv\            entorno aparte con los extras [video,localai,library]
%EIM_LOCALAI_DIR%\downloads\       un directorio por descarga, con su SHA-256 comprobado
```

**Instalación mínima** (una vez aprobada la lista; versiones fijadas en la auditoría):
1. **Ollama v0.40.11** (`675150d6`): bajar `ollama-windows-amd64.zip` (1,59 GB) de la release
   oficial de GitHub, comprobar su SHA-256 (`bda4a493…eda12a`) con el `sha256sum.txt` de la misma
   release y descomprimir en `%EIM_LOCALAI_DIR%\ollama` (`ollama.exe` firmado por «Ollama Inc.»).
   Variables de usuario: `EIM_OLLAMA_EXE=%EIM_LOCALAI_DIR%\ollama\ollama.exe`,
   `OLLAMA_MODELS=%EIM_LOCALAI_DIR%\ollama\models`, `OLLAMA_HOST=127.0.0.1:11434`,
   **`OLLAMA_NO_CLOUD=1`**, `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_NOPRUNE=1`. Arranque: solo
   `ollama.exe serve` (lo hace `servicio_continuo.ps1`); su registro debe decir
   «Ollama cloud disabled: true».
2. **Modelos** (`ollama pull`, y comprobar el digest con `ollama list` contra la tabla de la
   auditoría): `qwen3:4b-instruct` (`0edcdef34593`), `qwen3-vl:2b-instruct-q4_K_M`
   (`afc393e3572c`) y, para T71, `qwen3-embedding:0.6b` (`ac6da0dfba84`). Con
   `OLLAMA_NO_CLOUD=1` el `pull` del registro sigue funcionando.
3. **Entorno aparte:** `python -m venv %EIM_LOCALAI_DIR%\venv` (Python 3.12) y, desde `v2/`,
   `%EIM_LOCALAI_DIR%\venv\Scripts\python -m pip install -e ".[video,localai,library]" pip-audit`
   (`library` trae Pillow y pytesseract, que usa el banco; ≈ 0,85 GB); después
   `python -m pip_audit` en ese entorno (2026-10-31: sin vulnerabilidades conocidas).
4. **Pesos de faster-whisper** (sin descarga en ejecución), cada uno en su carpeta:
   `snapshot_download(<repo>, revision=<sha>, allow_patterns=["config.json",
   "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"],
   local_dir=r"%EIM_LOCALAI_DIR%\models\faster-whisper\<modelo>")` con `small` =
   `Systran/faster-whisper-small@536b0662…` (0,46 GB) y `large-v3-turbo` =
   `dropbox-dash/faster-whisper-large-v3-turbo@0a363e91…` (1,6 GB). El banco usa esa carpeta y
   no el alias de faster-whisper (alerta 11) y anota la revisión.
5. **llama.cpp b12018** (opcional, plan B): `llama-b12018-bin-win-cpu-x64.zip` (24,6 MB, SHA-256
   `205755a9…acb9a6` según el *digest* de la release) en `%EIM_LOCALAI_DIR%\llama.cpp`; sin firma.
6. **Tesseract 5.5.3** (opcional, ya lo usa la biblioteca): `tesseract-ocr-w64-setup-5.5.3.20260724.exe`
   de la release oficial (SHA-256 `bee9e343…0ae4`), **extraído con 7-Zip** en
   `%EIM_LOCALAI_DIR%\tesseract` sin ejecutar el instalador (no pide administrador; su firma de
   la Universität Mannheim sale «UnknownError» en este Windows, por eso cuenta el SHA-256). El
   instalador no trae idiomas: `eng`, `spa` y `osd` de `tessdata_best@e12c65a9` en `tessdata\`,
   comprobando con `git hash-object` el SHA del blob que da la API de GitHub.
   `EIM_TESSERACT=%EIM_LOCALAI_DIR%\tesseract\tesseract.exe`.

**Comando de verificación** (mide en el equipo y escribe `reports/localai/bench_<equipo>.md`):
```bash
%EIM_LOCALAI_DIR%\venv\Scripts\python scripts/localai_bench.py --sections system,llm,engines,gpu --llm qwen3:4b-instruct
%EIM_LOCALAI_DIR%\venv\Scripts\python scripts/localai_bench.py --sections scenes,ocr,vlm --vlm qwen3-vl:2b-instruct-q4_K_M
%EIM_LOCALAI_DIR%\venv\Scripts\python scripts/localai_bench.py --sections asr,embeddings,frameworks --audio-dir <carpeta> --emb qwen3-embedding:0.6b --llm qwen3:4b-instruct
```
Si el Ollama del banco no es el del puerto 11434, definir antes `EIM_LOCAL_LLM_HOST` y
`OLLAMA_MODELS` (el banco lee de ahí el GGUF para llama.cpp) y `EIM_TESSERACT`. El VLM se mide
sobre 12 fotogramas a 768 px (`--vlm-frames`, `--vlm-side`) y se corta solo si la RAM libre baja de
1,5 GB: en `juanpablo-cpu` su runner llegó a 8,8 GB y dejó el equipo sin memoria (auditoría,
alerta 15). Una sección que falla queda anotada como error y las demás siguen.

**Capa de motores en EIM (T63, `eim/localai/`).** Se configura con `EIM_LOCALAI_*` (§2; todo `off` por defecto) y se comprueba sin generar nada con `python -m eim.localai check` (motor, modelo y SHA de pesos por etapa, o por qué no se usa). Salud: `python -m eim.localai summary`. Prueba manual de aceptación (pesada: por la cola, con el entorno de `EIM_LOCALAI_DIR`): `python -m eim.operation.jobs submit --name localai-smoke --min-ram-mb 5500 -- %EIM_LOCALAI_DIR%\venv\Scripts\python -m eim.localai smoke --audio <1 min> --image <fotograma> --report reports/localai/smoke_<equipo>.json`. Si la RAM libre no cubre el pico del modelo más el margen, la etapa sale `deferred` (aplazada) y no se carga.
El banco no descarga nada (lo que falte sale «no instalado»/«no descargado»), mide con los servicios
de EIM tal como estén (y lo anota) y fusiona corridas sucesivas en el mismo informe. Las muestras de
audio (`--audio-dir`) llevan `manifest.json` con `file`, `lang` y `ref` (transcripción corregida a
mano de los primeros 3 min). Cada colaborador lo corre en su equipo; la lista se escribe para el
mínimo.
