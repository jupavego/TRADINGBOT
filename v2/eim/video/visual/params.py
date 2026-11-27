"""Parámetros de la lectura visual (T66), fijados antes de medir y versionados.

Cambiar cualquier valor exige subir `version`: cada observación guarda la versión con la que se
leyó (`VisualObservation.params_version`) y la medición de `evaluate.py` es por versión.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

# Presupuesto de T62 (`v2/reports/localai/bench_juanpablo-cpu.md`, supuestos del presupuesto):
# 120 fotogramas de OCR por hora de video y 20 del modelo visual.
FRAMES_OCR_PER_H = 120
FRAMES_VLM_PER_H = 20


@dataclass(frozen=True)
class VisualParams:
    version: str = "visual_v1"
    # --- muestreo y escenas (alerta 14 de T62: la luminancia media no ve cortes de pantalla) ---
    sample_every_s: float = 1.0       # muestreo mínimo para detectar escenas
    min_every_s: float = 30.0         # sin corte, al menos un candidato cada tanto
    hash_size: int = 8                # dHash de 64 bits
    cut_hash_bits: int = 12           # distancia de Hamming que cuenta como corte de escena
    cut_grid_mad: float = 0.06        # o diferencia media por celda (0..1) en rejilla 16×9
    dup_hash_bits: int = 5            # ≤ esto frente a un elegido = casi idéntico → se descarta
    frames_ocr_per_h: int = FRAMES_OCR_PER_H
    frames_vlm_per_h: int = FRAMES_VLM_PER_H
    min_frames: int = 3               # tope mínimo por video (videos muy cortos)
    thumb_width: int = 1280           # miniatura guardada (px de ancho, sin ampliar)
    # --- OCR ---
    min_ocr_conf: float = 0.5         # por debajo, la línea no produce observaciones
    title_top_frac: float = 0.22      # titular: en la franja superior…
    title_height_ratio: float = 1.5   # …o con letra ≥ 1,5× la mediana
    title_min_letters: int = 12
    # --- visión clásica ---
    axis_strip_frac: float = 0.16     # franja derecha donde viven las cifras del eje de precios
    axis_min_labels: int = 3          # cifras alineadas mínimas para ajustar el eje
    axis_max_resid: float = 0.01      # residuo relativo máximo del ajuste lineal del eje
    line_min_frac: float = 0.45       # una línea horizontal cubre ≥ 45 % del ancho del panel
    line_label_px: float = 12.0       # etiqueta del eje a ≤ 12 px de la línea = misma línea
    # --- validación ---
    agree_rel: float = 0.002          # OCR y modelo/visión «coinciden» a ≤ 0,2 %
    range_tol: float = 0.03           # rango real del activo ± 3 %
    range_bars: int = 150             # ventana del rango: 150 velas del marco leído
    range_default_days: float = 30.0  # sin marco leído: 30 días
    rsi_tol_abs: float = 3.0          # RSI recalculado frente al leído: ± 3 puntos
    ma_tol_rel: float = 0.005         # medias y VWAP recalculados: ± 0,5 %

    def fingerprint(self) -> str:
        raw = json.dumps(asdict(self), sort_keys=True).encode()
        return hashlib.sha256(raw).hexdigest()[:12]

    def frame_cap(self, duration_s: float, *, vlm: bool = False) -> int:
        """Tope de fotogramas por video según el presupuesto de T62 (mínimo `min_frames`)."""
        per_h = self.frames_vlm_per_h if vlm else self.frames_ocr_per_h
        return max(self.min_frames, int(-(-per_h * max(duration_s, 0.0) // 3600)))


DEFAULT = VisualParams()
