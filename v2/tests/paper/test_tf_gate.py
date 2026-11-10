"""T143 (3): la puerta de marcos por costo. El marco caro no opera y vuelve solo si abarata."""

from __future__ import annotations

from dataclasses import replace

import pytest

from eim.paper import tf_gate as g
from eim.paper.engine import Outcome
from eim.paper.params import ExecParams
from eim.paper.t143_config import EXEC_T143
from tests.paper.helpers import T0, idea

EP = EXEC_T143          # la puerta está encendida en la corrida aparte; T31 la tiene apagada
TFS = EP.timeframes
MAX, MIN_N = EP.tf_max_cost_r, EP.tf_cost_min_n


RISK = 0.02       # `Outcome.risk` es derivado: |llenado − SL| / llenado = |100 − 98| / 100


def out(tf: str, cost: float) -> Outcome:
    """Cerrada con un costo dado en R (el reparto entre comisión y desliz da igual)."""
    return Outcome(replace(idea(), timeframe=tf), "CERRADA", "SL", T0, 100.0, T0 + 1, 99.0,
                   fee_in=cost * RISK / 2, fee_out=cost * RISK / 2)


# --- el caso que motiva la tarea ---------------------------------------------------------------

def test_quince_minutos_no_opera_en_el_arranque_en_frio():
    """Sin sombra todavía, manda lo que midió T136: 0,157 R en 15 m, por encima del umbral."""
    assert g.admitted(TFS, {}, MAX, MIN_N) == ("1h", "4h")


def test_quince_minutos_no_puede_volver_con_el_costo_por_encima_del_umbral():
    """La prueba que pide la aceptación de T143: si 15 m operase caro, esto falla."""
    for cost in (0.15, 0.157, 0.2, 0.5):
        medido = {"15m": (cost, 10_000)}
        assert "15m" not in g.admitted(TFS, medido, MAX, MIN_N)
        assert "no opera" in g.why("15m", medido, MAX, MIN_N)


def test_quince_minutos_vuelve_solo_cuando_la_sombra_lo_mide_barato():
    medido = {"15m": (0.11, MIN_N)}
    assert g.admitted(TFS, medido, MAX, MIN_N) == TFS
    assert "sombra" in g.why("15m", medido, MAX, MIN_N)


def test_una_muestra_corta_no_reabre_el_marco():
    """Con pocas operaciones la media no decide: sigue mandando la medición de T136."""
    medido = {"15m": (0.01, MIN_N - 1)}
    assert "15m" not in g.admitted(TFS, medido, MAX, MIN_N)
    assert f"lleva {MIN_N - 1} de {MIN_N}" in g.why("15m", medido, MAX, MIN_N)


def test_la_puerta_no_es_solo_para_15m():
    """Si 1 h se encareciera saldría igual: la regla es el costo, no el nombre del marco."""
    assert g.admitted(TFS, {"1h": (0.18, 500)}, MAX, MIN_N) == ("4h",)


# --- la medición -------------------------------------------------------------------------------

def test_cost_by_tf_promedia_por_marco():
    outs = [out("15m", 0.20), out("15m", 0.10), out("4h", 0.08)]
    c = g.cost_by_tf(outs)
    assert c["15m"] == (pytest.approx(0.15), 2)
    assert c["4h"] == (pytest.approx(0.08), 1)


def test_cost_by_tf_ignora_lo_que_no_llego_a_operar():
    """Una idea sin riesgo o sin cerrar no tiene costo: contarla como 0 abarataría el marco."""
    i15 = replace(idea(), timeframe="15m")
    nada = Outcome(i15, "CANCELADA", "NO_LLENADA", T0, 0.0, None, None)
    abierta = Outcome(i15, "ABIERTA", "", T0, 100.0, None, None)
    c = g.cost_by_tf([out("15m", 0.20), nada, abierta])
    assert c["15m"] == (pytest.approx(0.20), 1)


def test_un_marco_sin_medicion_y_sin_linea_base_opera():
    """No se castiga lo que nadie midió: `5m` no está en T136 y entra hasta que se mida."""
    assert g.admitted(("5m",), {}, MAX, MIN_N) == ("5m",)
    assert "sin medición" in g.why("5m", {}, MAX, MIN_N)


# --- lo que ve el panel ------------------------------------------------------------------------

def test_report_expone_el_costo_su_procedencia_y_el_umbral():
    rows = g.report(TFS, {"4h": (0.05, 999)}, MAX, MIN_N)
    assert [r["timeframe"] for r in rows] == list(TFS)
    quince, cuatro = rows[0], rows[2]
    assert quince["admitted"] is False and quince["cost_r"] == pytest.approx(0.157)
    assert "T136" in quince["source"]                      # toda cifra expone su procedencia
    assert cuatro["admitted"] is True and "sombra (999" in cuatro["source"]
    assert all(r["max_cost_r"] == MAX for r in rows)


def test_el_umbral_sale_de_la_configuracion_no_del_codigo():
    """Cambiar `ExecParams` cambia la puerta: no hay ningún 0,15 escrito en la lógica."""
    suelto = ExecParams(tf_max_cost_r=0.30)
    assert g.admitted(TFS, {}, suelto.tf_max_cost_r, suelto.tf_cost_min_n) == TFS
    severo = ExecParams(tf_max_cost_r=0.10)
    assert g.admitted(TFS, {}, severo.tf_max_cost_r, severo.tf_cost_min_n) == ("4h",)


def test_con_la_configuracion_de_t31_la_puerta_esta_apagada():
    """Los valores por defecto son T31 hasta su cierre (◆ 2026-11-10): ningún marco se cierra."""
    rows, tradable = g.gate(("15m", "1h", "4h"), [out("15m", 0.9)] * 60, ExecParams())
    assert all(r["admitted"] for r in rows) and len(tradable) == 60
