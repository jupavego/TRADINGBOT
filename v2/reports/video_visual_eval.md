# T66 — Medición de la lectura visual de video

Fecha: 2026-11-20 (plantilla, sin muestra) · Equipo: `—` · Parámetros: `visual_v1` (huella `ca82d914b108`) · Motores: — (sin medir todavía)

## Umbrales (fijados antes de medir, en `eim/video/visual/evaluate.py`)

Un tipo pasa a T67 si, con al menos 40 fotogramas etiquetados y 10 observaciones aceptadas, la precisión de lo aceptado llega a su umbral:

| Tipo | Umbral de precisión |
|---|---|
| cifra | 95% |
| titular | 85% |
| nivel | 90% |
| indicador | 90% |
| dibujo | 80% |

## Resultado

> Estado al construir T66 (2026-11-20): **sin muestra etiquetada**. Este informe se reescribe con `python -m eim.video.visual eval` (desde `v2/`, en `juanpablo-cpu` con el extra `[video]` y `EIM_LOCALAI_OCR=rapidocr`) cuando haya ≥ 40 fotogramas reales en `tests/fixtures/video/labels/`.

**Muestra insuficiente:** 0 fotogramas etiquetados de 40. Ningún tipo pasa a T67 hasta completarla.

| Tipo | Etiquetas | Aceptadas | Precisión | Cobertura | Rechazadas por la validación | ¿Pasa a T67? |
|---|---|---|---|---|---|---|
| cifra | 0 | 0 | — | — | 0 | no |
| titular | 0 | 0 | — | — | 0 | no |
| nivel | 0 | 0 | — | — | 0 | no |
| indicador | 0 | 0 | — | — | 0 | no |
| dibujo | 0 | 0 | — | — | 0 | no |

## Errores típicos


## Qué pasa y qué se descarta

- Pasan a T67: ninguno.
- Se descartan por poco fiables (o sin muestra suficiente): cifra, titular, nivel, indicador, dibujo.

**◆ El usuario decide si la lectura visual es suficientemente fiel.**
