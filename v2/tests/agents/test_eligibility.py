"""T91: elegibilidad contra los datos realmente disponibles, con el motivo escrito, y BTC/ETH
sin una diferencia (la adaptación de un perpetuo 24/7 devuelve el mismo agente)."""
from __future__ import annotations

import pytest

from eim.agents import adapt
from eim.agents.eligibility import coverage_of, eligible, run_eligible, select
from eim.agents.registry import default_registry
from eim.instruments.registry import BTCUSDT, ETHUSDT, NASDAQ, SP500, XAUUSDT
from tests.agents import _t91_series as s
from tests.agents.technical._synth import snapshot as crypto_snapshot

AGENTS = default_registry().latest()
BY_ID = {a.id: a for a in AGENTS}


@pytest.mark.parametrize("inst", [BTCUSDT, ETHUSDT, XAUUSDT], ids=lambda i: i.symbol)
def test_native_perpetuals_get_the_very_same_agents(inst):
    snap = crypto_snapshot("up", 400)
    cov = coverage_of(snap, inst)
    assert all(adapt.adapt(a, inst, cov) is a for a in AGENTS)
    assert adapt.notes(inst, cov) == []


def test_btc_eligible_agents_report_exactly_what_they_report_alone():
    snap = crypto_snapshot("up", 400)
    reports = run_eligible(AGENTS, snap, BTCUSDT)
    assert [r.agent_id for r in reports] == [a.id for a in AGENTS]
    ok, out = select(AGENTS, BTCUSDT, coverage_of(snap, BTCUSDT))
    assert {a.id for a, _ in ok} >= {"vwap", "technical", "structure", "plan", "regime"}
    for agent, _ in ok:
        assert reports[AGENTS.index(agent)] == agent.run(snap), agent.id
    for agent, why in out:   # lo que falta en el snapshot sintético: funding, líderes, bots…
        rep = reports[AGENTS.index(agent)]
        assert rep.status == "no_data" and rep.warnings == [f"no elegible: {why}"]
        assert rep.metrics["eligibility"] == {"eligible": False, "reason": why}


def test_reasons_are_written_for_each_rule():
    eq = s.snapshot("ACME", "1h", s.equity_1h(90, volume="real"))
    cov = coverage_of(eq, s.EQUITY)
    assert eligible(BY_ID["derivatives"], s.EQUITY, cov)[1].startswith("modelo de sesión")
    assert eligible(BY_ID["liquidations"], s.EQUITY, cov)[1].startswith("clase no soportada")
    assert "libro L2" in eligible(BY_ID["microstructure"], BTCUSDT,
                                  coverage_of(crypto_snapshot("up", 400), BTCUSDT))[1]
    bond = coverage_of(s.snapshot("UST10Y", "1d", s.equity_1d(300)), s.BOND)
    good, why = eligible(BY_ID["structure"], s.BOND, bond)
    assert not good and why.startswith("clase no soportada: bond")
    assert eligible(BY_ID["calendar"], s.BOND, bond)[1] == "no hay calendario económico"
    short = coverage_of(s.snapshot("ACME", "1h", s.equity_1h(10, volume="real")), s.EQUITY)
    good, why = eligible(BY_ID["plan"], s.EQUITY, short)
    assert not good and why.startswith("historial < min_bars")
    good, why = eligible(BY_ID["seasonality"], s.EQUITY, short)
    assert not good and "días" in why


def test_volume_decides_vwap_and_degrades_technical():
    idx = coverage_of(s.snapshot("SP500", "1d", s.equity_1d(420)), SP500)
    assert idx.volume == "none" and not idx.taker_flow
    good, why = eligible(BY_ID["vwap"], SP500, idx)
    assert not good and "volumen" in why
    good, why = eligible(BY_ID["technical"], SP500, idx)
    assert good and "sin volumen negociado" in why
    for agent_id in ("structure", "plan"):     # razón de volumen F-008: sin volumen, NaN (T91)
        good, why = eligible(BY_ID[agent_id], SP500, idx)
        assert not good and "volumen" in why, agent_id
    fx = coverage_of(s.snapshot("EURUSD", "1h", s.fx_1h()), s.FX)
    assert fx.volume == "tick"
    assert eligible(BY_ID["vwap"], s.FX, fx) == (
        True, "elegible, degradado con aviso: volumen de ticks, no negociado")


def test_data_declared_but_zero_is_no_volume():
    cov = coverage_of(s.snapshot("ACME", "1h", s.equity_1h(30, volume="none")), s.EQUITY)
    assert cov.volume == "none", "volumen 0 en todas las velas = sin volumen, diga lo que diga"


def test_agent_without_capabilities_never_runs():
    class Ghost:
        id, version, requires = "ghost", "0.0.1", {"candles"}

        def run(self, snapshot):  # pragma: no cover - no debe llegar a correr
            raise AssertionError("corrió sin ficha")

    snap = s.snapshot("SP500", "1d", s.equity_1d(300))
    (rep,) = run_eligible([Ghost()], snap, NASDAQ)
    assert rep.status == "no_data" and "sin capacidades declaradas" in rep.warnings[0]
