"""T143 (5): el contrafactual aplica las tres palancas, y solo ellas, sobre lo vivido."""

from __future__ import annotations

import json

import pytest

from eim.paper.cost_whatif import apply, base, compare, shadow

FEES = json.dumps({"taker_fee": 0.0005, "maker_fee": 0.0002})


def row(**kw) -> dict:
    b = {"scope": "perfil", "retro": "False", "timeframe": "1h", "kind": "market",
         "pnl_usdt": "-10", "r": "-1", "notional": "1000", "fees": "1.0", "slip": "0.2",
         "funding": "0", "cost_params": FEES}
    return {**b, **kw}


def test_base_reconstruye_costo_y_bruto():
    b = base(row())                      # riesgo 10 USDT, costo 1,2 → 0,12 R
    assert b["cost"] == pytest.approx(0.12) and b["saving"] == pytest.approx(0.03)
    assert apply(b, "antes")["gross"] == pytest.approx(-0.88)


def test_maker_solo_ahorra_en_entradas_market_de_los_marcos_medidos():
    assert base(row(kind="limit"))["saving"] == 0.0
    b = base(row())
    assert apply(b, "sin_15m_maker")["cost"] == pytest.approx(0.09)
    assert apply(b, "sin_15m_maker", maker_tfs=("4h",))["cost"] == pytest.approx(0.12)


def test_riesgo_con_costo_escala_todo_por_uno_entre_uno_mas_costo():
    b = base(row())
    y = apply(b, "sin_15m_maker_riesgo")
    k = 1 / 1.09
    assert y["cost"] == pytest.approx(0.09 * k) and y["gross"] == pytest.approx(-0.88 * k)
    assert y["net"] == pytest.approx(y["gross"] - y["cost"])


def test_quince_minutos_sale_desde_el_primer_paso_y_retro_no_cuenta():
    rows = [row(), row(timeframe="15m"), row(retro="True")]
    c = compare(rows)
    assert c["lived"] == 2 and c["steps"]["antes"]["n"] == 2 and c["steps"]["sin_15m"]["n"] == 1


def test_sombra_por_marco_sin_retro():
    rows = [{"scope": "sombra", "retro": "False", "timeframe": "15m", "r": "-1"},
            {"scope": "sombra", "retro": "False", "timeframe": "15m", "r": "0"},
            {"scope": "sombra", "retro": "True", "timeframe": "15m", "r": "5"}]
    s = shadow(rows)
    assert s["15m"]["n"] == 2 and s["15m"]["net_r"] == pytest.approx(-0.5)
