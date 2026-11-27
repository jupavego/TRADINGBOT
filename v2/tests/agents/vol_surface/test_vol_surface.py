"""T214: agente `vol_surface` — informante puro, nunca vota y nunca sale `degraded`."""

from __future__ import annotations

import math

import pytest

from eim.agents.vol_surface import VolSurfaceAgent, VolSurfaceParams
from eim.core import Candle, MarketSnapshot, OptionChain, OptionRow
from tests.options.surface_helpers import T0, chain

H = 3_600_000
FIELDS = set(OptionRow.model_fields)


def _chain(rows: list[dict], taken: int = T0) -> OptionChain:
    return OptionChain(source="deribit-options (prueba sintética) BTC", currency="BTC",
                       taken_ms=taken, rows=[OptionRow(**{k: r[k] for k in FIELDS}) for r in rows])


def _candles(n: int, asof: int, step: int = H, r: float = 0.01) -> list[Candle]:
    out, px = [], 90_000.0
    start = asof - (asof % step) - n * step
    for i in range(n):
        px *= math.exp(r if i % 2 else -r)
        out.append(Candle(t=start + i * step, o=px, h=px * 1.001, l=px * 0.999, c=px, v=1.0))
    return out


def _snap(oc: OptionChain | None, asof: int = T0 + 30 * 60_000, n: int = 300,
          tf: dict | None = None) -> MarketSnapshot:
    return MarketSnapshot(symbol="BTCUSDT", timeframe="1h", candles=_candles(n, asof),
                          candles_tf=tf, option_chain=oc, asof=asof)


def test_normal_case_describes_the_surface_without_voting():
    r = VolSurfaceAgent().run(_snap(_chain(chain(slope=0.2))))
    assert r.status == "ok" and r.bias == 0.0 and r.horizon_bars == 0 and r.confidence == 1.0
    m = r.metrics
    assert m["surface_status"] == "ok" and m["votes"] is False and m["role"] == "informante"
    assert 0.4 < m["atm_7d"] < 0.6 and m["rr25"] > 0 and m["term_slope"] > 0
    assert m["vrp_7d"] is not None and m["vrp_30d"] is None       # 300 h no cubren 30 días
    assert any(e.startswith("σ implícita ATM") for e in r.evidence)
    assert any("Fuente: deribit-options" in e for e in r.evidence)
    assert any("nunca vota dirección" in e for e in r.evidence)
    assert any("30 d" in w and "prima de varianza" in w for w in r.warnings)


def test_coarser_neighbour_frame_covers_the_30_day_premium():
    asof = T0 + 30 * 60_000
    r = VolSurfaceAgent().run(_snap(_chain(chain()), asof, tf={"4h": _candles(300, asof, 4 * H)}))
    assert r.metrics["vrp_30d"] is not None and r.metrics["realized"]["30d"] is not None


def test_without_chain_is_no_data_with_reason():
    r = VolSurfaceAgent().run(_snap(None))
    assert r.status == "no_data" and r.bias == 0 and r.confidence == 0
    assert "sin cadena de opciones" in r.warnings[0]


def test_never_looks_ahead_or_uses_a_very_old_chain():
    future = VolSurfaceAgent().run(_snap(_chain(chain(), taken=T0 + H), asof=T0))
    assert future.status == "no_data" and "posterior" in future.warnings[0]
    old = VolSurfaceAgent().run(_snap(_chain(chain()), asof=T0 + 27 * H))
    assert old.status == "no_data" and "27 h" in old.warnings[0]


def test_stale_chain_warns_but_still_reads():
    r = VolSurfaceAgent().run(_snap(_chain(chain()), asof=T0 + 3 * H))
    assert r.status == "ok" and any("lectura vieja" in w for w in r.warnings)


def test_degraded_surface_is_ok_with_lower_confidence_never_degraded():
    r = VolSurfaceAgent().run(_snap(_chain(chain(mark_shift=0.05))))
    assert r.status == "ok" and r.confidence == 0.5
    assert r.metrics["surface_status"] == "degradado"
    assert any("se aparta" in w for w in r.warnings)


def test_unmeasurable_surface_is_no_data():
    r = VolSurfaceAgent().run(_snap(_chain(chain(((10, .5), (24, .5), (52, .5))))))
    assert r.status == "no_data" and "superficie sin medir" in r.warnings[0]


def test_deterministic_and_bias_in_range():
    snap = _snap(_chain(chain(slope=-0.1)))
    a, b = VolSurfaceAgent().run(snap), VolSurfaceAgent().run(snap)
    assert a == b and -1 <= a.bias <= 1


def test_params_mirror_the_preregistered_surface():
    p = VolSurfaceParams()
    s = p.surface()
    assert (s.tenors_days, s.skew_tenor_days, s.min_expiry_days, s.max_mark_gap) == \
        ((7, 30), 30, 2.0, 0.02)
    assert VolSurfaceAgent.requires == {"option_chain"} and p.min_bars == 0


@pytest.mark.parametrize("bad", [0.0, -1.0])
def test_zero_or_negative_mark_iv_is_ignored(bad):
    rows = chain()
    for r in rows[:4]:
        r["mark_iv"] = bad
    assert VolSurfaceAgent().run(_snap(_chain(rows))).status == "ok"
