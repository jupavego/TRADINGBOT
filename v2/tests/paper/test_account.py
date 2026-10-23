"""T107: liquidación simulada, suelo de la cuenta y coherencia de las cifras del panel.

Lo que estos tests prohíben: capital negativo, drawdown > 100 %, una pérdida mayor que el margen
de la posición y un perfil que siga abriendo con la cuenta agotada. Todo SIMULADO.
"""

from __future__ import annotations

import pytest

from eim.paper.account import capped, exhausted, liq_price, max_dd_pct
from eim.paper.book import run_profile
from eim.paper.engine import Outcome
from eim.paper.feedback import FeedbackParams, Learner
from eim.paper.params import PROFILES, ProfileParams
from eim.paper.summary import profile_summary
from tests.paper.helpers import H1, T0, idea, tp_mode

AGR = tp_mode(next(p for p in PROFILES if p.id == "agresivo"))  # salida TP (T109)
# Perfil de prueba sin apalancamiento: con el SL al 1 % y 0,5 % de riesgo, el margen de cada
# posición es la MITAD del capital, así que una liquidación se lleva medio capital y la cuenta se
# agota en siete cierres. Con los perfiles reales (hasta 10x) el margen es una fracción pequeña y
# el suelo solo llega tras decenas de pérdidas: esto prueba el estado «agotado» sin corridas
# largas, no un perfil que vaya a existir.
RUIN = ProfileParams(
    id="ruina", name="Ruina", description="prueba del suelo de la cuenta",
    risk_pct=0.005, max_leverage=1, max_open=8, min_conf=0.0, min_rr=0.0,
    families=frozenset({"consenso"}), allow_hedge=True, follow_synthesis=False,
    max_cost_r=10.0, feedback=FeedbackParams(observe_w=1.0, w_min=1.0, w_max=1.0, gain=0.0))


def _gap(k: int, t: int = T0, side: int = 1, mult: float = 100.0) -> Outcome:
    """Cierre con un hueco que ejecuta el stop muy por detrás del precio de liquidación."""
    entry, sl = 100.0, 100.0 - side
    ex = 0.10 if side > 0 else entry * mult
    i = idea(side=side, entry=entry, sl=sl, tp=entry + 20 * side, t=t, strategy=f"s{k}",
             conf=1.0, syn_bias=0.5 * side, iid=f"s{k}:0")
    return Outcome(i, "CERRADA", "SL", t, entry, t + (k + 1) * H1, ex,
                   gross=side * (ex - entry) / entry, r=-99.9)


def test_liquidacion_en_largo_pierde_el_margen_y_nada_mas():
    (o,) = [_gap(0)]
    st = run_profile(AGR, [o], Learner([o]), 0.004)
    (t,) = st.trades
    assert t["reason"] == "LIQUIDACION" and t["liq"] == pytest.approx(90.4)
    assert t["pnl"] == -t["margin"] and t["r"] == t["pnl"] / 100.0   # riesgo 100 USDT → −10 R
    assert st.equity == AGR.initial_equity - t["margin"] > 0
    (e,) = [e for e in st.events if e["cat"] == "liquidacion"]
    assert "se pierde el margen" in e["text"] and e["price"] == t["liq"]


def test_liquidacion_en_corto_pierde_el_margen_y_nada_mas():
    o = _gap(0, side=-1)
    st = run_profile(AGR, [o], Learner([o]), 0.004)
    (t,) = st.trades
    assert t["reason"] == "LIQUIDACION" and t["liq"] == pytest.approx(109.6)
    assert t["liq"] == liq_price(-1, 100.0, t["leverage"], 0.004)
    assert t["pnl"] == -t["margin"] and st.equity == AGR.initial_equity - t["margin"] > 0


def test_el_capital_nunca_queda_negativo_ni_el_drawdown_pasa_de_100():
    """Invariante de la cuenta: capital ≥ margen en uso ≥ 0 en cada punto de la curva."""
    outs = [_gap(k, T0 + k * 30 * H1) for k in range(12)]
    st = run_profile(RUIN, outs, Learner(outs), 0.004)
    assert len(st.trades) >= 3 and all(t["pnl"] >= -t["margin"] for t in st.trades)
    assert st.equity >= st.used >= 0.0
    assert all(eq >= 0.0 for _, eq in st.curve)
    assert max_dd_pct(st.curve) <= 1.0
    sm = profile_summary(st, Learner(outs), [], T0 + 400 * H1, 0.004)
    assert sm["max_dd_pct"] <= 1.0 and sm["return_pct"] >= -1.0
    assert sm["dd"] == {"pct": sm["max_dd_pct"], "base": "equity",
                        "from": st.curve[0][0], "to": sm["curve"][-1][0]}


def test_cuenta_agotada_deja_de_abrir_y_lo_dice():
    outs = [_gap(k, T0 + k * 30 * H1) for k in range(12)]
    st = run_profile(RUIN, outs, Learner(outs), 0.004)
    assert st.exhausted_t is not None and st.equity <= RUIN.initial_equity * 0.01
    (agotada,) = [e for e in st.events if e["cat"] == "cuenta"]
    assert "cuenta agotada" in agotada["text"] and agotada["t"] == st.exhausted_t
    # desde ese instante no se abre nada más: todo lo posterior se rechaza diciendo por qué
    after = [e for e in st.events if e["t"] > st.exhausted_t]
    assert after and not [e for e in after if e["cat"] in ("orden", "llenada")]
    assert all("cuenta agotada" in e["text"] or "capital insuficiente" in e["text"]
               for e in after if e["cat"] == "rechazada")
    sm = profile_summary(st, Learner(outs), [], T0 + 400 * H1, 0.004)
    assert sm["exhausted"] and sm["exhausted_t"] == st.exhausted_t
    assert sm["min_equity"] == RUIN.initial_equity * RUIN.min_equity_frac


def test_el_flotante_de_una_abierta_no_pasa_del_margen():
    """Una abierta cuya marca ya atravesó la liquidación no puede mostrar más pérdida que el
    margen (y el resumen lo dice en `liq_why`): si no, el equity del panel se iría a negativo."""
    o = Outcome(idea(t=T0, strategy="a", conf=1.0, iid="a:0"), "ABIERTA", "", T0, 100.0, None,
                None, gross=-0.95, r=-47.5, mark=5.0)
    st = run_profile(AGR, [o], Learner([o]), 0.004)
    sm = profile_summary(st, Learner([o]), [], T0 + 5 * H1, 0.004)
    (pos,) = sm["positions"]
    assert pos["upnl"] == -pos["margin"] and "atravesó la liquidación" in pos["liq_why"]
    assert sm["equity"] == sm["balance"] + sm["upnl"] > 0 and sm["return_pct"] > -1.0


def test_equity_balance_y_rentabilidad_son_coherentes():
    outs = [_gap(0), Outcome(idea(t=T0 + 2 * H1, strategy="b", conf=1.0, iid="b:0"), "ABIERTA",
                             "", T0 + 2 * H1, 100.0, None, None, gross=-0.01, r=-0.5, mark=99.0)]
    st = run_profile(AGR, outs, Learner(outs), 0.004)
    sm = profile_summary(st, Learner(outs), [], T0 + 9 * H1, 0.004)
    assert sm["balance"] == st.equity                       # realizado
    assert sm["equity"] == pytest.approx(sm["balance"] + sm["upnl"])
    assert sm["return_pct"] == pytest.approx(sm["equity"] / sm["initial"] - 1)
    assert sm["return_base"] == "equity" and sm["curve"][-1][1] == sm["equity"]
    assert sm["available"] == pytest.approx(sm["balance"] - sm["margin_used"] - sm["reserved"])


def test_el_recuento_de_operaciones_declara_origen_y_ventana():
    outs = [_gap(k) for k in range(3)]
    st = run_profile(AGR, outs, Learner(outs), 0.004)
    sm = profile_summary(st, Learner(outs), [], T0 + 9 * H1, 0.004)
    c = sm["counts"]
    assert c["closed"] == sm["n_closed"] == 3 and c["by_origin"] == {"backtest": 3}
    assert sum(c["by_origin"].values()) == c["closed"] and c["liquidations"] == 3
    assert c["from"] == st.trades[0]["exit_t"] and c["to"] == st.trades[-1]["exit_t"]
    assert "sin ventana" in c["scope"] and "T61" in c["scope"]


def test_el_tope_por_posicion_y_el_suelo_son_funciones_puras():
    assert capped(-50.0, 100.0, 1, 95.0, 90.0) == (-50.0, "")          # nada que liquidar
    pnl, why = capped(-500.0, 100.0, 1, 80.0, 90.0)                    # largo bajo la liquidación
    assert pnl == -100.0 and "atravesó la liquidación" in why
    pnl, why = capped(-500.0, 100.0, -1, 120.0, 110.0)                 # corto sobre su liquidación
    assert pnl == -100.0 and "atravesó la liquidación" in why
    pnl, why = capped(-500.0, 100.0, 1, None, None)                    # sin precio de referencia
    assert pnl == -100.0 and "supera el margen" in why
    assert exhausted(AGR, 101.0) is None and exhausted(AGR, 100.0)
    assert max_dd_pct([]) == 0.0 and max_dd_pct([(0, 100.0), (1, 50.0)]) == 0.5
