"""Persistencia point-in-time de `bot_signals` y servicio de bots (T57)."""

import threading

import duckdb
import pytest

from eim.bots.adapter import empty_signal, version_of
from eim.bots.card import card_of
from eim.bots.hb_directional import BollingerV1, HummingbotDirectionalAdapter
from eim.bots.service import BotService, default_service
from eim.core import NOT_SAVED, VERSION_CHANGED
from eim.data.bots.store import BotSignalStore
from tests.bots.helpers import candles, snapshot

NOW = 10**13  # reloj de guardado muy posterior a las velas del fixture


@pytest.fixture
def store():
    return BotSignalStore(duckdb.connect(":memory:"), threading.Lock())


def one_signal(n=300, strategy="bollinger_v1"):
    sigs = HummingbotDirectionalAdapter().signals(snapshot(n))
    return next(s for s in sigs if s.strategy == strategy)


def test_append_only_first_write_wins(store):
    s = one_signal()
    assert store.append(s, NOW) is True
    changed = s.model_copy(update={"stance": -1.0})
    assert store.append(changed, NOW + 1) is False        # misma clave: no se reescribe
    (back,) = store.query("ETHUSDT", "1h")
    assert back == s and back.stance == s.stance


def test_future_asof_is_rejected(store):
    s = one_signal()
    with pytest.raises(ValueError, match="posterior"):
        store.append(s, s.asof - 1)
    assert store.query("ETHUSDT", "1h") == []


def test_every_row_carries_asof_version_and_status(store):
    for n in (250, 300):
        store.append(one_signal(n), NOW)
    rows = store._con.execute(
        "SELECT asof_ms, version, status, created_ms FROM bot_signals ORDER BY asof_ms").fetchall()
    assert len(rows) == 2 and rows[0][0] < rows[1][0]
    assert all(len(r[1]) == 53 and r[2] == "ok" and r[3] == NOW for r in rows)


def test_new_sha_or_params_creates_a_new_version_row_not_an_overwrite(store):
    s = one_signal()
    store.append(s, NOW)
    tuned = HummingbotDirectionalAdapter(strategies={"bollinger_v1": BollingerV1(bb_std=2.5)})
    t = next(x for x in tuned.signals(snapshot(300)) if x.strategy == "bollinger_v1")
    assert t.version != s.version and t.asof == s.asof
    assert store.append(t, NOW) is True
    assert {x.version for x in store.query("ETHUSDT", "1h")} == {s.version, t.version}


def test_query_filters_and_orders(store):
    for n in (250, 260, 270):
        store.append(one_signal(n), NOW)
    got = store.query("ETHUSDT", "1h")
    assert [g.asof for g in got] == sorted(g.asof for g in got) and len(got) == 3
    assert len(store.query("ETHUSDT", "1h", start=got[1].asof)) == 2
    assert len(store.query("ETHUSDT", "1h", end=got[0].asof)) == 1
    assert store.query("BTCUSDT", "1h") == [] and store.query("ETHUSDT", "4h") == []
    assert len(store.query("ETHUSDT", "1h", bot_id="hummingbot-directional")) == 3
    assert len(store.query("ETHUSDT", "1h", limit=1)) == 1


# --- servicio -------------------------------------------------------------------------------
def test_service_produces_persists_and_attaches(store):
    svc = BotService([HummingbotDirectionalAdapter()], store, clock=lambda: NOW)
    snap = svc.attach(snapshot(300))
    assert {s.strategy for s in snap.bot_signals} == {"bollinger_v1", "macd_bb_v1"}
    assert len(store.query("ETHUSDT", "1h")) == 2
    svc.attach(snapshot(300))                                  # repetir no duplica
    assert len(store.query("ETHUSDT", "1h")) == 2


def test_service_marks_a_version_change_against_the_last_stored(store):
    svc = BotService([HummingbotDirectionalAdapter()], store, clock=lambda: NOW)
    svc.attach(snapshot(300))
    moved = card_of("hummingbot-directional").model_copy(update={"commit_sha": "7" * 40})
    svc2 = BotService([HummingbotDirectionalAdapter(moved)], store, clock=lambda: NOW)
    sigs = svc2.produce(snapshot(310))
    assert sigs and all(any(n.startswith(VERSION_CHANGED) for n in s.data_quality.notes)
                        for s in sigs)
    again = svc2.produce(snapshot(320))                        # misma versión que la última
    assert not any(n.startswith(VERSION_CHANGED) for s in again for n in s.data_quality.notes)


def test_a_failing_adapter_becomes_a_degraded_signal(store):
    class Boom:
        bot_id = "hummingbot-directional"
        card = card_of("hummingbot-directional")

        def signals(self, snapshot):
            raise RuntimeError("explotó")

    svc = BotService([Boom(), HummingbotDirectionalAdapter()], store, clock=lambda: NOW)
    sigs = svc.produce(snapshot(300))
    bad = [s for s in sigs if s.status == "degraded"]
    assert len(bad) == 1 and "explotó" in bad[0].evidence[0] and bad[0].stance == 0
    assert len(sigs) == 3                                       # el otro adaptador siguió


def test_only_usable_cards_take_part(store):
    pending = card_of("hummingbot-directional").model_copy(
        update={"approval": card_of("hummingbot-directional").approval.model_copy(
            update={"state": "pendiente"})})
    svc = BotService([HummingbotDirectionalAdapter(pending)], store, clock=lambda: NOW)
    assert svc.produce(snapshot(300)) == []
    assert svc.attach(snapshot(300)).bot_signals is None


def test_service_never_raises_when_the_store_fails():
    class BrokenStore:
        def last_version(self, *a):
            raise RuntimeError("disco")

        def append(self, *a):
            raise RuntimeError("disco")

    svc = BotService([HummingbotDirectionalAdapter()], BrokenStore())
    assert len(svc.produce(snapshot(300))) == 2


def test_default_service_has_mode_a_and_adds_b_only_when_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("EIM_BOT_FREQTRADE_PY", raising=False)
    assert [a.bot_id for a in default_service(tmp_path, None).adapters] == [
        "hummingbot-directional"]
    (tmp_path / "bots" / "freqtrade-strategies").mkdir(parents=True)
    monkeypatch.setenv("EIM_BOT_FREQTRADE_PY", "/py")
    monkeypatch.setenv("EIM_BOT_FREQTRADE_ENGINE", "2026.9")
    assert [a.bot_id for a in default_service(tmp_path, None).adapters] == [
        "hummingbot-directional", "freqtrade-strategies"]


def test_empty_signal_helper_and_version_of():
    snap = snapshot(300)
    card = card_of("hummingbot-directional")
    s = empty_signal(card, "x", version_of(card.commit_sha, {}), snap, "degraded", "motivo")
    assert s.status == "degraded" and s.stance == 0 and s.evidence == ["motivo"]
    assert candles()[0].t < snap.asof


def test_unsaved_signal_is_still_returned_but_marked(store):
    class Full:
        def last_version(self, *a):
            return None

        def append(self, *a):
            raise RuntimeError("disco lleno")

    sigs = BotService([HummingbotDirectionalAdapter()], Full()).produce(snapshot(300))
    assert len(sigs) == 2
    assert all(any(n.startswith(NOT_SAVED) for n in s.data_quality.notes) for s in sigs)


def test_snapshot_with_an_unclosed_candle_produces_no_signals():
    snap = snapshot(300)
    early = snap.model_copy(update={"asof": snap.candles[-1].t + 1})   # la última vela aún abierta
    assert BotService([HummingbotDirectionalAdapter()]).attach(early).bot_signals is None


def test_split_version():
    from eim.bots.adapter import split_version
    assert split_version("a" * 40 + "+0123456789ab") == ("a" * 40, "0123456789ab")
