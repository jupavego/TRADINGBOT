"""Montaje sin red: mercado sintético (proveedor falso), agentes stub y operación en paper."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from eim.agents.registry import AgentRegistry
from eim.api.execution import build_runtime
from eim.api.reports_db import ReportStore
from eim.api.risk import RiskDesk
from eim.core import AgentReport, Candle, MarketSnapshot, Overlay
from eim.data.store import Store
from eim.data.timeframes import tf_ms
from eim.operation.cycle import OperationParams
from eim.operation.supervisor import Operation
from eim.risk import KillSwitch
from tests.risk.helpers import CFG

H = 3_600_000
Q = 900_000
SYM = "ETHUSDT"
T0 = 1_700_000_000_000 // (7 * 86_400_000) * (7 * 86_400_000)   # múltiplo de semana
START = T0 + 600 * H                     # primera hora «en vivo»


class Market:
    """Proveedor falso: velas cerradas hasta `now` desde una función de precio por tramo."""

    name = "fake"

    def __init__(self) -> None:
        self.now = START + 60_000
        self.down = False
        self.shocks: dict[int, tuple[float, float, float, float]] = {}   # t(15m) → OHLC

    def ohlc(self, t: int, step: int) -> tuple[float, float, float, float]:
        if step == Q and t in self.shocks:
            return self.shocks[t]
        return (2000.0, 2004.0, 1996.0, 2000.0)

    def klines(self, symbol: str, timeframe: str, start: int, end: int) -> list[Candle]:
        if self.down:
            raise ConnectionError("red caída (simulada)")
        step = tf_ms(timeframe)
        t = start - start % step
        out = []
        while t < end and t + step <= self.now:
            if t >= start:
                if step == H:      # la hora resume sus cuatro cuartos
                    qs = [self.ohlc(t + i * Q, Q) for i in range(4)]
                    o, h, lo, c = qs[0][0], max(x[1] for x in qs), min(x[2] for x in qs), \
                        qs[-1][3]
                else:
                    o, h, lo, c = self.ohlc(t, step)
                out.append(Candle(t=t, o=o, h=h, l=lo, c=c, v=10.0))
            t += step
        return out


class StubAgent:
    def __init__(self, agent_id: str, plan: bool = False) -> None:
        self.id, self.version, self.requires, self.plan = agent_id, "1", frozenset(), plan

    def run(self, snap: MarketSnapshot) -> AgentReport:
        kw: dict = {}
        if self.plan:
            px = snap.candles[-1].c
            geom = {"side": "long", "entry": px, "sl": px - 40, "tp": [px + 80], "rr": 2.0,
                    "mode": "ANALISIS", "status": "VIGENTE"}
            kw = {"metrics": {"plan": geom}, "overlays": [Overlay(
                id=f"plan:{snap.asof - H}", agent_id="plan", kind="trade_plan",
                t_from=snap.asof - H, geometry=geom, label="Plan", confidence=0.6)]}
        return AgentReport(agent_id=self.id, version="1", asof=snap.asof, bias=0.5,
                           confidence=0.6, horizon_bars=1, **kw)


def registry() -> AgentRegistry:
    reg = AgentRegistry()
    for a in (StubAgent("plan", plan=True), StubAgent("structure"), StubAgent("levels")):
        reg.register(a)
    return reg


@dataclass
class Rig:
    root: Path
    market: Market
    clock: dict = field(default_factory=dict)
    kill: KillSwitch = field(default_factory=KillSwitch)
    sent: list = field(default_factory=list)
    reports: ReportStore | None = None
    op: Operation | None = None

    def now(self) -> int:
        return self.market.now

    def build(self) -> Operation:
        """(Re)crea la operación sobre el mismo directorio: simula un reinicio del proceso."""
        if self.reports is not None:
            self.reports.close()
        store = Store(self.root)
        self.reports = ReportStore(self.root / "reports.duckdb")
        rt = build_runtime("paper", self.kill, CFG, clock=self.now)
        desk = RiskDesk(store, self.reports, self.now, self.kill, rt)
        params = OperationParams(symbols=(SYM,), poll_s=1.0, history_bars=700)
        self.op = Operation(store=store, provider=self.market, reports=self.reports,
                            registry=registry(), desk=desk, params=params, data_dir=self.root,
                            reports_dir=self.root / "out", edge_path=self.root / "edge.json",
                            sinks=[self.sent.append], clock=self.now)
        return self.op

    def advance(self, ms: int) -> None:
        self.market.now += ms

    def close(self) -> None:
        if self.reports is not None:
            self.reports.close()
