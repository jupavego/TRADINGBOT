"""Completa los contextos del bróker con `lit` sin regenerar los agentes (T54).

El agente `literature` es puro sobre el snapshot: se recalcula con las `AGENT_BARS` velas cerradas
hasta `asof` (igual que `CtxGenerator`) y se fusiona en el contexto guardado; el resto del contexto
no se toca. Los contextos nuevos ya traen `lit` (`paper/context.py`, `CTX_VERSION` 2).
"""

from __future__ import annotations

from collections.abc import Callable

from eim.agents.literature.agent import LiteratureAgent
from eim.core import Candle, MarketSnapshot
from eim.data.paper_store import PaperStore
from eim.data.store import Store
from eim.data.timeframes import tf_ms
from eim.paper.context import CTX_VERSION, lit_summary
from eim.paper.generate import AGENT_BARS, now_ms


def lit_for(candles: list[Candle], i: int, symbol: str, tf: str, asof: int,
            agent: LiteratureAgent) -> dict | None:
    """`lit` de la vela de índice `i` (cerró en `asof`): usa solo candles[:i + 1]."""
    win = candles[max(0, i + 1 - AGENT_BARS):i + 1]
    if len(win) < AGENT_BARS // 2 or win[-1].t + tf_ms(tf) != asof:
        return None
    snap = MarketSnapshot(symbol=symbol, timeframe=tf, candles=win, asof=asof, sources={},
                          coverage={})
    return lit_summary(agent.run(snap))


def complete(store: Store, pstore: PaperStore, symbol: str, tf: str,
             progress: Callable[[int, int], None] | None = None) -> dict:
    """Añade `lit` a los contextos de (símbolo, marco) que aún no lo tienen. Devuelve el conteo."""
    ctxs = [c for c in pstore.load(symbol, tf) if "lit" not in c]
    if not ctxs:
        return {"symbol": symbol, "timeframe": tf, "completed": 0, "skipped": 0}
    candles = store.read_candles(symbol, tf)
    at = {c.t: k for k, c in enumerate(candles)}
    agent, bar, done, skipped = LiteratureAgent(), tf_ms(tf), 0, 0
    for n, ctx in enumerate(ctxs, 1):
        asof = int(ctx["t"])
        i = at.get(asof - bar, -1)
        lit = lit_for(candles, i, symbol, tf, asof, agent) if i >= 0 else None
        if lit is None and i < 0:
            skipped += 1                      # sin la vela de decisión en el almacén
        else:
            origin = ctx.pop("origin", "backtest")
            pstore.save(symbol, tf, {**ctx, "lit": lit, "v": CTX_VERSION}, origin, now_ms())
            done += 1
        if progress:
            progress(n, len(ctxs))
    return {"symbol": symbol, "timeframe": tf, "completed": done, "skipped": skipped}
