# T62 — Auditoría de motores de IA locales (licencia de código y de pesos, seguridad, instalación)
Fecha: 2026-10-30/31 · Método: metadatos vía API de GitHub (`gh api`), PyPI JSON, API de Hugging Face (`/api/models/<repo>`: `sha`, `license`, `gated`, tamaños), biblioteca de Ollama, documentación oficial y términos; clones superficiales aislados **fuera del proyecto** (carpeta temporal de la sesión, solo `grep`/lectura) donde hizo falta mirar telemetría, red al arrancar, `pickle`/`exec`/`trust_remote_code`. **No se instaló ni ejecutó código de terceros para la auditoría** ni se descargaron pesos; lo único ejecutado es lo que ya estaba instalado en `juanpablo-cpu` (Ollama 0.40.11 y su `llama-server`, ffmpeg 9.0.1), y solo en el banco de pruebas. Cinco grupos auditados en paralelo (captación+ASR, escenas+OCR+VLM, motores, LLM+embeddings, marcos), como pide `PLAN/T62.md`.
Limitación: análisis de código por patrones + lectura de los módulos citados, no línea a línea. Las cifras de velocidad o precisión de README y fichas se anotan como «declarado»; las únicas cifras aceptadas son las medidas (`v2/reports/localai/bench_<equipo>.md`).
Las referencias «A §1.2» remiten al grupo A, sección 1, punto 2 (detalle al final, con la evidencia enlazada: archivo:línea en el SHA clonado, LICENSE, fichas de HF y páginas oficiales).

Equipos: el de referencia (mínimo) es la portátil de Santivego (i5-8250U, 7,9 GB, MX130 2 GB); la medición de esta sesión es en `juanpablo-cpu` (i5-6400 4c/4t, 16 GB, GTX 750 Ti 2 GB, driver 582.78). Las dos GPU son Maxwell (CC 5.0).

## 🚩 Alertas (leer primero)
1. **Condiciones de YouTube.** Los ToS (15-dic-2023) prohíben descargar el contenido sin permiso y el acceso por medios automatizados; las Developer Policies (2026-10-15, III.E.1.a, III.I.7, III.E.6, III.I.14) prohíben guardar copias del audiovisual, separar el audio y el *scraping*. `yt-dlp` (audio) y `youtube-transcript-api` (InnerTube no documentado) chocan con esos textos; `captions.download` de la API oficial solo sirve para videos propios (permiso de edición, 200 unidades). **◆ Decidida el 2026-11-07 (delegada por el usuario): se cumplen los Términos.** Sin `yt-dlp` ni `youtube-transcript-api` con YouTube, metadatos con la Data API v3 y transcripción solo de material propio, aportado o con permiso (`v2/docs/SEGURIDAD.md` § «Videos de YouTube»). Detalle: A §1.1, A §3.3.
2. **Ollama habla con `ollama.com` aunque no se abra la app.** `ollama serve` pide recomendaciones de modelos al arrancar y cada 4 h, firmando la petición con la clave de `~/.ollama/id_ed25519` (identificador estable del equipo) (`server/model_recommendations.go:23,26,197-202` en v0.40.11). **Verificado aquí:** `~/.ollama/cache/model-recommendations.json` se reescribió el 2026-10-30 23:05 (-05:00) con solo `serve` en marcha y trae modelos `:cloud`. Se corta con `OLLAMA_NO_CLOUD=1` (línea 189: `refresh` sale antes de pedir nada; verificado en el código). La app de bandeja (`ollama app.exe`) busca actualizaciones cada hora sin forma de apagarlo y tiene un ajuste latente `Survey` = verdadero: **no usarla**, solo `ollama.exe serve`. C §1.1–1.2, 1.7.
3. **El Ollama de `juanpablo-cpu` vive en una unidad de red** (`Z:` = `\\DESKTOP-TVD562Q\USB`). El 2026-10-31 hacia las 07:00 UTC la unidad cayó (el equipo remoto no responde): el servidor siguió contestando `/api/version`, pero **no pudo cargar ningún modelo** (petición de 1 token colgada 150 s, sin proceso `llama-server`). Todo motor va en disco local, con el SHA-256 del instalador verificado. C §1.3 y medición de esta sesión.
4. **El `qwen3:4b` instalado es Qwen3-4B-*Thinking*-2507** (digest `359d7dd4bcda`; verificado aquí: su plantilla abre `<think>` en todo turno del asistente). Razona siempre: para extraer JSON el indicado es `qwen3:4b-instruct` (`0edcdef34593`, Apache-2.0, 2,5 GB). D §1.1.
5. **Licencias de pesos restrictivas (se descartan):** Qwen2.5-3B y Qwen2.5-VL-3B (Qwen RESEARCH, solo no comercial; las 1.5B/7B sí son Apache), Gemma 3/3n y EmbeddingGemma-300m (Gemma Terms + política de uso prohibido, *gated*), Llama 3.2 (Community License + AUP, *gated*), Ministral-8B-2410 (Mistral Research), familia LFM de Liquid AI (no OSI; uso comercial limitado), jina-embeddings-v5 y jina-ocr (CC-BY-NC), alineación española por defecto de WhisperX (VoxPopuli, CC BY-NC). **Gemma 4 pasó a Apache-2.0** (no *gated*), pero E2B ocupa 4,3–4,6 GB: no cabe en el mínimo. B §1.1–1.2, D §1.2–1.7, A §1.4.
6. **Telemetría activada por defecto:** pyannote.audio 4.x (`otel.pyannote.ai`; WhisperX la dispara al usarlo como VAD aunque no diarice), CrewAI (OTLP a `telemetry.crewai.com` desde el `import`, incluido el nombre del modelo), Microsoft Agent Framework (cabecera `User-Agent`), Open WebUI (consulta GitHub; escucha en `0.0.0.0:8080`), PaddleOCR/PaddleX (comprueba HF, AIStudio, ModelScope y BOS y descarga modelos al arrancar). A §1.2, E §1.1, E §1.5, C §1.6, B §1.3.
7. **Pickle y código remoto:** pyannote (`weights_only=False`), `torch.hub.load` de silero-vad en WhisperX y whisper-timestamped (descarga y ejecuta código de GitHub), bge-m3 solo en `.bin` (pickle), `trust_remote_code` en Florence-2, moondream2, InternVL3.5, MiniCPM-V-4, Granite Vision 4, Phi-4-mini-flash, nomic-embed y arctic-embed-m-v2. **Regla:** pesos solo en GGUF (Ollama/llama.cpp), safetensors u ONNX; nada que ejecute Python del repo de pesos. A §1.3, B §1.4, D §1.8–1.9.
8. **Cadena de suministro:** `litellm` 1.82.7/1.82.8 (PyPI, 2026-03-24) llevaban un ladrón de credenciales; no se instala nunca (solo entra como extra de CrewAI/instructor). `pydantic-ai`: 20 avisos GHSA en 2026 (ninguno en el camino «Agent + Ollama + output_type» sin herramientas), de 2.59 a 2.64 en 9 días: fijar la versión exacta y usar solo `pydantic-ai-slim` (el paquete completo instala `logfire`). E §1.3, 1.6–1.7.
9. **GPU Maxwell (CC 5.0, MX130 y GTX 750 Ti):** CTranslate2 no la soporta (faster-whisper solo en CPU); Ollama y llama.cpp con CUDA 12 solo vía PTX JIT (driver ≥ 570: aquí 582.78) y CUDA 13 ya la excluye; vLLM exige CC ≥ 7.5. Lo que dé la GPU se mide, no se supone. **Medido (2026-10-31, GTX 750 Ti):** con descarga parcial a la GPU (1,5 GB de VRAM, Vulkan) `qwen3:4b-instruct` genera a ×0,9 de la CPU sola: la GPU no ayuda; todo en CPU. A §1.5, C §1.5.
10. **APIs locales sin autenticación:** Ollama (CORS admite `file://`), `llama-server` (CORS `*` y web UI por defecto; durante la auditoría se vio uno así en el puerto 9931, que ya no escucha), servidor de whisper.cpp (CORS `*` y `/load` sin clave). El banco lanza `llama-server` solo en 127.0.0.1, puerto libre al azar, `--offline --no-webui` y `--api-key` aleatoria. **Medido al instalar (2026-10-31):** el runner que Ollama 0.40.11 lanza por debajo es un `llama-server` en `127.0.0.1:<puerto efímero>` con `--no-webui --offline` pero **sin clave y con CORS `*`** (su registro: «no API key is set and CORS allows all origins»); vive mientras el modelo está cargado, así que una web abierta en el navegador podría usarlo si da con el puerto. Riesgo bajo (puerto al azar, solo con modelo cargado, el modelo no tiene herramientas); mitigación: `OLLAMA_KEEP_ALIVE` corto y, en T63, evaluar `llama-server` propio con clave. C §1.4, A §1.12.
11. **Descargas en ejecución:** `WhisperModel("<nombre>")` llama a `snapshot_download` al instanciarse y el alias `turbo` apunta a un repo que cambió de dueño (mobiuslabsgmbh → dropbox-dash): pesos predescargados con revisión fijada y `local_files_only=True` (el banco ya lo hace). RapidOCR trae sus modelos dentro del *wheel*. A §1.6, B §1.7.
12. **Trampas de instalación:** `scenedetect` arrastra `opencv-python` con GUI (usar `scenedetect-headless` + `opencv-python-headless==4.14.0.94`, o pip instala la 5.0); RapidOCR no declara `onnxruntime`; los builds de FFmpeg de gyan.dev (el instalado aquí) son GPLv3: válido como **proceso externo**, preferible el LGPL de BtbN fijado por *autobuild* + SHA-256. B §1.6, 1.11–1.12.
13. **Ritmo de versiones:** Ollama sacó 0.40.6 → 0.40.13 en 12 días; CTranslate2 4.8.4 tiene 6 días; MiniCPM-V-4.7, MiniCPM-OCR y LFM3-VL tienen < 2 semanas. Se fija versión y SHA y se deja enfriar. C §1.8, A §1.13, B §1.9.
14. **Medido aquí: el filtro de escenas de ffmpeg no ve los cortes de pantalla.** Sobre 36 fotogramas con corte cada 4 s, `select=gt(scene,0.3)` halla el 20 % de los cortes (43 % con 0,05), sin falsos positivos: dos gráficos de fondo oscuro difieren muy poco en luminancia media. **PySceneDetect 0.7.2 (`detect-content` con su umbral por defecto) tampoco: 20 %**, a 2,2 s por minuto de video. Para T66: ajustar el umbral de PySceneDetect o una diferencia de fotogramas propia (p. ej. por cambio del texto de RapidOCR); los videos reales (cámara + pantalla) se miden en T64.
15. **Medido aquí: el VLM pequeño no cabe junto a los servicios.** `qwen3-vl:2b-instruct-q4_K_M` (1,8 GB en disco) lee bien los gráficos (activo y marco 100 %, niveles 89 % en 5 fotogramas), pero su runner llega a **8,8 GB de memoria privada** (4,7 GB residentes) y tarda ~66 s por fotograma, a 1280 px y también reducido a 768 px (la memoria no baja con la resolución). Con la API, la operación en papel y los líderes en marcha el equipo de 16 GB se quedó sin memoria dos veces (consultas de 1 min); el banco ahora corta el VLM si la RAM libre baja de 1,5 GB. En el equipo de referencia (7,9 GB) no entra: el camino de los fotogramas es **RapidOCR (99 % de cifras, 1,5 s, 0,4 GB) + el LLM de texto**; el VLM queda fuera del mínimo hasta medir uno más ligero (T66).

## Resumen de veredictos (por eslabón)
| Eslabón | Usar | Usar (opcional) | Referencia | Descartar |
|---|---|---|---|---|
| Captación | YouTube Data API v3 (metadatos y descubrimiento) · `yt-dlp` 2026.10.26 **condicionado ◆** | `youtube-transcript-api` v1.2.4 · RSS de canal (solo pista: 404 en las pruebas) | — | `captions.download` para canales ajenos (no lo permite) |
| ASR | faster-whisper v1.2.1 + CTranslate2 v4.8.3/4.8.4 (CPU, int8), pesos Systran (MIT) | whisper.cpp v1.9.5 · alineación wav2vec2 en inglés · `jonatasgrosman/…-spanish` | openai/whisper · WhisperX | pyannote (por ahora) · whisper-timestamped (AGPL) · alineación VoxPopuli es (NC) |
| Escenas | `scenedetect-headless` 0.7.2 · `opencv-python-headless` 4.14.0.94 · FFmpeg como proceso externo | — | — | — |
| OCR | RapidOCR 3.10.0 + `onnxruntime` 1.31.1 (PP-OCRv6, Apache) · Tesseract 5.5.3 (ya en la biblioteca) | GLM-OCR 0.9B (`glm-ocr:q8_0`, MIT) | PaddleOCR 3.x · PaddleOCR-VL · MiniCPM-OCR (reevaluar) | `rapidocr_onnxruntime` (legado) · DeepSeek-OCR-2, jina-ocr (NC) |
| Visión-lenguaje | — | **Qwen3-VL-2B-Instruct** (`qwen3-vl:2b-instruct-q4_K_M`, 1,9 GB, Apache) · Qwen3.5-2B/0.8B · Qwen3-VL-4B (solo 16 GB) | Gemma 4 E2B (16 GB) · SmolVLM2 · Florence-2 · moondream2 · MiniCPM-V-4.7 · LFM3-VL · Granite Vision | Qwen2.5-VL-3B (NC) · Gemma 3/3n (*gated*) · InternVL3.5 (código remoto) |
| Motor | **Ollama** v0.40.11 (o 0.40.13), solo `serve`, `OLLAMA_NO_CLOUD=1`, sin app | llama.cpp `llama-server` b12018 (plan B; es lo que Ollama ejecuta por debajo) | Open WebUI (panel manual, `OFFLINE_MODE`, 127.0.0.1) · OpenVINO GenAI · llamafile · ONNX Runtime GenAI | LM Studio (app propietaria) · vLLM (sin Windows, CC ≥ 7.5) · LocalAI (sin Windows, descarga backends) · koboldcpp (AGPL) |
| LLM de texto | **Qwen3-4B-Instruct-2507** (`qwen3:4b-instruct`, 2,5 GB, Apache) | Qwen3-4B-Thinking (instalado) · Qwen3-1.7B · Qwen3.5-4B/2B · Granite-4.1/4.2-3B · Ministral-3-3B · Phi-4-mini | Qwen3-4B (2025) · Gemma 4 E2B · Llama 3.2 · SmolLM3 · LFM2.5 | Qwen2.5-3B (NC) · Gemma 3/3n · Ministral-8B (MRL) · DeepSeek-R1-Distill-1.5B · Phi-4-mini-flash |
| Embeddings (calidad: T71) | Qwen3-Embedding-0.6B · multilingual-e5-small · granite-embedding-97m-multilingual-r2 | bge-m3 (solo vía Ollama) · embeddinggemma-2 (muy reciente) | e5-base · e5-large-instruct · granite-311m-r2 · nomic v2 · arctic-embed | EmbeddingGemma-300m (ToU) · nomic v1.5 (solo inglés) · jina v5 (NC) |
| Marcos | — | `pydantic-ai-slim[openai]` 2.64.0, solo para salida estructurada y solo si mejora a la validación propia | instructor · outlines · Agent Framework (diseño) | LangGraph · CrewAI · AutoGen (archivado) · litellm |

Versiones con SHA de commit o revisión de HF, digests de Ollama y hashes de *wheels*: tablas de cada grupo (abajo).

## Lista aprobada (el usuario la aprobó el 2026-10-31; instalada en `juanpablo-cpu`, `docs/OPERACION.md` §7)
Escrita para el **mínimo** (7,9 GB, ≈ 5 GB útiles con la API de EIM en marcha, un modelo a la vez). Un equipo con más RAM solo cambia el modelo elegido, no la arquitectura.

| Etapa | Propuesta | Licencia (código / pesos) | Versión fijada | Tamaño declarado |
|---|---|---|---|---|
| Motor | Ollama, instalado en disco local (`ollama-windows-amd64.zip`, sin app de bandeja), `OLLAMA_NO_CLOUD=1`, `OLLAMA_HOST=127.0.0.1:11434`, `OLLAMA_MODELS` en `EIM_LOCALAI_DIR` | MIT | v0.40.11 · `675150d6` (la medida); subir a 0.40.13 solo tras repetir el banco | 1,60 GB |
| Motor (plan B) | llama.cpp `llama-server`, build CPU | MIT | b12018 · `8956c769` (`win-cpu-x64.zip`) | 24,6 MB |
| LLM | `qwen3:4b-instruct` | Apache-2.0 / Apache-2.0 | digest `0edcdef34593` · HF `cdbee75f` | 2,5 GB |
| LLM respaldo | `qwen3:1.7b` | Apache-2.0 | digest `8f68893c685c` | 1,4 GB |
| VLM | `qwen3-vl:2b-instruct-q4_K_M` | Apache-2.0 / Apache-2.0 | digest `afc393e3572c` · GGUF oficial `52d6c8ff` | 1,9 GB |
| OCR | RapidOCR + onnxruntime; Tesseract como segundo lector | Apache-2.0 | rapidocr 3.10.0 · onnxruntime 1.31.1 · Tesseract 5.5.3.20260724 | ≈ 30 MB (estimado: los modelos van en el *wheel*) |
| Escenas | `scenedetect-headless` + `opencv-python-headless` | BSD-3 / Apache-2.0 (+ LGPL de FFmpeg empaquetado) | 0.7.2 · 4.14.0.94 | ≈ 60 MB (estimado) |
| ASR | faster-whisper en CPU int8: `Systran/faster-whisper-small` y un turbo (repo y SHA fijados) | MIT / MIT | faster-whisper 1.2.1 · CTranslate2 4.8.3 | 0,48 GB · 1,6 GB |
| Embeddings | `qwen3-embedding:0.6b` (Ollama) + `multilingual-e5-small` (ONNX), solo para T71 | Apache-2.0 / MIT | digest `ac6da0dfba84` · HF `614241f6` | 0,64 GB · 0,12 GB |
| Salida estructurada | validación propia (pydantic + `format`); Pydantic AI solo si el banco muestra que mejora | MIT | pydantic-ai-slim 2.64.0 | ≈ 26 paquetes |
| Captación | Data API v3 para metadatos; subtítulos/audio según la postura ◆ | — | — | — |

**Cómo se decide «entra»:** la licencia y la auditoría lo habilitan; la medición en el banco (`v2/reports/localai/bench_<equipo>.md`) en el equipo de referencia decide entre los que caben.

### Medido en `juanpablo-cpu` (2026-10-31, con la API, la operación en papel y los líderes en marcha)
Detalle en `v2/reports/localai/bench_juanpablo-cpu.md`. Falta el equipo de referencia (7,9 GB), que es el que decide.

| Etapa | Resultado | Lectura |
|---|---|---|
| LLM `qwen3:4b-instruct` | JSON válido 100 %, precisión 79 %, recall 85 %, 0 niveles inventados (10 casos es/en con 2 inyecciones), 13 s/caso; prompt ≈ 45 tok/s, generación ≈ 8 tok/s; pico 4,5 GB | **Entra.** El banco corrige el prompt cacheado de Ollama (inflaba ×13 el prompt tok/s) |
| Ollama ↔ llama.cpp (mismo GGUF, CPU) | prompt 43 ↔ 41 tok/s, generación 8,1 ↔ 7,4, pico 3,4 ↔ 2,6 GB, misma calidad | Ollama queda; llama.cpp es plan B real (menos RAM) |
| GPU GTX 750 Ti | ×0,93 (más lenta que la CPU sola) | Todo en CPU (alerta 9) |
| Pydantic AI 2.64.0 ↔ validación propia | misma calidad (79/85 %), 12,9 ↔ 13,5 s/caso | **No aporta**: no se añade la dependencia; se queda la validación propia |
| Escenas | ffmpeg 20–43 %, PySceneDetect 0.7.2 20 % (umbral por defecto), sin falsos positivos | Ninguno sirve tal cual para pantallas → T66 (alerta 14) |
| OCR | RapidOCR 99 % de cifras (1,5 s/fotograma, 0,44 GB) ↔ Tesseract 57 % (1,1 s) | **RapidOCR**; Tesseract fuera del camino de video |
| VLM `qwen3-vl:2b-instruct` | activo/marco 100 %, niveles 89 % (5 fotogramas), 66 s/fotograma, **8,8 GB** | Fuera del mínimo (alerta 15) |
| ASR faster-whisper int8 (audio sintético TTS, 3 + 3 min) | small ×0,15–0,18 del tiempo real, 2,6 GB; turbo ×0,52–0,60, 3,9 GB; WER 19–23 % ambos | small por velocidad; el WER sobre TTS no vale como calidad: faltan muestras reales |
| Embeddings `qwen3-embedding:0.6b` | 36 s/100 textos, 2,5 GB | La calidad la decide T71 |
| Presupuesto | 0,20 h/h con subtítulos y 0,38 h/h sin ellos (sin VLM): **≈ 95 videos de 20 min por noche de 8 h**; con VLM 39 | Supuestos declarados en el informe; T64 los mide sobre videos reales |

Fallos de instalación vistos al medir: PyAV 19 rompe faster-whisper 1.2.1 (`metadata_errors`, [SYSTRAN/faster-whisper#1589](https://github.com/SYSTRAN/faster-whisper/issues/1589)) → `av==18.1.0` fijado en el extra `[video]`; Pydantic AI 2.x cambió `output_retries` por `retries={"output": n}`.

---

# Detalle por grupo

## Grupo A — captación de YouTube y ASR

Auditoría de solo lectura, 2026-10-30/31. No se instaló ni se ejecutó nada de terceros. Hay clones superficiales en `scratchpad/t62_clones/` que solo se leyeron con grep, `git show` y `sed`. Las cifras de README van marcadas «declarado». Las referencias `archivo:línea` apuntan al HEAD clonado (SHA en «Consultas») salvo que se indique otra cosa.

---

### 1. Alertas

**Rojas**

1. **Términos de YouTube frente a descarga y scraping.** Los ToS de YouTube (en inglés, fechados el 15-dic-2023) prohíben «access, reproduce, download… or otherwise use» el contenido salvo que el Servicio lo autorice expresamente o haya permiso escrito. También prohíben el acceso «using any automated means (such as robots, botnets or scrapers)», con excepción para buscadores públicos que respeten robots.txt ([ToS](https://www.youtube.com/static?gl=US&template=terms&hl=en)). Las Developer Policies (actualizadas el 2026-10-15) dicen además:
   - III.E.1.a: no «download, import, backup, cache, or store copies of YouTube audiovisual content» sin aprobación escrita;
   - III.I.7: no «separate, isolate, or modify the audio».
   - III.E.6: no hacer scraping de YouTube Applications.
   - III.I.14: no usar otra tecnología para obtener API Data ([Developer Policies](https://developers.google.com/youtube/terms/developer-policies)).

   yt-dlp (descarga de audio) y youtube-transcript-api (InnerTube no documentado) chocan con estos textos. Si EIM también usa la Data API, las Developer Policies obligan a ese cliente de API (API Services Terms §2.1 y §3.1, [enlace](https://developers.google.com/youtube/terms/api-services-terms-of-service)). La postura la fija T62.
2. **pyannote.audio 4.x trae la telemetría ACTIVADA por defecto.** En el tag `4.0.7`, `src/pyannote/audio/telemetry/config.yaml` tiene `metrics_enabled: true` y `otlp_endpoint: https://otel.pyannote.ai/v1/traces`. Envía `origin`, `session_id`, `duration` del archivo y `num_speakers` (`telemetry/metrics.py:68-140`). Se dispara en `Model.from_pretrained` (`core/model.py:653`) y en `Pipeline` (`core/pipeline.py:291, 505-592`). **WhisperX usa pyannote como VAD por defecto**, así que hay telemetría aunque no se diarice. Mitigación: `PYANNOTE_METRICS_ENABLED=0` (`metrics.py:150-167`). El README la llama «optional», pero viene encendida.
3. **Pickle y código remoto en ejecución.**
   - pyannote carga sus checkpoints con `weights_only=False` (`core/model.py:602-603, 625, 644`).
   - WhisperX incluye un pickle propio, `whisperx/assets/pytorch_model.bin` (VAD), que se carga por esa misma vía (`whisperx/vads/pyannote.py:29-41`).
   - `torch.hub.load('snakers4/silero-vad', trust_repo=True)` descarga y ejecuta código de GitHub en ejecución: WhisperX `vads/silero.py:26-30` y whisper-timestamped `transcribe.py:2018-2023`.
   - whisper-timestamped usa `torch.load` sin `weights_only` (`transcribe.py:2587`).
4. **Licencias que bloquean.**
   - El modelo de alineación por defecto de WhisperX para **español**, `VOXPOPULI_ASR_BASE_10K_ES` (`whisperx/alignment.py:52-57`), es **CC BY-NC 4.0**, no comercial ([torchaudio](https://docs.pytorch.org/audio/2.8.0/generated/torchaudio.pipelines.VOXPOPULI_ASR_BASE_10K_ES.html)). El repo HF de respaldo `facebook/wav2vec2-base-10k-voxpopuli-es` responde 401: no existe o no es público.
   - whisper-timestamped: el archivo LICENSE es **AGPL-3.0**, mientras que `__license__ = "GPLv3"` (`transcribe.py:5`) y PyPI dicen «GPLv3». Inconsistente, y copyleft en cualquier caso.

**Amarillas**

5. **GPU Maxwell (cómputo 5.0) no sirve con CTranslate2.**
   - Las wheels de PyPI se compilan con CUDA 12.8 y `CUDA_ARCH_LIST="Common"` (`python/tools/prepare_build_environment_windows.sh:6,55`).
   - CTranslate2 solo reañade 3.5/5.0 con CUDA 11 (`CMakeLists.txt:581-589`), y CMake quita 3.5/5.0 a partir de CUDA 11 ([select_compute_arch.cmake:83](https://github.com/Kitware/CMake/blob/master/Modules/FindCUDA/select_compute_arch.cmake)).
   - Siguen abiertas las issues [#1765](https://github.com/OpenNMT/CTranslate2/issues/1765) y [#1766](https://github.com/OpenNMT/CTranslate2/issues/1766) («Reintroduce support for Compute Capability 5.0»).
   - Además, int8 en GPU exige CC ≥ 6.1 (`docs/quantization.md`), y `docs/hardware_support.md:22` («≥ 3.5») está desfasado.
   - **Conclusión: faster-whisper solo en CPU** en los dos equipos (MX130 y GTX 750 Ti son CC 5.0).
6. **El alias `turbo` de faster-whisper apunta a un repo que cambió de dueño.** `_MODELS["turbo"]` = `mobiuslabsgmbh/faster-whisper-large-v3-turbo` (`faster_whisper/utils.py:29-30`), que hoy redirige (HTTP 307) a `dropbox-dash/faster-whisper-large-v3-turbo`. Además, `WhisperModel("<nombre>")` llama a `huggingface_hub.snapshot_download` al instanciarse (`utils.py:84-115`, `transcribe.py:680-687`). Conviene fijar repo + `revision=<sha>`, o predescargar y pasar una ruta local con `local_files_only=True` y `HF_HUB_OFFLINE=1`.
7. **yt-dlp: plugins, JavaScript y configuración.**
   - Carga plugins al arrancar (`__init__.py:977-980`) y **también como librería** (`YoutubeDL.py:660-662`). Los busca en las carpetas de config y **en cada entrada de `sys.path`** (`plugins.py:81-106`). Se desactiva con `YTDLP_NO_PLUGINS` (`plugins.py:197`) o `--no-plugin-dirs`.
   - Para YouTube ejecuta el JS del player en **deno** (runtime por defecto, `options.py:460-470`), con `--no-remote --no-prompt --no-config --no-lock` (`jsc/_builtin/deno.py:35-38`).
   - El README avisa de que node y bun «are still considered insecure» (`README.md:1886`).
   - El CLI lee archivos de configuración del usuario (`options.py:56-86`); conviene `--ignore-config`.
8. **yt-dlp: actualización.** `-U` solo comprueba el `SHA2-256SUMS` de la misma release, no la firma `.sig`, y si no hay hash lo omite («skipping verification», `update.py:457-466`). Con pip no aplica. Fijar versión choca con lo rápido que YouTube rompe extractores; hace falta un procedimiento de actualización manual.
9. **youtube-transcript-api: API no oficial.** Usa el endpoint InnerTube `youtubei/v1/player` con cliente `ANDROID` (`_settings.py:1-3`). El propio README documenta bloqueos de IP (`README.md:313-318`) y dice que la autenticación por cookies «currently not available» (`README.md:431-435`). En 2026 hay issues de bloqueo: [#606](https://github.com/jdepoix/youtube-transcript-api/issues/606), [#613](https://github.com/jdepoix/youtube-transcript-api/issues/613) y [#612](https://github.com/jdepoix/youtube-transcript-api/issues/612). La última release es de ene-2026.
10. **RSS de canal: no oficial e inestable.** No aparece en la documentación de la v3. La prueba en vivo del 2026-10-31 a las 03:25 UTC dio **404 en 4 canales** y en la variante `playlist_id`. Hay reportes de 404 intermitentes desde dic-2025 ([hilo](https://discuss.ai.google.dev/t/youtube-rss-feed-endpoint-returns-404-errors/113379)).
11. **Data API: cuota y subtítulos.** Cuota por defecto: 10 000 unidades/día, más cubos aparte de 100 llamadas `search.list` y 100 `videos.insert` (cuota granular desde el 2026-06-01). `captions.download` cuesta 200 unidades, necesita OAuth con los alcances `youtube.force-ssl` o `youtubepartner` y **permiso de edición sobre el video**. No sirve para subtítulos de terceros.
12. **whisper.cpp server sin autenticación.** Escucha en `127.0.0.1:8080` por defecto (`examples/server/README.md:47-48`), pero responde con `Access-Control-Allow-Origin: *` (`server.cpp:739`) y expone `/load` para cambiar de modelo sin auth (`server.cpp:1175`). El README pide no ejecutarlo como administrador (`README.md:71`).
13. **CTranslate2 v4.8.4 tiene 6 días** (2026-10-25). La anterior es v4.8.3 (2026-10-13). Conviene un periodo de enfriamiento antes de fijarla.

---

### 2. Resumen de veredictos

| Candidato | Veredicto | Licencia código | Licencia pesos | Versión a fijar |
|---|---|---|---|---|
| yt-dlp | **Usar** (condicionado a la postura legal de T62 y a los controles de §3.1) | [Unlicense](https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE) | n/a | `2026.10.26` · `f264a6cbd1f630894da0f368df00f8aae50140e0` (+ `yt-dlp-ejs==0.8.0`) |
| youtube-transcript-api | **Usar (opcional)**: primer intento barato, con respaldo ASR | [MIT](https://github.com/jdepoix/youtube-transcript-api/blob/master/LICENSE) | n/a | `v1.2.4` · `505f412a5a691cc1bac6430dd35144222c667598` |
| YouTube Data API v3 | **Usar** para descubrimiento y metadatos (`videos.list`, `playlistItems.list`); **no** para subtítulos ajenos | servicio (términos de Google) | n/a | API v3; doc. revisada el 2026-10-15 |
| RSS de canal | **Usar (opcional)**, solo como pista y con reintentos | no documentado | n/a | n/a |
| faster-whisper + CTranslate2 | **Usar**: motor principal en CPU int8 | [MIT](https://github.com/SYSTRAN/faster-whisper/blob/master/LICENSE) / [MIT](https://github.com/OpenNMT/CTranslate2/blob/master/LICENSE) | MIT (Systran/*, dropbox-dash turbo, deepdml turbo) | fw `v1.2.1` · `65882eee9f5cdbeeb2d877f1131d48cf241b327d`; ct2 `v4.8.4` · `5de572ef60b67a0276c5989ee73d0072808ff4c3` (o v4.8.3) |
| whisper.cpp | **Usar (opcional)**: alternativa sin Python/torch y única vía GPU posible en Maxwell | [MIT](https://github.com/ggml-org/whisper.cpp/blob/master/LICENSE) | MIT (`ggerganov/whisper.cpp`) | `v1.9.5` · `d1be6fde11ac6e0407606b4e42fe72d34add8037` (binarios en la release `b5454`, mismo SHA) |
| openai/whisper | **Referencia** | [MIT](https://github.com/openai/whisper/blob/main/LICENSE) | MIT (README:160); la tarjeta HF de large-v3 dice apache-2.0 | `v20250625` · `31243bad24cc746f07d4c8bfdd2d974872cb1803` |
| WhisperX | **Referencia** (no instalar; diarización no justificada) | [BSD-2-Clause](https://github.com/m-bain/whisperX/blob/main/LICENSE) | mezcla: MIT, CC-BY-4.0 (gated), CC BY-NC 4.0 (alineación es) | `v3.8.6` · `3ccc17b8de34f305300f8a3fd3c9f76ba820c0d0` |
| pyannote (diarización) | **Descartar por ahora**; si algún día se necesita, offline y con telemetría desactivada | [MIT](https://github.com/pyannote/pyannote-audio/blob/main/LICENSE) | community-1: CC-BY-4.0, gated · 3.1: MIT, gated | `4.0.7` · `b749285c5cdd4636b2edc7f766f1352c8dde9369` |
| whisper-timestamped | **Descartar** | [AGPL-3.0](https://github.com/linto-ai/whisper-timestamped/blob/master/LICENSE) (los metadatos dicen GPLv3) | MIT (pesos OpenAI) | `v1.15.9` · `137f4e0415d6c1ccf00a2008231b74dc8a01c1d9` |
| wav2vec2 de alineación (es/en) | en: **Usar (opcional)** · es VoxPopuli: **Descartar** · es jonatasgrosman: **Usar (opcional)** | n/a | en `WAV2VEC2_ASR_BASE_960H`: MIT (torchaudio) / HF apache-2.0 · es VoxPopuli: **CC BY-NC 4.0** · `jonatasgrosman/...-spanish`: apache-2.0 | ver §3.9 |

---

### 3. Detalle por candidato

#### 3.1 yt-dlp
| Campo | Valor |
|---|---|
| URL | https://github.com/yt-dlp/yt-dlp |
| Licencia código | Unlicense ([LICENSE](https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE)); `yt-dlp-ejs` 0.8.0: «Unlicense AND MIT AND ISC» (PyPI) |
| Licencia pesos | n/a |
| Mantenimiento | ★ 204 012 · último commit 2026-10-29 (`b77c930`) · release `2026.10.26` (2026-10-26) · 2 055 issues y 685 PR abiertas |
| Pruebas | `test/` (40 archivos); workflows `core.yml`, `quick-test.yml`, `codeql.yml`, `challenge-tests.yml` |
| Instalación Windows | Wheel py3 pura (3,2 MB, Python ≥ 3.11) o `yt-dlp.exe` (23,6 MB, PyInstaller). Extra `default`: requests, websockets, pycryptodomex, mutagen, brotli, certifi y `yt-dlp-ejs==0.8.0`. Opcional `deno>=2.9.8` (extra `deno`). Necesita ffmpeg, ya instalado. |
| Red al arrancar | No busca actualizaciones por defecto (`--no-update` es el default, `options.py:370-372`). El aviso de «versión > 90 días» se calcula con la fecha local (`update.py:182-195`). Componentes remotos desactivados por defecto (`options.py:481-496`); `ejs:github` descarga el solver de GitHub (`jsc/_builtin/ejs.py:292-294`) |
| exec / descargas en ejecución | (a) Plugins Python autocargados, también vía API (ver alerta 7). (b) JS del player de YouTube ejecutado en deno, sandbox sin `--allow-*` (`deno.py:35-38, 102`). (c) `-U` reemplaza el ejecutable tras comprobar el SHA-256 de la misma release (alerta 8). (d) `--cookies-from-browser` descifra las cookies del navegador (`README.md:721`); **no usar** |
| Tamaño/RAM | n/a |
| Versión a fijar | `2026.10.26` → `f264a6cbd1f630894da0f368df00f8aae50140e0`; `yt-dlp-ejs==0.8.0` |
| Riesgos | Legal (alerta 1); roturas frecuentes por cambios de YouTube; superficie de plugins y config; sin JS runtime hay clientes de YouTube que se omiten (`README.md:1862`) |
| Veredicto | **Usar** (condicionado): es la única herramienta madura para audio y metadatos. Usarla como librería con `YTDLP_NO_PLUGINS=1`, sin cookies, sin `--remote-components` y con versión fijada. Si T62 no acepta la postura legal, se queda en Referencia |

#### 3.2 youtube-transcript-api
| Campo | Valor |
|---|---|
| URL | https://github.com/jdepoix/youtube-transcript-api |
| Licencia código | MIT ([LICENSE](https://github.com/jdepoix/youtube-transcript-api/blob/master/LICENSE)) |
| Mantenimiento | ★ 8 536 · último commit 2026-10-30 (merge de patrocinio) · release `v1.2.4` (2026-01-29) · 19 issues y 15 PR abiertas |
| Pruebas | `youtube_transcript_api/test/` (api, cli, formatters, proxies); `ci.yml` y coveralls |
| Instalación Windows | Wheel pura de 0,5 MB; dependencias `requests` y `defusedxml`; Python 3.8–3.14 |
| Red | Solo a youtube.com: página watch + `youtubei/v1/player` con cliente ANDROID (`_settings.py:1-3`). No hay telemetría |
| Proxies/cookies | `GenericProxyConfig` (HTTP/HTTPS/SOCKS) y `WebshareProxyConfig`; el README usa **enlaces de referido** de Webshare (`README.md:322-373`). Autenticación por cookies no disponible (`README.md:431-435`) |
| exec/pickle | No |
| Versión a fijar | `v1.2.4` → `505f412a5a691cc1bac6430dd35144222c667598` |
| Riesgos | Bloqueos de IP documentados y API no oficial que puede romperse sin aviso (alertas 1 y 9) |
| Veredicto | **Usar (opcional)**: barata y sin dependencias pesadas. Si falla, se pasa a ASR local. No contratar proxies |

#### 3.3 YouTube Data API v3 y RSS
| Campo | Valor (fuentes oficiales, revisadas el 2026-10-15) |
|---|---|
| Cuota por defecto | «100 `search.list` calls, 100 `videos.insert` calls, and 10,000 units per day combined for all other endpoints»; se reinicia a medianoche PT ([quota cost](https://developers.google.com/youtube/v3/determine_quota_cost), [getting started](https://developers.google.com/youtube/v3/getting-started)). Cuota granular desde el 2026-06-01 ([revision history](https://developers.google.com/youtube/v3/revision_history)) |
| Coste | `search.list`: 1 por llamada, en su propio cubo de 100/día · `videos.list`: 1 · `channels.list`: 1 · `playlistItems.list`: 1 · `captions.list`: 50 · `captions.download`: **200** |
| captions.download | Alcances `youtube.force-ssl` o `youtubepartner` (OAuth); «requires the user to have permission to edit the video» ([doc](https://developers.google.com/youtube/v3/docs/captions/download)). Solo vale para videos propios |
| Almacenamiento | Developer Policies III.E.4: los datos no autorizados se guardan como máximo 30 días; los autorizados se borran o refrescan cada 30 días ([policies](https://developers.google.com/youtube/terms/developer-policies)) |
| RSS | `https://www.youtube.com/feeds/videos.xml?channel_id=` no figura en la documentación oficial. Dio 404 el 2026-10-31 a las 03:25 UTC (alerta 10). Fuentes de terceros dicen que solo trae las 15 subidas más recientes (no verificado) |
| Veredicto | **Usar** la API para la cola (playlist de subidas del canal + `videos.list`, unas pocas unidades por canal y día). **RSS opcional**, siempre con la API como respaldo |

#### 3.4 faster-whisper + CTranslate2
| Campo | Valor |
|---|---|
| URL | https://github.com/SYSTRAN/faster-whisper · https://github.com/OpenNMT/CTranslate2 |
| Licencia código | MIT ([fw](https://github.com/SYSTRAN/faster-whisper/blob/master/LICENSE), [ct2](https://github.com/OpenNMT/CTranslate2/blob/master/LICENSE)) |
| Licencia pesos | `Systran/faster-whisper-*`: MIT, sin gate (repos de la organización Systran). Turbo: `dropbox-dash/faster-whisper-large-v3-turbo` (antes mobiuslabsgmbh), MIT, conversión FP16 de `openai/whisper-large-v3-turbo` (MIT); `deepdml/faster-whisper-large-v3-turbo-ct2`, MIT (particular, modificado el 2026-02-22) |
| Mantenimiento | fw: ★ 26 343 · último commit 2026-10-16 · release `v1.2.1` (2025-10-31, hace 1 año) · 6 issues y 14 PR. ct2: ★ 4 728 · commit 2026-10-30 · `v4.8.4` (2026-10-25) · 223 issues y 52 PR |
| Pruebas | fw: `tests/` + `ci.yml` (pytest, `ci.yml:60-62`); ct2: `tests/` |
| Instalación Windows | `faster_whisper` es wheel pura. `ctranslate2-4.8.4-cp312-win_amd64.whl` (20,4 MB) lleva MKL/oneDNN. Dependencias: `huggingface-hub`, `tokenizers`, `onnxruntime` (VAD), `av` (PyAV). En GPU haría falta cuBLAS 12 + cuDNN 9 por separado (README:63-70), pero CC 5.0 no está soportado (alerta 5) |
| Red al arrancar | Sin telemetría propia. `WhisperModel("small")` descarga del Hub (`utils.py:84-115`), mientras que una ruta local no descarga (`transcribe.py:680`). `huggingface_hub` puede contactar con el Hub: usar `HF_HUB_OFFLINE=1` y `HF_HUB_DISABLE_TELEMETRY=1` |
| exec/pickle | `model.bin` usa el formato binario de CTranslate2, no pickle. El VAD Silero va incluido en el paquete como ONNX (`faster_whisper/assets/silero_vad_v6.onnx`, `vad.py:332`), sin descarga |
| Tamaño en disco (HF API, `model.bin` FP16) | small 483,5 MB · medium 1 527,9 MB · large-v3 3 087,3 MB · large-v3-turbo 1 617,9 MB · distil-large-v3 1 512,9 MB (inglés) |
| RAM (declarado) | small int8 CPU: 1 477 MB; fp32: 2 257 MB; `batch_size=8` int8: 3 608 MB (13 min de audio, i7-12700K, README:44-52). No hay cifra declarada para turbo/large en CPU; hay que medirla en el bench de T62 |
| Versión a fijar | fw `v1.2.1` → `65882eee9f5cdbeeb2d877f1131d48cf241b327d`; ct2 `v4.8.4` → `5de572ef60b67a0276c5989ee73d0072808ff4c3`. Pesos (`sha` HF): small `536b0662742c02347bc0e980a01041f333bce120` · medium `08e178d48790749d25932bbc082711ddcfdfbc4f` · large-v3 `edaa852ec7e145841d8ffdb056a99866b5f0a478` · turbo dropbox-dash `0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf` · base `ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66` |
| Riesgos | Solo CPU; repo del alias turbo redirigido (alerta 6); release de fw con un año; onnxruntime y PyAV son dependencias nativas grandes |
| Veredicto | **Usar**: es la opción más ligera en Python para CPU int8, con licencias MIT en código y pesos y sin pickle |

#### 3.5 whisper.cpp
| Campo | Valor |
|---|---|
| URL | https://github.com/ggml-org/whisper.cpp |
| Licencia código / pesos | MIT ([LICENSE](https://github.com/ggml-org/whisper.cpp/blob/master/LICENSE)) / `ggerganov/whisper.cpp` en HF: MIT, sin gate |
| Mantenimiento | ★ 54 810 · commit 2026-10-30 · `v1.9.5` (2026-10-06) · 178 issues y 183 PR |
| Pruebas | `tests/` y unos 20 workflows (`build-windows.yml`, `build-cpu.yml`, `build-sanitize.yml`…) |
| Binarios Windows | En la release de build `b5454` (la etiqueta `v1.9.5` no lleva assets): `whisper-bin-x64.zip`, `whisper-blas-bin-x64.zip` (OpenBLAS), `whisper-bin-win-cuda-11.8.0-x64.zip` y `-12.4.0-x64.zip`. Se compilan con `GGML_NATIVE=OFF`, `GGML_CPU_ALL_VARIANTS=ON` y `GGML_BACKEND_DL=ON` (`release.yml:494-504`), y llevan **atestación** de artefactos (`release.yml:897-898`). No hay binario Vulkan para Windows (habría que compilarlo) |
| CUDA en Maxwell | Con CUDA < 13, ggml compila `50-virtual` (PTX) (`ggml/src/ggml-cuda/CMakeLists.txt:42-44`): en teoría corre en CC 5.0, **sin probar**. Con 2 GB de VRAM, como mucho medium-q5_0 o turbo-q5_0 |
| Red/telemetría | La librería no tiene cliente de red (grep). `download-ggml-model.cmd:79` baja de HF por `resolve/main`, sin fijar versión. El server tiene los riesgos de la alerta 12 |
| exec/pickle | Formato ggml binario, no pickle. Los scripts `convert-*.py` solo hacen falta para convertir |
| Tamaño (HF API) / RAM (declarado) | small 487,6 MB (q5_1 190 MB, q8_0 264 MB) · medium 1 533,8 MB (q5_0 539 MB) · large-v3 3 095 MB (q5_0 1 081 MB) · large-v3-turbo 1 624,6 MB (q5_0 574 MB, q8_0 874 MB). RAM declarada: small ~852 MB, medium ~2,1 GB, large ~3,9 GB (README «Memory usage») |
| Versión a fijar | `v1.9.5` → `d1be6fde11ac6e0407606b4e42fe72d34add8037`; pesos HF `5359861c739e955e79d9a303bcbc70fb988958b1`, descargando por `resolve/<sha>/` y no por `main` |
| Veredicto | **Usar (opcional)**: alternativa sin torch ni Python, con binarios atestados y posible uso de la GTX 750 Ti. Sirve si faster-whisper no basta en CPU |

#### 3.6 openai/whisper
| Campo | Valor |
|---|---|
| Licencia | Código y pesos MIT («Whisper's code and model weights are released under the MIT License», README:160). La tarjeta HF de `openai/whisper-large-v3` dice apache-2.0 y la de `-turbo` dice MIT |
| Mantenimiento | ★ 111 611 · commit 2026-08-31 · `v20250625` (2025-06-26) · issues desactivadas o 0, 180 PR |
| Instalación | Solo sdist; necesita torch, numba y tiktoken (los BPE van incluidos) |
| Descargas / pickle | Descarga los `.pt` de `openaipublic.azureedge.net` y comprueba SHA-256 (`whisper/__init__.py:54-90`). `torch.load(..., weights_only=True)` si `torch.__version__ >= "1.13"` (`__init__.py:150-151`), comparando cadenas |
| Pruebas | `tests/` + `test.yml` |
| Versión | `v20250625` → `31243bad24cc746f07d4c8bfdd2d974872cb1803` |
| Veredicto | **Referencia**: implementación de referencia; en CPU es más pesada (torch) y lenta que fw/whisper.cpp. Lo de «más lenta» está declarado en el README de fw, no medido |

#### 3.7 WhisperX (+ pyannote)
| Campo | Valor |
|---|---|
| Licencia código | WhisperX BSD-2-Clause; pyannote.audio MIT |
| Licencia pesos | Diarización por defecto `pyannote/speaker-diarization-community-1` (`diarize.py:101`, `__main__.py:48`): **CC-BY-4.0, gated** («agree to share your Hugging Face information»), necesita token HF, admite uso offline. `speaker-diarization-3.1`: MIT, gated (`gated: auto`), depende de `segmentation-3.0` (MIT, gated) y de `wespeaker-voxceleb-resnet34-LM` (CC-BY-4.0). El VAD incluido en `whisperx/assets/pytorch_model.bin` no declara licencia aparte |
| Mantenimiento | WhisperX ★ 24 956 · commit 2026-10-22 · `v3.8.6` (2026-05-25) · 178 issues y 36 PR. pyannote ★ 10 732 · `4.0.7` (2026-06-30) · 18 issues |
| Pruebas | WhisperX: 2 tests + `tests.yml` y `zizmor.yml` |
| Instalación Windows | Wheel de 16,5 MB. Fija `torch~=2.8.0`, `torchaudio~=2.8.0`, `torchvision~=0.23.0`, `torchcodec<0.8`, `pyannote-audio>=4.0.0`, `transformers` y `nltk`; pyannote arrastra opentelemetry, lightning y `pyannoteai-sdk`. Pesada para 7,9 GB de RAM |
| Red/telemetría | Telemetría de pyannote activa (alerta 2). Descarga NLTK `punkt_tab` en ejecución (`alignment.py:184-187`). Bundles de torchaudio desde download.pytorch.org (`alignment.py:124-128`) |
| exec/pickle | Ver alerta 3 (`weights_only=False`, `torch.hub` con `trust_repo=True`) |
| Versión | `v3.8.6` → `3ccc17b8de34f305300f8a3fd3c9f76ba820c0d0`; pyannote `4.0.7` → `b749285c5cdd4636b2edc7f766f1352c8dde9369`; HF: community-1 `3533c8cf8e369892e6b79ff1bf80f7b0286a54ee`, 3.1 `84fd25912480287da0247647c3d2b4853cb3ee5d` |
| Veredicto | **Referencia**: alineación y diarización no se justifican para videos de finanzas con un solo locutor, y el coste en telemetría, pickle, licencias y RAM es alto. Si algún día hace falta diarizar: `PYANNOTE_METRICS_ENABLED=0`, pesos clonados offline y SHA fijado |

#### 3.8 whisper-timestamped
| Campo | Valor |
|---|---|
| Licencia | Código **AGPL-3.0** (LICENSE en master y en `v1.15.9`), aunque los metadatos dicen «GPLv3». Depende de `dtw-python` (GPL v3). Pesos: los de OpenAI (MIT) |
| Mantenimiento | ★ 2 856 · commit 2026-09-28 · `v1.15.9` (2025-09-09) · 48 issues |
| exec/pickle | `torch.hub.load` de silero-vad (`transcribe.py:2018-2023`); `torch.load` sin `weights_only` (`transcribe.py:2587`) |
| Versión | `v1.15.9` → `137f4e0415d6c1ccf00a2008231b74dc8a01c1d9` |
| Veredicto | **Descartar**: copyleft fuerte, carga código remoto y depende de openai-whisper/torch; faster-whisper ya da marcas de tiempo por palabra |

#### 3.9 Modelos wav2vec2 de alineación (es/en)
| Modelo | Licencia | Revisión / tamaño | Nota |
|---|---|---|---|
| en: torchaudio `WAV2VEC2_ASR_BASE_960H` (por defecto en WhisperX) | MIT («redistributed with the same license», [doc](https://docs.pytorch.org/audio/2.8.0/generated/torchaudio.pipelines.WAV2VEC2_ASR_BASE_960H.html)) | equivalente HF `facebook/wav2vec2-base-960h` (apache-2.0) `22aad52d435eb6dbaf354bdad9b0da84ce7d6156`, safetensors de 377,6 MB | Usar (opcional) |
| es: torchaudio `VOXPOPULI_ASR_BASE_10K_ES` (por defecto en WhisperX) | **CC BY-NC 4.0** | respaldo HF `facebook/wav2vec2-base-10k-voxpopuli-es` → 401 | **Descartar** si EIM tiene cualquier uso comercial |
| es alternativa: `jonatasgrosman/wav2vec2-large-xlsr-53-spanish` | apache-2.0, sin gate | `96d7e9b4e4a78af515a3c6d3cee7c0826045d276`; `pytorch_model.bin` de 1 262 MB (**solo pickle**, sin safetensors) | Usar (opcional) vía `--align_model`, con `weights_only` |
| en alternativa: `jonatasgrosman/wav2vec2-large-xlsr-53-english` | apache-2.0 | `569a6236e92bd5f7652a0420bfe9bb94c5664080`; `model.safetensors` de 1 262 MB | opcional |

#### Encaje con los equipos (conclusión)
- **Solo CPU** para faster-whisper en el i5-8250U y en el i5-6400. small, medium y turbo en int8 entran en el margen de 5–6 GB según tamaños de archivo y RAM declarada; falta medirlo.
- La GTX 750 Ti y la MX130 solo podrían aprovecharse con whisper.cpp CUDA 11.8/12.4 (PTX sm_50, sin probar) y con modelos ≤ q5 por los 2 GB de VRAM.

---

### 4. Consultas (2026-10-30 / 2026-10-31 UTC)
- GitHub (`gh api`): `repos/<r>`, `repos/<r>/releases/latest`, `repos/<r>/commits?per_page=1`, `repos/<r>/commits/<tag>`, `search/issues?q=repo:<r>+type:issue|pr+state:open`, `repos/ggml-org/whisper.cpp/releases?per_page=6`, `repos/OpenNMT/CTranslate2/releases?per_page=4`, `search/issues?q=repo:OpenNMT/CTranslate2+"no kernel image"`, `repos/Kitware/CMake/contents/Modules/FindCUDA/select_compute_arch.cmake`, issues recientes de jdepoix (`created:>2026-05-01`). Repos: yt-dlp/yt-dlp, jdepoix/youtube-transcript-api, SYSTRAN/faster-whisper, OpenNMT/CTranslate2, ggml-org/whisper.cpp, openai/whisper, m-bain/whisperX, linto-ai/whisper-timestamped, pyannote/pyannote-audio.
- Clones `git clone --depth 1 --filter=blob:limit=2m` en `scratchpad/t62_clones/`, todos con HEAD verificado: yt-dlp `b77c9304`, youtube-transcript-api `b5c3339d`, faster-whisper `9e472ae9`, CTranslate2 `78b1e177`, whisper.cpp `482279b8` (checkout incompleto, leído con `git show HEAD:`), openai/whisper `86098128`, whisperX `5d3678b8`, whisper-timestamped `a7a9605f`, pyannote-audio `623ab14d`. Solo grep y lectura.
- Raw: `raw.githubusercontent.com/pyannote/pyannote-audio/4.0.7/src/pyannote/audio/telemetry/config.yaml`, `.../linto-ai/whisper-timestamped/v1.15.9/LICENSE`.
- PyPI JSON: yt-dlp, yt-dlp-ejs, youtube-transcript-api, faster-whisper, ctranslate2, openai-whisper, whisperx, whisper-timestamped, pyannote.audio, pywhispercpp.
- HF API `https://huggingface.co/api/models/<repo>[?blobs=true]`: Systran/faster-whisper-{base,small,medium,large-v2,large-v3}, Systran/faster-distil-whisper-large-v3, mobiuslabsgmbh→dropbox-dash/faster-whisper-large-v3-turbo, deepdml/faster-whisper-large-v3-turbo-ct2, openai/whisper-large-v3(-turbo), ggerganov/whisper.cpp, pyannote/{speaker-diarization-3.1, speaker-diarization-community-1, segmentation-3.0, wespeaker-voxceleb-resnet34-LM}, facebook/wav2vec2-base-960h, facebook/wav2vec2-base-10k-voxpopuli-es (401), jonatasgrosman/wav2vec2-large-xlsr-53-{spanish,english}. Además `huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo/raw/main/README.md` y la página de community-1.
- WebFetch: developers.google.com/youtube/v3/{docs/captions/download, docs/captions, determine_quota_cost, getting-started, revision_history}; developers.google.com/youtube/terms/{developer-policies, api-services-terms-of-service}; youtube.com/static?template=terms (ES 2022-01-05 y EN 2023-12-15); docs.pytorch.org/audio/2.8.0 (VOXPOPULI_ASR_BASE_10K_ES, WAV2VEC2_ASR_BASE_960H).
- WebSearch: documentación oficial del RSS (sin resultados de Google); «YouTube RSS feed 404 2026».
- Sondeo HTTP (GET, sin ejecutar nada): `curl https://www.youtube.com/feeds/videos.xml?channel_id={UCBR8-60-B28hp2BmDPdntcQ, UC_x5XG1OV2P6uZZ5FSM9Ttw, UCBJycsmduvYEL83R_U4JriQ, UCVHFbqXqoYvEWM1Ddxl0QDg}` y `?playlist_id=UU_x5XG1OV2P6uZZ5FSM9Ttw`: todos 404, el 2026-10-31 a las 03:25 UTC.

## Grupo B — Escenas/fotogramas, OCR y visión-lenguaje

Auditoría de solo lectura (2026-10-30/31). No se instaló ni ejecutó nada. Las cifras de README/tarjetas se marcan «declarado». Los tamaños de archivo salen de la API de Hugging Face, de PyPI o de las páginas de tags de ollama.com: son tamaños de descarga, no RAM medida.

### 1. Alertas

**Rojo**

1. **Qwen2.5-VL-3B: pesos no comerciales.** El [LICENSE](https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct/blob/main/LICENSE) es el «Qwen RESEARCH LICENSE AGREEMENT», que limita el uso a «NON-COMMERCIAL PURPOSES ONLY» (§2a). `qwen2.5vl:3b` de Ollama lleva esos mismos pesos. Se descarta; Qwen3-VL-2B/4B y Qwen3.5-0.8B/2B/4B son Apache-2.0.
2. **Gemma 3 4B y Gemma 3n: términos de Gemma y repos gated.** En HF figuran con `license:gemma` y `gated=manual`. **Gemma 4 E2B/E4B (2026-07) pasó a Apache-2.0** y no es gated ([tarjeta](https://huggingface.co/google/gemma-4-E2B-it)), así que sustituye a ambos.
3. **PaddleOCR 3.x / PaddleX: red al arrancar y dependencias pesadas.**
   - Comprueba conectividad con HuggingFace, AIStudio, ModelScope y BOS (Baidu) al construir los orígenes de modelos (`paddlex/inference/utils/official_models.py:906-916`) y descarga modelos en ejecución a la caché.
   - Se desactiva con `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK` (`paddlex/utils/flags.py:73`) y usando modelos locales.
   - Arrastra `modelscope`, `aistudio-sdk`, `huggingface-hub`, `pandas`, etc., y fija versiones exactas: `opencv-contrib-python==4.10.0.84` y `PyYAML==6.0.2`. Eso choca con `opencv-python-headless`.
4. **`trust_remote_code` (Python del repo HF ejecutado al cargar con transformers).** Lo exigen: Florence-2 (repo `microsoft/`, que además incluye `pytorch_model.bin` en pickle), moondream2, InternVL3.5, MiniCPM-V-4 (4.1B), LFM3-VL, Granite Vision 4.x, PaddleOCR-VL, DeepSeek-OCR-2, Unlimited-OCR-2 y Falcon-OCR. Con GGUF en Ollama o llama.cpp no se ejecuta código Python del repo.
5. **jina-ocr-v1: pesos CC-BY-NC-4.0.** No comercial; se descarta.

**Amarillo**

6. **OpenCV: dos trampas de instalación.**
   - En PyPI, `opencv-python-headless` 5.0.0.93 (OpenCV 5, 2026-07-02) es «mayor» que 4.14.0.94 (2026-07-28). `rapidocr` solo pide `>=4.5.1.48`, así que pip instalará OpenCV 5 si no se fija la versión.
   - El paquete `scenedetect` depende de `opencv-python` (con GUI), lo que da dos distribuciones de `cv2` en conflicto. Hay que usar **`scenedetect-headless`**.
7. **RapidOCR 3.x.**
   - No declara `onnxruntime` como dependencia; hay que fijarlo aparte.
   - Los modelos que no vienen por defecto (p. ej. `en_PP-OCRv5_rec_mobile`) se descargan de `modelscope.cn` en ejecución.
   - El SHA-256 se comprueba solo sobre un archivo que ya existe (`utils/download_file.py:37-41`), no justo después de descargarlo. El diccionario se descarga con `sha256=None` (`ch_ppocr_rec/main.py:85-92`).
   - La CI solo corre en ubuntu-latest con Python 3.10.
8. **LFM3-VL / LFM2.5-VL (Liquid AI).**
   - Pesos con «LFM Open License v1.0»: el uso comercial solo está licenciado por debajo de 10 M USD de ingresos anuales (§5). No es OSI.
   - En Windows, `lfm3-vl` exige **Ollama ≥ 0.40.13**: las notas de la 0.40.12 dicen «supported on Apple hardware in this release». Aquí está instalado 0.40.11.
9. **Modelos con menos de 2 semanas.** MiniCPM-V-4.7-1B (modificado 2026-10-30), MiniCPM-OCR-1.0 (2026-10-21/29) y LFM3-VL-2B (2026-10-28) siguen cambiando. Fijar SHA y reevaluar en 1–2 meses.
10. **Gemma 4 E2B no cabe en el portátil de referencia.** Ollama `gemma4:e2b` pesa 4,6 GB y `e2b-it-qat` 4,3 GB; el GGUF oficial suma 3,35 + 0,99 GB (mmproj). Con la API de EIM en marcha supera el margen; solo vale para el equipo de 16 GB.
11. **Instalador de Tesseract para Windows.**
   - El último es `tesseract-ocr-w64-setup-5.5.3.20260724.exe`, adjunto a la release [5.5.3 de tesseract-ocr/tesseract](https://github.com/tesseract-ocr/tesseract/releases/tag/5.5.3) (sha256 `bee9e343…0ae4`). La página de releases de UB-Mannheim solo muestra v5.4.0 (2024).
   - La 5.5.4 (2026-10-28) aún no tiene instalador.
12. **FFmpeg.**
   - Los builds de gyan.dev son **todos GPLv3** («All builds are 64-bit, static and licensed as GPLv3»). BtbN ofrece variantes `lgpl` y `gpl`, estáticas y `-shared`.
   - Usarlo como proceso externo (`subprocess`) no enlaza código. Redistribuir el binario obliga a cumplir la GPL/LGPL (texto de la licencia y fuente u oferta de fuente).
   - El tag `latest` de BtbN se mueve: fijar el `autobuild-AAAA-MM-DD-HH-MM` + `checksums.sha256`.
   - Se desconoce el origen y la configuración del ffmpeg 9.0.1 instalado. El usuario debe revisar `ffmpeg -version` (`--enable-gpl`).
13. **Biblioteca de Ollama desfasada en algunos modelos.**
   - `moondream:1.8b` es de hace unos 2 años (moondream2 antiguo).
   - `minicpm-v` es el 8B v2.6.
   - MiniCPM-V 4.7 solo está en el espacio comunitario `openbmb/minicpm-v4.7`, no en la biblioteca curada.
   - `qwen3-vl:2b` (digest `0635d9d857d4`) no coincide con `qwen3-vl:2b-instruct` (`afc393e3572c`): usar siempre el tag explícito.
14. **Qwen3.5 pequeño sin GGUF oficial.** Qwen no publicó GGUF de Qwen3.5-0.8B/2B/4B; solo hay de terceros (unsloth) y la biblioteca de Ollama. Qwen3.6 y Qwen3.8 no tienen tamaños ≤ 4B (comprobado en HF).

### 2. Tabla resumen

| Candidato | Veredicto | Licencia código | Licencia pesos | Versión a fijar |
|---|---|---|---|---|
| PySceneDetect (`scenedetect-headless`) | **Usar** | BSD-3-Clause | n/a | v0.7.2 · `7cd1005e8349d8e913d0930fc1750363eb4ddc51` · wheel sha256 `583fd5db…51ef2` |
| opencv-python-headless | **Usar** | MIT (empaquetado) + Apache-2.0 (OpenCV) + LGPL-2.1 (FFmpeg incluido) | n/a | 4.14.0.94 (tag `94` · `2ba8bf62f2f1215ab620416b041c9659005fa25c`) · wheel sha256 `cbed6541…dc64b` |
| FFmpeg (proceso externo) | **Usar** | GPLv3 (gyan.dev) / LGPL o GPL (BtbN) | n/a | BtbN `autobuild-2026-10-30-13-01`, `ffmpeg-n9.0-…-win64-lgpl-9.0.zip` + `checksums.sha256`; o gyan.dev release 9.0.2 + `.sha256` |
| RapidOCR (`rapidocr` + `onnxruntime`) | **Usar** | Apache-2.0 | Apache-2.0 (PP-OCRv6, [MODEL_LICENSES.md](https://github.com/RapidAI/RapidOCR/blob/main/python/MODEL_LICENSES.md)) | rapidocr 3.10.0 · `bd941dae09da793e76c6ba15c7aaf40f8424232a` · sha256 `2fc34e26…68050`; onnxruntime 1.31.1 cp312 win_amd64 sha256 `ae8a9a35…26130` |
| Tesseract 5 + `pytesseract` | **Usar** (ya en el proyecto) | Apache-2.0 | tessdata Apache-2.0 | instalador 5.5.3.20260724 (sha256 `bee9e3434bd94fd65387d9be28cd467a41f61b1275383b55b0f59a1331270ae4`); tessdata_best `e12c65a9…`; pytesseract 0.3.13 |
| PaddleOCR 3.x / PaddleX | Referencia | Apache-2.0 | Apache-2.0 | v3.7.0 · `b03f46425e8ff4442b268ce449e3eef758146cd4` (solo si se reevalúa) |
| rapidocr_onnxruntime (legado) | Descartar | Apache-2.0 | Apache-2.0 | 1.4.4 (2025-01, py<3.13): obsoleto |
| **Qwen3-VL-2B-Instruct** | **Usar (opcional)**: VLM principal | Apache-2.0 | Apache-2.0 (2B) | Ollama `qwen3-vl:2b-instruct-q4_K_M` (`afc393e3572c`, 1,9 GB) · GGUF oficial `Qwen/Qwen3-VL-2B-Instruct-GGUF@52d6c8ffea26cc873ac5ad116f8631268d7eb503` |
| Qwen3-VL-4B-Instruct | Usar (opcional), solo en el equipo de 16 GB | Apache-2.0 | Apache-2.0 (4B) | Ollama `qwen3-vl:4b` (`a1b29c246319`, 3,3 GB) · GGUF oficial `@1cd86afb9a95c410a6038ab3b40d8b578c892266` |
| Qwen3.5-0.8B/2B/4B | Usar (opcional), comparar con Qwen3-VL-2B | Apache-2.0 | Apache-2.0 (0.8B/2B/4B) | Ollama `qwen3.5:2b` (`0b28bbb3449d`, 2,7 GB) / `qwen3.5:0.8b` (`6a061203ed02`, 1,2 GB) · HF `Qwen/Qwen3.5-2B@15852e8c16360a2fea060d615a32b45270f8a8fc` |
| GLM-OCR (0.9B) | Usar (opcional): OCR-VLM de diapositivas y tablas | Apache-2.0 ([GitHub](https://github.com/zai-org/GLM-OCR)) | MIT | Ollama `glm-ocr:q8_0` (`6e5935a916fc`, 1,8 GB) · HF `zai-org/GLM-OCR@2e85a62840ccac27daa451df36c736c4636b8628` |
| Gemma 4 E2B-it | Referencia (16 GB) | Apache-2.0 | Apache-2.0 | Ollama `gemma4:e2b-it-qat` (`07ea59a47401`, 4,3 GB) · GGUF oficial `google/gemma-4-E2B-it-qat-q4_0-gguf@675cff42a74c774d6cb76f76d8eacb49b48c9b93` |
| Gemma 3 4B / Gemma 3n | Descartar | Apache-2.0 | Gemma Terms (gated) | — |
| Qwen2.5-VL-3B | **Descartar** | Apache-2.0 | qwen-research (no comercial) | — |
| SmolVLM2 (256M/500M/2.2B) | Referencia | Apache-2.0 | Apache-2.0 | `HuggingFaceTB/SmolVLM2-2.2B-Instruct@482adb537c021c86670beed01cd58990d01e72e4`; GGUF ggml-org `@1bc3c9f74ceafd4c8d4411cc9cf188bba3798f91` |
| Florence-2 base/large | Referencia | MIT | MIT | `florence-community/Florence-2-base@00921df66db728a9ceb750f5eca43e5c203a2051` (nativo, sin remote code) |
| moondream2 | Referencia | Apache-2.0 | Apache-2.0 | rev. `2025-06-21` = `9a7d4024050840e001defacec2b00727e89149e6` (no `main`) |
| MiniCPM-V-4.7-1B | Referencia (reevaluar) | Apache-2.0 | Apache-2.0 | `openbmb/MiniCPM-V-4.7-1B-gguf@345adbfa02c4a4671e61b7c75502dc9bf24fa93d` |
| InternVL3.5-1B/2B | Descartar | MIT (repo) | Apache-2.0 | — (remote code; sin GGUF oficial ni Ollama) |
| LFM3-VL-2B / LFM2.5-VL-1.6B | Referencia | LFM Open License (código HF) | LFM Open License v1.0 | Ollama `lfm3-vl:2b` (`b663c9779257`, 1,5 GB, exige Ollama ≥ 0.40.13) · GGUF `@b36554cfd35854b06429900131730cd80f092cdb` |
| Granite Vision 3.3-2B / chart2csv / 4.1-4B | Referencia | Apache-2.0 | Apache-2.0 | `ibm-granite/granite-vision-3.3-2b-GGUF@7edb59cacbffaeb016e29c760321c350fb43c429` |
| PaddleOCR-VL-1.6 (0.9B) | Referencia | Apache-2.0 | Apache-2.0 | GGUF oficial `@511b09642bb324401f15f97cc23bc67e8f0a291d` |
| MiniCPM-OCR-1.0 (1.3B) | Referencia (reevaluar) | Apache-2.0 | Apache-2.0 | GGUF oficial `@01d405f95fca2780f5bfed75c75d79fb2fb40d60` |
| DeepSeek-OCR-2, Unlimited-OCR-2, jina-ocr-v1, surya-ocr-2.5, moondream3-preview | Descartar | varias | Apache / MIT / **CC-BY-NC** / OpenRAIL / other | — |

### 3. Detalle por candidato

#### 3.1 PySceneDetect: [Breakthrough/PySceneDetect](https://github.com/Breakthrough/PySceneDetect)
- **Licencias:** código BSD-3-Clause ([LICENSE](https://github.com/Breakthrough/PySceneDetect/blob/main/LICENSE)). No hay pesos.
- **Mantenimiento:** 5,3 k★, 65 issues abiertas. Última release v0.7.2 (2026-10-12); último push 2026-10-27.
- **Pruebas:** `build.yml` en macOS, Ubuntu y **windows-latest** × Python 3.10–3.13.
- **Instalación en Windows:**
  - Wheel puro de 0,1 MB.
  - `scenedetect` depende de `opencv-python`; **`scenedetect-headless`** depende de `opencv-python-headless`. Además: `click~=8.0` (≠ 8.3.0), `numpy`, `platformdirs`, `tqdm`.
  - El extra `pyav` es opcional.
  - El `pyproject` del repo raíz no se publica: la 0.7.1 se publicó y se retiró (issue 558).
- **Red/exec:** sin red; solo usa `urllib.parse` en `scenedetect/platform.py:166`. Invoca ffmpeg o mkvmerge por `subprocess` solo para partir el vídeo (`scenedetect/output/video.py`). Sin pickle.
- **Riesgos:** conflicto de variantes de cv2 si se mezcla con paquetes que piden `opencv-python`.
- **Veredicto: Usar** `scenedetect-headless==0.7.2`. Su `ContentDetector`/`AdaptiveDetector` encaja con «pocos fotogramas por escena».

#### 3.2 OpenCV: [opencv/opencv-python](https://github.com/opencv/opencv-python) / [opencv/opencv](https://github.com/opencv/opencv)
- **Licencias:**
  - Empaquetado: MIT ([LICENSE.txt](https://github.com/opencv/opencv-python/blob/4.x/LICENSE.txt)).
  - OpenCV: Apache-2.0.
  - [LICENSE-3RD-PARTY.txt:243](https://github.com/opencv/opencv-python/blob/4.x/LICENSE-3RD-PARTY.txt): «FFmpeg is redistributed within all opencv-python packages» bajo LGPL-2.1, también en los wheels headless.
- **Mantenimiento:** 5,4 k★, 208 issues. Release `94` (2026-07-28); OpenCV 4.14.0 (2026-07-19) y 5.0.0 (2026-06-06).
- **Pruebas:** workflows por plataforma («Windows x86_64», «Windows ARM64», …).
- **Instalación en Windows:** wheel abi3 win_amd64 de 41,0 MB (4.14.0.94); `numpy>=2`.
- **Red/exec:** ninguna.
- **Riesgos:** pip prefiere 5.0.0.93 frente a 4.14.0.94 (alerta 6). `paddlex` fija `opencv-contrib-python==4.10.0.84`.
- **Veredicto: Usar** `opencv-python-headless==4.14.0.94`. OpenCV 5 queda pendiente de validar con RapidOCR.

#### 3.3 FFmpeg en Windows: [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) · [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds)
- **gyan.dev:** release 9.0.2 (2026-09-19); git master 2026-10-29. Todo **GPLv3** y estático; existe además `release-full-shared`. Cada paquete trae su `.sha256`.
- **BtbN:**
  - Script de build con licencia MIT; 11,9 k★; builds diarios.
  - Variantes `gpl`, `lgpl` (sin x264/x265), `gpl-shared` y `lgpl-shared`. «nonfree» no se publica en las releases.
  - Retención: el último build de cada mes se guarda 2 años y los últimos 14 diarios.
  - `latest` es flotante y hay `checksums.sha256`.
  - Tamaños: n9.0 win64 lgpl 168 MB y gpl 195 MB.
- **Implicaciones:** como proceso externo, EIM no enlaza libav*, así que la GPL no se extiende a EIM según la interpretación habitual. Si EIM redistribuye el ejecutable, conviene la build LGPL y adjuntar la licencia y la fuente u oferta de fuente.
- **Veredicto: Usar** como proceso externo. Preferir BtbN `n9.0 … lgpl` fijado por autobuild + sha256; usar gyan.dev solo para uso local.

#### 3.4 RapidOCR: [RapidAI/RapidOCR](https://github.com/RapidAI/RapidOCR)
- **Licencias:**
  - Código Apache-2.0.
  - Pesos Apache-2.0: derivados de PaddleOCR (Baidu) y documentados con su SHA-256 en [python/MODEL_LICENSES.md](https://github.com/RapidAI/RapidOCR/blob/main/python/MODEL_LICENSES.md) (§6: `PP-OCRv6_det_small.onnx`, `PP-OCRv6_rec_small.onnx`, `ch_ppocr_mobile_v2.0_cls_mobile.onnx`).
- **Mantenimiento:** 8,4 k★, 18 issues abiertas. v3.10.0 (2026-10-08); push 2026-10-30.
- **Pruebas:** unas 25 pruebas en `python/tests/`. CI (`gen_whl_to_pypi_rapidocr.yml`) solo en ubuntu-latest con Python 3.10.
- **Instalación en Windows:**
  - Wheel `py3-none-any` de 27,3 MB que **incluye los modelos por defecto**: `tools/prepare_wheel_assets.py` los mete en el build.
  - Dependencias: `opencv-python-headless`, `pyclipper`, `Shapely`, `omegaconf`, `requests`, …
  - **`onnxruntime` va aparte**: 1.31.1, 14,9 MB, cp312 win_amd64. Posible dependencia del runtime MSVC: verificar.
- **Red/exec:**
  - Por defecto (det/rec PP-OCRv6 small + cls) no hace falta red.
  - Con otro `lang_type`, `ocr_version` o `model_type` descarga de `modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/…` (`default_models.yaml:313+`; `inference_engine/onnxruntime/main.py:55-61`).
  - Verificación incompleta (alerta 7).
  - El motor PyTorch opcional usa `torch.load(..., weights_only=True)` (`networks/main.py:66`); no aplica con ONNX.
  - Sin telemetría (grep de `telemetry`, `sentry`, `posthog` sin resultados).
- **Riesgos:**
  - Leer cifras en inglés puede requerir un modelo de reconocimiento no incluido. Descargarlo una vez, fijar su SHA-256 y pasar `model_path`.
  - Precisión con números (declarado, no medido).
- **Veredicto: Usar** para el OCR principal de fotogramas (precios, %, ejes). Configurar `model_path` explícito y trabajar sin red.

#### 3.5 Tesseract 5: [tesseract-ocr/tesseract](https://github.com/tesseract-ocr/tesseract) + [UB-Mannheim](https://github.com/UB-Mannheim/tesseract/wiki)
- **Licencias:** código Apache-2.0. [tessdata](https://github.com/tesseract-ocr/tessdata), [tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast) y [tessdata_best](https://github.com/tesseract-ocr/tessdata_best) también Apache-2.0. Sus últimos commits son de 2024 (best `e12c65a9…`, fast `87416418…`).
- **Mantenimiento:** 77 k★, 494 issues abiertas. 5.5.4 (2026-10-28), 5.5.3 (2026-07-24).
- **Pruebas:** workflows `cmake-win64`, `installer-for-windows`, `unittest`, `cifuzz`, `codeql`.
- **Instalación en Windows:** instalador NSIS de 26,6 MB en la release 5.5.3 (alerta 11). `pytesseract` 0.3.13 (2024-08) es un envoltorio que llama al ejecutable. No se confirmó qué idiomas trae el instalador ni si los descarga durante la instalación: verificar.
- **Red/exec:** ninguna en ejecución.
- **Veredicto: Usar** (ya en el proyecto). Útil como segunda opinión con `tessedit_char_whitelist=0123456789.,%` sobre recortes.

#### 3.6 PaddleOCR 3.x: [PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)
- **Licencias:** código y pesos Apache-2.0. PP-OCRv6 se publica también en formato `_onnx` y `_safetensors` en HF (p. ej. `PP-OCRv6_small_det_onnx@28fe5895c24fd108c19eb3e8479f4ab385fbfc62`).
- **Mantenimiento:** 92 k★, 260 issues. v3.7.0 (2026-06-11); push 2026-09-16. `paddlepaddle` en PyPI está en 3.3.1 (2026-03-24); v3.4.0 (2026-09-11) solo en GitHub/índice propio.
- **Pruebas:** `tests.yml` solo ubuntu-latest, con `paddlepaddle==3.0.0` desde `paddlepaddle.org.cn`.
- **Instalación en Windows:** `paddleocr` no declara `paddlepaddle`; hay que instalarlo aparte (104,8 MB, cp312 win_amd64). Más `paddlex[ocr-core]`, con las fijaciones de la alerta 3.
- **Red/exec:**
  - Alerta 3.
  - `paddle.load` (pickle) en `paddlex/inference/models/common/transformers/transformers/utils.py:120-140`.
  - `pickle.load` en `det_3d_batch_sampler.py:68`, ruta que no se usa para OCR.
- **Veredicto: Referencia.** Sus modelos PP-OCRv6 ya llegan en ONNX vía RapidOCR sin el framework Paddle.

#### 3.7 Qwen3-VL-2B / 4B: [QwenLM/Qwen3-VL](https://github.com/QwenLM/Qwen3-VL)
- **Licencias:** código Apache-2.0. Pesos Apache-2.0 por tamaño (etiqueta HF en 2B y 4B); el repo 2B no incluye archivo LICENSE.
- **Mantenimiento:** 20 k★, 441 issues. Último push 2026-01-30; pesos sin cambios desde 2025-10/11.
- **Formato:** safetensors; arquitectura nativa en transformers (`Qwen3VLForConditionalGeneration`), sin `auto_map`.
- **GGUF oficial (Qwen):**
  - 2B: Q4_K_M 1,11 GB + mmproj Q8_0 0,45 GB.
  - 4B: Q4_K_M 2,5 GB + mmproj 0,45 GB.
- **Ollama, biblioteca nativa:** `qwen3-vl:2b-instruct-q4_K_M` 1,9 GB y `qwen3-vl:4b` 3,3 GB, con capacidades vision/tools/thinking.
- **Riesgos:** RAM real en CPU no medida. Puede inventar cifras: validarlas siempre contra el mercado, como ya está previsto.
- **Veredicto: Usar (opcional).** 2B como VLM por defecto en el portátil; 4B en el equipo de 16 GB.

#### 3.8 Qwen3.5-0.8B / 2B / 4B: [HF](https://huggingface.co/Qwen/Qwen3.5-2B) (2026-03)
- **Licencias:** pesos Apache-2.0 en los tres tamaños. Código nativo en transformers (`qwen3_5`). El repo GitHub `QwenLM/Qwen3.5` redirige a `QwenLM/Qwen3.8` (Apache-2.0).
- **Modelo:** «Causal Language Model with Vision Encoder»; fusión temprana visión-texto (declarado).
- **Formato:** safetensors; sin `auto_map`.
- **GGUF:** solo de terceros (unsloth `@f6d5376b…`, Q4_K_M 1,28 GB).
- **Ollama, biblioteca nativa:** `qwen3.5:0.8b` 1,2 GB, `:2b` 2,7 GB, `:4b` 3,3 GB (vision/tools/thinking).
- **Riesgos:** arquitectura híbrida nueva (Gated DeltaNet), menos rodada en llama.cpp sobre CPU antiguas; el modo thinking puede alargar las respuestas (verificar).
- **Veredicto: Usar (opcional)** como alternativa a comparar con Qwen3-VL-2B en una prueba propia.

#### 3.9 Gemma 4 E2B / E4B · Gemma 3 4B · Gemma 3n
- **Gemma 4:**
  - Código [google-deepmind/gemma](https://github.com/google-deepmind/gemma) Apache-2.0. Pesos Apache-2.0 ([gemma_4_license](https://ai.google.dev/gemma/docs/gemma_4_license)), no gated.
  - E2B: 2,3 B efectivos / 5,1 B con embeddings (declarado).
  - GGUF oficial QAT: E2B 3,35 + 0,99 GB; E4B 5,15 + 0,99 GB.
  - Ollama nativo: `gemma4:e2b` 4,6 GB, `e2b-it-qat` 4,3 GB.
  - Safetensors; sin remote code.
  - **Referencia:** solo para el equipo de 16 GB (alerta 10).
- **Gemma 3 4B y 3n:** Gemma Terms of Use + `gated=manual` (`gemma-3-4b-it@093f9f38…`, `gemma-3n-E2B-it@5e092ebc…`). **Descartar**; los sustituye Gemma 4.

#### 3.10 SmolVLM / SmolVLM2: [huggingface/smollm](https://github.com/huggingface/smollm)
- **Licencias:** código y pesos Apache-2.0.
- **Formato:** safetensors; nativo en transformers (`smolvlm`, `idefics3`); sin remote code.
- **Tamaños:** 2.2B 8,99 GB, 500M-Video 2,03 GB, 256M 0,51 GB en BF16.
- **GGUF:** solo `ggml-org` (mantenedores de llama.cpp, terceros respecto al autor): 2.2B Q4_K_M 1,11 GB + mmproj 0,59 GB.
- **Ollama:** no está en la biblioteca.
- **Mantenimiento:** pesos sin cambios desde 2025-04.
- **Veredicto: Referencia.** Sin ventaja clara sobre Qwen3-VL-2B para leer gráficos.

#### 3.11 Florence-2: [microsoft/Florence-2-base](https://huggingface.co/microsoft/Florence-2-base)
- **Licencias:** pesos MIT.
- **Repo `microsoft/`:** `auto_map` + README con `trust_remote_code=True`; contiene `pytorch_model.bin` (pickle) junto a safetensors.
- **Variante comunitaria** `florence-community/Florence-2-base`: nativa en transformers, solo safetensors (0,46 GB).
- **GGUF / Ollama:** ninguno.
- **Veredicto: Referencia.** OCR con regiones interesante, pero exige torch + transformers.

#### 3.12 moondream2: [vikhyatk/moondream2](https://huggingface.co/vikhyatk/moondream2) · [m87-labs/moondream](https://github.com/m87-labs/moondream)
- **Licencias:** código y pesos Apache-2.0.
- **Exec:** **exige `trust_remote_code=True`** (8+ archivos `.py`).
- **Revisiones:** `main` es mutable (2026-09-23); el README recomienda fijar `revision="2025-06-21"` (SHA `9a7d4024…`).
- **Repo GitHub:** se movió a `m87-labs/moondream`; push 2026-04-20.
- **Ollama:** `moondream:1.8b` (1,7 GB) es de hace unos 2 años.
- **moondream3-preview:** `license:other`, 37 GB, incluye `model_fp8.pt` (pickle). Descartar.
- **Veredicto: Referencia.**

#### 3.13 MiniCPM-V 4.7-1B / MiniCPM-V 4: [OpenBMB/MiniCPM-V](https://github.com/OpenBMB/MiniCPM-V)
- **Licencias:** código Apache-2.0. Pesos **Apache-2.0** (antes «MiniCPM Model License»; verificado en las tarjetas 4.7-1B y V-4).
- **4.7-1B:** nativo en transformers (`transformers>=5.18.0` declarado), sin remote code. GGUF oficial Q4_K_M 0,67 GB.
- **V-4 (4.1B):** `auto_map`, remote code. GGUF oficial Q4_K_M 2,19 GB + mmproj 0,96 GB.
- **Ollama:** solo `openbmb/minicpm-v4.7` (comunitario).
- **Veredicto: Referencia.** Prometedor por tamaño; reevaluar cuando se estabilice (alerta 9).

#### 3.14 InternVL3.5-1B / 2B: [OpenGVLab/InternVL](https://github.com/OpenGVLab/InternVL)
- **Licencias:** repo MIT; pesos Apache-2.0.
- **Exec:** `InternVLChatModel` con `auto_map`, es decir, **remote code**.
- **GGUF / Ollama:** sin GGUF oficial; no está en la biblioteca de Ollama.
- **Mantenimiento:** último push 2025-09-22.
- **Veredicto: Descartar.**

#### 3.15 LFM3-VL-2B / LFM2.5-VL-1.6B (Liquid AI)
- **Licencias:** pesos LFM Open License v1.0 (alerta 8). Código HF de LFM3-VL con `auto_map` (remote code); LFM2.5-VL es nativo.
- **GGUF oficial:**
  - LFM3-VL-2B: Q4_K_M 1,1 GB + mmproj 0,2–0,38 GB.
  - LFM2.5-VL-1.6B: Q4_K_M 0,73 GB + mmproj.
- **Ollama:** `lfm3-vl:2b` 1,5 GB en la biblioteca nativa; requiere 0.40.13.
- **Veredicto: Referencia** (licencia no OSI, lanzamiento muy reciente).

#### 3.16 Granite Vision (IBM): [ibm-granite/granite-vision-models](https://github.com/ibm-granite/granite-vision-models)
- **Licencias:** código y pesos Apache-2.0.
- **3.3-2B:** GGUF oficial Q4_K_M 1,55 + 0,89 GB. En Ollama solo está `granite3.2-vision:2b` (2,4 GB).
- **3.3-2b-chart2csv-preview:** convierte gráficos a CSV; preview; incluye `training_args.bin` (pickle, que no se carga en inferencia).
- **4.1-4B:** remote code; GGUF oficial 2,1 + 1,16 GB.
- **Veredicto: Referencia.** chart2csv es relevante para gráficos, pero está en preview.

#### 3.17 OCR-VLM pequeños (extra 2026)
- **GLM-OCR (0.9B):** [zai-org/GLM-OCR](https://github.com/zai-org/GLM-OCR).
  - Código Apache-2.0; pesos MIT. El pipeline completo usa PP-DocLayoutV3 (Apache-2.0).
  - Nativo en transformers (`glm_ocr`), sin remote code.
  - **Ollama nativo:** `glm-ocr:q8_0` 1,8 GB.
  - 7,6 k★; push 2026-10-14.
  - **Usar (opcional)** para diapositivas o tablas cuando RapidOCR no baste.
- **PaddleOCR-VL-1.6 (0.9B):** Apache-2.0. GGUF oficial 0,94 + 0,88 GB, pero pensado para usarse con el pipeline PaddleOCR (`paddlepaddle>=3.2.1` + llama-server). En transformers usa remote code. **Referencia.**
- **MiniCPM-OCR-1.0 (1.3B):** Apache-2.0 (código y pesos). GGUF oficial Q4_K_M 0,53 + 0,9 GB. Muy nuevo. **Referencia.**
- **Descartar:**
  - **DeepSeek-OCR-2** (3B): Apache-2.0, remote code, 6,78 GB; en Ollama solo hay `deepseek-ocr:3b` v1, de 6,7 GB.
  - **Unlimited-OCR-2** (Baidu): MIT, remote code, 6,69 GB.
  - **jina-ocr-v1:** CC-BY-NC-4.0.
  - **surya-ocr-2.5:** `license:openrail`; revisar sus límites.
- **Otros a vigilar:** Xiaomi-OCR-0 (Apache, base Qwen3.5, 1,75 GB, nativo), LightOnOCR-2-1B (Apache, 2,0 GB), Falcon-OCR (Apache, remote code).

### 4. Consultas (2026-10-30/31)
- `gh api repos/<owner>/<repo>` (★, issues, licencia SPDX, push), `gh api repos/<r>/releases?per_page=3` y `gh api repos/<r>/commits/<tag>` (SHA) para: Breakthrough/PySceneDetect, opencv/opencv-python, opencv/opencv, PaddlePaddle/PaddleOCR, PaddlePaddle/Paddle, RapidAI/RapidOCR, tesseract-ocr/tesseract, tesseract-ocr/tessdata{,_fast,_best}, UB-Mannheim/tesseract, BtbN/FFmpeg-Builds, QwenLM/Qwen3-VL, huggingface/smollm, m87-labs/moondream, OpenBMB/MiniCPM-V, OpenGVLab/InternVL, ollama/ollama, zai-org/GLM-OCR, OpenBMB/MiniCPM-OCR, google-deepmind/gemma, ibm-granite/granite-vision-models.
- `gh api repos/tesseract-ocr/tesseract/releases/tags/5.5.3` (activo del instalador + digest); `gh api repos/UB-Mannheim/tesseract/tags`.
- `gh api repos/BtbN/FFmpeg-Builds/readme` y `…/releases/tags/latest` (activos, `checksums.sha256`, digest).
- `gh api repos/opencv/opencv-python/contents/LICENSE-3RD-PARTY.txt` y `LICENSE.txt`.
- `gh api repos/ollama/ollama/releases/tags/v0.40.1{0,1,2,3}` (notas de LFM3).
- PyPI JSON `https://pypi.org/pypi/<pkg>/json` y `/<pkg>/<ver>/json`: scenedetect, scenedetect-headless, opencv-python-headless, paddleocr, paddlepaddle, paddlex, rapidocr, rapidocr_onnxruntime, onnxruntime, pytesseract.
- API HF `https://huggingface.co/api/models/<repo>?blobs=true` (sha, licencia, gated, archivos y tamaños, `auto_map`), `/api/models/vikhyatk/moondream2/refs` y búsquedas `/api/models?author=<org>&search=<q>&sort=lastModified` (Qwen, google, openbmb, OpenGVLab, LiquidAI, ibm-granite, PaddlePaddle, deepseek-ai, zai-org, lightonai, `search=OCR&sort=trendingScore`).
- Archivos crudos HF (`/raw/main/LICENSE|README.md`): Qwen2.5-VL-3B, Qwen3.5-2B, gemma-4-E2B-it, LFM3-VL-2B, MiniCPM-V-4.7-1B, moondream2, GLM-OCR, PaddleOCR-VL-1.6-GGUF, MiniCPM-OCR-1.0, Florence-2-base.
- `curl https://ollama.com/library/<m>/tags` para qwen3-vl, qwen3.5, gemma4, gemma3, gemma3n, moondream, minicpm-v, granite3.2-vision, glm-ocr, deepseek-ocr, lfm3-vl y qwen2.5vl (200). Devolvieron 404: minicpm-v4.7, granite-vision, paddleocr-vl, lfm2.5-vl, smolvlm, minicpm-ocr.
- WebFetch: https://www.gyan.dev/ffmpeg/builds/ · https://github.com/UB-Mannheim/tesseract/wiki
- Clones `--depth 1 --filter=blob:limit=2m`, solo grep, en `…\scratchpad\t62_clones\`:
  - RapidOCR `80b427d6`
  - PaddleOCR `dab3fe35`
  - PaddleX `ffb64904`
  - PySceneDetect `36ca0229`

## Grupo C — Motores de inferencia y paneles

Auditoría de solo lectura, 2026-10-30/31. Nada instalado ni ejecutado. Las cifras de README se marcan como «declarado». Clones superficiales para grep en `scratchpad\t62_clones\` (ollama @ v0.40.11, llama.cpp @ b12018, open-webui @ v0.12.5).

### 1. Alertas

1. **Ollama contacta `ollama.com` al arrancar `ollama serve`, con un identificador estable.** El servidor (no solo la app) pide `https://ollama.com/api/experimental/model-recommendations` al iniciar y luego cada ~4 h ([server/model_recommendations.go:23,26](https://github.com/ollama/ollama/blob/v0.40.11/server/model_recommendations.go#L23), arranque en [server/routes.go:2514](https://github.com/ollama/ollama/blob/v0.40.11/server/routes.go#L2514)). La petición se firma con la clave `~/.ollama/id_ed25519`: la cabecera `Authorization` lleva `<pubkey>:<firma>` ([server/model_recommendations.go:202](https://github.com/ollama/ollama/blob/v0.40.11/server/model_recommendations.go#L202), [server/cloud_proxy.go:401-406](https://github.com/ollama/ollama/blob/v0.40.11/server/cloud_proxy.go#L401), [auth/auth.go:83](https://github.com/ollama/ollama/blob/v0.40.11/auth/auth.go#L83)). Solo lo desactiva `OLLAMA_NO_CLOUD=1` o `"disable_ollama_cloud": true` en `~/.ollama/server.json` (línea 189). **Prueba local:** el proceso arrancó a las 18:35:49 y `%USERPROFILE%\.ollama\cache\model-recommendations.json` se escribió a las 18:35:56. El archivo contiene modelos `:cloud` con `"required_plan": "pro"`. En este equipo no hay ninguna variable `OLLAMA_*` definida (ni de proceso, ni de usuario, ni de máquina) y no existe `server.json`, así que la nube está activa.
2. **La app de bandeja de Ollama (`ollama app.exe`) está en `Z:\Ollama`.** Busca actualizaciones cada hora y siempre lo hace, porque el ajuste `AutoUpdateEnabled` solo controla la descarga ([app/updater/updater.go:33-36,388,401](https://github.com/ollama/ollama/blob/v0.40.11/app/updater/updater.go#L388)). Esa petición también va firmada con la pubkey (línea 87). La descarga automática está activada por defecto ([app/store/database.go:91](https://github.com/ollama/ollama/blob/v0.40.11/app/store/database.go#L91)). Además, la app recrea el acceso directo de inicio de sesión si falta ([app/cmd/app/app_windows.go:240-267](https://github.com/ollama/ollama/blob/v0.40.11/app/cmd/app/app_windows.go#L240)). No hay variable que desactive la comprobación. Ahora mismo la app **no** se está ejecutando y no hay `Ollama.lnk` en la carpeta Startup. Recomendación: no lanzar nunca `ollama app.exe` y usar solo `ollama.exe serve` (o el zip standalone, que no trae la app).
3. **El Ollama que está en marcha se ejecuta desde una unidad de red.** `Z:` es `\\DESKTOP-TVD562Q\USB` (DriveType 4). Durante la auditoría pasó a «Reconectando» y `Test-Path Z:\Ollama\ollama.exe` devolvió `False`, aunque el proceso 43576 seguía sirviendo. Riesgos: la integridad del binario depende de otro PC (los ejecutables están firmados por «Ollama Inc.», firma Authenticode válida cuando se leyeron) y, si se corta el recurso compartido, fallará la carga de DLL al lanzar un runner nuevo. Para EIM conviene instalar en disco local y verificar el SHA-256.
4. **Las APIs locales no tienen autenticación y su CORS es permisivo.** Ollama no tiene autenticación ([docs/api/authentication.mdx:5](https://github.com/ollama/ollama/blob/v0.40.11/docs/api/authentication.mdx)) y por defecto admite los orígenes `file://*`, `app://*`, `tauri://*` y `vscode-webview://*` ([envconfig/config.go:91-105](https://github.com/ollama/ollama/blob/v0.40.11/envconfig/config.go#L91)). Por tanto, un HTML local abierto en el navegador puede llamar a la API. Comprobado: un origen ajeno recibe `403`. `llama-server` usa por defecto **`cors_origins = "*"`**, deja la web UI y `/slots` activados y no tiene API key ([common/common.h:654-690](https://github.com/ggml-org/llama.cpp/blob/b12018/common/common.h#L654)). Eso permite que cualquier web visitada llame a `127.0.0.1:9931`. **Ojo: el puerto por defecto ya es 9931, no 8080.**
5. **CUDA en Maxwell CC 5.0 solo funciona vía PTX JIT.** Ollama Windows `cuda_v12` compila `50-virtual;52-virtual;60-virtual;61-virtual;70;…` ([llama/server/CMakePresets.json:79](https://github.com/ollama/ollama/blob/v0.40.11/llama/server/CMakePresets.json#L79)), mientras que `cuda_v13` empieza en 75. La documentación exige un driver ≥ 570 para CC 5.0–6.2 y cita la GTX 750 Ti ([docs/gpu.mdx:6-7,35](https://github.com/ollama/ollama/blob/v0.40.11/docs/gpu.mdx)). Este PC tiene el driver 32.0.15.8278 (= 582.78), que cumple. **Observado:** el runner `llama-server.exe` que está en marcha cargó `vulkan\ggml-vulkan.dll` y `ggml-cpu-haswell.dll`, **no** `ggml-cuda.dll`. En la práctica Ollama usa Vulkan (o CPU) en la 750 Ti. En llama.cpp, el zip `win-cuda-12.4` usa la lista por defecto con `50-virtual` ([ggml/src/ggml-cuda/CMakeLists.txt:43-44](https://github.com/ggml-org/llama.cpp/blob/b12018/ggml/src/ggml-cuda/CMakeLists.txt#L43)), y `win-cuda-13.4` no incluye Maxwell. La MX130 del equipo de referencia también es CC 5.0: mismas condiciones.
6. **Open WebUI escucha en `0.0.0.0:8080` por defecto** ([backend/open_webui/\_\_init\_\_.py:39-40](https://github.com/open-webui/open-webui/blob/v0.12.5/backend/open_webui/__init__.py#L39)), es decir, queda expuesto a la LAN. Al arrancar consulta `api.github.com` en busca de versiones ([main.py:2711-2718](https://github.com/open-webui/open-webui/blob/v0.12.5/backend/open_webui/main.py#L2711)) y descarga modelos de embeddings desde HF salvo con `OFFLINE_MODE=true` ([env.py:1250-1255](https://github.com/open-webui/open-webui/blob/v0.12.5/backend/open_webui/env.py#L1250), [config.py:1025-1031](https://github.com/open-webui/open-webui/blob/v0.12.5/backend/open_webui/config.py#L1025)). Su licencia no es OSI (cláusula de marca desde v0.6.6, más CLA).
7. **Ollama tiene un ajuste latente `Survey` («anonymous inference information … shared with Ollama»)** con valor `TRUE` por defecto ([app/store/store.go:133-135](https://github.com/ollama/ollama/blob/v0.40.11/app/store/store.go#L133), [database.go:70](https://github.com/ollama/ollama/blob/v0.40.11/app/store/database.go#L70)). Ningún código lo usa en v0.40.11 (grep), pero hay que reauditarlo en cada actualización. No se encontraron SDK de analítica (posthog, sentry, segment…).
8. **Ollama publica versiones a un ritmo muy alto** (v0.40.6 a v0.40.13 entre el 16 y el 28 de octubre). La versión local, 0.40.11, ya va dos por detrás. Hay que fijar la versión y no usar la app que se actualiza sola.

### 2. Resumen

| Candidato | Veredicto | Licencia | Versión a fijar (tag · commit) |
|---|---|---|---|
| Ollama | **Usar** (solo `ollama.exe serve`, con `OLLAMA_NO_CLOUD=1`, sin la app de bandeja) | MIT (repo completo, incluida la app en `app/`); el servicio ollama.com y los modelos cloud son cerrados | `v0.40.11` · `675150d6ad2747df1e218ef59de9194bc4a7e538` (instalada y medida); siguiente candidata `v0.40.13` · `04088e7c9d41cba5d33bafbf788d87a465c79d5b` |
| llama.cpp (`llama-server`) | **Usar (opcional)**: alternativa directa y más austera; es lo que Ollama ya ejecuta por debajo | MIT | `b12018` · `8956c769e8ababd9fbd89c81764f241d5f515d68` |
| LM Studio | **Descartar** (app propietaria) | App: EULA propietaria; `lms` y `lmstudio-js`: MIT | — |
| vLLM | **Descartar** (no funciona en Windows nativo; exige CC ≥ 7.5) | Apache-2.0 | (`v0.32.0` · `5df63a7203cdb9328d824a27b682e77c7b9928be`, solo como referencia) |
| LocalAI | **Descartar** (sin binario para Windows; descarga backends en ejecución) | MIT | (`v4.12.1` · `ec9274027eadd552d56f2c6c1fe86cd9216a991a`) |
| Open WebUI | **Referencia** (como mucho, panel manual opcional con `OFFLINE_MODE` y bind a 127.0.0.1) | «Open WebUI License» (BSD-3 + cláusula de marca, no OSI) | `v0.12.5` · `f7ac7ee10962ddec0017f5c29b6740d9b9c5faca` |
| OpenVINO GenAI (extra) | **Referencia** (interesante para CPU Intel 6.ª/8.ª gen.; exige convertir el modelo a IR) | Apache-2.0 | `2026.4.1.0` · `ab01d1771e4adaa0e1e08e9d630def170572506c` |
| llamafile (extra) | Referencia | Apache-2.0 (+ partes MIT de llama.cpp) | `0.10.6` · `017cdeb4b7217c0fb44cc7b61f44bd8ab2749dd2` |
| koboldcpp (extra) | Descartar | AGPL-3.0 | (`v1.124` · `4f78d791c5698ef62f0d317f8b2d9703e513ceaf`) |
| ONNX Runtime GenAI (extra) | Referencia (sin servidor HTTP propio) | MIT | PyPI `0.18.0`; GitHub `v0.17.0` · `1d67be30e5b1ed0c264f6f41c598f85157e8288b` |

### 3. Detalle por candidato

#### 3.1 Ollama — https://github.com/ollama/ollama
- **Licencia:** [MIT](https://github.com/ollama/ollama/blob/main/LICENSE). El código de la app de escritorio, la bandeja, el actualizador y la UI está en `app/` dentro del mismo repo y bajo esa licencia. Lo cerrado es el servicio: ollama.com, los modelos `:cloud` (planes «pro») y la búsqueda web.
- **Mantenimiento:** ★185 390 · 4 508 issues/PR abiertos · último push 2026-10-30 · última release v0.40.13 (2026-10-28).
- **Pruebas:** workflows `test.yaml`, `test-install.yaml`, `test-llamacpp-update.yaml` y otros; 36 archivos en `integration/`.
- **Instalación en Windows:** `OllamaSetup.exe` (1,68 GB, sin admin, en `%LOCALAPPDATA%\Programs\Ollama`, añade la ruta al PATH de usuario y crea el inicio automático) o `ollama-windows-amd64.zip` (1,60 GB, solo CLI y librerías, sin app; documentado para servicio con NSSM, [docs/windows.mdx](https://github.com/ollama/ollama/blob/v0.40.11/docs/windows.mdx)). Trae su propio VC++ runtime (msvcp140 en cada subcarpeta), además de CUDA 12/13, ROCm 7.1, Vulkan y variantes de CPU (sse42 → haswell/AVX2 → … zen4). SHA-256 publicados en `sha256sum.txt`: v0.40.11 zip `bda4a493ba8a7c24d57263cd843cd68cee84f44aed4299eeed532acad7eda12a`, Setup `87309d23b423abeae1d8df2f98df95f94bf35659debfdf3761d65b7b62a75508`; v0.40.13 zip `7afa3862…cc19`, Setup `9e3c76e5…e719`.
- **Arquitectura 0.40.x:** `ollama.exe serve` lanza `lib\ollama\llama-server.exe` (llama.cpp `b11845` vendorizado, archivo `LLAMA_CPP_VERSION`) con `--host 127.0.0.1 --no-webui --offline` (línea de comandos observada en el proceso 10484).
- **Red, telemetría y actualización:** ver alertas 1, 2 y 7. Ni el servidor ni la CLI tienen actualizador (grep de `api/update` solo aparece en `app/updater`). Variables útiles ([envconfig/config.go:313-337](https://github.com/ollama/ollama/blob/v0.40.11/envconfig/config.go#L313)): `OLLAMA_NO_CLOUD`, `OLLAMA_HOST`, `OLLAMA_ORIGINS`, `OLLAMA_MODELS`, `OLLAMA_KEEP_ALIVE`, `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_NUM_PARALLEL`, `OLLAMA_NOPRUNE` (no purgar blobs al arrancar), `OLLAMA_REMOTES` (por defecto «ollama.com») y `OLLAMA_VULKAN=0` para desactivar Vulkan. No existe variable para desactivar el actualizador de la app.
- **Descargas en ejecución:** solo con `pull` o con un `create` remoto. `pull` verifica el SHA-256 de cada blob y borra los que no coinciden ([server/images.go:1842-1858](https://github.com/ollama/ollama/blob/v0.40.11/server/images.go#L1842), [transfer/download.go:343](https://github.com/ollama/ollama/blob/v0.40.11/transfer/download.go#L343)). Los manifiestos vienen del registro de ollama.com (TLS, sin firma independiente).
- **API:** bind `127.0.0.1:11434` por defecto (verificado con `netstat`), sin autenticación, CORS según la alerta 4. Ofrece API nativa, `/v1/chat/completions` y `/v1/responses` compatibles con OpenAI y compatibilidad con Anthropic. Salida estructurada con `format: "json"` o un objeto JSON Schema ([docs/capabilities/structured-outputs.mdx](https://github.com/ollama/ollama/blob/v0.40.11/docs/capabilities/structured-outputs.mdx)). Admite herramientas y «thinking».
- **GPU:** ver alerta 5. Vulkan va activado por defecto si el backend está instalado ([docs/gpu.mdx:141-171](https://github.com/ollama/ollama/blob/v0.40.11/docs/gpu.mdx#L141)).
- **Instalación local leída:** versión `0.40.11` (`/api/version`) · binarios `Z:\Ollama\ollama.exe` y `Z:\Ollama\ollama app.exe` (firmados por Ollama Inc.; `Z:` = `\\DESKTOP-TVD562Q\USB`; `lib\Ollama.lnk` apunta a `E:\Ollama\ollama app.exe`) · proceso `"Z:\Ollama\ollama.exe" serve` (sin la app) · modelo `qwen3:4b` Q4_K_M de 2 497 293 931 B (`digest 359d7dd4…`) · `%USERPROFILE%\.ollama\` contiene `id_ed25519(.pub)`, `models\` (2,33 GB) y `cache\model-recommendations.json` · no existen `%LOCALAPPDATA%\Ollama` (ni logs), `%LOCALAPPDATA%\Programs\Ollama`, entrada de desinstalación en el registro, `Ollama.lnk` en Startup, entrada en `Run` ni variables `OLLAMA_*`.
- **Tamaño en disco:** instalador 1,68 GB (declarado por el tamaño del asset); el directorio `lib\ollama` incluye unos 2 GB de librerías CUDA y ROCm que se pueden omitir.
- **Riesgos:** la llamada a la nube por defecto, la app con autoactualización, el ritmo de releases, los orígenes `file://` en CORS y la ejecución desde una unidad de red.
- **Veredicto: Usar.** Es MIT, ya está medido en el equipo y expone una API OpenAI y JSON Schema en 127.0.0.1. Condiciones: lanzar solo `ollama.exe serve` desde disco local con `OLLAMA_NO_CLOUD=1`, `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_NOPRUNE=1` y sin la app de bandeja, con la versión fijada y el SHA-256 verificado.

#### 3.2 llama.cpp — https://github.com/ggml-org/llama.cpp
- **Licencia:** [MIT](https://github.com/ggml-org/llama.cpp/blob/master/LICENSE), todo abierto.
- **Mantenimiento:** ★132 901 · 2 589 issues/PR abiertos · push 2026-10-31 · tags `bNNNN` varias veces al día (b12015 → b12019 en unas 24 h).
- **Pruebas:** más de 60 workflows de CI (incluidos `build-cuda-windows.yml`, `build-vulkan.yml`, `server.yml` y `server-sanitize.yml`) y 74 archivos en `tests/`.
- **Binarios Windows (b12018):** `win-cpu-x64.zip` (24,6 MB, `GGML_CPU_ALL_VARIANTS` con DLL cargada en tiempo de ejecución según AVX2 y demás), `win-vulkan-x64.zip` (37,5 MB), `win-cuda-12.4-x64.zip` (280 MB) + `cudart-…-12.4` (391 MB), `win-cuda-13.4`, `win-openvino-2026.4.1-x64.zip` (104,6 MB), `win-sycl` y `win-rocm-10.0`. CUDA y CC 5.0: ver alerta 5.
- **Red:** con `-m <ruta>` no hay red. `-hf <repo>` descarga desde HF y también admite el registro de Docker ([common/download.cpp:908,968](https://github.com/ggml-org/llama.cpp/blob/b12018/common/download.cpp#L908)). `--offline` (o `LLAMA_ARG_OFFLINE`) fuerza la caché y bloquea la red ([common/arg.cpp:3927-3932](https://github.com/ggml-org/llama.cpp/blob/b12018/common/arg.cpp#L3927)). `--connect` (túnel P2P experimental) está desactivado por defecto y no descarga nada por sí solo ([tools/server/server-connect.cpp:180-183](https://github.com/ggml-org/llama.cpp/blob/b12018/tools/server/server-connect.cpp#L180)). No hay telemetría ni actualizador en `tools/server` ni en `common` (grep de URLs).
- **API:** compatible con OpenAI (`/v1/chat/completions` y otros). Gramáticas con `--grammar` y JSON Schema con `-j/--json-schema` (arg.cpp:2219,2233), y `response_format` por petición. Valores por defecto: `127.0.0.1:9931`, CORS `*`, web UI activada, `/slots` activado, sin API key (alerta 4). Arranque endurecido: `--host 127.0.0.1 --no-webui --offline --api-key <k> --cors-origins localhost --no-slots -np 1`.
- **Riesgos:** releases muy frecuentes sin canal LTS y cambios de valores por defecto entre versiones (el puerto pasó a 9931). Hay que fijar el número de build y guardar el SHA-256 del zip.
- **Veredicto: Usar (opcional).** Es MIT, son binarios pequeños y es el motor que Ollama ya lanza por debajo. Sirve de plan B si Ollama introduce más llamadas a la nube, siempre que se arranque con los flags de arriba.

#### 3.3 LM Studio — https://lmstudio.ai
- **Licencia:** la app es propietaria: «exclusive property of Company», prohíbe la ingeniería inversa y las obras derivadas ([app-terms](https://lmstudio.ai/app-terms), versión del 23-08-2026). [`lms`](https://github.com/lmstudio-ai/lms) (★5 393) y [`lmstudio-js`](https://github.com/lmstudio-ai/lmstudio-js) (★1 805) son MIT, pero solo son clientes de la app cerrada.
- **Red:** según su [privacidad](https://lmstudio.ai/app-privacy) (junio de 2026), declara «no telemetry». Aun así envía comprobaciones de actualización (versión, SO e IP) y búsquedas anonimizadas de modelos, sin opción documentada para desactivarlas. Ofrece funciones cloud opcionales.
- **Veredicto: Descartar.** No es código abierto y no se puede auditar ni fijar por commit. Se confirma lo previsto.

#### 3.4 vLLM — https://github.com/vllm-project/vllm
- **Licencia:** Apache-2.0 · ★95 938 · 9 636 issues/PR abiertos · v0.32.0 (2026-10-18).
- [Docs GPU](https://docs.vllm.ai/en/latest/getting_started/installation/gpu.html): «vLLM does not support Windows natively» (solo con WSL). La GPU debe tener «compute capability 7.5 or higher». Python 3.11–3.14. Las ruedas `+cpu` solo existen para Linux (manylinux) y macOS; en PyPI no hay rueda `win_amd64`.
- **Veredicto: Descartar.** Ni la GTX 750 Ti ni la MX130 (CC 5.0) son compatibles, no hay Windows nativo y está pensado para servidores. Se confirma lo previsto.

#### 3.5 LocalAI — https://github.com/mudler/LocalAI
- **Licencia:** MIT · ★50 082 · v4.12.1 (2026-10-23).
- Los assets de la release solo incluyen Linux, macOS y AppImage: no hay binario para Windows. Las [docs de instalación](https://localai.io/docs/installation/) recomiendan contenedores. Según el README, «backends are separate and pulled on demand», y LocalAI «automatically detects your GPU capabilities and downloads the appropriate backend» (imágenes OCI firmadas con cosign desde la 4.3, declarado).
- **Veredicto: Descartar.** En Windows exige Docker o WSL, descarga backends en ejecución y añade una capa extra sobre llama.cpp.

#### 3.6 Open WebUI — https://github.com/open-webui/open-webui
- **Licencia:** [Open WebUI License](https://github.com/open-webui/open-webui/blob/main/LICENSE): BSD-3 más una cláusula 4 que prohíbe alterar la marca «Open WebUI» salvo con ≤ 50 usuarios en 30 días, permiso escrito o licencia enterprise. Exige además una CLA. La cláusula entró con el commit [`60d84a3`](https://github.com/open-webui/open-webui/commit/60d84a3aae9802339705826e9095e272e3c83623) del 18-04-2025 («license "branding" clause»), que ya está en v0.6.6 y no en v0.6.5 (comparación por API). El código anterior sigue bajo BSD-3 ([LICENSE_HISTORY](https://github.com/open-webui/open-webui/blob/main/LICENSE_HISTORY)). El texto se retocó por última vez el 14-04-2026.
- **Mantenimiento:** ★157 307 · v0.12.5 (2026-10-29). PyPI: `open-webui` 0.12.5, Python ≥ 3.11 y < 3.13. Tiene unas 127 dependencias fijadas, entre ellas torch/transformers 5.5.4, sentence-transformers, chromadb 1.5.9 y playwright.
- **Red:** comprobación de versiones en GitHub y descarga de `all-MiniLM-L6-v2` desde HF (alerta 6). El Dockerfile fija `SCARF_NO_ANALYTICS=true`, `DO_NOT_TRACK=true` y `ANONYMIZED_TELEMETRY=false` (líneas 95-97); en una instalación con pip hay que definirlas a mano. `ENABLE_OTEL` está desactivado por defecto.
- **Autenticación:** `WEBUI_AUTH=True` por defecto ([env.py:785](https://github.com/open-webui/open-webui/blob/v0.12.5/backend/open_webui/env.py#L785)); la primera cuenta que se registra pasa a ser admin. Bind `0.0.0.0:8080`.
- **Veredicto: Referencia.** La licencia no es OSI, es pesado (torch) y tiene red por defecto. Si alguna vez se quiere un panel manual: `OFFLINE_MODE=true`, `--host 127.0.0.1` y las tres variables anti-telemetría, en un venv aparte y nunca dentro de EIM.

#### 3.7 Extras
- **OpenVINO GenAI** (https://github.com/openvinotoolkit/openvino.genai, Apache-2.0, ★606, 2026.4.1.0 del 01-10-2026). Hay rueda `win_amd64`. Los [requisitos](https://github.com/openvinotoolkit/openvino/blob/master/docs/articles_en/about-openvino/release-notes-openvino/system-requirements.rst) cubren Intel Core de 6.ª a 14.ª generación (incluye el i5-6400 y el i5-8250U), Windows 10/11 de 64 bits y GPU «Intel UHD Graphics» (UHD 620, líneas 27, 34 y 52). `openvino` depende de `openvino-telemetry`, que solo transmite si existe el archivo de consentimiento con «yes» ([README](https://github.com/openvinotoolkit/telemetry)). Necesita modelos en formato IR, ya convertidos o mediante `optimum-intel`, que arrastra torch. El servidor compatible con OpenAI es aparte (OpenVINO Model Server). llama.cpp también publica `win-openvino` como backend. **Referencia**, para medir más adelante en la CPU y la iGPU del equipo de referencia.
- **llamafile** (mozilla-ai, Apache-2.0, ★26 530, 0.10.6 del 15-09-2026). Es un único ejecutable que incluye llama.cpp; en Windows hay que renombrarlo a `.exe` y tiene un límite de 4 GB por ejecutable (declarado). **Referencia**: no aporta nada frente a llama.cpp, que es upstream.
- **koboldcpp** (AGPL-3.0, ★12 103, v1.124 del 31-10-2026). Ofrece exe para Windows (`koboldcpp.exe`, `-nocuda` y `-oldpc`). **Descartar**: la licencia es AGPL, está orientado a UI y rol, y su API OpenAI es secundaria.
- **ONNX Runtime GenAI** (MIT, ★1 148, PyPI 0.18.0). Hay rueda `win_amd64` y zip CUDA, pero no trae servidor HTTP. **Referencia.**

### 4. Consultas (2026-10-30/31)
- Local: `Get-ChildItem Z:\Ollama`, `Z:\Ollama\lib -Depth 2`, `~\.ollama`, `~\.ollama\cache`; `Get-AuthenticodeSignature`; `Get-CimInstance Win32_Process` (PID 43576/10484 CommandLine), `(Get-Process 10484).Modules`; `Win32_VideoController` (driver 32.0.15.8278); `Win32_LogicalDisk Z:` y `net use`; registro Uninstall y `HKCU\…\Run`; variables `OLLAMA_*` de proceso, usuario y máquina; `netstat -ano`.
- `curl http://127.0.0.1:11434/api/version` → `0.40.11`; `/api/tags` → `qwen3:4b`; `/api/version` con `Origin: http://evil.example` → 403. No se usó ningún otro endpoint.
- `gh api repos/{ollama/ollama, ggml-org/llama.cpp, vllm-project/vllm, mudler/LocalAI, open-webui/open-webui, lmstudio-ai/lms, lmstudio-ai/lmstudio-js, mozilla-ai/llamafile, LostRuins/koboldcpp, microsoft/onnxruntime-genai, openvinotoolkit/openvino.genai}` (metadatos y `/releases`); `gh api …/open-webui/contents/LICENSE|LICENSE_HISTORY`, `commits?path=LICENSE`, `compare/v0.6.5…60d84a3`, `compare/v0.6.6…60d84a3`; `gh api …/mudler/LocalAI/readme`; `gh api …/openvinotoolkit/openvino/contents/docs/…/system-requirements.rst`; `gh api …/openvinotoolkit/telemetry/readme`.
- `git ls-remote --tags` para los SHA de cada tag; `curl https://github.com/ollama/ollama/releases/download/v0.40.{11,13}/sha256sum.txt`.
- Clones `--depth 1 --filter=blob:limit=2m` (solo lectura y grep): `ollama@v0.40.11`, `llama.cpp@b12018`, `open-webui@v0.12.5` (sparse `backend`, `pyproject.toml`, `Dockerfile`).
- PyPI JSON: `open-webui`, `vllm`, `openvino`, `openvino-genai`, `optimum-intel`, `onnxruntime-genai`.
- Web: https://docs.ollama.com/faq · https://docs.vllm.ai/en/latest/getting_started/installation/gpu.html · https://lmstudio.ai/app-terms · https://lmstudio.ai/app-privacy · https://localai.io/docs/installation/ · búsqueda de requisitos de OpenVINO (la página de docs.openvino.ai era demasiado grande y se usó el `.rst` del repo).

## Grupo D — LLM de texto (≤ 4B cuantizados) y embeddings

Auditoría de solo lectura hecha el 2026-10-30/31. No se instaló nada, no se ejecutó código de terceros y no se descargaron pesos. Las fuentes fueron la API de Hugging Face (`/api/models/<repo>?blobs=true`), los README y LICENSE en crudo, las páginas `ollama.com/library/<modelo>` y `/tags`, y las páginas de licencia de Google y Meta. Las cifras de benchmarks son las **declaradas** en las fichas. «Digest Ollama» es el ID de 12 hex que muestra ollama.com, el mismo que da `ollama list` (el `qwen3:4b` de este equipo, `359d7dd4bcda`, coincide).

**MÍNIMO** = i5-8250U, 7,9 GB de RAM (≈ 5–6 GB útiles), todo en CPU y un modelo a la vez.

---

### 1. Alertas

1. **El `qwen3:4b` instalado es Qwen3-4B-*Thinking*-2507.** Su digest `359d7dd4bcda` es el mismo que el de `qwen3:4b-thinking-2507-q4_K_M`: 2,5 GB y 256K de contexto. No es el Qwen3-4B híbrido de abril de 2025, que hoy es `qwen3:4b-q4_K_M` (`2bfd38a7daaf`, 40K de contexto). Este modelo razona siempre (`<think>…</think>`), así que la extracción de JSON sale más lenta y más larga. Para el uso (a) conviene `qwen3:4b-instruct` (`0edcdef34593`, la misma licencia Apache-2.0 y el mismo tamaño, sin modo de razonamiento).
2. **Qwen2.5-3B-Instruct no es Apache: lleva la Qwen RESEARCH License** ([LICENSE](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/blob/main/LICENSE), del 19-09-2024). Solo permite usos no comerciales, «research or evaluation». El uso comercial exige pedir licencia. Quien redistribuya pesos o modificaciones debe incluir el acuerdo y un archivo Notice. Si sus salidas se usan para entrenar un modelo que se distribuye, hay que poner «Built with Qwen». El `qwen2.5:3b` de Ollama trae esta misma licencia. En cambio, Qwen2.5-1.5B-Instruct sí es Apache-2.0.
3. **Gemma 3 (1B/4B), Gemma 3n (E2B/E4B) y EmbeddingGemma-300m usan los [Gemma Terms of Use](https://ai.google.dev/gemma/terms)** (versión del 1-04-2026) más la [Prohibited Use Policy](https://ai.google.dev/gemma/prohibited_use_policy). En HF son `gated=manual`.
   - Para uso personal y local están permitidos. La política prohíbe la práctica no licenciada de una profesión y las afirmaciones engañosas de pericia en finanzas, y restringe las decisiones automatizadas en finanzas que afecten a terceros. Google se reserva el derecho a restringir el uso «remotely or otherwise».
   - Las salidas no se consideran «Model Derivative» y Google no reclama derechos sobre ellas. Un modelo destilado de esas salidas sí sería un derivado.
   - Quien redistribuya pesos o derivados debe trasladar las restricciones y adjuntar el aviso.
   - **Gemma 4 y EmbeddingGemma 2 pasaron a Apache-2.0** ([Gemma 4 license](https://ai.google.dev/gemma/docs/gemma_4_license)) y no son gated. La página de la política de uso prohibido no aclara si también aplica a Gemma 4; la ficha del modelo solo cita Apache-2.0.
4. **Llama 3.2 1B/3B usan la [Llama 3.2 Community License](https://raw.githubusercontent.com/meta-llama/llama-models/main/models/llama3_2/LICENSE) más la [AUP](https://raw.githubusercontent.com/meta-llama/llama-models/main/models/llama3_2/USE_POLICY.md)** y son `gated=manual`.
   - El uso personal está permitido. La AUP prohíbe la «unlicensed practice of any profession», incluidas las financieras, y el fraude o la desinformación.
   - Quien redistribuya pesos debe incluir la licencia, «Built with Llama» y un archivo Notice. Un modelo entrenado con sus salidas y luego distribuido debe llevar un nombre que empiece por «Llama».
   - Hay una cláusula para servicios de más de 700M de usuarios activos mensuales. La exclusión de la UE para modelos multimodales no se verificó en esta consulta.
   - El repo de HF trae además `original/consolidated.00.pth` (pickle).
5. **Mistral: Ministral-8B-Instruct-2410 está bajo la [Mistral Research License](https://mistral.ai/licenses/MRL-0.1.md)**, solo para investigación y uso no comercial, y además tiene 8B. **Ministral-3-3B-2512 sí es Apache-2.0.** Ojo: los pesos del repo principal de Ministral-3-3B-2512 están en **FP8**; la versión BF16 está en `-BF16`, y lo práctico es usar el GGUF.
6. **LiquidAI LFM2.5 (2.6B, 1.2B y Embedding-350M) usan la LFM Open License v1.0** ([LICENSE](https://huggingface.co/LiquidAI/LFM2.5-2.6B/blob/main/LICENSE)). Es de tipo Apache, con un límite: el uso comercial no está licenciado para entidades con ≥ 10 M USD de ingresos anuales. El uso personal no comercial no tiene ese límite. Para redistribuir hay que incluir la licencia y los avisos. Si se incumple, la licencia termina automáticamente.
7. **jina-embeddings-v5 (nano/small) son CC-BY-NC-4.0 y además requieren `trust_remote_code`.** Se descartan.
8. **Modelos con `trust_remote_code` o código `.py` en el repo** (la ruta GGUF/Ollama no ejecuta Python):
   - `microsoft/Phi-4-mini-instruct`: tiene `auto_map` y `modeling_phi3.py`, y su README usa `trust_remote_code=True`, aunque transformers ya trae Phi3 de forma nativa.
   - `Phi-4-mini-flash-reasoning`: arquitectura propia `phi4flash`, el código remoto es obligatorio.
   - `nomic-embed-text-v1.5`: requiere código remoto hasta transformers 5.5 y sentence-transformers 5.3, según su README.
   - `nomic-embed-text-v2-moe` y `snowflake-arctic-embed-m-v2.0` (GTE): requieren código remoto.
   - `LFM2.5-Embedding-350M`: requiere código remoto.
   - `granite-4.2-3b`: incluye `granite_thinking_parser.py`, un parser auxiliar que no está en `auto_map`.
9. **Pickle.** `BAAI/bge-m3` **no tiene safetensors**: sus pesos están en `pytorch_model.bin` (2,27 GB), `colbert_linear.pt` y `sparse_linear.pt`. Como alternativas hay `onnx/model.onnx_data` (fp32, 2,27 GB) o el GGUF de Ollama. Llama 3.2 trae `.pth` y también safetensors. e5 y granite-embedding R1 tienen `pytorch_model.bin` junto a `model.safetensors`, así que hay que usar los safetensors. Los `.bin` de OpenVINO son IR, no pickle.
10. **Sin GGUF oficial del autor, solo el de la biblioteca de Ollama o de terceros:**
    - **Qwen3-4B-Instruct-2507**: no existe `Qwen/…-GGUF`; `ggml-org` solo publica Q8_0 (4,28 GB). El Q4_K_M sale de Ollama o de unsloth o lmstudio-community.
    - **Qwen3.5-2B/4B**: no hay `Qwen/…-GGUF`; `ggml-org` solo publica 0.8B. Quedan Ollama, unsloth y bartowski.
    - **Phi-4-mini**: no hay GGUF de Microsoft. Quedan Ollama, unsloth y bartowski.
    - **Llama 3.2**: no hay GGUF de Meta. Quedan Ollama, bartowski y hugging-quants.
    - **DeepSeek-R1-Distill-1.5B**: no hay GGUF de DeepSeek. Además, `unsloth/…-GGUF` declara apache-2.0 cuando el original es MIT: los metadatos de terceros no son fiables.
    - **Gemma 3n**: solo `ggml-org`, y solo en Q8_0.
    - El GGUF oficial de **Qwen3-1.7B** solo existe en Q8_0 (1,83 GB).
11. **Manifiestos de Ollama sin capa de licencia:** `gemma3:*-it-qat`, `qwen3-embedding:0.6b`, `nomic-embed-text-v2-moe`, `snowflake-arctic-embed2` y `embeddinggemma-2`. En esos casos la licencia hay que tomarla del repo de HF.
12. **Etiquetas de Ollama engañosas:**
    - `llama3.2:1b` por defecto es **Q8_0** (1,3 GB) y `granite4:1b` por defecto es **BF16** (3,3 GB). Conviene fijar la etiqueta `…q4_K_M` explícita.
    - En `qwen3.5`, `gemma4` y `embeddinggemma-2`, la etiqueta por defecto es un índice multiformato (mlx + llamacpp), con un digest distinto del de la variante llama.cpp. Hay que fijar la variante concreta, por ejemplo `qwen3.5:4b-q4_K_M` (`d8b0f5e9760c`).
    - En los modelos multimodales, el tamaño de Ollama incluye el proyector de visión. `qwen3.5:4b-q4_K_M` ocupa 3,3 GB, de los que 676 MB son proyector BF16.

---

### 2. Resumen LLM (texto, ≤ 4B)

| Modelo | Tamaño | Licencia pesos | Gated | GGUF oficial | Ollama (digest) | Q4 declarado | Veredicto MÍNIMO |
|---|---|---|---|---|---|---|---|
| [Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) | 4,02B | Apache-2.0 | no | no (solo ggml-org Q8_0) | `qwen3:4b-instruct` `0edcdef34593` | 2,5 GB (Ollama Q4_K_M) | **Usar** (principal para (a)) |
| [Qwen3-4B-Thinking-2507](https://huggingface.co/Qwen/Qwen3-4B-Thinking-2507) | 4,02B | Apache-2.0 | no | no | `qwen3:4b` = `qwen3:4b-thinking` `359d7dd4bcda` (instalado) | 2,5 GB | Usar (opcional; razonamiento, no extracción masiva) |
| [Qwen3-4B](https://huggingface.co/Qwen/Qwen3-4B) (híbrido, 2025-04) | 4,02B | Apache-2.0 | no | **sí** `Qwen/Qwen3-4B-GGUF` | `qwen3:4b-q4_K_M` `2bfd38a7daaf` | 2,50 GB (oficial) / 2,6 GB | Referencia (superado por 2507) |
| [Qwen3-1.7B](https://huggingface.co/Qwen/Qwen3-1.7B) | 2,03B | Apache-2.0 | no | sí, solo Q8_0 (1,83 GB) | `qwen3:1.7b` `8f68893c685c` | 1,4 GB | Usar (opcional; respaldo con poca RAM) |
| [Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B) (2026-02) | 4,66B (incl. visión) | Apache-2.0 | no | no (terceros: unsloth/bartowski) | `qwen3.5:4b-q4_K_M` `d8b0f5e9760c` | 3,3 GB (2,6 GB modelo + 0,68 GB visión) | Usar (opcional; comparar con 2507) |
| [Qwen3.5-2B](https://huggingface.co/Qwen/Qwen3.5-2B) | 2,27B | Apache-2.0 | no | no | `qwen3.5:2b-q4_K_M` `1e2d21a4f03a` | 1,9 GB | Usar (opcional; ligero) |
| [Qwen3.5-0.8B](https://huggingface.co/Qwen/Qwen3.5-0.8B) | 0,87B | Apache-2.0 | no | ggml-org (Q4_0 0,56 GB) | `qwen3.5:0.8b-q8_0` `7c00f78aed0f` | 1,0 GB (Q8) | Referencia |
| [Qwen2.5-3B-Instruct](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct) | 3,09B | **qwen-research** | no | sí (q4_k_m 2,10 GB) | `qwen2.5:3b` `357c53fb659c` | 1,9 GB | **Descartar** (licencia) |
| [Qwen2.5-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct) | 1,54B | Apache-2.0 | no | sí | `qwen2.5:1.5b` `65ec06548149` | 986 MB | Referencia |
| [Gemma 3 4B it](https://huggingface.co/google/gemma-3-4b-it) | 4,30B (incl. visión) | **Gemma ToU** | **sí** | sí: QAT q4_0 (3,16 + 0,85 mmproj) | `gemma3:4b` `68ceab7e468a` | 3,4 GB | Descartar (ToU; superado por Gemma 4) |
| [Gemma 3 1B it](https://huggingface.co/google/gemma-3-1b-it) | 1,00B | **Gemma ToU** | **sí** | sí: QAT q4_0 1,0 GB | `gemma3:1b` `97558784bdc9` | 806 MB | Descartar |
| [Gemma 3n E2B/E4B it](https://huggingface.co/google/gemma-3n-E2B-it) | 5,44B / 7,85B totales | **Gemma ToU** | **sí** | no (ggml-org solo Q8_0) | `gemma3n:e2b` `dae166dc6a5e` / `e4b` `0a377808afea` | 7,8 / 9,8 GB | Descartar (no cabe) |
| [Gemma 4 E2B it](https://huggingface.co/google/gemma-4-E2B-it) (2026-03) | 2,3B efectivos / 5,1B totales | Apache-2.0 | no | **sí** QAT q4_0 (3,35 + 0,99 mmproj); ggml-org Q4_0 2,84 | `gemma4:e2b-it-qat` `07ea59a47401` | 4,3 GB (QAT) / 4,6 GB (Q4_K_M) | Referencia (justo en MÍNIMO; opcional en este PC) |
| [Gemma 4 E4B it](https://huggingface.co/google/gemma-4-E4B-it) | 4,5B efectivos / 8B totales | Apache-2.0 | no | sí, QAT q4_0 5,15 GB | `gemma4:e4b-it-qat` `ee6656371218` | 6,1 GB | Descartar (no cabe) |
| [Llama 3.2 3B Instruct](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct) | 3,21B | **Llama 3.2 CL + AUP** | **sí** | no (terceros) | `llama3.2:3b` `a80c4f17acd5` | 2,0 GB | Referencia |
| [Llama 3.2 1B Instruct](https://huggingface.co/meta-llama/Llama-3.2-1B-Instruct) | 1,24B | **Llama 3.2 CL + AUP** | **sí** | no | `llama3.2:1b-instruct-q4_K_M` `22bc6b92eb01` (la etiqueta por defecto es Q8) | 808 MB | Referencia |
| [Phi-4-mini-instruct](https://huggingface.co/microsoft/Phi-4-mini-instruct) | 3,84B | MIT | no | no (terceros) | `phi4-mini:3.8b` `78fad5d182a7` | 2,5 GB | Usar (opcional) |
| [Phi-4-mini-reasoning](https://huggingface.co/microsoft/Phi-4-mini-reasoning) | 3,84B | MIT | no | no | `phi4-mini-reasoning` `3ca8c2865ce9` | 3,2 GB | Referencia (solo inglés, matemáticas) |
| [Phi-4-mini-flash-reasoning](https://huggingface.co/microsoft/Phi-4-mini-flash-reasoning) | 3,85B | MIT | no | no | — | — | Descartar (código remoto obligatorio) |
| [Ministral-3-3B-Instruct-2512](https://huggingface.co/mistralai/Ministral-3-3B-Instruct-2512) | 3,85B (3,4B LM + 0,4B visión) | Apache-2.0 | no | **sí** `mistralai/…-GGUF` Q4_K_M 2,15 GB (+0,84 mmproj) | `ministral-3:3b` `f04aa1c738f6` | 3,0 GB | Usar (opcional) |
| [Ministral-8B-Instruct-2410](https://huggingface.co/mistralai/Ministral-8B-Instruct-2410) | 8,02B | **MRL (investigación)** | no | — | — | — | Descartar |
| [DeepSeek-R1-Distill-Qwen-1.5B](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B) | 1,78B | MIT (base Qwen2.5, Apache) | no | no (terceros) | `deepseek-r1:1.5b` `e0979632db5a` | 1,1 GB | Descartar (solo razonamiento) |
| [Granite-4.1-3B](https://huggingface.co/ibm-granite/granite-4.1-3b) (2026-04) | 3,40B | Apache-2.0 | no | **sí** Q4_K_M 2,10 GB | `granite4.1:3b` `6fd349357287` | 2,1 GB | Usar (opcional) |
| [Granite-4.2-3B](https://huggingface.co/ibm-granite/granite-4.2-3b) (2026-08) | 3,66B | Apache-2.0 | no | **sí** Q4_K_M 2,24 GB | `granite4.2:3b` `40577dc168a3` | 2,2 GB | Usar (opcional; razonamiento) |
| [Granite-4.0-micro / h-micro](https://huggingface.co/ibm-granite/granite-4.0-h-micro) | 3,40B / 3,19B | Apache-2.0 | no | sí: 2,10 / 1,94 GB | `granite4:micro` `89962fcc7523` / `micro-h` `076afb3855dc` | 2,1 / 1,9 GB | Referencia (superado por 4.1/4.2) |
| [Granite-4.0-1b / h-1b](https://huggingface.co/ibm-granite/granite-4.0-1b) | 1,63B / 1,46B | Apache-2.0 | no | sí (base GGUF) | `granite4:1b-h` `7761ae79cab9` (Q8, 1,6 GB) | — | Referencia |
| [SmolLM3-3B](https://huggingface.co/HuggingFaceTB/SmolLM3-3B) | 3,08B | Apache-2.0 | no | ggml-org Q4_K_M 1,92 GB | **no está en la biblioteca** | 1,92 GB | Referencia |
| [LFM2.5-2.6B](https://huggingface.co/LiquidAI/LFM2.5-2.6B) (2026-07) | 2,70B | **LFM Open v1.0** | no | **sí** Q4_K_M 1,67 GB | no (solo `lfm2.5-thinking:1.2b` `95bd9d45385f` y `lfm2.5:8b`) | 1,67 GB | Referencia |

Contexto, idiomas y salida estructurada declarados en las fichas:

| Modelo | Contexto declarado | Español | Tools / JSON (declarado) | SHA HF (revisión) |
|---|---|---|---|---|
| Qwen3-4B-Instruct-2507 | 262 144 | «multiple languages» (familia Qwen3: 100+) | tool calling (Qwen-Agent), sin `<think>` | `cdbee75f17c01a7cc42f958dc650907174af0554` |
| Qwen3-4B-Thinking-2507 | 262 144 | ídem | tool calling; solo modo razonamiento | `768f209d9ea81521153ed38c47d515654e938aea` |
| Qwen3-4B / -GGUF | 32 768 (131K con YaRN) | 100+ idiomas | tools; `/think` y `/no_think` | `1cfa9a7208912126459214e8b04321603b3df60c` / `bc640142c66e1fdd12af0bd68f40445458f3869b` |
| Qwen3-1.7B / -GGUF | 32 768 | 100+ | tools, razonamiento conmutable | `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e` / `90862c4b9d2787eaed51d12237eafdfe7c5f6077` |
| Qwen3.5-4B / 2B / 0.8B | 262 144 | 201 idiomas | tools; **razonamiento activado por defecto** (`enable_thinking=False` lo apaga); multimodal | `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a` / `15852e8c16360a2fea060d615a32b45270f8a8fc` / `2fc06364715b967f1860aea9cf38778875588b17` |
| Qwen2.5-3B-Instruct / 1.5B | 32K | sí | tools | `aa8e72537993ba99e69dfaafa59ed015b17504d1` / `989aa7980e4cf806f80c7fef2b1adb7bc71aa306` |
| Gemma 3 4B / 1B | 128K / 32K | 140+ idiomas | — | `093f9f388b31de276ce2de164bdc2081324b9767` / `dcc83ea841ab6100d6b47a070329e1ba4cf78752` |
| Gemma 3n E2B / E4B | 32K | sí | — | `5e092ebca197cdcd8d8b195040accf22693501bc` / `c1221e9c62e34a43ab7ffacd1be0ea71f126ef10` |
| Gemma 4 E2B / E4B | 128K | 35+ listos de serie (140+ en preentrenamiento) | function calling nativo; razonamiento opcional; audio | `3e22461f65e89153144f8adb70e3b8c2cc9845a7` / `ee0ef6023621cff504d758262d4e04895a5af4a2` |
| Llama 3.2 3B / 1B | 128K | sí (8 idiomas oficiales) | tools | `0cb88a4f764b7a12671c53f0838cd831a0843b95` / `9213176726f574b556790deb65791e0c5aa438b6` |
| Phi-4-mini-instruct | 128K | sí (23 idiomas) | function calling (`<\|tool\|>`) | `cfbefacb99257ffa30c83adab238a50856ac3083` |
| Phi-4-mini-reasoning / flash | 128K | no (solo inglés) | — | `0e3b1e2d02ee478a3743abe3f629e9c0cb722e0a` / `1dff8163d28ec880ca2411c474ddc0a927792810` |
| Ministral-3-3B-Instruct-2512 / GGUF | 256K | sí | «native function calling and JSON outputting» | `b35d4dfe56c142746f54dbd64f579faab2744308` / `eb599d408350ea2bb60452cb86be7c7b2fc28227` |
| DeepSeek-R1-Distill-Qwen-1.5B | 128K (según Ollama) | no declarado | — | `ad9f0ae0864d7fbcd1cd905e3c6c5b069cc8b562` |
| Granite-4.1-3B / GGUF | 128K | sí (12 idiomas) | tools (`<tool_call>` JSON) | `c0650403e44e78ec0262dab1c90914c65b196c4e` / `ab4701481089b58a082ef63cc1cee738887293ff` |
| Granite-4.2-3B / GGUF | 128K (512K ampliado) | sí (12 idiomas probados) | tools; razonamiento completo, desactivado o de bajo esfuerzo | `4e9c275e232f10211ec88644d106a1f6a1b60e06` / `c40945d71cd90f249a56985e8155551a9188dc30` |
| Granite-4.0-micro / h-micro (GGUF) | 128K / 1M | sí | tools | `56111ae135df9c53a78c99028e7bc24035a9e979` / `d5f01a3ea75f088947be3aae039f4ad52837dfde` (GGUF `ec48475f…`, `dc1dd258…`) |
| SmolLM3-3B / ggml-org GGUF | 64K (128K con YaRN) | sí (6 idiomas) | tools (`xml_tools`); razonamiento por defecto | `a07cc9a04f16550a088caea529712d1d335b0ac1` / `4965cb60b150737b68a0408c36aeefb65078f894` |
| LFM2.5-2.6B / GGUF | 131 072 | sí (16 idiomas) | tools | `b212e75975bbda9676a94d3cb7b2ca25b65fed48` / `e7caca5d835a3901a8e0d63e94009429bafafdfc` |

Ollama admite salida restringida a un esquema JSON con el parámetro `format` ([blog del 6-12-2024](https://ollama.com/blog/structured-outputs)). Es una función del runtime, no del modelo, y el blog no dice que funcione igual con todos los modelos. Sigue haciendo falta validar el JSON en EIM.

---

### 3. Resumen embeddings

| Modelo | Tamaño | Licencia | Multilingüe | Dim. | Contexto | Formatos | `trust_remote_code` | Ollama (digest, tamaño) | SHA HF | Veredicto |
|---|---|---|---|---|---|---|---|---|---|---|
| [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) | 596M | Apache-2.0 | sí (100+) | 1024 (MRL 32–1024) | 32K | safetensors; **GGUF oficial** Q8_0 0,64 GB | no | `qwen3-embedding:0.6b` `ac6da0dfba84` 639 MB Q8 | `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` (GGUF `370f27d7550e0def9b39c1f16d3fbaa13aa67728`) | **Usar** (candidato T71) |
| [multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small) | 118M | MIT | sí (≈ 94) | 384 | 512 | safetensors; **ONNX oficial** (fp32 0,47 / O4 0,24 / qint8 0,12 GB); además `.bin` | no | no | `614241f622f53c4eeff9890bdc4f31cfecc418b3` | **Usar** (candidato T71, el más ligero) |
| [granite-embedding-97m-multilingual-r2](https://huggingface.co/ibm-granite/granite-embedding-97m-multilingual-r2) (2026-04) | 97M | Apache-2.0 | sí (52 con soporte reforzado, incl. es) | 384 | 32 768 | safetensors 0,20 GB; ONNX oficial (+ quint8 0,10 GB) | no (ModernBERT nativo) | no | `835ad14087e140460703cf0fae09f97d469d65c2` | **Usar** (candidato T71 ligero) |
| [bge-m3](https://huggingface.co/BAAI/bge-m3) | 568M | MIT | sí (100+) | 1024 (denso, disperso y ColBERT) | 8192 | **solo `.bin` pickle** + ONNX fp32 2,27 GB | no | `bge-m3:567m` `790764642607` 1,2 GB F16 | `5617a9f61b028005a4858fdac845db406aefb181` | Usar (opcional, **solo vía Ollama/GGUF**) |
| [embeddinggemma-2](https://huggingface.co/google/embeddinggemma-2) (2026-09) | 740M total (≈ 270M texto) | Apache-2.0 | sí (100+) | 768 (MRL 128–512) | 8K (declarado) | safetensors; ggml-org GGUF texto Q8_0 0,31 GB (+ mmproj) | no (requiere transformers reciente) | `embeddinggemma-2:270m-q8_0-text` `c21dd30c1e38` 304 MB | `f9972ac22e696a105c482202646979e33e4b5a1e` (GGUF `58faf909…`) | Usar (opcional; muy reciente) |
| [multilingual-e5-base](https://huggingface.co/intfloat/multilingual-e5-base) | 278M | MIT | sí | 768 | 512 | safetensors; ONNX (qint8 0,28 GB) | no | no | `d128750597153bb5987e10b1c3493a34e5a4502a` | Referencia |
| [multilingual-e5-large-instruct](https://huggingface.co/intfloat/multilingual-e5-large-instruct) | 560M | MIT | sí | 1024 | 512 | safetensors | no | no | `274baa43b0e13e37fafa6428dbc7938e62e5c439` | Referencia |
| [granite-embedding-311m-multilingual-r2](https://huggingface.co/ibm-granite/granite-embedding-311m-multilingual-r2) | 311M | Apache-2.0 | sí | 768 (MRL) | 32 768 | safetensors; ONNX (+ quint8 0,31 GB) | no | no | `44399559930365213510b1ee2eb15ded83374f0e` | Referencia (opcional) |
| [granite-embedding-278m / 107m-multilingual](https://huggingface.co/ibm-granite/granite-embedding-278m-multilingual) (R1) | 278M / 107M | Apache-2.0 | sí (12 idiomas) | 768 / 384 | 512 | safetensors, ONNX, `.bin` | no | `granite-embedding:278m` `1a37926bf842` 563 MB | `a9cb5338491faf32b73dd17b714a31821c021bbf` / `d6cffd338414d6a1c1f5decfad5fec62eebc90d5` | Referencia (superado por R2) |
| [nomic-embed-text-v2-moe](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe) | 475M (305M activos) | Apache-2.0 | sí (≈ 100) | 768 (MRL hasta 256) | **512** | safetensors; GGUF oficial | **sí** | `nomic-embed-text-v2-moe` `ff9c2f10ef5e` 958 MB | `1066b6599d099fbb93dfcb64f9c37a7c9e503e85` | Referencia |
| [snowflake-arctic-embed-l-v2.0](https://huggingface.co/Snowflake/snowflake-arctic-embed-l-v2.0) | 568M | Apache-2.0 | sí | 1024 (MRL) | 8192 | safetensors; ONNX | no | `snowflake-arctic-embed2:568m` `5de93a84837d` 1,2 GB | `ac6544c8a46e00af67e330e85a9028c66b8cfd9a` | Referencia |
| [snowflake-arctic-embed-m-v2.0](https://huggingface.co/Snowflake/snowflake-arctic-embed-m-v2.0) | 305M | Apache-2.0 | sí | 768 (MRL) | 8192 | safetensors; ONNX | **sí** (GTE) | no | `95c2741480856aa9666782eb4afe11959938017f` | Referencia |
| [embeddinggemma-300m](https://huggingface.co/google/embeddinggemma-300m) | 303M | **Gemma ToU** | sí | 768 (MRL) | 2K | safetensors; ggml-org GGUF | no | `embeddinggemma:300m` `85462619ee72` 622 MB (QAT q4_0 `101341d65c2c` 239 MB) | `57c266a740f537b4dc058e1b0cda161fd15afa75` | Descartar (ToU + gated; tiene sucesor Apache) |
| [nomic-embed-text-v1.5](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5) | 137M | Apache-2.0 | **no** (inglés) | 768 (MRL) | 2048 (8192 con RoPE) | safetensors; ONNX; GGUF oficial | **sí** (hasta transformers 5.5) | `nomic-embed-text:v1.5` `0a109f422b47` 274 MB | `e9b6763023c676ca8431644204f50c2b100d9aab` | Descartar (solo inglés) |
| [jina-embeddings-v5-text-nano / small](https://huggingface.co/jinaai/jina-embeddings-v5-text-nano) | 212M / 596M | **CC-BY-NC-4.0** | — | — | 8K | safetensors; GGUF | **sí** | no | `8a7f00aac812071b69403df470f1038ec85f8925` / `dd76d535f5447ca3897a9c893fb1e612ead98192` | Descartar |
| [LFM2.5-Embedding-350M](https://huggingface.co/LiquidAI/LFM2.5-Embedding-350M) | 354M | **LFM Open v1.0** | sí (11 idiomas, incl. es) | 1024 | 512 | safetensors; GGUF oficial | **sí** | no | `f35ae2c91d687658dbf1f2b449382f0b019b9808` | Referencia |

Ninguno se adopta si no supera a BM25 en la prueba de T71. Para esa prueba, el trío ligero propuesto es multilingual-e5-small, granite-embedding-97m-r2 y Qwen3-Embedding-0.6B.

---

### 4. Detalle (solo lo no obvio)

- **Huella en el MÍNIMO (estimación propia, no declarada).** Qwen3-4B tiene 36 capas, 8 cabezas KV y head_dim 128. Con caché KV en f16 son ≈ 0,15 MB por token: ≈ 0,6 GB con 4K de contexto y ≈ 1,2 GB con 8K. Sumado al Q4_K_M de 2,5 GB, el total ronda 3,1–3,7 GB más el runtime. Cabe en 5 GB. Gemma 4 E2B en Ollama ocupa 4,3–4,6 GB **antes** de la caché, así que queda al límite. El GGUF de ggml-org en Q4_0 (2,84 GB), sin mmproj y solo para texto, deja más margen.
- **Qwen3.5 (feb-2026)** sucede a Qwen3 en tamaños pequeños, con 0.8B, 2B y 4B en Apache-2.0. Son modelos multimodales (`image-text-to-text`) y el README recomienda ≥ 128K de contexto para preservar el razonamiento. En un equipo de 5 GB eso no se puede, así que hay que usarlos con `enable_thinking=False`. Las generaciones posteriores (Qwen3.6, abril de 2026, y Qwen3.8, agosto de 2026) solo publican 27B o más; no hay versiones de ≤ 4B.
- **Qwen3-4B-Instruct-2507 frente a Qwen3.5-4B.** El 2507 es solo texto y no razona, ocupa 2,5 GB y en Ollama sale de la build de la biblioteca. El 3.5 es más nuevo pero lleva un proyector de visión de 0,68 GB. Ambos son Apache. Se propone medir los dos con el mismo juego de transcripciones antes de fijar uno.
- **Gemma 4 (abril de 2026) cambió la licencia a Apache-2.0**, el principal cambio de licencias de 2026 en este grupo. Su modelo «E2B» tiene 5,1B parámetros reales por los Per-Layer Embeddings, así que solo cumple «≤ 4B» si se cuentan los parámetros efectivos.
- **Granite.** IBM publica GGUF oficiales de 4.0, 4.1 y 4.2 en Q2_K a BF16. La serie 4.2 (agosto de 2026) añade razonamiento conmutable y la 4.1 no razona; la 4.1 es la más directa para extraer JSON. `granite-switch-4.1` es de 8B o más.
- **Ministral 3 3B** es el único candidato que declara explícitamente «JSON outputting», y tiene GGUF oficial del autor. Los pesos del repo HF principal están en FP8 (para GPU H200/vLLM), así que en CPU hay que usar el GGUF.
- **Phi-4-mini**: las etiquetas `q8_0` y `fp16` de Ollama muestran solo 4K de contexto, mientras que `q4_K_M` muestra 128K. No se verificó la causa.
- **DeepSeek-R1-Distill-1.5B** es MIT, con base Qwen2.5-Math, que es Apache. Sirve para razonamiento matemático y no declara idiomas ni herramientas.
- **bge-m3**: si alguna vez se usa con sentence-transformers, `torch.load` del `.bin` deserializa pickle, así que es mejor el GGUF de Ollama o el ONNX. La variante dispersa/ColBERT necesita la librería FlagEmbedding, que es código de terceros.
- **Prefijos obligatorios** declarados: e5 (`query: ` / `passage: `), nomic (`search_query: ` / `search_document: `), Qwen3-Embedding (instrucción en la consulta, entre 1 y 5 % de mejora declarada) y EmbeddingGemma (prefijos de tarea). T71 debe aplicarlos o la comparación con BM25 será injusta.

---

### 5. Consultas

Fecha de todas: 2026-10-30, salvo las marcadas como (31).

- API HF, búsquedas por autor: `https://huggingface.co/api/models?author=<org>&search=<q>&sort=createdAt&direction=-1` para Qwen, google, mistralai, ibm-granite, HuggingFaceTB, microsoft, meta-llama, ggml-org, nomic-ai, Snowflake, deepseek-ai, LiquidAI, BAAI, intfloat y jinaai.
- API HF por repo: `https://huggingface.co/api/models/<repo>?blobs=true` (de ahí salen sha, `cardData.license`, gated, siblings con tamaños, `config.auto_map`, `safetensors.total` y `gguf`). Repos consultados: todos los enlazados en las tablas 2 y 3, más los repos `-GGUF` citados de Qwen, google, ggml-org, mistralai, ibm-granite, nomic-ai y LiquidAI, y la existencia de los de terceros: unsloth/Qwen3.5-4B-GGUF, bartowski/Qwen_Qwen3.5-4B-GGUF, unsloth/Qwen3-4B-Instruct-2507-GGUF, lmstudio-community/Qwen3-4B-Instruct-2507-GGUF, unsloth/Phi-4-mini-instruct-GGUF, bartowski/microsoft_Phi-4-mini-instruct-GGUF, bartowski/Llama-3.2-3B-Instruct-GGUF, hugging-quants/Llama-3.2-3B-Instruct-Q4_K_M-GGUF, unsloth/DeepSeek-R1-Distill-Qwen-1.5B-GGUF, unsloth/SmolLM3-3B-GGUF y unsloth/gemma-3n-E2B-it-GGUF. También se comprobó la inexistencia de Qwen/Qwen3-4B-Instruct-2507-GGUF, Qwen/Qwen3.5-4B-GGUF y microsoft/Phi-4-mini-instruct-gguf.
- README en crudo: `https://huggingface.co/<repo>/raw/main/README.md` para 30 repos. Los de gemma-3, gemma-3n, Llama-3.2 y embeddinggemma-300m devolvieron 401 (gated).
- Licencias:
  - https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/raw/main/LICENSE
  - https://huggingface.co/LiquidAI/LFM2.5-2.6B/raw/main/LICENSE
  - https://raw.githubusercontent.com/meta-llama/llama-models/main/models/llama3_2/LICENSE
  - https://raw.githubusercontent.com/meta-llama/llama-models/main/models/llama3_2/USE_POLICY.md
  - https://ai.google.dev/gemma/terms
  - https://ai.google.dev/gemma/docs/gemma_4_license
  - https://ai.google.dev/gemma/prohibited_use_policy (31)
  - https://mistral.ai/licenses/MRL-0.1.md (citada en la `cardData`; no se abrió)
- Ollama, tags: `https://ollama.com/library/<m>/tags` para qwen3, qwen3.5, qwen2.5, gemma3, gemma3n, gemma4, llama3.2, phi4-mini, ministral-3, deepseek-r1, granite4, granite4.1, granite4.2, granite3.3, lfm2.5, lfm2.5-thinking, bge-m3, nomic-embed-text, nomic-embed-text-v2-moe, snowflake-arctic-embed2, granite-embedding, qwen3-embedding, embeddinggemma y embeddinggemma-2. `smollm3`, `multilingual-e5` y `jina-embeddings-v5` dieron 404.
- Ollama, página de cada modelo (capas, licencia, parámetros, cuantización): `https://ollama.com/library/<m>:<tag>` para cada etiqueta citada en las tablas. Búsqueda: `https://ollama.com/search?q=embedding`.
- https://ollama.com/blog/structured-outputs (31)
- WebSearch: lanzamientos de Qwen3.5 small, Gemma 4, Ministral 3, Granite 4.x y Phi en 2026 (sin Phi-5 a la fecha).

## Grupo E — Marcos de agentes (auditoría de solo lectura)

Fecha de consulta: 2026-10-30/31. No se instaló ni ejecutó código de terceros. Evidencia por `gh api`, PyPI JSON y `git grep` sobre clones superficiales en `t62_clones/` (SHA de `main` citados abajo).

Contexto: EIM ya tiene coordinador determinista (`Agent.run(MarketSnapshot) -> AgentReport`, runner con timeout, síntesis y riesgo con veto). Lo único que podría aportar un marco es la **salida estructurada validada** de un LLM local (Ollama / llama.cpp en 127.0.0.1).

### 1. Alertas

1. **CrewAI envía telemetría por defecto** a `https://telemetry.crewai.com:4319/v1/traces` (OTLP), sin que el usuario la active ([constants.py:9](https://github.com/crewAIInc/crewAI/blob/97bbfb64811775a965304bda45c8ec0e8e4ef3a2/lib/crewai/src/crewai/telemetry/constants.py#L9), [telemetry.py:117-118](https://github.com/crewAIInc/crewAI/blob/97bbfb64811775a965304bda45c8ec0e8e4ef3a2/lib/crewai/src/crewai/telemetry/telemetry.py#L117-L118)). El singleton se crea al importar (`event_listener = EventListener()` en [event_listener.py:1077](https://github.com/crewAIInc/crewAI/blob/97bbfb64811775a965304bda45c8ec0e8e4ef3a2/lib/crewai/src/crewai/events/event_listener.py#L1077)). Incluso sin `share_crew` envía la versión, la versión de Python, `crew_id`/`crew_key`, nº de agentes y tareas, nombres de herramientas, **nombre del modelo LLM** ([telemetry.py:654-657](https://github.com/crewAIInc/crewAI/blob/97bbfb64811775a965304bda45c8ec0e8e4ef3a2/lib/crewai/src/crewai/telemetry/telemetry.py#L654-L657)), `coding_agent`, `runtime_context`, `cpu_band` y `project_id` ([crewai_core/telemetry.py:238-260](https://github.com/crewAIInc/crewAI/blob/97bbfb64811775a965304bda45c8ec0e8e4ef3a2/lib/crewai-core/src/crewai_core/telemetry.py#L238-L260)). Se apaga con `OTEL_SDK_DISABLED=true`, `CREWAI_DISABLE_TELEMETRY=true` o `CREWAI_DISABLE_TRACKING=true` ([crewai_core/telemetry.py:356-358](https://github.com/crewAIInc/crewAI/blob/97bbfb64811775a965304bda45c8ec0e8e4ef3a2/lib/crewai-core/src/crewai_core/telemetry.py#L356-L358)).
2. **CrewAI arrastra unos 139 paquetes, 27 de ellos nativos** (chromadb, onnxruntime, lancedb, pyarrow, grpcio, numpy, kubernetes, pywin32, `uv`, textual…) y fija `pydantic<2.13`. Eso choca con el principio de mínimo de EIM.
3. **litellm** sufrió un compromiso de cadena de suministro: las versiones 1.82.7 y 1.82.8 publicadas en PyPI el 2026-03-24 (atribuidas a TeamPCP, tras el compromiso de Trivy y KICS) contenían un ladrón de credenciales; la 1.82.8 lo cargaba con un `.pth` que se ejecuta al arrancar Python. Ese mismo incidente afectó a dependientes como CrewAI y DSPy. Además, desde abril de 2026 hay **≥ 6 GHSA críticos** en el proxy (p. ej. CVE-2026-42208 SQLi, CVE-2026-49468 bypass de autenticación, GHSA-w4c7-34wj-hqm8 del 2026-10-27). Hoy solo entra como *extra* en crewai (`litellm==1.100.4`) e instructor (`litellm<=1.83.7`); **ningún candidato recomendado lo instala por defecto**. Si alguna vez aparece, debe ser `>=1.83.0`.
4. **AutoGen está archivado y sin mantenimiento**: el README dice que no recibirá correcciones de seguridad y remite a Microsoft Agent Framework (commits del 2026-10-16 y del 2026-10-28). La última release es `python-v0.7.5`, del 2025-09-30. Ojo: en GitHub el flag `archived` todavía es `false`.
5. **Microsoft Agent Framework añade por defecto la cabecera `User-Agent: agent-framework-python/<ver>`** a las llamadas a proveedores ([_telemetry.py:19-33](https://github.com/microsoft/agent-framework/blob/b7884ad88eb85c27b2a7bf40c0e15948e7ccc28d/python/packages/core/agent_framework/_telemetry.py#L19-L33)); se quita con `AGENT_FRAMEWORK_USER_AGENT_DISABLED=true`. La instrumentación OTel también viene activada por defecto ([observability.py:1066,1109](https://github.com/microsoft/agent-framework/blob/b7884ad88eb85c27b2a7bf40c0e15948e7ccc28d/python/packages/core/agent_framework/observability.py#L1109)), pero solo instala `opentelemetry-api`, así que sin SDK no exporta nada. El conector `agent-framework-ollama` sigue en beta (`1.0.0b261030`) y fija `ollama<0.5.4`.
6. **pydantic-ai ya va por la 2.x** (la 2.0.0 salió el 2026-06-23; la 1.x solo recibe parches, la última es 1.107.9 del 2026-10-21). La cadencia es muy alta: de 2.59 a 2.64 en 9 días. Hay que fijar la versión exacta y revisar cada subida. Acumula 20 GHSA en 2026, casi todos en piezas que EIM no usaría (`web_fetch`, UI/AG-UI, `Agent.to_web()`, redacción de OTel).
7. **El paquete `pydantic-ai` completo instala `logfire` y unos 10 SDK de proveedores**. Solo es aceptable `pydantic-ai-slim[openai]`. El wheel de slim incluye además `.agents/skills/*.md`, que piden a los agentes de código configurar Logfire «por defecto» ([SKILL.md:483](https://github.com/pydantic/pydantic-ai/blob/d56fa5561f512a7f25fe27170782f7beb8521bc6/pydantic_ai_slim/pydantic_ai/.agents/skills/building-pydantic-ai-agents/SKILL.md)). En EIM eso se trata como dato, no como instrucción: no se instala `logfire`.
8. **El SDK `openai>=3` usa `httpx2`**, un fork de httpx mantenido por pydantic (BSD-3, [pydantic/httpx2](https://github.com/pydantic/httpx2)). Es una dependencia nueva en la cadena de suministro de pydantic-ai, instructor y langsmith.
9. **LangGraph tiene un historial de deserialización insegura en checkpoints**: `pickle` opcional e `importlib.import_module` desde datos serializados ([jsonplus.py:309-310, 674-725](https://github.com/langchain-ai/langgraph/blob/e5c961d7fbe7ca6fdd4c94c84d90511372514d55/libs/checkpoint/langgraph/checkpoint/serde/jsonplus.py#L309)), con varios CVE (CVE-2025-64439 RCE, CVE-2026-28277, CVE-2026-48775). Además arrastra `langsmith`, `langgraph-sdk` y `websockets` aunque no se usen.

### 2. Tabla resumen

| Candidato | Veredicto | Licencia | Telemetría por defecto | Versión a fijar (tag · SHA) |
|---|---|---|---|---|
| pydantic-ai (`pydantic-ai-slim[openai]`) | **Usar (opcional)**, solo para salida estructurada | MIT | No (instrumentación desactivada; solo un aviso local por stderr) | `v2.64.0` · `cde1d10f88ce6d0ab4743e226d51a9ac65810f50` |
| instructor | Referencia (alternativa válida a pydantic-ai) | MIT | No (grep sin hallazgos) | `v1.17.0` · `f539bf2bf43ef4d1cb4e2a405751d6a8815ce05f` |
| outlines | Referencia | Apache-2.0 | No | `1.3.3` · `3d251f8d758a01cfee4ddc99646886845dbd8c6d` |
| langgraph | Descartar | MIT | No (LangSmith es opt-in con `LANGSMITH_TRACING=true`) | `1.2.19` · `5bd231cbfd913e05ebc662f519eb9a655bc766df` (si se usara) |
| microsoft/agent-framework | Descartar (Referencia de diseño) | MIT | Sí: cabecera User-Agent; OTel sin exportador | `python-1.24.0` · `43d767c55050480e470ebf0a89caa4141d325ebf` |
| crewAI | **Descartar** | MIT | **Sí: OTLP a telemetry.crewai.com** | `1.15.33` · `1551ceb5d4cf557c26da6c971fb845118ec0cb26` (no recomendado) |
| microsoft/autogen | **Descartar** (archivado) | Código MIT / docs CC-BY-4.0 | No (solo `opentelemetry-api`) | `python-v0.7.5` · `83afbf5857aac683340d4c692194e548b1e8edda` (no usar) |
| litellm (dependencia indirecta) | **Descartar** | MIT; `enterprise/` con licencia propia | Callbacks opt-in; el riesgo real es la cadena de suministro | — (si aparece transitivamente: `>=1.83.0`) |

Alternativa de referencia (base de comparación): **escribirlo a mano**, unas 100 líneas con `httpx` o `ollama==0.6.3` (12 paquetes, 1 nativo: pydantic-core) más pydantic v2 y el `format` con JSON Schema de Ollama (o una gramática/`json_schema` de llama.cpp), con un bucle «validar → reinyectar el error → reintentar N veces». Para EIM es igual de capaz y no añade superficie de ataque.

### 3. Detalle por candidato

Recuento de dependencias: es aproximado. Se calculó con un script propio que resuelve `requires_dist` de PyPI JSON (última versión compatible, CPython 3.12, win_amd64, el paquete raíz incluido) sin descargar ninguna distribución. Todos los nativos tienen wheel win_amd64: no hace falta compilar.

#### 3.1 pydantic/pydantic-ai, propuesta: **Usar (opcional)**
- **URL**: https://github.com/pydantic/pydantic-ai · docs https://ai.pydantic.dev · **Licencia**: [MIT](https://github.com/pydantic/pydantic-ai/blob/main/LICENSE).
- **Mantenimiento**: 20 964★, 1 710 issues+PR abiertos. Último commit el 2026-10-31 (`d56fa556`). Release `v2.64.0` del 2026-10-30. Rama 1.x en `v1.107.9` (2026-10-21).
- **Pruebas**: 60 workflows en `.github/workflows` y unos 1 100 ficheros de test.
- **Instalación (Py 3.12, Windows)**: `pydantic-ai-slim[openai]==2.64.0` suma **unos 26 paquetes, 4 nativos** (pydantic-core, jiter, regex, tiktoken). Requiere Python ≥ 3.11. El núcleo del slim: anyio, genai-prices, griffelib, httpx2, opentelemetry-api, pydantic-graph, pydantic, typing-inspection; el extra `openai` añade `openai>=3.31` y tiktoken.
- **Red y telemetría**:
  - La instrumentación está desactivada por defecto: `_instrument_default = False` ([agent/__init__.py:585](https://github.com/pydantic/pydantic-ai/blob/d56fa5561f512a7f25fe27170782f7beb8521bc6/pydantic_ai_slim/pydantic_ai/agent/__init__.py#L585)). Solo trae `opentelemetry-api` y no hay exportador.
  - Los precios salen de un snapshot empaquetado ([usage.py:11](https://github.com/pydantic/pydantic-ai/blob/d56fa5561f512a7f25fe27170782f7beb8521bc6/pydantic_ai_slim/pydantic_ai/usage.py#L11); `genai_prices/data_snapshot.py` usa `from_auto_update=False`). La descarga de precios solo ocurre si se llama a `prices.update_in_background()` ([prices.py:10-25](https://github.com/pydantic/pydantic-ai/blob/d56fa5561f512a7f25fe27170782f7beb8521bc6/pydantic_ai_slim/pydantic_ai/prices.py#L10)).
  - En la primera ejecución muestra un aviso **local** por stderr, sin red; se apaga con `PYDANTIC_AI_NO_BANNER=1` o `pydantic_ai.BANNER_ENABLED=False` ([__init__.py:513](https://github.com/pydantic/pydantic-ai/blob/d56fa5561f512a7f25fe27170782f7beb8521bc6/pydantic_ai_slim/pydantic_ai/__init__.py#L513), [_display.py:292](https://github.com/pydantic/pydantic-ai/blob/d56fa5561f512a7f25fe27170782f7beb8521bc6/pydantic_ai_slim/pydantic_ai/_display.py#L292)).
  - tiktoken puede descargar codificaciones, pero solo en embeddings, realtime o `count_tokens`; no en el camino de chat.
  - No se encontró red al importar.
- **exec/eval**: no hay `exec`/`eval`/`pickle` en el paquete; `subprocess` solo aparece en workspaces/capabilities, que EIM no usaría.
- **Seguridad**: 20 GHSA en el repositorio (2026-02 a 2026-10): SSRF, `web_fetch`, UI web, adaptadores de UI y redacción de OTel. Ninguno toca el camino «Agent + OllamaModel + output_type» sin herramientas. Fuente: [advisories](https://github.com/pydantic/pydantic-ai/security/advisories).
- **Qué aporta frente a EIM**: **salida estructurada**:
  - `Agent(model, output_type=MiModelo)` con `NativeOutput` (JSON Schema nativo), `ToolOutput` o `PromptedOutput` ([output.py:104-238](https://github.com/pydantic/pydantic-ai/blob/d56fa5561f512a7f25fe27170782f7beb8521bc6/pydantic_ai_slim/pydantic_ai/output.py#L104)).
  - Reintentos de validación con el error reinyectado (`output_retries`, `ModelRetry`).
  - El resto del marco (grafos, herramientas, MCP, UI) **no** se debe usar.
- **Integración con Ollama local**:
  - `OllamaModel` + `OllamaProvider(base_url='http://127.0.0.1:11434/v1')`. Si no hay clave usa el marcador `'api-key-not-set'` ([providers/ollama.py:104-113](https://github.com/pydantic/pydantic-ai/blob/d56fa5561f512a7f25fe27170782f7beb8521bc6/pydantic_ai_slim/pydantic_ai/providers/ollama.py#L104-L113)).
  - Para Ollama autoalojado ≥ 0.5 envía `response_format` con `json_schema` ([models/ollama.py:47-59](https://github.com/pydantic/pydantic-ai/blob/d56fa5561f512a7f25fe27170782f7beb8521bc6/pydantic_ai_slim/pydantic_ai/models/ollama.py#L47)).
  - llama.cpp `llama-server` funciona vía `OpenAIChatModel` con un proveedor OpenAI-compatible.
- **Versión a fijar**: `pydantic-ai-slim[openai]==2.64.0` (tag `v2.64.0` · `cde1d10f88ce6d0ab4743e226d51a9ac65810f50`), con hashes en el lock.
- **Veredicto**: *Usar (opcional)*. Es la opción más limpia si no se quiere escribir el bucle a mano, siempre detrás de la interfaz de EIM, con `PYDANTIC_AI_NO_BANNER=1`, sin `logfire` y sin herramientas. Si se prefiere cero dependencias nuevas, la versión manual es igual de válida.

#### 3.2 567-labs/instructor, propuesta: Referencia
- **URL**: https://github.com/567-labs/instructor · **Licencia**: [MIT](https://github.com/567-labs/instructor/blob/main/LICENSE).
- **Mantenimiento**: 14 081★, 229 abiertos. Último commit el 2026-10-20. Release `v1.17.0` del 2026-09-09. CI con 11 workflows y unos 256 ficheros de test.
- **Instalación**: **unos 41 paquetes, 4 nativos**. Arrastra aiohttp, rich, typer, jinja2, tenacity, requests y `openai<4` (que trae httpx2).
- **Red y telemetría**: el grep de telemetry/posthog/sentry/urlopen no dio hallazgos. No hay `exec`/`eval`/`pickle`/`subprocess`.
- **Seguridad**: 0 GHSA en el repositorio y en la base global (pip).
- **Qué aporta**: salida estructurada (`response_model=`, `max_retries` con reinyección del error de validación).
- **Integración**: `from_provider("ollama/<modelo>")` usa por defecto `http://localhost:11434/v1` y `api_key="ollama"` ([auto_client.py:1276-1278](https://github.com/567-labs/instructor/blob/6cd771c5254a69f6a6cf9cdf357fb2f9523f0b85/instructor/v2/auto_client.py#L1276-L1278)).
- **Versión**: `v1.17.0` · `f539bf2bf43ef4d1cb4e2a405751d6a8815ce05f`.
- **Veredicto**: *Referencia*. Hace lo mismo que pydantic-ai-slim con más dependencias (CLI, aiohttp) y un mantenimiento algo más lento; su extra `litellm<=1.83.7` no se debe usar.

#### 3.3 dottxt-ai/outlines, propuesta: Referencia
- **URL**: https://github.com/dottxt-ai/outlines · **Licencia**: [Apache-2.0](https://github.com/dottxt-ai/outlines/blob/main/LICENSE).
- **Mantenimiento**: 15 986★, 206 abiertos. Último commit el **2026-08-24**. Release `1.3.3` del 2026-08-06, más lento que el resto. CI con 6 workflows y unos 59 ficheros de test.
- **Instalación**: `outlines[ollama]` suma **unos 25 paquetes, 5 nativos** (outlines-core en Rust, pillow, rpds-py, markupsafe, pydantic-core). Requiere Python < 3.14.
- **Red y telemetría**: no se encontró.
- **Riesgo**: caché en disco con `diskcache` + `cloudpickle.loads` en `~/.cache/outlines` ([caching.py:23-38, 55-75](https://github.com/dottxt-ai/outlines/blob/c52af8472c6fe8a607a733ec11b709476af77a96/src/outlines/caching.py#L23)). Se crea de forma perezosa (`lru_cache`) y sirve para modelos locales; `OUTLINES_CACHE_DIR` permite moverla.
- **Seguridad**: 0 GHSA.
- **Qué aporta**: con Ollama solo pasa el JSON Schema a `format=` ([models/ollama.py:202](https://github.com/dottxt-ai/outlines/blob/c52af8472c6fe8a607a733ec11b709476af77a96/src/outlines/models/ollama.py#L202)), lo mismo que haría el código manual, y sin bucle de reintento. Su valor real (decodificación restringida con FSM) requiere transformers o llama-cpp-python en el mismo proceso.
- **Versión**: `1.3.3` · `3d251f8d758a01cfee4ddc99646886845dbd8c6d`.
- **Veredicto**: *Referencia*. Contra Ollama por HTTP no aporta nada sobre `format` + pydantic.

#### 3.4 langchain-ai/langgraph, propuesta: Descartar
- **URL**: https://github.com/langchain-ai/langgraph · **Licencia**: [MIT](https://github.com/langchain-ai/langgraph/blob/main/LICENSE).
- **Mantenimiento**: 44 189★, 514 abiertos. Último commit el 2026-10-31. Release `1.2.19` del 2026-10-30. CI con 17 workflows y unos 218 ficheros de test.
- **Instalación**: **unos 38 paquetes, 7 nativos** (orjson, ormsgpack, xxhash, zstandard, uuid-utils, pyyaml, pydantic-core). Arrastra `langchain-core 1.7.3`, `langsmith 0.14.16`, `langgraph-sdk` y websockets.
- **Telemetría**: LangSmith **no** traza por defecto. Solo lo hace si `LANGSMITH_TRACING`/`LANGCHAIN_TRACING_V2` vale `"true"` ([langsmith utils.py:141-142](https://github.com/langchain-ai/langsmith-sdk/blob/290f06a628dffb2ca690e389dc48b629f5623312/python/langsmith/utils.py#L141-L142)). No se encontró telemetría en `libs/langgraph`.
- **exec**: deserialización de checkpoints con `pickle` opcional e `import_module` dinámico (alerta 9).
- **Seguridad**: 14 GHSA en langgraph, 9 en langchain y 5 en langsmith-sdk (uno crítico: CVE-2026-59152).
- **Qué aporta**: **nada**. Es un orquestador de grafos de agentes que duplicaría el coordinador de EIM. Para salida estructurada necesitaría además `langchain-ollama`.
- **Versión**: `1.2.19` · `5bd231cbfd913e05ebc662f519eb9a655bc766df`.
- **Veredicto**: *Descartar*. Duplica la capa de orquestación y suma superficie (checkpoints, SDK de servidor).

#### 3.5 microsoft/agent-framework, propuesta: Descartar (Referencia de diseño)
- **URL**: https://github.com/microsoft/agent-framework · **Licencia**: [MIT](https://github.com/microsoft/agent-framework/blob/main/LICENSE).
- **Mantenimiento**: 14 392★, 849 abiertos. Releases `python-1.24.0` (2026-10-30) y `dotnet-1.27.0` (2026-10-30); API 1.x GA. CI con 32 workflows y unos 368 ficheros de test.
- **Instalación**: `agent-framework-core` suma **11 paquetes (4 nativos: msgspec, regex, pyyaml, pydantic-core)**; con `agent-framework-ollama` (beta) llega a **19**. El metapaquete `agent-framework` instala `core[all]`, unos 30 subpaquetes.
- **Telemetría**: cabecera User-Agent activada por defecto y OTel activado sin exportador; `enable_sensitive_data` es `False` por defecto ([observability.py:1110](https://github.com/microsoft/agent-framework/blob/b7884ad88eb85c27b2a7bf40c0e15948e7ccc28d/python/packages/core/agent_framework/observability.py#L1110)). Ver alerta 5.
- **Seguridad**: 8 GHSA en octubre de 2026 (workflows declarativos, MCP, hosting en Foundry, .NET).
- **Qué aporta**: orquestación multiagente y workflows, que **duplica** el coordinador de EIM. El cliente de Ollama traduce `response_format` a `format` ([_chat_client.py:241](https://github.com/microsoft/agent-framework/blob/b7884ad88eb85c27b2a7bf40c0e15948e7ccc28d/python/packages/ollama/agent_framework_ollama/_chat_client.py#L241)); host por defecto `http://localhost:11434`, sin clave.
- **Versión**: `python-1.24.0` · `43d767c55050480e470ebf0a89caa4141d325ebf`.
- **Veredicto**: *Descartar*. Es un marco empresarial (Azure/Foundry) y su conector de Ollama sigue en beta; como mucho sirve de referencia de diseño de middleware y OTel.

#### 3.6 crewAIInc/crewAI, propuesta: Descartar
- **URL**: https://github.com/crewAIInc/crewAI · **Licencia**: [MIT](https://github.com/crewAIInc/crewAI/blob/main/LICENSE) (en PyPI el campo de licencia está vacío).
- **Mantenimiento**: 60 318★, 959 abiertos. Release `1.15.33` del 2026-10-29. CI con 19 workflows y unos 505 ficheros de test.
- **Instalación**: unos **139 paquetes, 27 nativos**; además `crewai-cli` instala `uv` y `textual`.
- **Telemetría**: activada por defecto (alerta 1). Hay además «first-time traces»: se recogen en local y solo se suben a app.crewai.com si el usuario acepta en un prompt interactivo ([first_time_trace_handler.py:53-56](https://github.com/crewAIInc/crewAI/blob/97bbfb64811775a965304bda45c8ec0e8e4ef3a2/lib/crewai/src/crewai/events/listeners/tracing/first_time_trace_handler.py#L53)); se apaga con `CREWAI_TRACING_ENABLED=false`. `share_crew` vale `False` por defecto ([crew.py:300](https://github.com/crewAIInc/crewAI/blob/97bbfb64811775a965304bda45c8ec0e8e4ef3a2/lib/crewai/src/crewai/crew.py#L300)).
- **Seguridad**: 0 GHSA publicados (repositorio y base global). Fue afectado indirectamente por el compromiso de litellm de marzo de 2026.
- **Qué aporta**: nada; orquesta agentes LLM que se delegan tareas entre sí, justo lo contrario de «los LLM solo informan».
- **Versión**: `1.15.33` · `1551ceb5d4cf557c26da6c971fb845118ec0cb26`.
- **Veredicto**: *Descartar*. Telemetría por defecto, unos 139 paquetes y un modelo de autonomía incompatible con EIM.

#### 3.7 microsoft/autogen, propuesta: Descartar
- **URL**: https://github.com/microsoft/autogen · **Licencia**: código [MIT (LICENSE-CODE)](https://github.com/microsoft/autogen/blob/main/LICENSE-CODE), docs [CC-BY-4.0 (LICENSE)](https://github.com/microsoft/autogen/blob/main/LICENSE). Por eso GitHub muestra «CC-BY-4.0».
- **Estado**: README con «Project archived and no longer maintained… not providing… security fixes». Última release `python-v0.7.5` (2025-09-30). Último commit de código el 2026-03-26; los de 2026-10 son de documentación.
- **Instalación**: `autogen-agentchat` suma 11 paquetes (pillow y protobuf~=5.29). Haría falta además `autogen-ext[ollama]`.
- **Seguridad**: 0 GHSA, pero sin parches futuros.
- **Qué aporta**: nada; su sucesor es Agent Framework.
- **Versión**: `python-v0.7.5` · `83afbf5857aac683340d4c692194e548b1e8edda` (no usar).
- **Veredicto**: *Descartar*. Archivado y sin correcciones de seguridad.

#### 3.8 BerriAI/litellm (aparece como dependencia), propuesta: Descartar
- **URL**: https://github.com/BerriAI/litellm · **Licencia**: [MIT, salvo `enterprise/`](https://github.com/BerriAI/litellm/blob/main/LICENSE) (GitHub muestra NOASSERTION).
- **Estado**: 62 409★ y **5 579 abiertos**. Varias líneas de release en paralelo (1.104.x / 1.105.x / 1.106.6 del 2026-10-28, más dev/rc).
- **Instalación**: unos **59 paquetes, 11 nativos** (boto3, huggingface-hub, hf-xet, tokenizers, tiktoken…).
- **Seguridad**: compromiso de PyPI en marzo de 2026 (alerta 3) y 18 GHSA en el repositorio en 2026, 6 críticos (sobre todo en el proxy).
- **Veredicto**: *Descartar*. EIM habla con un único backend local; no necesita un enrutador multiproveedor.

### 4. Consultas (2026-10-30/31)

- Metadatos de repo: `gh api repos/<o>/<r>` (licencia, ★, issues, `pushed_at`, `archived`) para los 8 repositorios.
- Releases y último commit: `gh api repos/<o>/<r>/releases?per_page=8` · `gh api repos/<o>/<r>/commits?per_page=1`.
- Avisos: `gh api repos/<o>/<r>/security-advisories?per_page=50` (más langchain-ai/langchain y langsmith-sdk) · `gh api "advisories?ecosystem=pip&affects=<pkg>"`.
- SHA de tags: `git ls-remote --tags https://github.com/<o>/<r>.git refs/tags/<tag> refs/tags/<tag>^{}`.
- PyPI JSON: `https://pypi.org/pypi/<pkg>/json` para langgraph, langchain-core, langsmith, crewai, crewai-core, crewai-cli, pydantic-ai, pydantic-ai-slim, pydantic-graph, genai-prices, httpx2, griffelib, agent-framework, agent-framework-core, -ollama, -openai, autogen-agentchat, autogen-core, instructor, outlines, outlines-core, litellm, ollama, openai y langgraph-*. Guardados en `t62_audit/pypi_*.json`.
- Clausura de dependencias: script propio `t62_scripts_E/deps.py` (solo PyPI JSON, sin instalar), con salida en `t62_scripts_E/deps_out.txt`.
- Clones superficiales (`--depth 1 --filter=blob:limit=2m`, solo `git grep`/`git show`) en `t62_clones/`: pydantic-ai `d56fa556`, crewAI `97bbfb64`, langgraph `e5c961d7`, langsmith-sdk `290f06a6`, agent-framework `b7884ad8`, instructor `6cd771c5`, outlines `c52af847`.
- README de AutoGen: `gh api repos/microsoft/autogen/readme`. Licencias: `gh api repos/<o>/<r>/contents/LICENSE`.
- genai-prices: `gh api repos/pydantic/genai-prices/contents/packages/python/genai_prices/data_snapshot.py`.
- Incidente de litellm (búsqueda web): [docs.litellm.ai/blog/tags/security](https://docs.litellm.ai/blog/tags/security), [NetSPI](https://www.netspi.com/blog/executive-blog/ai-ml-pentesting/litellm-supply-chain-compromise/), [FutureSearch](https://futuresearch.ai/blog/litellm-pypi-supply-chain-attack/), [Rescana](https://www.rescana.com/post/litellm-supply-chain-attack-analysis-credential-stealer-and-backdoor-compromise-in-pypi-packages-march-2026).
