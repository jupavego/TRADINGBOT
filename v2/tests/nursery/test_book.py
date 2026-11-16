"""Libro de la cantera (T168): cuentas, gemelos, puerta de costo y reglas sin futuro. Sin red."""

from __future__ import annotations

import pytest

from eim.nursery.book import Book, _Gate, make_twins, run_book, twin_seed
from eim.nursery.params import V6_MAX_COST_R, NurseryParams
from eim.nursery.prospect import load_prospects
from eim.nursery.signals import CONTROL, PROSPECT, accounts_for, signals
from eim.nursery.sim import simulate
from eim.nursery.summary import DAY_MS, account_summary, summarize
from eim.paper.tf_gate import BASELINE_COST_R
from tests.nursery.helpers import H1, M15, make_ctxs, make_path

PROSPECTS = load_prospects()


@pytest.fixture(scope="module")
def world():
    path = make_path(96 * 10)
    ctxs = {"15m": make_ctxs(path, M15), "1h": make_ctxs(path, H1, 12),
            "4h": make_ctxs(path, 4 * H1, 13)}
    return path, ctxs, run_book(ctxs, path, PROSPECTS)


def test_rules_never_see_the_next_bar(world):
    """La señal de la vela i es la misma aunque se cambien o se quiten las velas posteriores."""
    _, ctxs, _ = world
    accs = accounts_for(PROSPECTS)
    for tf in ("15m", "1h", "4h"):
        cs = ctxs[tf]
        cut = len(cs) // 2
        future = make_ctxs(make_path(96 * 10, seed=99), {"15m": M15, "1h": H1}.get(tf, 4 * H1),
                           seed=5)[cut:]
        for a in (x for x in accs if x.timeframe == tf):
            full = signals(a, cs, 4)
            assert signals(a, cs[:cut], 4) == full[:cut], a.id
            assert signals(a, cs[:cut] + future, 4)[:cut] == full[:cut], a.id


def test_every_rule_runs_and_some_trade(world):
    _, _, book = world
    traded = {e.account for e in book.entries}
    prospects = [a for a in book.accounts if a.kind == PROSPECT]
    assert len(prospects) == len(PROSPECTS) == 43
    assert len(traded & {a.id for a in prospects}) >= 30      # datos al azar: casi todas operan


def test_controls_do_not_count_as_prospects(world):
    path, ctxs, book = world
    s = summarize(book, path, ctxs["15m"][0])
    assert s["prospects"] == book.prospect_count == 43
    ctrl = [a for a in s["accounts"] if a["kind"] == CONTROL]
    assert s["controls"] == len(ctrl) > 0
    assert all(a["account"].startswith("control:agente_") and a["prospect"] is None for a in ctrl)


def test_each_balance_matches_its_net_trades(world):
    _, _, book = world
    p = book.params
    for a in book.accounts:
        es = book.of(a.id)
        total = sum(e.qty * e.trade.fill * (e.trade.gross - e.trade.fee_in - e.trade.fee_out
                                            - e.trade.slip - e.trade.funding)
                    for e in es if e.booked and e.trade.status == "CERRADA")
        assert abs(book.balance(a.id) - (p.initial_equity + total)) < 1e-6
        run = p.initial_equity
        for e in sorted(es, key=lambda e: e.t):
            assert abs(e.balance_before - run) < 1e-6          # mismo capital, encadenado
            if e.booked:
                assert abs(e.risk_usd - p.risk_pct * run) < 1e-9   # 1 % del saldo, sin pesos
            run += e.pnl_usd


def test_changing_a_param_is_a_new_prospect_without_trades():
    base = PROSPECTS[0]
    other = base.model_copy(update={"params": {**base.params, "majority": "> 2/3"}})
    assert other.fingerprint != base.fingerprint and other.account != base.account
    path = make_path(96 * 4)
    ctxs = {base.timeframe: make_ctxs(path, H1)}
    late = int(ctxs[base.timeframe][-10]["t"])
    book = run_book(ctxs, path, (base, other), registered={other.account: late})
    assert all(e.t >= late for e in book.of(other.account))
    assert book.of(base.account) and not set(map(id, book.of(base.account))) & set(
        map(id, book.of(other.account)))


def test_twins_are_reproducible_and_blind_to_prices(world):
    path, _, book = world
    e = next(x for x in book.entries if x.twins is not None)
    again = make_twins(e.order, e.trade, e.account, path, book.params, 8 * H1)
    assert again == e.twins and e.twins.k == 200
    assert twin_seed(168, e.account, e.t) == twin_seed(168, e.account, e.t)
    for s in (1, -1):        # ningún gemelo sigue vivo después de la operación real
        tw = simulate(e.order.twin(s, e.trade.exit_t), path, book.params.exec)
        assert tw.exit_t is None or tw.exit_t <= e.trade.exit_t + int(path.step)
    assert abs(e.d_r - (e.trade.r - e.twins.mean_r)) < 1e-12


def test_twins_do_not_change_if_the_path_after_the_exit_changes(world):
    path, _, book = world
    e = next(x for x in book.entries if x.twins is not None and x.trade.exit_t
             < int(path.t[-1]) - 8 * H1)
    cut = int((path.t <= e.trade.exit_t + int(path.step)).sum()) + 1
    short = make_path(len(path.t))
    for k in ("t", "o", "h", "l", "c"):
        getattr(short, k)[:cut] = getattr(path, k)[:cut]
    short.ft, short.fr = path.ft, path.fr
    assert make_twins(e.order, e.trade, e.account, short, book.params, 8 * H1) == e.twins


def test_cost_gate_closes_one_timeframe_for_everyone_and_logs_it():
    accs = accounts_for(PROSPECTS)
    events: list[dict] = []
    g = _Gate(NurseryParams(), events, accs)
    for k in range(60):
        g.push("15m", 1000 + k, 0.40)
        g.push("1h", 1000 + k, 0.05)
    assert g.open_at("1h", 5000) and not g.open_at("15m", 5000)
    ev15 = [e for e in events if e["timeframe"] == "15m"][-1]
    ids15 = {a.id for a in accs if a.timeframe == "15m"}
    assert ev15["after"] == "cerrado" and set(ev15["accounts"]) == ids15
    assert any(i.startswith("control:") for i in ev15["accounts"])     # controles incluidos
    assert {"t", "value_r", "threshold_r", "before", "after", "source"} <= set(ev15)


def test_closed_gate_books_nothing_but_keeps_measuring(world):
    path, ctxs, _ = world
    np_ = NurseryParams(exec=NurseryParams().exec.model_copy(
        update={"tf_max_cost_r": 1e-6, "tf_cost_min_n": 1}))
    book = run_book(ctxs, path, PROSPECTS, np_)
    shut = [e for e in book.events if e["kind"] == "puerta_costo" and e["after"] == "cerrado"]
    assert {e["timeframe"] for e in shut} == {"15m", "1h", "4h"}
    for tf in ("1h", "4h"):
        t_shut = min(e["t"] for e in shut if e["timeframe"] == tf)
        late = [e for e in book.entries if e.timeframe == tf and e.t > t_shut]
        assert late and not any(e.booked for e in late)
        assert all(e.pnl_usd == 0 for e in late)


def test_no_learned_weight_no_own_brake_no_adaptive_exit():
    for bad in ({"ladder_weight": 1.5}, {"own_brake": True}, {"adaptive_exit": True}):
        with pytest.raises(ValueError):
            NurseryParams(**bad)
    cfg = NurseryParams().auto_adapt()
    assert cfg["ladder_weight"] == 1.0 and not cfg["own_brake"] and not cfg["adaptive_exit"]
    assert cfg["maker_entry_timeframes"] == ["1h", "4h"] and cfg["risk_includes_costs"]


def test_book_is_deterministic(world):
    path, ctxs, book = world
    again: Book = run_book(ctxs, path, PROSPECTS)
    assert [(e.account, e.t, e.trade, e.twins) for e in again.entries] == \
        [(e.account, e.t, e.trade, e.twins) for e in book.entries]

def test_cost_gate_uses_the_v6_limit_so_scalping_can_be_measured():
    """La puerta es automática, pero su valor es 0,3 R (V6 de T49), no los 0,15 R de T143.

    Con 0,15 R el punto de partida de T136 para 15 m (0,157 R) cierra el marco en el primer
    ciclo y la banda de scalping no llega a medirse nunca (nota §3).
    """
    np_ = NurseryParams()
    assert np_.tf_max_cost_r == V6_MAX_COST_R == 0.30 > BASELINE_COST_R["15m"]
    accs = accounts_for(PROSPECTS)
    assert _Gate(np_, [], accs).open_at("15m", 0)          # abre: se puede medir
    tight = np_.model_copy(update={"exec": np_.exec.model_copy(update={"tf_max_cost_r": 0.15})})
    assert not _Gate(tight, [], accs).open_at("15m", 0)    # con 0,15 R quedaría cerrada
    with pytest.raises(ValueError, match="no se apaga"):
        NurseryParams(exec=np_.exec.model_copy(update={"tf_max_cost_r": None}))


def test_max_bars_caps_every_exit_template():
    """El tope de velas del scalping manda sobre cualquier plantilla (nota §3)."""
    from eim.nursery.rules.base import Signal
    from eim.nursery.signals import Account, build_order

    np_ = NurseryParams()
    ctxs = [{"t": 0, "close": 100.0, "atr": 1.0}, {"t": H1, "close": 100.0, "atr": 1.0},
            {"t": 2 * H1, "close": 100.0, "atr": 1.0}]
    sigs = [Signal(enter=1, hold=1), Signal(hold=-1), Signal(hold=-1)]
    for tpl in ("atr_ladder", "rule_flip", "time_stop"):
        a = Account(f"x:{tpl}", PROSPECT, "ema", "1h", tpl, max_bars=1)
        o = build_order(a, 0, 1, ctxs, sigs, np_)
        assert o is not None and o.forced_t == H1, tpl          # nunca más allá del tope
    late = Account("x:flip", PROSPECT, "ema", "1h", "rule_flip", max_bars=4)
    assert build_order(late, 0, 1, ctxs, sigs, np_).forced_t == H1   # el giro llega antes


def test_days_in_position_counts_the_days_with_a_position(world):
    _, _, book = world
    for a in book.accounts:
        s = account_summary(book, a.id)
        days = {d for e in book.of(a.id) if e.booked and e.trade.fill_t is not None
                for d in range(int(e.trade.fill_t) // DAY_MS,
                               int(e.trade.exit_t or e.trade.fill_t) // DAY_MS + 1)}
        assert s["days_in_position"] == len(days)
        assert set(s["daily"]) <= {str(d) for d in days}       # los cierres caen en esos días
