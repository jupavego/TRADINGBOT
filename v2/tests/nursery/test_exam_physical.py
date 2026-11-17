"""T169: la física de un prospecto sale del motor de T168 con su misma regla de cupo."""

from __future__ import annotations

import pytest

from eim.core import Candle
from eim.nursery.exam.physical import physics
from eim.nursery.exam.plan import DAY_MS, Stretch
from eim.nursery.exam.report import FORBIDDEN, tokens
from eim.nursery.prospect import from_dossier, load_dossiers, load_prospects
from eim.paper.engine import Path
from tests.nursery.helpers import H1, M15, T0, make_ctxs, make_path

PS = {p.id: p for p in load_prospects()}
_REG = load_dossiers()["regime"]
# `regimen_tramo` se dio de baja en T169 (regime, excluido en T177), pero su regla sigue siendo la
# prueba más limpia de `rule_flip`: etiquetas que entran, sostienen y cambian.
PS["regimen_tramo"] = from_dossier(_REG, next(x for x in _REG["discarded"]
                                              if x["id"] == "regimen_tramo"))


def _calm_path(hours: int) -> Path:
    """Precio quieto con mechas de ±0,05 %: la límite llena y el stop (1,5 ATR) no salta."""
    cs = [Candle(t=T0 + k * M15, o=60_000.0, h=60_030.0, l=59_970.0, c=60_000.0, v=1.0)
          for k in range(hours * 4)]
    return Path(cs, [], M15)


def _regime_ctxs(labels: list[str]) -> list[dict]:
    return [{"t": T0 + (i + 1) * H1, "close": 60_000.0, "atr": 240.0,
             "nat": {"regime": {"regime": lab, "_h": 6}}} for i, lab in enumerate(labels)]


def test_rule_flip_hold_censoring_and_cadence() -> None:
    labels = ["trend_up"] * 10 + ["range"] * 5 + ["trend_down"] * 10
    ctxs = _regime_ctxs(labels)
    st = Stretch("1h", 0, T0, T0 + 25 * H1)
    ph = physics(PS["regimen_tramo"], [(st, ctxs)], _calm_path(30))
    assert ph["ideas"] == 20                 # señales de entrada, no operaciones
    assert ph["filled"] == 2 and ph["closed"] == 1 and ph["censored"] == 1
    assert ph["hold_h_median"] == pytest.approx(10.0)   # sale al cambiar la etiqueta
    assert ph["ops_month"] == pytest.approx(2 / (25 / 24) * 30, rel=1e-3)
    assert ph["long_share"] == 0.5 and ph["side_flips_month"] > 0
    assert 0.7 < ph["exposure"] < 0.8
    assert ph["cost_r_mean"] is not None and ph["cost_r_mean"] > 0
    assert ph["turnover_month"] > 0
    cov = ph["coverage"]
    assert cov["agent_ok"] == 1.0 and cov["variables"][0]["with_value"] == 1.0


def test_one_position_at_a_time_and_missing_agent_rows() -> None:
    ctxs = _regime_ctxs(["trend_up"] * 12)
    for c in ctxs[6:]:
        c["nat"] = {}                         # el agente no tuvo datos: la regla no decide
    st = Stretch("1h", 0, T0, T0 + 12 * H1)
    ph = physics(PS["regimen_tramo"], [(st, ctxs)], _calm_path(14))
    assert ph["ideas"] == 6 and ph["filled"] == 1     # sostiene una sola posición
    assert ph["coverage"]["agent_ok"] == 0.5


def test_every_prospect_with_history_runs_and_reports_only_physics() -> None:
    path = make_path(96 * 20)
    ctx = {"15m": make_ctxs(path, M15), "1h": make_ctxs(path, H1), "4h": make_ctxs(path, 4 * H1)}
    end = int(path.t[-1])
    for p in PS.values():
        if p.agent_id in {"bots", "derivatives", "liquidations", "microstructure"}:
            continue
        st = Stretch(p.timeframe, -1, T0, end)
        ph = physics(p, [(st, ctx[p.timeframe])], path)
        assert ph["closed"] + ph["censored"] == ph["filled"] <= ph["orders"] <= ph["ideas"]
        assert ph["days"] == pytest.approx((end - T0) / DAY_MS, abs=0.01)
        assert not {k for k in ph if tokens(k) & FORBIDDEN}, p.id
