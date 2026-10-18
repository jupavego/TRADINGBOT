"""La prueba E2E de testnet (`arb_smoke`) contra el exchange simulado: su lógica es correcta
antes de correrla con claves reales de testnet."""

import httpx
import pytest

import eim.execution.arb_smoke as smoke
from eim.execution.binance_rest import ENV_KEY, ENV_SECRET
from tests.execution.fake_binance import KEY, SECRET
from tests.execution.fake_venue import FakeHTTP, Venue

SYM = "BTCUSDT"


@pytest.fixture
def s(monkeypatch):
    sv = Venue({SYM: 100_000.0}, step=0.00001, tick=0.01)
    fv = Venue({SYM: 100_050.0}, futures=True)
    routes = {"testnet.binance.vision": FakeHTTP(sv), "testnet.binancefuture.com": FakeHTTP(fv)}

    class Router(httpx.BaseTransport):
        def handle_request(self, request):
            return routes[request.url.host].handle(request)

    monkeypatch.setattr(smoke.httpx, "HTTPTransport", Router)
    monkeypatch.setattr(smoke.time, "sleep", lambda _s: None)
    for k in ("EIM_SPOT_TESTNET_API_KEY", "EIM_SPOT_TESTNET_API_SECRET",
              "EIM_TESTNET_URL", "EIM_SPOT_TESTNET_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv(ENV_KEY, KEY)
    monkeypatch.setenv(ENV_SECRET, SECRET)
    out = smoke.Smoke(SYM, 300.0)
    out.venues = (sv, fv)
    return out


def test_carry_open_hold_close(s):
    assert s.carry(0)
    sv, fv = s.venues
    assert fv.pos[SYM][0] == 0 and sv.balances["BTC"] == pytest.approx(1.0)


def test_failed_leg_is_unwound_to_net_zero(s):
    assert s.fail()
    sv, fv = s.venues
    assert fv.pos.get(SYM, [0.0])[0] == 0 and sv.balances["BTC"] == pytest.approx(1.0)


def test_network_cut_leaves_no_orphan(s):
    assert s.cut()
    assert s.venues[1].pos.get(SYM, [0.0])[0] == 0
