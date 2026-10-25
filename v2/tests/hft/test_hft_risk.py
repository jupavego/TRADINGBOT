"""T83 · Riesgo HFT: configuración versionada, cada regla, el camino que reduce, sello y coste."""

from __future__ import annotations

import json
import re

import pytest
from pydantic import ValidationError

from eim.core import Mode
from eim.risk.hft_config import HftRiskConfig, load_hft_config
from eim.risk.hft_models import HftDecision, hft_client_id
from tests.hft.hft_helpers import ASK, BID, CFG, T0, account, engine, market, order
from tests.perf import measure


# --- configuración ---------------------------------------------------------------------------
def test_config_is_versioned_frozen_and_hashed():
    assert CFG.version == "hft_risk_v1" and re.fullmatch(r"[0-9a-f]{64}", CFG.sha256)
    assert CFG.allowed_modes == ("SIMULADO", "TESTNET") and CFG.symbols == ("BTCUSDT",)
    assert CFG.decision_budget_ms == pytest.approx(6.2)
    with pytest.raises(ValidationError, match="frozen"):
        CFG.max_order_qty = 1.0                                   # inmutable


def _raw() -> dict:
    return {k: v for k, v in CFG.model_dump().items() if k != "sha256"}


@pytest.mark.parametrize("change, match", [
    ({"allowed_modes": ["REAL"]}, "nunca REAL"),
    ({"allowed_modes": ["ANALISIS"]}, "nunca REAL"),
    ({"max_orders_10s": 200}, "órdenes/10 s"),                    # > 50 % de 300
    ({"max_cancels_60s": 700}, "cancelaciones/min"),
    ({"max_order_qty": 0.5}, "max_order_qty"),
    ({"max_order_notional": 10.0}, "ninguna orden cabría"),
])
def test_config_rejects_incoherent_limits(change, match):
    with pytest.raises(ValueError, match=match):
        HftRiskConfig(**{**_raw(), **change})


def test_config_file_name_must_match_version(tmp_path):
    p = tmp_path / "hft_risk_v9.json"
    p.write_text(json.dumps(_raw()), encoding="utf-8")
    with pytest.raises(ValueError, match="no coincide"):
        load_hft_config(p)


# --- aprobación y vetos ------------------------------------------------------------------------
def test_a_good_quote_is_approved_sealed_and_names_no_rule():
    sink: list[HftDecision] = []
    d = engine(sink).evaluate(order(), market(), account(), T0)
    assert d.approved and d.rule == "" and d.reasons == () and sink == [d]
    assert re.fullmatch(r"[0-9a-f]{64}", d.seal) and d.client_id == hft_client_id("q1", "BTCUSDT")
    assert re.fullmatch(r"^[.A-Z:/a-z0-9_-]{1,36}$", d.client_id)
    assert {c.rule for c in d.checks} >= {
        "fuente", "caducidad", "modo", "símbolo", "orden", "límite del exchange",
        "tasa de órdenes", "kill-switch", "kill-switch HFT", "datos", "libro", "reloj",
        "hombre muerto", "flujo de usuario", "tamaño", "inventario", "exposición neta",
        "órdenes vivas", "pérdidas", "caída intradía", "enfriamiento"}
    rec = d.as_record()
    assert rec.authority == "risk.hft_engine" and rec.exit_mode == "hft_rules"
    assert rec.approved and rec.size == 0.001 and rec.seal == d.seal


LOSS = -CFG.capital_usd
CASES = [  # (orden, mercado, cuenta, regla que veta)
    (dict(), dict(age=1_500), dict(), "datos"),
    (dict(), dict(synced=False, issue="hueco de pu"), dict(), "libro"),
    (dict(), dict(offset=800.0), dict(), "reloj"),
    (dict(), dict(offset=None), dict(), "reloj"),
    (dict(), dict(), dict(heartbeat_t=T0 - 3_500), "hombre muerto"),
    (dict(), dict(), dict(user_stream_ok=False), "flujo de usuario"),
    (dict(qty=0.006), dict(), dict(), "tamaño"),                     # > 0,005
    (dict(), dict(bid=40_000.0, ask=40_000.1), dict(), "orden"),     # precio lejos del mid
    (dict(price=40_000.0), dict(bid=40_000.0, ask=40_000.1), dict(), "tamaño"),  # 40 < 50 USD
    (dict(), dict(), dict(position=0.0195), "inventario"),
    (dict(), dict(), dict(position=0.009, live_buy_qty=0.001), "inventario"),   # 1 100 USD
    (dict(side=-1), dict(), dict(position=0.0, live_sell_qty=0.0145), "exposición neta"),
    (dict(), dict(), dict(live_orders=6), "órdenes vivas"),
    (dict(), dict(), dict(pnl_session=0.0101 * LOSS), "pérdidas"),
    (dict(), dict(), dict(pnl_hour=0.006 * LOSS), "pérdidas"),
    (dict(), dict(), dict(drawdown_day=11.0), "caída intradía"),
    (dict(), dict(), dict(consecutive_losses=6, last_loss_t=T0 - 1_000), "enfriamiento"),
    (dict(), dict(), dict(orders_10s=100), "tasa de órdenes"),
    (dict(), dict(), dict(orders_60s=400), "tasa de órdenes"),
    (dict(), dict(), dict(rate_limited_until=T0 + 900), "límite del exchange"),
    (dict(), dict(), dict(banned=True), "límite del exchange"),
    (dict(price=ASK), dict(), dict(), "orden"),                      # post-only que cruzaría
    (dict(side=-1, price=BID), dict(), dict(), "orden"),
    (dict(purpose="take", tif="GTX"), dict(), dict(), "orden"),      # tomar exige IOC
    (dict(kind="MARKET"), dict(), dict(), "orden"),                  # a mercado solo para cerrar
    (dict(purpose="exit"), dict(), dict(), "orden"),                 # salida sin reduce-only
    (dict(now=T0 - 1_000), dict(), dict(), "caducidad"),
    (dict(source="agents.context"), dict(), dict(), "fuente"),       # LLM: solo informa
    (dict(source="desconocida"), dict(), dict(), "fuente"),
    (dict(mode=Mode.REAL), dict(), dict(), "modo"),
    (dict(symbol="ETHUSDT"), dict(), dict(), "símbolo"),
]


@pytest.mark.parametrize("o, m, a, rule", CASES)
def test_each_rule_vetoes_with_its_name(o, m, a, rule):
    d = engine().evaluate(order(**o), market(**m), account(**a), T0)
    assert not d.approved and rule in {c.rule for c in d.checks if not c.ok}, d.reasons
    assert d.rule and d.reasons and d.seal                        # el veto también se sella


def test_cooldown_ends():
    a = account(consecutive_losses=6, last_loss_t=T0 - CFG.cooldown_ms - 1)
    assert engine().evaluate(order(), market(), a, T0).approved


@pytest.mark.parametrize("kill", ["global", "lane"])
def test_kill_switches_veto_new_exposure(kill):
    eng = engine()
    (eng.kill_switch if kill == "global" else eng.lane_kill).activate("prueba", T0)
    d = eng.evaluate(order(), market(), account(), T0)
    assert not d.approved and d.rule == ("kill-switch" if kill == "global" else "kill-switch HFT")


# --- el camino que reduce ------------------------------------------------------------------
def _flatten(qty: float = 0.003) -> dict:
    return dict(side=-1, qty=qty, kind="MARKET", price=None, purpose="flatten", reduce_only=True)


def test_reducing_order_passes_kill_switch_stale_book_and_clock():
    eng = engine()
    eng.kill_switch.activate("prueba", T0)
    eng.lane_kill.activate("prueba", T0)
    d = eng.evaluate(order(**_flatten()), market(age=9_000, synced=False, offset=None),
                     account(position=0.003, heartbeat_t=None, user_stream_ok=False), T0)
    assert d.approved and d.reducing and any(c.rule == "reduce" for c in d.checks)
    eng.verify_hft(d, T0)                                         # pasa aunque haya kill-switch


@pytest.mark.parametrize("pos, qty", [(0.003, 0.004), (-0.003, 0.003), (0.0, 0.001)])
def test_reduce_only_that_does_not_reduce_is_vetoed(pos, qty):
    d = engine().evaluate(order(**_flatten(qty)), market(), account(position=pos), T0)
    assert not d.approved and d.rule == "reduce"


def test_reducing_orders_still_respect_the_exchange_limits():
    a = account(position=0.003, orders_10s=270)                   # 90 % de 300
    d = engine().evaluate(order(**_flatten()), market(), a, T0)
    assert not d.approved and d.rule == "tasa de órdenes"
    a = account(position=0.003, rate_limited_until=T0 + 5_000)
    assert engine().evaluate(order(**_flatten()), market(), a, T0).rule == "límite del exchange"


# --- sello y vigencia -------------------------------------------------------------------------
def _approved():
    eng = engine()
    return eng, eng.evaluate(order(), market(), account(), T0)


@pytest.mark.parametrize("field, value, match", [
    ("order", None, "sello"), ("approved", False, "sello"), ("notional", 1.0, "sello"),
    ("client_id", "eih-otro", "sello"), ("seal", "0" * 64, "sello")])
def test_tampered_decisions_are_rejected(field, value, match):
    eng, d = _approved()
    if field == "order":
        value = d.order.model_copy(update={"qty": 0.005})
    with pytest.raises(PermissionError, match=match):
        eng.verify_hft(d.model_copy(update={field: value}), T0)


def test_vetoed_other_config_and_expired_decisions_are_rejected():
    eng, d = _approved()
    eng.verify_hft(d, T0 + CFG.decision_ttl_ms)
    for t in (T0 + CFG.decision_ttl_ms + 1, T0 - 1):
        with pytest.raises(PermissionError, match="caducada"):
            eng.verify_hft(d, t)
    other = type(eng)(CFG.model_copy(update={"sha256": "otro"}), None, eng.kill_switch,
                      eng.lane_kill)
    with pytest.raises(PermissionError, match="configuración"):
        other.verify_hft(d, T0)
    veto = eng.evaluate(order(qty=0.006), market(), account(), T0)
    with pytest.raises(PermissionError, match="vetada"):
        eng.verify_hft(veto, T0)


def test_kill_switch_after_approval_blocks_the_send():
    eng, d = _approved()
    eng.lane_kill.activate("divergencia", T0)
    with pytest.raises(PermissionError, match="kill-switch"):
        eng.verify_hft(d, T0)


# --- coste de la decisión (presupuesto de T77) ---------------------------------------------
@pytest.mark.perf
def test_decision_cost_p99_fits_the_latency_budget_fraction():
    """Decidir + verificar una orden, p99 ≤ 2 % de los 310 ms p99 del presupuesto de T77."""
    eng, m = engine(), market()
    cases = iter([(account(position=0.002 * (i % 3), live_orders=i % 4, orders_10s=i % 50),
                   order(i=f"q{i}", side=1 if i % 2 else -1)) for i in range(2_001)])

    def decide():
        a, o = next(cases)
        d = eng.evaluate(o, m, a, T0)
        if d.approved:
            eng.verify_hft(d, T0)

    lat = measure(decide, samples=2_000)                    # la primera, de calentamiento
    assert lat.ms(0.99) <= CFG.decision_budget_ms, (
        f"{lat.describe()} > {CFG.decision_budget_ms} ms")
