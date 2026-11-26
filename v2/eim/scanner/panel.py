"""Panel de velas del universo (T93): una matriz por campo, una fila por instrumento.

La etapa 3 trabaja sobre matrices de NumPy y no sobre un objeto `Candle` por vela: con 10 000
instrumentos y 90 velas son 900 000 velas, y crear objetos cuesta más que calcular. Cada fila
tiene sus `n` velas válidas **alineadas a la derecha** (la última columna es la última vela
cerrada) y relleno `NaN` a la izquierda; las filas no comparten fecha, cada una lleva su `t`.

`data_hash` resume las velas exactas de cada fila (t, o, h, l, c, v): es la clave de datos de la
caché de la cola. Si una vela cambia o llega una nueva, cambia el hash y la caché no sirve.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

FIELDS = ("o", "h", "l", "c", "v")


@dataclass(frozen=True)
class Panel:
    ids: tuple[str, ...]           # id de instrumento por fila, en orden
    symbols: tuple[str, ...]
    t: np.ndarray                  # int64 (S, N); 0 en el relleno
    o: np.ndarray                  # float64 (S, N); NaN en el relleno
    h: np.ndarray
    l: np.ndarray                  # noqa: E741
    c: np.ndarray
    v: np.ndarray
    n: np.ndarray                  # int64 (S,): velas válidas por fila
    hashes: tuple[str, ...]

    @property
    def size(self) -> int:
        return len(self.ids)

    @property
    def width(self) -> int:
        return int(self.c.shape[1]) if self.c.ndim == 2 else 0

    def last_t(self) -> np.ndarray:
        return np.where(self.n > 0, self.t[:, -1], 0) if self.size else np.zeros(0, np.int64)

    def take(self, rows: list[int] | np.ndarray) -> Panel:
        """Subpanel con esas filas (en ese orden)."""
        idx = np.asarray(rows, dtype=np.int64)
        return Panel(ids=tuple(self.ids[i] for i in idx),
                     symbols=tuple(self.symbols[i] for i in idx), t=self.t[idx],
                     o=self.o[idx], h=self.h[idx], l=self.l[idx], c=self.c[idx], v=self.v[idx],
                     n=self.n[idx], hashes=tuple(self.hashes[i] for i in idx))

    def nbytes(self) -> int:
        return int(sum(getattr(self, f).nbytes for f in ("t", *FIELDS, "n")))


def row_hash(t: np.ndarray, o: np.ndarray, h: np.ndarray, lo: np.ndarray, c: np.ndarray,
             v: np.ndarray) -> str:
    """Huella de las velas válidas de una fila (orden y bytes exactos)."""
    d = hashlib.blake2b(digest_size=12)
    d.update(np.ascontiguousarray(t, dtype=np.int64).tobytes())
    for a in (o, h, lo, c, v):
        d.update(np.ascontiguousarray(a, dtype=np.float64).tobytes())
    return d.hexdigest()


def empty_panel(width: int) -> Panel:
    z = np.zeros((0, width))
    return Panel((), (), np.zeros((0, width), np.int64), z, z, z, z, z,
                 np.zeros(0, np.int64), ())


def from_rows(sym_ids: dict[str, str], symbol: np.ndarray, t: np.ndarray, o: np.ndarray,
              h: np.ndarray, lo: np.ndarray, c: np.ndarray, v: np.ndarray,
              width: int) -> Panel:
    """Panel desde filas planas ordenadas por (símbolo, t) ascendente.

    `sym_ids` = símbolo → id de instrumento, y define las filas y su orden (por id); un símbolo
    sin velas sale con `n = 0`. Si un símbolo trae más de `width` velas, se quedan las últimas.
    """
    order = sorted(sym_ids.items(), key=lambda kv: kv[1])
    S = len(order)
    T = np.zeros((S, width), np.int64)
    M = {f: np.full((S, width), np.nan) for f in FIELDS}
    n = np.zeros(S, np.int64)
    hashes: list[str] = []
    symbol = np.asarray(symbol).astype(str)
    if len(symbol):
        starts = np.flatnonzero(np.r_[True, symbol[1:] != symbol[:-1]])
        ends = np.r_[starts[1:], len(symbol)]
        spans = {str(symbol[a]): (int(a), int(b)) for a, b in zip(starts, ends, strict=True)}
    else:
        spans = {}
    cols = {"o": o, "h": h, "l": lo, "c": c, "v": v}
    for row, (sym, _iid) in enumerate(order):
        a, b = spans.get(sym, (0, 0))
        a = max(a, b - width)
        k = b - a
        n[row] = k
        if k:
            T[row, width - k:] = t[a:b]
            for f in FIELDS:
                M[f][row, width - k:] = cols[f][a:b]
        hashes.append(row_hash(T[row, width - k:], *(M[f][row, width - k:] for f in FIELDS)))
    return Panel(ids=tuple(i for _, i in order), symbols=tuple(s for s, _ in order), t=T,
                 o=M["o"], h=M["h"], l=M["l"], c=M["c"], v=M["v"], n=n, hashes=tuple(hashes))


def synthetic(n_instruments: int, width: int, *, seed: int = 0, step_ms: int = 86_400_000,
              end_t: int = 1_767_225_600_000) -> Panel:
    """Panel sintético reproducible (paseo aleatorio): para medir y proyectar el presupuesto
    sin datos reales. Nunca se presenta como mercado."""
    rng = np.random.default_rng(seed)
    r = rng.normal(0, 0.03, (n_instruments, width))
    c = 100 * np.exp(np.cumsum(r, axis=1))
    o = np.c_[c[:, :1], c[:, :-1]]
    spread = np.abs(rng.normal(0, 0.01, (n_instruments, width)))
    h, lo = np.maximum(o, c) * (1 + spread), np.minimum(o, c) * (1 - spread)
    v = rng.lognormal(12, 1, (n_instruments, width))
    t = np.broadcast_to(end_t - step_ms * np.arange(width)[::-1], (n_instruments, width)).copy()
    ids = tuple(f"crypto.synthetic.SYN{i:05d}" for i in range(n_instruments))
    hashes = tuple(row_hash(t[i], o[i], h[i], lo[i], c[i], v[i]) for i in range(n_instruments))
    return Panel(ids=ids, symbols=tuple(i.rsplit(".", 1)[1] for i in ids), t=t, o=o, h=h, l=lo,
                 c=c, v=v, n=np.full(n_instruments, width, np.int64), hashes=hashes)
