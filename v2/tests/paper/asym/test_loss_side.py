"""T187: el lado de la pérdida (pérdida acotada, una idea un riesgo, peso sin rasguños)."""

from __future__ import annotations

import pytest

from eim.paper.asym import prereg as P
from eim.paper.asym.loss_side import capped_loss, capped_weight, measured, one_bet, unit_r
from eim.paper.params import PROFILES
from tests.paper.asym.helpers import row

FB = {p.id: p.feedback for p in PROFILES}


def test_only_trades_opened_after_the_start_count():
    old = row(1, opened=P.START_MS - 1)
    new = row(2, opened=P.START_MS)
    assert [r["ledger_id"] for r in measured([old, new])] == ["L2"]


def test_unit_r_carries_the_size():
    assert unit_r(row(1, r=-1.2, weight=1.0)) == pytest.approx(-1.2)
    assert unit_r(row(1, r=-1.2, weight=0.25)) == pytest.approx(-0.3)


def test_capped_loss_shrinks_size_like_risk_budget():
    # SL a 1 % del precio y costo estimado 0,16 %: tamaño × 0,01/(0,01+0,0016)
    p = capped_loss([row(1, r=-1.2, weight=1.0)], lambda _: 0.0016)[0]
    assert p.cf == pytest.approx(-1.2 * 0.01 / 0.0116)
    assert p.changed and p.delta > 0      # en una pérdida, acotarla mejora


def test_one_bet_keeps_only_the_first_entry_of_a_candle_and_side():
    a = row(1, r=-1.1, weight=0.5)
    b = row(2, r=-1.1, weight=1.0)                  # misma vela y sentido, más peso: va primero
    c = row(3, r=0.1, weight=0.5, side=-1)          # otro sentido: otra apuesta
    d = row(4, r=0.1, weight=0.5, profile="agresivo")   # otro perfil: otra cuenta
    out = {p.key: p for p in one_bet([a, b, c, d])}
    assert out["L2"].cf == out["L2"].actual          # la de más peso se queda
    assert out["L1"].cf == 0.0 and out["L1"].changed
    assert not out["L3"].changed and not out["L4"].changed


def test_weight_above_one_needs_own_evidence():
    hist_bad = [row(100 + k, r=0.1, weight=1.2, opened=P.START_MS - (40 - k) * 3_600_000)
                for k in range(25)]
    hist_good = [row(200 + k, r=0.6, weight=1.2, sid="agente_levels@15m",
                     opened=P.START_MS - (40 - k) * 3_600_000) for k in range(25)]
    t = row(1, r=-1.2, weight=1.6)                               # rasguños: m − se no sube
    u = row(2, r=-1.2, weight=1.6, sid="agente_levels@15m")     # +0,6 R × 25: respalda
    v = row(3, r=-1.2, weight=0.8)                               # ≤ 1: no se toca
    w = row(4, r=-1.2, weight=1.6, floor=True)                   # mínimo: no se toca
    out = {p.key: p for p in capped_weight([t, u, v, w], hist_bad + hist_good,
                                           lambda pid: FB[pid])}
    assert out["L1"].cf == pytest.approx(-1.2 * P.WEIGHT_CAP)
    assert out["L2"].cf == out["L2"].actual
    assert not out["L3"].changed and not out["L4"].changed


def test_weight_rule_ignores_closes_after_the_decision():
    future = [row(100 + k, r=0.6, weight=1.2, opened=P.START_MS + 10 * P.DAY_MS)
              for k in range(30)]
    t = row(1, r=-1.2, weight=1.6)
    assert capped_weight([t], future, lambda pid: FB[pid])[0].changed
