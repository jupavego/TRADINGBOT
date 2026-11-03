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

## 2026-10-30 23:40 UTC · juanpablo-cpu · T125/T117 llegada del equipo y simulacro
- **Hecho:** diagnóstico de `DESKTOP-93R810K`. El clon está en `C:\Users\jo\Desktop\JP\TRADINGBOT`, con `main` 19 commits atrasado y nada sin subir: las ramas locales `t106`/`t107` ya están en `origin/main`, y solo quedan sin seguir `.claude/settings.local.json` y el informe propio `v2/reports/operation/semana_2026-W43.*`. Es el **caso A** (historial propio). El modo automático de T61 apuntaba al repo viejo `jupavego/eim-shared-data` (ramas `machine/juanpablo` y `machine/juanpablo-cpu`). No hay `D:/eim-bots`. Corrían el recolector de microestructura, la captura HFT y Vite; la API, la operación y los líderes estaban parados (último latido de la operación: 2026-10-29 16:31 UTC). La tarea «EIM - servicio continuo (broker simulado)» arrancaba al iniciar sesión.
  - Respaldo en `%USERPROFILE%\EIM_respaldos\20261030-175903`. `-SoloRespaldo` se paró en su verificación (la captura HFT escribe en `micro_hft`, BACKLOG T125 (1)); los mismos pasos, completados a mano, dan 346 archivos y 432 642 449 B idénticos sin `micro_hft`, y el bundle de ramas verificado. Copia del sistema: `eim_20261030-230202` **íntegra**.
  - `git pull --ff-only` (`ebf3900` → `f44cae5`). Locks sin cambios: el simulacro de pip no instala nada, `pip check` y `npm ls` salen bien y se reinstaló el paquete editable; `npm ci` no se ejecutó porque Vite estaba en marcha.
  - Con permiso del usuario: tarea de inicio **desactivada**, `data/share_repo` apartado a `share_repo.jupavego-20261030` (BACKLOG T125 (2)), `share setup --git-url https://github.com/Santivego/eim-shared-data.git --machine juanpablo-cpu`, `export` → rama `machine/juanpablo-cpu` en Santivego (`0105753`, `20261030T231112Z`, 29 s) y `import` en simulacro (100 s).
- **Archivos:** `PLAN/{BITACORA,ESTADO_PROYECTO,BACKLOG}.md`.
- **Pruebas:**
  - `backup verify` → 4 bases, 561 909 filas (reports 116 631, paper 18 716, leaders 232 639, obs 193 923).
  - `eim.continuity check` → **CON AVISOS**: 2 archivos sin confirmar y sin copia externa propia; datos, copias, código (`main @ f44cae5`) y seguridad OK.
  - `git ls-remote` de Santivego antes del export: solo `machine/laptop-i6pf9ovp-fce8d9` (identidad libre). Después: más `machine/juanpablo-cpu`. La rama del repo viejo no cambió (`a54bc4f`).
  - Simulacro desde `laptop-i6pf9ovp-fce8d9` `20261030T030349Z` (nuevas / ya estaban / conflicto / incompat.): reports 12 517 / 589 / 1 242 / 0 · sim_trades 41 / 3 / 1 / 0 · paper_ctx 35 499 / 8 / 3 449 / 0 · val_versions 0 / 191 / 0 / 0 · val_windows 104 / 87 / 0 / 0 · leaders 15 / 0 / 0 / 0 · leader_fills 2 807 174 · leader_funding 35 772 · leader_leverage 4 · leader_positions 35 444 · leader_follow 2 129 264 · leader_recon 87 924 · leader_gaps 16 623 · copy_journal 33 992 (líderes: todo nuevas). **Total: 5 194 373 nuevas, 878 ya estaban, 4 692 en conflicto, 0 incompatibles.** Las bases y los WAL no cambiaron (mismos bytes y fechas).
  - Gate: ruff OK; 2 425 pruebas pasadas, 7 omitidas y 0 fallidas en 13,4 min, con el recolector y la captura HFT en marcha.
- **Abierto:** ◆ revisión del simulacro por el usuario (no se ejecutó `import --apply`). Mientras `share_config.json` apunte a Santivego, abrir la API o los líderes (icono o `servicio_continuo.ps1`) **aplica** la importación sola. Por la cantidad de filas de líderes, aplicar antes a mano con los servicios parados (nota T117 §6.6). Este equipo no tiene copia externa ni Freqtrade.
- **En curso:** T31 (portátil), T45, T78, T104, T116, T117, T119.
- **Siguiente paso:** ◆ visto bueno del simulacro → `import --apply` en `juanpablo-cpu` con los servicios parados; la portátil hace su simulacro sobre `machine/juanpablo-cpu`; decidir si `juanpablo-cpu` opera a diario (reactivar la tarea de inicio e instalar `instalar_copia_externa.ps1`).

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
