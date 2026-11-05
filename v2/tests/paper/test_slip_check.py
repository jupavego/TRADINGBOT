"""T136 (6), E4b: el deslizamiento del stop frente al libro capturado."""

from __future__ import annotations

import math

import pytest

from eim.paper import slip_check as sc

T0 = 1_793_800_000_000


def fill(side: int = 1, stop: float = 80_000.0, qty: float = 0.02, slip_usd: float = 1.0,
         tid: str = "a") -> sc.StopFill:
    return sc.StopFill(id=tid, profile="moderado", side=side, qty=qty, stop=stop,
                       notional=qty * stop, slip_usd=slip_usd, exit_t=T0)


def touch(bid: float, ask: float, t: int = T0, bid_q: float = 5.0,
          ask_q: float = 5.0) -> sc.Touch:
    return sc.Touch(t_ms=t, bid_p=bid, bid_q=bid_q, ask_p=ask, ask_q=ask_q)


def test_model_bps_is_the_slip_over_the_notional():
    f = fill(qty=0.02, stop=80_000.0, slip_usd=1.6)       # nocional 1 600 USDT
    assert sc.model_bps(f) == pytest.approx(10.0)
    assert math.isnan(sc.model_bps(fill(qty=0.0, stop=0.0)))


def test_a_long_crosses_against_the_bid_and_a_short_against_the_ask():
    """Un largo cierra vendiendo; el signo positivo es siempre «peor para el operador»."""
    long_ = sc.crossing(fill(side=1, stop=80_000.0), touch(bid=79_992.0, ask=80_000.0))
    assert long_["touch"] == 79_992.0
    assert long_["real_bps"] == pytest.approx(1e4 * 8 / 80_000)
    short = sc.crossing(fill(side=-1, stop=80_000.0), touch(bid=80_000.0, ask=80_008.0))
    assert short["touch"] == 80_008.0
    assert short["real_bps"] == pytest.approx(1e4 * 8 / 80_000)


def test_crossing_says_whether_the_touch_holds_the_quantity():
    assert sc.crossing(fill(qty=0.02), touch(79_990, 80_000, bid_q=1.0))["enough"] is True
    assert sc.crossing(fill(qty=5.0), touch(79_990, 80_000, bid_q=1.0))["enough"] is False


def test_crossing_with_an_empty_book_returns_nothing_instead_of_zero():
    out = sc.crossing(fill(), touch(bid=0.0, ask=0.0))
    assert out["touch"] is None and out["real_bps"] is None


def test_first_crossed_picks_the_first_instant_the_level_is_reached():
    f = fill(side=1, stop=80_000.0)
    win = [touch(80_050, 80_060, T0 + 1), touch(80_010, 80_020, T0 + 2),
           touch(79_995, 80_005, T0 + 3), touch(79_900, 79_910, T0 + 4)]
    got = sc.first_crossed(f, win)
    assert got is not None and got.t_ms == T0 + 3
    short = fill(side=-1, stop=80_000.0)
    assert sc.first_crossed(short, win).t_ms == T0 + 1       # el ask ya estaba por encima


def test_first_crossed_returns_none_when_the_book_never_got_there():
    f = fill(side=1, stop=70_000.0)
    assert sc.first_crossed(f, [touch(80_050, 80_060, T0 + 1)]) is None


def test_rows_report_why_a_stop_could_not_be_measured():
    f1, f2, f3 = fill(tid="sin"), fill(tid="lejos", stop=70_000.0), fill(tid="ok")
    books = {"lejos": [touch(80_050, 80_060)], "ok": [touch(79_990, 80_000)]}
    got = {r["id"]: r for r in sc.rows([f1, f2, f3], books)}
    assert got["sin"]["state"] == "sin cobertura" and got["sin"]["real_bps"] is None
    assert got["lejos"]["state"] == "el libro no llegó al nivel"
    assert got["ok"]["state"] == "medido" and got["ok"]["real_bps"] > 0


def test_rows_flag_when_the_model_falls_short():
    caro = fill(tid="caro", slip_usd=0.01)                  # el modelo supone casi nada
    books = {"caro": [touch(79_900, 79_910)]}               # el libro da 12,5 pb de hueco
    r = sc.rows([caro], books)[0]
    assert r["model_short"] is True
    assert r["real_bps"] > r["model_bps"]


def test_summary_does_not_conclude_without_coverage():
    out = sc.summary([{"state": "sin cobertura", "real_bps": None}])
    assert out["n_measured"] == 0
    assert out["verdict"] == "sin cobertura suficiente"
    assert out["model_short_share"] is None


def test_summary_refuses_to_conclude_below_thirty_stops():
    rows = sc.rows([fill(tid=f"t{i}", slip_usd=0.01) for i in range(10)],
                   {f"t{i}": [touch(79_900, 79_910)] for i in range(10)})
    out = sc.summary(rows)
    assert out["n_measured"] == 10
    assert out["verdict"] == "muestra insuficiente para concluir"
    assert out["model_short_share"] == pytest.approx(1.0)


def test_summary_says_the_model_falls_short_with_enough_stops():
    rows = sc.rows([fill(tid=f"t{i}", slip_usd=0.01) for i in range(40)],
                   {f"t{i}": [touch(79_900, 79_910)] for i in range(40)})
    out = sc.summary(rows)
    assert out["verdict"] == "el modelo se queda corto"
    assert out["diff_bps_median"] > 0
    assert out["enough_at_touch_share"] == pytest.approx(1.0)


def test_summary_says_the_model_holds_when_it_is_generous():
    rows = sc.rows([fill(tid=f"t{i}", slip_usd=50.0) for i in range(40)],
                   {f"t{i}": [touch(79_999, 80_000)] for i in range(40)})
    out = sc.summary(rows)
    assert out["verdict"] == "el modelo aguanta"
    assert out["model_short_share"] == pytest.approx(0.0)


def test_rows_found_separates_no_coverage_from_never_reached():
    """La versión que recibe el cruce ya localizado (la que usa el script, con SQL)."""
    f1, f2, f3 = fill(tid="sin"), fill(tid="lejos"), fill(tid="ok")
    got = {r["id"]: r for r in sc.rows_found(
        [f1, f2, f3],
        {"sin": (None, 0), "lejos": (None, 1_200_000), "ok": (touch(79_990, 80_000), 900_000)})}
    assert got["sin"]["state"] == "sin cobertura" and got["sin"]["n_book"] == 0
    assert got["lejos"]["state"] == "el libro no llegó al nivel"
    assert got["lejos"]["n_book"] == 1_200_000
    assert got["ok"]["state"] == "medido" and got["ok"]["real_bps"] > 0


def test_rows_and_rows_found_agree():
    f = fill(tid="x")
    win = [touch(80_050, 80_060, T0 + 1), touch(79_990, 80_000, T0 + 2)]
    a = sc.rows([f], {"x": win})
    b = sc.rows_found([f], {"x": (sc.first_crossed(f, win), len(win))})
    assert a == b
