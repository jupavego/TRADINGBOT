"""T60: un bot que vota y se degrada entra en cuarentena (kill-switch del escuadrón)."""
from __future__ import annotations

import pytest

from eim.bots.card import default_cards
from eim.bots.quarantine import Quarantine
from eim.bots.service import BotService
from eim.synthesis.squad import policy_from_scorecard, set_policy
from tests.bots.helpers import snapshot
from tests.bots.score_helpers import signal

BOT = "hummingbot-directional"


class Stub:
    def __init__(self, status: str) -> None:
        self.card, self.status = default_cards()[BOT], status

    def signals(self, snap):
        return [signal(snap.asof, 1.0, status=self.status, bot=BOT, strategy="s1")]


@pytest.fixture(autouse=True)
def _reset():
    set_policy(None)
    yield
    set_policy(None)


def _vote_policy():
    row = {"bot": BOT, "strategy": "s1", "state": "vota", "initial_weight": 0.25,
           "publicable": False, "modulates_confidence": False, "marginal": {"rho_max": 0.1}}
    set_policy(policy_from_scorecard({"symbol": "ETHUSDT", "bots": [row]}, default_cards()))


def test_degraded_voter_is_quarantined(tmp_path):
    q = Quarantine(tmp_path)
    _vote_policy()
    BotService([Stub("ok")], quarantine=q).produce(snapshot())
    assert not q.keys()
    BotService([Stub("degraded")], quarantine=q).produce(snapshot())
    assert q.keys() == {f"{BOT}@s1"}


def test_degraded_non_voter_is_not_quarantined(tmp_path):
    q = Quarantine(tmp_path)
    BotService([Stub("degraded")], quarantine=q).produce(snapshot())
    assert not q.keys()
