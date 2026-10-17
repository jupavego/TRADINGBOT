"""Series históricas para simular arbitraje (T43): entrada pura del simulador.

La carga (I/O) vive en `eim/data/arb_history.py`. Cada serie lleva su `source`; lo que no se
pudo cargar queda en `ArbHistory.missing` con su motivo (el simulador lo declara).
Convención temporal: `t` = apertura de la vela (ms). Una decisión en `t` ve solo velas
cerradas antes de `t` (cierre de la vela `t − 1 h`) y se ejecuta a la apertura de `t`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from eim.arbitrage.sim.depth import DepthProfile
from eim.core import ArbMarket, Candle, SpotPair

H_MS = 3_600_000


@dataclass(frozen=True, eq=False)
class Bars:
    """Velas como arrays alineables por `t`; `vq` = volumen en moneda cotizada (≈ v · c)."""

    t: np.ndarray
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray  # noqa: E741 — mínimo de la vela (nombre del contrato `Candle`)
    c: np.ndarray
    vq: np.ndarray
    source: str

    @classmethod
    def from_candles(cls, candles: list[Candle], source: str) -> Bars:
        rows = sorted(candles, key=lambda k: k.t)
        return cls(t=np.array([k.t for k in rows], dtype=np.int64),
                   o=np.array([k.o for k in rows], dtype=float),
                   h=np.array([k.h for k in rows], dtype=float),
                   l=np.array([k.l for k in rows], dtype=float),
                   c=np.array([k.c for k in rows], dtype=float),
                   vq=np.array([k.v * k.c for k in rows], dtype=float), source=source)

    @classmethod
    def flat(cls, t: np.ndarray, price: np.ndarray, source: str = "test",
             vq: float = 1e9) -> Bars:
        """Velas de precio único por vela (tests y precios de referencia)."""
        p = np.asarray(price, dtype=float)
        return cls(t=np.asarray(t, dtype=np.int64), o=p.copy(), h=p.copy(), l=p.copy(),
                   c=p.copy(), vq=np.full(len(p), vq), source=source)

    def __len__(self) -> int:
        return len(self.t)

    @property
    def coverage(self) -> tuple[int, int] | None:
        return (int(self.t[0]), int(self.t[-1])) if len(self.t) else None

    def at(self, t: int) -> int | None:
        """Índice de la vela que abre exactamente en `t`."""
        i = int(np.searchsorted(self.t, t))
        return i if i < len(self.t) and self.t[i] == t else None

    def before(self, t: int) -> int | None:
        """Índice de la última vela que abre antes de `t` (ya cerrada en `t` si es de 1 h)."""
        i = int(np.searchsorted(self.t, t)) - 1
        return i if i >= 0 else None

    def vol_scale(self, i: int, ref: float | None, lo: float, window: int = 24) -> float:
        """Adelgazamiento del libro en la vela `i`: volumen medio de las `window` velas previas
        / volumen de referencia (el de la captura), recortado a [lo, 1]."""
        if ref is None or ref <= 0 or i <= 0:
            return 1.0
        v = float(self.vq[max(0, i - window):i].mean())
        return float(min(1.0, max(lo, v / ref)))


@dataclass(frozen=True, eq=False)
class Quarterly:
    symbol: str  # "BTCUSDT_250328"
    delivery_t: int
    bars: Bars  # solo velas con t < delivery_t
    settle: float | None  # precio de liquidación real (vela plana tras el vencimiento)
    settle_source: str = ""


@dataclass(frozen=True, eq=False)
class AssetHistory:
    asset: str
    spot: Bars | None = None  # {A}USDT spot
    perp: Bars | None = None  # {A}USDT perpetuo USDⓈ-M
    funding: tuple[tuple[int, float], ...] = ()  # liquidaciones realizadas del perpetuo
    quarterlies: tuple[Quarterly, ...] = ()
    usdc_perp: Bars | None = None  # {A}USDC perpetuo USDC-M
    usdc_funding: tuple[tuple[int, float], ...] = ()
    returns_15m: np.ndarray | None = None  # log-rendimientos 15 min (riesgo de latencia)


@dataclass(frozen=True, eq=False)
class ArbHistory:
    assets: dict[str, AssetHistory]
    usdcusdt: Bars | None = None
    depth: tuple[DepthProfile, ...] = ()
    depth_ref_vq: dict[str, float] = field(default_factory=dict)  # volumen/h en la captura
    tri_bars: dict[str, Bars] = field(default_factory=dict)  # spot 1 min (triangular)
    tri_pairs: tuple[SpotPair, ...] = ()
    captures: tuple[ArbMarket, ...] = ()  # fotografías reales con libros (T38/T39)
    filters: dict[str, dict[str, float | str]] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    coverage: dict[str, tuple[int, int]] = field(default_factory=dict)
    missing: dict[str, str] = field(default_factory=dict)  # pieza → motivo


@dataclass(frozen=True, eq=False)
class Funding:
    """Liquidaciones realizadas como arrays (búsquedas binarias en el bucle de decisiones)."""

    t: np.ndarray
    rate: np.ndarray

    @classmethod
    def of(cls, events: tuple[tuple[int, float], ...]) -> Funding:
        return cls(t=np.array([e for e, _ in events], dtype=np.int64),
                   rate=np.array([r for _, r in events], dtype=float))

    def __len__(self) -> int:
        return len(self.t)

    def next_after(self, t: int) -> int | None:
        """Primera liquidación posterior a `t` (el calendario se conoce de antemano)."""
        i = int(np.searchsorted(self.t, t, side="right"))
        return int(self.t[i]) if i < len(self.t) else None

    def interval_h(self, t: int) -> float:
        """Horas entre las dos últimas liquidaciones ≤ `t` (8 si no hay dos)."""
        i = int(np.searchsorted(self.t, t, side="right"))
        return float(self.t[i - 1] - self.t[i - 2]) / H_MS if i >= 2 else 8.0

    def before(self, t: int, n: int) -> list[tuple[int, float]]:
        """Últimas `n` liquidaciones ya ocurridas en `t` (sin mirar al futuro)."""
        i = int(np.searchsorted(self.t, t, side="right"))
        return [(int(a), float(b)) for a, b in zip(self.t[max(0, i - n):i],
                                                    self.rate[max(0, i - n):i], strict=True)]

    def between(self, a: int, b: int) -> tuple[np.ndarray, np.ndarray]:
        """Liquidaciones con a < T < b: las que cruza una posición abierta en a y cerrada en b."""
        i, j = np.searchsorted(self.t, a, side="right"), np.searchsorted(self.t, b, side="left")
        return self.t[i:j], self.rate[i:j]


def bar_of(t_event: int) -> int:
    """Vela de 1 h que abre en la hora de una liquidación (Binance sella con unos ms)."""
    return t_event - t_event % H_MS
