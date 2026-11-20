"""Panel muestreado y matriz de variables (T80). Puro: arreglos dentro, arreglos fuera.

`Panel` es lo que deja el lector de la captura (`eim/data/collectors/hft_panel.py`): una fila por
cubo de muestreo con el estado del libro al CIERRE del cubo, el OFI acumulado dentro del cubo y
el flujo agresor del cubo. `build_matrix` lo convierte en la matriz de variables; cada columna se
calcula solo con la fila y las anteriores, y el calentamiento queda en NaN (`valid_rows`).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from eim.hft.features import book, flow, vol
from eim.hft.features.params import FeatureParams
from eim.hft.features.sampling import trailing_sum


@dataclass(frozen=True)
class Panel:
    """Cubos de muestreo de un símbolo. Todos los arreglos tienen la misma longitud."""

    t: np.ndarray            # ms UTC del cierre del cubo
    bid_p: np.ndarray        # (n, niveles) precios, mejor primero
    bid_q: np.ndarray
    ask_p: np.ndarray
    ask_q: np.ndarray
    ofi: np.ndarray          # (n, niveles) OFI acumulado dentro del cubo
    buy_v: np.ndarray        # volumen agresor comprador del cubo
    sell_v: np.ndarray
    n_trades: np.ndarray
    complete: np.ndarray     # False si el cubo toca un hueco o el libro no estaba sincronizado
    step_ms: int = 1000
    symbol: str = "BTCUSDT"

    def __len__(self) -> int:
        return int(self.t.shape[0])

    @property
    def levels(self) -> int:
        return int(self.bid_p.shape[1])

    @property
    def mid(self) -> np.ndarray:
        return book.mid(self.bid_p[:, 0], self.ask_p[:, 0])

    @property
    def micro(self) -> np.ndarray:
        return book.microprice(self.bid_p[:, 0], self.bid_q[:, 0],
                               self.ask_p[:, 0], self.ask_q[:, 0])

    def take(self, sel) -> Panel:
        """Submuestra (máscara booleana o índices), conservando el orden."""
        return replace(self, t=self.t[sel], bid_p=self.bid_p[sel], bid_q=self.bid_q[sel],
                       ask_p=self.ask_p[sel], ask_q=self.ask_q[sel], ofi=self.ofi[sel],
                       buy_v=self.buy_v[sel], sell_v=self.sell_v[sel],
                       n_trades=self.n_trades[sel], complete=self.complete[sel])


def concat(panels: list[Panel]) -> Panel:
    """Une paneles consecutivos (mismo paso y símbolo), en el orden recibido."""
    ps = [p for p in panels if len(p)]
    if not ps:
        raise ValueError("ningún panel con filas")
    first = ps[0]
    if any(p.step_ms != first.step_ms or p.symbol != first.symbol for p in ps):
        raise ValueError("paneles con paso o símbolo distintos")
    cat = lambda name: np.concatenate([getattr(p, name) for p in ps])  # noqa: E731
    return replace(first, t=cat("t"), bid_p=cat("bid_p"), bid_q=cat("bid_q"),
                   ask_p=cat("ask_p"), ask_q=cat("ask_q"), ofi=cat("ofi"),
                   buy_v=cat("buy_v"), sell_v=cat("sell_v"), n_trades=cat("n_trades"),
                   complete=cat("complete"))


def build_matrix(panel: Panel, params: FeatureParams | None = None
                 ) -> tuple[tuple[str, ...], np.ndarray]:
    """Matriz (n, k) de variables y sus nombres. NaN donde falta historia."""
    p = params or FeatureParams()
    lv = min(p.levels, panel.levels)
    scaled = book.ofi_scaled(panel.ofi[:, :lv], panel.bid_q, panel.ask_q)
    cols: list[tuple[str, np.ndarray]] = [
        ("tilt_bps", book.tilt_bps(panel.bid_p[:, 0], panel.bid_q[:, 0],
                                   panel.ask_p[:, 0], panel.ask_q[:, 0])),
        ("spread_bps", book.relative_spread_bps(panel.bid_p[:, 0], panel.ask_p[:, 0])),
        ("depth_imb", book.depth_imbalance(panel.bid_q, panel.ask_q,
                                           min(p.depth_levels, panel.levels))),
    ]
    deep = scaled.sum(axis=1)
    for w in p.ofi_windows:
        cols.append((f"ofi_top_{w}", trailing_sum(scaled[:, 0], w)))
        cols.append((f"ofi_all_{w}", trailing_sum(deep, w)))
    for w in p.flow_windows:
        cols.append((f"flow_imb_{w}", flow.trade_imbalance(panel.buy_v, panel.sell_v, w)))
    ret = vol.log_returns(panel.mid)
    cols += [
        ("intensity", flow.arrival_intensity(panel.n_trades, p.intensity_window, p.intensity_ref)),
        ("rv_bps", vol.realized_vol_bps(ret, p.rv_window)),
        ("jump_share", vol.jump_share(ret, p.rv_window)),
        ("vpin", flow.vpin(panel.buy_v, panel.sell_v, p.vpin_bucket, p.vpin_buckets)),
    ]
    names = tuple(n for n, _ in cols)
    x = np.column_stack([c for _, c in cols]) if cols else np.empty((len(panel), 0))
    return names, x


def contiguous_history(t: np.ndarray, step_ms: int, buckets: int) -> np.ndarray:
    """Filas cuyos `buckets` cubos anteriores son contiguos (ningún hueco de captura dentro).

    Sin esto, una ventana hacia atrás que cruza una hora no capturada mezclaría datos de antes y
    después del hueco como si fueran seguidos.
    """
    tt = np.asarray(t, dtype=np.int64)
    n = tt.shape[0]
    ok = np.zeros(n, bool)
    if buckets < 1 or n <= buckets:
        return ok
    ok[buckets:] = (tt[buckets:] - tt[:n - buckets]) == buckets * step_ms
    return ok


def valid_rows(x: np.ndarray, complete: np.ndarray | None = None, t: np.ndarray | None = None,
               step_ms: int = 1000, history: int = 0) -> np.ndarray:
    """Filas con todas las variables finitas, el cubo completo y la historia contigua."""
    ok = np.isfinite(x).all(axis=1)
    if complete is not None:
        ok &= np.asarray(complete, bool)
    if t is not None and history:
        ok &= contiguous_history(t, step_ms, history)
    return ok
