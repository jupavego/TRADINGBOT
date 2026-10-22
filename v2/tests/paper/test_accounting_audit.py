"""Auditoría T106 (actualizada en T107): salidas y contabilidad de los perfiles.

T106 fijó aquí el DEFECTO: sin liquidación ni suelo, el mismo escenario dejaba el capital en
−19.970 USDT y el drawdown en 299,70 %. T107 lo corrigió, así que los dos primeros tests pasaron
a fijar el comportamiento CORRECTO (misma escena, mismas cifras de entrada) y se anota junto a
cada uno lo que daba antes. El inventario de vías de cierre y los tres tests de costos, bases y
recargas no cambian.
"""

from __future__ import annotations

import pytest

from eim.paper.account import liq_price, max_dd_pct
from eim.paper.book import ProfileState, run_profile
from eim.paper.engine import ExecParams, Outcome, Path, simulate
from eim.paper.feedback import Learner
from eim.paper.params import PROFILES
from eim.paper.summary import profile_summary
from tests.paper.helpers import H1, M15, T0, flat, idea, with_bar

AGR = next(p for p in PROFILES if p.id == "agresivo")
MOD = next(p for p in PROFILES if p.id == "moderado")


def _blowup(k: int, t: int = T0) -> Outcome:
    """Largo con SL al 1 % cuyo hueco ejecuta el stop a 0,10 USDT (pérdida ≈ 100 × el riesgo)."""
    i = idea(side=1, entry=100.0, sl=99.0, tp=120.0, t=t, strategy=f"s{k}", conf=1.0,
             iid=f"s{k}:0")
    return Outcome(i, "CERRADA", "SL", t, 100.0, t + (k + 1) * H1, 0.10,
                   gross=(0.10 - 100.0) / 100.0, r=-99.9)


def test_el_hueco_que_atraviesa_la_liquidacion_se_cierra_como_liquidacion():
    """T106 medía aquí capital −19.970 USDT y DD 299,70 % (tres huecos ejecutados a 0,10). Con la
    liquidación de T107 cada posición pierde su margen (1.000 USDT) y nada más: 7.000 USDT y
    30 % de DD. El precio de liquidación (90,40) ya no se atraviesa sin consecuencia."""
    outs = [_blowup(k) for k in range(3)]       # el tope del 3 % por dirección solo deja 3
    st = run_profile(AGR, outs, Learner(outs), 0.004)
    assert len(st.trades) == 3
    assert [t["reason"] for t in st.trades] == ["LIQUIDACION"] * 3
    assert st.equity == 7_000.0 and st.used == 0.0           # antes: −19.970 USDT
    liq = liq_price(1, 100.0, st.trades[0]["leverage"], 0.004)
    for t in st.trades:
        assert t["liq"] == liq > 0.10 and t["pnl"] == -t["margin"] == -1_000.0
        assert t["pnl_path"] < t["pnl"] and t["reason_path"] == "SL"   # el hueco pedía −9.990
    assert max_dd_pct(st.curve) == 0.3                        # antes: 2,997
    sm = profile_summary(st, Learner(outs), [], T0 + 9 * H1, 0.004)
    assert sm["max_dd_pct"] == 0.3 and sm["return_pct"] == pytest.approx(-0.3)
    assert sm["counts"]["liquidations"] == 3 and sm["dd"]["base"] == "equity"


def test_el_freno_por_drawdown_frena_entradas_pero_nadie_cierra():
    """Tras las liquidaciones, el freno por drawdown pausa las ENTRADAS (`caps.Brake`), pero la
    posición ya abierta sigue abierta: ni el freno ni el tope por dirección cierran nada.
    (T106 llegaba aquí con el capital en negativo; ahora el capital se queda en 8.000 USDT.)"""
    abierta = Outcome(idea(t=T0, strategy="v", conf=1.0, iid="v:0"), "ABIERTA", "", T0, 100.0,
                      None, None, gross=-0.01, r=-0.5, mark=99.0)
    outs = [abierta, *(_blowup(k) for k in range(3)), _blowup(9, T0 + 10 * H1)]
    st = run_profile(AGR, outs, Learner(outs), 0.004)
    assert len(st.trades) == 2 and st.equity == 8_000.0   # la abierta ocupa cupo de riesgo
    tardia = [e["text"] for e in st.events if e["cat"] == "rechazada" and e["idea"] == "s9:0"]
    assert len(tardia) == 1 and tardia[0].startswith("freno por drawdown")
    assert st.brake.activations == 1
    assert list(st.slots) == ["v:0"]              # la abierta nunca se cerró
    assert not [e for e in st.events if e["cat"] in ("sl", "tp", "be", "tiempo")
                and e["idea"] == "v:0"]


def test_balance_y_equity_son_dos_bases_distintas_y_la_vista_declara_cual_manda():
    """`return_pct` usa `equity` (realizado + flotante) y «Saldo realizado» muestra `balance`:
    son dos cifras distintas y mezclarlas daba filas imposibles. Desde T107 el resumen declara
    la base (`return_base`) y el flotante no puede pasar del margen."""
    cerr = Outcome(idea(t=T0, strategy="a", conf=1.0, iid="a:0"), "CERRADA", "SL", T0, 100.0,
                   T0 + H1, 98.0, gross=-0.02, r=-1.0)
    abierta = Outcome(idea(t=T0 + 2 * H1, strategy="b", conf=1.0, iid="b:1"), "ABIERTA", "",
                      T0 + 2 * H1, 100.0, None, None, gross=-0.30, r=-15.0, mark=70.0)
    outs = [cerr, abierta]
    st = run_profile(MOD, outs, Learner(outs), 0.005)
    sm = profile_summary(st, Learner(outs), [], T0 + 5 * H1, 0.005)
    assert sm["balance"] == st.equity                       # columna «Saldo de la cartera»
    assert sm["equity"] == st.equity + sm["upnl"] and sm["upnl"] < 0
    assert sm["return_pct"] == sm["equity"] / sm["initial"] - 1
    assert sm["return_pct"] < sm["balance"] / sm["initial"] - 1       # bases distintas
    assert sm["return_base"] == "equity" and sm["dd"]["base"] == "equity"
    assert sm["upnl"] >= -sum(x["margin"] for x in sm["positions"])   # margen aislado
    assert sm["curve"][-1][1] == sm["equity"]               # la curva termina en equity


def test_el_pnl_del_libro_ya_descuenta_comisiones_deslizamiento_y_funding():
    i = idea(t=T0, strategy="a", conf=1.0)
    o = Outcome(i, "CERRADA", "SL", T0, 100.0, T0 + H1, 98.0, fee_in=0.0005, fee_out=0.0005,
                slip=0.0003, funding=0.0001, gross=-0.02, r=-1.0)
    st = run_profile(MOD, [o], Learner([o]), 0.005)
    tr = st.trades[0]
    assert tr["pnl"] == tr["notional"] * o.net
    assert o.net == o.gross - o.fee_in - o.fee_out - o.slip - o.funding
    assert st.equity == MOD.initial_equity + tr["pnl"]      # única mutación del capital


def test_nadie_recarga_el_capital():
    """El capital solo cambia en `book._close`: ni recargas ni reinicios."""
    st = ProfileState(p=MOD, equity=MOD.initial_equity)
    assert not st.trades and st.equity == 10_000.0
    outs = [Outcome(idea(t=T0, strategy="a", conf=1.0), "CERRADA", "SL", T0, 100.0, T0 + H1,
                    98.0, gross=-0.02, r=-1.0)]
    st2 = run_profile(MOD, outs, Learner(outs), 0.005)
    assert st2.equity < 10_000.0 and len(st2.curve) == 2


def _sim(i, candles) -> Outcome:
    return simulate(i, Path(candles, (), M15), ExecParams())


def test_todas_las_vias_de_cierre_del_motor():
    """Inventario vivo: los siete motivos que hoy puede devolver `engine.simulate`."""
    base = flat(100)
    assert _sim(idea(), with_bar(base, 5, 100.0, 100.2, 97.0, 99.0)).reason == "SL"
    assert _sim(idea(), with_bar(base, 5, 100.0, 105.0, 99.8, 104.0)).reason == "TP"
    be = with_bar(with_bar(base, 5, 100.0, 102.5, 99.9, 102.0), 10, 100.2, 100.3, 100.0, 100.1)
    assert _sim(idea(), be).reason == "BE"                  # SL a entrada + costos + be_lock_r
    assert _sim(idea(), base).reason == "TIEMPO"             # 24 h sin tocar nada
    assert _sim(idea(sl=99.95), base).reason == "GEOMETRIA"  # SL a < min_risk_frac del llenado
    lim = idea(kind="limit", entry=95.0, fill_h=1.0)
    assert _sim(lim, base).reason == "NO_LLENADA"
    tp_first = with_bar(base, 1, 100.0, 104.5, 99.9, 104.0)
    assert _sim(lim, tp_first).reason == "OBJETIVO_SIN_LLENAR"
