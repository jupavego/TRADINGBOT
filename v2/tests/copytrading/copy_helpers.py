"""Escenarios de la copia simulada (T42): sin red, deterministas.

Líder con cuenta de 1 000 000 USD y subcuenta de 10 000 → proporción 0,01. BTC a ~50 000:
4 BTC del líder = 0,04 BTC propios = 2 000 USD (20 % del capital, bajo los topes de 40 %).
"""

from __future__ import annotations

from eim.copytrading.copy_engine import CopyEngine
from eim.copytrading.copy_models import ExecQuote, Signal, group_fills
from eim.copytrading.copy_params import CopyParams, ExchangeSpec
from eim.copytrading.copy_risk import copy_config
from eim.copytrading.replicator import CoinCopy, Ctx
from tests.copytrading.helpers import LID, T0, fill

SPEC = ExchangeSpec(sz_decimals={"BTC": 5, "ETH": 4}, source="test")
AV = 1_000_000.0
P = CopyParams()


def quote(px: float, t: int, bps: float = 1.0, src: str = "bbo") -> ExecQuote:
    """Libro alrededor de `px` con medio diferencial de `bps` puntos básicos."""
    h = px * bps / 1e4
    return ExecQuote(t=t, at=t, mid=px, bid=px - h if src == "bbo" else None,
                     ask=px + h if src == "bbo" else None, src=src)


def sig(coin: str, start: float, end: float, px: float, t: int, tid: int, **kw) -> Signal:
    (s,) = group_fills([fill(coin, start, end, px, t, tid, **kw)])
    return s


def ctx(t: int, px: float | None = 50_000.0, equity: float = 10_000.0, av: float | None = AV,
        other: float = 0.0, bps: float = 1.0) -> Ctx:
    return Ctx(t=t, equity=equity, leader_av=av, quote=quote(px, t, bps) if px else None,
               other_notional=other)


def engine(alerts: list | None = None, p: CopyParams = P, **kw) -> CopyEngine:
    e = CopyEngine(LID, p, SPEC, copy_config(p), t0=T0, label="test",
                   on_alert=(lambda *a: alerts.append(a)) if alerts is not None else None, **kw)
    e.leader_av = AV
    e.confirm_feed(T0)
    e.start(T0, [])
    return e


def feed(e: CopyEngine, coin: str, start: float, end: float, px: float, t: int, tid: int,
         qpx: float | None = None, bps: float = 1.0, **kw):
    """Señal del líder vista en vivo y ejecutada a los 300 ms con el libro en `qpx`."""
    s = sig(coin, start, end, px, t, tid, **kw)
    at = s.observed_at + P.exec_delay_ms
    e.confirm_feed(s.observed_at)
    return e.on_signal(s, quote(qpx or px, at, bps), at)


def coin(**kw) -> CoinCopy:
    return CoinCopy("BTC", **kw)
