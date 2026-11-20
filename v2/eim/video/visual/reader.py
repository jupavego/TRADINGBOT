"""Lector de un fotograma (T66): OCR → visión clásica → modelo visual (si toca) → validación.

Puro salvo los motores inyectados (`ocr.read`, `vision.ask` de `LocalAI`) y el proveedor de velas.
Un motor que falla no tumba la lectura: se sigue con lo que haya y queda en `warnings`. El texto
del OCR nunca llega al modelo visual (su pregunta es fija): lo escrito en la imagen es dato.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np

from eim.core.video import VisualObservation
from eim.video.visual import chart_cv, ocr_layer, vlm_layer
from eim.video.visual.imageops import gray
from eim.video.visual.params import DEFAULT, VisualParams
from eim.video.visual.readings import Reading, box_center_y, rel_diff
from eim.video.visual.validate import CandleSource, Validator

CALLER = "video.visual"


@dataclass(frozen=True)
class Frame:
    video_id: str
    frame_id: str
    t: float                 # segundos desde el inicio del video
    path: Path               # miniatura guardada (la ven los motores)
    image: np.ndarray        # la misma miniatura en memoria (la ve la visión clásica)


@dataclass
class FrameResult:
    frame_id: str
    observations: list[VisualObservation] = field(default_factory=list)
    is_chart: bool = False
    vlm_used: bool = False
    symbol: str | None = None
    timeframe: str | None = None
    warnings: list[str] = field(default_factory=list)


def _same(a: Reading, b: Reading, p: VisualParams) -> bool:
    if a.kind != b.kind or a.unit != b.unit:
        return False
    if a.kind == "indicador":
        return True
    if a.box and b.box and "y" in a.tags and "y" in b.tags:
        return a.tags["y"] == b.tags["y"]
    if a.box and b.box and abs(box_center_y(a.box) - box_center_y(b.box)) <= p.line_label_px:
        return True
    return rel_diff(float(a.value), float(b.value)) <= 0.02


def merge(primary: list[Reading], secondary: list[Reading], p: VisualParams) -> list[Reading]:
    """Une la misma cosa leída por dos capas (`ambos`); el valor que manda es el de `primary`."""
    out = list(primary)
    for r in secondary:
        hit = next((i for i, o in enumerate(out)
                    if o.kind in ("nivel", "indicador") and _same(o, r, p)
                    and not any(e in o.engines for e in r.engines)), None)
        if hit is None:
            out.append(r)
        else:
            out[hit] = out[hit].merged(r)
    return out


class FrameReader:
    def __init__(self, ocr: Any, vision: Any | None = None, candles: CandleSource | None = None,
                 p: VisualParams = DEFAULT) -> None:
        self.ocr, self.vision, self.candles, self.p = ocr, vision, candles, p

    def read(self, frame: Frame, *, ref_ms: int | None, allow_vlm: bool = False) -> FrameResult:
        p, res = self.p, FrameResult(frame.frame_id)
        h, w = frame.image.shape[:2]
        o = self.ocr.read(frame.path, caller=CALLER)
        lines = o.data if o.ok and o.data else []
        if not o.ok:
            res.warnings.append(f"OCR sin datos: {o.outcome} {o.reason}".strip())
        ocr_eng = vlm_layer.engine_of(o)
        ctx = ocr_layer.context(lines, p)
        found = ocr_layer.read(lines, h, ocr_eng, p)
        axis = chart_cv.fit_axis(found, w, h, p)
        levels: list[Reading] = []
        if axis is not None:
            res.is_chart = True
            levels = chart_cv.levels(gray(frame.image), axis, p)
            used = {id(t) for t in axis.ticks}
            tag_levels = {t.box for t in levels if t.source == "ocr"}
            found = [r for r in found if id(r) not in used and r.box not in tag_levels]
            tag_ids = {id(t) for t in axis.tags}
            found = [replace(r, unit="precio") if id(r) in tag_ids else r for r in found]
        ocr_levels = [r for r in levels if r.source == "ocr"]
        cv_levels = [r for r in levels if r.source == "vision"]
        readings = merge(found + ocr_levels, cv_levels, p)
        symbol, timeframe = ctx.symbol, ctx.timeframe
        if res.is_chart and allow_vlm and self.vision is not None:
            v = self.vision.ask(frame.path, vlm_layer.QUESTION, vlm_layer.ChartReading,
                                caller=CALLER)
            if v.ok and v.data is not None:
                res.vlm_used = True
                vs, vt = vlm_layer.context(v.data, w, h)
                if symbol and vs and vs != symbol:
                    res.warnings.append(f"activo: OCR {symbol} y modelo {vs}; manda el OCR")
                symbol, timeframe = symbol or vs, timeframe or vt
                readings = merge(readings, vlm_layer.readings(v.data, w, h,
                                                              vlm_layer.engine_of(v)), p)
            else:
                res.warnings.append(f"modelo visual sin datos: {v.outcome} {v.reason}".strip())
        res.symbol, res.timeframe = symbol, timeframe
        val = Validator(self.candles, symbol, timeframe, ref_ms, p)
        for r in readings:
            verdict = val.check(r)
            res.observations.append(self._obs(frame, r, verdict.state, verdict.note,
                                              symbol, timeframe))
        return res

    def _obs(self, frame: Frame, r: Reading, state: str, note: str, symbol: str | None,
             timeframe: str | None) -> VisualObservation:
        def join(attr: str) -> str:
            return "+".join(getattr(e, attr) for e in r.engines)

        return VisualObservation(
            video_id=frame.video_id, t=frame.t, frame_id=frame.frame_id, kind=r.kind,
            value=r.value, unit=r.unit, box=r.box, quote=r.quote, source=r.source,
            validation=state, validation_note=note, symbol=symbol, timeframe=timeframe,
            confidence=r.confidence, engine=join("engine"), model=join("model"),
            weights_sha=join("weights_sha"), params_version=self.p.version)

