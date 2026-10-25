"""T118: una sola base de capital (panel = motor = libro fijo) y el motivo real de cada rechazo.

La serie conocida: tres operaciones en vivo seguidas, sin costos, con riesgo fijo del 1 % y peso 1:
+2 %, −1 % y +1,5 % sobre el nocional. Con capital inicial 10 000 USDT el motor dimensiona con
10 000 → 10 200 → 10 098 y el capital final es 10 249,47; el panel, el motor y el libro fijo
tienen que decir exactamente eso. Todo SIMULADO.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from eim.data.paper_store import PaperStore
from eim.paper import ledger
from eim.paper.account import capital
from eim.paper.book import ProfileState, run_profile
from eim.paper.caps import CapParams
from eim.paper.engine import Outcome
from eim.paper.feedback import FeedbackParams, Learner
from eim.paper.params import ExecParams, ProfileParams
from eim.paper.policy import decide
from eim.paper.summary import profile_summary
from eim.paper.vetoes import CAPITAL_CODES
from tests.paper.helpers import H1, T0, idea
from tests.paper.test_account import RUIN, _gap

FIXED = FeedbackParams(observe_w=1.0, w_min=1.0, w_max=1.0, gain=0.0)     # peso 1 siempre
AUD = ProfileParams(id="auditoria", name="Auditoría", description="serie conocida (T118)",
                    risk_pct=0.01, max_leverage=10, max_open=1, min_conf=0.0, min_rr=0.0,
                    families=frozenset({"consenso"}), allow_hedge=False, follow_synthesis=False,
                    max_cost_r=10.0,
                    feedback=FIXED)
GROSS = (0.02, -0.01, 0.015)
BASES = (10_000.0, 10_200.0, 10_098.0)          # capital con el que se dimensiona cada una
AFTER = (10_200.0, 10_098.0, 10_249.47)         # capital realizado tras cada cierre


def _series(gross=GROSS) -> list[Outcome]:
    out = []
    for k, g in enumerate(gross):
        t = T0 + k * 10 * H1
        i = replace(idea(t=t, strategy=f"s{k}", conf=1.0, iid=f"s{k}:{t}", sl=99.0, tp=103.0),
                    origin="vivo")
        out.append(Outcome(i, "CERRADA", "TP" if g > 0 else "SL", t, 100.0, t + 5 * H1,
                           100.0 * (1 + g), gross=g, r=g / 0.01))
    return out


def test_panel_motor_y_libro_fijo_salen_de_la_misma_base():
    outs = _series()
    st = run_profile(AUD, outs, Learner(outs), 0.004)
    # motor: dimensiona con el capital realizado del instante de la señal
    approved = [d for d in st.decisions if d.approved]
    assert [d.equity for d in approved] == pytest.approx(BASES, rel=1e-12)
    assert [d.risk_usd for d in approved] == pytest.approx([b * 0.01 for b in BASES], rel=1e-12)
    # panel: la cuenta que se muestra es la misma lectura (`account.capital`)
    sm = profile_summary(st, Learner(outs), [], T0 + 40 * H1, 0.004)
    assert sm["balance"] == sm["equity"] == capital(st).balance == pytest.approx(AFTER[-1])
    assert sm["available"] == capital(st).available == sm["balance"]
    assert sm["n_closed"] == 3 and sm["counts"]["by_origin"] == {"vivo": 3}
    # libro fijo: guarda el capital antes y después de cada cierre, igual que el libro
    ps = PaperStore(":memory:")
    ledger.ensure(ps)
    assert ledger.record(ps, ledger.rows_from_view("X", outs, {AUD.id: st}, ExecParams(),
                                                   T0 + 40 * H1)) == 3 + 3   # perfil + sombra
    rows = sorted(ledger.query(ps, "X", "perfil"), key=lambda r: r["exit_t"])
    assert [r["capital_before"] for r in rows] == pytest.approx(BASES, rel=1e-12)
    assert [r["capital_after"] for r in rows] == pytest.approx(AFTER, rel=1e-12)
    assert len(rows) == sm["counts"]["by_origin"]["vivo"]
    assert rows[-1]["capital_after"] == sm["balance"]
    (rec,) = ledger.reconcile(rows, {AUD.id: st}).values()
    assert rec["match"] and rec["rows"] == rec["view_live"] == 3 and not rec["differ"]
    assert rec["capital_after"] == rec["view_capital_after"] == sm["balance"]
    ps.close()


def test_la_conciliacion_delata_una_vista_recalculada_con_otro_capital():
    """Mismas operaciones, otro capital inicial: la vista ya no es la historia del libro fijo."""
    outs = _series()
    st = run_profile(AUD, outs, Learner(outs), 0.004)
    ps = PaperStore(":memory:")
    ledger.ensure(ps)
    ledger.record(ps, ledger.rows_from_view("X", outs, {AUD.id: st}, ExecParams(), T0))
    other = run_profile(AUD.model_copy(update={"initial_equity": 5_000.0}), outs,
                        Learner(outs), 0.004)
    rows = ledger.query(ps, "X", "perfil")
    (rec,) = ledger.reconcile(rows, {AUD.id: other}).values()
    assert not rec["match"] and rec["differ"] == 3 and rec["outside"] == 0
    assert rec["capital_after"] == pytest.approx(AFTER[-1])
    assert rec["view_capital_after"] == pytest.approx(AFTER[-1] / 2)
    # y una operación del libro que la vista ya no tiene sale como «fuera», con su ventana
    (rec,) = ledger.reconcile(rows, {AUD.id: run_profile(AUD, outs[:2], Learner(outs[:2]),
                                                         0.004)}).values()
    assert rec["outside"] == 1 and rec["outside_from"] == rec["outside_to"] == outs[2].exit_t
    ps.close()


def test_libro_fijo_anterior_a_t118_se_migra_sin_tocar_sus_filas():
    ps = PaperStore(":memory:")
    old = [c for c in ledger.COLS if c not in ledger.NEW_COLS]
    types = [t for c, t in zip(ledger.COLS, ledger._TYPES, strict=True) if c not in ledger.NEW_COLS]
    ps.execute("CREATE TABLE paper_ledger (" + ", ".join(f"{c} {t}" for c, t in
                                                         zip(old, types, strict=True)) + ")")
    outs = _series()
    st = run_profile(AUD, outs, Learner(outs), 0.004)
    first = run_profile(AUD, outs[:1], Learner(outs[:1]), 0.004)     # el libro de entonces
    rows = ledger.rows_from_view("X", outs[:1], {AUD.id: first}, ExecParams(), T0)
    ps.executemany(f"INSERT INTO paper_ledger VALUES ({', '.join('?' * len(old))})",
                   [r[:len(old)] for r in rows])
    ledger.ensure(ps)                                  # añade las columnas; no reescribe nada
    assert ledger.record(ps, ledger.rows_from_view("X", outs, {AUD.id: st}, ExecParams(), T0)) > 0
    got = {r["idea_id"]: r for r in ledger.query(ps, "X", "perfil")}
    assert got[outs[0].idea.id]["capital_after"] is None           # fila vieja: tal como estaba
    assert got[outs[1].idea.id]["capital_after"] == pytest.approx(AFTER[1])
    ps.close()


def test_rechazo_por_capital_nunca_sale_como_tope_ni_como_freno():
    """El caso de T106: con la cuenta sin capital y los topes encendidos, el motivo registrado
    era «tope de riesgo abierto por dirección». Ahora es la cuenta agotada, con su código."""
    caps = CapParams(max_dir_risk=0.03, dd_brake=0.05)
    p = RUIN.model_copy(update={"caps": caps})
    outs = [_gap(k, T0 + k * 30 * H1) for k in range(12)]
    st = run_profile(p, outs, Learner(outs), 0.004)
    assert st.exhausted_t is not None
    after = [e for e in st.events if e["cat"] == "rechazada" and e["t"] > st.exhausted_t]
    assert after and {e["code"] for e in after} <= CAPITAL_CODES
    assert all(e["text"].startswith("cuenta agotada") for e in after)
    assert st.rejected["cuenta_agotada"] == len(after)
    codes = {e["code"] for e in st.events if e["cat"] == "rechazada"}
    assert "tope_direccion" not in codes and codes <= CAPITAL_CODES | {"freno_drawdown"}
    assert profile_summary(st, Learner(outs), [], T0 + 400 * H1, 0.004)["counts"]["rejections"] \
        == st.rejected
    # y la decisión directa con capital 0 y el tope encendido: agotada, nunca «tope»
    st0 = ProfileState(p=p, equity=0.0)
    o = _gap(99, T0 + 999 * H1)
    j = Learner([o]).at(o.idea.sid, o.idea.t, p.feedback)
    d = decide(st0, o, j, j, "s99|x|largo", 0.004, None)
    assert not d.approved and d.code == "cuenta_agotada" and "tope" not in d.reason


def test_tope_y_freno_conservan_sus_codigos_con_capital_sano():
    from tests.paper.test_caps import MOD, _long_lived
    outs = [_long_lived(0, f"s{n}") for n in range(3)]
    st = run_profile(MOD.model_copy(update={"caps": CapParams(max_dir_risk=0.004)}), outs,
                     Learner(outs), 0.005)
    codes = {e["code"] for e in st.events if e["cat"] == "rechazada"}
    assert "tope_direccion" in codes and not codes & CAPITAL_CODES


def test_el_aprendizaje_por_filtro_saltado_solo_ve_operaciones_cerradas():
    """El motivo de un rechazo no entra en ningún aprendizaje: `floor_r` contiene exactamente el
    R de las operaciones que SÍ entraron por el mínimo de abiertas, por cada filtro saltado, y
    los pesos no dependen del texto ni del código de los rechazos."""
    p = RUIN.model_copy(update={"min_open": 1, "min_conf": 0.9, "max_open": 1,
                                "caps": CapParams(max_dir_risk=0.03, dd_brake=0.05)})
    outs = [replace(o, idea=replace(o.idea, conf=0.5)) for o in
            (_gap(k, T0 + k * 30 * H1) for k in range(12))]
    st = run_profile(p, outs, Learner(outs), 0.004)
    floor = [t for t in st.trades if t["floor"]]
    assert floor and st.rejected.get("confianza")      # hubo rechazos y entradas por el mínimo
    want: dict[str, list[float]] = {}
    for t in floor:
        for k in t["skipped"]:
            want.setdefault(k, []).append(t["r"])
    assert st.floor_r == want
