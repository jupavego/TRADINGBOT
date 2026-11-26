"""Etapa 3 del embudo (T93): puntuación barata y vectorizada de todo el universo, sin agentes.

Una sola pasada de NumPy sobre el panel (`panel.py`) calcula, por instrumento, métricas de
precio, volatilidad, régimen, anomalías, fuerza relativa y calidad del dato, y las resume en una
**puntuación de interés** entre 0 y 1. Es un **filtro de atención**, no una señal ni una
predicción: dice qué merece que los agentes profundos (T94) lo miren, no hacia dónde irá.

**Fórmula (versión `SCREEN_VERSION`).** Cada componente se convierte en su percentil dentro del
universo de la corrida (empates promediados), se promedia con los pesos de `WEIGHTS` sobre los
que existen en esa fila, y se multiplica por la calidad (0–1). Mismas velas → mismas
puntuaciones: no hay azar ni dependencia del orden de entrada (las filas se ordenan por id).

Requiere ≥ 61 velas válidas por fila (lo garantiza la etapa 2 con `min_bars`).
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from eim.scanner.panel import Panel
from eim.scanner.params import SCREEN_VERSION

WINDOW = 61                     # 60 rendimientos: volatilidad larga y anomalía de precio
HORIZONS = (1, 5, 20)
ATR_N = 14
CLIP_Z = 10.0
MAD_K = 1.4826                  # MAD → σ bajo normalidad
JUMP_SIGMAS, JUMP_FLOOR = 8.0, 0.15   # los mismos umbrales de salto de `eim/data/quality.py`
EPS = 1e-12
#: Componentes de la puntuación y su peso (todos en valor absoluto: interés, no dirección).
WEIGHTS: dict[str, float] = {"mom": 1.0, "vol_anom": 1.0, "price_anom": 1.0, "regime": 1.0,
                             "rs": 1.0}
#: Referencia de fuerza relativa por clase; sin referencia válida, la mediana de su clase.
BENCHMARKS: dict[str, str] = {"crypto": "crypto.binance.usdm.BTCUSDT"}
MIN_CLASS_MEDIAN = 3


@dataclass(frozen=True)
class ScreenResult:
    ids: tuple[str, ...]
    score: np.ndarray
    quality: np.ndarray
    metrics: dict[str, np.ndarray]
    elapsed_ms: float
    version: str = SCREEN_VERSION

    @property
    def ms_per_instrument(self) -> float:
        return self.elapsed_ms / len(self.ids) if self.ids else 0.0

    def order(self) -> list[int]:
        """Filas por puntuación descendente; empates por id (determinista)."""
        s = np.nan_to_num(self.score, nan=-1.0)
        return sorted(range(len(self.ids)), key=lambda i: (-s[i], self.ids[i]))

    def rows(self) -> list[dict]:
        """Una fila por instrumento, ya ordenada, con su rango (1 = más interesante)."""
        out = []
        for rank, i in enumerate(self.order(), 1):
            out.append({"instrument_id": self.ids[i], "rank": rank, "score": _f(self.score[i]),
                        "quality": _f(self.quality[i]),
                        "metrics": {k: _f(v[i]) for k, v in sorted(self.metrics.items())}})
        return out

    def shortlist(self, k: int, min_score: float = 0.0) -> list[str]:
        return [self.ids[i] for i in self.order()[:k]
                if np.isfinite(self.score[i]) and self.score[i] >= min_score]

    def fingerprint(self) -> str:
        """Huella de las puntuaciones (para comprobar que un barrido es reproducible)."""
        import hashlib
        d = hashlib.blake2b(digest_size=12)
        d.update("|".join(self.ids).encode())
        d.update(np.ascontiguousarray(self.score, dtype=np.float64).tobytes())
        return d.hexdigest()


def _f(x: float) -> float | None:
    return float(x) if np.isfinite(x) else None


def pct_rank(x: np.ndarray) -> np.ndarray:
    """Percentil 0–1 dentro del vector, empates promediados; NaN se queda NaN."""
    out = np.full(x.shape, np.nan)
    ok = np.isfinite(x)
    m = int(ok.sum())
    if m == 0:
        return out
    if m == 1:
        out[ok] = 0.5
        return out
    s = np.sort(x[ok])
    lo = np.searchsorted(s, x[ok], "left")
    hi = np.searchsorted(s, x[ok], "right")
    out[ok] = (lo + hi - 1) / 2 / (m - 1)
    return out


def _robust_z(last: np.ndarray, hist: np.ndarray) -> np.ndarray:
    med = np.median(hist, axis=1)
    mad = np.median(np.abs(hist - med[:, None]), axis=1) * MAD_K
    return np.clip((last - med) / np.maximum(mad, EPS), -CLIP_Z, CLIP_Z)


def _relative_strength(ret20: np.ndarray, last_t: np.ndarray, ids: Sequence[str],
                       classes: Sequence[str]) -> np.ndarray:
    """Rendimiento de 20 velas menos el de la referencia de su clase en la misma fecha."""
    rs = np.full(len(ids), np.nan)
    pos = {iid: k for k, iid in enumerate(ids)}
    groups: dict[tuple[str, int], list[int]] = {}
    for k, (cls, t) in enumerate(zip(classes, last_t.tolist(), strict=True)):
        groups.setdefault((cls, int(t)), []).append(k)
    for (cls, t), rows in groups.items():
        b = pos.get(BENCHMARKS.get(cls, ""))
        if b is not None and int(last_t[b]) == t and np.isfinite(ret20[b]):
            ref = ret20[b]
        else:
            vals = ret20[rows][np.isfinite(ret20[rows])]
            if len(vals) < MIN_CLASS_MEDIAN:
                continue
            ref = float(np.median(vals))
        rs[rows] = ret20[rows] - ref
    return rs


def compute_metrics(p: Panel, classes: Sequence[str]) -> dict[str, np.ndarray]:
    """Métricas por fila sobre las últimas `WINDOW` velas (todas válidas tras la etapa 2)."""
    C, H, L, V = (a[:, -WINDOW:] for a in (p.c, p.h, p.l, p.v))
    with np.errstate(divide="ignore", invalid="ignore"):
        lr = np.diff(np.log(C), axis=1)                       # (S, 60)
        last = C[:, -1]
        m: dict[str, np.ndarray] = {f"ret_{h}": np.log(last / C[:, -1 - h]) for h in HORIZONS}
        vol5, vol20, vol60 = (np.std(lr[:, -k:], axis=1, ddof=1) for k in (5, 20, 60))
        m["vol_20"], m["vol_60"] = vol20, vol60
        m["mom"] = m["ret_20"] / np.maximum(vol20 * np.sqrt(20), EPS)
        prev = C[:, -ATR_N - 1:-1]
        hh, ll = H[:, -ATR_N:], L[:, -ATR_N:]
        tr = np.maximum(hh - ll, np.maximum(np.abs(hh - prev), np.abs(ll - prev)))
        m["atr_rel"] = tr.mean(axis=1) / last
        m["range_rel"] = (H[:, -20:].max(axis=1) - L[:, -20:].min(axis=1)) / last
        m["regime"] = np.log(np.maximum(vol5, EPS) / np.maximum(vol60, EPS))
        def sma(k: int, end: int) -> np.ndarray:
            return C[:, end - k:end if end else None].mean(axis=1)
        now, before = sma(10, 0) - sma(30, 0), sma(10, -5) - sma(30, -5)
        m["trend_flip"] = (np.sign(now) != np.sign(before)).astype(float)
        lv = np.log1p(np.maximum(V[:, -20:], 0.0))
        m["vol_anom"] = _robust_z(lv[:, -1], lv[:, :-1])
        m["price_anom"] = _robust_z(lr[:, -1], lr[:, :-1])
        m["rs"] = _relative_strength(m["ret_20"], p.last_t(), p.ids, classes)
        m["rs_z"] = m["rs"] / np.maximum(vol20 * np.sqrt(20), EPS)
        # calidad del dato
        madr = np.median(np.abs(lr - np.median(lr, axis=1)[:, None]), axis=1) * MAD_K
        jump = np.abs(lr) > np.maximum(JUMP_SIGMAS * madr, JUMP_FLOOR)[:, None]
        m["jumps"] = jump.sum(axis=1).astype(float)
        m["zero_volume"] = (V[:, -20:] <= 0).mean(axis=1)
        m["flat_bars"] = (H[:, -20:] <= L[:, -20:]).mean(axis=1)
        m["coverage"] = np.minimum(p.n, p.width) / max(p.width, 1)
    return m


def quality_of(m: Mapping[str, np.ndarray]) -> np.ndarray:
    """0–1: penaliza volumen cero, velas planas (sin negociación) y saltos anómalos."""
    q = (1 - m["zero_volume"]) * (1 - m["flat_bars"]) / (1 + m["jumps"])
    return np.where(np.isfinite(q), np.clip(q, 0.0, 1.0), 0.0)


def score_of(m: Mapping[str, np.ndarray], quality: np.ndarray) -> np.ndarray:
    comp = {"mom": np.abs(m["mom"]), "vol_anom": np.abs(m["vol_anom"]),
            "price_anom": np.abs(m["price_anom"]), "regime": np.maximum(m["regime"], 0.0),
            "rs": np.abs(m["rs_z"])}
    ranks = np.vstack([pct_rank(comp[k]) for k in WEIGHTS])
    w = np.array(list(WEIGHTS.values()))[:, None] * np.isfinite(ranks)
    with np.errstate(invalid="ignore"):
        mean = np.nansum(np.nan_to_num(ranks) * w, axis=0) / w.sum(axis=0)
    return np.where(w.sum(axis=0) > 0, mean * quality, np.nan)


def screen(p: Panel, classes: Sequence[str]) -> ScreenResult:
    """Puntuación de todo el panel. `classes` = clase de activo por fila (para la referencia)."""
    if len(classes) != p.size:
        raise ValueError("una clase por fila del panel")
    t0 = time.perf_counter()
    if p.size == 0:
        return ScreenResult((), np.zeros(0), np.zeros(0), {}, 0.0)
    if int(p.n.min()) < WINDOW:
        raise ValueError(f"la etapa 3 necesita ≥ {WINDOW} velas por fila (etapa 2: min_bars)")
    order = sorted(range(p.size), key=lambda i: p.ids[i])
    if order != list(range(p.size)):
        p = p.take(order)
        classes = [classes[i] for i in order]
    m = compute_metrics(p, classes)
    q = quality_of(m)
    s = score_of(m, q)
    return ScreenResult(ids=p.ids, score=s, quality=q, metrics=m,
                        elapsed_ms=(time.perf_counter() - t0) * 1000)
