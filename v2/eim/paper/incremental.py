"""Sombra incremental de la vista del bróker simulado (T49).

Con la historia completa, rehacer todas las ideas y toda la sombra con cada contexto nuevo
tardaba decenas de segundos. Aquí se guarda, por símbolo y marco de decisión, lo ya evaluado y
solo se rehace desde el corte `T` = lo más temprano que pudo cambiar:

- contextos nuevos, borrados o reemplazados (`PaperStore.index`: origen + huella del JSON);
- velas de decisión o del marco mayor nuevas o revisadas desde la que abre en `c`: una idea en
  `t` solo ve velas cerradas ≤ t (sin anticipación) → pueden cambiar las ideas con
  `t ≥ c + vela`; si cambia el principio de la serie cambian todos los indicadores (son
  recursivos) → todo el marco;
- velas del camino o funding nuevos o revisados desde `c`: un resultado definitivo solo depende
  del camino y del funding entre su idea y su salida → se rehacen los no definitivos (ABIERTA,
  PENDIENTE) y los que salieron en `c` o después.

Lo anterior a `T` se reutiliza tal cual y la sombra sigue desde `T` con el estado que dejaron
esos resultados (`run_shadow(prior=...)`). Idéntico al cálculo completo: lo comprueba
`tests/paper/test_view_incremental.py` agregando contextos y velas por tandas.
"""

from __future__ import annotations

import heapq
from bisect import bisect_left
from collections import Counter
from dataclasses import dataclass, field
from typing import NamedTuple

import numpy as np

from eim.data.paper_store import PaperStore
from eim.data.store import Store
from eim.data.timeframes import tf_ms
from eim.paper.catalog import generate_ideas
from eim.paper.engine import FUNDING_MS, NEVER, Outcome, Path, run_shadow
from eim.paper.params import ExecParams
from eim.paper.service import WARMUP_BARS
from eim.paper.trend import HtfTrend

PATH_LEAD_MS = 4 * 3_600_000      # el camino empieza 4 h antes del primer contexto
ALL = -NEVER                      # corte «todo»: sin memoria o con el principio cambiado


class Bar(NamedTuple):
    """Vela ligera con los campos de `Candle`, sin validar (ver `Store.read_candle_columns`)."""

    t: int
    o: float
    h: float
    l: float  # noqa: E741
    c: float
    v: float
    taker_buy_v: float
    trades: float


@dataclass(frozen=True)
class Series:
    """Serie leída del almacén en un cálculo: columnas numpy con `t` ascendente."""

    start: int                        # inicio pedido de la lectura
    cols: dict[str, np.ndarray]

    @property
    def t(self) -> np.ndarray:
        return self.cols["t"]

    def bars(self) -> list[Bar]:
        return list(map(Bar, *(self.cols[k].tolist() for k in Bar._fields)))

    def pairs(self) -> list[tuple[int, float]]:
        return list(zip(self.t.tolist(), self.cols["x"].tolist(), strict=True))


def _differs(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    d = a != b
    if a.dtype.kind == "f":
        d &= ~(np.isnan(a) & np.isnan(b))       # dato ausente en ambas lecturas = igual
    return d


def first_change(old: Series, new: Series, overlap: bool = False) -> int | None:
    """Primer instante (`t` de vela o de tasa) desde el que `new` difiere de `old`: filas
    nuevas (también al final), revisadas o borradas; None si son iguales. Con `overlap` solo se
    mira desde el mayor de los dos inicios de lectura (camino y funding: un resultado no mira
    antes de su idea y todas las ideas vigentes son posteriores a ambos inicios)."""
    lo = max(old.start, new.start) if overlap else None
    ia = 0 if lo is None else int(np.searchsorted(old.t, lo))
    ib = 0 if lo is None else int(np.searchsorted(new.t, lo))
    na, nb = len(old.t) - ia, len(new.t) - ib
    m = min(na, nb)
    diff = np.zeros(m, dtype=bool)
    for k, a in old.cols.items():
        diff |= _differs(a[ia:ia + m], new.cols[k][ib:ib + m])
    if diff.any():
        j = int(np.argmax(diff))
        return int(min(old.t[ia + j], new.t[ib + j]))
    if na != nb:
        return int(old.t[ia + m] if na > nb else new.t[ib + m])
    return None


def _earliest(*ts: int | None) -> int | None:
    return min((t for t in ts if t is not None), default=None)


def _t(o: Outcome) -> int:
    return o.idea.t


def _order(o: Outcome) -> tuple[int, str]:
    return o.idea.t, o.idea.sid          # el orden de `run_shadow`


@dataclass
class TfMemo:
    """Lo evaluado en un marco de decisión."""

    keys: dict[int, tuple[str, int]]     # asof → (origen, huella del contexto)
    counts: dict[int, int]               # asof → ideas generadas
    dec: Series                          # velas de decisión
    htf: Series | None                   # velas del marco mayor (tendencia)
    outs: list[Outcome]                  # resultados sombra del marco, en orden (t, sid)


@dataclass
class Memo:
    path: Series
    funding: Series
    tfs: dict[str, TfMemo] = field(default_factory=dict)


@dataclass
class Shadow:
    """Resultado de `IncrementalShadow.refresh` (la memoria se confirma aparte)."""

    index: dict[str, list[tuple[int, str, int]]]     # marco → (asof, origen, huella)
    outcomes: list[Outcome] = field(default_factory=list)
    path: Path | None = None
    n_ideas: int = 0
    since: int = ALL          # ideas y resultados anteriores a `since`: iguales al cálculo previo
    memo: Memo | None = None


class IncrementalShadow:
    """Ideas y sombra de la vista por símbolo. `refresh` no toca la memoria; `commit` la
    reemplaza cuando la vista ya está completa (un fallo a medias no la deja inconsistente)."""

    def __init__(self, store: Store, pstore: PaperStore, ep: ExecParams) -> None:
        self.store, self.pstore, self.ep = store, pstore, ep
        self._memo: dict[str, Memo] = {}

    def commit(self, symbol: str, sh: Shadow) -> None:
        if sh.memo is None:
            self._memo.pop(symbol, None)
        else:
            self._memo[symbol] = sh.memo

    def refresh(self, symbol: str) -> Shadow:
        index = {tf: self.pstore.index(symbol, tf) for tf in self.ep.timeframes}
        sh = Shadow(index)
        firsts = [rows[0][0] for rows in index.values() if rows]
        if not firsts:
            return sh
        t0 = min(firsts)
        start = t0 - PATH_LEAD_MS
        pser = Series(start, self.store.read_candle_columns(symbol, self.ep.path_tf, start=start))
        fser = _funding(self.store, symbol, t0 - FUNDING_MS)
        sh.path = Path(pser.bars(), fser.pairs(), tf_ms(self.ep.path_tf))
        old = self._memo.get(symbol)
        moved = None if old is None else _earliest(first_change(old.path, pser, overlap=True),
                                                    first_change(old.funding, fser, overlap=True))
        memo = Memo(pser, fser)
        since = ALL if old is None else NEVER
        for tf, rows in index.items():
            om = old.tfs.get(tf) if old is not None else None
            if not rows:
                since = ALL if om is not None else since    # el marco se quedó sin contextos
                continue
            tm, cut = self._timeframe(symbol, tf, rows, om, moved, sh.path)
            memo.tfs[tf] = tm
            since = min(since, cut)
            sh.n_ideas += sum(tm.counts.values())
        sh.outcomes = list(heapq.merge(*(tm.outs for tm in memo.tfs.values()), key=_order))
        sh.since, sh.memo = since, memo
        return sh

    def _timeframe(self, symbol: str, tf: str, rows: list[tuple[int, str, int]],
                   om: TfMemo | None, moved: int | None, path: Path) -> tuple[TfMemo, int]:
        bar, first = tf_ms(tf), rows[0][0]
        dec = self._candles(symbol, tf, first - WARMUP_BARS * bar)
        spec = self.ep.htf.get(tf)
        htf = None
        if spec:
            htf = self._candles(symbol, spec[0], first - 4 * spec[2] * tf_ms(spec[0]))
        keys = {a: (o, h) for a, o, h in rows}
        cut = ALL if om is None else _cut(om, keys, dec, bar, htf, spec, moved)
        if om is not None and cut >= NEVER:
            return TfMemo(keys, om.counts, dec, htf, om.outs), cut
        kept = om.outs[:bisect_left(om.outs, cut, key=_t)] if om is not None else []
        ctxs = [c for c in self.pstore.load(symbol, tf, start=cut if cut > first else None)
                if int(c["t"]) in keys]                 # coherente con el índice leído
        trend = HtfTrend(htf.bars(), tf_ms(spec[0]), spec[1], spec[2]).at if spec else None
        ideas = generate_ideas(ctxs, dec.bars(), symbol, bar, timeframe=tf, htf=trend,
                               exec_params=self.ep)
        counts = {a: n for a, n in om.counts.items() if a < cut} if om is not None else {}
        counts.update(Counter(i.t for i in ideas))
        outs = kept + run_shadow(ideas, path, self.ep, prior=kept)
        return TfMemo(keys, counts, dec, htf, outs), cut

    def _candles(self, symbol: str, tf: str, start: int) -> Series:
        return Series(start, self.store.read_candle_columns(symbol, tf, start=start))


def _funding(store: Store, symbol: str, start: int) -> Series:
    rows = store.read_series("funding", symbol, start=start)
    return Series(start, {"t": np.array([t for t, _ in rows], dtype=np.int64),
                          "x": np.array([x for _, x in rows], dtype=float)})


def _cut(om: TfMemo, keys: dict[int, tuple[str, int]], dec: Series, bar: int,
         htf: Series | None, spec: tuple[str, int, int] | None, moved: int | None) -> int:
    """Primer `t` de idea del marco que puede haber cambiado (NEVER si ninguno)."""
    ts = list(keys.keys() ^ om.keys.keys())                       # nuevos o borrados
    ts += [a for a, k in keys.items() if om.keys.get(a, k) != k]  # reemplazados
    c = first_change(om.dec, dec)
    if c is not None:
        ts.append(c + bar)
    if htf is not None and om.htf is not None and spec:
        c = first_change(om.htf, htf)
        if c is not None:
            ts.append(c + tf_ms(spec[0]))
    if moved is not None:          # no definitivos o con salida en/tras el cambio del camino
        t = next((o.idea.t for o in om.outs if o.exit_t is None or o.exit_t >= moved), None)
        if t is not None:
            ts.append(t)
    return min(ts, default=NEVER)
