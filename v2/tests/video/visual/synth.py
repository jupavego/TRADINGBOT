"""Fotogramas sintéticos con valores conocidos para T66 (numpy puro, sin Pillow ni OpenCV).

Gráfico oscuro 1280×720: eje de precios a la derecha (y=100 → 66.000 … y=600 → 61.000, 1.000 por
cada 100 px), rejilla en las marcas, velas verticales y una línea de nivel brillante en y=275
(= 64.250). El OCR se simula con las líneas que leería un OCR real sobre esa imagen.
"""

from __future__ import annotations

import numpy as np

from eim.core import Candle
from eim.indicators import momentum
from eim.localai.results import OCRLine

W, H = 1280, 720
AXIS_X = 1150
LEVEL_Y = 275
LEVEL = 64250.0
T0 = 1_762_000_000_000          # 2025-11-01 aprox., ms
HOUR = 3_600_000


def price_at(y: float) -> float:
    return 67000.0 - 10.0 * y


def chart_image(level_y: int | None = LEVEL_Y, *, seed: int = 0, shift: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.full((H, W, 3), (34, 23, 19), dtype=np.uint8)          # fondo oscuro (BGR)
    for y in range(100, 601, 100):
        img[y, :AXIS_X] = (57, 46, 42)                              # rejilla tenue
    img[400, :AXIS_X] = (200, 200, 200)                             # rejilla marcada (y=400)
    x = 30 + shift
    while x < AXIS_X - 20:
        top, bot = sorted(rng.integers(150, 560, size=2))
        img[top:bot + 1, x:x + 6] = (154, 166, 38) if rng.random() > 0.5 else (80, 83, 239)
        x += 14
    if level_y is not None:
        img[level_y - 1:level_y + 1, :AXIS_X] = (0, 200, 255)       # nivel naranja, 2 px
    return img


def slide_image(seed: int = 1) -> np.ndarray:
    img = np.full((H, W, 3), 245, dtype=np.uint8)
    img[60:140, 100:1180] = 30                                      # bloque de título
    return img


def line(text: str, x0: float, y0: float, x1: float, y1: float, conf: float = 0.95) -> OCRLine:
    return OCRLine(text=text, box=(x0, y0, x1, y1), confidence=conf)


def axis_lines() -> list[OCRLine]:
    out = []
    for y in range(100, 601, 100):
        v = f"{int(price_at(y)):,}".replace(",", ".")
        out.append(line(v, AXIS_X + 10, y - 9, AXIS_X + 110, y + 9))
    return out


def chart_ocr(*, tag: str | None = "64.250", rsi: str | None = None,
              extra: list[OCRLine] | None = None) -> list[OCRLine]:
    out = [line("BTCUSDT · 1H · Binance", 20, 10, 420, 40)] + axis_lines()
    if tag is not None:
        out.append(line(tag, AXIS_X + 10, LEVEL_Y - 9, AXIS_X + 110, LEVEL_Y + 9))
    if rsi is not None:
        out.append(line(rsi, 20, 620, 260, 640))
    return out + (extra or [])


def candles(n: int = 400, end: int | None = None, lo: float = 61500, hi: float = 65500
            ) -> list[Candle]:
    end = end or T0
    rng = np.random.default_rng(7)
    i = np.arange(n)
    px = np.clip(63500 + 1600 * np.sin(i / 9) + rng.normal(0, 80, n), lo, hi)
    out = []
    for i, c in enumerate(px):
        t = end - (n - i) * HOUR
        o = px[i - 1] if i else c
        out.append(Candle(t=t, o=float(o), h=float(max(o, c) + 50), l=float(min(o, c) - 50),
                          c=float(c), v=10.0))
    return out


def source(cs: list[Candle] | None = None):
    data = candles() if cs is None else cs

    def get(sym: str, tf: str, start: int, end: int) -> list[Candle]:
        if sym != "BTCUSDT":
            return []
        return [c for c in data if start <= c.t < end]

    return get


def rsi_now(n: int = 14) -> float:
    cs = candles()
    return float(momentum.rsi(np.array([c.c for c in cs]), n)[-1])
