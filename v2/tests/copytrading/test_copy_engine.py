"""Motor de copia simulada (T42): riesgo T29, desconexión, reconciliación con pausa, stop,
kill-switch propio, funding, bitácora, persistencia y atribución aparente vs copiable."""

from __future__ import annotations

import json

import pytest

from eim.copytrading.copy_attrib import CAUSES, attribute
from eim.copytrading.copy_engine import CopyEngine
from eim.copytrading.copy_models import group_fills
from eim.copytrading.copy_risk import copy_config
from eim.copytrading.trades import build_trips
from eim.risk import global_kill_switch
from tests.copytrading.copy_helpers import SPEC, P, engine, feed, quote, sig
from tests.copytrading.helpers import LID, T0, fill, position


def test_journal_records_signal_decision_risk_and_order():
    e = engine()
    (f,) = feed(e, "BTC", 0.0, 4.0, 50_000.0, T0 + 1_000, 1)
    assert f.kind == "open" and f.price == pytest.approx(50_005.0) and f.src == "bbo"
    assert f.fee == pytest.approx(0.04 * 50_005.0 * P.taker_fee) and f.latency_ms == 500
    kinds = [x.kind for x in e.journal]
    assert kinds == ["start", "signal", "decision", "risk", "order"]
    risk = e.journal[3]
    assert risk.code == "aprobado" and risk.data["config"] == "risk_copy_v1"
    assert e.account.positions["BTC"].stop == pytest.approx(50_005.0 * 0.95)


def test_stale_signal_is_vetoed_by_the_risk_engine_but_closes_are_never_vetoed():
    e = engine()
    feed(e, "BTC", 0.0, 4.0, 50_000.0, T0 + 1_000, 1)
    late = feed(e, "BTC", 4.0, 8.0, 50_000.0, T0 + 5_000, 2, delay=45_000)  # 45 s tarde
    assert late == [] and e.journal[-1].code == "riesgo" and "vigencia" in e.journal[-1].text
    assert e.coins["BTC"].note.startswith("motor de riesgo")
    (close,) = feed(e, "BTC", 8.0, 0.0, 50_100.0, T0 + 9_000, 3, delay=90_000)
    assert close.kind == "close" and e.account.size("BTC") == 0


def test_disconnection_mid_trip_blocks_opens_and_still_follows_the_exit():
    alerts: list = []
    e = engine(alerts)
    feed(e, "BTC", 0.0, 4.0, 50_000.0, T0 + 1_000, 1)
    e.set_feed_down(T0 + 2_000)  # WS caído: el relleno REST llega después
    up = feed(e, "BTC", 4.0, 6.0, 50_050.0, T0 + 3_000, 2, delay=200, channel="rest_backfill")
    assert up == [] and e.journal[-1].code == "flujo_caido"
    eth = feed(e, "ETH", 0.0, 10.0, 2_500.0, T0 + 3_500, 3)
    assert eth == [] and e.journal[-1].code == "flujo_caido"
    e.set_feed_down(None)
    (c,) = feed(e, "BTC", 6.0, 0.0, 50_100.0, T0 + 4_000, 4, delay=60_000,
                channel="rest_backfill")
    assert c.kind == "close"
    r = e.reconcile(T0 + 70_000, {"ETH": 10.0})
    assert r.ok and r.diffs[0].coin == "ETH" and r.diffs[0].status == "explicada"
    assert not alerts and e.paused is None


def test_missed_signal_pauses_after_confirmation_and_resume_resyncs_without_buying():
    alerts: list = []
    e = engine(alerts)
    feed(e, "BTC", 0.0, 4.0, 50_000.0, T0 + 1_000, 1)
    assert e.reconcile(T0 + 30_000, {"BTC": 4.0}).ok
    r1 = e.reconcile(T0 + 60_000, {"BTC": 6.0})  # aumento que nunca llegó como señal
    assert not r1.ok and e.paused is None  # una sola comprobación no basta
    e.reconcile(T0 + 90_000, {"BTC": 6.0})
    assert e.paused and "señal perdida" in e.paused and alerts[0][0] == "critical"
    blocked = feed(e, "ETH", 0.0, 10.0, 2_500.0, T0 + 95_000, 2)
    assert blocked == [] and e.journal[-1].code == "pausa"
    (red,) = feed(e, "BTC", 6.0, 3.0, 50_000.0, T0 + 96_000, 3)  # reducir sí, en pausa
    assert red.kind == "reduce" and e.account.size("BTC") == pytest.approx(0.03)
    e.resume(T0 + 100_000)
    assert e.reconcile(T0 + 120_000, {"BTC": 3.0, "ETH": 10.0}).ok
    assert e.account.size("ETH") == 0 and e.coins["ETH"].note.startswith("copia en pausa")
    e.resume(T0 + 130_000)  # otra vez: ahora la foto trae algo que la copia nunca vio
    assert e.reconcile(T0 + 150_000, {"BTC": 3.0, "ETH": 10.0, "SOL": -5.0}).ok
    assert e.coins["SOL"].excluded == "apertura_no_vista" and e.account.size("SOL") == 0
    assert e.paused is None and [x.code for x in e.journal if x.kind == "resume"] == \
        ["manual", "manual"]
    assert [x.code for x in e.journal if x.kind == "recon"].count("resync") == 2


def test_fills_after_the_photo_state_are_not_a_missed_signal():
    e = engine()
    feed(e, "BTC", 0.0, 4.0, 50_000.0, T0 + 1_000, 1)
    feed(e, "BTC", 4.0, 6.0, 50_000.0, T0 + 40_000, 2)  # posterior al estado de la foto
    for k in range(3):  # la foto (estado de T0 + 30 s) llega tarde, varias veces
        r = e.reconcile(T0 + 45_000 + k, {"BTC": 4.0}, state_t=T0 + 30_000)
        assert r.ok and r.diffs[0].why == "señal del líder pendiente de ejecutar"
    assert e.paused is None


def test_known_capture_gap_resyncs_to_the_photo_without_opening_anything():
    alerts: list = []
    e = engine(alerts)
    feed(e, "BTC", 0.0, 4.0, 50_000.0, T0 + 1_000, 1)
    feed(e, "ETH", 0.0, 10.0, 2_500.0, T0 + 2_000, 2)
    e.on_mark("BTC", T0 + 60_000, 50_500.0)
    e.confirm_feed(T0 + 60_000)
    later = T0 + 8 * 3_600_000  # equipo suspendido toda la noche: nada confirmado
    e.confirm_feed(later)
    r = e.reconcile(later, {"ETH": 10.0, "SOL": 3.0}, state_t=later - 500)
    assert r.ok and not alerts and e.paused is None
    assert e.account.size("BTC") == 0 and e.account.size("ETH") == pytest.approx(0.1, abs=1e-3)
    assert e.coins["SOL"].excluded == "apertura_no_vista" and e.account.size("SOL") == 0
    assert "hueco de captura de 479 min" in [x for x in e.journal if x.code == "resync"][0].text
    old = sig("BTC", 4.0, 0.0, 50_000.0, later - 1_000, 9)  # relleno anterior a la foto
    assert e.on_signal(old, quote(50_000.0, later + 10), later + 10) == []


def test_unexplained_own_position_without_a_reason_is_flagged():
    e = engine()
    feed(e, "BTC", 0.0, 4.0, 50_000.0, T0 + 1_000, 1)
    e.coins["BTC"].ratio = 0.02  # objetivo cambiado sin motivo registrado
    r = e.reconcile(T0 + 30_000, {"BTC": 4.0})
    assert not r.ok and "sin motivo registrado" in r.diffs[0].why


def test_protective_stop_closes_and_excludes_the_rest_of_the_trip():
    e = engine()
    feed(e, "BTC", 0.0, 4.0, 50_000.0, T0 + 1_000, 1)
    stop = e.account.positions["BTC"].stop
    out = e.on_mark("BTC", T0 + 60_000, 47_000.0, low=47_000.0, high=48_000.0, open_=48_000.0)
    assert out.kind == "stop" and out.price < stop and e.coins["BTC"].excluded == "stop"
    assert feed(e, "BTC", 4.0, 6.0, 47_100.0, T0 + 70_000, 2) == []
    assert e.reconcile(T0 + 80_000, {"BTC": 6.0}).ok  # explicado: viaje excluido


def test_own_kill_switch_on_drawdown_closes_everything_and_spares_the_global_one():
    alerts: list = []
    e = engine(alerts)
    for k, coin in enumerate(("BTC", "ETH")):
        px = 50_000.0 if coin == "BTC" else 2_500.0
        feed(e, coin, 0.0, 8.0 if coin == "BTC" else 160.0, px, T0 + 1_000 + k, k + 1)
    e.account.positions["BTC"].stop = e.account.positions["ETH"].stop = None  # sin stop
    e.on_mark("BTC", T0 + 60_000, 33_000.0)
    e.on_mark("ETH", T0 + 60_000, 1_650.0)
    assert e.risk.kill.active and not global_kill_switch().active
    assert e.account.positions == {} and [f.kind for f in e.fills[-2:]] == ["kill", "kill"]
    assert any("kill-switch" in a[1] for a in alerts)
    assert feed(e, "BTC", 0.0, 1.0, 33_000.0, T0 + 90_000, 9) == []


def test_funding_uses_the_position_held_at_the_payment_hour():
    e = engine()
    feed(e, "BTC", 0.0, 4.0, 50_000.0, T0 + 1_000, 1)
    h = T0 + 3_600_000 - T0 % 3_600_000
    paid = e.on_funding("BTC", h, 0.0001, 50_000.0)
    assert paid == pytest.approx(-0.04 * 50_000.0 * 0.0001)
    assert e.on_funding("BTC", h, 0.0001, 50_000.0) is None  # una vez por hora
    assert e.on_funding("ETH", h, 0.0001, 2_500.0) is None  # sin posición: nada


def test_state_roundtrip_keeps_account_coins_pause_and_dedupe():
    e = engine()
    feed(e, "BTC", 0.0, 4.0, 50_000.0, T0 + 1_000, 1)
    e.pause("prueba", T0 + 2_000)
    st = json.loads(json.dumps(e.to_state()))
    e2 = CopyEngine(LID, P, SPEC, copy_config(P), t0=0)
    e2.load_state(st)
    assert e2.summary(0) | {"journal": []} == e.summary(0) | {"journal": []}
    s = sig("BTC", 0.0, 4.0, 50_000.0, T0 + 1_000, 1)
    assert e2.on_signal(s, quote(50_000.0, T0 + 1_500), T0 + 1_500) == []  # ya procesada


def test_signals_before_the_first_photo_are_ignored_and_preexisting_not_copied():
    e = CopyEngine(LID, P, SPEC, copy_config(P), t0=T0)
    e.leader_av = 1_000_000.0
    e.confirm_feed(T0)
    e.start(T0, [position("ETH", "long", 10.0, 2_500.0, T0 - 100)], state_t=T0 - 100)
    old = group_fills([fill("BTC", 0.0, 4.0, 50_000.0, T0 - 500, 1)])[0]
    assert e.on_signal(old, quote(50_000.0, T0), T0) == []
    assert feed(e, "ETH", 10.0, 12.0, 2_500.0, T0 + 1_000, 2) == []
    assert e.journal[-1].code == "excluido:preexistente"


def test_attribution_splits_the_gap_into_causes_that_add_up():
    e = engine()
    fills = [fill("BTC", 0.0, 4.0, 50_000.0, T0 + 1_000, 1, fee=40.0),
             fill("BTC", 4.0, 0.0, 51_000.0, T0 + 60_000, 2, pnl=4_000.0, fee=40.8),
             fill("ETH", 0.0, 10.0, 2_500.0, T0 + 70_000, 3, fee=5.0),
             fill("ETH", 10.0, 0.0, 2_550.0, T0 + 90_000, 4, pnl=500.0, fee=5.1)]
    feed(e, "BTC", 0.0, 4.0, 50_000.0, T0 + 1_000, 1, qpx=50_020.0)  # latencia en contra
    feed(e, "BTC", 4.0, 0.0, 51_000.0, T0 + 60_000, 2, qpx=50_990.0)
    feed(e, "ETH", 0.0, 10.0, 2_500.0, T0 + 70_000, 3, qpx=2_600.0)  # deslizamiento: no se copia
    feed(e, "ETH", 10.0, 0.0, 2_550.0, T0 + 90_000, 4)
    a = attribute(LID, build_trips(fills), e.fills, e.closed, e.trip_info, {})
    assert (a.trips, a.copied, a.skipped) == (2, 1, 1)
    assert a.skipped_n == {"deslizamiento": 1}
    assert a.follower - a.apparent == pytest.approx(sum(a.causes[k] for k in CAUSES))
    assert a.causes["latencia"] < 0 and a.causes["diferencial"] < 0
    ratio = e.trip_info[f"ETH:{T0 + 70_000}"]["ratio"]  # capital tras el viaje de BTC
    assert a.causes["no_copiadas"] == pytest.approx(-(500.0 - 10.1) * ratio)
    assert a.leader_bps > a.follower_bps


def test_late_backfill_older_than_the_ws_resend_does_not_overwrite_the_position():
    """Tras un corte del WS, el reenvío (lo más nuevo) llega antes que el relleno REST (lo más
    viejo): las ejecuciones viejas no deben pisar la posición actual (caso real 2026-10-16)."""
    e = engine()
    feed(e, "BTC", 0.0, 6.0, 50_000.0, T0 + 1_000, 1)
    e.set_feed_down(T0 + 2_000)
    s_new = sig("BTC", 4.0, 3.0, 50_000.0, T0 + 60_000, 9, delay=500, channel="ws_snapshot")
    e.set_feed_down(None)
    e.on_signal(s_new, quote(50_000.0, s_new.observed_at + 300), s_new.observed_at + 300)
    old = group_fills([fill("BTC", 6.0, 5.0, 50_000.0, T0 + 30_000, 7, delay=40_000,
                            channel="rest_backfill"),
                       fill("BTC", 5.0, 4.0, 50_000.0, T0 + 40_000, 8, delay=30_000,
                            channel="rest_backfill")])
    for s in old:  # llegan después, con hora de exchange anterior
        assert e.on_signal(s, quote(50_000.0, T0 + 70_500), T0 + 70_500) == []
    assert e.coins["BTC"].leader == 3.0 and e.account.size("BTC") == pytest.approx(0.03)
    assert e.reconcile(T0 + 80_000, {"BTC": 3.0}, state_t=T0 + 79_000).ok
    assert e.counts["stale"] == 1 and e.journal[-1].kind in ("signal", "recon")


def test_gap_resync_never_rewinds_a_view_newer_than_the_photo():
    """Reinicio tras un hueco: la foto del arranque se compara después de que el WS ya trajo
    ejecuciones más nuevas; adoptarla haría retroceder la vista (caso real 2026-10-16)."""
    e = engine()
    feed(e, "BTC", 0.0, 4.0, 50_000.0, T0 + 1_000, 1)
    e.confirm_feed(T0 + 60_000)
    boot = T0 + 30 * 60_000  # 30 min sin capturar
    feed(e, "BTC", 5.0, 6.0, 50_000.0, boot + 40_000, 2)  # WS vivo tras el arranque
    r = e.reconcile(boot + 60_000, {"BTC": 5.0}, state_t=boot)  # foto del arranque
    assert r.ok and e.coins["BTC"].leader == 6.0 and e.paused is None
    assert e.reconcile(boot + 90_000, {"BTC": 6.0}, state_t=boot + 89_000).ok
