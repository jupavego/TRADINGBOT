"""Ningún camino llega a ejecución sin el motor de riesgo.

1. Comportamiento: la única puerta (`OrderGateway`) rechaza decisiones fabricadas, alteradas,
   vetadas, caducadas, de otra configuración o con el kill-switch activo.
2. Estático: ningún módulo de `eim/` contiene llamadas de envío de órdenes ni peticiones
   firmadas a un exchange; un `Broker` solo se invoca desde `execution/gateway.py`.
"""

import re
from pathlib import Path

import pytest

from eim.core import Mode
from eim.execution.gateway import OrderGateway, OrderIntent
from eim.risk import RiskDecision, RiskEngine
from eim.risk.engine import DECISION_TTL_MS
from tests.risk.helpers import CFG, NOW, account, engine, market, plan

EIM = Path(__file__).resolve().parents[2] / "eim"


class FakeBroker:
    mode = Mode.SIMULADO

    def __init__(self) -> None:
        self.sent: list[OrderIntent] = []

    def place(self, order: OrderIntent) -> str:
        self.sent.append(order)
        return f"sim-{len(self.sent)}"


def _setup():
    eng, sink, ks = engine()
    broker = FakeBroker()
    return eng, ks, broker, OrderGateway(eng, broker)


def test_approved_decision_reaches_broker():
    eng, _, broker, gw = _setup()
    d = eng.evaluate(plan(), account(), market())
    assert gw.submit(d, NOW) == "sim-1"
    o = broker.sent[0]
    assert (o.symbol, o.side, o.size, o.leverage) == (d.symbol, d.side, d.size, d.leverage)


def test_vetoed_decision_rejected():
    eng, _, broker, gw = _setup()
    d = eng.evaluate(plan(rr=0.5), account(), market())
    with pytest.raises(PermissionError, match="vetado"):
        gw.submit(d, NOW)
    assert broker.sent == []


def test_fabricated_decision_rejected():
    _, _, broker, gw = _setup()
    fake = RiskDecision(approved=True, symbol="BTCUSDT", timeframe="1h", plan_id="x", side=1,
                        mode=Mode.SIMULADO, asof=NOW, decided_at=NOW, size=10.0,
                        leverage=3.0, config_version=CFG.version, config_sha256=CFG.sha256,
                        account_source="yo", seal="0" * 64)
    with pytest.raises(PermissionError, match="sello"):
        gw.submit(fake, NOW)
    assert broker.sent == []


def test_tampered_decision_rejected():
    eng, _, broker, gw = _setup()
    d = eng.evaluate(plan(), account(), market())
    bigger = d.model_copy(update={"size": d.size * 10})
    with pytest.raises(PermissionError, match="sello"):
        gw.submit(bigger, NOW)
    assert broker.sent == []


def test_other_config_rejected():
    eng, _, _, _ = _setup()
    d = eng.evaluate(plan(), account(), market())
    other = RiskEngine(CFG.model_copy(update={"sha256": "otro"}), lambda _: None, eng.kill_switch)
    with pytest.raises(PermissionError, match="configuración"):
        OrderGateway(other, FakeBroker()).submit(d, NOW)


def test_kill_switch_after_approval_blocks():
    eng, ks, broker, gw = _setup()
    d = eng.evaluate(plan(), account(), market())
    ks.activate("desconexión", NOW)
    with pytest.raises(PermissionError, match="kill-switch"):
        gw.submit(d, NOW)
    assert broker.sent == []


@pytest.mark.parametrize("dt", [DECISION_TTL_MS + 1, -1])
def test_stale_or_future_decision_rejected(dt):
    eng, _, broker, gw = _setup()
    d = eng.evaluate(plan(), account(), market())
    with pytest.raises(PermissionError, match="caducada"):
        gw.submit(d, NOW + dt)


def test_mode_mismatch_rejected():
    eng, _, _, gw = _setup()
    d = eng.evaluate(plan(mode=Mode.TESTNET), account(), market())
    with pytest.raises(PermissionError, match="modo"):
        gw.submit(d, NOW)


# --- análisis estático -------------------------------------------------------
ORDER_PATTERNS = [
    r"/fapi/v\d/order", r"/fapi/v\d/batchOrders", r"/fapi/v\d/leverage", r"/api/v\d/order",
    r"X-MBX-APIKEY", r"signature=", r"create_order", r"new_order", r"place_order",
    r'"type"\s*:\s*"order"',           # acción de órdenes del endpoint /exchange de Hyperliquid
]
GATEWAY = EIM / "execution" / "gateway.py"


def _sources():
    return [p for p in EIM.rglob("*.py") if "web" not in p.relative_to(EIM).parts]


def test_no_order_endpoints_anywhere():
    hits = []
    for p in _sources():
        text = p.read_text(encoding="utf-8")
        hits += [f"{p.relative_to(EIM)}: {pat}" for pat in ORDER_PATTERNS
                 if re.search(pat, text)]
    assert hits == []


def test_broker_place_only_called_by_gateway():
    callers = [p.relative_to(EIM) for p in _sources()
               if p != GATEWAY and re.search(r"\.place\(", p.read_text(encoding="utf-8"))]
    assert callers == []


def test_gateway_verifies_before_placing():
    text = GATEWAY.read_text(encoding="utf-8")
    assert text.index("self._engine.verify(") < text.index("self._broker.place(")
