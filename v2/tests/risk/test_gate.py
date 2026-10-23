"""Ningún camino llega a ejecución sin el motor de riesgo.

1. Comportamiento: la única puerta (`OrderGateway`) rechaza decisiones fabricadas, alteradas,
   vetadas, caducadas, de otra configuración o con el kill-switch activo.
2. Estático: solo los módulos de testnet (`execution/binance_rest.py` firma, `binance_testnet.py`
   futuros, `binance_spot_testnet.py` spot, T45) contienen endpoints de órdenes o peticiones
   firmadas (y solo hacia la testnet); el ejecutor solo se invoca (`.place(` / `.place_arb(`)
   desde `execution/gateway.py` y el broker solo recibe órdenes (`.post_order(`) desde
   `execution/service.py`.
"""

import re
from pathlib import Path

import pytest

from eim.core import Mode
from eim.execution.gateway import OrderGateway, OrderIntent
from eim.risk import RiskDecision, RiskEngine
from eim.risk.engine import DECISION_TTL_MS
from tests.risk.helpers import CFG, NOW, decide, engine, plan

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
    d = decide(eng, plan())
    assert gw.submit(d, NOW) == "sim-1"
    o = broker.sent[0]
    assert (o.symbol, o.side, o.size, o.leverage) == (d.symbol, d.side, d.size, d.leverage)


def test_vetoed_decision_rejected():
    eng, _, broker, gw = _setup()
    d = decide(eng, plan(rr=0.5))
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
    d = decide(eng, plan())
    bigger = d.model_copy(update={"size": d.size * 10})
    with pytest.raises(PermissionError, match="sello"):
        gw.submit(bigger, NOW)
    assert broker.sent == []


def test_other_config_rejected():
    eng, _, _, _ = _setup()
    d = decide(eng, plan())
    other = RiskEngine(CFG.model_copy(update={"sha256": "otro"}), lambda _: None, eng.kill_switch)
    with pytest.raises(PermissionError, match="configuración"):
        OrderGateway(other, FakeBroker()).submit(d, NOW)


def test_kill_switch_after_approval_blocks():
    eng, ks, broker, gw = _setup()
    d = decide(eng, plan())
    ks.activate("desconexión", NOW)
    with pytest.raises(PermissionError, match="kill-switch"):
        gw.submit(d, NOW)
    assert broker.sent == []


@pytest.mark.parametrize("dt", [DECISION_TTL_MS + 1, -1])
def test_stale_or_future_decision_rejected(dt):
    eng, _, broker, gw = _setup()
    d = decide(eng, plan())
    with pytest.raises(PermissionError, match="caducada"):
        gw.submit(d, NOW + dt)


def test_mode_mismatch_rejected():
    eng, _, _, gw = _setup()
    d = decide(eng, plan(mode=Mode.TESTNET))
    with pytest.raises(PermissionError, match="modo"):
        gw.submit(d, NOW)


# --- análisis estático -------------------------------------------------------
ORDER_PATTERNS = [
    r"/fapi/v\d/order", r"/fapi/v\d/batchOrders", r"/fapi/v\d/leverage", r"/api/v\d/order",
    r"X-MBX-APIKEY", r"signature=", r"create_order", r"new_order", r"place_order",
    r'"type"\s*:\s*"order"',           # acción de órdenes del endpoint /exchange de Hyperliquid
]
GATEWAY = EIM / "execution" / "gateway.py"
TESTNET = EIM / "execution" / "binance_testnet.py"
SPOT = EIM / "execution" / "binance_spot_testnet.py"
REST = EIM / "execution" / "binance_rest.py"
SERVICE = EIM / "execution" / "service.py"


def _sources():
    return [p for p in EIM.rglob("*.py") if "web" not in p.relative_to(EIM).parts]


def test_no_order_endpoints_anywhere():
    hits = []
    for p in _sources():
        if p in (TESTNET, SPOT, REST):
            continue
        text = p.read_text(encoding="utf-8")
        hits += [f"{p.relative_to(EIM)}: {pat}" for pat in ORDER_PATTERNS
                 if re.search(pat, text)]
    assert hits == []


def test_broker_place_only_called_by_gateway():
    callers = [p.relative_to(EIM) for p in _sources()
               if p != GATEWAY and re.search(r"\.place(_arb)?\(", p.read_text(encoding="utf-8"))]
    assert callers == []


def test_post_order_only_called_by_service():
    callers = [p.relative_to(EIM) for p in _sources()
               if p != SERVICE and re.search(r"\.post_order\(", p.read_text(encoding="utf-8"))]
    assert callers == []


def test_testnet_module_only_knows_testnet_hosts():
    text = TESTNET.read_text(encoding="utf-8")
    hosts = set(re.findall(r"https?://([\w.-]+)", text))
    assert hosts == {"testnet.binancefuture.com"}
    assert not re.search(r"fapi\.binance\.com|api\.binance\.com", text.replace(
        "demo-fapi.binance.com", ""))


def test_spot_and_rest_modules_only_know_testnet_hosts():
    spot = SPOT.read_text(encoding="utf-8")
    assert set(re.findall(r"https?://([\w.-]+)", spot)) == {"testnet.binance.vision"}
    assert not re.search(r"(?<![\w-])api\.binance\.com", spot.replace("demo-api.binance.com", ""))
    assert re.findall(r"https?://([\w.-]+)", REST.read_text(encoding="utf-8")) == []


def test_gateway_verifies_before_placing():
    text = GATEWAY.read_text(encoding="utf-8")
    assert text.index("self._engine.verify(") < text.index("self._broker.place(")
    assert text.index("self._engine.verify_arb(") < text.index("self._executor.place_arb(")
