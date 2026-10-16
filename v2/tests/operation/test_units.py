"""Piezas sueltas: alertas, notificación, vigilante, capital, informe y persistencia."""

import base64
import json
import threading

import duckdb
import pytest

from eim.execution.broker import STOP, OrderSpec
from eim.execution.service import CLOSED, LiveTrade
from eim.execution.sim_broker import SimBroker
from eim.operation import alerts as A
from eim.operation import report, weekly
from eim.operation.equity import EquityBook, account_state, drawdown, loss_streak
from eim.operation.notify import JsonLog, WindowsToast, toast_script
from eim.operation.watchdog import Watchdog, instance_lock

DAY = 86_400_000
MON = 4 * DAY + 2_000 * 7 * DAY          # un lunes 00:00 UTC


def _db():
    return duckdb.connect(), threading.Lock()


# --- alertas -------------------------------------------------------------------------
def _cond(on, key="k"):
    return A.Condition(key, A.DIVERGENCE, on, A.CRITICAL, "t", "d")


def test_alert_fires_on_transition_only_and_resolves():
    got = []
    ac = A.AlertCenter(*_db(), sinks=[got.append])
    assert len(ac.update(1, [_cond(True)])) == 1
    assert ac.update(2, [_cond(True)]) == [] and ac.active == ["k"]
    out = ac.update(3, [_cond(False)])
    assert out[0].resolved and out[0].level == A.INFO and ac.active == []
    assert [a.t for a in ac.recent()] == [3, 1] and len(got) == 2


def test_alert_reminder_and_broken_sink():
    def boom(_):
        raise OSError("sin escritorio")

    ac = A.AlertCenter(*_db(), sinks=[boom], repeat_ms=10)
    ac.update(0, [_cond(True)])
    assert ac.update(5, [_cond(True)]) == [] and len(ac.update(10, [_cond(True)])) == 1
    assert len(ac.sink_errors) == 2 and len(ac.recent()) == 2       # quedan registradas


def test_conditions_cover_the_five_families():
    cs = A.conditions(now=10_000, data_fail_since={"BTCUSDT": 0, "ETHUSDT": None},
                      disconnect_ms=5_000, recon={"issues": ["BTCUSDT: posición 1 sin SL"]},
                      kill={"active": True, "by": "regla:drawdown", "reason": "x"},
                      drawdown=0.07, drawdown_warn=0.05, drawdown_kill=0.15,
                      agent_status={"BTCUSDT": {"plan": "no_data", "context": "no_data",
                                                "ema": "degraded"}},
                      critical=("plan",))
    on = {c.key: c for c in cs if c.on}
    assert set(on) == {"desconexion:BTCUSDT", "divergencia", "kill_switch", "drawdown",
                       "agentes_degradados:BTCUSDT"}
    assert on["drawdown"].level == A.WARN
    assert "context" not in on["agentes_degradados:BTCUSDT"].detail    # no crítico y no_data


# --- notificación ----------------------------------------------------------------------
def test_toast_only_for_warn_critical_or_resolved():
    calls = []
    t = WindowsToast(enabled=True, spawn=calls.append)
    t(A.Alert(1, A.REPORT, A.INFO, "informe"))
    t(A.Alert(1, A.KILL, A.CRITICAL, "Kill-switch activado", "it's"))
    t(A.Alert(2, A.KILL, A.INFO, "Resuelta", resolved=True))
    assert len(calls) == 2 and calls[0][:2] == ["powershell", "-NoProfile"]
    script = base64.b64decode(calls[0][-1]).decode("utf-16-le")
    assert "SystemIcons]::Error" in script and "'it''s'" in script
    WindowsToast(enabled=False, spawn=calls.append)(A.Alert(1, A.KILL, A.CRITICAL, "x"))
    assert len(calls) == 2 and "Information" in toast_script(A.Alert(1, "x", A.INFO, "y"))


def test_json_log_daily_files(tmp_path):
    clock = {"t": MON}
    log = JsonLog(tmp_path, lambda: clock["t"])
    log.write("a", x=1)
    clock["t"] += DAY
    log.alert_sink(A.Alert(clock["t"], A.KILL, A.CRITICAL, "k"))
    files = sorted(tmp_path.glob("op-*.jsonl"))
    assert len(files) == 2
    row = json.loads(files[1].read_text(encoding="utf-8"))
    assert row["event"] == "alerta" and row["kind"] == A.KILL and row["level"] == A.CRITICAL


# --- vigilante -------------------------------------------------------------------------
class FakeProc:
    def __init__(self, rc_after=None):
        self.polls, self.rc_after, self.terminated = 0, rc_after, False

    def poll(self):
        self.polls += 1
        return 1 if self.rc_after is not None and self.polls >= self.rc_after else None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


def test_watchdog_restarts_on_exit_and_on_stale_heartbeat(tmp_path):
    clock = {"t": 1_000.0}
    procs = [FakeProc(rc_after=2), FakeProc()]
    hb = tmp_path / "heartbeat.json"

    def sleep(s):
        clock["t"] += s

    notes = []
    wd = Watchdog(["x"], {}, hb, JsonLog(tmp_path / "logs", lambda: int(clock["t"] * 1000)),
                  stale_s=100, check_s=10, spawn=lambda cmd, env: procs.pop(0),
                  clock=lambda: clock["t"], sleep=sleep, notify=notes.append)
    second = procs[1]
    wd.run(max_starts=2)
    assert wd.restarts == 2 and second.terminated                   # 2.º: latido detenido
    assert notes[0].kind == A.SERVICE and "terminó" in notes[0].detail
    assert "latido" in notes[1].detail


def test_instance_lock_is_exclusive_until_released(tmp_path):
    path = tmp_path / "x" / "supervisor.lock"
    first = instance_lock(path)
    assert first is not None and instance_lock(path) is None       # segunda instancia: fuera
    first.close()
    again = instance_lock(path)
    assert again is not None
    again.close()


# --- capital -----------------------------------------------------------------------------
def _closed(pnl_sign, t):
    tr = LiveTrade("k", "p", "BTCUSDT", 1, 1.0, 1, 90.0, 120.0, "MARKET", status=CLOSED,
                   filled=1.0, avg_entry=100.0, closed_at=t)
    tr.exit_price = 90.0 if pnl_sign < 0 else 120.0
    return tr


def test_account_state_from_history():
    book = EquityBook(*_db(), mode="SIMULADO")
    book.record(MON - DAY, 10_000)          # semana anterior
    book.record(MON + 1_000, 10_500)        # lunes: pico
    book.record(MON + 2 * DAY, 10_200)      # miércoles
    now = MON + 2 * DAY + 3_600_000
    acc = account_state(9_900, now, book, [_closed(1, 1), _closed(-1, 2), _closed(-1, 3)],
                        ("BTCUSDT",), "SIMULADO")
    assert acc.week_start_equity == 10_000 and acc.day_start_equity == 10_500
    assert acc.peak_equity == 10_500 and acc.consecutive_losses == 2 and acc.last_loss_t == 3
    assert drawdown(9_900, acc.peak_equity) == pytest.approx(600 / 10_500)
    assert loss_streak([]) == (0, None)
    bare = account_state(5.0, now, None, [], (), "x")
    assert bare.day_start_equity == bare.peak_equity == 5.0


def test_equity_without_prior_day_uses_first_record():
    book = EquityBook(*_db(), mode="TESTNET")
    book.record(MON + 5_000, 1_000)
    assert book.start_at(MON) == 1_000 and book.peak() == 1_000


# --- informe -----------------------------------------------------------------------------
EDGE = {"assets": {"BTCUSDT": {"windows": [
    {"from_t": 0, "to_t": 26 * weekly.WEEK_MS, "n_trades": 26, "expectancy_r": -0.5,
     "max_drawdown": 0.12}]}}}


def test_baseline_and_deviations():
    base = weekly.backtest_baseline(EDGE, ["BTCUSDT", "ETHUSDT"])
    assert set(base) == {"BTCUSDT"} and base["BTCUSDT"]["trades_per_week"] == pytest.approx(1)
    live = {"BTCUSDT": weekly.trade_stats([_closed(1, 1), _closed(-1, 2)], 0.0)}
    dev = weekly.deviations(live, base, weeks=1.0)
    assert "2.0 operaciones/semana vs 1.0" in dev[0] and "no concluyente" in dev[1]


def test_net_r_subtracts_fees():
    tr = _closed(1, 1)
    assert weekly.net_r(tr, 0.0) == pytest.approx(2.0)
    assert weekly.net_r(tr, 0.001) == pytest.approx((20 - 0.22) / 10)


def test_incidents_flag_unresolved_reconciliation():
    al = [A.Alert(1, A.DIVERGENCE, A.CRITICAL, "d", key="divergencia"),
          A.Alert(2, A.DIVERGENCE, A.INFO, "r", key="divergencia", resolved=True),
          A.Alert(3, A.DIVERGENCE, A.CRITICAL, "d", key="divergencia")]
    assert weekly.incidents(al, [])["recon_unresolved"] == ["divergencia"]
    assert weekly.incidents(al[:2], [])["recon_unresolved"] == []


def test_report_renders_without_data(tmp_path):
    rep = weekly.compose(t0=MON, t1=MON + weekly.WEEK_MS, mode="SIMULADO",
                         symbols=("BTCUSDT",), trades=[], fee_rate=0.0004, equity=[],
                         alerts=[], active_alerts=[], decisions=[], edge=None,
                         calib={"BTCUSDT": weekly.calibration([], {}, 25)}, started_at=MON)
    j, m = report.write(rep, tmp_path)
    assert m.name == f"semana_{weekly.week_label(MON)}.md" and j.exists()
    assert "Sin resultados de backtest" in m.read_text(encoding="utf-8")


# --- persistencia del simulador -----------------------------------------------------------
def test_sim_broker_dump_load_roundtrip():
    b = SimBroker()
    b.set_price("BTCUSDT", 100.0)
    b.post_order(OrderSpec("eim-a-s", "BTCUSDT", -1, STOP, trigger=90.0, close_position=True))
    b.post_order(OrderSpec("eim-a-e", "BTCUSDT", 1, "MARKET", qty=1.0))
    c = SimBroker()
    c.load(json.loads(json.dumps(b.dump())))
    assert c.position("BTCUSDT") == b.position("BTCUSDT") and c.balance == b.balance
    assert c.open_orders("BTCUSDT") == b.open_orders("BTCUSDT")
    c.set_price("BTCUSDT", 89.0)
    assert c.position("BTCUSDT").qty == 0
