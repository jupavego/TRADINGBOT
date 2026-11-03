# Banco de motores locales (T62) — `juanpablo-cpu`

Última corrida 2026-10-31T14:53:13Z → 2026-10-31T14:53:28Z. Todo medido en este equipo con `scripts/localai_bench.py`; «—» = no medido. Memoria = pico de memoria privada de los procesos del motor; «RAM libre mín.» = la del sistema durante la etapa, con los servicios de abajo en marcha.

- Equipo `juanpablo-cpu`: Intel(R) Core(TM) i5-6400 CPU @ 2.70GHz, 4 hilos, RAM 16346 MB (libre al empezar 6697 MB; al terminar 6618 MB). Windows-10-10.0.19045-SP0, Python 3.12.10.
- GPU: NVIDIA GeForce GTX 750 Ti 2048 MB (cc 5.0, driver 582.78). ffmpeg: ffmpeg version 9.0.1-full_build-www.gyan.dev.
- Servicios en marcha al medir: eim.data.collectors (209 MB), ollama.exe (71 MB), eim.operation (14 MB), uvicorn eim.api (1731 MB), eim.leaders (919 MB).

## LLM de texto (Ollama 0.40.11)

| Modelo | Cuant. | Carga s | Prompt tok/s | Gen tok/s | Pico MB | RAM libre mín. MB | JSON válido | Precisión | Recall | Niveles inventados | s/caso |
|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen3:4b-instruct | Q4_K_M | 6.83 | 47.0 | 7.62 | 4496 | 2963 | 100 % | 79 % | 85 % | 0 | 13.4 |

## Motores: Ollama frente a llama.cpp (`qwen3:4b-instruct`, CPU, 4 hilos)

| Motor | Versión | Carga s | Prompt tok/s | Gen tok/s | Pico MB | Errores | JSON válido | Precisión | Recall |
|---|---|---|---|---|---|---|---|---|---|
| ollama | 0.40.11 | 5.22 | 42.9 | 8.07 | 3443 | 0 | 100 % | 71 % | 77 % |
| llamacpp | version: 0.8.0-dev (build 12018, commit 8956c769e) | 13.8 | 40.8 | 7.42 | 2576 | 0 | 100 % | 71 % | 77 % |

## GPU

| Ollama | Gen tok/s | Prompt tok/s | Carga s | VRAM usada MB |
|---|---|---|---|---|
| cpu | 8.12 | 41.9 | 3.88 | 844 |
| auto | 7.56 | 46.0 | 6.24 | 1555 |

Aceleración de generación con GPU: ×0.93.

## Marcos: salida estructurada

| Vía | JSON válido | Precisión | Recall | s/caso |
|---|---|---|---|---|
| validación propia | 100 % | 79 % | 85 % | 13.5 |
| Pydantic AI 2.64.0 | 100 % | 79 % | 85 % | 12.9 |

## Escenas (video sintético de 2.4 min, corte cada 4 s)

| Detector | Versión | s por min de video | Cortes hallados | Falsos + |
|---|---|---|---|---|
| ffmpeg_scene_0.3 | — | 0.261 | 20 % | 0 |
| ffmpeg_scene_0.2 | — | 0.259 | 20 % | 0 |
| ffmpeg_scene_0.1 | — | 0.26 | 26 % | 0 |
| ffmpeg_scene_0.05 | — | 0.265 | 43 % | 0 |
| pyscenedetect | 0.7.2 | 1.78 | 20 % | 0 |

## OCR (36 fotogramas sintéticos con cifras conocidas)

| Motor | Versión | s/fotograma | Cifras | 720p | 480p | Fotogramas completos | Pico MB |
|---|---|---|---|---|---|---|---|
| tesseract | 5.5.3.20260724 (spa+eng) | 1.1 | 57 % | 55 % | 62 % | 12 | 224 |
| rapidocr | 3.10.0 | 1.52 | 99 % | 99 % | 100 % | 35 | 437 |

## Visión-lenguaje (subconjunto de los mismos fotogramas)

| Modelo | Lado px | Fotogramas | Carga s | s/fotograma | Activo | Marco | Niveles | Pico MB | RAM libre mín. MB | Errores |
|---|---|---|---|---|---|---|---|---|---|---|
| qwen3-vl:2b-instruct-q4_K_M | 768 | 5 | 18.3 | 66.5 | 100 % | 100 % | 89 % | 8833 | 1380 | 0 |

- qwen3-vl:2b-instruct-q4_K_M: cortado: RAM libre 1470 MB < 1500 MB.
## ASR

| Motor | Modelo | Cómputo | Factor de tiempo real | WER | Pico MB |
|---|---|---|---|---|---|
| faster-whisper | small | int8 | es ×0.184; en ×0.146 | es 23 %; en 21 % | 2638 |
| faster-whisper | large-v3-turbo | int8 | es ×0.517; en ×0.602 | es 19 %; en 21 % | 3938 |

## Embeddings (calidad: T71)

| Modelo | Dim. | s/100 textos | Primer lote s | Pico MB |
|---|---|---|---|---|
| qwen3-embedding:0.6b | 1024 | 36.2 | 21.4 | 2450 |

## Presupuesto de cómputo (derivado)

Horas de cómputo por hora de video, una etapa a la vez (sin solaparse):

| Etapa | h/h de video | Origen |
|---|---|---|
| asr_h | 0.184 | medido |
| scenes_h | 0.03 | medido |
| ocr_h | 0.051 | medido |
| vlm_h | 0.369 | medido |
| llm_h | 0.117 | medido |

- Con subtítulos (sin ASR): 0.567 h/h · sin subtítulos: 0.751 h/h.
- Videos por noche (8 h, videos de 20 min, 70 % con subtítulos): **38.6**; sin VLM (solo OCR + LLM): **95.2**.
- Tope de RAM por etapa (pico medido, MB): asr 2638, ocr 437, vlm 8833, llm 4496.
- Supuestos (no medidos; T64 los mide en la muestra real): `{'words_per_min': 150, 'tokens_per_word': 1.6, 'out_tokens_per_1k_in': 60, 'frames_ocr_per_h': 120, 'frames_vlm_per_h': 20, 'night_h': 8, 'video_min': 20, 'subs_share': 0.7}`.
- Etapas sin medir (el presupuesto las omite): ninguna.
