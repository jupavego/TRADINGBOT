"""Panel sintético para los tests de T80 (sin red, sin disco)."""

from __future__ import annotations

import numpy as np

from eim.hft.features.matrix import Panel

STEP_MS = 1000
T0 = 1_800_000_000_000


def panel(n: int = 3000, levels: int = 5, seed: int = 0, signal: float = 0.0,
          tick: float = 0.1) -> Panel:
    """Panel de `n` cubos de 1 s. Con `signal` > 0 el OFI del mejor nivel predice el retorno
    de DOS cubos después, que es lo que se puede capturar con 1 s de reacción (señal plantada:
    sirve para comprobar que el marco la encuentra)."""
    rng = np.random.default_rng(seed)
    ofi1 = rng.normal(0, 1, n)
    step = rng.normal(0, 2.0, n) + signal * np.concatenate([[0.0, 0.0], ofi1[:-2]])
    mid = 100_000 + np.cumsum(step)
    bid = np.round((mid - tick / 2) / tick) * tick
    bid_p = np.column_stack([bid - k * tick for k in range(levels)])
    ask_p = np.column_stack([bid + (k + 1) * tick for k in range(levels)])
    bid_q = np.abs(rng.normal(3, 1, (n, levels))) + 0.1
    ask_q = np.abs(rng.normal(3, 1, (n, levels))) + 0.1
    ofi = np.column_stack([ofi1] + [rng.normal(0, 1, n) for _ in range(levels - 1)])
    buy = np.abs(rng.normal(2, 1, n))
    sell = np.abs(rng.normal(2, 1, n))
    return Panel(t=T0 + (np.arange(n) + 1) * STEP_MS, bid_p=bid_p, bid_q=bid_q, ask_p=ask_p,
                 ask_q=ask_q, ofi=ofi, buy_v=buy, sell_v=sell,
                 n_trades=rng.integers(1, 30, n).astype(float),
                 complete=np.ones(n, bool), step_ms=STEP_MS)


def scramble_after(p: Panel, k: int, seed: int = 99) -> Panel:
    """El mismo panel con TODO lo posterior a la fila `k` cambiado (prueba de look-ahead)."""
    rng = np.random.default_rng(seed)
    out = panel(len(p), p.levels, seed=seed)
    sel = slice(k + 1, None)
    bid_p, bid_q = p.bid_p.copy(), p.bid_q.copy()
    ask_p, ask_q, ofi = p.ask_p.copy(), p.ask_q.copy(), p.ofi.copy()
    buy, sell, nt = p.buy_v.copy(), p.sell_v.copy(), p.n_trades.copy()
    bid_p[sel], bid_q[sel] = out.bid_p[sel], out.bid_q[sel]
    ask_p[sel], ask_q[sel] = out.ask_p[sel], out.ask_q[sel]
    ofi[sel] = out.ofi[sel]
    buy[sel], sell[sel] = out.buy_v[sel] * 7, out.sell_v[sel] * 3
    nt[sel] = rng.integers(50, 90, len(p) - k - 1)
    return Panel(t=p.t, bid_p=bid_p, bid_q=bid_q, ask_p=ask_p, ask_q=ask_q, ofi=ofi,
                 buy_v=buy, sell_v=sell, n_trades=nt, complete=p.complete, step_ms=p.step_ms)
