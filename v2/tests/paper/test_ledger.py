"""Libro de registro fijo: solo adición, solo origen `vivo`, sombra y perfil, sin reescribir."""

from __future__ import annotations

from dataclasses import replace

import pytest

from eim.backtest.params import CostParams
from eim.data.paper_store import PaperStore
from eim.paper import ledger
from eim.paper.book import run_profile
from eim.paper.engine import Outcome
from eim.paper.feedback import Learner
from eim.paper.params import PROFILES, ExecParams
from tests.paper.helpers import H1, T0, idea

MOD = next(p for p in PROFILES if p.id == "moderado")
NOW = T0 + 40 * H1


def _closed(k: int, r: float, origin: str) -> Outcome:
    i = replace(idea(t=T0 + k * H1, strategy="s", iid=f"s:{k}"), origin=origin, version="v1")
    risk = 2.0 / 100.0
    return Outcome(i, "CERRADA", "TP" if r > 0 else "SL", T0 + k * H1, 100.0, T0 + (k + 1) * H1,
                   100.0 * (1 + r * risk), fee_in=0.0005, fee_out=0.0005, gross=r * risk, r=r)


def _rows(outs, ep=None):
    st = {MOD.id: run_profile(MOD, outs, Learner(outs), mmr=0.004)}
    return ledger.rows_from_view("BTCUSDT", outs, st, ep or ExecParams(), NOW)


@pytest.fixture
def pstore():
    ps = PaperStore(":memory:")
    ledger.ensure(ps)
    yield ps
    ps.close()


def test_only_live_closed_trades_enter_both_scopes(pstore):
    outs = [_closed(0, 1.0, "vivo"), _closed(1, -1.0, "vivo"), _closed(2, 1.0, "backtest")]
    rows = _rows(outs)
    assert ledger.record(pstore, rows) == len(rows)
    got = ledger.query(pstore, "BTCUSDT")
    assert {r["origin"] for r in got} == {"vivo"}
    assert {r["scope"] for r in got} == {"sombra", "perfil"}
    assert sum(r["scope"] == "sombra" for r in got) == 2          # la de backtest no entra
    assert ledger.counts(pstore)["sombra:BTCUSDT"] == 2
    perfil = next(r for r in got if r["scope"] == "perfil" and r["r"] == 1.0)
    assert perfil["profile"] == "moderado" and perfil["pnl_usdt"] > 0 and perfil["qty"] > 0
    assert perfil["rules_version"] == "v1" and perfil["mech_version"] and perfil["cost_params"]


def test_ledger_is_append_only_even_if_costs_change(pstore):
    outs = [_closed(0, 1.0, "vivo")]
    first = _rows(outs)
    ledger.record(pstore, first)
    before = {r["ledger_id"]: (r["pnl_usdt"], r["r"], r["mech_version"])
              for r in ledger.query(pstore)}
    other = ExecParams(costs=CostParams(slip_entry_base_bps=5.0))    # otra mecánica
    changed = _rows([replace(outs[0], r=-1.0, gross=-0.02)], other)  # el «recálculo» da otro PnL
    assert ledger.record(pstore, changed) == 0                      # no se reescribe ni se duplica
    after = {r["ledger_id"]: (r["pnl_usdt"], r["r"], r["mech_version"])
             for r in ledger.query(pstore)}
    assert after == before


def test_new_closures_are_added_and_old_untouched(pstore):
    ledger.record(pstore, _rows([_closed(0, 1.0, "vivo")]))
    n = ledger.record(pstore, _rows([_closed(0, 1.0, "vivo"), _closed(1, -1.0, "vivo")]))
    assert n >= 1 and len(ledger.query(pstore, scope="sombra")) == 2
    assert len(ledger.query(pstore, scope="perfil", profile="moderado")) >= 1


def test_retro_flag_marks_late_registrations(pstore):
    o = _closed(0, 1.0, "vivo")
    late = ledger.rows_from_view("BTCUSDT", [o], {}, ExecParams(), o.exit_t + 5 * H1)
    soon = ledger.rows_from_view("BTCUSDT", [_closed(1, 1.0, "vivo")], {}, ExecParams(),
                                 T0 + 2 * H1 + 60_000)
    ledger.record(pstore, late + soon)
    by = {r["idea_id"]: r["retro"] for r in ledger.query(pstore)}
    assert by == {"s:0": True, "s:1": False}
