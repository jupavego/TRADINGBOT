"""Andamiaje del carril HFT (T83) sin red: SimBroker + flujo de usuario simulado + reloj fijo."""

from __future__ import annotations

from dataclasses import dataclass, field

from eim.core import Mode
from eim.execution.hft_executor import HftExecutor
from eim.execution.hft_lane import HftLane
from eim.execution.hft_ledger import HftLedger
from eim.execution.sim_broker import SimBroker
from eim.execution.user_stream import SimUserStream
from eim.risk.hft_config import HftRiskConfig, load_hft_config
from eim.risk.hft_engine import HftRiskEngine
from eim.risk.hft_models import HftAccount, HftDecision, HftMarket, HftOrder
from eim.risk.killswitch import KillSwitch

T0 = 1_761_300_000_000
SYM = "BTCUSDT"
CFG = load_hft_config()
BID, ASK = 100_000.0, 100_000.1


class Clock:
    def __init__(self, t: int = T0) -> None:
        self.t = t

    def __call__(self) -> int:
        return self.t

    def advance(self, ms: int) -> int:
        self.t += ms
        return self.t


def market(now: int = T0, bid: float = BID, ask: float = ASK, age: int = 100,
           synced: bool = True, offset: float | None = 5.0, issue: str = "") -> HftMarket:
    return HftMarket(SYM, bid, ask, now - age, now - age, synced, offset, issue, "prueba")


def order(i: str = "q1", side: int = 1, qty: float = 0.001, price: float | None = None,
          purpose: str = "quote", tif: str = "GTX", kind: str = "LIMIT",
          reduce_only: bool = False, now: int = T0, mode: Mode = Mode.SIMULADO,
          source: str = "hft.micro", symbol: str = SYM) -> HftOrder:
    if price is None and kind == "LIMIT":
        price = BID if side > 0 else ASK
    return HftOrder(order_id=i, source=source, source_version="prueba@1", symbol=symbol,
                    side=side, qty=qty, kind=kind, price=price, tif=tif,
                    reduce_only=reduce_only, purpose=purpose, mode=mode, asof=now,
                    expires_at=now + 500)


def account(now: int = T0, **kw) -> HftAccount:
    kw.setdefault("heartbeat_t", now)
    return HftAccount(source="prueba", **kw)


def engine(sink: list | None = None, cfg: HftRiskConfig = CFG) -> HftRiskEngine:
    return HftRiskEngine(cfg, (sink if sink is not None else []).append, KillSwitch(),
                         KillSwitch())


@dataclass
class Rig:
    clock: Clock
    sim: SimBroker
    stream: SimUserStream
    ledger: HftLedger
    ex: HftExecutor
    engine: HftRiskEngine
    lane: HftLane
    sink: list[HftDecision] = field(default_factory=list)

    def pump(self) -> int:
        return self.stream.pump(self.lane.on_user_events)

    def move(self, price: float) -> None:
        """El precio del simulado se mueve (casa órdenes) y llegan los eventos."""
        self.sim.set_price(SYM, price)
        self.pump()

    def mkt(self, **kw) -> HftMarket:
        return market(self.clock(), **kw)

    def submit(self, o: HftOrder, **kw) -> HftDecision:
        d = self.lane.submit(o, self.mkt(**kw), self.clock())
        self.pump()
        return d


def rig(fill_cap: float | None = None, min_notional: float = 50.0,
        sim: SimBroker | None = None, cfg: HftRiskConfig = CFG) -> Rig:
    clk = Clock()
    sim = sim or SimBroker(balance=10_000.0, fee_rate=0.0002, fill_cap=fill_cap,
                           min_notional=min_notional)
    sim.set_price(SYM, (BID + ASK) / 2)
    stream = SimUserStream(sim, clk)
    ledger = HftLedger(clk)
    ex = HftExecutor(sim, ledger, clk, backoff=0.0, sleep=lambda _s: None)
    sink: list[HftDecision] = []
    eng = engine(sink, cfg)
    lane = HftLane(eng, ex)
    lane.heartbeat(clk())
    return Rig(clk, sim, stream, ledger, ex, eng, lane, sink)
