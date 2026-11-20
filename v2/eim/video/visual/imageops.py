"""Operaciones de imagen puras sobre arreglos numpy (sin OpenCV ni Pillow: el gate no las exige).

`gray` (H×W o H×W×3 → H×W en 0..1), `resize_area` (promedio por bloques), `dhash` (hash
perceptual por diferencias), `hamming` y `grid_mad` (diferencia media por celda, que sí ve el
cambio entre dos gráficos de fondo oscuro aunque su luminancia media sea igual: alerta 14 de T62).
"""

from __future__ import annotations

import numpy as np


def gray(img: np.ndarray) -> np.ndarray:
    a = np.asarray(img, dtype=float)
    if a.ndim == 3:
        a = a[..., :3] @ np.array([0.299, 0.587, 0.114])   # RGB; el orden BGR apenas cambia
    return a / 255.0 if a.max(initial=0) > 1.0 else a


def resize_area(a: np.ndarray, h: int, w: int) -> np.ndarray:
    """Reducción por promedio de área (bordes repartidos con índices enteros)."""
    a = np.asarray(a, dtype=float)
    ys = np.linspace(0, a.shape[0], h + 1).astype(int)
    xs = np.linspace(0, a.shape[1], w + 1).astype(int)
    out = np.empty((h, w))
    for i in range(h):
        y0, y1 = ys[i], max(ys[i + 1], ys[i] + 1)
        row = a[y0:y1]
        for j in range(w):
            x0, x1 = xs[j], max(xs[j + 1], xs[j] + 1)
            out[i, j] = row[:, x0:x1].mean()
    return out


def dhash(img: np.ndarray, size: int = 8) -> int:
    small = resize_area(gray(img), size, size + 1)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)


def hamming(a: int, b: int) -> int:
    return int(bin(a ^ b).count("1"))


def grid(img: np.ndarray, rows: int = 9, cols: int = 16) -> np.ndarray:
    return resize_area(gray(img), rows, cols)


def grid_mad(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.abs(np.asarray(a) - np.asarray(b))))
