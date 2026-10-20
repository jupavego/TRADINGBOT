"""Posturas de bots → operaciones sombra (T59), con la mecánica y los costos del bróker (T49/T25).

Una postura NO es una orden: aquí se traduce, con una regla fija igual para todos los bots y
decidida antes de mirar ningún resultado, a una idea del bróker simulado:

- Se abre una idea a mercado en el cierre de la vela cuando la postura cambia de lado
  (|stance| ≥ `MIN_STANCE`; pasar a plano no abre nada).
- SL a `SL_ATR`·ATR y TP a `TP_R`·riesgo del cierre (la misma geometría que T44); salida por tiempo
  a `horizon_bars` del bot o, si no lo da, a `HOLD_BARS`.
- La simulación la hace `eim.paper.engine` con los costos de perpetuos de T25 (`ExecParams`):
  los `costs_assumed` del bot se IGNORAN (se guardan en la señal, nunca llegan aquí).
- **Control aleatorio** de la misma familia: los mismos instantes y la misma geometría con el lado
  sorteado (semilla fija por identidad). Es un intento más de la familia de Holm y jamás vota.
Sin anticipación: cada idea usa solo velas hasta su cierre; la salida la resuelve el camino de 15 m.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from eim.agents.levels.pivots import atr
from eim.core import BotSignal, Candle
from eim.data.timeframes import tf_ms
from eim.paper.engine import Path, run_shadow, simulate
from eim.paper.ideas import Idea
from eim.paper.params import ExecParams
from eim.validation.evidence import Trade, flip_idea, trade_of

MIN_STANCE = 0.2      # postura mínima para considerarse «larga» o «corta»
SL_ATR, TP_R, ATR_N = 1.5, 2.0, 14
HOLD_BARS = 24        # salida por tiempo si el bot no da horizonte
LIVE_LAG_BARS = 2     # guardada a ≤ 2 velas de su cierre = «vivo»; si no, relleno histórico
CONTROL_FAMILY = "control"

RegimeAt = Callable[[int], "str | None"]


@dataclass(frozen=True)
class BotId:
    """Identidad de lo que se puntúa: `bot@estrategia@marco@versión`."""

    bot_id: str
    strategy: str
    timeframe: str
    version: str                      # SHA del bot + hash de parámetros (T57)
    n: int = 1                        # vN en el orden en que apareció en `bot_signals`

    @property
    def sid(self) -> str:
        return f"{self.bot_id}:{self.strategy}@{self.timeframe}"

    @property
    def label(self) -> str:
        return f"{self.sid}@v{self.n}"


def identities(rows: Sequence[tuple[BotSignal, int]]) -> list[BotId]:
    """Versiones distintas de cada bot/estrategia/marco, numeradas por su primera aparición."""
    first: dict[tuple[str, str, str, str], int] = {}
    for s, _ in rows:
        k = (s.bot_id, s.strategy, s.timeframe, s.version)
        first[k] = min(first.get(k, s.asof), s.asof)
    seen: dict[tuple[str, str, str], int] = {}
    out = []
    for (b, st, tf, v), _t in sorted(first.items(), key=lambda kv: (kv[0][:3], kv[1], kv[0][3])):
        seen[(b, st, tf)] = n = seen.get((b, st, tf), 0) + 1
        out.append(BotId(b, st, tf, v, n))
    return out


def _side(s: BotSignal) -> int:
    if s.status != "ok" or abs(s.stance) < MIN_STANCE:
        return 0
    return 1 if s.stance > 0 else -1


def ideas_of(ident: BotId, sigs: Sequence[tuple[BotSignal, int]], candles: Sequence[Candle],
             symbol: str, regime_at: RegimeAt | None = None,
             control: bool = False) -> list[Idea]:
    """Ideas de una versión: una por cambio de lado; `control` sortea el lado (misma geometría)."""
    step = tf_ms(ident.timeframe)
    pos = {c.t: i for i, c in enumerate(candles)}
    h = np.array([c.h for c in candles])
    lo = np.array([c.l for c in candles])
    cl = np.array([c.c for c in candles])
    seed = int(hashlib.sha256(f"{ident.label}|control".encode()).hexdigest()[:12], 16)
    rng = random.Random(seed)
    out: list[Idea] = []
    prev = 0
    for s, created in sorted((x for x in sigs if x[0].version == ident.version),
                             key=lambda x: x[0].asof):
        side = _side(s)
        was, prev = prev, side
        if side == 0 or side == was:
            continue
        i = pos.get(s.asof - step)
        if i is None or i < ATR_N:
            continue                       # sin la vela que cierra en `asof` o sin calentamiento
        a = atr(h[:i + 1], lo[:i + 1], cl[:i + 1], ATR_N)
        close = float(cl[i])
        if not a > 0:
            continue
        if control:
            side = rng.choice((-1, 1))
        risk = SL_ATR * a
        hold = (s.horizon_bars or HOLD_BARS) * step
        out.append(Idea(
            id=f"{symbol}:{ident.timeframe}:{s.asof}:{ident.label}"
               + (":control" if control else ""),
            strategy=ident.bot_id + ":" + ident.strategy
            + ("#control" if control else ""),
            family=CONTROL_FAMILY if control else "bots", symbol=symbol, t=s.asof, side=side,
            kind="market", entry=close, sl=close - side * risk, tp=close + side * TP_R * risk,
            fill_ms=0, hold_ms=int(hold), conf=float(s.confidence or abs(s.stance)),
            why=(f"postura {s.stance:+.2f} de {ident.bot_id}/{ident.strategy}",),
            regime=regime_at(s.asof) if regime_at else None,
            origin="vivo" if created - s.asof <= LIVE_LAG_BARS * step else "backtest",
            timeframe=ident.timeframe, version=ident.version))
    return out


def trades_of(ideas: Sequence[Idea], path: Path, ep: ExecParams | None = None) -> list[Trade]:
    """Operaciones sombra cerradas (con el lado contrario simulado para la réplica de V3)."""
    ep = ep or ExecParams()
    out = []
    for o in run_shadow(ideas, path, ep):
        if o.status != "CERRADA":
            continue
        # ideas siempre a mercado: el precio de la decisión es la entrada
        flip = simulate(flip_idea(o.idea, o.idea.entry), path, ep)
        t = trade_of(o, flip)
        if t is not None:
            out.append(t)
    return out


def shadow_trades(ident: BotId, rows: Sequence[tuple[BotSignal, int]], candles: Sequence[Candle],
                  path: Path, symbol: str, regime_at: RegimeAt | None = None,
                  ep: ExecParams | None = None, control: bool = False) -> list[Trade]:
    return trades_of(ideas_of(ident, rows, candles, symbol, regime_at, control), path, ep)
