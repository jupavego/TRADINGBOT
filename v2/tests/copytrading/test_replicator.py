"""Replicador puro (T42): objetivo = líder × proporción, nunca contra el movimiento del líder,
topes, redondeo, mínimos, deslizamiento y viajes excluidos."""

from __future__ import annotations

import pytest

from eim.copytrading.copy_params import CopyParams, ExchangeSpec
from eim.copytrading.replicator import CoinCopy, decide
from tests.copytrading.copy_helpers import AV, SPEC, ctx, sig
from tests.copytrading.helpers import T0

P = CopyParams()


def _open(size: float = 4.0, px: float = 50_000.0):
    return decide(CoinCopy("BTC"), 0.0, sig("BTC", 0.0, size, px, T0, 1), ctx(T0 + 500), P, SPEC)


def test_open_is_proportional_to_own_balance():
    d, c = _open()
    (a,) = d.actions
    assert a.kind == "open" and a.side == 1 and a.qty == pytest.approx(0.04)
    assert c.ratio == pytest.approx(10_000 / AV) and c.trip_t == T0 and d.note is None
    d2, _ = decide(CoinCopy("BTC"), 0.0, sig("BTC", 0.0, 4.0, 50_000.0, T0, 1),
                   ctx(T0 + 500, equity=5_000.0), P, SPEC)
    assert d2.actions[0].qty == pytest.approx(0.02)  # mitad de saldo, mitad de posición


def test_partial_close_reduces_to_target():
    _, c = _open()
    d, c2 = decide(c, 0.04, sig("BTC", 4.0, 1.0, 50_100.0, T0 + 9_000, 2),
                   ctx(T0 + 9_500, 50_100.0), P, SPEC)
    (a,) = d.actions
    assert a.kind == "reduce" and a.side == -1 and a.qty == pytest.approx(0.03)
    assert a.target == pytest.approx(0.01) and c2.leader == 1.0 and c2.ratio == c.ratio


def test_flip_closes_and_opens_the_other_side_with_a_new_ratio():
    _, c = _open()
    d, c2 = decide(c, 0.04, sig("BTC", 4.0, -2.0, 50_200.0, T0 + 9_000, 2),
                   ctx(T0 + 9_500, 50_200.0, equity=12_000.0), P, SPEC)
    close, opn = d.actions
    assert (close.kind, close.side, close.qty) == ("close", -1, 0.04)
    assert (opn.kind, opn.side) == ("open", -1) and opn.qty == pytest.approx(0.024)
    assert d.trip_end and d.new_trip and c2.trip_t == T0 + 9_000
    assert c2.ratio == pytest.approx(12_000 / AV) and c2.leader_entry == 50_200.0


def test_flip_still_closes_when_the_new_side_is_blocked_by_slippage():
    _, c = _open()
    d, c2 = decide(c, 0.04, sig("BTC", 4.0, -2.0, 50_200.0, T0 + 9_000, 2),
                   ctx(T0 + 9_500, 49_000.0), P, SPEC)  # vender 2,4 % por debajo del líder
    assert [a.kind for a in d.actions] == ["close"]
    assert d.skips[0].code == "deslizamiento" and "en contra" in d.note


def test_cascade_accumulates_below_minimum_and_stops_at_the_asset_cap():
    c, own, out = CoinCopy("BTC"), 0.0, []
    for i in range(60):  # el líder compra 0,01 BTC cada vez (5 USD a nuestra escala)
        start, end = round(i * 0.01, 2), round((i + 1) * 0.01, 2)
        s = sig("BTC", start, end, 50_000.0 + i, T0 + i * 1_000, i + 1)
        d, c = decide(c, own, s, ctx(T0 + i * 1_000 + 500, 50_000.0 + i), P, SPEC)
        for a in d.actions:
            own += a.side * a.qty
        out.append(d)
    assert out[0].skips[0].code == "bajo_minimo" and not out[0].actions  # 5 USD < 10 USD
    assert out[1].actions[0].qty == pytest.approx(0.0002)  # recupera lo acumulado: 10 USD
    assert own == pytest.approx(0.006)  # 0,6 BTC del líder × 0,01: sin tope todavía
    c2, own2 = CoinCopy("BTC"), 0.0
    for i, size in enumerate((10.0, 20.0, 30.0)):  # cascada grande: tope por moneda (40 %)
        s = sig("BTC", size - 10.0, size, 50_000.0, T0 + i, i + 1)
        d, c2 = decide(c2, own2, s, ctx(T0 + i + 500), P, SPEC)
        for a in d.actions:
            own2 += a.side * a.qty
    assert own2 * 50_000 <= 0.4 * 10_000 + 1e-6 and "tope por moneda" in c2.note
    assert d.skips[0].code == "tope"


def test_below_minimum_order_is_not_sent_but_a_full_close_is():
    d, c = decide(CoinCopy("BTC"), 0.0, sig("BTC", 0.0, 0.01, 50_000.0, T0, 1),
                  ctx(T0 + 500), P, SPEC)
    assert not d.actions and d.skips[0].code == "bajo_minimo" and "mínimo" in d.note
    d2, _ = decide(c, 0.0001, sig("BTC", 0.01, 0.0, 50_000.0, T0 + 9_000, 2),
                   ctx(T0 + 9_500), P, SPEC)
    assert [a.kind for a in d2.actions] == ["close"]  # reduce-only: exento del mínimo
    strict = CopyParams(close_below_min=False)
    d3, _ = decide(c, 0.0001, sig("BTC", 0.01, 0.0, 50_000.0, T0 + 9_000, 2),
                   ctx(T0 + 9_500), strict, SPEC)
    assert d3.trip_end and [a.kind for a in d3.actions] == ["close"]  # el cierre del líder manda


def test_reduce_below_minimum_is_skipped_and_explained():
    _, c = _open()
    d, _ = decide(c, 0.04, sig("BTC", 4.0, 3.99, 50_000.0, T0 + 9_000, 2),
                  ctx(T0 + 9_500), P, SPEC)
    assert not d.actions and d.skips[0].code == "bajo_minimo" and d.skips[0].kind == "reduce"


def test_never_reduces_on_an_increase_nor_increases_on_a_reduce():
    _, c = _open()
    blocked = decide(c, 0.04, sig("BTC", 4.0, 8.0, 50_000.0, T0 + 9_000, 2),
                     ctx(T0 + 9_500, 52_000.0), P, SPEC)  # aumento omitido por deslizamiento
    d, c2 = blocked
    assert not d.actions and d.skips[0].code == "deslizamiento"
    d2, _ = decide(c2, 0.04, sig("BTC", 8.0, 6.0, 50_000.0, T0 + 19_000, 3),
                   ctx(T0 + 19_500), P, SPEC)  # objetivo 0,06 > propia 0,04: no se compra
    assert not d2.actions and d2.note == c2.note


def test_preexisting_trip_is_not_copied_until_the_leader_goes_flat():
    c = CoinCopy("BTC", leader=4.0, leader_entry=48_000.0, trip_t=T0 - 1,
                 excluded="preexistente")
    d, c2 = decide(c, 0.0, sig("BTC", 4.0, 6.0, 50_000.0, T0, 1), ctx(T0 + 500), P, SPEC)
    assert not d.actions and d.skips[0].code == "excluido:preexistente"
    d2, c3 = decide(c2, 0.0, sig("BTC", 6.0, 0.0, 50_000.0, T0 + 1_000, 2),
                    ctx(T0 + 1_500), P, SPEC)
    assert not d2.actions and c3.excluded is None and c3.trip_t is None
    d3, _ = decide(c3, 0.0, sig("BTC", 0.0, 2.0, 50_000.0, T0 + 2_000, 3), ctx(T0 + 2_500),
                   P, SPEC)
    assert d3.actions[0].kind == "open"  # el viaje siguiente sí se copia


def test_missed_close_closes_own_and_skips_the_unseen_trip():
    _, c = _open()  # la copia cree que el líder tiene +4
    d, c2 = decide(c, 0.04, sig("BTC", -2.0, -3.0, 50_000.0, T0 + 9_000, 2),
                   ctx(T0 + 9_500), P, SPEC)
    assert [a.kind for a in d.actions] == ["close"] and c2.excluded == "apertura_no_vista"


def test_no_account_value_or_price_or_spec_is_a_reasoned_skip():
    s = sig("BTC", 0.0, 4.0, 50_000.0, T0, 1)
    assert decide(CoinCopy("BTC"), 0.0, s, ctx(T0, av=None), P, SPEC)[0].skips[0].code == \
        "sin_cuenta"
    assert decide(CoinCopy("BTC"), 0.0, s, ctx(T0, px=None), P, SPEC)[0].skips[0].code == \
        "sin_precio"
    assert decide(CoinCopy("BTC"), 0.0, s, ctx(T0), P, ExchangeSpec())[0].skips[0].code == \
        "sin_especificacion"


def test_exchange_spec_rounds_toward_zero():
    spec = ExchangeSpec.from_meta({"universe": [{"name": "BTC", "szDecimals": 5},
                                                {"name": "DOGE", "szDecimals": 0}]})
    assert spec.round_down("BTC", 0.123456789) == 0.12345
    assert spec.round_down("DOGE", 9.99) == 9.0 and spec.round_down("XYZ", 5.0) == 0.0


def test_unseen_fills_follow_the_net_change_since_the_last_view():
    """Caso real 2026-10-16: la copia vio +2 177; tras un corte la primera señal es un aumento
    113 → 238. Respecto de lo visto el líder redujo: se reduce, no se mantiene."""
    _, c = _open(size=40.0)  # propia 0,4 BTC
    d, c2 = decide(c, 0.4, sig("BTC", 2.0, 4.0, 50_000.0, T0 + 9_000, 2),
                   ctx(T0 + 9_500, equity=100_000.0), P, SPEC)
    (a,) = d.actions
    assert a.kind == "reduce" and a.target == pytest.approx(0.04) and c2.leader == 4.0
    assert "no vistas" in c2.note
