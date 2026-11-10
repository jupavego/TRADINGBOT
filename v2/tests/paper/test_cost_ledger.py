"""T143 (4): el costo vivido sale del libro fijo con el método del diagnóstico, con su `source`."""

from __future__ import annotations

import pytest

from eim.operation.report_costs import cost_lines
from eim.paper import cost_ledger as cl
from eim.paper import tf_gate
from eim.paper.params import ExecParams


def row(**kw) -> dict:
    base = {"scope": "perfil", "profile": "p1", "symbol": "BTCUSDT", "timeframe": "1h",
            "kind": "market", "exit_t": 1_000, "pnl_usdt": -10.0, "r": -1.0, "notional": 1_000.0,
            "fees": 0.7, "slip": 0.3, "funding": 0.0, "retro": False}
    return {**base, **kw}


def test_costo_en_r_usa_el_riesgo_reconstruido():
    c = cl.trade_cost(row())        # riesgo |−10| / |−1| = 10 USDT, costo 1 USDT
    assert c["cost_usdt"] == pytest.approx(1.0)
    assert c["cost_r"] == pytest.approx(0.1)
    assert c["cost_bps"] == pytest.approx(10.0)


def test_sombra_y_retro_no_cuentan():
    s = cl.summarize([row(), row(scope="sombra"), row(retro=True)])
    assert s["all"]["n"] == 1


def test_sin_riesgo_reconstruible_cuenta_en_usdt_y_no_en_r():
    s = cl.summarize([row(), row(pnl_usdt=0.0)])
    assert (s["all"]["n"], s["all"]["n_r"]) == (2, 1)
    assert s["all"]["cost_usdt"] == pytest.approx(2.0)
    assert s["all"]["cost_r_mean"] == pytest.approx(0.1)


def test_ventana_y_grupos_por_marco_y_tipo():
    rows = [row(exit_t=5, timeframe="4h", kind="limit"), row(exit_t=50), row(exit_t=500)]
    s = cl.summarize(rows, t0=10, t1=100)
    assert s["all"]["n"] == 1 and set(s["by_timeframe"]) == {"1h"}
    assert set(cl.summarize(rows)["by_kind"]) == {"limit", "market"}


def test_lleva_su_source_y_las_ultimas_primero():
    s = cl.summarize([row(exit_t=1), row(exit_t=2, profile="p2")])
    assert "paper_ledger" in s["source"]
    assert s["recent"][0]["profile"] == "p2"


def test_el_informe_semanal_trae_la_seccion_aunque_no_haya_operaciones():
    assert any("Costo medido" in x for x in cost_lines({}))
    txt = "\n".join(cost_lines(cl.summarize([row()])))
    assert "0.100" in txt and "Fuente:" in txt


def test_arranque_falla_con_umbral_no_positivo_y_registra_los_marcos():
    with pytest.raises(ValueError):
        tf_gate.check(ExecParams(tf_max_cost_r=0.0))
    lines = tf_gate.check(ExecParams())
    assert any(x.startswith("15m:") and "no opera" in x for x in lines)
    assert any(x.startswith("4h:") and "→ opera" in x for x in lines)


def test_retro_en_texto_del_csv_tambien_sale():
    s = cl.summarize([row(retro="False"), row(retro="True")])
    assert s["all"]["n"] == 1


def test_puerta_que_cierra_todos_los_marcos_avisa(caplog):
    import logging

    from tests.paper.test_tf_gate import out
    outs = [out(tf, 0.5) for tf in ("15m", "1h", "4h") for _ in range(60)]
    with caplog.at_level(logging.WARNING, logger="eim.paper.tf_gate"):
        rows, tradable = tf_gate.gate(("15m", "1h", "4h"), outs, ExecParams())
    assert tradable == [] and "ningún marco opera" in caplog.text
