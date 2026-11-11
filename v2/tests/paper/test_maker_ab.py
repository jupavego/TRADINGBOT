"""T143 — comparación emparejada maker/taker: conversión, contabilidad y criterio (sin red)."""

from __future__ import annotations

import numpy as np
import pytest

from eim.backtest.params import ZERO_COSTS
from eim.data.timeframes import tf_ms
from eim.paper import maker_ab as ab
from eim.paper.engine import Path, simulate
from eim.paper.params import ExecParams
from eim.paper.t143_config import EXEC_T143 as T143
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


def test_paired_delta_por_tandas_da_lo_mismo_que_de_una_vez(monkeypatch):
    """El bootstrap se saca por tandas para no pedir 8,4 GiB: el resultado no debe moverse."""
    rs = np.random.default_rng(7).normal(size=400)
    tk = [leg(0.0) for _ in rs]
    mk = [leg(float(x)) for x in rs]
    de_una = ab.paired_delta(tk, mk, draws=300)
    monkeypatch.setattr(ab, "CELLS", 1)          # una fila por tanda: el caso extremo
    por_tandas = ab.paired_delta(tk, mk, draws=300)
    assert por_tandas == de_una


def test_paired_delta_con_ruido_devuelve_un_ic_que_abarca_cero():
    tk = [leg(float(i % 2)) for i in range(200)]
    mk = [leg(float((i + 1) % 2)) for i in range(200)]
    d = ab.paired_delta(tk, mk, draws=500)
    assert d["lo"] <= 0.0 <= d["hi"]


def test_delta_split_separa_el_ahorro_de_la_abstencion():
    """Si el brazo maker se llena menos, parte de su ventaja es solo no haber operado."""
    tk = {"llenado_pct": 100.0, "neto_r_llenada": -0.20}
    mk = {"llenado_pct": 90.0}
    sp = ab.delta_split(tk, mk, {"delta": 0.05})
    assert sp["no_operar"] == pytest.approx(0.02)        # 10 % de los intentos × 0,20 R evitados
    assert sp["ejecucion"] == pytest.approx(0.03)
    assert sp["no_operar_pct"] == pytest.approx(40.0)
    assert sp["llenado_menos_pp"] == pytest.approx(10.0)


def test_delta_split_no_reparte_nada_si_los_dos_brazos_se_llenan_igual():
    tk = {"llenado_pct": 99.5, "neto_r_llenada": -0.20}
    mk = {"llenado_pct": 99.5}
    sp = ab.delta_split(tk, mk, {"delta": 0.04})
    assert sp["no_operar"] == pytest.approx(0.0)
    assert sp["ejecucion"] == pytest.approx(0.04)


def test_delta_split_con_un_brazo_ganador_no_premia_abstenerse():
    """Con E[R] por llenada positivo, dejar de operar RESTA: el signo debe invertirse."""
    tk = {"llenado_pct": 100.0, "neto_r_llenada": +0.30}
    mk = {"llenado_pct": 80.0}
    sp = ab.delta_split(tk, mk, {"delta": 0.0})
    assert sp["no_operar"] == pytest.approx(-0.06)
    assert sp["ejecucion"] == pytest.approx(+0.06)


def test_delta_split_con_total_cero_no_divide_por_cero():
    sp = ab.delta_split({"llenado_pct": 100.0, "neto_r_llenada": -0.2},
                        {"llenado_pct": 100.0}, {"delta": 0.0})
    assert sp["no_operar_pct"] is None


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


# --- lo adoptado: dónde se aplica y dónde no (T143 1b) ----------------------------------------
#
# La entrada maker NO va en los valores por defecto: T31 sigue con su configuración hasta cerrar
# y T143 corre en una mesa aparte (◆ del usuario 2026-11-10, `eim/paper/t143_config.py`). Estas
# pruebas usan esa configuración explícita, y la primera fija que por defecto está apagada.

def _kinds(tf: str, ep: ExecParams, **kw) -> set[str]:
    from eim.data.timeframes import tf_ms as _ms
    from eim.paper.catalog import generate_ideas
    from tests.paper.test_strategies import ctx_for, walk
    cs = walk(400)
    ideas = generate_ideas([ctx_for(c) for c in cs[300:340]], cs, "BTCUSDT", _ms(tf),
                           timeframe=tf, exec_params=ep, **kw)
    return {i.kind for i in ideas}


def test_por_defecto_la_entrada_sigue_siendo_a_mercado():
    """T31 no cambia de objeto a mitad de su medición: la adopción vive en la corrida aparte."""
    ep = ExecParams()
    assert ep.maker_entry_timeframes == ()
    assert "market" in _kinds("1h", ep)


def test_en_la_corrida_aparte_entra_en_los_marcos_medidos():
    """1 h y 4 h se midieron; 15 m no tiene ni una operación en el banco, así que no se toca."""
    ep = T143
    assert _kinds("1h", ep) == {"limit"}
    assert _kinds("4h", ep) == {"limit"}
    assert "market" in _kinds("15m", ep)


def test_la_vigencia_de_la_limite_es_la_del_pre_registro():
    """Una vela del marco de decisión, el plazo que decidió la medición."""
    from eim.data.timeframes import tf_ms as _ms
    from eim.paper.catalog import generate_ideas
    from tests.paper.test_strategies import ctx_for, walk
    cs = walk(400)
    ideas = generate_ideas([ctx_for(c) for c in cs[300:340]], cs, "BTCUSDT", _ms("1h"),
                           timeframe="1h", exec_params=T143)
    assert [i for i in ideas if i.fill_ms == _ms("1h")], "ninguna con la vigencia de una vela"


def test_un_catalogo_propio_no_se_convierte():
    """T139 y sus nulos traen su catálogo: cerraron con entradas a mercado y su control de
    entrada aleatoria se compara con ellas. Convertirlas cambiaría lo que ya midieron, incluso
    si alguien les pasara la mecánica de la corrida aparte."""
    from eim.paper.catalog import CATALOG
    propio = dict(list(CATALOG.items())[:3])
    assert "market" in _kinds("1h", T143, catalog=propio)


def test_se_puede_forzar_en_los_dos_sentidos():
    from eim.paper.catalog import CATALOG
    propio = dict(list(CATALOG.items())[:3])
    assert _kinds("1h", T143, catalog=propio, maker_entry=True) == {"limit"}
    assert "market" in _kinds("1h", T143, maker_entry=False)


def test_apagarlo_en_la_configuracion_lo_apaga_entero():
    assert "market" in _kinds("1h", T143.model_copy(update={"maker_entry_timeframes": ()}))
    assert "market" in _kinds("1h", T143.model_copy(update={"maker_entry_bars": 0.0}))
