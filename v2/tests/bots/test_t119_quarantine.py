"""T119: camino completo de la cuarentena con un bot real (adaptador de Hummingbot sobre velas del
fixture) y reactivación por CLI con la «API» en marcha, sin reiniciarla. Sin red."""

from __future__ import annotations

import json

import pytest

from eim.bots.card import default_cards
from eim.bots.hb_directional import HummingbotDirectionalAdapter
from eim.bots.quarantine import Quarantine, main
from eim.bots.service import BotService
from eim.synthesis.squad import current_policy, policy_from_scorecard, set_policy
from tests.bots.helpers import snapshot

BOT = "hummingbot-directional"
KEY = f"{BOT}@bollinger_v1"
CARDS = default_cards()
SC = {"symbol": "ETHUSDT", "bots": [{
    "bot": BOT, "strategy": "bollinger_v1", "state": "vota", "initial_weight": 0.25,
    "publicable": False, "modulates_confidence": False, "marginal": {"rho_max": 0.1}}]}


class Hung(HummingbotDirectionalAdapter):
    """El bot real, pero su ejecución cae (como un proceso colgado que mata el tiempo límite)."""

    def signals(self, snap):
        raise TimeoutError("el ejecutor no respondió en 30 s")


@pytest.fixture(autouse=True)
def _reset():
    set_policy(None)
    yield
    set_policy(None)


def test_quarantine_trip_and_cli_release_while_the_api_runs(tmp_path, capsys):
    data = tmp_path / "data"
    q = Quarantine(data / "bots")                    # el de la API (en memoria + archivo)

    def refresh():                                  # lo que hace `SquadRuntime`
        set_policy(policy_from_scorecard(SC, CARDS, q.keys()))

    q.on_change.append(refresh)
    refresh()
    voters = [b.key for b in current_policy().voters]
    assert voters == [KEY]

    BotService([HummingbotDirectionalAdapter()], quarantine=q).produce(snapshot())
    assert not q.keys()                              # sano: sigue votando
    sigs = BotService([Hung()], quarantine=q).produce(snapshot())
    assert sigs[0].status == "degraded" and "TimeoutError" in sigs[0].evidence[0]
    assert set(q.keys()) == {KEY} and not current_policy().voters     # voto perdido al instante
    assert "TimeoutError" in q.entries()[KEY]["reason"]

    assert main(["--data-dir", str(data), "list"]) == 0
    assert KEY in capsys.readouterr().out
    assert main(["--data-dir", str(data), "release", KEY, "--by", "prueba"]) == 0   # otro proceso
    assert main(["--data-dir", str(data), "release", KEY]) == 1                    # ya no estaba

    BotService([HummingbotDirectionalAdapter()], quarantine=q).produce(snapshot())
    assert not q.keys() and [b.key for b in current_policy().voters] == [KEY]     # sin reiniciar

    q.trip("otro@s1", "prueba", 3)                   # un disparo posterior no la resucita
    assert set(json.loads((data / "bots" / "quarantine.json").read_text("utf-8"))) == {"otro@s1"}
    lines = (data / "bots" / "quarantine.jsonl").read_text("utf-8").splitlines()
    log = [json.loads(x) for x in lines]
    assert [(e["action"], e["bot"]) for e in log] == [
        ("trip", KEY), ("release", KEY), ("trip", "otro@s1")]
    assert log[1]["why"] == "prueba"


def test_a_partially_written_file_keeps_the_previous_state(tmp_path):
    q = Quarantine(tmp_path)
    q.trip("a@s", "x", 1)
    (tmp_path / "quarantine.json").write_text('{"a@s": {"rea', encoding="utf-8")
    assert q.keys() == {"a@s"}                       # no se pierde la cuarentena por leer a medias
