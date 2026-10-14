"""Kill-switch: manual, por reglas, solo se apaga a mano y bloquea al motor."""

import pytest

from eim.risk import KillSwitch, global_kill_switch
from tests.risk.helpers import CFG, NOW, account, engine, failed, market, plan


def test_manual_on_off_records_events():
    ks = KillSwitch()
    assert not ks.active
    ks.activate("revisión", NOW)
    assert ks.active and ks.close_requested
    st = ks.state()
    assert st["reason"] == "revisión" and st["by"] == "manual" and st["since"] == NOW
    ks.deactivate(NOW + 1, reason="ok")
    assert not ks.active
    assert [e["action"] for e in ks.state()["events"]] == ["activate", "deactivate"]


def test_rule_cannot_deactivate():
    ks = KillSwitch()
    ks.activate("x", NOW)
    with pytest.raises(PermissionError):
        ks.deactivate(NOW, by="regla:drawdown")
    assert ks.active


@pytest.mark.parametrize("kw,by", [
    ({"drawdown": 0.15}, "regla:drawdown"),
    ({"disconnected_ms": 300_000}, "regla:desconexion"),
    ({"recon_drift": 0.02}, "regla:reconciliacion"),
])
def test_rules_trigger(kw, by):
    ks = KillSwitch()
    why = ks.check_rules(CFG, NOW, **kw)
    assert ks.active and len(why) == 1 and ks.state()["by"] == by


def test_rules_below_threshold_do_nothing():
    ks = KillSwitch()
    assert ks.check_rules(CFG, NOW, drawdown=0.149, disconnected_ms=299_999,
                          recon_drift=0.0099) == []
    assert not ks.active


def test_first_reason_kept_while_active():
    ks = KillSwitch()
    ks.check_rules(CFG, NOW, drawdown=0.2, recon_drift=0.5)
    assert ks.state()["by"] == "regla:drawdown"
    assert len(ks.state()["events"]) == 2


def test_engine_blocked_while_active():
    eng, _, ks = engine()
    ks.activate("pánico", NOW)
    d = eng.evaluate(plan(), account(), market())
    assert not d.approved and failed(d) == {"kill-switch"} and "pánico" in d.reasons[0]
    ks.deactivate(NOW)
    assert eng.evaluate(plan(), account(), market()).approved


def test_global_instance_is_singleton():
    assert global_kill_switch() is global_kill_switch()
