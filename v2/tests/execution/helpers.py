"""Montaje común: exchange simulado + broker de testnet + servicio + puerta de riesgo."""

from __future__ import annotations

from dataclasses import dataclass

from eim.core import Mode
from eim.execution.binance_testnet import BinanceTestnetBroker, Credentials
from eim.execution.gateway import OrderGateway
from eim.execution.reconcile import Reconciler
from eim.execution.service import ExecutionService
from eim.execution.sim_broker import SimBroker
from eim.risk import KillSwitch, RiskDecision, RiskEngine
from tests.execution.fake_binance import KEY, SECRET, FakeBinance
from tests.risk.helpers import CFG, NOW, account, decide, engine, market, plan

SYM = "BTCUSDT"
PX = 100_000.0


@dataclass
class Rig:
    fx: FakeBinance
    broker: BinanceTestnetBroker
    svc: ExecutionService
    gw: OrderGateway
    eng: RiskEngine
    ks: KillSwitch
    recon: Reconciler

    def decision(self, **kw) -> RiskDecision:
        return decide(self.eng, plan(mode=Mode.TESTNET, **kw), account(), market(last_price=PX))

    def open(self, entry_kind: str = "MARKET", **kw) -> str:
        return self.gw.submit(self.decision(**kw), NOW, entry_kind)

    def orders(self) -> list:
        return self.fx.sim.open_orders(SYM)

    def pos(self) -> float:
        return self.fx.sim.position(SYM).qty


def rig(fill_cap: float | None = None) -> Rig:
    fx = FakeBinance(SimBroker(fill_cap=fill_cap))
    fx.sim.set_price(SYM, PX)
    broker = BinanceTestnetBroker(Credentials(KEY, SECRET), client=fx.client(),
                                  clock=lambda: NOW)
    eng, _, ks = engine()
    svc = ExecutionService(broker, ks, sleep=lambda _: None, clock=lambda: NOW)
    return Rig(fx, broker, svc, OrderGateway(eng, svc), eng, ks, Reconciler(svc, CFG))
