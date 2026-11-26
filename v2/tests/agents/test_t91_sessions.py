"""T91 (b): series con huecos nocturnos y de fin de semana, sin volumen o con ticks. Cada
agente elegible devuelve un reporte válido o `no_data` con motivo: jamás una excepción ni un
valor inventado. Y los supuestos adaptados hacen lo que dicen (anclas, mes, volumen)."""
from __future__ import annotations

import math

import pandas as pd
import pytest

from eim.agents.eligibility import coverage_of, run_eligible
from eim.agents.registry import default_registry
from eim.agents.seasonality import SeasonalityAgent, SeasonalityParams
from eim.agents.seasonality.compute import monthly_closes
from eim.agents.technical import TechnicalAgent, TechnicalParams
from eim.agents.vwap import VWAPAgent, VWAPParams
from eim.agents.vwap.compute import period_keys
from eim.instruments.registry import NASDAQ, SP500
from tests.agents import _t91_series as s

AGENTS = default_registry().latest()

CASES = {
    "indice_1d_sin_volumen": (SP500, s.snapshot("SP500", "1d", s.equity_1d(420))),
    "indice_1h_sin_volumen": (NASDAQ, s.snapshot("NASDAQ", "1h", s.equity_1h(90))),
    "accion_1h_volumen_real": (s.EQUITY, s.snapshot("ACME", "1h", s.equity_1h(90, "real"))),
    "accion_1d_volumen_real": (s.EQUITY, s.snapshot("ACME", "1d", s.equity_1d(420, "real"))),
    "fx_1h_ticks": (s.FX, s.snapshot("EURUSD", "1h", s.fx_1h(60))),
}


@pytest.fixture(scope="module", params=list(CASES))
def case(request):
    inst, snap = CASES[request.param]
    return request.param, inst, snap, run_eligible(AGENTS, snap, inst)


def test_never_an_exception_nor_a_silent_number(case):
    name, _inst, _snap, reports = case
    assert [r.agent_id for r in reports] == [a.id for a in AGENTS]
    for r in reports:
        assert not any(w.startswith(("error:", "timeout")) for w in r.warnings), (name, r)
        assert math.isfinite(r.bias) and math.isfinite(r.confidence)
        if r.status == "no_data":
            assert r.warnings and r.bias == 0 and r.confidence == 0, (name, r.agent_id)


def test_no_volume_means_no_vwap_and_no_volume_families(case):
    name, inst, snap, reports = case
    by = {r.agent_id: r for r in reports}
    vol = coverage_of(snap, inst).volume
    if vol == "none":
        assert by["vwap"].status == "no_data" and "volumen" in by["vwap"].warnings[0]
        for agent_id in ("structure", "plan"):
            assert by[agent_id].warnings[0].startswith("no elegible: necesita volumen")
        fams = by["technical"].metrics["families"]
        assert fams["volumen"]["vote"] is None and fams["flujo"]["vote"] is None
        assert by["technical"].status == "degraded"
        assert any("no tiene volumen negociado" in w for w in by["technical"].warnings)
    if vol == "tick":
        assert by["vwap"].status == "degraded"
        assert any("ticks" in w for w in by["vwap"].warnings)
        assert by["structure"].status == "degraded"           # el aviso llega al estado
        assert by["structure"].metrics["eligibility"]["eligible"] is True
    if vol == "real":   # acción: flujo sin taker_buy_v = capacidad ausente, no degradación
        tech = by["technical"]
        assert tech.metrics["families_absent"] == ["flujo"]
        assert not any("familias sin datos" in w and "flujo" in w for w in tech.warnings)


def test_daily_anchor_is_declared_dead_on_daily_bars():
    snap = s.snapshot("ACME", "1d", s.equity_1d(420, "real"))
    rep = VWAPAgent(VWAPParams(explicit_dead_anchors=True, anchor_tz="America/New_York")
                    ).run(snap)
    assert rep.metrics["periods"]["daily"] == {"applicable": False}
    assert rep.status == "degraded" and any("ancla diario no aplica" in w for w in rep.warnings)
    assert rep.confidence <= 0.6 * 3 / 4 + 1e-12, "perder un ancla cuesta confianza (T87)"
    assert all(o.geometry["period"] != "daily" for o in rep.overlays)
    legacy = VWAPAgent().run(snap)             # por defecto, el comportamiento de siempre
    assert legacy.metrics["periods"]["daily"]["position"] == "SIN_DATOS"


def test_session_anchor_uses_the_exchange_day():
    # 2025-03-10 00:30 UTC es aún el domingo 9 en Nueva York (fin de semana): otra semana.
    ts = pd.Series(pd.to_datetime([1741566600000], unit="ms", utc=True))
    utc, ny = period_keys(ts), period_keys(ts, "America/New_York")
    assert utc["daily"].iloc[0] == pd.Timestamp("2025-03-10", tz="UTC")
    assert ny["daily"].iloc[0] == pd.Timestamp("2025-03-09 05:00", tz="UTC")  # medianoche NY
    assert ny["weekly"].iloc[0] < utc["weekly"].iloc[0]


def test_month_closes_on_its_last_session():
    # mayo de 2025 termina en sábado: su última sesión es el viernes 30 (vela de las 14:30 UTC)
    cs = [c for c in s.equity_1d(160, "real") if pd.Timestamp(c.t, unit="ms").month <= 5]
    asof = int(pd.Timestamp("2025-06-02", tz="UTC").timestamp() * 1000)
    plain = monthly_closes(cs, "1d", asof)
    graced = monthly_closes(cs, "1d", asof, grace_ms=4 * s.DAY)
    assert len(graced) == len(plain) + 1                     # mayo cuenta con el calendario
    assert graced["timestamp"].iloc[-1] == pd.Timestamp("2025-05-01", tz="UTC")
    rep = SeasonalityAgent(SeasonalityParams(month_end_grace_days=4)).run(
        s.snapshot("ACME", "1d", cs).model_copy(update={"asof": asof}))
    assert rep.status in ("ok", "no_data") and math.isfinite(rep.bias)


def test_technical_defaults_are_unchanged():
    p = TechnicalParams()
    assert p.volume_kind == "real" and p.families_absent == ()
    assert TechnicalAgent().absent == ()
