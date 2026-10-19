# Universo de motores locales y herramientas de video (insumo de T62, NO es una auditoría)
Fecha: 2026-10-19 · Fuente: investigación del usuario (GitHub, 46 s de búsqueda) + contraste con lo que ya hay en el repo + medición del equipo.
**Todo lo marcado «sin verificar» viene de la investigación del usuario o de memoria; T62 lo comprueba con el `LICENSE` real (del código y de los pesos), clones aislados y mediciones en este equipo. Ninguna cifra de velocidad o precisión se acepta de un README.** Nombres de modelos: pueden haber cambiado; T62 fija versión y SHA de los pesos.

## 1. Equipo de referencia (medido 2026-10-19, línea base del plan)
| Recurso | Valor | Consecuencia |
|---|---|---|
| CPU | Intel i5-8250U, 4 núcleos / 8 hilos, 1,6 GHz | Todo corre en CPU; los lotes se ponen en cola nocturna |
| RAM | 7,9 GB | **Un solo modelo cargado a la vez**; sin VLM de 7B; techo de proceso ≈ 5–6 GB |
| GPU | NVIDIA MX130 (2 GB) + Intel UHD 620 | Probablemente inservible para inferencia moderna (arquitectura antigua, 2 GB): **T62 lo mide, no se supone** |
| Disco | C: 6 GB libres · E: 378 GB · D: 196 GB | Modelos y datos en E: (`EIM_LOCALAI_DIR`), nunca en C: |
| Instalado | Python 3.12.10; **no** hay ollama, ffmpeg, yt-dlp, nvidia-smi | T62 define la instalación mínima y documentada |
Es el «Escenario A» de la investigación (equipo modesto). El plan se diseña para este mínimo; un equipo mejor solo cambia el modelo elegido, no la arquitectura (los motores son intercambiables, T63). **La RAM útil para modelos es menor que la total**: la API sola usa ≈ 1,8 GB (BACKLOG T49 (9)) y conviven el servicio de papel y el de líderes; T62 mide con los servicios en marcha. Otro equipo del proyecto parece tener 16 GB (mismo BACKLOG): el informe de T62 se corre en cada equipo y se compara; la lista aprobada se escribe para el mínimo.

## 2. Cadena y qué existe ya en el proyecto
| Eslabón | Candidatos (sin verificar) | Ya en el repo |
|---|---|---|
| Descubrimiento | YouTube Data API v3 (cuotas), feeds RSS de canal | — |
| Captación | `yt-dlp` (audio/metadatos), `youtube-transcript-api` (subtítulos) | Patrón de proceso aislado y sin claves: T57 |
| ASR | `faster-whisper` (CTranslate2, int8), `whisper.cpp`, `openai/whisper`; `WhisperX` (alineación + diarización; la diarización suele exigir pesos con aceptación de términos y token) | — |
| Escenas y fotogramas | `PySceneDetect` (BSD-3), `OpenCV` (Apache-2.0), `ffmpeg` | — |
| OCR | `PaddleOCR`, `RapidOCR` (ONNX, ligero), Tesseract | Tesseract ya se usa en la biblioteca (`eim/data/library_extract.py`, `EIM_TESSERACT`) |
| Visión-lenguaje (gráficos) | Familia Qwen-VL; alternativas pequeñas (SmolVLM, Florence-2, moondream…) | — |
| LLM de texto | Servidor local `Ollama` / `llama.cpp` con modelo ≤ 4B cuantizado (Qwen, Llama, Gemma, Phi…) | API de Claude en `agents/context` (T24) |
| Embeddings | Modelos multilingües pequeños (familias bge / e5, sin verificar) | Búsqueda BM25 propia (`eim/library/bm25.py`) |
| Orquestación y memoria | Cola con reintentos; PostgreSQL + pgvector; LlamaIndex / Haystack | **DuckDB** + Parquet (`eim/data/`), sin servidor |
| Referencias de flujo (no producción) | AI-Video-Transcriber, VidBee, YouTubeTLDR, SummaryYou, video-to-llm, whisper-timestamped, whisper-diarization | — |

## 3. Dónde este plan se aparta de la investigación (y por qué)
1. **PostgreSQL + pgvector → DuckDB + BM25 primero.** El proyecto es local y sin servidor (`CLAUDE.md`, T61 descarta bases compartidas); un servicio más rompe «un comando y corre» y la copia/mezcla de T61. Los embeddings entran solo si T71 demuestra que mejoran sobre BM25 en consultas etiquetadas.
2. **LlamaIndex / Haystack → no.** Sumar un marco para recuperar de una tabla propia agrega dependencias sin necesidad (T04: reciclar solo lo que ahorra trabajo real).
3. **WhisperX/diarización → opcional, decide T62.** Con 8 GB y CPU, el costo es alto y la identidad del hablante no se prueba con diarización (la propia investigación lo dice); se pide solo si la muestra muestra que entrevistas con varios hablantes son frecuentes.
4. **Un VLM «grande» como núcleo → no.** En este equipo el camino viable es OCR + visión clásica + un modelo visual pequeño solo en fotogramas elegidos; las cifras se validan contra el mercado, no contra el modelo.
5. **«Puntuación de credibilidad» única → no** (la investigación ya lo recomienda): dimensiones separadas y el peso en la síntesis lo decide la prueba marginal (T44), no un número decretado.

## 4. Riesgos a decidir con el usuario en T62 (◆)
- **Condiciones de YouTube.** Bajar audio con `yt-dlp` y usar la API no oficial de subtítulos puede infringir las condiciones del servicio y es frágil (cambios del sitio, bloqueos de IP). Postura propuesta: uso personal, local, sin redistribuir; **subtítulos y API oficial primero**, audio solo como respaldo y **borrado al terminar**; sin cookies ni cuenta del usuario; en git solo paráfrasis cortas con enlace y marca de tiempo (misma política de derechos que la biblioteca T52). El usuario aprueba o ajusta.
- **Licencia de pesos ≠ licencia de código.** Algunas variantes de modelos (según tamaño) usan licencias de investigación o comunitarias con restricciones; T62 registra la licencia de cada pesos antes de adoptarlo.
- **Contenido de terceros no confiable.** Transcripciones, títulos y texto en pantalla pueden traer instrucciones dirigidas al modelo: siempre datos, nunca órdenes (patrón T24). Descargas y decodificación de medios = superficie de ataque: proceso aislado, entorno limpio, versiones fijadas.
- **Datos que no viajan.** Las transcripciones completas son texto con derechos de terceros y reproducibles: no entran a git ni a la mezcla de T61; sí viajan las afirmaciones y los pronósticos derivados (con enlace).

## 5. Qué se espera de la evidencia (honestidad previa)
El proyecto ya midió que sus señales propias no superan el azar (T27, T44, T49). Para los analistas de YouTube la hipótesis nula es la misma: **no superan al azar**; la popularidad y la seguridad al hablar no son habilidad. El valor probable del módulo es (a) contexto y alertas de riesgo trazables, (b) un resultado medido, positivo o nulo, sobre quién acierta. Cada cifra expone su fuente y cobertura (`CLAUDE.md`).
