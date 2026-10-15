"""Tipos base de las estrategias en papel: `Draft` (lo que propone una estrategia), `Idea` (la
propuesta fechada y lista para simular) y `StrategyInfo` (ficha del catálogo)."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

HOUR_MS = 3_600_000


@dataclass(frozen=True)
class Draft:
    """Propuesta de una estrategia en la vela de contexto. Precios absolutos."""

    side: int                    # +1 largo, −1 corto
    sl: float
    tp: float
    conf: float                  # 0..1 (lo usa el filtro de cada perfil)
    why: tuple[str, ...]
    kind: str = "market"         # market | limit
    entry: float | None = None   # obligatorio en límite; en mercado, el cierre de referencia
    fill_h: float = 0.0          # vigencia de la orden límite (horas)
    hold_h: float = 24.0         # tiempo máximo con la posición abierta (horas)
    key: str = ""                # identidad para no repetir la misma propuesta (p. ej. el plan)


@dataclass(frozen=True)
class Idea:
    """Propuesta fechada: se decide con datos hasta `t` (cierre de la vela) y se ejecuta después."""

    id: str
    strategy: str
    family: str
    symbol: str
    t: int
    side: int
    kind: str
    entry: float
    sl: float
    tp: float
    fill_ms: int
    hold_ms: int
    conf: float
    why: tuple[str, ...]
    key: str = ""
    syn_bias: float = 0.0
    regime: str | None = None
    origin: str = "backtest"     # backtest (reconstruida) | vivo (decidida en tiempo real)

    @property
    def rr(self) -> float:
        risk = abs(self.entry - self.sl)
        return abs(self.tp - self.entry) / risk if risk > 0 else 0.0

    def to_json(self) -> dict:
        return {"id": self.id, "strategy": self.strategy, "family": self.family,
                "symbol": self.symbol, "t": self.t, "side": self.side, "kind": self.kind,
                "entry": self.entry, "sl": self.sl, "tp": self.tp, "fill_ms": self.fill_ms,
                "hold_ms": self.hold_ms, "conf": self.conf, "rr": self.rr, "why": list(self.why),
                "syn_bias": self.syn_bias, "regime": self.regime, "origin": self.origin}


Fn = Callable[[dict, object, int], "Draft | None"]


@dataclass(frozen=True)
class StrategyInfo:
    id: str
    name: str
    family: str
    description: str
    fn: Fn = field(repr=False, compare=False)

    def to_json(self) -> dict:
        return {"id": self.id, "name": self.name, "family": self.family,
                "description": self.description}


def sign(x: float) -> int:
    return 1 if x > 0 else -1 if x < 0 else 0


def finite(*xs: float | None) -> bool:
    return all(x is not None and math.isfinite(x) for x in xs)


def atr_draft(side: int, ctx: dict, sl_k: float, tp_k: float, conf: float,
              why: tuple[str, ...], hold_h: float = 24.0, key: str = "") -> Draft | None:
    """Entrada a mercado con SL y TP a `sl_k` y `tp_k` ATR del cierre."""
    c, a = ctx.get("close"), ctx.get("atr")
    if side == 0 or not finite(c, a) or a <= 0:
        return None
    return Draft(side=side, sl=c - side * sl_k * a, tp=c + side * tp_k * a, conf=conf,
                 why=why + (f"SL {sl_k:g} ATR · TP {tp_k:g} ATR",), entry=c, hold_h=hold_h,
                 key=key)


def to_idea(info: StrategyInfo, d: Draft, ctx: dict, symbol: str, origin: str) -> Idea | None:
    entry = d.entry if d.entry is not None else ctx.get("close")
    if not finite(entry, d.sl, d.tp) or entry <= 0:
        return None
    if (entry - d.sl) * d.side <= 0 or (d.tp - entry) * d.side <= 0:
        return None                      # geometría imposible: SL y TP del lado correcto
    syn = ctx.get("syn") or {}
    return Idea(
        id=f"{symbol}:{ctx['t']}:{info.id}", strategy=info.id, family=info.family,
        symbol=symbol, t=int(ctx["t"]), side=d.side, kind=d.kind, entry=float(entry),
        sl=float(d.sl), tp=float(d.tp), fill_ms=int(d.fill_h * HOUR_MS) if d.kind == "limit" else 0,
        hold_ms=int(d.hold_h * HOUR_MS), conf=max(0.0, min(1.0, float(d.conf))), why=d.why,
        key=d.key, syn_bias=float(syn.get("bias") or 0.0), regime=ctx.get("regime"),
        origin=origin)
