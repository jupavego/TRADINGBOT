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
- **Desplegado (14:50 UTC, con permiso):** `git merge --ff-only origin/main` en la carpeta
  principal (sin reiniciar servicios) e `instalar_copia_externa.ps1` → tarea «EIM - copia externa
  diaria» (20:30 hora local); probada con `Start-ScheduledTask` → salida 0 en 54 s (copia ya en
  GitHub, no la vuelve a subir). El registro salía con los acentos rotos (la consola oculta usa
  ibm850): `copia_externa.ps1` fija ahora la salida de la consola a UTF-8 (llega con el PR #172).
- **Abierto:** `juanpablo-cpu` sin verificar.
- **En curso:** T31, T45, T78, T104, T116, T117, T119.
- **Siguiente paso:** fusionar el PR #172 y `--ff-only` en la carpeta principal; en `juanpablo-cpu`,
  `docs/CONTINUIDAD.md` §2 y §3 A.

## 2026-10-30 23:40 UTC · juanpablo-cpu · T125/T117 llegada del equipo, simulacro e importación
- **Hecho:** diagnóstico de `DESKTOP-93R810K`. El clon está en `C:\Users\jo\Desktop\JP\TRADINGBOT`, con `main` 19 commits atrasado y nada sin subir: las ramas locales `t106`/`t107` ya están en `origin/main`, y solo quedan sin seguir `.claude/settings.local.json` y el informe propio `v2/reports/operation/semana_2026-W43.*`. Es el **caso A** (historial propio). El modo automático de T61 apuntaba al repo viejo `jupavego/eim-shared-data` (ramas `machine/juanpablo` y `machine/juanpablo-cpu`). No hay `D:/eim-bots`. Corrían el recolector de microestructura, la captura HFT y Vite; la API, la operación y los líderes estaban parados (último latido de la operación: 2026-10-29 16:31 UTC). La tarea «EIM - servicio continuo (broker simulado)» arrancaba al iniciar sesión.
  - Respaldo en `%USERPROFILE%\EIM_respaldos\20261030-175903`. `-SoloRespaldo` se paró en su verificación (la captura HFT escribe en `micro_hft`, BACKLOG T125 (1)); los mismos pasos, completados a mano, dan 346 archivos y 432 642 449 B idénticos sin `micro_hft`, y el bundle de ramas verificado. Copia del sistema: `eim_20261030-230202` **íntegra**.
  - `git pull --ff-only` (`ebf3900` → `f44cae5`). Locks sin cambios: el simulacro de pip no instala nada, `pip check` y `npm ls` salen bien y se reinstaló el paquete editable; `npm ci` no se ejecutó porque Vite estaba en marcha.
  - Con permiso del usuario: tarea de inicio **desactivada**, `data/share_repo` apartado a `share_repo.jupavego-20261030` (BACKLOG T125 (2)), `share setup --git-url https://github.com/Santivego/eim-shared-data.git --machine juanpablo-cpu`, `export` → rama `machine/juanpablo-cpu` en Santivego (`0105753`, `20261030T231112Z`, 29 s) y `import` en simulacro (100 s).
  - Con el visto bueno del usuario al simulacro: `import --apply --from laptop-i6pf9ovp-fce8d9` con los servicios parados, sobre la misma foto (`730dce4`), en 124 s. Salieron las mismas cifras. Copia previa en `backups/pre-import_20261030T232551Z-juanpablo-cpu`; veredictos recalculados (208 intentos).
- **Archivos:** `PLAN/{BITACORA,ESTADO_PROYECTO,BACKLOG}.md`.
- **Pruebas:**
  - `backup verify` → 4 bases, 561 909 filas (reports 116 631, paper 18 716, leaders 232 639, obs 193 923).
  - `eim.continuity check` → **CON AVISOS**: 2 archivos sin confirmar y sin copia externa propia; datos, copias, código (`main @ f44cae5`) y seguridad OK.
  - `git ls-remote` de Santivego antes del export: solo `machine/laptop-i6pf9ovp-fce8d9` (identidad libre). Después: más `machine/juanpablo-cpu`. La rama del repo viejo no cambió (`a54bc4f`).
  - Simulacro desde `laptop-i6pf9ovp-fce8d9` `20261030T030349Z` (nuevas / ya estaban / conflicto / incompat.): reports 12 517 / 589 / 1 242 / 0 · sim_trades 41 / 3 / 1 / 0 · paper_ctx 35 499 / 8 / 3 449 / 0 · val_versions 0 / 191 / 0 / 0 · val_windows 104 / 87 / 0 / 0 · leaders 15 / 0 / 0 / 0 · leader_fills 2 807 174 · leader_funding 35 772 · leader_leverage 4 · leader_positions 35 444 · leader_follow 2 129 264 · leader_recon 87 924 · leader_gaps 16 623 · copy_journal 33 992 (líderes: todo nuevas). **Total: 5 194 373 nuevas, 878 ya estaban, 4 692 en conflicto, 0 incompatibles.** Las bases y los WAL no cambiaron (mismos bytes y fechas).
  - Gate: ruff OK; 2 425 pruebas pasadas, 7 omitidas y 0 fallidas en 13,4 min, con el recolector y la captura HFT en marcha.
  - Tras aplicar, cada tabla importada creció exactamente en sus «nuevas»: líderes +5 146 212, paper_ctx +35 499, reports +12 517, val_windows +104, sim_trades +41. `share_conflicts` sumó +1 243 (reports) y +3 449 (paper). El recálculo añadió 104 `val_verdicts`, 486 filas de `paper_ledger` y 1 `paper_view_snapshot`. `backup verify` de `eim_20261030-232849` → **íntegra**, 10 955 952 filas (reports 142 992, paper 93 965, leaders 10 525 072, obs 193 923). `leaders.duckdb` pasó de 88 MB a 1,27 GB.
  - Arranque (con permiso, 23:35 UTC). Modo automático **apagado** antes, como en la portátil: `share_config.json` apartado, y `GET /v2/share/status` → `enabled: false`. `servicio_continuo.ps1 -ConWeb` lanzado por WMI. API sana en 8 s (`SIMULADO`, «operando», 19 agentes). El primer ciclo del bróker falló al leer una hora de microestructura que la operación compactaba en ese instante (`micro_compactada`, 23:37:43); el reintento se puso al día con ~31 h de velas en ~17 min, y el cierre de las 00:00 UTC se analizó solo (15m/1h/4h, sin error). Operación: 23 ciclos, 0 fallos. Líderes: 17/17 listos y tablero fresco. Arbitraje: escaneo cada ~11 s. Microestructura y HFT con latido (`dropped` 0). Proyección con 3 escenarios. Operaciones sugeridas: «sin validadas» (89 en observación, 15 rechazadas; puerta T49). La interfaz se dibuja «EN VIVO»; vista del bróker: 38 914 velas (1 105 en vivo) y 270 operaciones, 77 % ganadas. Tras abrir la interfaz se resolvieron los avisos «sin latido» de precio en vivo y difusor. Siguen degradados por datos, como antes del reinicio: liquidaciones (cobertura 54 %), microestructura (huecos de secuencia), VWAP mensual parcial y literatura. Hoja de ruta viva republicada (`build_roadmap.py`: 125 tareas, 79 hechas).
- **Abierto:** la importación manual no anota `data/share/state_*.json` (BACKLOG T125 (5)); con el modo automático apagado no hace falta. Revisar `share_conflicts` fila a fila (nota T117 §6.6). Este equipo no tiene copia externa ni Freqtrade.
- **En curso:** T31 (portátil; aquí corre una operación en papel propia), T45, T78, T104, T116, T117, T119.
- **Siguiente paso:** la portátil hace su simulacro sobre `machine/juanpablo-cpu`; decidir si `juanpablo-cpu` opera a diario (reactivar la tarea de inicio e instalar `instalar_copia_externa.ps1`, que también publica su experiencia).

## 2026-10-31 07:18 UTC · juanpablo-cpu · T31/T78/T116/T117/T119 tareas en curso desde este equipo
- **Hecho:** por decisión del usuario, las tareas que estaban en curso en la portátil siguen desde aquí.
  - **Operación diaria:** la tarea «EIM - servicio continuo (broker simulado)» está reactivada (al iniciar sesión) y se instaló «EIM - copia externa diaria» (20:30 hora local, ~01:30 UTC). La primera copia externa, a mano, es `eim_20261030-232849` (581 MB en 3 partes). La exportación de la experiencia falló con HTTP 408 al subir 243 MB, y el reintento dijo «PUBLICADO» sin subir nada (BACKLOG T125 (6)). Se subió a mano con `http.postBuffer` grande → `machine/juanpablo-cpu` = `87a7426`.
  - **T31:** corrida propia de este equipo desde el 2026-10-30 23:35 UTC hasta el 2026-11-27. La de la portátil sigue en paralelo.
  - **T117:** desde aquí se comprobó la idempotencia y se hizo el simulacro en sentido portátil. La unión es conmutativa.
  - **T119 ☑:** la API y la CLI dan la misma puntuación.
  - **Copias de `leaders.duckdb`:** las copias en caliente `eim_20261031-000042` y `-002221` salieron **sin `leaders.duckdb`**: la instantánea del servicio de líderes se quedó sin memoria con el tope de 1 GB y una base de 1,27 GB. Con permiso: `EIM_DUCKDB_MEMORY=2GB` (variable de usuario) y reinicio solo del servicio de líderes. La API, la operación, el bróker y los recolectores siguieron en marcha y `/v2/health` respondió `ok` todo el rato. Resultado: `eim_20261031-005644` completa (BACKLOG T125 (7)).
  - **T78:** contraste con la QC de la portátil (viaja en su copia externa `eim_20261030-030349`). Aquí rinde mejor; lo que le resta horas es la carga local. Ventana de 72 h: del 2026-10-31T08 al 2026-11-03T07 UTC (72 horas completas: de las 08:00 UTC del 31-oct a las 08:00 UTC del 3-nov), abierta tras los gates de T116 y la copia externa repetida.
  - **T116:** las 3 corridas «con Ollama real» que quedaban pendientes, con `qwen3:4b` generando sin parar y los servicios en marcha. **No salen verdes**, pero todos los fallos son de pruebas con plazo de tiempo o latidos.
  - **Copia diaria del 2026-10-31:** la tarea de las 01:36 UTC falló por la carga de T116: TLS con GitHub agotado, `git ls-remote` a 300 s y `git rev-parse` a 60 s (BACKLOG T125 (8)). La copia local de ese día quedó verificada. Repetida a mano a las 07:09 UTC (la misma copia diaria aprobada): `eim_20261031-005644` subida (589 MB en 3 partes, con líderes) y experiencia `20261031T005644Z` publicada, `machine/juanpablo-cpu` = `35cc71e` (comprobado con `git ls-remote`). Su *bundle* de ramas solo locales falló por una ruta relativa (BACKLOG T125 (9)).
  - **Suspensión:** a petición del usuario se comprobó que no detiene los procesos. Plan «Alto rendimiento»: suspender e hibernar «Nunca», con corriente y con batería; 0 suspensiones, reanudaciones o reinicios en las 24 h previas. Windows Update sin reinicio pendiente (horas activas 8–17 hora local). La app de Claude mantiene el equipo despierto mientras trabaja. No se cambió ningún ajuste del sistema.
- **Archivos:** `PLAN/{BITACORA,STATUS,ESTADO_PROYECTO,BACKLOG}.md` y la hoja de ruta regenerada.
- **Pruebas:**
  - T117, idempotencia: la misma foto sobre la copia posterior da 0 nuevas en las 14 tablas. Sentido portátil (copia `eim_20261030-030349` y exportación `20261030T232849Z`): 217 084 nuevas, 5 195 251 ya estaban (= lo aplicado aquí), los mismos 4 692 conflictos y 0 incompatibles.
  - T119: API viva (`GET /v2/bots/scorecard`, corte 00:00 UTC, `vigente`) frente a la CLI sobre la copia en caliente `eim_20261031-002221` (corte 00:15 UTC). Mismos 24 intentos de Holm (id, veredicto, n, p bruto, p Holm, retirado, control), mismos estados por bot y mismo resumen (11 informan, 0 votan).
  - Copia `eim_20261031-005644`: `backup verify` → **íntegra**, 1 565 MB, líderes 10 589 988 filas. La instantánea de líderes tardó 410 s con el equipo cargado.
  - T78: antes de la ventana, 19 de 32 horas completas (59 %). En las 11 horas en que capturaban los dos equipos (28-oct 23 UTC a 30-oct 01 UTC), la portátil completó 0 (24–122 silencios por hora) y este equipo 6 de las 9 que llevaba capturando. Las 2 horas que fallan en ambos (28-oct 23 y 29-oct 23 UTC, con desconexiones) son eventos de Binance.
  - T116: 3 corridas de 00:32 a 03:38 UTC con 324 generaciones de Ollama. `ruff` limpio en las 3. `pytest`: 2, 1 y 10 fallos, en 63,8, 36,2 y 85,8 min (las de la portátil, 11–20 min). Fallan `test_emit` (sobrecarga del ciclo, las 3; dos procesos), `test_obs_api` (100k eventos), `test_hft_risk` (p99), 3 de `test_service_heartbeats` y 3 de `test_paper_api`. Los 11 casos pasan aislados en 63 s con los servicios en marcha.
- **Abierto:** BACKLOG T125 (6)–(9). T116: decidir si el gate debe aguantar Ollama generando (margen de las pruebas con plazo). T117: revisar `share_conflicts` fila a fila. La copia externa diaria (~01:30 UTC) cae dentro de la ventana de T78. Conviene pausar Windows Update durante la ventana: lo hace el usuario.
- **En curso:** T31 (aquí y en la portátil), T45, T78 (ventana del 2026-10-31T08 al 2026-11-03T07 UTC (72 horas completas: de las 08:00 UTC del 31-oct a las 08:00 UTC del 3-nov), abierta tras los gates de T116 y la copia externa repetida), T104, T116, T117.
- **Siguiente paso:** al cerrar la ventana de T78, leer `data/micro_hft/qc/symbol=BTCUSDT/summary.json` y anotar la aceptación en `STATUS.md`. Después, T104 (corte de red provocado y línea base de 7 días) y T116 con el equipo descargado (◆ permiso para parar servicios).

## 2026-10-31 07:45 UTC · juanpablo-cpu · T62 motores locales (auditoría y banco)
- **Hecho:** T62 de ☐ a ◐, en la rama `claude/t62-motores-locales` (worktree aparte: en la carpeta principal trabajaba la sesión de T116).
  - Auditoría en 5 grupos paralelos, solo lectura (nada instalado ni ejecutado de terceros): captación+ASR, escenas/OCR/VLM, motores, LLM+embeddings y marcos. Licencia de código y de pesos por tamaño concreto, SHA/digest a fijar, red/telemetría, pickle/código remoto e instalación en Windows → `PLAN/notas/T62_auditoria.md`: 14 alertas, veredictos por eslabón, lista aprobada **propuesta** y detalle con evidencia enlazada.
  - Verificado aquí: el `qwen3:4b` instalado es la variante *Thinking* (su plantilla abre `<think>` siempre); `ollama serve` reescribió `~/.ollama/cache/model-recommendations.json` sin la app abierta, y en el código v0.40.11 `OLLAMA_NO_CLOUD` corta esa consulta.
  - Banco `v2/scripts/localai_bench.py` + `localai_bench_{sys,score,llm,engines,frames,vision,audio,report}.py`: LLM (velocidad, memoria, 10 transcripciones es/en con afirmaciones esperadas, dos con texto dirigido al modelo), Ollama frente a `llama-server` con el mismo GGUF (lanzado en 127.0.0.1 con `--offline --no-webui --api-key`), GPU (`num_gpu=0` frente a automático), Pydantic AI frente a la validación propia, escenas sobre un video con cortes conocidos, OCR y VLM sobre 36 fotogramas sintéticos con cifras conocidas (es/en, claro/oscuro, 480p JPEG), ASR (factor de tiempo real y WER contra referencia corregida, un proceso por modelo) y embeddings; presupuesto derivado que separa lo medido de lo supuesto. Sin red salvo 127.0.0.1; nunca descarga.
  - Postura ante YouTube propuesta (`v2/docs/SEGURIDAD.md`), reglas de seguridad de motores locales, instalación mínima (`v2/docs/OPERACION.md` §7 y variables en §2) y extras `[video]`/`[localai]` con versiones exactas (`v2/pyproject.toml`).
- **Medido** (`v2/reports/localai/bench_juanpablo-cpu.md`, servicios de EIM en marcha: API 1,8 GB, líderes 0,9 GB, recolectores 0,2 GB; 5,0 GB libres de 16): el filtro de escenas de ffmpeg halla el 20 % de los cortes con umbral 0,3 y el 43 % con 0,05, sin falsos positivos (0,3 s por minuto de video). **No se pudo medir nada con Ollama:** vive en `Z:` (`\DESKTOP-TVD562Q\USB`), que cayó hacia las 07:00 UTC; el servidor sigue respondiendo, pero una petición de 1 token quedó colgada 150 s sin runner.
- **Archivos:** `PLAN/notas/T62_auditoria.md`, `PLAN/{STATUS,BACKLOG,ESTADO_PROYECTO,BITACORA}.md`, `PLAN/status.js`, `v2/scripts/localai_bench*.py`, `v2/scripts/localai_data/claims_cases.json`, `v2/tests/localai/`, `v2/reports/localai/bench_juanpablo-cpu.{json,md}`, `v2/docs/{SEGURIDAD,OPERACION}.md`, `v2/pyproject.toml`.
- **Pruebas:** `tests/localai/test_bench.py` (8: lectura de cifras es/en, WER, normalización, puntuación de afirmaciones con niveles inventados, datos válidos, presupuesto parcial y vacío, fotogramas deterministas, informe con secciones a medias). Gate: ruff OK; 2 433 pasadas, 7 omitidas, 0 fallidas en 12,1 min con los servicios en marcha.
- **Abierto:** ◆ el usuario decide la lista (motores, licencias de pesos) y la postura ante YouTube; permiso para instalar en disco local (`EIM_LOCALAI_DIR`; este equipo no tiene E:) y bajar pesos (≈ 9 GB en total con Ollama); muestras de audio es/en con 3 min corregidos a mano. Nada commiteado.
- **En curso:** T31 (portátil), T45, T62, T78, T104, T116, T117, T119.
- **Siguiente paso:** con el visto bueno, instalar según `OPERACION.md` §7 y correr las tres órdenes de verificación aquí y en la portátil (equipo de referencia); con eso, completar el presupuesto y cerrar T62.

## 2026-10-31 15:00 UTC · juanpablo-cpu · T62 instalación y banco completo
- **Hecho:** el usuario aprobó la lista y la instalación («Sí, instala»); T62 sigue ◐ (rama `claude/t62-motores-locales`).
  - Instalado en `C:\eim-localai` (12 GB; este equipo no tiene E:) según `v2/docs/OPERACION.md` §7: Ollama v0.40.11 (zip con SHA-256 `bda4a493…` = `sha256sum.txt`; firmado por Ollama Inc.), llama.cpp b12018 CPU (`205755a9…` = *digest* de la release; sin firma), Tesseract 5.5.3 extraído con 7-Zip sin ejecutar el instalador (`bee9e343…`) + `eng/spa/osd` de `tessdata_best@e12c65a9` (SHA de blob comprobado); modelos `qwen3:4b-instruct` `0edcdef34593`, `qwen3-vl:2b-instruct-q4_K_M` `afc393e3572c`, `qwen3-embedding:0.6b` `ac6da0dfba84` (= auditoría); faster-whisper small `536b0662…` y turbo `0a363e91…` por revisión; entorno aparte con `[video,localai,library]`, `pip check` y `pip-audit` limpios.
  - El Ollama nuevo corrió en 127.0.0.1:**11435** solo durante el banco (lanzado a mano, `OLLAMA_NO_CLOUD=1`: «Ollama cloud disabled: true»; parado al terminar); el de `Z:` sigue ocupando el 11434 y `EIM_OLLAMA_EXE` apunta a él (sin tocar: ◆).
  - Banco corregido al medir: el prompt tok/s de Ollama salía ×13 inflado (reusa el prompt de su caché y cuenta igual sus tokens) → prefijo único por repetición; el presupuesto tomaba el OCR más rápido y no el que lee → por recall; VLM con subconjunto, lado máximo y corte por RAM libre < 1,5 GB; una sección que falla queda anotada y no tumba la corrida; faster-whisper desde la carpeta con revisión fijada; `av==18.1.0` (PyAV 19 rompe faster-whisper 1.2.1, SYSTRAN/faster-whisper#1589); Pydantic AI 2.x usa `retries`.
- **Medido** (`v2/reports/localai/bench_juanpablo-cpu.md`, con API 1,7 GB, líderes 1,1 GB y recolectores en marcha): `qwen3:4b-instruct` JSON 100 %, precisión 79 %, recall 85 %, 0 niveles inventados, 13 s/caso, prompt ≈ 45 tok/s, generación ≈ 8 tok/s, pico 4,5 GB · Ollama ≈ llama.cpp (8,1 ↔ 7,4 tok/s; 3,4 ↔ 2,6 GB) · GPU ×0,93 · Pydantic AI = validación propia (no se adopta) · RapidOCR 99 % de cifras a 1,5 s (Tesseract 57 %) · escenas ffmpeg 20–43 %, PySceneDetect 20 % · VLM 2B: aciertos altos pero 66 s/fotograma y 8,8 GB (dejó el equipo sin memoria dos veces; se cortó a mano y después con el corte automático) · faster-whisper small ×0,15–0,18 del tiempo real, turbo ×0,52–0,60 (audio sintético con el TTS de Windows sobre los casos del banco: el WER de 19–23 % no vale como calidad) · embeddings 36 s/100 textos · presupuesto ≈ 95 videos de 20 min por noche sin VLM (39 con VLM).
- **Visto al instalar:** el runner que lanza Ollama es un `llama-server` en un puerto efímero de 127.0.0.1 sin clave y con CORS `*` (alerta 10 ampliada, `docs/SEGURIDAD.md`).
- **Archivos:** `PLAN/notas/T62_auditoria.md` (alertas 9, 10, 14 y 15 nueva; tabla de lo medido), `PLAN/{STATUS,BACKLOG,ESTADO_PROYECTO,BITACORA}.md`, `PLAN/status.js`, `v2/scripts/localai_bench{,_audio,_engines,_llm,_report,_score,_vision}.py`, `v2/tests/localai/test_bench.py`, `v2/reports/localai/bench_juanpablo-cpu.{json,md}`, `v2/docs/{OPERACION,SEGURIDAD}.md`, `v2/pyproject.toml`.
- **Pruebas:** `tests/localai/test_bench.py` 9 (nueva: sección rota anotada e informe que la muestra; presupuesto sin VLM). Gate: ruff OK (`eim tests scripts`); 2 434 pasadas, 7 omitidas, 0 fallidas en 12,9 min, con los servicios de EIM en marcha.
- **Abierto:** ◆ postura ante YouTube; banco en el equipo de referencia (7,9 GB); muestras de audio reales con 3 min corregidos a mano; ◆ pasar el Ollama del sistema a `C:\eim-localai` (parar el de `Z:`, variables de usuario, puerto 11434). Nada commiteado.
- **En curso:** T31 (portátil), T45, T62, T78, T104, T116, T117, T119.
- **Siguiente paso:** correr las órdenes de `OPERACION.md` §7 en la portátil; con eso y la postura ante YouTube, cerrar T62 y empezar T63.

## 2026-11-01 21:40 UTC · juanpablo-cpu · T126 director de recursos (fase 1)
- **Hecho:** a pedido del usuario, diagnóstico de por qué fallan las corridas de días en este equipo (i5-6400, 4 núcleos, 16 GB) y fase 1 del arreglo en la rama `claude/t126-director-fase1`, **sin desplegar** (los servicios en marcha no se tocaron).
  - **Diagnóstico** (detalle en `PLAN/T126.md`):
    - La ventana de 72 h de T78 se perdió el 31-oct a las 13–14 UTC, cuando el equipo se saturó con la prueba de un modelo de visión de T62.
    - A las 21:46 UTC hubo un apagado forzado: botón de encendido durante una suspensión, con el inicio rápido activo.
    - Después, ~23 h sin servicios: las tareas del EIM solo arrancan al iniciar sesión.
    - La tarea programada dejaba los 26 procesos del EIM en BELOW_NORMAL, captura incluida, por debajo de cualquier programa abierto.
    - 34 alertas falsas de latido al día.
    - Restos de pruebas de juegos (NVIDIA Overlay, FrameView SDK) a decisión del usuario.
  - **Prioridades por nivel** (`eim/operation/priority.py`): captura en vivo en ABOVE_NORMAL, API, líderes y vigilantes en BELOW_NORMAL, mantenimiento, gate, copias y Ollama en IDLE. Se activa solo con `EIM_PRIORITY=on` (lo fija `servicio_continuo.ps1`). Para trabajos a mano: `python -m eim.operation.priority run batch -- <orden>`.
  - **Cadencias reales en el catálogo:** almacén de velas 3600 s y bróker 300 s.
  - **Arranque al encender:** `instalar_inicio_automatico.ps1 -AlEncender` registra una tarea S4U, sin necesidad de iniciar sesión. El lanzador ya no duplica nada con dos arranques a la vez.
  - **T78 por racha:** `hft_ops --streak` y `t78_streak` en el resumen. La mejor racha real es de 9 h (31-oct 04–12 UTC).
- **Archivos:**
  - `v2/eim/operation/priority.py` y los 9 puntos de arranque (`api/main.py`, `collectors/{binance_ws,hft_ws,liq_ws,supervise,hft_supervise}.py`, `leaders/cli.py`, `operation/__main__.py`).
  - `v2/eim/data/collectors/hft_ops.py` y `v2/eim/observability/catalog/components_flow.py`.
  - `v2/scripts/{servicio_continuo,instalar_inicio_automatico}.ps1`.
  - `v2/tests/{operation/test_priority,data/test_hft_streak}.py` y `v2/tests/observability/test_obs_alerts.py`.
  - `v2/docs/OPERACION.md`, `CLAUDE.md`, `PLAN/{T126,STATUS,BACKLOG,ESTADO_PROYECTO,BITACORA}.md` y la hoja de ruta.
- **Pruebas:** gate con la herramienta nueva (`priority run batch`, el intérprete real en IDLE, comprobado en vivo) y los servicios en marcha: ruff limpio; 2 436 pasadas, 7 omitidas y 0 fallidas en 12 min 39 s. Pruebas nuevas: niveles en subprocesos (la captura sube, el mantenimiento baja y se restaura, la API queda en BELOW_NORMAL, `run` deja a los hijos en IDLE), todo papel declarado con nivel, racha de T78 (5) y las dos alertas sin saltar a su ritmo normal. Los dos scripts se analizan sin errores, y la detección del vigilante de la API y de Vite encuentra los procesos reales. Racha calculada sobre los JSON de QC de la carpeta viva (solo lectura): 57 horas auditadas, la mejor de 9 h.
- **Abierto:** ◆ desplegar (reiniciar los servicios con el código nuevo) y registrar la tarea al encender desde una consola de administrador. Ajustes de Windows del usuario: inicio rápido, botón de encendido y, opcionalmente, exclusión de `v2\data` en Defender. Fases 2–3 en BACKLOG T126.
- **En curso:** T31, T45, T78 (sin ventana fija: por racha), T104, T116, T117, T126.
- **Siguiente paso:** con permiso del usuario, fusionar el PR, `git merge --ff-only origin/main` en la carpeta principal, reiniciar los servicios por la tarea y comprobar las clases de prioridad. Después, dejar correr la captura y leer `hft_ops --streak` hasta las 72 h.

## 2026-11-01 21:40 UTC · juanpablo-cpu · T126 despliegue de la fase 1
- **Hecho:** con permiso del usuario se desplegó la fase 1.
  - PR #175 fusionado (`efda32c`) y `git merge --ff-only origin/main` en la carpeta principal.
  - A las 21:34 UTC se detuvieron los 4 vigilantes y luego sus 5 servicios: 18 procesos con su lanzador, ninguno quedó vivo.
  - Se relanzó todo con `Start-ScheduledTask` de la tarea de inicio de sesión (resultado 0). Vite, la hoja de ruta, el icono y «equipo despierto» siguieron en marcha y el script no los duplicó.
- **Archivos:** `PLAN/{BITACORA,STATUS,ESTADO_PROYECTO,BACKLOG}.md`.
- **Pruebas:**
  - Prioridades medidas en los procesos reales: `binance_ws`, `hft_ws` y `liq_ws` en **AboveNormal**; la API, `leaders run`, los vigilantes y `eim.operation run` en **BelowNormal**. Antes estaban los 18 en BelowNormal.
  - La API respondió `ok` en SIMULADO, «operando», con 19 agentes, a los 12 s; 4 ciclos sin error y 0 reinicios.
  - A los 4 min: latidos de líderes 11 s y bróker 51 s, sin error. Captura HFT sincronizada, 0 mensajes perdidos, 0 silencios y 1/1 verificación del libro igual a Binance.
  - Un solo Vite, una sola hoja de ruta y un solo vigilante de la API.
  - Alertas al arrancar: «Precio en vivo» y «Difusor» sin latido, que salen en cada arranque hasta que se abre la interfaz, y «Protección en estado inconsistente: agresivo BTCUSDT», el diario de T110 que se repite en cada arranque desde el 31-oct. Ninguna la causa T126.
- **Abierto:** ◆ registrar `instalar_inicio_automatico.ps1 -AlEncender` desde una consola de administrador. Ajustes de Windows del usuario. Fases 2–3 en BACKLOG T126. La hora 21 UTC del 1-nov saldrá incompleta por el reinicio.
- **En curso:** T31, T45, T78 (por racha desde las 22 UTC del 1-nov), T104, T116, T117, T126.
- **Siguiente paso:** leer `python -m eim.data.collectors.hft_ops --root data --streak` a diario; T78 se cumple en cuanto la racha llegue a 72 h, como pronto el 2026-11-04 22 UTC.

## 2026-11-01 21:55 UTC · juanpablo-cpu · T126 tarea al encender
- **Hecho:** el usuario registró «EIM - servicio continuo al encender» desde una consola de administrador. Comprobado: estado `Ready`, S4U con el usuario `jo`, nivel limitado, disparo al arrancar con 2 min de retraso y la acción de `servicio_continuo.ps1 -ConWeb`. La tarea de inicio de sesión se conserva.
- **Pruebas:** `Start-ScheduledTask` con los servicios en marcha. Salió con código 0 en ~3 s: 23 procesos del EIM antes y 23 después, ninguno nuevo y ninguno parado. El registro operativo del Programador está desactivado (lo normal en Windows 10), así que no hay más rastro de la ejecución.
- **Abierto:** el arranque desde cero sin sesión iniciada solo se verá en el próximo reinicio real. Si Vite no levanta (PATH de `npm` en S4U), la interfaz llega al iniciar sesión. Los ajustes de Windows siguen pendientes del usuario.
- **Siguiente paso:** tras el próximo reinicio, comprobar que los servicios arrancaron antes de iniciar sesión (`proceso_lanzado` en `data/operation/logs/op-*.jsonl` unos 2 min después del arranque).

## 2026-11-01 22:00 UTC · juanpablo-cpu · T126 ajustes de Windows
- **Hecho:** el usuario hizo los ajustes de Windows (Claude no cambia ajustes del sistema; solo los comprobó). Desactivó el inicio rápido: `HiberbootEnabled` 0, leído del registro. Excluyó `C:\Users\jo\Desktop\JP\TRADINGBOT\v2\data` del análisis de Defender, comprobado en su captura de Seguridad de Windows. El botón de encendido sigue en «Apagar» (`PBUTTONACTION` 3), que sin inicio rápido es un apagado completo.
- **Causa del 31-oct confirmada:** con el botón en «Apagar» y el inicio rápido activo, pulsarlo inicia una hibernación del núcleo. Por eso el evento 41 marca `SleepInProgress=1`: esa transición se colgó y la segunda pulsación cortó la corriente.
- **Archivos:** `PLAN/{ESTADO_PROYECTO,T126,BITACORA}.md`.
- **Abierto:** ver el primer reinicio real (servicios ~2 min tras encender, sin iniciar sesión). Restos de juegos en NVIDIA App a decisión del usuario.
- **Siguiente paso:** seguir la racha de T78 con `hft_ops --streak`.

## 2026-11-01 22:15 UTC · juanpablo-cpu · T126 en la hoja de ruta
- **Hecho:** a pedido del usuario, el director de recursos entra en la hoja de ruta con su avance. Nueva fase 21 «Capacidad del equipo y procesos largos» con T126 (fase 1, ☑), T127 (fase 2: registro de consumo y cola de trabajos pesados con pausa, reanudación y puntos de control) y T128 (fase 3: un recolector por fuente, retención de líderes, ganchos fuera de la API, menos ruido; ◆ qué historial de líderes se conserva y qué restos se borran). Los ítems de la línea T126 del BACKLOG quedan repartidos entre las dos.
- **Archivos:** `PLAN/{T126,T127,T128,STATUS,00_MASTER,BACKLOG,ESTADO_PROYECTO,BITACORA}.md`, `PLAN/roadmap.html`, `PLAN/status.js`.
- **Pruebas:** `build_roadmap.py` sin tareas huérfanas (128 tareas, 81 hechas); hoja de ruta viva comprobada en el navegador.
- **Siguiente paso:** T127 y T128 están «Listas»; empezar por T127, antes comprobando el primer reinicio real.

## 2026-11-01 22:45 UTC · juanpablo-cpu · T126 prueba del reinicio y del arranque desde la sesión 0
- **Hecho:**
  - **Reinicio real a pedido del usuario** (arranque a las 22:08:34 UTC). Windows inició sesión solo a los 8 s (inicio de sesión automático tras un reinicio voluntario), así que actuó la tarea de inicio de sesión: vigilante a las 22:09:57 y API a las 22:10:46. La tarea al encender, a las 22:10:10, esperó el cerrojo y no lanzó nada (salida 0). Al arrancar se disparó también la copia externa diaria, que el 31-oct no llegó a correr: `eim_20261101-221145` publicada (622 MB, salida 0, 733 s).
  - **Arranque en frío desde la sesión 0**, simulado con permiso del usuario. Se detuvieron los 25 procesos (servicios, Vite y «equipo despierto») a las 22:25:03 UTC y se lanzó a mano la tarea al encender. En 19 s escuchaban la API y Vite (salida 0), y luego quedaron API `ok`, líderes, captura HFT sincronizada (1/1 verificación) e identidad `juanpablo-cpu`, sin errores en los registros. Todo en la sesión 0, con la prioridad base correcta: 3 procesos en AboveNormal (los recolectores) y 17 en BelowNormal.
  - **Hallazgo:** desde la sesión del usuario no se puede leer la línea de órdenes, la prioridad ni la hora de inicio de los procesos de la sesión 0 (sí la prioridad base por WMI, los puertos y los cerrojos). `servicio_continuo.ps1` detectaba los servicios por la línea de órdenes, así que al iniciar sesión después de un arranque en frío habría lanzado otro recolector de liquidaciones (sin cerrojo: dos escritores) y otro «equipo despierto». El resto lo frenaban sus cerrojos o los puertos, pero tocando sus registros abiertos.
  - **Arreglo:** cerrojo de instancia en `liq_ws` y en `eim.operation run`, cerrojo global en `mantener_despierto.ps1`, y `Ocupado` en el lanzador, que consulta el cerrojo de cada servicio (visible desde cualquier sesión) antes de lanzarlo. Si el cerrojo global del lanzador no se puede abrir, espera 30 s.
- **Archivos:** `v2/eim/data/collectors/liq_ws.py`, `v2/eim/operation/__main__.py`, `v2/scripts/{servicio_continuo,mantener_despierto}.ps1`, `v2/tests/operation/test_instance_locks.py`, `PLAN/{STATUS,ESTADO_PROYECTO,T127,BITACORA}.md`.
- **Pruebas:** la comprobación `Ocupado` contra los cerrojos reales de la sesión 0 da ocupados los 5 que existían y libre un archivo de prueba. 3 pruebas nuevas (vigilante duplicado, liquidaciones duplicadas, y `Ocupado` de PowerShell frente a `instance_lock` de Python) más las relacionadas: 31 pasadas. Los dos scripts se analizan sin errores. Gate en Idle con los servicios en marcha: ruff limpio; 2 439 pasadas, 7 omitidas y 0 fallidas en 14 min 12 s.
- **Abierto:** ◆ desplegar (reiniciar los servicios; hoy corren en la sesión 0 con el código anterior, sin el cerrojo de liquidaciones: no cerrar ni abrir sesión hasta desplegar). La racha de T78 cuenta desde las 23 UTC del 1-nov.
- **Siguiente paso:** fusionar, desplegar y comprobar que una ejecución de la tarea de inicio de sesión con todo en marcha no lanza nada.

## 2026-11-02 02:55 UTC · juanpablo-cpu · T126 despliegue de los cerrojos de instancia (PR #180)
- **Hecho:**
  - Fusionado el PR #180 (`d23d030`) con permiso del usuario, y main actualizada en la carpeta principal.
  - **Detener los servicios de la sesión 0:** desde la sesión del usuario, sin elevar, `Stop-Process` dio «Acceso denegado» en los 25 procesos y no se detuvo ninguno. El usuario ejecutó, en un PowerShell de administrador, un script de un solo uso: detiene los procesos del usuario en la sesión 0 (vigilantes antes que sus hijos), relanza con la tarea al encender y espera a la API.
  - **Relanzado** a las 02:48:07 UTC en la sesión 0: 25 procesos, 3 recolectores en AboveNormal y el resto en BelowNormal; los 5 cerrojos (vigilantes de la API, líderes, microestructura y HFT, y liquidaciones) tomados, y los de la API y las liquidaciones solo existen con el código nuevo. API `ok` (19 agentes, SIMULADO, operando), interfaz y hoja de ruta escuchando.
  - **Prueba sin duplicados:** la tarea de inicio de sesión, lanzada con todo en marcha, terminó en 8 s (salida 0) con los mismos 26 procesos y sin reabrir ningún registro. El lanzador, ejecutado a mano, da «ya corre: no se lanza otro» en cada servicio; el segundo «equipo despierto» sale por su cerrojo global.
- **Archivos:** `PLAN/{STATUS,ESTADO_PROYECTO,T127,BITACORA}.md`, `v2/docs/OPERACION.md`.
- **Pruebas:** las del PR #180 (gate verde: 2 439 pasadas, 7 omitidas) y las comprobaciones de arriba.
- **Abierto:**
  - **Parar los servicios de la sesión 0 sin elevar:** «Parar servicio» del icono no los alcanza (entregable 5 de T127).
  - Avisos tras el arranque, ninguno del despliegue: dos «sin latido» transitorios (precio en vivo y difusor de la API) y la alerta de protección inconsistente de BTCUSDT, que sale en cada arranque desde el 31-oct.
  - El lanzador avisa de que Ollama no está instalado (`Z:\Ollama`, la unidad Z: no existe): el agente de contexto queda «sin datos».
  - **Racha de T78:** iba en 3 h (23 a 01 UTC); el corte de ~1 min deja incompleta la hora de las 02, así que cuenta de nuevo desde las 03 UTC del 2-nov y se cumple como pronto el 5-nov a las 03 UTC.
- **Siguiente paso:** dejar correr la captura; revisar la racha con `hft_ops --streak`.

## 2026-11-02 03:25 UTC · juanpablo-cpu · T127 registro de consumo (entregable 1)
- **Hecho:**
  - `eim/operation/usage_win.py` lee con `ctypes`, en una llamada de ~4 ms, todos los procesos del equipo (`NtQuerySystemInformation`): padre, sesión, prioridad base, CPU acumulada y RAM privada, sin abrir ninguno. Así se miden también los servicios de la sesión 0. También lee la CPU del equipo, la memoria y los dueños de los puertos.
  - `eim/operation/usage.py` toma una muestra cada 30 s y la escribe en `data/usage/AAAA-MM-DD.jsonl` (~1,7 KB por muestra; los días cerrados se comprimen; 30 días). Cada parte del EIM sale con su papel por su archivo de observabilidad (`obs/spool/<papel>.<día>.<pid>.jsonl`, válido si es posterior al nacimiento del proceso) o por su puerto; los lanzadores del venv (< 4 MB confirmados) y los vigilantes salen por parentesco. Fuera de `data/operation`, porque la copia diaria copia esa carpeta entera mientras retiene el ciclo.
  - `eim/operation/usage_summary.py` resume cada día (CPU media/p95/máx., RAM libre mínima, horas saturadas, gasto por papel y por programa) y lo cruza con las horas incompletas de la captura HFT. Resultado: cuáles coincidieron con el equipo saturado y cuáles no tienen registro. Nueva sección «Consumo del equipo» en el informe semanal.
  - Lo lanza `servicio_continuo.ps1` (cerrojo `data/usage/usage.lock`, nivel `service`); componente `operation.usage` en el catálogo.
  - **Primera medida (03:10 UTC):** equipo al 22 %; el EIM, 14,4 %. De eso, el recolector viejo de microestructura (`collector`, T23) se lleva **11,4 %** del equipo, frente a 1,2 % de la captura HFT y 1,6 % de la API (dato para T128.1).
- **Archivos:** `v2/eim/operation/{usage,usage_win,usage_summary,priority,report,weekly,supervisor}.py`, `v2/eim/observability/catalog/components_flow.py`, `v2/eim/continuity/inventory.py`, `v2/scripts/servicio_continuo.ps1`, `v2/tests/operation/test_usage.py`, `v2/docs/{OPERACION,ALMACENAMIENTO}.md`, `CLAUDE.md`, `PLAN/{STATUS,BITACORA}.md`.
- **Pruebas:** 9 nuevas: atribución sin línea de órdenes, PID reutilizado, CPU como parte del equipo, archivo diario, compresión y poda, resumen cruzado con QC, informe, cerrojo y lectura real de Windows. Además, bucle real de 9 s sobre una carpeta temporal (4 muestras, segunda instancia rechazada con salida 4, coste propio 0,1 % del equipo). Gate verde: 2 448 pasadas, 7 omitidas, 0 fallidas (14 min 41 s en Idle, de 03:18 a 03:33 UTC, con los servicios en marcha: su QC de la hora 03 dirá si estorbó a la captura).
- **Abierto:** desplegarlo no reinicia nada (es un proceso nuevo): basta con lanzar la tarea de inicio de sesión, que solo arranca lo que falta. La sección del informe semanal llega con el próximo reinicio de la API. Siguen pendientes los entregables 2–5 de T127.
- **Siguiente paso:** con permiso, desplegar el registro y, después, la cola de trabajos pesados (entregable 2).

## 2026-11-02 04:10 UTC · juanpablo-cpu · T127 cola de trabajos pesados (entregable 2) y despliegue del registro de consumo
- **Hecho:**
  - **Despliegue del registro de consumo** (PR #182, con permiso del usuario): fusionado y lanzado a las 03:38 UTC con la tarea de inicio de sesión. Esa tarea solo arrancó el muestreador (dos procesos, sesión 1, BelowNormal), sin tocar nada más. Escribe en `data/usage/` cada 30 s con los 11 papeles reconocidos; sus registros de errores están vacíos.
  - **El gate en Idle no estorba a la captura:** el del PR #182 (03:18–03:33 UTC) no dejó ni un hueco ni un descarte en la captura HFT; la cola llegó como mucho a 645 mensajes. El QC de la hora 03 lo confirma: completa, libro usable 100 %, sin huecos, 12/12 verificaciones, con el gate y el despliegue del registro dentro.
  - **Corrección:** la hora 02 UTC del 2-nov salió completa en el QC. El corte del despliegue del PR #180 duró menos de 36 s, dentro del 99 % de cobertura por hora (`qc.COVERAGE_MIN`). La entrada de las 02:55 decía que la rompía. La racha de T78 sigue desde las 23 UTC del 1-nov (5 h con la hora 03) y se cumple como pronto al cerrar la hora 22 UTC del 4-nov.
  - **Cola de trabajos pesados:** `python -m eim.operation.jobs submit --name N -- <orden>` (`eim/operation/jobs{,_store,_proc}.py`). Un ejecutor (cerrojo `data/jobs/runner.lock`) corre un trabajo a la vez: lo hace quien encola si no hay otro, y el siguiente que espera toma el relevo si aquel muere. Se admite con RAM libre ≥ 2 GB, CPU ≤ 80 % y la captura sin presión. Se pausa con todo su árbol (`NtSuspendProcess` sobre cada proceso de un objeto de Windows) si la cola de la captura pasa de 1 000, la escritura se atrasa más de 200, hay huecos o descartes nuevos, la captura se reinicia o la RAM libre baja de 1 GB. Se reanuda tras 90 s sin presión, o a los 15 min si la presión no viene de él. El objeto mata el trabajo si el ejecutor muere (`KILL_ON_JOB_CLOSE`), así que nada queda congelado ni huérfano. Arranca en IDLE, suspendido hasta entrar en el objeto. Registro en `data/jobs/log/`, salida en `data/jobs/out/`, 14 días.
- **Archivos:** `v2/eim/operation/{jobs,jobs_store,jobs_proc}.py`, `v2/tests/operation/test_jobs.py`, `v2/eim/continuity/inventory.py`, `v2/docs/{OPERACION,ALMACENAMIENTO}.md`, `CLAUDE.md`, `PLAN/{STATUS,ESTADO_PROYECTO,BITACORA}.md`.
- **Pruebas:** 8 nuevas, que pasaron tres veces seguidas. Cubren la presión según el latido, la pausa real de un trabajo con CPU (el contador se congela) y su reanudación sola, la espera sin margen con cancelación, cancelar uno en marcha, los restos de un ejecutor muerto, el código de salida, el relevo de un segundo `submit` y el árbol en IDLE. Gate **por la propia cola** contra los datos reales: admitido al instante, 2 458 pasadas, 7 omitidas, 0 fallidas, 850 s y 0 pausas (la captura no sufrió). Tras endurecer la lectura del estado (Windows niega leer o reemplazar el JSON mientras el otro lado lo usa: reintentos breves en `Store.save` y `Store.get`), un segundo gate por la cola dio lo mismo en 790 s.
- **Abierto:** entregables 3 (puntos de control de la copia externa), 4 (copia externa por la cola) y 5 (parar los servicios sin elevar).
- **Siguiente paso:** puntos de control de la copia externa.

## 2026-11-02 05:00 UTC · juanpablo-cpu · T127 copia externa reanudable y por la cola (entregables 3 y 4)
- **Hecho:**
  - **Puntos de control de la subida** (`eim/continuity/offsite.py`): antes, cada reintento volvía a comprimir y subía todas las partes de 256 MB, porque los extras cambian entre intentos. Ahora, con `work`, el empaquetado queda en `backups/.continuity/pack-<equipo>__<copia>/` con `pack.json` (partes, SHA-256 y cuáles subieron). El intento siguiente lo reutiliza, salta las partes ya subidas que siguen en GitHub con su tamaño y sube el resto y el `meta` al final; luego borra la carpeta. Los extras quedan los del primer intento. Cada parte se reintenta 3 veces (espera de 20 y 60 s), porque la pausa de la cola puede cortar una conexión. Se borran los empaquetados de copias anteriores del mismo equipo y los temporales de antes. Sin `work`, el comportamiento no cambia. `publish` anota «(retomada: N ya subidas)». Alcance: solo se retoma la misma copia; si la pasada siguiente llega tras la copia diaria de las 00:00 UTC, elige la nueva y la sube entera. El beneficio está en repetir el mismo día y en los reintentos por parte.
  - **Por la cola** (`scripts/copia_externa.ps1`): la lanza con `python -m eim.operation.jobs submit --name copia_externa -- … publish`, así que espera margen, corre en IDLE y se pausa si la captura sufre; `-SinCola` la lanza como antes. La tarea de Windows no cambia. Si la tarea la corta a las 3 h, Windows mata el trabajo con el ejecutor (objeto de la cola) y la pasada siguiente retoma.
  - No se probó lanzando el script real: con otra carpeta de datos, `publish` sigue usando `backups/` y subiría la copia de hoy a GitHub. Se comprobó en PowerShell la orden que compone y cómo la entiende la cola.
- **Archivos:** `v2/eim/continuity/{offsite,publish}.py`, `v2/scripts/copia_externa.ps1`, `v2/tests/continuity/test_offsite_resume.py`, `v2/docs/{CONTINUIDAD,OPERACION}.md`, `PLAN/{STATUS,BITACORA}.md`.
- **Pruebas:** 6 nuevas, todas sin red:
  - un corte tras 2 partes retoma sin repetirlas;
  - una parte que falla una vez se reintenta en la misma pasada;
  - los extras del primer intento se conservan;
  - una parte perdida en remoto o un empaquetado dañado se suben de nuevo;
  - se limpian los restos de copias anteriores;
  - `publish` dice «retomada».
  La suite de continuidad pasa entera (34). Gate por la cola: 2 464 pasadas, 7 omitidas, 0 fallidas (850 s, 0 pausas).
- **Abierto:** entregable 5 (parar los servicios sin elevar: necesita que el usuario registre una tarea desde una consola de administrador). La próxima copia externa diaria (20:30 hora local) será la primera por la cola: revisar `data/operation/logs/copia_externa.log` y `python -m eim.operation.jobs list`.
- **Siguiente paso:** entregable 5.

## 2026-11-02 05:45 UTC · juanpablo-cpu · T127 parar los servicios sin elevar (entregable 5)
- **Hecho:**
  - **Causa confirmada:** desde la sesión del usuario, `OpenProcess` sobre un servicio de la sesión 0 da error 5 incluso solo para consultar (`PROCESS_QUERY_LIMITED_INFORMATION`) o leer sus permisos. Los procesos de la sesión del usuario tienen `D:(A;;0x1fffff;;;<usuario>)(…;BA)(…;SY)`. Los que lanza la tarea S4U nacen con una lista sin el usuario, aunque corren con su misma cuenta. Por eso ni el lanzador ve su línea de órdenes ni «Parar servicio» los para.
  - **Arreglo:** `eim/operation/proc_access.py`. Cada servicio Python, al arrancar con `EIM_PRIORITY=on` (`priority.apply_role`, que ya llaman todos), añade a su propia lista un permiso para su usuario: terminar, consultar, leer su memoria (para la línea de órdenes por WMI), pausar, esperar y leer sus permisos. No incluye escribir en su memoria ni crear hilos. Es lo que ya tiene cualquier programa de la sesión del usuario. Sustituye a la tarea S4U elevada que proponía T127.md, porque una tarea con privilegios que ejecuta un script editable por el usuario sería una puerta para saltarse el UAC.
  - `scripts/detener_servicio.ps1`: para primero los vigilantes y, 2 s después, los servicios, en cualquier sesión. Sin `-Todo` hace lo mismo que el icono (operación, líderes, interfaz, «equipo despierto»); con `-Todo`, también la captura, el registro de consumo y la hoja de ruta. Al final lista lo que en otra sesión no se deja ver. «Parar servicio» del icono lo usa en vez de su bucle sin orden.
- **Archivos:** `v2/eim/operation/{proc_access,priority}.py`, `v2/scripts/{detener_servicio,icono_bandeja}.ps1`, `v2/tests/operation/test_proc_access.py`, `v2/docs/OPERACION.md`, `PLAN/{STATUS,ESTADO_PROYECTO,T127,BITACORA}.md`.
- **Pruebas:** 3 nuevas, que pasaron 3 veces:
  - **Servicio de la sesión 0 emulado** (lista de permisos solo con SYSTEM):
    - antes es inaccesible y WMI devuelve su línea de órdenes vacía;
    - tras `apply_role` se puede consultar, pausar, leer y terminar, y WMI ve su línea de órdenes;
    - sigue sin poder escribirse ni crearle hilos.
  - Sin `EIM_PRIORITY` no cambia nada.
  - El script para primero el vigilante y luego la API; la captura sigue hasta `-Todo`. `-SoloCon` evita tocar los servicios reales. Gate por la cola: el primero falló solo en `test_emit::test_cycle_overhead_within_budget_even_if_disk_fails`, una prueba de tiempos (68 ms frente a 50 ms con el equipo al 40–75 %, según el registro de consumo). No toca este cambio: aislada pasa 5/5, con y sin él (BACKLOG T127 (1)). El segundo, verde: 2 465 pasadas, 7 omitidas, 0 fallidas (855 s, 0 pausas).
- **Abierto:** ◆ desplegar: hay que reiniciar los servicios, que hoy corren en la sesión 0 con el código anterior, y por tanto parar la captura. Se hará cuando se cumpla T78, como pronto al cerrar la hora 22 UTC del 4-nov; hasta entonces, para pararlos sigue haciendo falta un PowerShell de administrador. Queda la aceptación de T127: una semana del registro de consumo en el informe semanal.
- **Siguiente paso:** tras T78, reiniciar los servicios y comprobar que `detener_servicio.ps1` los para sin elevar.

## 2026-11-02 07:30 UTC · juanpablo-cpu · T128 un recolector por fuente (entregable 1)
- **Hecho:**
  - **Diagnóstico:** el recolector T23 (`binance_ws`) abría dos conexiones más a Binance para BTCUSDT. Llevaba su propio libro (la misma clase `LocalBook` que la captura HFT) y guardaba cada nivel de cada diff como una fila. El registro de consumo le mide ~11 % de la CPU del equipo, frente al ~1 % de la captura. El agente solo necesita los trades, una foto top-10 por segundo y los huecos.
  - **Feed** (`eim/data/collectors/micro_feed.py`): `HftCapture` llama a `on_book` tras cada diff aplicado y al completar una sincronía, como hacía T23 con el primer diff tras el snapshot. El feed guarda en memoria la foto top-10 de cada segundo, y `hft_ws` la vuelca a `data/micro/top` en un hilo desde su latido, así la cola de la captura nunca espera. También escribe `data/micro/heartbeat.json` para `/v2/micro/status`. Un fallo del feed solo cuenta `errores_feed`. **Un solo escritor:** el feed toma el cerrojo de T23 (`micro/collector.lock`). Si la captura se reiniciara con este código antes del despliegue coordinado, mientras T23 siga vivo el feed no escribe nada (dos libros distintos en `micro/top` estropearían el OFI) y lo reintenta en cada latido. Con el feed activo, T23 no puede arrancar.
  - **Lector** (`eim/data/micro.py`): trades de `micro_hft` (un trade repetido tras reconectar cuenta una vez) o de `micro` si no hay captura en la ventana. Huecos de ambas fuentes; de la captura, los tramos de `depth`/`trades` salvo silencios, que dejan incompletas todas las velas que tocan.
  - **Lanzador:** ya no arranca el recolector T23 para BTCUSDT. El módulo sigue para otros símbolos y para validar. Catálogo: `data.micro_collector` sale de la captura.
- **Archivos:** `v2/eim/data/collectors/{micro_feed,hft_capture,hft_ws}.py`, `v2/eim/data/micro.py`, `v2/scripts/servicio_continuo.ps1`, `v2/eim/observability/catalog/components_flow.py`, `v2/eim/continuity/inventory.py`, `v2/tests/data/test_micro_feed.py`, `v2/docs/{OPERACION,ALMACENAMIENTO}.md`, `PLAN/{STATUS,BITACORA}.md`.
- **Pruebas:** 6 nuevas.
  - Los mismos mensajes de Binance (20 min, 1 diff y 1 trade por segundo, con y sin un diff perdido y su resincronía) por el recolector T23 y por la captura con el feed dan **las mismas velas**: OFI, desequilibrio, trades y velas completas. Volúmenes y delta coinciden salvo el último decimal (orden de suma de DuckDB), y el último libro es el mismo.
  - La vela del arranque queda incompleta: no hay libro hasta el primer snapshot.
  - Un trade repetido cuenta una vez.
  - Una desconexión larga deja incompletas todas sus velas, y un silencio ninguna.
  - Un fallo del feed no para la captura.
  - Mientras un T23 siga vivo, el feed no escribe nada; cuando T23 se detiene, toma el relevo.
  Pasan también las de recolector, captura y `hft_ws`. Gate por la cola: el primero falló solo en una prueba de tiempos de la API de observabilidad (p95 120 ms > 100 ms con el equipo cargado; aislada 3/3, BACKLOG T127 (1)). El segundo, verde: 2 470 pasadas, 7 omitidas, 0 fallidas. Con el cerrojo de un solo escritor (y su prueba), otro gate verde: 2 471 pasadas, 7 omitidas, 0 fallidas.
- **Abierto:** ◆ desplegar cuando se cumpla T78: reinicia la captura, y el corte cabe en el 99 % de cobertura por hora. Validar unas horas comparando con el recolector T23 lanzado a mano en otra carpeta. Faltan los entregables 2–5; el 2 y el 5 esperan la decisión de la puerta: qué historial de líderes se conserva y qué restos de `data/` se borran.
- **Siguiente paso:** entregable 3 (ganchos fuera del bucle de la API) o 4 (menos ruido), que no tocan la captura.

## 2026-11-02 16:27 UTC · juanpablo-cpu · T128 ganchos del bróker fuera de su ciclo (entregable 3)
- **Medido:**
  - En el observatorio, el bróker late cada ~62 s (mediana). Al cierre de cada vela de 4 h calla de 90 a 230 s, porque su ciclo esperaba a los ganchos.
  - Sobre una copia de las bases de la copia diaria (por la cola, en IDLE): la validación tarda 2,1 s, la puntuación de bots 2,3 s y los setups 0,3 s. Lo caro es la vista del bróker, que los ganchos rehacen cuando hay contextos nuevos: 37 s (29 s de CPU). La validación la pide cada 4 h, el libro fijo cada hora y los setups, en un hilo aparte, cada 15 min.
  - Un proceso aparte no sirve: DuckDB no deja abrir `paper.duckdb` ni `reports.duckdb` desde otro proceso mientras la API los tiene abiertos.
- **Hecho:**
  - `eim/paper/hooks.py` (`HookRunner`): el ciclo del bróker solo avisa (`kick`) y sigue. Los ganchos corren en orden en su propio hilo. Si llega un aviso durante una pasada, queda una más pendiente, nunca una cola. Un gancho que falla no tumba a los demás y avisa como `paper.hooks`, como mucho cada 15 min.
  - **Latido:** `paper.hooks` late tras cada pasada (muestreado a ~4 min) con lo que tardó cada gancho. La validación y la puntuación laten con su propio componente cuando recalculan (`maybe_run` devuelve True si lo hizo sin error). Estado en `/v2/paper` → `live.hooks`.
  - **Nivel batch dentro de la API:** `priority.lower_thread` baja el hilo de los ganchos y el que rehace la vista a THREAD_PRIORITY_LOWEST. En el proceso BELOW_NORMAL quedan a 4, a la par de los trabajos IDLE y por debajo del resto de la API. Solo con `EIM_PRIORITY` activo.
  - **Catálogo:** `paper.broker` vuelve a «cada 60 s» (cadencia 120 s, aviso a los 6 min). Nuevo `paper.hooks` (300 s). `validation.gate` pasa a cada cierre de 4 h.
- **Archivos:** `v2/eim/paper/{hooks,service,desk}.py`, `v2/eim/operation/priority.py`, `v2/eim/api/main.py`, `v2/eim/validation/service.py`, `v2/eim/bots/scorer.py`, `v2/eim/observability/catalog/components_flow.py`, `v2/tests/paper/test_hooks.py`, `v2/tests/api/test_paper_api.py`, `v2/tests/observability/test_obs_alerts.py`, `v2/docs/OPERACION.md`, `PLAN/{STATUS,BITACORA}.md`.
- **Pruebas:** 6 nuevas.
  - Una pasada corre todos los ganchos en orden y uno que falla no para al resto.
  - Los avisos durante una pasada dejan una sola pasada más.
  - El bróker sigue su ciclo mientras un gancho lento corre.
  - Los ganchos corren a nivel batch y solo su hilo baja.
  - `lower_thread` necesita `EIM_PRIORITY`.
  - En la API, los cuatro ganchos se registran en orden y corren sin errores.
  Se ajusta la prueba de silencio del bróker (T126). Gate en el PR.
- **Abierto:** ◆ entra con el reinicio de la API tras T78 (no toca la captura). Después, comprobar en el observatorio que el bróker late cada minuto también al cierre de 4 h y cuánto tarda cada gancho. Faltan los entregables 2, 4 y 5.
- **Siguiente paso:** entregable 4 (menos ruido y menos gasto).

## 2026-11-02 17:09 UTC · juanpablo-cpu · T128 menos ruido y menos gasto (entregable 4)
- **Medido:**
  - **Ollama:** `EIM_OLLAMA_EXE` apunta a `Z:\Ollama\ollama.exe`, una unidad de red (`\\DESKTOP-TVD562Q\USB`) que la tarea al encender (sesión 0) no ve. El lanzador no arranca Ollama y Contexto queda «sin datos» sin aviso. Hay una copia local en `C:\eim-localai\ollama\ollama.exe` (T62); cambiar la variable es decisión del usuario, porque gasta RAM.
  - **Interfaz:** el registro de consumo da a Vite (`web`, sesión 0) 0,001 % de CPU de media (máx. 0,69 %) y ~170 MB de memoria reservada, casi toda fuera de la RAM. Servirla compilada ahorraría ~150 MB a cambio de recompilar con cada cambio: no se hace.
  - **Arbitraje:** el escáner toma una foto cada ~11 s, de 47 KB cada una (~400 MB de escritura al día), aunque aquí no hay ejecución.
  - **Vigilancia con cliente:** el canal en vivo del Hub solo nace cuando la interfaz se suscribe y ya no se cierra.
- **Hecho:**
  - `local_context.ollama_problem`: el motivo, con la comprobación de la ruta acotada a 2 s (una unidad de red caída tarda minutos). `obs_alerts.llm_conditions` lo convierte en el aviso «LLM local no disponible», que el supervisor añade a sus alertas, como mucho una comprobación cada 10 min. El registro pasa el motivo al agente Contexto (`unavailable`). El lanzador escribe un `Write-Warning`.
  - `obs_conditions(started_ms=…)`: `data.live_ticks` y `api.hub` (`CON_CLIENTE`) no se vigilan hasta su primer evento en este arranque.
  - `Settings`: escáner de arbitraje cada 60 s, o cada 10 s con `EIM_ARB_EXECUTION=testnet`. La alerta de oportunidad sigue pidiendo 60 s seguidos. El agente de arbitraje, que no vota, verá fotos de hasta un minuto con menos confianza. Catálogo ajustado.
- **Archivos:** `v2/eim/data/providers/local_context.py`, `v2/eim/agents/context/agent.py`, `v2/eim/agents/registry.py`, `v2/eim/observability/obs_alerts.py`, `v2/eim/operation/supervisor.py`, `v2/eim/api/config.py`, `v2/eim/observability/catalog/components_flow.py`, `v2/scripts/servicio_continuo.ps1`, `v2/tests/operation/test_t128_ruido.py`, `v2/docs/OPERACION.md`, `PLAN/{STATUS,BITACORA}.md`.
- **Pruebas:** 6 nuevas.
  - El motivo solo sale si la variable está puesta y la ruta falta; una unidad que no contesta no cuelga la comprobación.
  - El aviso se enciende, se apaga y comprueba como mucho cada 10 min.
  - Contexto dice por qué no tiene LLM.
  - Precio en vivo y Difusor no avisan hasta que alguien se conecta, y sí después.
  - El escáner va cada minuto salvo con ejecución.
  Gate en el PR.
- **Decidido (el usuario lo delegó, opción recomendada):** se quitó la variable de usuario `EIM_OLLAMA_EXE` (era `Z:\Ollama\ollama.exe`). La copia local cargaría un modelo de ~3,5 GB con la RAM libre bajando a 2,5 GB durante T78, y Contexto no vota (sesgo 0). `E:\Ollama\ollama.exe`, la ruta por defecto, no existe: el lanzador no arranca Ollama y no hay aviso. Los servicios en marcha conservan la variable hasta su reinicio. Para activar Contexto con LLM tras T78: `EIM_OLLAMA_EXE=C:\eim-localai\ollama\ollama.exe`, midiendo la RAM.
- **Abierto:** ◆ entra con el reinicio de la API tras T78. Faltan los entregables 2 y 5: esperan la decisión de la puerta (qué historial de líderes se conserva y qué restos de `data/` se borran).
- **Siguiente paso:** la decisión de la puerta para los entregables 2 y 5.

## 2026-11-02 18:40 UTC · juanpablo-cpu · T128 base de líderes, primera parte (entregables 2 y 5)
- **Medido** (copias de la noche, sin tocar la base viva):
  - **Espacio:** `leaders.duckdb` pesa 2,1 GB con 1,34 GB en uso, y ~0,75 GB son bloques libres que DuckDB no devuelve al disco. De lo usado, ~450 MB son datos y ~890 MB índices de las claves primarias.
  - **Crecimiento real:** ~110 MB por día en marcha, no 300.
  - **Quién lo llena:** el 85 % de las ejecuciones (2,67 M de 3,13 M) es de un líder rechazado de alta frecuencia (~50 ejecuciones por operación cerrada). 16 de los 17 líderes capturados están rechazados: son el grupo de control de T41.
  - **Resincronías:** dos líderes rechazados ejecutan órdenes TWAP sin parar (278 y 597 porciones en una hora; API pública, 2026-11-02). `userFills` no las trae, así que su libro nunca cuadraba y se resincronizaba en cada reconciliación.
- **Decisión del usuario:** los rechazados conservan 7 días de detalle. Al leer la evaluación se vio que un resumen por día cambiaría los veredictos (Sharpe por operación, deflactado, caída) y que las fotos de posiciones dan los días observados. El usuario aprobó guardar en su lugar las operaciones cerradas y conservar las fotos (PR aparte).
- **Hecho (esta parte):**
  - `eim/data/duck_compact.py`: compacta una base que nadie tiene abierta si más del 30 % está libre, con la misma copia que la diaria. Comprueba las filas tabla a tabla y luego cambia un archivo por otro (`.old` si se corta). El vigilante de líderes la llama al arrancar, en lote, antes de lanzar `run`. Medido sobre una copia de 1,34 GB: 76 s.
  - **TWAP:** suscripción WS `userTwapSliceFills` junto a `userFills` (mismos usuarios, dentro del límite de 10 por IP). REST `userTwapSliceFillsByTime` paginado en cada relleno, arranque, sondeo y reconciliación (`parse.twap_fills`).
  - **Entregable 5:** con el visto bueno del usuario, a la Papelera (recuperable): la carpeta vacía `leaders.duckdb.tmp`, cerrojos, latido y registros de ETHUSDT (~450 KB) y `ollama.*.log`.
- **Archivos:** `v2/eim/data/duck_compact.py`, `v2/eim/leaders/{cli,parse}.py`, `v2/eim/data/leader_watch.py`, `v2/eim/data/providers/leaders.py`, `v2/tests/data/{test_duck_compact,test_leader_twap,test_leader_watch}.py`, `v2/tests/leaders/helpers.py`, `v2/docs/OPERACION.md`, `PLAN/{STATUS,BITACORA}.md`.
- **Pruebas:** 7 nuevas.
  - **Compactado:** conserva filas y claves, y después no hay nada que hacer; deja en paz las bases pequeñas; una copia que no cuadra deja el original; un cambio cortado se deshace.
  - **TWAP:** sus porciones por REST cuadran el libro sin resincronizar; las del WS se guardan como `ws`; el REST desenvuelve y pagina.
  Gate en el PR.
- **Abierto:** ◆ entra con el reinicio tras T78: el primer arranque compacta (2,1 → ~1,35 GB, ~1–2 min sin captura de líderes; al arrancar se rellena el último día). Falta la retención por operaciones cerradas.
- **Siguiente paso:** retención por operaciones cerradas, comprobando sobre una copia que los veredictos no cambian.

## 2026-11-02 20:45 UTC · juanpablo-cpu · T128 base de líderes, segunda parte: retención de los rechazados (entregable 2)
- **Hecho:**
  - **Archivo plegado** (`eim/copytrading/trip_archive.py`, puro): por moneda, el corte es el último instante ≤ ahora − 7 d tras el que la posición quedó plana y sin cotizaciones pendientes. Lo anterior se guarda como `SymbolBase`: los viajes con su seguidor (`TripFollow`), el histograma de latencias en vivo (milisegundos enteros: no pierde nada), las tomadoras y el número de ejecuciones. `LeaderFold.restore` arranca de ahí y `rebuild` vuelve a ese punto, no a cero.
  - **Tablas** `leader_archive` y `leader_archive_trips` (`eim/data/leader_archive.py`): columnas y JSON con versión, sin pickle. Los deslizamientos de cada viaje van en una lista de DOUBLE. No viajan en T61.
  - **Poda** (`eim/data/leader_prune.py`): solo líderes `rejected`. Por moneda y en lotes de 200 000 ejecuciones, archiva y borra (`leader_fills` y las cotizaciones de esas ejecuciones en `leader_follow`) en una sola transacción; al final de cada líder, una pasada borra su procedencia T61 huérfana en `share_origin` (lote a lote costaba 314 s en vez de 92). Funding, fotos de posiciones, reconciliaciones y huecos se conservan enteros. Corre en el servicio una vez al día (la primera, 30 min tras arrancar), en `supervise` antes del compactado y con `python -m eim.leaders prune [--days 7]` (servicio apagado; poda y compacta).
  - **Evaluación** (`leader_fold_io.py`): rehacer carga el archivo y lee solo lo posterior a cada corte; el control de ejecuciones suma lo archivado; cada poda cambia la `generation` y el líder se rehace. Una ejecución anterior al corte que reaparezca (unión T61) se ignora y la poda siguiente la borra.
  - **Otros lectores:** `copy-sim` (T42) de un rechazado empieza en la primera foto posterior a su último corte y lo avisa. `history`, `gather`, `fills_fast` documentan que solo ven lo no podado. `report`, la copia en vivo y el arranque del vigilante solo leen lo reciente.
- **Medido** (copias de `backups/eim_20261102-000037/leaders.duckdb`, nunca la base viva, por la cola; 17 líderes capturados, 16 rechazados):
  - **Mismas cifras:** con 7 días y con un corte artificial de 1 día, el tablero entero sale idéntico bit a bit antes de podar, después y tras compactar: veredictos, razones y cifras (`all`, `hist`, `fwd`, `copyability`) de los 17.
  - **7 días:** 7 líderes podados; 590 617 ejecuciones (571 649 del de alta frecuencia), 510 237 cotizaciones y 1,09 M claves de `share_origin` fuera; 15 936 viajes archivados (4 MB). Compactada, de 1 343 a 1 161 MB. Durante la poda el archivo crece a ~1,8 GB (bloques libres que el compactado devuelve). Poda 139 s (92 s sin limpiar `share_origin`; 314 s limpiándola lote a lote, descartado); compactado 65 s.
  - **1 día:** 10 líderes, 1,30 M ejecuciones, 27 800 viajes; 937 MB compactada.
  - **Dónde está el espacio:** ~450 MB son datos; el resto, índices de claves primarias. La tabla más grande es `share_origin` (5,16 M claves de texto de la unión T61, hoy apagada): por eso la poda borra también su procedencia huérfana.
  - **Lo que sigue creciendo:** todas las ejecuciones recientes son de rechazados (el líder en `watch` no opera). Sin poda quedan las fotos de posiciones (~0,7 KB por foto en disco, 1 000–8 000 fotos al día), reconciliaciones, huecos y la bitácora de la copia: unos pocos MB al día frente a ~110.
- **Archivos:** `v2/eim/copytrading/{trip_archive,trip_fold}.py`, `v2/eim/data/{leader_archive,leader_prune,leader_fold_io,leader_service,leader_store,leader_eval,leader_score_store,copy_replay,share_spec}.py`, `v2/eim/leaders/cli.py`, `v2/tests/copytrading/test_trip_archive.py`, `v2/tests/data/test_leader_prune.py`, `v2/docs/{OPERACION,ALMACENAMIENTO}.md`, `PLAN/{STATUS,BITACORA}.md`.
- **Pruebas:** 13 nuevas.
  - **Puras:** arrancar del archivo da lo mismo que `build_trips` + `copy_stats` sobre todo el historial, en cinco cortes; por lotes se llega al mismo archivo que de una vez; solo se corta con la posición plana y todo definitivo; las cuentas cuadran con el plegado.
  - **Con la base:** evaluación vuelta a vuelta con poda «diaria» igual a releer todo el historial (y el tablero entero); solo se podan rechazados; con lo podado se va su procedencia en `share_origin` y nada más; una ejecución podada que vuelve se ignora y se vuelve a podar; se archivan todos los campos de `Trip` y otros parámetros avisan; el servicio poda y deja la siguiente para mañana; `supervise` poda antes de compactar y un fallo no le impide arrancar; la CLI poda y compacta; `copy-sim` empieza tras el corte.
  Gate en el PR.
- **Abierto:** ◆ entra con el reinicio tras T78: el vigilante poda y compacta antes de lanzar `run`. Medir una semana que `leaders.duckdb` deja de crecer (aceptación de T128).
- **Siguiente paso:** desplegar los entregables 1–4 con el reinicio tras T78.

## 2026-11-02 21:20 UTC · juanpablo-cpu · T116 gate estable con la cola en IDLE
- **Problema:** desde T127 el gate corre en IDLE. Con el equipo cargado fallaba a veces en
  pruebas de tiempo de reloj que aisladas pasan (`test_emit`, `test_obs_api`; con Ollama además
  latidos, `test_paper_api` y dos procesos). Cada fallo costaba repetir 16 min de gate.
- **Hecho:**
  - **Prioridad:** las pruebas `perf` suben el proceso a NORMAL mientras corren (autouse en
    `tests/conftest.py`, `tests/perf.py::normal_priority`), por debajo de la captura (ABOVE_NORMAL).
  - **Medición:** `measure` entrega la ronda de p95 mediano de 3.
  - **Esperas:** las pruebas con plazos fijos cortos (latidos 0,15–1,4 s, vista del bróker, backtest
    30 s, dos procesos 60 s) esperan hasta que se cumple, con tope amplio.
  - Mismos umbrales (`thresholds.py` intacto), ninguna prueba saltada ni borrada.
- **Medido:** con 3 procesos ocupando CPU en BELOW_NORMAL y las pruebas en IDLE, `main` falla
  `test_obs_api` (p95 189 ms, p99 1 742 ms) y la rama pasa 3 de 3 (147–425 s). La captura (ABOVE_NORMAL)
  no se ve afectada por esa carga.
- **Archivos:** `v2/tests/{perf,conftest}.py`, `v2/tests/observability/{test_emit,test_service_heartbeats}.py`,
  `v2/tests/api/test_paper_api.py`, `v2/tests/hft/test_hft_risk.py`, `v2/docs/RETOMAR_COLABORADOR.md`,
  `PLAN/notas/T116_gate.md`, `PLAN/{STATUS,BACKLOG,BITACORA}.md`.
- **Abierto:** gates completos seguidos por la cola (en el PR). Las 3 corridas con el equipo
  descargado necesitan parar los servicios: tras T78.
- **Siguiente paso:** con el PR fusionado, los gates por la cola dejan de fallar por la carga.
- **Tres gates por la cola:** 1.º y 2.º verdes (2 503 pasadas, 950 y 895 s). El 3.º falló en
  `test_proc_access` porque la cola lo pausó dos veces (185 s congelado cada una, por silencios
  de red en la captura) y el plazo de 120 s de un PowerShell caducó durante la pausa. Arreglo:
  `jobs submit --retry-paused N` repite el trabajo que falla tras una pausa; el gate va con 1
  (`CLAUDE.md`, `docs/OPERACION.md`). Prueba nueva en `tests/operation/test_jobs.py`.

## 2026-11-02 23:20 UTC · juanpablo-cpu · Despliegue de #185–#191 y racha de T78 rota
- **Racha de T78:** llegó a 23 h (2026-11-01T23 → 02T21) y se rompió en la hora 02T22. Entre
  22:04 y 22:10 UTC hubo 19 silencios de 3–8 s en todos los flujos a la vez y una desconexión:
  libro útil 98,2 % y precio de marca 98,5 %, por debajo del 99 %.
  - Apunta a la red: la captura tuvo su CPU de siempre (~4 %), varios silencios ocurrieron con el
    gate ya congelado por la cola, y la conexión de liquidaciones de OKX también cayó a las 22:07.
  - La hora 21, con carga sintética de T116 en BELOW_NORMAL, quedó completa (libro útil 100 %).
- **Despliegue:** con la racha en cero, el usuario aprobó desplegar ya en vez de esperar tres
  días. Lo hizo con un PowerShell de administrador (`desplegar_t128.ps1`, fuera del repo): los
  servicios de la sesión 0 se pararon a las 23:12:50 y se relanzaron con la tarea al encender.
  Comprobado:
  - **API:** responde, con 19 agentes y la operación en marcha.
  - **Captura HFT:** volvió a las 23:13:39 (49 s de corte, así que la hora 23 queda incompleta).
    La microestructura sale de ella (`micro/heartbeat.json` con `source: hft_ws`, 87 fotos en el
    primer minuto) y el recolector T23 ya no se lanza (#186).
  - **Bróker:** los ganchos corren en su hilo y laten como `paper.hooks`; primera pasada de 38 s,
    34 de ellos la validación (#187).
  - **Arbitraje:** el escáner toma una foto cada 61 s (#188).
  - **Líderes:** el vigilante podó 7 rechazados y compactó `leaders.duckdb` de 2 151 a 1 267 MB
    en 77 s; el servicio volvió a latir a las 23:17:46 (#189, #190).
  - **Permisos:** desde la sesión del usuario, sin elevar, ya hay permiso de consulta y de
    detención sobre los procesos del EIM (#185); se comprobó el permiso sin parar ninguno.
  - **Prioridades:** captura y liquidaciones en ABOVE_NORMAL; API y vigilantes en BELOW_NORMAL.
- **Aviso que ya existía:** «Protección en estado inconsistente: agresivo BTCUSDT» (la operación
  del 31-oct de `agente_levels`; el recálculo la cerraría antes del estado guardado). Sale en cada
  arranque de la API desde el 2026-11-01; no viene de este despliegue. Resolverlo es decisión del
  usuario.
- **Abierto:**
  - T78 se cumple como pronto al cerrar la hora 23 UTC del 2026-11-05.
  - Validar unas horas la microestructura con el recolector viejo en otra carpeta.
  - Medir una semana el tamaño de `leaders.duckdb`.
  - T116: tres corridas con el equipo descargado.

## 2026-11-03 06:30 UTC · juanpablo-cpu · Operación inconsistente resuelta y T129 (stop dinámico, solo lectura)
- **Comprobación al volver:** continuidad CON AVISOS (sin bloqueo), servicios latiendo, copias del 2026-11-03 locales y externas. La racha de T78 iba en 5 h (desde 2026-11-03T00). Hay que usar el python del `.venv`: el del sistema no tiene pydantic.
- **Aviso «Protección en estado inconsistente: agresivo BTCUSDT»:** era un corto de `agente_levels@1h` del 31-oct. Se fijó el escalón 2 (SL 77 164,5) a las 03:45 con la regla de 15 m sin velas de 1 m completas; con ellas, el recálculo lo cerraba a las 03:41. Las velas de 1 m y los trades HFT confirman el toque del SL a las 03:40:03 UTC. Con permiso del usuario se reconcilió con `recalculo` (nota en el diario): SLD a 77 164,5 y +0,11 R. El Agresivo deja de tener esa posición fantasma.
- **T129 (encargo del usuario, sin cambios de código):** informe `PLAN/notas/T129_sl_dinamico.md`.
  - **Libro:** 307 cierres, acierto 75,6 %, +0,108 R por ganadora frente a −0,964 R por perdedora (PF 0,35).
  - **Causa:** el stop del escalón queda a menos de un incremento del extremo (27–61 USD de BTC, frente a 29 USD de rango mediano en 1 min).
  - **Además:** costos de 0,12 R/op y entradas sin ventaja antes de costos.
  - **Resto del informe:** hallazgos H1–H10, investigación con fuentes y repositorios verificados (`gh api`), arquitectura propuesta y plan T130–T136 (fase 22) con criterios pre-registrados.
- **Archivos:** `PLAN/notas/T129_sl_dinamico.md`, `PLAN/T129.md`–`PLAN/T136.md`, `PLAN/{STATUS,00_MASTER,BITACORA,ESTADO_PROYECTO}.md`, `PLAN/roadmap.html`. Scripts de lectura fuera del repo (scratchpad de la sesión).
- **Pruebas:** no aplica (solo documentos); ruff y las pruebas que leen `PLAN/`.
- **Abierto:** las ◆ de §6 del informe (reabrir la decisión de T111, cierres parciales, geometría del SL inicial, papel de los agentes, dependencias). La historia desde 2023 no está en este equipo: T131 la reconstruye en una copia.
- **Siguiente paso:** decidir las ◆ y empezar T130.
- **◆ de T129 resueltas (2026-11-03, el usuario pidió «hacer todo lo recomendado»):** la escalera queda como referencia provisional hasta T134, sin cambiar la salida en vivo, y el A/B en vivo sale de la sombra. Cierres parciales y SL con piso solo en el banco; agentes como selectores discretos validados; sin dependencias nuevas salvo statsmodels si T133 lo exige. Modelos añadidos (§7 del informe): stop por tiempo, salida por reversión del marco mayor, SL por cuantil del MAE, estimadores OHLC de volatilidad, cociente de varianzas, vida media de OU y momento de serie temporal.

## 2026-11-03 07:40 UTC · juanpablo-cpu · T130 medición honesta de las salidas
- **Hecho:**
  - MFE/MAE desde el llenado (`eim/paper/excursion.py`), con una sola definición en `engine.simulate` y en `simulate_ladder`.
  - Falso positivo de T110 arreglado (`ladder_floor.early`, `floor_superseded`).
  - Calidad de la salida y A/B en vivo frente a la sombra (`eim/paper/exit_quality.py`, `GET /v2/paper/exits`, `python -m eim.paper salidas`).
  - BE+ inerte documentado (`docs/PPP.md` §2.3 y §14).
- **Vista previa con el libro real (JSON del 2026-11-03):**
  - Agresivo: acierto 76,9 % frente a un 90,3 % de equilibrio; los costos se llevan el 80 % de lo ganado en bruto.
  - Frente a la sombra, la escalera pierde en el Agresivo (Δ −0,10 R, 46 pares) y gana en el Moderado (+0,31, 17 pares) y en el control (+0,18, 14 pares). El periodo es lateral y las muestras pequeñas y dependientes.
- **Archivos:** `v2/eim/paper/{excursion,exit_quality,exit_cli,engine,ladder,ladder_floor,__main__}.py`, `v2/eim/api/paper.py`, `v2/docs/PPP.md`, `v2/tests/paper/test_{t130_measurement,exit_quality}.py`, `v2/tests/api/test_paper_api.py`, `PLAN/{STATUS,BACKLOG,BITACORA}.md`.
- **Pruebas:** ruff limpio; `tests/paper` (331), API del bróker y seguridad verdes; gate completo por la cola (ver PR).
- **Abierto:** panel y despliegue (BACKLOG T130). La API viva sigue con el código anterior hasta fusionar y reiniciar solo la API (con permiso; no toca la captura HFT).
- **Siguiente paso:** T131, banco emparejado con la historia desde 2023 reconstruida en una copia.
## 2026-11-03 16:15 UTC · juanpablo-cpu · Despliegue de T129 y T130 (#194, #197)
- **Antes de desplegar:**
  - Windows se reinició a las 15:56 UTC (no fue el despliegue). La tarea de inicio de sesión relanzó todo a las 15:57, en la sesión 1.
  - La racha de T78 volvió a 0 (iba en 5 h a las 05 UTC).
  - La carpeta principal estaba en la rama de otra sesión, `claude/doc-biblioteca-operacion` (PR #195, subida y sin cambios rastreados). Se devolvió a `main` y se avisó a esa sesión.
- **Despliegue (con permiso del usuario):**
  - #194 y #197 fusionados (`695b2cb`); `git merge --ff-only` en la carpeta principal.
  - Se paró solo el Python real de la API (pid 4656) a las 16:07:53. El vigilante `eim.operation run` (13112) la relanzó en 43 s (pid 3380, BelowNormal); `servicio_iniciado` a las 16:08:31.
  - La captura HFT no se tocó: siguió latiendo.
- **Comprobado:**
  - `GET /v2/paper/exits` responde en modo SIMULADO.
  - `python -m eim.paper salidas` funciona.
  - Diario de protección: 81 cerradas, 0 inconsistentes.
- **A/B en vivo emparejado** (vista 5c4b4251a135, todas las ideas): la escalera **supera** a la salida A de la sombra en los cuatro perfiles en este periodo:

  | Perfil | Pares | Δ | Escalera | Sombra (A) |
  |---|--:|--:|--:|--:|
  | Moderado | 106 | +0,46 R | −0,17 | −0,62 |
  | Agresivo | 147 | +0,15 R | −0,12 | −0,27 |
  | `ppp_btcusdt` | 39 | +0,24 R | — | — |
  | Conservador | 11 | +0,13 R | — | — |

  - Las dos salidas pierden.
  - Cuando A llega al TP, la escalera cobra +0,07…+0,24 R frente a +1,3…+1,4 R. Cuando A pierde por SL, la escalera pierde −0,29…−0,45 R frente a −1,1 R.
  - Coincide con T111 (la escalera gana en lateral y pierde en tendencia): estos 17 días fueron mayormente laterales. Por eso T133 es la pieza clave.
  - La vista previa de antes, con solo 1 000 decisiones, daba Δ −0,10 en el Agresivo: muestra parcial.
- **Abierto:**
  - En `.claude/worktrees/t129-proteccion-falso-positivo` (bloqueado, de otra sesión) hay una «T129» sin confirmar (fase 18) sobre el mismo falso positivo: choca con el número de la T129 de la fase 22 y su arreglo ya está en `main` (T130). Decisión del usuario: descartarla o renombrarla como anexo de T130.
  - Panel de `/v2/paper/exits` (BACKLOG T130 (1)).
- **Siguiente paso:** T131.
## 2026-11-03 16:30 UTC · juanpablo-cpu · Traspaso a otra cuenta de Claude
- El usuario sigue con otra cuenta de Claude en este PC. Traspaso en `PLAN/ESTADO_PROYECTO.md` §0: primeros pasos, estado de git y worktrees a medias, y siguiente tarea (T131, tras integrar `claude/fase22-mejoras-estudio`).
- La «T129» duplicada (fase 18) del worktree `t129-proteccion-falso-positivo` queda superada por T130; su diagnóstico se conservó como `PLAN/notas/T130_anexo_falso_inconsistente.md`, con la causa de raíz (sincronización del 1 m solo en el tick del bróker). Esa carrera queda en BACKLOG T130 (4).
- Se pidió a la sesión «Biblioteca del proyecto» que confirme y suba su trabajo en `claude/fase22-mejoras-estudio` sin fusionar: lo hizo, en el **PR #199** (fusionado en `382d423`). Se quitaron los worktrees fusionados y limpios `wt-t128f` y `wt-t62`.
## 2026-11-03 16:20 UTC · juanpablo-cpu · Fase 22 enriquecida con el estudio de la bibliografía
- **Hecho:** se cruzaron las tareas pendientes de la fase 22 (T131–T136) con tres obras leídas completas en esta sesión: Kelly y Xiu, *Financial Machine Learning*; Sutton y Barto, *Reinforcement Learning*; y Kakushadze, *101 Formulaic Alphas*. Los apuntes con páginas están en `v2/data/library/estudio/`, fuera de git. El informe de T129 ya tenía los métodos; se añadieron 12 mejoras de método (E1–E12) en `PLAN/notas/T129_sl_dinamico.md` §8:
  - purga y embargo entre ajuste y prueba;
  - objetivo de selección pre-registrado;
  - Romano-Wolf además de Holm;
  - estrés de costos ×1,5 y ×2, y calibración del deslizamiento con la captura HFT;
  - MAE de las ganadoras sin fuga ni circularidad (M8, M5);
  - cota del oráculo antes de T133;
  - pruebas múltiples en el régimen;
  - valor económico por encima de la AUC;
  - prueba en papel con potencia calculada;
  - Kelly sobre el límite inferior de E[R];
  - una sola σ para stop y tamaño;
  - freno de drawdown y CVaR dentro de la rejilla, con comprobación del ES.
- **Criterios de §5.4 cambiados antes del pre-registro de T131:**
  - el 1 usa Romano-Wolf (Holm como referencia);
  - el 7 deja «el mismo signo» (una salida sin efecto lo cumple el 50 % de las veces) y pasa a potencia calculada + IC que contiene la estimación de T134;
  - nuevo 8: seguir aprobando con el deslizamiento de los stops ×1,5.
- **Archivos:** `PLAN/notas/T129_sl_dinamico.md` (§5.3, §5.4, §8, fuentes), `PLAN/T131.md`–`PLAN/T136.md`, `PLAN/ESTADO_PROYECTO.md`. Sin cambios de código.
- **Pruebas:** no hay código; solo se regeneró la hoja de ruta.
- **Abierto:** nada nuevo. Sigue descartado el aprendizaje por refuerzo para la salida; el estudio lo confirma (solo se justifica cuando las propias órdenes mueven el precio).
- **Siguiente paso:** T131, ahora con E1–E4 y E12 en su pre-registro.
## 2026-11-03 18:20 UTC · juanpablo-cpu · T131 banco de salidas, pre-registro y historia desde 2023
- **Hecho:**
  - **Banco** `v2/eim/paper/exits/`: interfaz pura `ExitPolicy` + M0 (escalera) y M1 (TP/BE+/tiempo), banco emparejado con tamaño fijo y sin la memoria de los perfiles, métricas de §5.3, pliegues de 12 + 3 meses con purga y embargo (E1), Romano-Wolf con Holm de referencia (E3), PBO por CSCV, objetivo de selección pre-registrado (E2) y estrés de costos ×1,5 y ×2 (E4a).
  - **Pre-registro inmutable** con huella fijada en el código y 107 intentos; confirmado en un commit **anterior** a cualquier resultado. `prereg_t131_v2` corrige la meseta para medirla sobre **la mejora** frente a la base (§5.3 dice «≥ 70 % de la mejora»): con el nivel absoluto no elegía nada, porque todas las variantes pierden. `v1` queda publicada e intacta, como manda el proyecto.
  - **Datos:** historia desde 2023 reconstruida en una COPIA (`v2/backups/t131_banco/`, por la cola de T127, 34 min): 4 h, 1 h, 15 m y 1 m (2 019 972 velas) y 4 209 tasas de funding, **cobertura 100 % y 0 huecos**. Hallazgo que ahorró la parte cara: los **contextos de 1 h ya cubrían 2023-01-11 → hoy** (33 399, llegados con la mezcla de T117), así que no hubo que regenerar ~33 000 contextos (≈ 10 h de CPU).
  - **Regresión con T111:** M0 y M1 **delegan** en `simulate_ladder` y `engine.simulate`, las dos funciones que llamó T111, así que reproducen sus cifras por construcción. Comprobado campo a campo con fixtures (los dos lados, mercado y límite, con y sin costos) y con 500 ideas reales de la copia: 0 diferencias, también con las velas de 1 min cargadas.
- **Primera corrida** (60 720 ideas, 45 814 emparejadas, 29 828 fuera de muestra por variante, 10 pliegues, 18 min; `v2/reports/t131_banco.md`):
  - La escalera queda **confirmada en 3,5 años y fuera de muestra**: acierto 76,1 %, ganadora media +0,127 R, perdedora media −1,048 R, cociente 0,12, PF 0,39. Son las mismas cifras que los 307 cierres del libro real de T129 (75,6 %, +0,108, −0,964, 0,11): no era un artefacto de 17 días laterales.
  - **Las once variantes pierden** (E[R] −0,138 a −0,175 R, costo 0,146 a 0,186 R). El problema está en la entrada, no en la salida (T27/T49/T111).
  - **Nada bate a la salida vigente** tras corregir: la mejor candidata frente a `M0 0.1` es `M0 0.075` con p bruto 0,013 → Romano-Wolf 0,057 y Holm 0,126. Frente a `M1 be=1/0.1`, `M1 be=1.5/0` **pasa Romano-Wolf (0,034) y no Holm (0,064)**: único caso en que discrepan, y E3 obliga a informarlo.
  - **PBO 0,46** frente al 0,2 que pide el pre-registro, con solo las once variantes de M0 y M1; Sharpe deflactado 0,000 en todas. Aviso para T134: el riesgo de adoptar ruido es alto.
  - **Purga y embargo:** 0 fugas en los 10 pliegues. En el primero, de 11 130 operaciones del ajuste se conservan 10 857 (8 purgadas por cerrarse dentro de la prueba, 265 en el embargo de 200 h).
  - **El control aleatorio FALLA** en `M0` con `first_r` 0,075 y 0,1: bruto +0,025 R con IC [+0,004, +0,047] en 2 820 operaciones. Se informa como fallo, sin reinterpretar el criterio. Diagnóstico 2 × 2 (con/sin costos × con/sin velas de 1 min): dos efectos aditivos de ≈ +0,010 R — (a) el motor solo baja al 1 min en las velas **ambiguas** y, con un stop de trinquete, la regla gruesa solo puede sub-proteger, así que la información entra asimétricamente (es el `fine_bias` de T111; el número con 1 min es el correcto); (b) el stop se coloca sobre el **neto** estimado con una reserva conservadora de costos, que infla el bruto pero no el neto. **No hay anticipación:** sobre paseos aleatorios independientes y sin costos, M0 y M1 dan E[R] ≈ 0. Lo que el 1 min aporta sobre datos reales es dependencia serial del BTC, que un paseo aleatorio no tiene. Consecuencia: el nulo del control está mal especificado para salidas dependientes del camino medidas sobre la serie real; hay que cambiarlo a un nulo con la dependencia serial destruida (bloques o fases) **antes** de juzgar las candidatas de T132 → BACKLOG T131 (8).
  - **Estrés de costos:** las once empeoran de forma monótona con ×1,5 y ×2 y ninguna cruza a positivo. El criterio 8 de §5.4 no llega a aplicarse porque ninguna pasa el criterio 1.
- **Archivos:** `v2/eim/paper/exits/{__init__,policy,bench,metrics,stats,walkforward,select,costs,prereg,run,report}.py`, `v2/eim/paper/exits/versions/prereg_t131_v{1,2}.json`, `v2/scripts/{t131_history,t131_bench,t131_t111_diff}.py`, `v2/tests/paper/exits/` (11 archivos), `v2/reports/t131_banco.{json,md}`, `v2/docs/ARQUITECTURA.md`, `PLAN/{STATUS,BACKLOG,BITACORA,ESTADO_PROYECTO}.md`, `PLAN/notas/T131_banco_salidas.md`.
- **Pruebas:** 110 nuevas en `tests/paper/exits/`, sin red, con la que exige la aceptación (ninguna operación del ajuste se cierra dentro de su prueba ni de su embargo) y el control aleatorio sobre paseos independientes. Dos defectos los encontraron las propias pruebas: la regla de meseta elegía la **peor** variante de la rejilla (faltaba exigir que la candidata sea competitiva) y una varianza degenerada daba una t absurda en Romano-Wolf (ahora se informa como saltada). **Gate verde** por la cola: `ruff` limpio y `pytest -q` con ~2 641 pruebas y 0 fallos (33 min, de los que 16 pausado en 2 tramos por RAM libre < 1 GB, reanudando solo).
- **Nada tocado en vivo:** ni `data/`, ni la salida del bróker, ni los servicios. La copia del banco vive en `v2/backups/t131_banco/` (no versionada, reconstruible).
- **Efecto real sobre la captura HFT de T78, hora a hora (UTC del 2026-11-03):** 16 (banco sin velas finas) **completa**, libro 1,0000; 17 (descarga del 1 m, 1 347 peticiones y 2 M velas, **más** el banco con las velas finas) **completa**, libro 1,0000; **18 (el gate) INCOMPLETA**, libro 0,9164 y cobertura de `depth` 0,9172; 19–21 completas, 1,0000. Es decir: **las descargas y el banco no le hicieron daño; el gate sí**, y rompió la racha, que volvió a arrancar en la hora 19 (3 h a las 21 UTC). El gate se pausó **dos veces** (16:15 y 18:31, por RAM libre 978 y 1 016 MB) y se reanudó solo, pero la regla de pausa salta con RAM libre < 1 GB y a esa altura el equipo ya estaba al límite: **la pausa llegó tarde para salvar esa hora**. Corrige lo que se anotó al cerrar la sesión («la racha siguió subiendo»), que era cierto con las horas 16 y 17 pero no con la 18. Ajuste pendiente en BACKLOG T127 (3).
- **Abierto:** el nulo del control (BACKLOG T131 (8)) y los puntos (1)–(7) de esa misma entrada. La reproducción del informe de T111 sobre la copia (`scripts/t131_t111_diff.py`, con pruebas) está lista pero no se corrió: su tramo «dentro» no es comparable porque el almacén ganó contextos desde entonces (37 928 → 39 252).
- **Siguiente paso:** T132 y T133, que ya pueden ir en paralelo. En T133 conviene empezar por la cota del oráculo (E6), que puede descartar M4 sin más trabajo.
## 2026-11-03 23:10 UTC · juanpablo-cpu · T133 régimen ex ante: M4 descartada por la cota del oráculo
- **Veredicto: M4 SE DESCARTA.** La tarea se cierra en su **entregable 0**, la cota del oráculo (E6), como manda su ficha: «si incluso así M4 no cumpliría los criterios 1–3 de §5.4 frente a M0 y M1, se descarta sin seguir». Nota `PLAN/notas/T133_regimen_ex_ante.md`, informe `v2/reports/t133_oracle.md`.
- **Hecho:** `eim/paper/exits/oracle.py` (oráculo por día con mapa declarado, envolvente por operación, criterios 1–3 y veredicto) y `oracle_report.py`, más `scripts/t133_oracle.py` (~70 s sobre la copia de T131). Puro, sin red y sin disco; 16 pruebas.
- **Cómo se midió:** con el banco de T131 sobre la copia reconstruida (2 019 972 velas de 1 min desde 2023) y **solo los tramos de prueba** de sus 10 pliegues, con purga y embargo de 200 h: 60 720 ideas, 45 822 emparejadas, **29 828 operaciones fuera de muestra** por serie.
- **Las cifras:**
  - M0 escalera: E[R] −0,154, acierto 76,1 %, cociente 0,12, PF 0,386, DD 4 591 R, CVaR −1,350.
  - M1 TP/BE+/tiempo: E[R] −0,152, acierto 49,2 %, cociente 0,76, PF 0,731, DD 4 560 R, CVaR −1,394.
  - **Oráculo por día** (etiqueta ex post de `ab_conditions`: M0 en lateral, M1 en tendencia, «intermedio» a la escalera): E[R] **−0,093**, acierto 67,8 %, cociente 0,35, PF 0,737, DD 2 812 R, CVaR −1,373. Δ +0,061 frente a M0 (IC [+0,045, +0,076]) y +0,059 frente a M1 (IC [+0,046, +0,073]).
  - Envolvente por operación: E[R] +0,210, PF 1,85, DD **45 R**.
- **Por qué falla, con nombre y apellido:** frente a M0, criterio 2 (cociente 0,35 < 0,50 exigido) y criterio 3 (CVaR −1,373 peor que −1,350); frente a M1, criterio 2 (PF 0,737 < 1,15 × 0,731 = 0,841). Y sobre todo **sigue perdiendo**: conocer el régimen del día decide *cuál* de las dos salidas usar, no cambia la forma de las operaciones (las perdedoras siguen costando ~1,1 R).
- **La envolvente no salva nada, y es importante no leerla mal:** sí cumple los tres criterios, pero su drawdown cae de 4 591 R a **45 R**, que es el termómetro de cuánta información futura usa. Eligió M0 en 28 794 entradas y M1 en 17 028: acierta **operación a operación**, no día a día, y el régimen es una propiedad del día. Mide que estas entradas serían rentables si se supiera de antemano el resultado de cada una, no que haya techo para un selector de régimen. Mi primera versión de `verdict()` juzgaba por la envolvente —la pregunta equivocada— y lo corregí; una prueba lo fija (`test_the_verdict_judges_the_day_oracle_and_not_the_envelope`).
- **Pruebas estadísticas sobre rasgos: 0.** No se construyó ninguno (ni Efficiency Ratio, ni ADX, ni cociente de varianzas, ni OU, ni BOCPD), así que no hubo cribado de Benjamini-Hochberg ni confirmación por Holm o Romano-Wolf. El recuento de intentos de la fase y el Sharpe deflactado quedan limpios (E7). Sin dependencias nuevas: la ◆5 de T129 (statsmodels tras T04) **no se abre**. El agente `regime` no se tocó (fuera de alcance).
- **Consecuencia para la fase 22:** T134 ya no mide M4. **T132 no queda afectada**: M2, M3, M5, M6, M7, M8 y S1 cambian la *geometría* del stop (distancia, unidad de volatilidad, ancla de estructura, fases), no eligen entre las dos salidas de hoy. El pre-registro `prereg_t131_v2` **no se edita**: la rejilla declarada se conserva y M4 queda marcada como descartada aquí y en `STATUS.md`; si T134 quiere recontar intentos (105 en vez de 107), lo hará con una versión nueva.
- **Tercera señal apuntando al mismo sitio:** con el PBO de 0,46 de T131, todas las variantes en E[R] negativo y ahora un oráculo de régimen que tampoco cruza a positivo, la evidencia insiste en que **el problema está en la entrada** (T27, T49, T111). La fase 22 puede mejorar la salida; no va a hacer rentable un conjunto de entradas sin ventaja.
- **Pruebas:** 16 nuevas en `tests/paper/exits/test_oracle.py`. `ruff` limpio y 173 pruebas verdes en los paquetes afectados (`tests/paper/exits`, `test_ladder`, `test_t130_measurement`). **Gate completo pendiente a propósito:** la racha de T78 estaba en 3 h y hoy se midió que el `pytest` entero la rompe (BACKLOG T127 (3)); todo lo añadido es aditivo (dos módulos y un script nuevos, ningún archivo de código existente modificado).
- **Abierto:** nada de T133 a medias. Si en el futuro cambian las **entradas** (T27/T49) y vuelven a tener ventaja, esta cota hay que recalcularla antes de reabrir M4: es específica de este conjunto de entradas y de estas dos salidas. El cribado por FDR de E7 sigue sin implementar en el proyecto (hoy solo Holm y Romano-Wolf, en `eim/paper/exits/stats.py`).
- **Siguiente paso:** T132 (implementar M2, M3, M5, S1 y M6–M8 como `ExitPolicy`), teniendo presente antes de juzgar candidatas el nulo del control de BACKLOG T131 (8).
## 2026-11-04 00:30 UTC · juanpablo-cpu · T132 salidas candidatas implementadas
- **Hecho:** todas las candidatas de §3 y §7 de `PLAN/notas/T129_sl_dinamico.md` como `ExitPolicy` **puras**, sin conectarlas a los perfiles y sin tocar el libro (una prueba lo comprueba en los imports de los nueve módulos):
  - **M2** Chandelier (`extremo − k·σ`, activo desde un avance de `a` R), **M3** estructura (swing confirmado por fractal ± colchón de `b·σ`), **M5** híbrida por fases con **una** política por fase y nunca «el mejor de varios» (H5), **M6** barrera de tiempo, **M7** reversión del marco mayor, **S1** SL inicial con piso de `d_min·σ` y **M8** SL inicial por cuantil del MAE de las ganadoras.
  - **σ:** `sigma.py` con ATR de Wilder, cierre a cierre, Parkinson, Garman–Klass, Rogers–Satchell y Yang–Zhang; `harrv.py` con HAR-RV sobre las velas de 1 min, ajustado **solo con días anteriores**. Todos causales, en σ relativo por vela, y `nan` donde falta ventana: nunca 0 (un σ de 0 pondría el stop encima del precio).
  - **`ExitFeatures` v1** (`features.py`): σ, swings confirmados, dirección del marco mayor y rango mediano, cada campo con su **procedencia y su cobertura real**.
  - **`trail.py`:** el bucle de velas que comparten las candidatas, con la misma mecánica conservadora que `ladder.py` (entrada idéntica reutilizando `_entry`, trinquete, piso de ruido, redondeo al tick en contra, huecos a la apertura, velas ambiguas resueltas con 1 min).
  - **E5 sin fuga ni circularidad** (`winners_mae.py`): cuantil por pliegue calculado solo con ganadoras del tramo de **ajuste**, «ganadora» definida por una salida de **referencia fija** (nunca la que se evalúa, que es el defecto H1) y muestra mínima por estrategia@marco; sin muestra, no se aprieta.
- **Dos defectos que encontraron las pruebas, no yo:**
  1. El motor calculaba el candidato de stop con el extremo de la vela **anterior**, así que el arrastre iba un paso por detrás de `ladder.py`. Ahora la regla recibe el extremo **prospectivo**, igual que `ladder._Run.peek`. Se vio en el caso de 3 velas: el stop salía 99,2 cuando debía ser 109.
  2. Mi `htf_dir` usaba EMAs del **propio camino de 15 m**, no del marco mayor, que es lo que mide `ExecParams.htf` en todo el proyecto. Con el 1 h real, las salidas de M7 bajan de 1 825 a 970 y su E[R] descriptivo de +0,206 a +0,156. Si se hubiera quedado el sustituto, T134 habría medido otra cosa; ahora `source` declara cuándo es el marco mayor y cuándo el sustituto.
- **Un tercer hallazgo, de método:** la propiedad «paseo aleatorio sin costos ⇒ E[R] ≈ 0» fallaba con −0,11 R, y **no era el motor**: `walk_path` pega mechas sorteadas aparte del recorrido, así que el máximo de la vela no corresponde a ningún camino y un arrastre que ancla en el extremo mueve el stop a un nivel que el precio nunca visitó en ese orden. Con un camino **coherente** (15 m agregado de velas de 1 min reales) sale 0,00 con k = 1, 2,5 y 6, con y sin velas finas. Queda `coherent_path` en los helpers para cualquier medición futura de esperanza.
- **Comprobado sobre la copia real** (`v2/reports/t132_smoke.md`, 4 000 ideas de 2023, descriptivo y **sin** criterios de §5.4): las seis corren y cierran sin incidencias. Cobertura de rasgos en 3,5 años: σ 99,9 % (HAR-RV 94,8 %, le faltan los 60 días de ajuste), swings 100 %, marco mayor 100 %. S1 se mide **compuesta con M2**, que es como la usaría T134: sola solo puede perder (sin nada que la cierre en positivo, su E[R] condicionado a cerrar es −1 R por construcción), y así aparece etiquetada.
- **Archivos:** `v2/eim/paper/exits/{sigma,harrv,features,trail,rules,candidates,winners_mae}.py`, `v2/scripts/t132_smoke.py`, `v2/tests/paper/exits/test_{sigma,features,trail,candidates,winners_mae}.py`, `v2/reports/t132_smoke.{json,md}`, `PLAN/{STATUS,BITACORA}.md`.
- **Pruebas:** 212 en `tests/paper/exits/` (sin red), con las de §5.2 a cientos de semillas y la que exige la aceptación: el cuantil de M8 de un pliegue no cambia aunque se reescriba por completo su tramo de prueba. Archivos ≤ 300 líneas. `ruff` limpio.
- **Gate completo pendiente**, junto con el de T133: rompería la racha de T78 (§3 de `ESTADO_PROYECTO.md`, BACKLOG T127 (3)). Todo lo de T132 es aditivo: siete módulos y un script nuevos, sin modificar ningún archivo de código existente.
- **Abierto:** elegir parámetros o ganadora es T134, y necesita una **versión nueva del pre-registro** (`prereg_t131_v3`): poner M2–M8 y S1 como implementadas, quitar M4 (descartada en T133) y arreglar el nulo del control (BACKLOG T131 (8)) antes de juzgar nada. `prereg_t131_v2` no se edita.
- **Siguiente paso:** T134, con esas tres cosas resueltas en su propia versión del pre-registro.
## 2026-11-04 05:45 UTC · juanpablo-cpu · T134 experimento de salidas: 87 de 87 rechazadas
- **Veredicto: no se adopta ninguna salida.** 89 variantes de la rejilla pre-registrada sobre 60 720 ideas, ventana 2023-01-11 → 2026-07-11, 10 pliegues, embargo 200 h, ≈ 29 830 operaciones fuera de muestra por variante, 53 min. Nota `PLAN/notas/T134_experimento_salidas.md`, informe `v2/reports/exits_ab.{md,json,csv}`, reproducible con una orden: `python scripts/t134_exits_ab.py --data backups/t131_banco`.
- **Pre-registro v3** (v1 y v2 quedan publicadas e intactas): políticas de T132 como implementadas; M4 descartada por T133 **sin descontar sus intentos** (declararlas ya fue un grado de libertad gastado: siguen los 107, que es la cuenta conservadora); y el **criterio 6 redefinido**. Además se cerraron dos huecos de la propia v3 **antes de calcular nada con ella** (el historial lo muestra): la salida de referencia de E5 (`M1 be=1/0.1`, que no había nombrado) y el acompañante de S1 y M8 (`initial_stop.companion` = M0, porque las dos solo cambian el SL inicial y con qué se acompañan era un grado de libertad sin declarar).
- **El nulo del control, arreglado y validado.** El de la v1 y la v2 pedía que el R bruto de unas entradas al azar contuviera el 0, y eso solo vale si la serie es una martingala; el BTC no lo es y un arrastre es justo una apuesta a esa dependencia. El nuevo baraja los log-retornos reales de 1 min, rehace el camino de 15 m agregando desde ellos y compara contra esa distribución. Resultado: **todas las variantes pasan** con p = 0,62 y 0,67 (bruto observado +0,026 frente a un nulo de media +0,045, p95 +0,098). El «fallo» que T131 veía era la mala especificación, no un defecto del banco. Cierra BACKLOG T131 (8).
- **Lo que el experimento sí encontró: el SL inicial, no el arrastre.** Las dos únicas variantes que pasan el criterio 1 son de M8 (cuantil del MAE de las ganadoras) y la segunda mejor de todo el banco es de S1 (piso de σ). M8 es monótona: q=0,8 → −0,1404, q=0,9 → −0,1194, q=0,95 → −0,1045. `M8 q=0.95` da ΔE[R] **+0,0493** frente a M0 (IC [+0,0435, …], Romano-Wolf 0,0002), baja el drawdown de 4 591 a 3 121 R y el CVaR de −1,350 a −1,241, y **aguanta el estrés de costos** (×1,5: Δ +0,0595, p 0,0002). Coherente con Lo y Remorov: al alejar el stop, la misma pérdida en R cuesta menos en costos.
- **Por qué ni esa se adopta:** falla el criterio 2 (cociente 0,11 frente a 0,50 exigido y PF 0,475 frente a 0,841), el 4 (10/10 pliegues con Δ > 0 pero **2023 negativo**) y el 5 (no forma meseta), y **sigue perdiendo** −0,1045 R. Apartar el stop mejora la media y la cola pero no cambia la forma de las operaciones: las ganadoras siguen diminutas.
- **PBO 0,129**, por debajo del 0,20 pre-registrado. El 0,46 de T131 salía de medir once variantes casi idénticas; con 89 el CSCV tiene de dónde elegir.
- **Cuatro defectos encontrados por medir antes de lanzar y por desconfiar de los resultados.** Los cuatro habrían falseado el informe:
  1. **El piso de ruido lo decidía el redondeo al tick.** Se medía sobre el candidato ya redondeado, y como el redondeo va en contra del operador, una variante con `k` igual al piso quedaba siempre por dentro y el stop **no se movía nunca**: 15 variantes de M2 inertes, 0 movimientos, 55 221 velas recorridas en balde por idea, 28 de 60 operaciones sin cerrar y 276 s por variante. Ahora el piso se mide sin redondear.
  2. **`min_r = 0` nunca disparaba la barrera de tiempo** («avance < 0» es imposible porque el avance está acotado en 0): 3 variantes de M6 midiendo «no cerrar nunca». Ahora 0 significa sin excepción.
  3. **Las tres variantes de M8 eran la misma política:** salían idénticas hasta el cuarto decimal porque `grid` pasaba la misma función de cuantil a las tres y nunca usaba `q`, que es el parámetro que M8 varía. Entraban además en la corrección como tres copias correlacionadas y su meseta pasaba trivialmente. Ahora `grid.expand` recibe una fábrica de cuantiles.
  4. **El criterio 4 se medía sobre el E[R] absoluto por año en vez del Δ.** El informe decía a la vez «10/10 pliegues con Δ > 0» y «fallan los cuatro años»; esa incoherencia era la pista. §5.4 pide que la MEJORA aguante año a año, como el criterio 1; exigir rentabilidad absoluta cada año es criterio de la entrada (T27).
  El experimento pasó de ~200 h de cómputo a 53 min.
- **Y un fallo de método que atrapó una prueba:** el conjunto emparejado de `bench.run` es la intersección de **todas** las políticas de la corrida, así que al correr por lotes las cifras de una variante dependían de con quién le tocaba lote (la base daba n=112 con el lote completo y n=121 en lotes de uno). Habría invalidado el experimento entero. Ahora cada variante se mide sobre las ideas que ELLA cerró y cada comparación contra una base sobre las que cerraron las dos, con su n a la vista; una prueba compara lotes contra corrida completa y exige que no cambie ni una cifra.
- **Potencia para T135 (E9):** σ de las diferencias emparejadas de `M8 q=0.95` frente a M0 = **0,352 R** → **≈ 315 operaciones emparejadas** para detectar +0,0493 R con α 0,05 a una cola y potencia 0,80. El banco cierra 230 por semana pero con tamaño fijo y sin cupos: el ritmo real por perfil hay que tomarlo del libro en vivo, y esa traducción es de T135.
- **Lo que T134 no podía hacer, y se dice:** no aprobar nada (el criterio 7 es prospectivo y su dato nace en T135, así que el estado máximo era «candidata a T135» y ninguna llegó); el libro completo solo es calculable para M0 y M1, porque las demás exigen conectarlas a los perfiles (T135); S2 y S3 no se corrieron (permiso del usuario y T136) y cuentan como intentos.
- **Archivos:** `v2/eim/paper/exits/{surrogate,grid,verdict,experiment,exits_report}.py`, `v2/eim/paper/exits/versions/prereg_t131_v3.json`, `v2/eim/paper/exits/{prereg,trail}.py`, `v2/scripts/t134_exits_ab.py`, `v2/tests/paper/exits/test_{surrogate,grid,verdict,experiment}.py`, `v2/reports/exits_ab.{json,md,csv}`, `PLAN/{STATUS,BITACORA,ESTADO_PROYECTO}.md`, `PLAN/notas/T134_experimento_salidas.md`.
- **Pruebas:** 255 en `tests/paper/exits/`, sin red. `ruff` limpio. **Gate completo pendiente** junto con los de T132 y T133, para no romper la racha de T78 (§3 de `ESTADO_PROYECTO.md`).
- **Nada tocado en vivo:** ni `data/`, ni la salida del bróker, ni los servicios. Nada habilita dinero real.
- **Abierto:** la pregunta ◆ de T134 al usuario (qué salida y qué tamaño adoptan los perfiles). La respuesta que sostiene la evidencia es **ninguna**, y lo del SL inicial es indicación para T136 y T49, no una salida que adoptar.
- **Lectura de conjunto de la fase 22:** cuatro mediciones independientes apuntan a la entrada y no a la salida — el PBO de T131, el oráculo de régimen de T133, las 87 variantes de aquí, y que la única mejora real sea geométrica (apartar el stop) y no de la regla de salida. La fase ha hecho su trabajo: ha descartado con pruebas que el problema esté en cómo se sale.
- **Siguiente paso:** la decisión ◆ del usuario. Según lo que decida, T136 (riesgo por operación con costos, donde encaja lo del SL inicial) o volver a la entrada (T27/T49). T135 solo tiene sentido si se adopta algo, y hoy no hay nada que adoptar.

## 2026-11-04 17:40 UTC · juanpablo-cpu · gate completo de la fase 22, verde
- **Hecho:** el `pytest` entero que T132, T133 y T134 habían dejado pendiente a propósito. Desde `main` @ `2dba569` y **por la cola de T127** (`jobs submit --name gate-fase22 --retry-paused 1 -- python -m pytest -q`, prioridad `batch`): **2 778 pruebas pasadas, 8 omitidas, 0 fallos** en 945 s (17:13–17:28 UTC), **sin ninguna pausa de la cola**. `ruff check eim tests` limpio antes de lanzarlo. Con esto la fase 22 no deja ningún gate pendiente: las 255 pruebas nuevas de `tests/paper/exits/` pasan dentro de la suite completa y no solo en su paquete.
- **Por qué ahora y no al cumplirse T78:** la condición que dejó escrita §3 era «en cuanto T78 cumpla sus 72 h **o si la racha se rompe por otra causa**». La racha estaba en **1 hora** (`hft_ops --streak`: actual 1 h desde 2026-11-04T16, mejor 23 h del 1–2 nov), así que romperla costaba una hora, no 71.
- **Lo que no se sabe todavía, y se dice:** el gate cayó entero dentro de la **hora 17 UTC**, que a esta hora aún no es auditable (el QC audita horas cerradas con margen). Si la 17 sale incompleta, la racha vuelve a 0 y se confirma por segunda vez lo medido el 2026-11-03; si sale completa, es la primera corrida del gate que la captura aguanta, y entonces lo que cambió fue la cola (prioridad `batch`). **Hay que mirarlo en la próxima sesión** con `python -m eim.data.collectors.hft_ops --root data --streak --symbol BTCUSDT`. La regla de §3 sigue en pie mientras no se ajuste el umbral (BACKLOG T127 (3)): no correr el gate completo con una racha ya avanzada.
- **Dato para T116:** es la primera corrida completa **verde** en `juanpablo-cpu` con los servicios en marcha. Las tres no verdes de T116 tenían Ollama generando sin parar; aquí Ollama estaba parado y el gate fue en `batch`. No cierra T116 (le faltan sus 3 corridas con el equipo descargado), pero descarta que el equipo por sí solo haga fallar las pruebas con plazo.
- **Archivos:** `PLAN/{STATUS,ESTADO_PROYECTO,BITACORA}.md`, `PLAN/roadmap.html`. Sin cambios de código.
- **Corregido de paso en `ESTADO_PROYECTO.md`:** la cabecera estaba en T131 (ahora dice fase 22 cerrada) y la fila de T131 de §2 seguía citando el **PBO 0,46** como si fuera el número bueno; T134 lo deja en **0,129** y así queda anotado donde se lee primero.
- **Abierto:** la pregunta ◆ de T134, que sigue siendo lo único que la fase 22 espera del usuario (qué salida y qué tamaño adoptan los perfiles; la respuesta que sostiene la evidencia es **ninguna**), y la auditoría de la hora 17 UTC de la captura.
- **Siguiente paso:** la decisión ◆. Según lo que decida, T136 o volver a la entrada (T27/T49).

## 2026-11-05 22:25 UTC · juanpablo-cpu · T136 cierre: riesgo por operación con costos y freno gradual
- **Hecho:** cierre de T136, que venía de otra cuenta con la nota `PLAN/notas/T136_TRASPASO.md`. Rellenados los dos marcadores con el deslizamiento medido contra el libro, tras comprobar cada cifra en `v2/reports/t136_deslizamiento.json`: 114 stops medidos de 129 con cobertura, real mediana 2,08 pb frente a 5,70 del modelo, corto en el 28 %, veredicto «el modelo aguanta»; en la cola, 77,4 pb reales frente a 17,1. **No se cambia el modelo de costos.** Todo el código de T136 sale apagado y ningún perfil cambia.
- **Corregido del traspaso:** (1) el commit `16061ba` había metido `.claude/settings.local.json`, que al fusionar habría chocado con el archivo sin seguimiento del checkout principal: fuera de la rama, aunque sigue en su historia (es la lista de permisos locales, sin claves). (2) La nota estaba en `v2/PLAN/notas/` y todas las referencias apuntan a `PLAN/notas/`: movida. (3) Las filas de `ESTADO_PROYECTO.md` que daban T136 como siguiente tarea y T78 con fecha de cumplimiento ya no valían: actualizadas.
- **Hora 18 UTC del 2026-11-04, auditada: se perdió.** Incompleta, libro útil 98,39 %, 18 silencios, 0 huecos sin detectar; coincide con la primera versión de `t136_deslizamiento.py` (10,2 GB). Ninguno de los 114 stops medidos cae en ella, así que no afecta al resultado.
- **Hora 17 del gate de la fase 22: salió completa**, lo que la bitácora anterior dejaba abierto. El traspaso concluía de ahí que el gate por la cola ya no rompe la racha; **no se da por sentado**, porque el gate de T131 también iba por la cola y rompió su hora. Hay una sola medición a favor, y la regla de §3 se mantiene.
- **Encontrado de paso:** (1) las horas 10–21 UTC de hoy salen incompletas solo por la cobertura de `mark`, con los 3 600 mensajes presentes y el libro útil ≥ 0,99, desde el reinicio de Windows de las 08:11 UTC; parece un artefacto de medición y tiene la racha de T78 en 0 (BACKLOG T78, hipótesis sin demostrar). (2) La publicación externa de las 01:30 UTC terminó incompleta y `continuity check` no lo avisa (BACKLOG T125).
- **Archivos:** código y pruebas de T136 (`v2/eim/paper/{risk_budget,kelly,caps,slip_check,policy,book,params,vetoes}.py`, `v2/eim/paper/exits/{es_check,risk_study,risk_report,stats}.py`, `v2/scripts/t136_{riesgo,deslizamiento}.py`, `v2/tests/paper/`), informes `v2/reports/t136_*`, `PLAN/notas/T136_{riesgo,TRASPASO}.md`, `PLAN/{STATUS,BACKLOG,ESTADO_PROYECTO,BITACORA}.md`, `PLAN/status.js`. La nota de traspaso se conserva como registro; su apartado «sin commitear» ya no describe el estado.
- **Pruebas:** `ruff check eim tests` limpio. `pytest -q` entero por la cola (`gate-t136`, 21:57–22:21 UTC, desde el worktree, con `--data-dir` de los servicios para vigilar la captura real): **rc 0, 2 856 pasadas, 8 omitidas, 0 fallos** en 1 451 s, con una pausa de 115 s por RAM libre de 1 023 MB. El recuento sale del progreso del registro, porque `addopts` ya trae `-q` y con el segundo pytest no imprime la línea de resumen.
- **Abierto:** las tres ◆ de T136 (`risk_includes_costs`, tope de costo a 0,08 R, freno gradual). Auditar la hora 22 UTC de hoy, la del gate, cuando cierre: da una segunda medición de si el gate daña la captura; mirar `book_usable` y `depth`, porque `complete` está falseado por `mark`. El PR de T136 falta por fusionar.
- **En curso:** T31, T45, T62, T104, T78, T116, T117, T127, T128, sin cambios en esta sesión.
- **Siguiente paso:** fusionar el PR de T136 y responder sus tres ◆. Después, el frente de la entrada: T27 (puerta de edge) y T49 (versiones de estrategia).

## 2026-11-05 22:40 UTC · juanpablo-cpu · T136 fusionada, sus tres ◆ resueltas y T137 abierta
- **Hecho:** PR #208 fusionado (`fe33c1c`) y `main` traído a la carpeta principal **sin reiniciar servicios**: cargarán T136 en su próximo reinicio. El usuario resolvió la ◆1: `risk_includes_costs` se enciende **al cerrar T31** (→ 2026-11-27) y no antes. Queda como sección «Al cerrar» de `PLAN/T31.md`, que es lo que leerá quien cierre esa tarea, con dos trampas anotadas: la prueba que fija el valor apagado y la corrida de la portátil, a la que el cambio le llegaría al traer `main`. El parámetro sigue en `False`. Resuelta también la ◆2: el tope de costo **no se aprieta en los perfiles** y se evalúa junto con el SL inicial más amplio, como versión de estrategia puntuada por la puerta de T49. Y la ◆3: el freno gradual sustituye al de hoy **al cerrar T31**, decidiendo antes con qué regla reanuda, porque con tramo 0 no vuelve a operar. Los dos encendidos están en la misma sección de `PLAN/T31.md`.
- **Corregido:** el «siguiente frente: T27/T49» que venía del traspaso y de esta misma sesión no se sostiene tal cual: las dos están ☑ con veredicto negativo y la ficha de T49 excluye cambiar estrategias. A petición del usuario queda como **T137**, en una fase 23 nueva de la hoja de ruta (`PLAN/T137.md`), pendiente de empezar.
- **Archivos:** `PLAN/T31.md`, `PLAN/T137.md`, `PLAN/{STATUS,ESTADO_PROYECTO,BACKLOG,BITACORA}.md`, `PLAN/roadmap.html`, `PLAN/status.js`, `PLAN/notas/T136_riesgo.md`. Sin cambios de código.
- **Pruebas:** sin código nuevo, así que no se repitió el gate; el último es el de T136. `build_roadmap.py` sin errores.
- **Abierto:** la regla de reanudación del freno gradual, antes de encenderlo al cerrar T31. La auditoría de la hora 22 UTC de hoy pasó a la sesión aparte sobre la cobertura de `mark`.
- **En curso:** T31, T45, T62, T104, T78, T116, T117, T127, T128, sin cambios aquí; la cobertura de `mark` (T78) va en su propia sesión.
- **Siguiente paso:** empezar T137: versiones con SL inicial más amplio y tope de costo, puntuadas por la puerta de T49.

## 2026-11-05 23:20 UTC · juanpablo-cpu · T138: la racha de T78 está en 0 por una forma de contar y por el reloj
- **Hecho:** demostrada la hipótesis de la cobertura de `mark` con crudos: de las horas 09–21 UTC de hoy no falta ningún evento (46 800 de 46 800, intervalo entre eventos ≤ 1,018 s), pero contadas por segundo de llegada dan 5 308 segundos vacíos y 5 308 dobles. El modelo `1 − p(1 − p)` reproduce la cobertura con un error medio de 0,010. Causa de fondo: el reloj del equipo va ~835 ms adelantado desde el arranque de las 08:11 UTC (NTP y, sin NTP, cota por snapshots REST de al menos 624–652 ms). Windows Time sincroniza a diario, pero solo da el salto con más de 1 s de desfase: −1,607 s el 29-oct, menos de 1 ms estos días. Hora 22 auditada: el gate de T136 no dañó la captura (libro útil 1,0).
- **Preparado, sin aplicar:** medida `qc.cadence_coverage` (`QC_VERSION` 2) y `hft_ops --requalify DESDE [--apply]`, que lee solo `mark` y conserva el veredicto original. En una réplica en seco sobre las 150 horas auditadas solo cambian las 13 falsas, todas de no a sí. Ningún JSON escrito, ningún servicio reiniciado, el reloj sin tocar.
- **Archivos:** `v2/eim/data/collectors/{qc,hft_ops}.py`, `v2/tests/data/{hft_helpers,test_hft_qc_cadence}.py`, `PLAN/T138.md`, `PLAN/notas/T138_cobertura_mark.md`, `PLAN/{STATUS,ESTADO_PROYECTO,BACKLOG,BITACORA,00_MASTER}.md`, `PLAN/roadmap.html`, `PLAN/status.js`.
- **Pruebas:** `ruff check eim tests` limpio. Por la prioridad `batch`, en verde: `test_hft_qc`, `test_hft_qc_cadence`, `test_hft_ops`, `test_hft_capture`, `test_hft_events`, `test_usage`, `test_build_roadmap`, `test_tasks_inventory` y `test_catalog`. **Gate completo pendiente a propósito:** con la medida nueva la racha real lleva 14 h, y uno de cada tres gates la ha roto; no se arriesga antes de que el usuario decida si esas horas cuentan. Se corre al cerrar T138.
- **Corregido de paso:** esta tarea iba a ser T137, pero el PR #209 ya la usa para la entrada. `git merge` a mano porque `sync_with_base_branch` falló con «Committer identity unknown»; ojo también con `build_roadmap.py`: publica si la rama tiene las mismas tareas que el tablero vivo, aunque sean otras.
- **Abierto:** ◆ de T138: ¿se adopta la medida y se recalculan las horas pasadas? ◆ del reloj, con permiso. Sin explicar: por qué el arranque del 2026-11-03 casi no movió el reloj.
- **En curso:** T31, T45, T62, T104, T78, T116, T117, T127, T128, T137, sin cambios aquí.
- **Siguiente paso:** la decisión del usuario. Si adopta: fusionar, traer `main` a la carpeta principal sin reiniciar, `hft_ops --requalify 2026-11-05T09 --apply`, `--streak`, y el gate completo por la cola.

## 2026-11-06 00:20 UTC · juanpablo-cpu · T138 cerrada: medida adoptada y horas recalificadas
- **Hecho:** el usuario resolvió la ◆ («Sí, y recalcula»). Gate completo por la cola (`gate-t138`, 23:20:47–23:42:58 UTC, sin pausas). Después, `hft_ops --requalify 2026-11-05T09 --apply`: en seco y aplicado dieron lo mismo, 13 horas de no a sí, y dentro de cada JSON solo cambiaron `version`, `complete`, `coverage_cadence` y `requalified`. Con la hora 23, recalificada igual, la racha de T78 va en **15 h** (faltan 57); se cumple como pronto al cerrar la hora 2026-11-08T08 UTC. Ningún servicio reiniciado.
- **Comprobado de punta a punta:** el vigilante, aún con el código viejo, escribió la hora 23 en versión 1 y `--streak` dijo 0 h. Tras `--requalify`, 15 h. **Hasta reiniciarlo hay que recalificar antes de leer la racha**; `t78_streak` de `summary.json` tiene el mismo retraso.
- **Medición:** el gate de T138 no rompió la hora 23, pero se nota (libro útil 0,9989, 2 silencios, p99 de `bbo` 4 874 ms, con casi el triple de `bbo` que la hora 22). Van 3 gates que no rompen la hora, de 4; la regla no se levanta.
- **Archivos:** `PLAN/{T138,STATUS,ESTADO_PROYECTO,BACKLOG,BITACORA}.md`, `PLAN/notas/T138_cobertura_mark.md`, `PLAN/status.js`. En el almacén: los JSON de QC de las horas 09–23 del 2026-11-05.
- **Pruebas:** `ruff check eim tests` limpio; `pytest -q` entero: 2 875 pasadas, 8 omitidas, 0 fallos en 1 331 s.
- **Abierto:** ◆ el reloj sigue ~835 ms adelantado (BACKLOG T138 (3)). Sin explicar: por qué el arranque del 2026-11-03 casi no lo movió.
- **En curso:** T31, T45, T62, T104, T78, T116, T117, T127, T128, T137, sin cambios aquí.
- **Siguiente paso:** dejar correr la captura hasta 2026-11-08T08 UTC sin gates completos, y recalificar antes de cada lectura de la racha.

## 2026-11-06 00:40 UTC · juanpablo-cpu · T137: versiones de entrada por la puerta de T49, ninguna validada
- **Hecho:** T137 entera, con el pre-registro `prereg_t137_v1` en `213247f`, anterior a todo cálculo. 520 versiones (las 104 estrategia@marco × `m8`, `s1`, `tope`, `m8_tope`, `s1_tope`), cada una con su propia sombra, puntuadas con `validation_v1` sin cambios. **Veredicto oficial: 0 VALIDADA, 484 EN OBSERVACIÓN, 36 RECHAZADA**, y ninguna cumple la regla de lectura pre-registrada para proponer seguimiento.
- **Lo que queda:** apartar el stop no crea ventaja, abarata el costo en R. En el banco el bruto sigue en cero en todas (padre −0,000 R, `m8_tope` −0,005 R); el neto mejora de −0,152 a −0,060 R y el costo baja de 0,152 a 0,054 R. La mejora de T134 y T136 era real, pero es costo diluido.
- **Decisión de diseño, fijada antes de calcular:** `M8 q=0.95`, `S1` y el tope se eligieron mirando T134 y T136, así que esa ventana es ajuste según la definición de T49, y además se heredan las automáticas del padre (hasta 2026-10-22T22:36Z). La lectura oficial queda en ≈ 11 días y 0 de 520 llegan a V1; la reserva tampoco. El banco es solo descriptivo, una cota optimista: llegan 102 de 365 y ninguna pasa V3 con Holm.
- **Cierra:** BACKLOG T134 (1), el control ahora mueve el SL en el 92 % de las ideas al azar con M8 y nada destaca sobre las sustitutas; y BACKLOG T136 (1), 15 m medido, costo ex ante de la idea media 0,490 R y el tope deja fuera el 100 %.
- **Encontrado:** (1) las unidades de M8 no coinciden desde T134 (cuantil en σ de Parkinson aplicado sobre σ ATR14, mediana 1,377); se conservó porque es la geometría con señal, y va a BACKLOG. (2) Un intento registrado podía ser padre de una versión viva y pasarle sus ventanas; lo atrapó una prueba y `ensure` ya no los ve. (3) La primera corrida mezclaba el control en los agregados: se vio porque el padre no daba la cifra de T134.
- **Archivos:** `v2/eim/validation/{entry_prereg,entry_versions,entry_run,entry_control,entry_report,attempts,service,gate,__main__}.py`, `v2/eim/validation/prereg/prereg_t137_v1.json`, `v2/eim/validation/attempts_t137.json`, `v2/eim/data/validation_store.py`, `v2/eim/api/{config,main}.py`, `v2/scripts/t137_entrada.py`, `v2/reports/t137_entrada.{md,json,csv}`, `v2/docs/OPERACION.md`, `v2/tests/validation/test_entry_{prereg,versions,control,registry}.py`, `test_service.py`, `PLAN/notas/T137_entrada.md`, `PLAN/{STATUS,BACKLOG,ESTADO_PROYECTO,BITACORA}.md`. `eim/paper` y el catálogo no se tocaron.
- **Pruebas:** cinco regresiones exactas contra T134 y T136 sobre datos reales. `pytest -q` entero por la cola (`gate-t137`, 00:10–00:30 UTC, desde el worktree @ `f569129`, con el `--data-dir` de los servicios): **rc 0, 2 908 pasadas, 8 omitidas, 0 fallos**, sin pausas. Tras traer `main` (T138) solo se repitieron `tests/validation` y las pruebas de `qc` de T138, porque no comparten código. La hora 00 UTC del gate no se auditó en la captura HFT.
- **Abierto:** la ◆ de T137: ¿se cierra la línea de apartar el stop? Los 520 intentos entran en el registro vivo al próximo reinicio de la API; hasta entonces el registro es `attempts_t137.json`. No se reinició nada.
- **En curso:** T31 (→ 2026-11-27), T45, T62, T104, T78, T116, T117, T127, T128, sin cambios aquí.
- **Siguiente paso:** responder la ◆. Si se cierra, buscar entradas con bruto positivo, que es una tarea nueva.

## 2026-11-06 00:45 UTC · juanpablo-cpu · T137: el usuario cierra la línea de apartar el stop
- **Hecho:** el usuario resolvió la ◆ de T137: la línea se cierra. No se adopta ninguna versión, los perfiles no cambian y la corrida no se repite al cerrar T31. Los 520 intentos siguen contando en Holm.
- **Archivos:** `PLAN/{STATUS,ESTADO_PROYECTO,BACKLOG,BITACORA}.md`, `PLAN/notas/T137_entrada.md`, `PLAN/status.js`. Sin cambios de código.
- **Pruebas:** sin código nuevo, así que no se repitió el gate; el último es `gate-t137`. `build_roadmap.py` sin errores.
- **Abierto:** fusionar el PR #211. Los intentos entran en el registro vivo al siguiente reinicio de la API.
- **En curso:** T31 (→ 2026-11-27), T45, T62, T104, T78, T116, T117, T127, T128, sin cambios aquí.
- **Siguiente paso:** buscar entradas con bruto positivo, que es una tarea nueva todavía sin ficha.

## 2026-11-06 01:05 UTC · juanpablo-cpu · T139: ficha de la búsqueda de entradas con R bruto positivo
- **Hecho:** ficha `PLAN/T139.md`, con fila en `STATUS.md`, fase 23 en la hoja de ruta y en `00_MASTER.md` (no estaba) y una línea en `BACKLOG.md`. **Sin calcular nada sobre datos de mercado ni implementar estrategias:** las cifras nuevas son aritmética sobre lo publicado (`v2/reports/t137_entrada.csv`, costos de T137, criterios de `validation_v1`).
- **Lo que fija:** cinco hipótesis (H1 funding, H2 y H3 flujo agresor, H4 cascada forzada, H5 momento en 1 d) con la salida de `control_aleatorio`. 9 claves, familia de 841, z ≈ 3,85. 2023 → hoy solo descarta; se puntúa antes de 2023, de un solo uso, y en vivo desde el pre-registro. Regla de lectura de cinco condiciones y parada P0–P3 con fecha límite de 6 meses.
- **Hallazgos al calcular los mínimos:** V3 mide el bruto y V2 el neto, así que el costo manda sobre Holm desde n ≈ 160 en 1 h y n ≈ 560 en 4 h, y reducir la familia apenas ayudaría. 15 m no puede pasar V6 sea cual sea la entrada. La evidencia de 4 h son solo 114 días de contextos. V3 no controla la deriva. Que `taker_buy_v` esté en el banco de T131 y la historia anterior a 2023 **no se ha comprobado**: es el paso 4 de la ficha.
- **Archivos:** `PLAN/{T139,STATUS,BACKLOG,BITACORA,ESTADO_PROYECTO,00_MASTER}.md`, `PLAN/roadmap.html`, `PLAN/status.js`. Sin cambios de código.
- **Pruebas:** sin código nuevo. `ruff check eim tests` limpio y `test_build_roadmap` + `test_tasks_inventory` en verde (10 pruebas); **gate completo sin correr a propósito**, para no arriesgar la racha de T78 (como pronto hasta 2026-11-08T08 UTC) por un cambio solo de documentos. `continuity check` da CON AVISOS desde la carpeta principal; desde este worktree da NO SINCRONIZADO solo porque el worktree no tiene `v2/data`.
- **Abierto:** las cuatro ◆ de la ficha: abrir o parar ya, lista de hipótesis, parada vinculante, Holm completo.
- **En curso:** T31, T45, T62, T104, T78, T116, T117, T127, T128, sin cambios aquí.
- **Siguiente paso:** responder las ◆. Si se abre, el primer commit es `prereg_t139_v1.json`, antes de descargar nada.

## 2026-11-06 05:40 UTC · juanpablo-cpu · T139: la lectura limpia da P1
- **Hecho:** el usuario respondió «lo recomendado» a las cuatro ◆. Pre-registro `3d396f7` antes de descargar; reglas y pruebas `8a599e7`; revisión de código `b56993e`; descarga de 2019-09-08 → hoy a `backups/t139_banco` por la cola; cobertura, regresión y banco con los intentos confirmados en `0d04ab3`; lectura limpia una vez, 770 s.
- **Resultado:** P1, ninguna clave sigue, y las 9 salen RECHAZADA. `flujo_sigue@4h` es la única cerca (+0,182 R netos, IC [+0,0002, +0,366], n = 152) y solo falla V3 con Holm (p 0,0016). Con una familia de 9 sí seguiría: consta en la nota, §2. No se reabre: se decidió antes de calcular. Se debilita en el banco (+0,018 R) y no podría validarse antes de la fecha límite.
- **Corregido:** la primera ficha leía el p95 de +0,096 R del control de T137 como si fuera con n ≈ 1 800; son 300 ideas por serie. Corregido antes del pre-registro.
- **Archivos:** `v2/eim/validation/hypotheses/`, `v2/eim/validation/{attempts.py,attempts_t139.json,__main__.py}`, `v2/eim/validation/prereg/prereg_t139_v1.json`, `v2/eim/api/main.py`, `v2/eim/data/timeframes.py` (1 d solo de almacén), `v2/scripts/t139_entradas.py`, `v2/tests/validation/{t139_market,test_t139_*}.py`, `v2/reports/t139_*`, `PLAN/notas/T139_entradas.md` y el plan.
- **Pruebas:** `ruff check eim tests` limpio y `tests/validation` en verde, a prioridad `batch`. **Gate completo sin correr** para no arriesgar la racha de T78. Las horas 03 y 04 UTC, con mis trabajos, salieron completas; la 05 sin auditar al escribir esto. Otra sesión corrió `gate-t135` a las 05:00 UTC, no es de aquí.
- **Sin desplegar:** la API sigue con el código anterior. Los 9 intentos entran en el registro al reiniciarla.
- **Abierto:** ◆ ¿se cierra la búsqueda con P1? Gate completo. Etapa en vivo sin implementar, porque ninguna clave sigue.
- **En curso:** T31, T45, T62, T104, T78, T116, T117, T127, T128, T139.
- **Siguiente paso:** la respuesta del usuario; después, el gate cuando no haya racha en juego, y T139 a ☑.

## 2026-11-06 05:30 UTC · juanpablo-cpu · T135 motor de la posición, construido y apagado
- **Hecho:** el usuario pidió empezar T135 «mientras no interrumpa lo que se está llevando a cabo». Su condición era que T134 aprobara una salida, y no aprobó ninguna; T137 además cerró la línea de apartar el stop. Se construyó lo que no depende de elegir: `exit_mode="adaptativo"` con M2, M3, M5, M6 y M7, por la autoridad de T114, con el suelo del diario T110, fase, motivo, fuente y versión, panel en «Perfiles» y cálculo de potencia (E9). **Ningún perfil lo usa y el A/B no empezó:** no hay salida que comparar. Todo en un worktree propio, sin reiniciar nada ni tocar la base.
- **Comprobado que no cambia nada de lo vigente:** contra `main`, con `PYTHONHASHSEED=0`, las huellas de los 4 perfiles, sus volcados y las 111 versiones de T49 son idénticos. La solución obvia lo habría roto: un `"adaptive": null` en el volcado cambia la versión de los cuatro perfiles.
- **Revisión de código (nivel alto, la que pide la ficha):** 10 hallazgos, 5 corregidos con prueba (`check_profiles`, `sigma` sin validar, tope de peso, plan de potencia editado a mano, fuente de `htf_dir` en el panel). Los otros 5 quedan en BACKLOG T135 y en la nota.
- **Encontrado de paso:** (1) **la API no abre el puerto 8000 desde las 01:41 UTC**, cuando el vigilante la reinició por «latido detenido 932 s»; el proceso vive y los latidos siguen, pero la interfaz no carga datos. No lo causó esta sesión y no se reinició. Hay alertas críticas a las 01:50 UTC («el recálculo bajaría el stop guardado»). (2) `params_fingerprint` cambia entre procesos, desde antes de T135 (BACKLOG T135 (2)).
- **Archivos:** `v2/eim/paper/{adaptive,adaptive_params,params,policy,book,summary,desk,service,ladder_book,protection_sync,versioning,ab_gate}.py`, `v2/eim/paper/exits/{trail,trail_limits,candidates,power}.py`, `v2/eim/{core,risk}/authority.py`, `v2/eim/web/src/paper_{adaptive,chart,fmt,profiles,protect,tables,types}.ts`, `v2/scripts/t135_potencia.py`, pruebas en `v2/tests/paper` y `v2/tests/architecture`, `PLAN/notas/T135_motor.md`, `PLAN/{STATUS,BACKLOG,ESTADO_PROYECTO,BITACORA}.md`, `PLAN/status.js`.
- **Pruebas:** `ruff check eim tests` limpio; `tsc --noEmit` limpio; `pytest -q` entero por la cola (`gate-t135`, desde el worktree, vigilando la captura real): **rc 0, 3 006 pasadas, 8 omitidas, 0 fallos** en 945 s, sin pausas. El panel se comprobó en el navegador con datos de prueba, porque ningún perfil genera datos reales. **No probado:** la unión del libro y el diario con datos reales.
- **Abierto:** auditar la hora 05 UTC de hoy, la del gate, cuando cierre: es otra medición de si el gate daña la captura. Diagnosticar la API. El roadmap vivo no recoge el ◐ de T135 hasta fusionar, porque la rama de T139 ya publicó más tareas.
- **En curso:** T135 (◐), T139 en su propia sesión y sus trabajos en la cola; T31, T45, T62, T104, T78, T116, T117, T127 y T128 sin cambios aquí.
- **Siguiente paso:** T135 queda parada hasta que haya una salida aprobada por §5.4; hoy el frente es la entrada (T139). Lo urgente es la API.

## 2026-11-06 13:55 UTC · juanpablo-cpu · Diagnóstico y reinicio de la API sin puerto; abiertas T140, T141 y T142
- **Hecho:** T135 fusionada en #213, con el motor apagado y sin traer `main` a la carpeta principal. El usuario pidió decidir y se diagnosticó la API solo leyendo. **Después, con su permiso y ya terminado el gate de T139, se reinició solo la API a las 13:51:18 UTC:** relanzada a las 13:51:31 y escuchando a las 13:51:54, con el mismo código (`d1921eb`). Los otros 14 procesos de servicio siguieron vivos y la captura siguió escribiendo. Interfaz comprobada en el navegador: EN VIVO y precio en movimiento. Las 5 alertas críticas volvieron a salir a las 13:52:37, como se esperaba hasta cerrar T142.
- **Causa:** `asyncio` cierra el socket de escucha cuando falla un `accept` (`WinError 64`; `proactor_events.py:864-871`) y el vigilante solo mira el latido, que sigue al día. Pasó en las dos instancias que recoge el registro. Debajo hay otro problema: el equipo saturado por `python.exe` ajenos sin identificar deja parada a la API y causó 3 reinicios en 46 h. Las alertas «el recálculo bajaría el stop guardado» son 5 operaciones congeladas desde el 2026-11-04, siguen abiertas en los libros de T31 y repiten el patrón del falso positivo del 31-oct. Evidencia en `PLAN/notas/T140_api_sin_puerto.md`.
- **Correcciones a lo escrito antes:** la API sí arrancó tras las 01:41 y perdió el socket hacia las 02:00. Ese reinicio no fue durante la copia, que empezó a las 01:48. Y fusionar T135 no bastaba para ver su ◐ en el roadmap vivo: hacía falta que la rama de T139, con más tareas, trajera `main`.
- **Captura T78:** el gate de T135 (05:10–05:26 UTC) no la dañó, la hora 05 salió completa. Las horas 06 y 07 salieron incompletas por silencios y desconexiones con el equipo libre y la cola vacía, lo que apunta a la red, sin poder asegurarlo. La hora 13, la del reinicio, salió completa. Racha de 6 h desde las 08 UTC; como pronto llega a 72 h el 2026-11-09 hacia las 08:00 UTC.
- **Archivos:** `PLAN/notas/T140_api_sin_puerto.md`, `PLAN/T140.md`, `PLAN/T141.md`, `PLAN/T142.md`, `PLAN/{00_MASTER,STATUS,BACKLOG,ESTADO_PROYECTO,BITACORA}.md`, `PLAN/roadmap.html`, `PLAN/status.js`. Sin cambios de código.
- **Pruebas:** no aplica, son documentos. Lo leído: registros de operación y del vigilante, `data/usage`, velas de 1 m y la copia `backups/eim_20261106-000006`, abierta en solo lectura.
- **Abierto:** reconciliar las 5 operaciones (◆ de T142). Qué procesos saturan el equipo (T141). Reproducir el `WinError 64`, porque su relación con el bloqueo es una hipótesis (T140). **El fallo puede repetirse hasta cerrar T140:** el remedio está en `ESTADO_PROYECTO.md` §3.
- **En curso:** T135 (◐), T139 en su propia sesión; T31, T45, T62, T104, T78, T116, T117, T127 y T128 sin cambios aquí.
- **Siguiente paso:** T140, que evita que vuelva a pasar en silencio, y T142, que importa para T31 porque esas posiciones siguen en sus libros.

## 2026-11-06 15:25 UTC · juanpablo-cpu · T140: la API no vuelve a quedarse sin puerto en silencio
- **Hecho:** T140 entera en la rama `claude/t140-puerto`, apilada sobre las fichas de `claude/t140-api-sorda` (PR #214). **Reproducido el fallo:** con el bucle bloqueado y un cliente que corta con RST, Proactor cierra el socket; Selector lo conserva, y se adopta. **El vigilante reinicia** tras 2 min sin escuchar (20 min si no llegó a abrirse), mirando la tabla de puertos y sin conectarse. **Registros** con hora y `vigilante.*` conservados entre arranques. **`continuity check` y el icono** distinguen «sin puerto» de «parada». `RUNBOOK.md` §16.
- **Se aparta de la ficha:** tabla de puertos en vez de conexión TCP, porque una sonda que cortara con RST podría provocar el fallo. La reproducción es `python -m eim.operation.accept_check`, dentro del paquete para que las pruebas la usen, y no un script suelto.
- **Revisión de código:** 10 hallazgos: 4 corregidos (falso «sin puerto» durante 15 min tras una parada, en el check y en el icono; documentación equivocada; prueba que no cubría `anyio`), 5 sin aplicar, la mayoría en BACKLOG T140, y 1 que no pedía cambios. Mirarlos destapó algo más: `Watchdog` también vigila la captura y los líderes, así que pasar stdout por tubería habría atado la captura de T78 al vigilante; ahora solo lo hace la API.
- **Archivos:** `v2/eim/operation/{port_watch,event_loop,accept_check,watchdog,__main__}.py`, `v2/eim/continuity/check.py`, `v2/scripts/{servicio_continuo,icono_bandeja}.ps1`, `v2/docs/{RUNBOOK,OPERACION}.md`, `v2/tests/operation/test_{port_watch,event_loop,service_logs}.py`, `v2/tests/continuity/test_check.py`, `PLAN/notas/T140_api_sin_puerto.md` §1 y §6, `PLAN/{STATUS,BACKLOG,ESTADO_PROYECTO,BITACORA}.md`, `PLAN/status.js`.
- **Pruebas:** `pytest -q` entero por la cola (`gate-t140`, desde el worktree, 14:59–15:18 UTC): **rc 0, 3 042 pasadas, 8 omitidas, 0 fallos**, una pausa de 125 s; `ruff` limpio. Ensayo con la API real en el puerto 18140 sobre datos vacíos: rutas, WebSocket, un ciclo de análisis, 60 RST sin perder el puerto y parada con `detener_servicio.ps1 -SoloCon`. **No probado:** el relanzamiento con `servicio_continuo.ps1` ni horas seguidas con Selector.
- **Medido:** la falta de puerto no alteró T31 (665 ciclos, reconciliación bien en los 665, capital igual). Otra sesión lo midió y reprodujo el fallo por su cuenta; ciclos, decisiones y capital se recontaron aquí.
- **Captura T78, con posible responsabilidad de esta sesión:** la hora 14 salió incompleta y la racha de 6 h volvió a 0. Hay un silencio a las 14:34 ajeno a la carga, pero la tanda de las 14:39–14:40 empieza 4 s después de mi `git worktree add`, y mi ensayo coincide con otro hueco a las 14:57. No se puede aislar la causa (nota §6). La cola pausó el gate a las 15:14 por 2 huecos más.
- **Abierto:** fusionar #214 y este trabajo. **Desplegar:** reiniciar vigilante y API (◆ permiso), porque hasta entonces el fallo puede repetirse. Leer el QC de la hora 15.
- **En curso:** T135 (◐), T139 en su PR #212; T31, T45, T62, T104, T78, T116, T117, T127 y T128 sin cambios aquí.
- **Siguiente paso:** el despliegue de T140 y después T142, que es lo que sí toca a los libros de T31.
## 2026-11-06 14:15 UTC · juanpablo-cpu · T139 cerrada: la búsqueda de entradas se para
- **Hecho:** el usuario delegó la ◆ de cierre («toma tu la mejor decision») y Claude decidió cerrar con P1, aplicando la regla de parada que el usuario hizo vinculante antes de calcular. Seguir `flujo_sigue@4h` habría sido una excepción justo ante un resultado cercano. T139 a ☑. Se trajo `origin/main` (T135) a mano, porque `sync_with_base_branch` falló con «Committer identity unknown»; conflictos solo en `BACKLOG`, `ESTADO_PROYECTO` y `status.js`.
- **Archivos:** `PLAN/{T139,STATUS,BACKLOG,ESTADO_PROYECTO,BITACORA}.md`, `PLAN/notas/T139_entradas.md`, `PLAN/{roadmap.html,status.js}`.
- **Pruebas:** `ruff` limpio y gate completo por la cola sobre el código fusionado: `gate-t139`, rc 0, **3 054 pasadas, 8 omitidas, 0 fallos**, 1 105 s, sin pausas. Contadas en el registro de puntos, porque `addopts = "-q"` más `-q` oculta el resumen (BACKLOG T139 (10)).
- **Gate y racha de T78:** se corrió a sabiendas con la racha en 5 h, porque era lo más barato que iba a estar. **La hora 13 salió completa,** con libro 1,0 y sin huecos. La hora 05, la que dejó abierta la sesión de T135, también. Con estas van cuatro horas de gate sanas y una rota; el registro está en `ESTADO_PROYECTO` §3.
- **T78:** con `mark` recalificado, la racha llegó a 21 h (2026-11-05T09 → 2026-11-06T05) y se rompió en las horas T06 y T07, sin ningún trabajo en la cola; causa sin investigar (BACKLOG). La actual va en 6 h desde T08 y T78 se cumple como pronto al cerrar la hora 2026-11-09T07 UTC. No se aplicó `--requalify --apply`.
- **Abierto:** PR #212 sin fusionar. ◆ del usuario, posterior a esta: para qué sirve entonces el sistema. La API escucha desde las 13:51 UTC y `/v2/health` da 200 (comprobado a las 14:48 UTC); el diagnóstico y las fichas están en el PR #214 y el fallo puede repetirse hasta desplegar T140. **Corrección:** una versión anterior de esta línea decía que seguía caída a las 14:09 UTC, por una prueba mía contra `/api/health`, ruta que no existe y da 404. Los 9 intentos entran en el registro al primer reinicio de la API después de fusionar este PR: el de las 13:51 fue sin ellos.
- **En curso:** T31, T45, T62, T78, T104, T116, T117, T127, T128, T135.
- **Siguiente paso:** fusionar con permiso del usuario, y traer `main` a la carpeta principal, hoy en `b935cde`, sin reiniciar nada que no se decida aparte.
## 2026-11-06 20:00 UTC · juanpablo-cpu · T141: quién ahoga a la API, y opciones para decidir
- **Hecho:** el registro de consumo identifica a los programas ajenos que pasan de un umbral, por árbol para que un conjunto de trabajadores cuente como uno, con su orden recortada y sin secretos y su carpeta (`usage_foreign.py`). También guarda los fallos de página y la edad del latido. `usage incidents` cruza cada ciclo lento, reinicio y arranque lento con el consumo. `usage_alert.py` avisa con umbrales medidos. Informe con opciones en `PLAN/notas/T141_carga_ajena.md`.
- **Hallazgos:** (1) 4 de los 5 bloqueos coinciden con scripts de `OPERACION/PROTOTIPO` con 4–7 procesos, por hora y número de procesos (`--procesos 7` lanzado en el mismo segundo que el último latido de las 01:25:47); el quinto fue memoria acumulada. La cola no estuvo en ninguno. Es indicio fuerte, sacado de los registros de las sesiones, no lectura directa. (2) **Todo el EIM, captura incluida, corre con prioridad de memoria 2 y E/S baja;** los programas del usuario, con 5 y normal. (3) La CPU llena no dañó a la captura y la presión de memoria sí, con 3 horas incompletas: correlación con pocas horas. (4) El arranque de 7 min hace el mismo trabajo a menos del 9 % de un núcleo.
- **Aviso, repasado sobre 4,6 días con el código real:** los 3 reinicios, con 644, 2 705 y 967 s de margen; 8 de 10 ciclos de más de 120 s; 2,4 avisos al día. La condición de latido no se pudo repasar. La revisión de código encontró que un silencio de 30 min entre avisos dejaba sin notificar el tramo previo al reinicio de las 04:14: se quitó.
- **Archivos:** `v2/eim/operation/{usage,usage_win,usage_roles,usage_foreign,usage_alert,usage_incidents}.py`, `v2/tests/operation/test_usage_{foreign,alert,incidents}.py`, `v2/eim/observability/catalog/components_flow.py`, `v2/eim/continuity/inventory.py`, `v2/docs/{OPERACION,ALMACENAMIENTO}.md`, `CLAUDE.md`, `PLAN/notas/T141_carga_ajena.md`, `PLAN/{STATUS,BACKLOG,ESTADO_PROYECTO,BITACORA}.md`, `PLAN/{roadmap.html,status.js}`.
- **Pruebas:** `ruff` limpio y gate completo por la cola: `gate-t141`, rc 0, **3 102 pasadas, 8 omitidas, 0 fallos**, 965 s, sin pausas. Revisión de código a nivel medio: 10 hallazgos, corregidos. Una muestra real con `usage run --once`, sin escribir nada. Sin notificación real ni prueba desde la sesión 0. Cambios de prioridad probados solo en un proceso hijo propio.
- **Abierto:** T141 sigue ◐. Falta fusionar, reiniciar el registro de consumo (pide permiso; no toca la captura) y medir 3 días, hasta el 2026-11-10 si es hoy. Opciones ◆A–◆E del usuario. **Ninguna prioridad cambió y no se reinició nada.** No editados, por ser de T140: `watchdog`, `__main__`, `continuity/check`, los scripts y `RUNBOOK`.
- **En curso:** T140 en su sesión; T31, T45, T62, T78, T104, T116, T117, T127, T128, T135.
- **Siguiente paso:** con el registro ya reiniciado, `python -m eim.operation.usage incidents --days 7`. El usuario decidió ◆A y ◆B justo después: entrada siguiente.
## 2026-11-06 19:55 UTC · juanpablo-cpu · T142: las 5 comprobadas, efecto medido y causa arreglada
- **Hecho:** las 5 operaciones comprobadas una por una con velas de 1 min y trades de la captura: son falsos positivos y el recálculo las cierra con +22,22 USDT, que **ya están en el libro fijo**, porque `_record_ledger` corre antes que la pasada que las congela. Medida la distorsión reconstruyendo los libros con y sin ellas, hasta 2026-11-06 00:00 UTC: **16 entradas no tomadas y −167,10 USDT** (Moderado +17,30, Agresivo −171,26, PPP −13,14). La congelación favoreció a estos libros, y eso es suerte de la muestra. Arreglada la causa: el diario espera a tener las 15 velas de 1 min antes de guardar lo que dependa de esa vela de 15 m. El efecto va en los informes de T31 de este equipo.
- **Archivos:** `v2/eim/paper/{protection_settle,protection_ops}.py` (nuevos), `v2/eim/paper/{protection_sync,protection_desk,desk,ladder_floor}.py`, `v2/eim/operation/distortions.py` (nuevo), `v2/eim/operation/{report,weekly,supervisor}.py`, `v2/tests/paper/{test_protection_settle,test_t142_real_cases}.py`, `v2/tests/operation/test_distortions.py`, `v2/tests/fixtures/paper/t142_cases.json`, `PLAN/notas/T142_posiciones_fantasma.md`, `PLAN/{T31,STATUS,BACKLOG,ESTADO_PROYECTO,BITACORA}.md`, `PLAN/status.js`.
- **Pruebas:** `ruff` limpio y gate por la cola: `gate-t142`, rc 0, **3 093 pasadas, 8 omitidas, 0 fallos**, 1 075 s, sin pausas. Tras el gate solo cambió una cifra en un texto de `distortions.py` y se repitió su prueba. Casos reales del 31-oct y de los dos grupos del 4-nov, con velas de 1 min incompletas y completas: sin congelar y sin stop bajado; sin la espera reproducen el mismo escalón, stop y hora que el diario real. Huellas idénticas a `main` con `PYTHONHASHSEED=0`: 4 perfiles, volcados, mecánica y 104 versiones de T49. Libros A y B idénticos entre `main` y la rama. `code-review` (high): 9 hallazgos, 6 corregidos y 3 anotados.
- **Sin escribir en `data/paper.duckdb`:** todo sobre copias de `backups/eim_20261106-000006` en el directorio temporal de la sesión.
- **Abierto:** **las 5 siguen congeladas.** Falta, con permiso del usuario: fusionar, reiniciar la API y reconciliar (◆). Al hacerlo, poner `t1` en `distortions.py` y repetir la medida. Lo dejado fuera está en BACKLOG T142, sobre todo que el libro fijo no pasa por la espera (no observado: 91 de 91 filas coinciden).
- **En curso:** T142 (◐), T140 y T141 en sus sesiones; T31, T45, T62, T78, T104, T116, T117, T127, T128 y T135 sin cambios aquí.
- **Siguiente paso:** decisión del usuario sobre el PR de T142, y coordinar el reinicio con T140 y T141 para reiniciar la API una sola vez.

## 2026-11-06 19:20 UTC · juanpablo-cpu · T140: trae main y queda lista para el PR
- **Hecho:** se fusionaron #212 (T139) y #214 (las fichas), así que la rama trajo `main`. Solo chocaban `PLAN/{BACKLOG,STATUS,ESTADO_PROYECTO}.md` y `PLAN/status.js`: se conservó lo de ambos lados. Ningún archivo de código se solapa con T139.
- **Captura T78:** la hora 15, la del gate de T140, salió completa (libro útil 99,5 %) pese a sus 2 huecos, y la 16 también (1,0). La racha cuenta desde la 15, iba en 3 h a las 19:11 UTC y T78 se cumple como pronto al cerrar 2026-11-09T14 UTC.
- **Pruebas:** tras traer `main` se repitieron `ruff` y las pruebas de T140 y de continuidad, porque el resto no comparte código; la de los usos de `asyncio` que Selector no admite ya recorre también el código de T139. El gate completo es el de antes de traer `main` (`gate-t140`).
- **Abierto:** fusionar este PR. **Desplegar:** reiniciar vigilante y API (◆ permiso); la API sigue con el proceso de las 13:51 UTC y el fallo aún puede repetirse.
- **En curso:** T135 (◐); T31, T45, T62, T104, T78, T116, T117, T127 y T128 sin cambios aquí.
- **Siguiente paso:** el despliegue de T140 y después T142.
## 2026-11-06 20:15 UTC · juanpablo-cpu · T141: el usuario decide ◆A y ◆B, y se aplican
- **Hecho:** ◆A, regla en `~/.claude/CLAUDE.md`, fuera del repositorio: lo pesado que se lance desde sesiones de Claude va por la cola y con 2 procesos como máximo; la orden se probó desde otra carpeta. ◆B, memoria y E/S de `hft_collector` y `liq_collector` de 2 y baja a **5 y normal**, a las 20:01:48 UTC, en marcha y sin reiniciar, comprobado hilo a hilo. `priority.apply_role` lo repite al arrancar. Herramienta nueva: `python -m eim.operation.priority_memory show|apply`. Se trajo `origin/main` (T140) a mano: `sync_with_base_branch` falló con el mismo «Committer identity unknown»; conflictos solo en `ESTADO_PROYECTO`, `STATUS` y `status.js`.
- **Sin tocar:** la API y los demás servicios siguen en memoria 2 y E/S baja, a propósito; hay pruebas que fallan si suben. No se reinició nada.
- **Corrección:** el informe decía que T78 podía cumplirse hacia el 2026-11-09 08:00 UTC. La racha se rompió en la hora T14 del 6-nov, también con el criterio recalificado, y va desde T15: como pronto al cerrar la hora 2026-11-09T14 UTC.
- **Archivos:** `v2/eim/operation/{priority,priority_memory}.py`, `v2/tests/operation/{test_priority,test_priority_memory}.py`, `v2/docs/OPERACION.md`, `PLAN/notas/T141_carga_ajena.md`, `PLAN/{STATUS,BACKLOG,ESTADO_PROYECTO,BITACORA}.md`, `PLAN/{roadmap.html,status.js}`; fuera del repositorio, `~/.claude/CLAUDE.md`.
- **Pruebas:** `ruff` limpio y gate completo por la cola antes de traer T142: `gate-t141-b`, rc 0, **3 154 pasadas, 8 omitidas, 0 fallos**, 1 471 s, con 1 pausa de 95 s (1 hueco nuevo en la captura; la hora 20 salió completa). Auditoría de la captura antes y después en el informe.
- **Abierto:** T141 sigue ◐. Falta fusionar el PR #216 y reiniciar el registro de consumo (pide permiso) y medir 3 días. **La mejora de ◆B no está demostrada:** hace falta un episodio en el que la API caiga y la captura no. Si la captura se reinicia antes de desplegar, vuelve a memoria 2. Las sesiones ya abiertas no leen la regla de ◆A.
- **En curso:** T31, T45, T62, T78, T104, T116, T117, T127, T128, T135, T141.
- **Siguiente paso:** fusionar con permiso del usuario, y después `python -m eim.operation.usage incidents --days 7`.
## 2026-11-06 20:25 UTC · juanpablo-cpu · T142: desplegada y las 5 reconciliadas, con una sexta congelada
- **Hecho, con permiso del usuario («Sí, los tres»):** PR #217 fusionado (`b1a0a11`), carpeta principal al día, reinicio de la API (solo la hija de `uvicorn`, a las 20:04:33 UTC) y las 5 reconciliadas a las 20:07 UTC con `--decision recalculo`. Cerradas en el diario al precio previsto.
- **Efecto real en el capital realizado:** Moderado +17,79, Agresivo −147,51, PPP −13,14 USDT. 18 entradas nuevas en el libro fijo, marcadas `retro`. Antes de reconciliar, las 390 operaciones eran iguales con el código viejo y el nuevo.
- **No previsto:** al bajar el capital de Agresivo, su única operación abierta (`15m:1793981700000:agente_technical`) quedó con otra cantidad (0,125 frente a 0,122) y se congeló a las 20:08 UTC. La nota no lo había previsto. El permiso cubría las 5, así que no se ha tocado.
- **Coordinación:** la sesión de T140 esperó a la reconciliación para reiniciar vigilante y API; se le avisó de que al arrancar debe salir 1 alerta, no 5.
- **Archivos:** `v2/eim/operation/distortions.py`, `v2/tests/operation/test_distortions.py`, `PLAN/notas/T142_posiciones_fantasma.md`, `PLAN/{STATUS,BACKLOG,ESTADO_PROYECTO,BITACORA}.md`, `PLAN/status.js`.
- **Pruebas:** comparación de libros antes y después por la API. Gate por la cola sobre T140 + T142 juntas: `gate-t142-cierre`, rc 0, 3 129 pasadas, 8 omitidas, 0 fallos, 1 100 s, sin pausas.
- **Abierto:** permiso para reconciliar la sexta (◆); hasta entonces T142 queda ◐. Comprobar «sin alertas al arrancar» cuando no quede ninguna congelada.
- **En curso:** T142 (◐), T141 en su PR #216; T31, T45, T62, T78, T104, T116, T117, T127, T128 y T135 sin cambios aquí.
- **Siguiente paso:** decisión del usuario sobre la sexta.
## 2026-11-07 02:40 UTC · juanpablo-cpu · T142: la sexta reconciliada, 0 congeladas
- **Hecho:** con permiso del usuario, reconciliada `agresivo|BTCUSDT|BTCUSDT:15m:1793981700000:agente_technical` a las 02:33 UTC. **0 congeladas y 0 alertas de protección activas.** Cerró en su stop, 76 159,55, con −93,75 USDT (−1,17 R). La foto de antes y la de después solo difieren en esta operación: sin más cascadas.
- **Mientras esperaba:** el precio tocó su stop el 2026-11-06 a las 22:02 UTC y siguió abierta. El permiso llegó antes, pero la sesión se cortó y el usuario pidió repetirlo; se comprobó el estado y solo entonces se reconcilió.
- **Archivos:** `v2/eim/operation/distortions.py`, `v2/tests/operation/test_distortions.py`, `PLAN/notas/T142_posiciones_fantasma.md`, `PLAN/{T31,STATUS,BACKLOG,ESTADO_PROYECTO,BITACORA}.md`, `PLAN/status.js`.
- **Pruebas:** tras el gate combinado solo cambiaron un texto y `t1` de `distortions.py` y documentos: `ruff` limpio y `tests/operation/test_distortions.py`.
- **«Sin alertas al arrancar», comprobado:** la sesión de T140 reinició el vigilante y la API a las 02:35:48 UTC, para desplegarla. A las 02:37:08 `/v2/paper` respondía con 0 congeladas, sin recuperaciones, 0 alertas desde el arranque y ninguna activa, y con el mismo capital en los 4 perfiles. T142 ☑.
- **Abierto:** PR #218, a la espera de permiso para fusionar: solo lleva la distorsión cerrada y documentos.
- **En curso:** T141 en su PR #216, que ahora tiene conflictos; T31, T45, T62, T78, T104, T116, T117, T127, T128 y T135 sin cambios aquí.
- **Siguiente paso:** fusionar #218 con permiso del usuario y traerlo a la carpeta principal; no hace falta reiniciar para esto hasta el próximo arranque, porque el texto del informe se carga al arrancar.

## 2026-11-07 02:45 UTC · juanpablo-cpu · T140 desplegada
- **Hecho:** vigilante y API reiniciados con permiso del usuario, a las 02:35–02:36 UTC, tras esperar a que T142 acabara de reconciliar y a un gate de T141. El puerto volvió a escuchar a los 42 s, con `--loop eim.operation.event_loop:selector_loop`. Detalle en `PLAN/notas/T140_api_sin_puerto.md` §7.
- **Comprobado:** 2 ciclos correctos con el mismo capital, WebSocket con ticks, 0 alertas de protección al arrancar, los otros 15 procesos con los mismos PID y `continuity check` dice que la API escucha. Registros anteriores conservados y los nuevos con hora.
- **Tropiezos:** la comprobación previa del despliegue traía `main` aunque no parara nada, y así entró T142 en la carpeta antes de saberlo; T142 reinició la API por su cuenta y con permiso a las 20:04 UTC, justo entonces. Después, mi sesión se cortó esperando un gate y el reinicio se retrasó 6 h. En ese tiempo la API siguió sin protección, sin que pasara nada.
- **Archivos:** `PLAN/{STATUS,ESTADO_PROYECTO,BITACORA}.md`, `PLAN/status.js`, `PLAN/notas/T140_api_sin_puerto.md` §7, `v2/docs/RUNBOOK.md`. Sin código, así que no se repitió el gate.
- **Abierto:** leer la hora 02 de la captura, la del reinicio. Vigilar la API con Selector unos días.
- **En curso:** T31 (→ 2026-11-27), T45, T62, T104, T78, T116, T117, T127 y T128 sin cambios aquí.
- **Siguiente paso:** los PR #218 (T142) y #216 (T141) siguen abiertos en sus sesiones.
## 2026-11-07 02:55 UTC · juanpablo-cpu · T141: auditoría de ◆B y rama al día
- **Hecho:** auditoría de la captura hasta las 02:44 UTC: racha de 11 h (T15 a T01), horas T20 a T01 completas, cola máxima 100 y sin descartes. ◆B sigue aplicada (mismo arranque de la captura, todos los hilos en 5 y normal) y la API, ya con T140 y otro PID, sigue en 2 y baja. Ningún bloqueo desde el cambio. **◆A ya se usó:** `24_facetas_radio.py --procesos 2` fue por la cola y esta lo pausó dos veces por RAM. La rama trae `main` con T140 y T142, a mano y con conflictos solo en `ESTADO_PROYECTO`, `STATUS` y `status.js`.
- **Sin hacer:** el registro de consumo sigue con el código viejo, sin órdenes ni aviso, hasta fusionar y reiniciarlo. La sesión anterior se cortó con el gate ya terminado y la auditoría sin rellenar; los dos procesos en segundo plano no dejaron nada a medias.
- **Archivos:** `PLAN/notas/T141_carga_ajena.md`, `PLAN/{STATUS,ESTADO_PROYECTO,BITACORA}.md`, `PLAN/{roadmap.html,status.js}`.
- **Pruebas:** tras traer T142, `ruff` y `tests/operation` por la cola: rc 0, 179 pasadas, 0 omitidas, 0 fallos, 135 s, sin pausas. **No se repitió el gate completo**, para no cargar el equipo con la racha de T78 en marcha: `gate-t142-cierre` y `gate-t141-b` salieron verdes por separado y esta fusión no toca código en conflicto.
- **Abierto:** fusionar el PR #216 y reiniciar el registro de consumo, con permiso del usuario. ◆C, ◆D y ◆E sin decidir.
- **En curso:** T31, T45, T62, T78, T104, T116, T117, T127, T128, T135, T141, T142.
- **Siguiente paso:** con el registro reiniciado, `python -m eim.operation.usage incidents --days 7` hasta el 2026-11-10.
## 2026-11-07 03:10 UTC · juanpablo-cpu · T141 desplegada: el registro ya nombra a los procesos
- **Hecho, con permiso del usuario:** PR #216 fusionado a las 03:00:21 UTC y carpeta principal en `85f02f5`. Se detuvo solo el registro de consumo (PID 7368) a las 03:00:45 y se volvió a lanzar la tarea programada, que solo completa lo que falta: nació a las 03:00:50 (PID 30816), en la sesión 1, con prioridad 6, memoria 2 y E/S baja como antes. La captura, la API y los demás servicios conservaron sus PID.
- **Comprobado en el servicio real:** un proceso de prueba de 350 MB salió en `data/usage` con su orden (`python.exe -I prueba_t141.py --procesos 1 --token ***`) y su carpeta; la clave falsa no quedó ni allí ni en el registro de operación. Las muestras traen `api_beat_age_s` y `faults`, cada 30 s, sin errores en `consumo.err.log`. Captura en el arranque de siempre, cola 0 y sin descartes; recolectores aún en memoria 5 y E/S normal.
- **Archivos:** `PLAN/notas/T141_carga_ajena.md`, `PLAN/{STATUS,ESTADO_PROYECTO,BITACORA}.md`, `PLAN/{roadmap.html,status.js}`. Sin cambios de código.
- **Pruebas:** no aplica, son documentos; lo probado es el servicio desplegado (arriba). Sin notificación real ni prueba desde la sesión 0.
- **Abierto:** medir hasta el 2026-11-10 03:00 UTC y cerrar T141. La mejora de ◆B sigue sin demostrarse. ◆C, ◆D y ◆E sin decidir.
- **En curso:** T31, T45, T62, T78, T104, T116, T117, T127, T128, T135, T141.
- **Siguiente paso:** a partir del 2026-11-10 03:00 UTC, `python -m eim.operation.usage incidents --days 7` y completar el informe, nombrando los procesos de cada bloqueo o diciendo que no los hubo.

## 2026-11-07 03:45 UTC · juanpablo-cpu · T135 reabierta: A/B de M8 congelado, empieza el 2026-11-08
- **Hecho:** el usuario pidió reabrir T135 midiendo M8. Se congeló un A/B prospectivo emparejado: tabla de 42 estrategia@marco, inicio 2026-11-08 00:00 UTC y mínimos de 4 semanas, 315 operaciones y 21 días. Sin adoptar nada.
- **Cambio de diseño:** se había hablado de un perfil aparte, y se descartó al leer §5.4: el criterio 7 compara con T134, que midió otra población. Un perfil tampoco era necesario y tocaba T31. El A/B corre sobre una copia, sin reiniciar nada.
- **Comprobado:** reproduce T134 hasta el último decimal (E[R] −0,10448885991888382, n 29 841). La potencia por día da 21 días y un efecto detectable de 0,042 R con 28. La cadena corrió con datos reales en un ensayo que **no cuenta** como resultado.
- **Revisión de código:** 10 hallazgos, 8 corregidos, entre ellos el veredicto, que se podía cambiar con solo seguir corriendo, y la mecánica sin fijar. Los otros 2, en BACKLOG T135. Por eso se congeló de nuevo: el primer archivo nunca se confirmó ni contó ninguna idea.
- **Captura T78:** la hora 02 de hoy, la del reinicio de T140, salió completa (libro útil 1,0).
- **Archivos:** `v2/eim/paper/exits/ab_live.py`, `v2/eim/paper/exits/versions/t135_ab_m8_v1.json`, `v2/scripts/t135_ab_m8.py`, `v2/scripts/t135_ab_semanal.ps1`, `v2/reports/t135_regress.json`, `v2/tests/paper/exits/test_ab_live.py`, `v2/tests/operation/test_service_logs.py`, `PLAN/notas/{T135_ab_m8,T135_motor}.md`, `PLAN/{STATUS,BACKLOG,ESTADO_PROYECTO,BITACORA}.md`, `PLAN/status.js`.
- **Pruebas:** `pytest -q` entero por la cola (`gate-t135-m8`, 03:36–03:54 UTC, desde el worktree): **rc 0, 3 215 pasadas, 8 omitidas, 0 fallos**, sin pausas; `ruff` limpio. La hora 03 de la captura, la del gate, aún no tenía QC.
- **Abierto:** ◆ la tarea semanal de los lunes, que pide permiso. Sin ella, la pasada se lanza a mano.
- **En curso:** T135 (◐); T31 (→ 2026-11-27), T45, T62, T104, T78, T116, T117, T127 y T128 sin cambios aquí.
- **Siguiente paso:** primera pasada a partir del 2026-11-09 y veredicto como pronto el 2026-12-06.

## 2026-11-07 04:05 UTC · juanpablo-cpu · T135: tarea semanal del A/B instalada
- **Hecho:** PR #221 fusionado y carpeta principal al día; solo entraron archivos nuevos que nada del vivo importa, así que no hizo falta reiniciar. Con permiso del usuario, tarea «EIM - informe semanal A-B M8 (T135)»: lunes 02:30 UTC, primera el 2026-11-09. Corre con la sesión del usuario iniciada y se pone al día si se perdió la hora.
- **Comprobado:** pasada completa con `v2\scripts\t135_ab_semanal.ps1`: copia actualizada, cobertura 100 %, informe EN CURSO con 0 ideas y su línea en el registro. Ese informe es anterior al inicio y no cuenta. La tarea programada en sí aún no se ha disparado.
- **Captura T78:** la hora 03, la de `gate-t135-m8`, aún no tenía QC. La racha iba en 12 h, con la hora 02 como última auditada.
- **Archivos:** `PLAN/{ESTADO_PROYECTO,BITACORA}.md`, `PLAN/notas/T135_ab_m8.md`. Sin código.
- **Abierto:** mirar el primer informe el 2026-11-09 y su línea en el registro. Veredicto como pronto el 2026-12-06.
- **En curso:** T135 (◐); T31 (→ 2026-11-27), T45, T62, T104, T78, T116, T117, T127 y T128 sin cambios aquí.
- **Siguiente paso:** nada en T135 hasta el veredicto. Las cifras semanales son provisionales.
