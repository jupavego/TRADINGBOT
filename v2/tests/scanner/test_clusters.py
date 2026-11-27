"""T95 — duplicados y correlación: una apuesta, un representante y la exposición a la vista."""

from __future__ import annotations

import numpy as np

from eim.scanner import clusters

DAY = 86_400_000


def series(rets: np.ndarray) -> tuple[list[int], list[float]]:
    c = 100 * np.exp(np.cumsum(rets))
    return [k * DAY for k in range(len(c))], list(c)


def row(oid, iid, side="largo", pr=0.5):
    return {"opportunity_id": oid, "instrument_id": iid, "symbol": iid, "side": side,
            "priority": pr}


def test_legs_drop_the_settlement_currency_and_the_multiplier():
    assert clusters.legs("1000PEPEUSDT", "USDT", "1000PEPEUSDT") == {"PEPE"}
    assert clusters.legs("PEPEUSDT", "USDT", "PEPEUSDT") == {"PEPE"}
    assert clusters.legs("1INCHUSDT", "USDT", None) == {"1INCH"}
    assert clusters.legs("EURUSD", "USD", "EUR/USD") == {"EUR"}
    assert clusters.legs("EURJPY", "JPY", "EUR/JPY") == {"EUR", "JPY"}
    assert clusters.legs("BTCUSDT", "USDT") & clusters.legs("ETHUSDT", "USDT") == frozenset()


def test_correlated_and_same_underlying_collapse_into_one_bet():
    rng = np.random.default_rng(0)
    f = rng.normal(0, 0.02, 120)                        # un factor común
    s = {"A": series(f + rng.normal(0, 0.004, 120)),
         "B": series(f + rng.normal(0, 0.004, 120)),    # ρ alto con A
         "C": series(-f + rng.normal(0, 0.004, 120)),   # ρ alto negativo: corto C = largo A
         "D": series(rng.normal(0, 0.02, 120)),         # independiente
         "P1": series(rng.normal(0, 0.02, 120)), "P2": series(rng.normal(0, 0.02, 120))}
    rows = [row("op-a", "A", pr=0.9), row("op-b", "B", pr=0.8), row("op-c", "C", "corto", 0.7),
            row("op-d", "D", pr=0.6), row("op-p2", "P2", "corto", 0.5), row("op-p1", "P1", pr=0.4)]
    legs = {"A": frozenset({"AAA"}), "B": frozenset({"BBB"}), "C": frozenset({"CCC"}),
            "D": frozenset({"DDD"}), "P1": frozenset({"PEPE"}), "P2": frozenset({"PEPE"})}
    g = clusters.cluster(rows, legs, s)
    assert [x["representative"] for x in g] == ["op-a", "op-d", "op-p2"]
    big = g[0]
    assert {m["opportunity_id"] for m in big["members"]} == {"op-a", "op-b", "op-c"}
    e = big["exposure"]
    assert e["n"] == 3 and e["same_direction"] == 3 and e["hedging"] == 0   # corto C ≡ largo A
    assert e["largo"] == 2 and e["corto"] == 1
    assert 1.0 <= e["effective_bets"] < 1.2
    pepe = g[2]                                       # mismo subyacente, lados opuestos: cubre
    assert pepe["exposure"]["hedging"] == 1
    assert "comparten PEPE" in pepe["members"][1]["link"]
    assert g[1]["exposure"] == {"n": 1, "largo": 1, "corto": 0, "same_direction": 1,
                                "hedging": 0, "mean_abs_rho": 0.0, "effective_bets": 1.0}


def test_short_overlap_is_not_a_correlation():
    rng = np.random.default_rng(1)
    a = series(rng.normal(0, 0.02, 20))
    assert clusters.corr(a, a) is None                   # < MIN_OVERLAP velas comunes
    b = series(rng.normal(0, 0.02, 100))
    assert clusters.corr(b, b) > 0.999
