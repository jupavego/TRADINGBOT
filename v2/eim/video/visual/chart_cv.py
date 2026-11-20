"""Capa (b) visión clásica (T66): panel de gráfico, eje de precios y líneas horizontales.

Puro sobre arreglos numpy (sin OpenCV, para que el gate no lo exija):
1. **Eje**: cifras del OCR en la franja derecha que encajan en una recta `precio = a·y + b`
   (a < 0, residuo ≤ `axis_max_resid`). Sin eje ajustado no hay gráfico ni niveles.
2. **Rejilla vs etiquetas**: las cifras del eje en progresión aritmética son marcas de la
   rejilla; las que se salen de ella son etiquetas de precio (niveles dibujados, precio actual).
3. **Líneas**: filas finas que contrastan con las de arriba y abajo en ≥ `line_min_frac` del ancho
   del panel. Una línea en la altura de una marca es rejilla y se descarta.
Cada nivel sale dos veces si se puede: por la visión (altura → eje) y por el OCR (etiqueta a la
misma altura); el lector las compara.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from eim.core.video import Box
from eim.video.visual.params import DEFAULT, VisualParams
from eim.video.visual.readings import CV_ENGINE, Engine, Reading, box_center_y

CV = Engine(CV_ENGINE[0], CV_ENGINE[1], "sin-pesos")


@dataclass(frozen=True)
class Axis:
    a: float
    b: float
    ticks: tuple[Reading, ...]
    tags: tuple[Reading, ...]
    left: float                       # x donde empieza la franja del eje
    panel: Box

    def price(self, y: float) -> float:
        return self.a * y + self.b


def _fit(pts: list[tuple[float, float]]) -> tuple[float, float, float]:
    ys = np.array([p[0] for p in pts])
    vs = np.array([p[1] for p in pts])
    a, b = np.polyfit(ys, vs, 1)
    resid = float(np.max(np.abs(a * ys + b - vs) / np.maximum(np.abs(vs), 1e-9)))
    return float(a), float(b), resid


def fit_axis(cifras: list[Reading], width: float, height: float,
             p: VisualParams = DEFAULT) -> Axis | None:
    left = (1 - p.axis_strip_frac) * width
    labels = [r for r in cifras if r.kind == "cifra" and r.box and r.box[0] >= left
              and r.unit != "%" and isinstance(r.value, float) and r.value > 0]
    labels = list({round(box_center_y(r.box)): r for r in labels}.values())
    if len(labels) < p.axis_min_labels:
        return None
    pts = [(box_center_y(r.box), float(r.value)) for r in labels]
    a, b, resid = _fit(pts)
    if resid > p.axis_max_resid and len(pts) > p.axis_min_labels:   # una cifra mal leída
        worst = max(range(len(pts)), key=lambda i: abs(a * pts[i][0] + b - pts[i][1]))
        labels = labels[:worst] + labels[worst + 1:]
        a, b, resid = _fit([pt for i, pt in enumerate(pts) if i != worst])
    if a >= 0 or resid > p.axis_max_resid:
        return None
    vals = sorted(float(r.value) for r in labels)
    steps = np.diff(vals)
    step = float(np.median(steps)) if len(steps) else 0.0
    base = vals[0]

    def on_grid(v: float) -> bool:
        return step > 0 and abs((v - base) / step - round((v - base) / step)) < 0.02

    ticks = tuple(r for r in labels if on_grid(float(r.value)))
    tags = tuple(r for r in labels if not on_grid(float(r.value)))
    if len(ticks) < p.axis_min_labels:
        return None
    return Axis(a, b, ticks, tags, left, (0.0, 0.0, left, height))


def horizontal_lines(g: np.ndarray, x1: float, p: VisualParams = DEFAULT,
                     contrast: float = 0.12) -> list[float]:
    """Alturas (px) de las líneas horizontales finas del panel `[0, x1)` de la imagen gris."""
    a = np.asarray(g, dtype=float)[:, : max(1, int(x1))]
    if a.shape[0] < 5:
        return []
    up = np.abs(a[2:-2] - a[:-4])
    dn = np.abs(a[2:-2] - a[4:])
    frac = ((up > contrast) & (dn > contrast)).mean(axis=1)
    rows = np.where(frac >= p.line_min_frac)[0] + 2
    lines: list[float] = []
    run: list[int] = []
    for r in rows:
        if run and r - run[-1] > 1:
            lines.append(float(np.mean(run)))
            run = []
        run.append(int(r))
    if run:
        lines.append(float(np.mean(run)))
    return lines


def levels(g: np.ndarray, axis: Axis, p: VisualParams = DEFAULT) -> list[Reading]:
    """Niveles por visión (altura → eje) y por OCR (etiqueta a la misma altura)."""
    out: list[Reading] = []
    tick_y = [box_center_y(t.box) for t in axis.ticks if t.box]
    for y in horizontal_lines(g, axis.left, p):
        if any(abs(y - ty) <= p.line_label_px for ty in tick_y):
            continue                                   # rejilla del eje
        box = (0.0, y - 1, axis.left, y + 1)
        out.append(Reading("nivel", round(axis.price(y), 8), "precio", "vision", (CV,),
                           box=box, tags={"y": f"{y:.1f}"}))
        for tag in axis.tags:
            if tag.box and abs(box_center_y(tag.box) - y) <= p.line_label_px:
                out.append(Reading("nivel", float(tag.value), "precio", "ocr", tag.engines,
                                   box=tag.box, quote=tag.quote, confidence=tag.confidence,
                                   tags={"y": f"{y:.1f}"}))
                break
    return out
