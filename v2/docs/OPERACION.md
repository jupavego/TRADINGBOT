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
| Literatura con evidencia (T54) | `python -m eim.literature ctx` (completa los contextos con `lit`) · `python -m eim.literature report` → `reports/literature/lit_v1_<fecha>.md` + `.json` | Con la API detenida (DuckDB admite un solo proceso escritor). El ajuste de escenarios está apagado (`eim/forecast/lit_tilt_state.json`; definición inmutable en `versions/lit_tilt_v1.json`); encenderlo = commit con `enabled: true` tras un informe que cumpla T1–T6 |
| Copy trading: líderes (T40, solo lectura) | `python -m eim.leaders discover --seconds 300` → `watch 0x…` → `run [--minutes M]` → `report --minutes 60` | Hyperliquid público, sin claves; ≤ 10 líderes por WS y el resto por REST; base `data/leaders.duckdb` (proceso propio) |
| Copy trading: evaluación (T41) | `run` evalúa cada 5 min y escribe `data/leaders/board_*.json` (pestaña «Líderes», agente `smart_money`); con el vigilante apagado: `score [--portfolio]` | El veredicto (aprobado/vigilancia/descartado) lo fija el scorecard; solo aprueba con ≥ 30 operaciones y ≥ 7 d observados adelante; `unwatch` deja de capturar |
| Copy trading: servicio continuo | `python -m eim.leaders supervise` (lo lanza `scripts/servicio_continuo.ps1`, §6) | `run` sin fin bajo vigilante de proceso: lo relanza si cae o si su latido se detiene; uno solo por carpeta de datos |
| Captura HFT (T78) | Servicio: `python -m eim.data.collectors.hft_supervise BTCUSDT --root data` (lo lanza `scripts/servicio_continuo.ps1`, §6). A mano: `python -m eim.data.collectors.hft_ops --root data` (QC + compactación + retención + resumen), `python -m eim.data.collectors.hft_verify --root data --all [--out carpeta]` (ida y vuelta y `.npz` del simulador) | Escribe `data/micro_hft/` (no toca `data/micro/` de T23): todos los diffs de `depth@100ms`, `bookTicker`, `aggTrade`, `markPrice@1s` y `forceOrder` con la hora de Binance y la de llegada; snapshot REST cada 5 min para verificar el libro (top-10 exacto). QC por hora en `data/micro_hft/qc/` y resumen en `qc/symbol=BTCUSDT/summary.json` (horas completas, coincidencia top-10, huecos no detectados, MB/día, proyección a 30 días). Medido (1 h, 04 UTC del 2026-10-24): ≈ 417 MB/día sin compactar, ≈ 370 MB/día compactado (ZSTD) → ≈ 11 GB en 30 días, ≈ 17 GB con la retención de 45 días |
| Copia de seguridad a demanda | `python -m eim.data.backup create` | Las tres bases (`reports`, `paper`, `leaders`) + observatorio y estado. Si la API está en marcha, se la pide a ella; `leaders.duckdb`, al servicio de líderes. La CLI usa `EIM_DATA_DIR`, `EIM_BACKUP_DIR` y `EIM_BACKUP_KEEP` como la API |
| Verificar la traza de una vela (T74) | `python scripts/obs_verify_traces.py` (desde `v2/`; `--provider spot` si `fapi.binance.com` da 451; `--wait` segundos; `--keep` conserva los datos) | Arranca la API real en papel con carpeta temporal (no toca tus datos ni envía nada a un exchange), espera un ciclo y comprueba la traza más reciente en `/v2/obs/traces`: fuente y cobertura de datos, una señal por agente, síntesis, pronóstico, plan, riesgo y —solo si el riesgo aprobó— la cadena de órdenes. Código de salida 0 si todo lo obligatorio pasa |

**Nunca** lances la API con `--host 0.0.0.0`: además de quedar en la red, el middleware de
`eim/api/security.py` rechazará a los clientes remotos (403) y los `Host` ajenos (400).

## 2. Variables de entorno
| Variable | Defecto | Uso |
|---|---|---|
| `EIM_DATA_DIR` | `data` | Almacén (parquet, DuckDB, estado) |
| `EIM_EXECUTION` | `off` | `paper` / `testnet` |
| `EIM_OPERATE`, `EIM_OPERATE_TF`, `EIM_OPERATE_POLL_S` | `0`, `1h`, `60` | Servicio continuo (lo fija `eim.operation run`) |
| `EIM_BACKUP_DIR`, `EIM_BACKUP_KEEP` | `backups`, `14` | Copias; se conservan las N completas más recientes (§3) |
| `EIM_ALLOWED_HOSTS` | `127.0.0.1,localhost,::1` | Cabeceras `Host` aceptadas |
| `EIM_API_TOKEN` | — | Sin él, ningún cliente remoto entra. Con él: `Authorization: Bearer <token>`; en WebSocket, subprotocolo `eim-token.<token>` (los navegadores no admiten cabeceras ahí) |
| `EIM_CORS_ORIGINS` | `http://127.0.0.1:5173,http://localhost:5173` | Orígenes del navegador (también para el WebSocket) |
| `EIM_TESTNET_API_KEY` / `_SECRET` / `_URL` | — | Solo testnet; el broker bloquea cualquier otro host |
| `EIM_CALENDAR`, `EIM_CALENDAR_S` | `1`, `21600` | Calendario económico (Fed/BLS/BEA): consulta al arrancar y cada 6 h en `data/calendar/` (T36). `0` lo apaga |
| `EIM_OBS` | `on` | Observatorio (T72): `off` apaga la emisión de eventos (JSONL en `data/obs/spool/`). Emitir nunca rompe ni frena el ciclo; los descartes se cuentan. T73: la API indexa esos JSONL cada 5 s en `data/obs/obs.duckdb` (derivado, entra en la copia diaria, no viaja entre equipos) y lo sirve en solo lectura en `/v2/obs/*`; estado y retraso en `/v2/obs/health`. Retención: spool 7 d, eventos 30 d, `runs`/`decisiones` 180 d. Si se pierde la base, se reconstruye indexando el spool |
| `EIM_ARBITRAGE`, `EIM_ARBITRAGE_S` | `1`, `10` | Escáner de arbitraje Binance (REST público, solo lectura): fotografía cada ~10 s en `data/arbitrage/` (últimas 20), pestaña «Arbitraje» y mensaje WS `arbitrage` (T39). `0` lo apaga. Modo Análisis: no ejecuta |
| `EIM_ARB_ASSETS`, `EIM_ARB_TRI_ASSETS` | `BTC`, `USDT,BTC,BNB,SOL,XRP` | Foco actual (T122, 2026-10-22: solo BTC): activos del escáner de arbitraje (funding, base, perpetuos relacionados) y de sus ciclos triangulares; sin ETH. `BTC,ETH` lo devuelve |
| `EIM_ARB_EXECUTION`, `EIM_ARB_EXEC_S` | `off`, `60` | `testnet`: ejecución automática de arbitraje (T45) en spot testnet + futuros testnet con la fotografía del escáner; ciclo cada N s. Riesgo `eim/risk/versions/risk_arb_v1.json` (cuenta total: margen y exposición de toda la cuenta de futuros; kill-switch compartido) |
| `EIM_SPOT_TESTNET_API_KEY` / `_SECRET` / `_URL` | — (usa las de futuros) | Clave de la testnet spot (`testnet.binance.vision`); en la cuenta demo de Binance la de futuros vale para ambas. Sin permiso de retiro |
| `EIM_ARB_ALERT_SCORE`, `EIM_ARB_ALERT_S` | `3`, `60` | Alerta de arbitraje: puntuación del selector ≥ umbral (pb/día ajustados por riesgo) sostenida N segundos de escaneos seguidos (T39) |
| `EIM_PAPER`, `EIM_PAPER_S` | `1`, `60` | Bróker simulado (T47/T48): cada ciclo trae velas de 15 m/1 h/4 h y funding de BTCUSDT y analiza las velas cerradas nuevas de los tres marcos → `data/paper.duckdb`. `0` lo apaga. Siempre SIMULADO |
| `EIM_SHARED_DIR`, `EIM_MACHINE`, `EIM_SHARE_*` | — | Experiencia compartida entre equipos (T61, §3.1): carpeta de nube compartida, alias único de esta máquina y cadencias del modo automático (también `python -m eim.data.share setup`) |
| `EIM_FRED_API_KEY` | — | Opcional (gratuita): valores real/anterior/revisado de IPC, NFP, PCE, PIB, IPP desde FRED. Sin ella los eventos salen sin valores |
| `EIM_LIBRARY_DIR`, `EIM_LIBRARY_INDEX`, `EIM_TESSERACT` | `data/library/books`, `data/library/index`, autodetección | Biblioteca de trading (T52): carpeta de los libros del usuario (fuera del repo), índice local (catálogo, texto por página, caché de OCR) y ruta de `tesseract.exe` si no está en el PATH |
| `EIM_WS_URL`, `EIM_HEARTBEAT_S`, `EIM_SNAPSHOT_BARS`, `EIM_AUTO_HISTORY`, `EIM_RECON_S` | ver `eim/api/config.py` | |

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
- **Fuera del equipo:** `backups/` está en `.gitignore` y vive en el mismo disco. Sincroniza esa
  carpeta con otro disco o un almacenamiento en la nube (p. ej. OneDrive) o usa `EIM_BACKUP_DIR`
  apuntando a otra unidad. `share export` (§3.1) es otra vía fuera del equipo, pero no se restaura.
- **Captura HFT (T78):** la copia lleva solo los JSON de calidad (`state/micro_hft_qc/`), nunca los crudos de `data/micro_hft/` (≈ 370 MB/día; se podan a los 45 días). Para conservar más tiempo un tramo para T80/T84, copiarlo a otro disco a mano.
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
  equipo (gestor de credenciales / `gh auth`); cada colaborador necesita acceso de escritura al repo. Un
  archivo > 90 MB se rechaza (límite de GitHub). **Nunca** apuntes esto al repo del código.
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
la carpeta compartida: solo viajan Parquet + `manifest.json` (SHA-256 por tabla, commit, esquema).
**Pendiente ◆:** el usuario revisa el informe de la primera mezcla real antes de dar T61 por cerrada.

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
set EIM_LIBRARY_DIR=C:
uta\Books        # PowerShell: $env:EIM_LIBRARY_DIR = '...'
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
- **Servicio continuo (T48):** `powershell -ExecutionPolicy Bypass -File v2\scripts\servicio_continuo.ps1 -ConWeb` deja corriendo el vigilante (API + operación en papel + bróker simulado en 15 m, 1 h y 4 h), el servicio de líderes (abajo) y la interfaz; no duplica si ya están arriba. `v2\scripts\instalar_inicio_automatico.ps1` lo registra al iniciar sesión (`-Quitar` lo borra); la tarea llama al script por su ruta, así que lo añadido al script entra sin reinstalarla. El equipo no debe suspenderse. Latido del bróker: `data/paper/heartbeat.json`; la vista muestra «Servicio en vivo · último ciclo hace …». Salidas de consola: `data/operation/logs/` (`vigilante.*`, `lideres.*`, `web.*`).
- **Captura HFT (T78):** el mismo script lanza `python -m eim.data.collectors.hft_supervise BTCUSDT --root <datos>` (vigilante de T104: cerrojo `data/micro_hft/supervisor.lock`, latido `data/micro_hft/heartbeat.json`, reinicio con espera creciente, aviso si se apaga, se queda sin flujo o el disco baja de 5 GB). Cada 10 min audita las horas cerradas (QC), compacta las de más de 2 h, poda los crudos de más de 45 días (`--keep-days`) y reescribe el resumen; registro en `data/micro_hft/logs/` (`mantenimiento_hft`, `qc_hft_aviso`). El informe semanal trae la sección «Captura HFT (calidad de datos)». Para detenerla: matar el vigilante y luego `hft_ws` (el vigilante solo deja la captura huérfana). T80/T84 piden 14–30 días contiguos: la racha contigua más larga de horas completas sale en el resumen.
- **Servicio de líderes (T41):** el mismo script lanza `python -m eim.leaders --root <datos> supervise`, en un proceso propio porque es el único que puede abrir `data/leaders.duckdb` (DuckDB admite un solo proceso). El vigilante lanza `run` (captura de Hyperliquid + tablero cada 5 min en `data/leaders/`) y lo relanza si termina o si su latido (`data/leaders/heartbeat.json`, cada ≤ 30 s mientras terminan tareas) no avanza en 15 min, con espera creciente (10 s… máx. 5 min). Reinicios en `data/leaders/logs/op-AAAA-MM-DD.jsonl` (`proceso_reiniciado`) y aviso de Windows «Líderes: servicio reiniciado». No se lanza otro si ya corre `supervise` o un `run` a mano (el script lo detecta por la línea de órdenes y el cerrojo `data/leaders/supervisor.lock` lo impide de todos modos). Sale sin vigilar, y el script lo dice («Servicio de líderes NO lanzado: …»), si no hay líderes en seguimiento o si la base está en uso.
  - **Para `watch`/`unwatch`/`list`/`score`** (necesitan la base): detener el servicio, ejecutar la orden y volver a lanzar el script. Detener (vigilante y captura):
    `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ? CommandLine -match 'eim\.leaders' | % { Stop-Process -Id $_.ProcessId -Force }`.
    Matar el vigilante solo deja la captura huérfana (sin relanzamiento): el script ya no la duplica, pero tampoco la vigila; detén ambos.
  - **Si se apaga** (equipo suspendido, proceso detenido): a los 10 min el tablero queda viejo; la pestaña «Líderes» lo marca y `build_snapshot`/la API dejan sin líderes al agente `smart_money` → `no_data`. El tiempo sin captura no cuenta como días adelante (cada salto entre fotos cuenta como mucho 15 min): la aprobación (≥ 7 d y ≥ 30 operaciones) se retrasa lo que dure el apagado. Las ejecuciones de ese periodo no tienen precio del seguidor (solo se graba en vivo).
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
- **Semanal (lunes UTC):** leer `reports/operation/semana_AAAA-Www.md` (se genera solo).
- **Mensual:** auditoría de dependencias (§5) y `python -m eim.data.backup verify` sobre una copia
  antigua (prueba de restauración en una carpeta temporal: `restore <copia> --data-dir <tmp>`).
