"""Capa (a) OCR (T66): de líneas de texto con caja y confianza a lecturas.

Del texto salen: activo y marco del fotograma (contexto, con su caja), cifras, titulares (franja
superior o letra grande, con letras de verdad) e indicadores escritos («RSI (14) 62,3»). El texto
es SIEMPRE dato: una línea que «ordena» algo se guarda tal cual como titular y no cambia nada.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from eim.core.video import Box
from eim.localai.results import OCRLine
from eim.video.visual import text as T
from eim.video.visual.params import DEFAULT, VisualParams
from eim.video.visual.readings import Engine, Reading, box_center_y, box_height


@dataclass(frozen=True)
class Context:
    """Activo y marco leídos en el fotograma, con la caja que los respalda (o None)."""

    symbol: str | None = None
    symbol_box: Box | None = None
    timeframe: str | None = None
    timeframe_box: Box | None = None


def context(lines: list[OCRLine], p: VisualParams = DEFAULT) -> Context:
    sym = tf = None
    sbox = tbox = None
    for ln in sorted(lines, key=lambda ln: box_center_y(ln.box)):   # arriba primero
        if ln.confidence < p.min_ocr_conf:
            continue
        if sym is None and (s := T.symbol_of(ln.text)):
            sym, sbox = s, ln.box
        if tf is None and (f := T.timeframe_of(ln.text)):
            tf, tbox = f, ln.box
    return Context(sym, sbox, tf, tbox)


def read(lines: list[OCRLine], height: float, engine: Engine,
         p: VisualParams = DEFAULT) -> list[Reading]:
    good = [ln for ln in lines if ln.confidence >= p.min_ocr_conf and ln.text.strip()]
    if not good:
        return []
    med_h = median(box_height(ln.box) for ln in good) or 1.0
    out: list[Reading] = []
    for ln in good:
        inds = T.indicators(ln.text)
        for ind in inds:
            out.append(Reading("indicador", float(ind.value), ind.unit, "ocr", (engine,),
                               box=ln.box, quote=ind.raw, confidence=ln.confidence))
        ind_raw = " ".join(i.raw for i in inds)
        for num in T.numbers(ln.text):
            if num.raw in ind_raw:
                continue
            out.append(Reading("cifra", float(num.value), num.unit, "ocr", (engine,),
                               box=ln.box, quote=num.raw, confidence=ln.confidence))
        top = box_center_y(ln.box) <= p.title_top_frac * height
        big = box_height(ln.box) >= p.title_height_ratio * med_h
        words = [w for w in ln.text.split() if T.letters(w) >= 2]
        if (top or big) and T.letters(ln.text) >= p.title_min_letters and len(words) >= 2:
            out.append(Reading("titular", ln.text.strip(), "", "ocr", (engine,), box=ln.box,
                               quote=ln.text.strip(), confidence=ln.confidence))
    return out
