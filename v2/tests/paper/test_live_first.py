"""T182: lo vivo manda. Lo reconstruido no entra en los libros y en el aprendizaje solo pesa como
opinión inicial acotada, que se diluye con cada cierre vivo y nunca mira el futuro."""

from __future__ import annotations

from dataclasses import replace

import pytest

from eim.paper.book import run_profile
from eim.paper.engine import Outcome
from eim.paper.feedback import FeedbackParams, Learner, context_key, judge
from eim.paper.ladder_book import LadderRisk
from eim.paper.live_books import profile_books
from eim.paper.params import PROFILES, ExecParams
from eim.paper.prior import EMPTY, LiveFirstLearner, Prior, blend, judge_blend
from eim.paper.versioning import exec_fingerprint
from tests.paper.helpers import H1, T0, idea
from tests.paper.test_capital_base import AUD

P = FeedbackParams()          # vida media 40, n_min 8, prior_n 10
CAP = 8.0


def _out(k: int, r: float, origin: str, strategy: str = "s", t0: int = T0) -> Outcome:
    t = t0 + k * 10 * H1
    i = replace(idea(t=t, strategy=strategy, conf=1.0, iid=f"{strategy}:{origin}:{t}", sl=99.0,
                     tp=103.0), origin=origin)
    return Outcome(i, "CERRADA", "TP" if r > 0 else "SL", t, 100.0, t + 5 * H1,
                   100.0 * (1 + r / 100), gross=r / 100, r=r)


def _many(n: int, r: float, origin: str, start: int = 0) -> list[Outcome]:
    return [_out(start + k, r, origin) for k in range(n)]


def test_por_defecto_esta_apagado_y_no_cambia_la_huella_de_t31():
    ep = ExecParams()
    assert ep.live_first is False and ep.prior_cap == CAP
    on = ep.model_copy(update={"live_first": True, "prior_cap": 3.0})
    for tf in ep.timeframes:     # no cambia la sombra: las versiones de estrategia son las mismas
        assert exec_fingerprint(on, tf) == exec_fingerprint(ep, tf)


def test_sin_cierres_vivos_lo_reconstruido_vale_como_mucho_cap_operaciones():
    outs = _many(200, 1.0, "backtest")
    t = outs[-1].exit_t + 1
    j = LiveFirstLearner(outs, CAP).at(outs[0].idea.sid, t, P)
    assert j.n_live == 0 and j.prior == pytest.approx(CAP) and j.n == CAP
    assert j.m == pytest.approx(CAP * 1.0 / (CAP + P.prior_n))     # contraído hacia 0
    full = Learner(outs).at(outs[0].idea.sid, t, P)                  # antes: todo pesaba igual
    assert full.m > j.m and "n_live" not in full.to_json() and j.to_json()["n_live"] == 0


def test_el_prior_se_diluye_con_cada_cierre_vivo():
    past = _many(200, 1.0, "backtest")
    live = _many(int(P.half_life), 0.0, "vivo", start=300)
    t = live[-1].exit_t + 1
    j = LiveFirstLearner(past + live, CAP).at(live[0].idea.sid, t, P)
    assert j.n_live == len(live) and j.prior == pytest.approx(CAP / 2)   # una vida media: mitad


def test_si_lo_vivo_contradice_a_lo_reconstruido_gana_lo_vivo():
    past = _many(500, 2.0, "backtest")
    live = _many(30, -1.0, "vivo", start=600)
    t = live[-1].exit_t + 1
    sid = live[0].idea.sid
    assert Learner(past + live).at(sid, t, P).m > 0                  # antes mandaba lo viejo
    j = LiveFirstLearner(past + live, CAP).at(sid, t, P)
    assert j.m < 0 and j.prior < CAP


def test_el_prior_no_mira_el_futuro():
    past = _many(50, 1.0, "backtest", start=100)
    first_exit = past[0].exit_t
    lf = LiveFirstLearner(past, CAP)
    before = lf.at(past[0].idea.sid, first_exit - 1, P)
    assert before.prior == 0 and before.n == 0 and before.state == "observacion"
    assert lf.at(past[0].idea.sid, first_exit, P).prior > 0


def test_por_contexto_tambien_usa_el_prior():
    past = _many(100, -1.0, "backtest")
    lf = LiveFirstLearner(past, CAP)
    jc = lf.context_at(past[0].idea, past[-1].exit_t + 1, P)
    assert jc.n_live == 0 and jc.prior == pytest.approx(CAP) and jc.m < 0


def test_blend_sin_prior_o_con_tope_cero_es_lo_vivo_tal_cual():
    rs = [1.0, -0.5, 2.0, 0.3, -1.0, 0.7, 0.1, -0.2, 0.4]
    base = judge(rs, P)
    for pri, cap in ((EMPTY, CAP), ((50, 30.0, 30.0, 30.0), 0.0)):
        j = judge_blend(rs, pri, P, cap)
        assert (j.state, j.n) == (base.state, base.n)
        assert (j.weight, j.m) == pytest.approx((base.weight, base.m), rel=1e-12)
        assert j.n_live == len(rs) and j.prior == 0
    n, sw, *_rest, w = blend(0, (0.0, 0.0, 0.0), (3, 2.0, 2.0, 2.0), CAP, 40)
    assert w == 2.0 and sw == 2.0 and n == 2        # menos que el tope: entra entero


def test_la_memoria_propia_de_la_escalera_usa_el_prior_con_su_tiempo():
    i = idea(t=T0, strategy="s", iid="x")
    ck = context_key(i)
    closes = [("s@1h", ck, T0 + k * H1, 1.0) for k in range(100)]
    p = PROFILES[1]                                   # moderado (escalera)
    lr = LadderRisk(prior=Prior(closes), prior_cap=CAP)
    sid = "s@1h"
    assert lr.strategy(sid, p).prior == 0             # sin tiempo no hay prior (como antes)
    j = lr.strategy(sid, p, T0 + 200 * H1)
    assert j.n_live == 0 and j.prior == pytest.approx(CAP)
    assert lr.strategy(sid, p, T0 - 1).prior == 0     # todavía no había cerrado nada
    _, jc = lr.own(sid, ck, p, T0 + 200 * H1)
    assert jc.prior == pytest.approx(CAP)
    assert lr.log == []                               # el registro es de SUS cierres


def test_el_libro_registra_sus_cierres_para_servir_de_prior():
    lr = LadderRisk()
    i = idea(t=T0, strategy="s", iid="y")
    lr.closed(i, 0.8, 10.0, 10_010.0, T0 + 3 * H1, None, 10_000.0)
    assert lr.log == [(i.sid, context_key(i), T0 + 3 * H1, 0.8)]


def test_apagado_los_libros_son_los_de_siempre():
    outs = _many(3, 1.0, "backtest") + _many(3, 1.0, "vivo", start=10)
    ep = ExecParams()
    got = profile_books((AUD,), {AUD.id: outs}, Learner(outs), 0.004, None, ep)
    ref = run_profile(AUD, outs, Learner(outs), 0.004)
    assert [t["exit_t"] for t in got[AUD.id].trades] == [t["exit_t"] for t in ref.trades]
    assert len(ref.trades) == 6


def test_encendido_el_libro_solo_toma_lo_decidido_en_vivo():
    outs = _many(3, 1.0, "backtest") + _many(3, 1.0, "vivo", start=10)
    ep = ExecParams(live_first=True)
    lf = LiveFirstLearner(outs, ep.prior_cap)
    st = profile_books((AUD,), {AUD.id: outs}, lf, 0.004, None, ep)[AUD.id]
    assert len(st.trades) == 3 and {t["origin"] for t in st.trades} == {"vivo"}
    assert st.curve[0][0] == outs[3].idea.t           # la cuenta empieza con lo vivo
