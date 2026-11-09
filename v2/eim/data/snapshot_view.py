"""Lectura de una instantánea con la interfaz del almacén (T124): corta en su fecha.

`SnapshotView` ofrece `read_candles`, `read_series("funding")` y `source` con las firmas de
`Store`, así que un productor (puerta de edge, backtest, calibración) lee de la instantánea sin
cambiar su código. Pedir una vela posterior al corte lanza `LookaheadError`; pedir otra serie o
antes del inicio, `SnapshotScopeError`: nunca se devuelve en silencio menos de lo pedido.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from eim.core import Candle
    from eim.data.snapshots import Snapshot


class LookaheadError(LookupError):
    """Se pidió una vela posterior al corte de la instantánea."""


class SnapshotScopeError(LookupError):
    """Se pidió algo que la instantánea no contiene (otra serie, antes de su inicio)."""


class SnapshotView:
    """Lectura de una instantánea con la interfaz del almacén. Corta en su fecha."""

    def __init__(self, snap: Snapshot) -> None:
        self.snap, self.info = snap, snap.info

    def _check(self, symbol: str, timeframe: str, kind: str, start: int | None,
               end: int | None) -> None:
        i = self.info
        if (kind, symbol, timeframe) != (i.kind, i.symbol, i.timeframe):
            raise SnapshotScopeError(f"{i.id} es {i.kind} {i.symbol} {i.timeframe}, "
                                     f"no {kind} {symbol} {timeframe}")
        if end is not None and end > i.end_ms:
            raise LookaheadError(f"{i.id} corta en {i.end_ms}: no hay datos hasta {end}")
        if start is not None and start < i.start_ms:
            raise SnapshotScopeError(f"{i.id} empieza en {i.start_ms}: no cubre {start}")

    def read_candles(self, symbol: str, timeframe: str, start: int | None = None,
                     end: int | None = None, last: int | None = None,
                     kind: str = "candles") -> list[Candle]:
        self._check(symbol, timeframe, kind, start, end)
        out = [c for c in self.snap.candles
               if (start is None or c.t >= start) and (end is None or c.t < end)]
        return out[-last:] if last else out

    def read_series(self, kind: str, symbol: str, timeframe: str = "-", start: int | None = None,
                    end: int | None = None, last: int | None = None) -> list[tuple[int, float]]:
        if kind != "funding":
            raise SnapshotScopeError(f"{self.info.id} solo guarda velas y funding, no {kind}")
        self._check(symbol, self.info.timeframe, self.info.kind, start, end)
        out = [r for r in self.snap.funding
               if (start is None or r[0] >= start) and (end is None or r[0] < end)]
        return out[-last:] if last else out

    def source(self, kind: str, symbol: str, timeframe: str = "-") -> str | None:
        if kind == "funding":
            return self.info.funding_source or None
        self._check(symbol, timeframe, kind, None, None)
        return self.info.source
