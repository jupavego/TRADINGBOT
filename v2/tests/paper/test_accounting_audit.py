"""Auditoría T106: deja PROBADO el comportamiento actual de las salidas y de la contabilidad.

No cambia lógica: fija lo que hoy ocurre para que T107 (liquidación simulada, una sola
definición de capital, drawdown acotado) y T109 (solo cierra el stop) tengan oráculo de partida.
Lo que estos tests fijan es un DEFECTO conocido, no el comportamiento deseado.
"""

from __future__ import annotations

from eim.paper.book import ProfileState, liq_price, run_profile
from eim.paper.engine import ExecParams, Outcome, Path, simulate
from eim.paper.feedback import Learner
from eim.paper.params import PROFILES
from eim.paper.summary import _max_dd_pct, profile_summary
from tests.paper.helpers import H1, M15, T0, flat, idea, with_bar

AGR = next(p for p in PROFILES if p.id == "agresivo")
MOD = next(p for p in PROFILES if p.id == "moderado")


def _blowup(k: int, t: int = T0) -> Outcome:
    """Largo con SL al 1 % cuyo hueco ejecuta el stop a 0,10 USDT (pérdida ≈ 100 × el riesgo)."""
    i = idea(side=1, entry=100.0, sl=99.0, tp=120.0, t=t, strategy=f"s{k}", conf=1.0,
             iid=f"s{k}:0")
    return Outcome(i, "CERRADA", "SL", t, 100.0, t + (k + 1) * H1, 0.10,
                   gross=(0.10 - 100.0) / 100.0, r=-99.9)


def test_sin_liquidacion_el_capital_queda_negativo_y_el_dd_pasa_de_100():
    """Hoy no hay liquidación ni suelo: `book._close` resta el PnL y la curva se vuelve negativa,
    así que `_max_dd_pct` = (pico − eq)/pico puede pasar del 100 % (el panel mostró 1204 %)."""
    outs = [_blowup(k) for k in range(3)]       # el tope del 3 % por dirección solo deja 3
    st = run_profile(AGR, outs, Learner(outs), 0.004)
    assert len(st.trades) == 3
    assert st.equity < 0                                    # capital imposible en una cuenta real
    # la liquidación se informa pero no se aplica: la salida (0,10) está muy por debajo
    assert liq_price(1, 100.0, st.trades[0]["leverage"], 0.004) > 0.10
    assert _max_dd_pct(st.curve) > 1.0
    sm = profile_summary(st, Learner(outs), [], T0 + 9 * H1, 0.004)
    assert sm["max_dd_pct"] > 1.0 and sm["return_pct"] < -1.0


def test_con_capital_negativo_frena_entradas_pero_nadie_cierra():
    """Tras arruinar la cuenta, el freno por drawdown pausa las ENTRADAS (`caps.Brake`), pero la
    posición ya abierta sigue abierta: ni el freno ni el tope por dirección cierran nada."""
    abierta = Outcome(idea(t=T0, strategy="v", conf=1.0, iid="v:0"), "ABIERTA", "", T0, 100.0,
                      None, None, gross=-0.01, r=-0.5, mark=99.0)
    outs = [abierta, *(_blowup(k) for k in range(3)), _blowup(9, T0 + 10 * H1)]
    st = run_profile(AGR, outs, Learner(outs), 0.004)
    assert len(st.trades) == 2 and st.equity < 0   # la abierta ocupa cupo de riesgo
    tardia = [e["text"] for e in st.events if e["cat"] == "rechazada" and e["idea"] == "s9:0"]
    assert len(tardia) == 1 and tardia[0].startswith("freno por drawdown")
    assert st.brake.activations == 1
    assert list(st.slots) == ["v:0"]              # la abierta nunca se cerró
    assert not [e for e in st.events if e["cat"] in ("sl", "tp", "be", "tiempo")
                and e["idea"] == "v:0"]


def test_balance_y_equity_son_dos_bases_distintas():
    """`return_pct` usa `equity` (realizado + flotante) mientras «Saldo de la cartera» muestra
    `balance` (solo realizado): mezclar las dos columnas da filas imposibles."""
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
