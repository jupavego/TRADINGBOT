"""T110 — El diario en la mesa: avisos (`op_alerts`), eventos del observatorio, contadores del
resumen, reconciliación manual y CLI."""

from __future__ import annotations

import threading
from types import SimpleNamespace

import duckdb
import pytest

from eim.operation.alerts import AlertCenter
from eim.paper import protection, protection_desk
from eim.paper.__main__ import main
from eim.paper.feedback import Learner
from eim.paper.protection_desk import DeskProtection, trace_of
from eim.paper.protection_sync import reconcile
from eim.paper.summary import profile_summary
from tests.paper.helpers import T0
from tests.paper.protection_helpers import (
    EP,
    MOD,
    OP,
    SYM,
    TOP,
    btc,
    pullback,
    rise,
    sim_book,
    step,
    store,
)

WIDER = MOD.model_copy(update={"ladder": MOD.ladder.model_copy(update={"step_r": 0.15})})


class Desk(DeskProtection):
    def __init__(self, ps, alerts=None):
        self.pstore, self.ep, self.alerts = ps, EP, alerts
        self._lock, self._cache = threading.Lock(), {}
        self._protection_init()

    def view(self, rows, p=MOD, ideas=None):
        """Lo que hace `PaperDesk._compute` con el diario: suelo, libro y pasada."""
        st = sim_book(rows, p, ideas, self._guards(SYM))
        v = SimpleNamespace(symbol=SYM, books={p.id: st}, protection={})
        self._sync_protection(v)
        return v


@pytest.fixture
def ps():
    s = store()
    yield s
    s.close()


@pytest.fixture
def center():
    con = duckdb.connect(":memory:")
    yield AlertCenter(con, threading.Lock())
    con.close()


@pytest.fixture
def events(monkeypatch):
    got: list[dict] = []
    monkeypatch.setattr(protection_desk, "emit", lambda kind, comp, **kw: got.append(
        {"kind": kind, "component": comp, **kw}))
    return got


def _alerts(center):
    return [(a.level, a.title, a.resolved) for a in reversed(center.recent())]


def test_steps_and_recovery_emit_observatory_events_with_one_trace(ps, events):
    d = Desk(ps)
    d.view(rise(6))
    whats = [e["detail"]["what"] for e in events]
    assert whats == ["proteccion_alta"] + ["proteccion_escalon"] * 5
    assert {e["trace_id"] for e in events} == {trace_of(OP)}
    assert all(e["kind"] == "alert" and e["component"] == "paper.broker" for e in events)
    events.clear()
    d2 = Desk(ps)                                       # «reinicio» con un recálculo menor
    d2.view(rise(6), p=WIDER)
    (e,) = events
    assert e["detail"]["what"] == "proteccion_recuperacion" and e["status"] == "degraded"
    assert e["trace_id"] == trace_of(OP) and e["detail"]["stop"] == TOP


def test_recovery_and_inconsistency_reach_op_alerts_and_resolve(ps, center):
    Desk(ps, center).view(rise(6))
    d = Desk(ps, center)
    v = d.view(rise(6), p=WIDER)
    assert v.protection["verified"] and v.protection["recovered"][0]["op_id"] == OP
    assert ("warn", f"Protección recuperada del diario: moderado {SYM}", False) in _alerts(center)
    ps.execute("DELETE FROM paper_protection WHERE op_id = ?", [OP])
    v = d.view(pullback(rise(6), TOP - 20))
    assert v.protection["n_inconsistent"] == 1 and v.protection["held"] == {OP: protection.MISSING}
    held = f"Protección en estado inconsistente: moderado {SYM}"
    assert ("critical", held, False) in _alerts(center)
    d.resolve_protection(OP, "recalculo", "instantánea perdida en una prueba")
    d.view(pullback(rise(6), TOP - 20))
    assert ("info", f"Resuelta: {held}", True) in _alerts(center)


def test_summary_counts_inconsistent_and_recovered_positions(ps):
    Desk(ps).view(rise(6))
    ps.execute("DELETE FROM paper_protection WHERE op_id = ?", [OP])
    d = Desk(ps)
    v = d.view(rise(6))
    s = profile_summary(v.books["moderado"], Learner([]), [], T0, 0.004)
    d.annotate_protection(v, [s])
    assert s["protection"] == {"verified": True, "inconsistent": 1, "recovered": 0}
    (pos,) = s["positions"]
    assert pos["protection_state"] == "inconsistente" and "falta" in pos["protection_why"]


def test_unreadable_journal_marks_the_view_unverified(ps, center):
    d = Desk(ps, center)
    d.pstore = SimpleNamespace(execute=lambda *a, **k: (_ for _ in ()).throw(OSError("disco")))
    v = d.view(rise(6))
    assert v.protection["verified"] is False and "disco" in v.protection["error"]
    assert any(t.startswith("Diario de protección sin verificar") for _l, t, _r in _alerts(center))


def test_reconcile_rules(ps):
    step(ps, rise(6))
    with pytest.raises(ValueError, match="estado inconsistente"):
        reconcile(ps, OP, "recalculo", "no hace falta", T0)
    with pytest.raises(LookupError):
        reconcile(ps, "moderado|BTCUSDT|nada", "recalculo", "no existe", T0)
    ps.execute("DELETE FROM paper_protection WHERE op_id = ?", [OP])
    step(ps, pullback(rise(6), TOP - 20))                          # inconsistente, sin cierre
    with pytest.raises(ValueError, match="nota"):
        reconcile(ps, OP, "recalculo", "  ", T0)
    row = reconcile(ps, OP, "recalculo", "se acepta el recálculo", T0)
    assert row["status"] == "reconciliada" and "a mano" in row["note"]
    st, res = step(ps, pullback(rise(6), TOP - 20))
    assert st.trades and st.trades[0]["exit"] == TOP               # ahora sí cierra (por datos)
    events = [r["event"] for r in protection.history(ps, OP)]
    assert events == ["inconsistente", "reconciliada", "alta"] + ["escalon"] * 5 + ["cierre"]
    assert "reanudada" in res.rows[0]["note"]


def test_discarded_operation_is_no_longer_followed(ps):
    step(ps, rise(6))
    step(ps, rise(6), ideas=[])                                    # ya no aparece al recalcular
    reconcile(ps, OP, "descartar", "la idea ya no existe", T0)
    _st, res = step(ps, rise(6), ideas=[])
    assert res.rows == [] and res.held == {}
    assert protection.history(ps, OP)[-1]["status"] == "descartada"


def test_cli_lists_and_reconciles_against_the_local_store(tmp_path, capsys):
    from eim.data.paper_store import PaperStore
    ps = PaperStore(tmp_path / "paper.duckdb")
    protection.ensure(ps)
    step(ps, rise(6), ideas=[btc()])
    step(ps, rise(6), ideas=[])
    ps.close()
    off = ["--api", "http://127.0.0.1:9", "--data", str(tmp_path)]
    assert main(["proteccion", "lista", "--estado", "inconsistente", *off]) == 0
    assert OP in capsys.readouterr().out
    assert main(["proteccion", "reconciliar", OP, "--decision", "descartar",
                 "--nota", "prueba de la CLI", *off]) == 0
    assert main(["proteccion", "historial", OP, *off]) == 0
    out = capsys.readouterr().out
    assert "descartada" in out and "prueba de la CLI" in out
