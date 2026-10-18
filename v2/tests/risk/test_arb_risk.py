"""Motor de riesgo del arbitraje (T45): vetos, tamaño contra la cuenta total y sello."""

import json

import pytest
from pydantic import ValidationError

from eim.core import Mode
from eim.risk import KillSwitch
from eim.risk.arb_config import load_arb_config
from eim.risk.arb_engine import ArbRiskEngine
from eim.risk.config import VERSIONS_DIR
from eim.risk.engine import DECISION_TTL_MS
from tests.execution.arb_helpers import CFG, PERP, arb_rig


@pytest.fixture
def r():
    return arb_rig()


def _eval(r, plan=None, **acct):
    return r.engine.evaluate(plan or r.plan(), r.account(**acct), r.clock())


def _vetoed_by(d) -> set[str]:
    return {c.rule for c in d.checks if not c.ok}


def test_approves_and_caps_at_max_notional(r):
    d = _eval(r, r.plan(qty=0.05))                           # 5 000 USD propuestos
    assert d.approved and d.qty == pytest.approx(CFG.max_notional_usd / 100_000.0)
    assert any("nocional máximo" in x for x in d.reasons)
    assert d.max_leg_loss == pytest.approx(d.notional * CFG.max_leg_loss_bps / 1e4)
    assert d.config_version == "risk_arb_v1" and d.seal and r.decisions == [d]


@pytest.mark.parametrize("plan_kw, acct, rule", [
    ({"strategy": "related_perps"}, {}, "estrategia"),
    ({"strategy": "triangular"}, {}, "estrategia"),
    ({"mode": Mode.SIMULADO}, {}, "modo"),
    ({"net_bps": 0.5}, {}, "neto"),
    ({"leverage": 5}, {}, "liquidación"),
    ({}, {"open_arbs": ("funding_carry:BTC",)}, "abiertos"),
    ({}, {"open_arbs": ("basis:BTC", "basis:ETH")}, "abiertos"),
    ({}, {"directional_symbols": (PERP,)}, "conflicto direccional"),
    ({}, {"equity": 97_000.0}, "pérdida diaria"),
])
def test_vetoes(r, plan_kw, acct, rule):
    d = _eval(r, r.plan(**plan_kw), **acct)
    assert not d.approved and rule in _vetoed_by(d) and d.qty == 0


def test_stale_or_expired_opportunity_vetoed(r):
    p = r.plan()
    r.clock.t += CFG.max_quote_age_ms + 1
    d = r.engine.evaluate(p, r.account(), r.clock())
    assert not d.approved and "vigencia" in _vetoed_by(d)


def test_short_spot_needs_borrow_and_is_out_of_scope(r):
    p = r.plan()
    legs = tuple(lg.model_copy(update={"side": -lg.side}) for lg in p.legs)
    d = _eval(r, p.model_copy(update={"legs": legs}))
    assert not d.approved and "estrategia" in _vetoed_by(d)


def test_kill_switch_vetoes(r):
    r.kill.activate("prueba", r.clock())
    assert "kill-switch" in _vetoed_by(_eval(r))


def test_total_account_margin_and_exposure_count(r):
    """El margen y la exposición del carril direccional también cuentan."""
    free = _eval(r)
    tight = _eval(r, initial_margin=CFG.max_margin_frac * 20_000.0 - 100.0)
    assert tight.approved and tight.qty < free.qty
    assert any("margen total" in x for x in tight.reasons)
    full = _eval(r, initial_margin=CFG.max_margin_frac * 20_000.0)
    assert not full.approved and "tamaño" in _vetoed_by(full)
    gross = _eval(r, gross_exposure=CFG.max_gross_frac * 100_000.0 - 1_000.0)
    assert gross.approved and any("exposición bruta" in x for x in gross.reasons)


def test_spot_cash_and_incident_cap(r):
    d = _eval(r, spot_quote_free=510.0)
    assert d.approved and d.notional == pytest.approx(500.0, rel=1e-3)
    tiny = _eval(r, equity=10_000.0, day_start_equity=10_000.0)
    cap = CFG.max_incident_loss_frac * 10_000.0 / (CFG.max_leg_loss_bps / 1e4)
    assert tiny.notional == pytest.approx(min(cap, 1_000.0))


def test_verify_rejects_tampered_vetoed_expired_and_other_config(r):
    d = _eval(r)
    r.engine.verify_arb(d, r.clock())
    with pytest.raises(PermissionError, match="sello"):
        r.engine.verify_arb(d.model_copy(update={"qty": d.qty * 10}), r.clock())
    with pytest.raises(PermissionError, match="vetado"):
        r.engine.verify_arb(_eval(r, r.plan(net_bps=0.0)), r.clock())
    with pytest.raises(PermissionError, match="caducada"):
        r.engine.verify_arb(d, r.clock() + DECISION_TTL_MS + 1)
    other = ArbRiskEngine(CFG.model_copy(update={"sha256": "x"}), lambda _: None, KillSwitch())
    with pytest.raises(PermissionError, match="configuración"):
        other.verify_arb(d, r.clock())


def test_config_never_allows_real(tmp_path):
    data = json.loads((VERSIONS_DIR / "risk_arb_v1.json").read_text(encoding="utf-8"))
    for modes in (["TESTNET", "REAL"], ["ANALISIS"], []):
        p = tmp_path / "risk_arb_vx.json"
        p.write_text(json.dumps({**data, "version": "risk_arb_vx", "allowed_modes": modes}),
                     encoding="utf-8")
        with pytest.raises(ValidationError, match="nunca REAL"):
            load_arb_config(p)
    assert load_arb_config().allowed_modes == ("TESTNET",)
    assert load_arb_config(version="risk_arb_sim_v1").allowed_modes == ("SIMULADO",)
    assert load_arb_config().strategies == ("funding_carry", "basis")   # Viable/Marginal T43
