"""Estadística pura del banco de latencia (T77): histogramas fusionables, reloj y flujos.

Sin red ni disco: `scripts/hft_latency.py` captura y este módulo resume. Unidades en ms salvo
donde el nombre diga `_us`. Definiciones (las mismas en el informe):
- desfase = `serverTime − punto medio local` de cada `GET /fapi/v1/time` (supone ida y vuelta
  simétricas; el error está acotado por RTT/2, que se informa como incertidumbre absoluta);
- antigüedad de un evento = reloj local corregido al recibirlo − `E` (o `T`);
- `E − T` = retraso interno de Binance entre la transacción y la emisión (solo relojes del
  servidor: no depende del desfase);
- jitter = p95 − p50 de la antigüedad; IPDV = media de |Δ antigüedad| entre mensajes seguidos.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

import numpy as np

QUANTILES = (0.5, 0.95, 0.99)
STALL_MS = 5_000.0                       # silencio de un flujo que cuenta como corte


@dataclass
class Hist:
    """Histograma disperso de ancho fijo: se fusiona entre corridas y da percentiles."""

    width: float = 1.0
    counts: dict[int, int] = field(default_factory=dict)

    @classmethod
    def of(cls, values: Iterable[float], width: float = 1.0) -> Hist:
        h = cls(width)
        h.add_many(values)
        return h

    def add_many(self, values: Iterable[float]) -> None:
        v = np.asarray(list(values) if not isinstance(values, np.ndarray) else values,
                       dtype=float)
        v = v[np.isfinite(v)]
        if not v.size:
            return
        keys, n = np.unique(np.floor(v / self.width).astype(np.int64), return_counts=True)
        for k, c in zip(keys.tolist(), n.tolist(), strict=True):
            self.counts[k] = self.counts.get(k, 0) + c

    def add(self, value: float) -> None:
        if math.isfinite(value):
            k = math.floor(value / self.width)
            self.counts[k] = self.counts.get(k, 0) + 1

    @property
    def n(self) -> int:
        return sum(self.counts.values())

    def merge(self, other: Hist) -> Hist:
        if other.width != self.width:
            raise ValueError(f"anchos distintos: {self.width} y {other.width}")
        out = Hist(self.width, dict(self.counts))
        for k, c in other.counts.items():
            out.counts[k] = out.counts.get(k, 0) + c
        return out

    def quantile(self, q: float) -> float | None:
        """Rango más cercano (`ceil(q·n)`); devuelve el centro del intervalo."""
        n = self.n
        if not n:
            return None
        target, cum = max(1, math.ceil(q * n)), 0
        for k in sorted(self.counts):
            cum += self.counts[k]
            if cum >= target:
                return (k + 0.5) * self.width
        return None  # inalcanzable: cum llega a n

    def summary(self, nd: int = 1) -> dict:
        if not self.counts:
            return {"n": 0}
        out = {"n": self.n}
        for q in QUANTILES:
            out[f"p{round(q * 100)}"] = round(self.quantile(q), nd)
        out["max"] = round((max(self.counts) + 0.5) * self.width, nd)
        return out

    def to_json(self) -> dict:
        return {"width": self.width, "counts": {str(k): c for k, c in sorted(self.counts.items())}}

    @classmethod
    def from_json(cls, d: dict) -> Hist:
        return cls(float(d["width"]), {int(k): int(c) for k, c in d["counts"].items()})


@dataclass(frozen=True)
class ClockSample:
    """Un `GET /fapi/v1/time`: reloj local (época, µs) al enviar y al recibir + `serverTime`."""

    send_us: int
    recv_us: int
    server_ms: int

    @property
    def rtt_ms(self) -> float:
        return (self.recv_us - self.send_us) / 1000

    @property
    def mid_ms(self) -> float:
        return (self.send_us + self.recv_us) / 2000

    @property
    def offset_ms(self) -> float:
        return self.server_ms - self.mid_ms


@dataclass(frozen=True)
class Anchors:
    """Desfase servidor − local por ventana (la muestra de menor RTT de cada una)."""

    t_ms: np.ndarray
    offset_ms: np.ndarray
    rtt_ms: np.ndarray

    def offset_at(self, t_ms: np.ndarray | float) -> np.ndarray:
        """Interpolación lineal entre anclas (constante fuera de los extremos): tolera saltos
        del reloj de Windows mejor que una sola recta."""
        return np.interp(t_ms, self.t_ms, self.offset_ms)


def clock_anchors(samples: Sequence[ClockSample], win_s: float = 60.0) -> Anchors:
    if not samples:
        raise ValueError("sin muestras de reloj: no se puede corregir la antigüedad")
    t0 = min(s.mid_ms for s in samples)
    best: dict[int, ClockSample] = {}
    for s in samples:
        k = int((s.mid_ms - t0) // (win_s * 1000))
        if k not in best or s.rtt_ms < best[k].rtt_ms:
            best[k] = s
    chosen = [best[k] for k in sorted(best)]
    return Anchors(np.array([s.mid_ms for s in chosen]), np.array([s.offset_ms for s in chosen]),
                   np.array([s.rtt_ms for s in chosen]))


def clock_summary(samples: Sequence[ClockSample], anchors: Anchors) -> dict:
    """Deriva (ppm, recta de mínimos cuadrados sobre las anclas), residuo máximo (delata saltos
    del reloj) e incertidumbre absoluta (mediana de RTT/2 de las anclas)."""
    out = {"samples": len(samples), "anchors": int(anchors.t_ms.size),
           "offset_ms_first": round(float(anchors.offset_ms[0]), 1),
           "offset_ms_last": round(float(anchors.offset_ms[-1]), 1),
           "uncertainty_ms": round(float(np.median(anchors.rtt_ms)) / 2, 1)}
    if anchors.t_ms.size >= 2:
        x = anchors.t_ms - anchors.t_ms[0]
        slope, icpt = np.polyfit(x, anchors.offset_ms, 1)
        resid = anchors.offset_ms - (slope * x + icpt)
        out["drift_ppm"] = round(float(slope) * 1e6, 2)
        out["resid_max_ms"] = round(float(np.max(np.abs(resid))), 1)
    return out


def stream_kind(stream: str) -> str | None:
    """`btcusdt@depth@100ms` → `depth`; `btcusdt@markPrice@1s` → `markPrice`."""
    parts = stream.split("@")
    return parts[1] if len(parts) > 1 else None


def event_times(kind: str, data: dict) -> tuple[int, int]:
    """(`E`, `T`) del evento; −1 si falta. En `markPrice`, `T` es la próxima hora de funding,
    no una transacción: no se usa."""
    e = int(data.get("E", -1))
    t = -1 if kind == "markPrice" else int(data.get("T", -1))
    return e, t


def _rates(loc_ms: np.ndarray, duration_s: float) -> dict:
    """Mensajes por segundo de cada minuto completo (p5/p50/p95)."""
    if loc_ms.size < 2 or duration_s < 60:
        return {}
    bins = np.floor((loc_ms - loc_ms[0]) / 60_000).astype(int)
    full = int(duration_s // 60)
    per_min = np.bincount(bins, minlength=full)[:full] / 60.0
    return {k: round(float(np.percentile(per_min, q)), 2)
            for k, q in (("p5", 5), ("p50", 50), ("p95", 95))}


def stream_stats(loc_us: Sequence[int], e_ms: Sequence[int], t_ms: Sequence[int],
                 anchors: Anchors, duration_s: float,
                 proc_us: Hist | None = None) -> tuple[dict, dict[str, Hist]]:
    """Resumen de un flujo + sus histogramas (para fusionar corridas)."""
    loc = np.asarray(loc_us, dtype=float) / 1000
    e = np.asarray(e_ms, dtype=float)
    t = np.asarray(t_ms, dtype=float)
    hists: dict[str, Hist] = {}
    if loc.size == 0:
        return {"msgs": 0}, hists
    server_now = loc + anchors.offset_at(loc)
    ok_e = e > 0
    age_e = server_now[ok_e] - e[ok_e]
    hists["age_E"] = Hist.of(age_e)
    ok_t = t > 0
    if ok_t.any():
        hists["age_T"] = Hist.of(server_now[ok_t] - t[ok_t])
        both = ok_t & ok_e
        hists["E_minus_T"] = Hist.of(e[both] - t[both])
    inter = np.diff(loc)
    if inter.size:
        hists["interarrival"] = Hist.of(inter)
    if proc_us is not None and proc_us.n:
        hists["proc_us"] = proc_us
    out = {"msgs": int(loc.size), "msg_per_s": round(loc.size / max(duration_s, 1e-9), 2),
           "msg_per_s_by_minute": _rates(loc, duration_s),
           "stalls_5s": int((inter > STALL_MS).sum()) if inter.size else 0}
    for k, h in hists.items():
        out[k] = h.summary(0 if k == "proc_us" else 1)
    if age_e.size:
        a = hists["age_E"]
        out["jitter_ms"] = round(a.quantile(0.95) - a.quantile(0.5), 1)
        out["ipdv_ms"] = round(float(np.mean(np.abs(np.diff(age_e)))), 2) if age_e.size > 1 else 0
    return out, hists
