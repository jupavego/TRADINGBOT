"""T100: calidad y resumen de una cadena de opciones (agente de prueba de la familia IV)."""

import pytest

from eim.options import black_scholes as bs
from eim.options.chain import Quote, analyze

S, T, R = 100.0, 0.25, 0.02


def _smile(k: float) -> float:
    return 0.25 + 0.4 * (k / S - 1) ** 2 - 0.15 * (k / S - 1)


def _chain(width: float = 0.02):
    out = []
    for k in range(70, 135, 5):
        for kind in ("call", "put"):
            mid = bs.price(S, k, T, R, _smile(k), kind)
            out.append(Quote(k, kind, mid * (1 - width / 2), mid * (1 + width / 2)))
    return out


def test_clean_chain_is_ok_and_recovers_the_smile():
    rep = analyze(_chain(), S, T, R)
    assert rep.status == "ok" and not rep.arbitrage and rep.n_crossed == 0
    fwd = S * 2.718281828459045 ** (R * T)
    assert rep.atm_iv == pytest.approx(_smile(fwd), abs=2e-3)
    assert rep.skew_90_110 == pytest.approx(_smile(0.9 * fwd) - _smile(1.1 * fwd), abs=5e-3)
    assert rep.skew_90_110 > 0                   # puts caras: sesgo bajista típico


def test_detects_crossed_wide_and_arbitrage():
    q = _chain()
    q[0] = Quote(70, "call", 40.0, 30.0)                         # cruzada
    q[2] = Quote(75, "call", 1.0, 3.0)                           # horquilla enorme
    i = next(j for j, x in enumerate(q) if x.strike == 100 and x.kind == "call")
    q[i] = Quote(100, "call", 20.0, 20.2)                        # rompe monotonía y paridad
    rep = analyze(q, S, T, R)
    assert rep.status == "degradado"
    assert rep.n_crossed == 1 and rep.n_wide == 1
    assert any("no decreciente" in a or "no convexa" in a for a in rep.arbitrage)
    assert any("paridad" in a for a in rep.arbitrage)


def test_empty_or_one_sided_chain_is_no_data():
    rep = analyze([Quote(100, "call", None, 2.0), Quote(105, "put", 0.0, 1.0)], S, T, R)
    assert rep.status == "no_data" and rep.atm_iv is None
