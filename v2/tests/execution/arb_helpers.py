"""Montaje común del arbitraje (T45): exchanges simulados con libro + brokers de testnet reales +
ejecutor, motor de riesgo, puerta y reconciliación."""

from __future__ import annotations

from dataclasses import dataclass, field

from eim.core import Mode
from eim.execution.arb_book import ArbPosition
from eim.execution.arb_executor import ArbExecutor
from eim.execution.arb_legs import ExecParams
from eim.execution.arb_recon import ArbReconciler
from eim.execution.binance_rest import Credentials
from eim.execution.binance_spot_testnet import BinanceSpotTestnetBroker
from eim.execution.binance_testnet import BinanceTestnetBroker
from eim.execution.gateway import ArbGateway
from eim.risk import KillSwitch
from eim.risk.arb_config import load_arb_config
from eim.risk.arb_engine import ArbRiskEngine
from eim.risk.arb_models import ArbAccount, ArbDecision, ArbLegPlan, ArbPlan
from tests.execution.fake_binance import KEY, SECRET
from tests.execution.fake_venue import FakeHTTP, Venue

SPOT, PERP, QTR = "BTCUSDT", "BTCUSDT", "BTCUSDT_261225"
NOW = 1_792_080_000_000
CFG = load_arb_config()


class Clock:
    """Reloj de prueba: `sleep` lo avanza (las esperas de las patas no bloquean)."""

    def __init__(self, t: int) -> None:
        self.t = t

    def __call__(self) -> int:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += int(s * 1000)


@dataclass
class ArbRig:
    sv: Venue
    fv: Venue
    sh: FakeHTTP
    fh: FakeHTTP
    spot: BinanceSpotTestnetBroker
    fut: BinanceTestnetBroker
    ex: ArbExecutor
    kill: KillSwitch
    clock: Clock
    engine: ArbRiskEngine
    gw: ArbGateway
    recon: ArbReconciler
    decisions: list[ArbDecision] = field(default_factory=list)
    journal: list[tuple[str, dict]] = field(default_factory=list)
    saved: list[dict] = field(default_factory=list)

    def plan(self, qty: float = 0.01, fut: str = PERP, strategy: str = "funding_carry",
             **kw) -> ArbPlan:
        now = self.clock()
        s_px, f_px = self.sv.mids[SPOT], self.fv.mids[fut]
        base = dict(
            arb_id=f"{strategy}|test|BTC|{fut}|{now}", strategy=strategy,
            variant="largo spot / corto perpetuo", asset="BTC",
            legs=(ArbLegPlan(market="usdm", symbol=fut, side=-1, ref_price=f_px,
                             depth_frac=0.2),
                  ArbLegPlan(market="spot", symbol=SPOT, side=1, ref_price=s_px,
                             depth_frac=0.02)),
            qty=qty, notional=qty * s_px, leverage=3, net_edge=10.0, net_bps=100.0,
            score=1.0, horizon_h=2160.0, funding_rate=1e-4, interval_h=8.0,
            exit_cost_bps=15.0, asof=now, valid_until=now + 15_000, source="test",
            mode=Mode.TESTNET)
        base.update(kw)
        return ArbPlan(**base)

    def account(self, **kw) -> ArbAccount:
        base = dict(equity=100_000.0, day_start_equity=100_000.0, futures_equity=20_000.0,
                    futures_available=20_000.0, spot_quote_free=50_000.0, initial_margin=0.0,
                    gross_exposure=0.0, source="test")
        base.update(kw)
        return ArbAccount(**base)

    def decision(self, plan: ArbPlan | None = None, **kw) -> ArbDecision:
        plan = plan or self.plan(**kw)
        return self.engine.evaluate(plan, self.account(), self.clock(),
                                    proposal=plan.as_proposal("arb.scanner", "test"))

    def open(self, plan: ArbPlan | None = None, **kw) -> ArbPosition:
        key = self.gw.submit(self.decision(plan, **kw), self.clock())
        return self.ex.positions[key]

    def btc(self) -> float:
        """BTC spot ganados/perdidos frente al saldo inicial (1 BTC)."""
        return round(self.sv.balances["BTC"] - 1.0, 10)

    def short(self, sym: str = PERP) -> float:
        return self.fv.pos.get(sym, [0.0])[0]

    def net(self, sym: str = PERP) -> float:
        """Exposición neta real en el exchange (spot ganado + futuros de `sym`)."""
        return round(self.btc() + self.short(sym), 8)

    def net_all(self) -> float:
        """Exposición neta de toda la cuenta (spot ganado + todos los futuros)."""
        return round(self.btc() + sum(q for q, _, _ in self.fv.pos.values()), 8)


def arb_rig(spot_mid: float = 100_000.0, fut_mid: float = 100_050.0,
            qtr_mid: float = 101_500.0, params: ExecParams | None = None,
            fee_rate: float = 0.0, fee_in_base: bool = False) -> ArbRig:
    sv = Venue({SPOT: spot_mid}, futures=False, step=0.00001, tick=0.01, fee_rate=fee_rate,
               fee_in_base=fee_in_base)
    fv = Venue({PERP: fut_mid, QTR: qtr_mid}, futures=True, step=0.001, tick=0.1)
    sh, fh = FakeHTTP(sv), FakeHTTP(fv)
    clock = Clock(NOW)
    spot = BinanceSpotTestnetBroker(Credentials(KEY, SECRET), client=sh.client(), clock=clock)
    fut = BinanceTestnetBroker(Credentials(KEY, SECRET), client=fh.client(), clock=clock)
    kill = KillSwitch()
    rig = ArbRig(sv, fv, sh, fh, spot, fut, None, kill, clock, None, None, None)  # type: ignore
    rig.ex = ArbExecutor(spot, fut, kill, params or ExecParams(), sleep=clock.sleep, clock=clock,
                         save=rig.saved.append, journal=lambda k, d: rig.journal.append((k, d)))
    rig.engine = ArbRiskEngine(CFG, rig.decisions.append, kill)
    rig.gw = ArbGateway(rig.engine, rig.ex)
    rig.recon = ArbReconciler(rig.ex, CFG)
    return rig
