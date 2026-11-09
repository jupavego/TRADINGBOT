"""T143 — comparación emparejada maker/taker: conversión, contabilidad y criterio (sin red)."""

from __future__ import annotations

import pytest

from eim.backtest.params import ZERO_COSTS
from eim.data.timeframes import tf_ms
from eim.paper import maker_ab as ab
from eim.paper.engine import Path, simulate
from eim.paper.params import ExecParams
from tests.paper.helpers import M15, T0, bar, flat, idea, with_bar

ZERO = ExecParams(costs=ZERO_COSTS, funding_8h_assumed=0.0)
COSTS = ExecParams(funding_8h_assumed=0.0)


def above(price: float = 101.0, n: int = 20) -> list:
    """Velas planas por encima de 100: una límite en 100 nunca se llena."""
    return [bar(T0 + i * M15, price, price + 0.5, price - 0.5, price) for i in range(n)]


def leg(net_p: float = 0.0, filled: bool = True, reason: str = "x") -> ab.Leg:
    return ab.Leg(filled, reason, net=net_p, net_p=net_p)


# --- conversión -------------------------------------------------------------------------------

def test_to_limit_solo_cambia_como_se_entra():
    base = idea(side=1, sl=98.0, tp=104.0, hold_h=24.0)
    lim = ab.to_limit(base, 1.0)
    assert lim.kind == "limit" and lim.fill_ms == tf_ms(base.timeframe)
    for f in ("side", "sl", "tp", "entry", "hold_ms", "t", "strategy", "timeframe"):
        assert getattr(lim, f) == getattr(base, f)


def test_to_limit_escala_con_el_marco():
    base = idea()
    assert ab.to_limit(base, 2.0).fill_ms == 2 * tf_ms("1h")
    assert ab.to_limit(base, 0.5).fill_ms == tf_ms("1h") // 2


def test_el_paso_por_el_nivel_mueve_la_orden_en_contra_del_llenado():
    """En largos el nivel baja y en cortos sube: así hay que pasar, no rozar."""
    lo = ab.to_limit(idea(side=1, entry=100.0), 1.0, through_bps=10.0)
    sh = ab.to_limit(idea(side=-1, entry=100.0, sl=102.0, tp=96.0), 1.0, through_bps=10.0)
    assert lo.entry == pytest.approx(99.9)
    assert sh.entry == pytest.approx(100.1)


def test_el_paso_por_el_nivel_impide_un_llenado_que_solo_rozaba():
    cs = with_bar(above(), 1, 101, 101.5, 100.0, 101)      # toca 100 justo, no lo pasa
    base = idea(hold_h=1.0)
    assert simulate(ab.to_limit(base, 1.0), Path(cs), ZERO).status == "CERRADA"
    assert simulate(ab.to_limit(base, 1.0, 10.0), Path(cs), ZERO).reason == "NO_LLENADA"


# --- contabilidad en R ------------------------------------------------------------------------

def test_planned_risk_es_el_mismo_para_los_dos_brazos():
    base = idea(entry=100.0, sl=98.0)
    assert ab.planned_risk(base) == pytest.approx(0.02)
    assert ab.planned_risk(ab.to_limit(base, 1.0)) == pytest.approx(0.02)


def test_leg_de_una_cancelada_aporta_cero_y_no_cuenta_como_operacion():
    o = simulate(idea(kind="limit", entry=100.0, fill_h=0.5), Path(above()), ZERO)
    assert (o.status, o.reason) == ("CANCELADA", "NO_LLENADA")
    x = ab.leg_of(o, 0.02)
    assert (x.net_p, x.gross_p, x.cost_p) == (0.0, 0.0, 0.0)
    assert x.filled is False and x.won is False and x.reason == "NO_LLENADA"


def test_leg_de_una_cerrada_sin_costos_tiene_coste_cero():
    cs = with_bar(flat(20), 5, 100, 105, 99.5, 104.5)
    x = ab.leg_of(simulate(idea(), Path(cs), ZERO), 0.02)
    assert x.filled is True and x.cost_p == pytest.approx(0.0)
    assert x.net_p == pytest.approx(2.0) and x.won is True


def test_leg_descompone_el_coste_en_comision_desliz_y_funding():
    cs = with_bar(flat(20), 5, 100, 105, 99.5, 104.5)
    x = ab.leg_of(simulate(idea(), Path(cs), COSTS), 0.02)
    assert x.fee_p > 0.0
    assert x.cost_p == pytest.approx(x.fee_p + x.slip_p + x.fund_p)
    assert x.net_p == pytest.approx(x.gross_p - x.cost_p)


def test_el_denominador_planeado_no_depende_del_precio_de_llenado():
    """El R del motor cambia con el llenado; el `_p` no. Es lo que quita la inflación."""
    cs = with_bar(with_bar(flat(20), 1, 100, 100.2, 99.0, 99.5), 6, 100, 104.2, 99.8, 104)
    o = simulate(idea(kind="limit", entry=99.0, fill_h=2), Path(cs), ZERO)
    x = ab.leg_of(o, ab.planned_risk(idea()))       # riesgo planeado del padre: |100 − 98|/100
    assert o.fill == 99.0
    assert x.net == pytest.approx(5.0)              # riesgo realizado |99 − 98|/99 = 1,01 %
    assert x.net_p == pytest.approx(2.525, abs=1e-3)   # planeado 2 %: la mitad de inflado


# --- emparejamiento ---------------------------------------------------------------------------

def test_pair_up_empareja_y_la_no_llenada_cuenta_cero():
    ideas = [idea(hold_h=1.0, iid="a")]
    tk, mk, kept, dropped = ab.pair_up(ideas, Path(above()), ZERO, 0.5)
    assert dropped == 0 and kept == [0] and len(tk) == len(mk) == 1
    assert tk[0].filled is True                     # a mercado se entra siempre
    assert mk[0].filled is False and mk[0].net_p == 0.0


def test_pair_up_usa_el_mismo_denominador_en_los_dos_brazos():
    """El mercado se llena en la apertura (101) y la límite en su nivel (100): riesgos distintos."""
    cs = with_bar(with_bar(with_bar(flat(20), 0, 101, 101.5, 100.5, 101),
                           1, 101, 101.2, 99.5, 100), 6, 100, 104.2, 99.8, 104)
    tk, mk, _, _ = ab.pair_up([idea(iid="a")], Path(cs), ZERO, 2.0)
    assert tk[0].risk_planned == pytest.approx(mk[0].risk_planned) == pytest.approx(0.02)
    assert tk[0].risk == pytest.approx(3 / 101)      # el realizado sí difiere
    assert mk[0].risk == pytest.approx(0.02)
    # con el denominador del motor la límite parece el doble; con el común, la ventaja real
    assert (tk[0].net, mk[0].net) == (pytest.approx(1.0), pytest.approx(2.0))
    assert mk[0].net_p - tk[0].net_p == pytest.approx(0.515, abs=1e-3)


def test_pair_up_descarta_la_pareja_sin_resolver():
    ideas = [idea(hold_h=100.0, iid="a")]            # no cierra dentro del camino
    tk, mk, kept, dropped = ab.pair_up(ideas, Path(flat(20)), ZERO, 1.0)
    assert (dropped, kept, tk, mk) == (1, [], [], [])


def test_arm_stats_cuenta_por_intento_no_por_llenado():
    s = ab.arm_stats([leg(1.0), leg(0.0, filled=False, reason="NO_LLENADA")])
    assert s["intentos"] == 2 and s["llenadas"] == 1
    assert s["llenado_pct"] == pytest.approx(50.0)
    assert s["neto_r"] == pytest.approx(0.5)             # por intento: la no llenada divide
    assert s["neto_r_llenada"] == pytest.approx(1.0)     # por llenado: no divide
    assert s["acierto_pct"] == pytest.approx(100.0)
    assert s["no_llenada"] == 1


def test_arm_stats_sin_operaciones_no_revienta():
    s = ab.arm_stats([])
    assert s["intentos"] == 0 and s["llenadas"] == 0


# --- estadística y criterio -------------------------------------------------------------------

def test_paired_delta_es_emparejado():
    tk = [leg(0.0) for _ in range(200)]
    mk = [leg(0.2) for _ in range(200)]
    d = ab.paired_delta(tk, mk, draws=500)
    assert d["delta"] == pytest.approx(0.2)
    assert d["lo"] == pytest.approx(0.2) and d["hi"] == pytest.approx(0.2)


def test_paired_delta_con_ruido_devuelve_un_ic_que_abarca_cero():
    tk = [leg(float(i % 2)) for i in range(200)]
    mk = [leg(float((i + 1) % 2)) for i in range(200)]
    d = ab.paired_delta(tk, mk, draws=500)
    assert d["lo"] <= 0.0 <= d["hi"]


def _arms(costo_tk: float, costo_mk: float):
    return {"costo_r": costo_tk}, {"costo_r": costo_mk}


def test_verdict_adopta_solo_con_los_tres_criterios():
    tk, mk = _arms(0.15, 0.05)
    v = ab.verdict(tk, mk, {"delta": 0.03, "lo": 0.01, "hi": 0.05}, stable=True)
    assert v["adopta"] is True and v["costo_baja_r"] == pytest.approx(0.10)


def test_verdict_rechaza_si_el_coste_baja_poco():
    tk, mk = _arms(0.15, 0.13)
    v = ab.verdict(tk, mk, {"delta": 0.03, "lo": 0.01, "hi": 0.05}, stable=True)
    assert v["adopta"] is False and "el costo solo baja" in v["motivo"]


def test_verdict_rechaza_si_el_ic_toca_cero():
    """Un ΔE[R] positivo cuyo intervalo incluya 0 no basta: lo dice §4 del pre-registro."""
    tk, mk = _arms(0.15, 0.05)
    v = ab.verdict(tk, mk, {"delta": 0.03, "lo": -0.01, "hi": 0.07}, stable=True)
    assert v["adopta"] is False and "límite inferior no llega a 0" in v["motivo"]


def test_verdict_rechaza_si_el_signo_no_aguanta():
    tk, mk = _arms(0.15, 0.05)
    v = ab.verdict(tk, mk, {"delta": 0.03, "lo": 0.01, "hi": 0.05}, stable=False)
    assert v["adopta"] is False and "cambia entre plazos" in v["motivo"]


def test_by_year_usa_los_indices_conservados():
    ideas = [idea(t=T0, iid="a"), idea(t=T0 + 400 * 24 * 3_600_000, iid="b")]
    out = ab.by_year(ideas, [leg(0.0)], [leg(0.5)], [1])     # solo quedó la segunda idea
    assert len(out) == 1
    (year, s), = out.items()
    assert s["n"] == 1 and s["delta"] == pytest.approx(0.5) and year == "2026"
