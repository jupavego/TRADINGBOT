"""T140: el vigilante recupera una API sin puerto y no la confunde con un bucle bloqueado.

El 2026-11-06 `asyncio` cerró el socket de escucha y la API pasó casi 12 h sorda con el latido al
día. Todo con una sonda inyectada salvo las pruebas de `listening`, que usan sockets de loopback.
"""

from __future__ import annotations

import io
import json
import os
import re
import socket
import subprocess
import sys
import time

import pytest

from eim.operation import port_watch, usage_win, watchdog
from eim.operation.notify import JsonLog
from eim.operation.port_watch import PortWatch, listening
from eim.operation.watchdog import Watchdog, spawn_with_tail

windows = pytest.mark.skipif(sys.platform != "win32", reason="tabla de puertos de Windows")


class Proc:
    """Proceso falso, vivo hasta la consulta número `polls`."""

    def __init__(self, polls: int = 10_000) -> None:
        self.left, self.terminated = polls, False

    def poll(self):
        self.left -= 1
        return 0 if self.left <= 0 else None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


class Rig:
    """Vigilante con reloj falso, latido al día salvo que se pida otra cosa y sonda por guion."""

    def __init__(self, tmp_path, monkeypatch, answers, *, beat=True, **kw) -> None:
        self.t = {"now": 10_000.0}
        self.answers, self.asked = answers, 0
        monkeypatch.setattr(watchdog, "heartbeat_t",
                            lambda _: int(self.t["now"] * 1000) if beat else None)
        self.notes: list = []
        self.wd = Watchdog(["x"], {}, tmp_path / "hb.json",
                           JsonLog(tmp_path / "logs", lambda: int(self.t["now"] * 1000)),
                           check_s=15, stale_s=900, clock=lambda: self.t["now"],
                           sleep=self._sleep, notify=self.notes.append, port_probe=self.probe, **kw)

    def _sleep(self, s: float) -> None:
        self.t["now"] += s

    def probe(self):
        self.asked += 1
        return self.answers(self.t["now"] - 10_000.0)


def test_lost_socket_with_a_fresh_heartbeat_restarts_within_minutes(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch, lambda elapsed: elapsed < 300)
    proc = Proc()
    why = rig.wd._watch(proc)
    assert why.startswith("puerto sin escuchar") and proc.terminated
    assert 300 + 120 <= rig.t["now"] - 10_000.0 <= 300 + 120 + 15    # solo lo sostenido


def test_blocked_loop_with_the_socket_open_is_not_restarted_by_this_path(tmp_path, monkeypatch):
    """Con el bucle bloqueado el puerto sigue en escucha: si algo reinicia, es el latido."""
    rig = Rig(tmp_path, monkeypatch, lambda _: True, beat=False)
    proc = Proc()
    assert rig.wd._watch(proc).startswith("latido detenido") and proc.terminated
    assert rig.asked > 0


def test_slow_start_inside_the_grace_is_not_restarted(tmp_path, monkeypatch):
    """7 min sin puerto, como el arranque del 2026-11-06 01:41 con el equipo cargado."""
    rig = Rig(tmp_path, monkeypatch, lambda elapsed: elapsed >= 420)
    proc = Proc(polls=60)
    assert "terminó" in rig.wd._watch(proc) and not proc.terminated


def test_port_that_never_opens_restarts_after_the_grace(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch, lambda _: False)
    proc = Proc()
    why = rig.wd._watch(proc)
    assert "no llegó a abrirse" in why and proc.terminated
    assert rig.t["now"] - 10_000.0 >= port_watch.GRACE_S


def test_service_without_a_port_behaves_as_today(tmp_path, monkeypatch):
    """El vigilante de líderes no tiene puerto: ni se construye la vigilancia."""
    monkeypatch.setattr(watchdog, "PortWatch", lambda *a, **k: pytest.fail("sin sonda no se usa"))
    monkeypatch.setattr(watchdog, "heartbeat_t", lambda _: None)
    wd = Watchdog(["x"], {}, tmp_path / "hb.json", JsonLog(tmp_path / "logs"), check_s=1,
                  stale_s=1e9, sleep=lambda s: None, notify=lambda a: None)
    assert wd.port_probe is None
    proc = Proc(polls=3)
    assert "terminó" in wd._watch(proc) and not proc.terminated


def test_restart_leaves_the_reason_in_the_log_and_the_alert(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch, lambda elapsed: elapsed < 60)
    rig.wd._spawn = lambda c, e: Proc()
    rig.wd.run(max_starts=1)
    assert rig.wd.restarts == 1 and "puerto sin escuchar" in rig.notes[0].detail
    rows = [json.loads(x) for f in (tmp_path / "logs").glob("*.jsonl")
            for x in f.read_text(encoding="utf-8").splitlines()]
    [row] = [r for r in rows if r["event"] == "proceso_reiniciado"]
    assert row["reason"].startswith("puerto sin escuchar") and row["level"] == "error"


def test_a_real_process_that_loses_its_socket_is_detected_and_stopped(tmp_path):
    """Sin nada inyectado salvo los plazos: un hijo que abre el puerto, lo cierra y sigue vivo."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    code = ("import socket, time\n"
            f"s = socket.socket(); s.bind(('127.0.0.1', {port})); s.listen(1)\n"
            "time.sleep(2); s.close(); time.sleep(120)\n")
    proc = spawn_with_tail([sys.executable, "-c", code], dict(os.environ))   # sockets: SystemRoot
    wd = Watchdog(["x"], {}, tmp_path / "hb.json", JsonLog(tmp_path / "logs"), check_s=0.2,
                  stale_s=1e9, notify=lambda a: None, port_probe=lambda: listening(port),
                  port_grace_s=60, port_lost_s=1)
    try:
        why = wd._watch(proc)
        assert why.startswith("puerto sin escuchar") and "no llegó" not in why
        assert proc.wait(timeout=30) is not None           # el vigilante lo paró
    finally:
        proc.kill()


def _watch(answers: list, step: float = 30.0) -> tuple[PortWatch, list]:
    clock, script = {"t": 0.0}, iter(answers)
    watch = PortWatch(lambda: next(script), grace_s=1200, lost_s=120, clock=lambda: clock["t"])
    out = []
    for _ in answers:
        clock["t"] += step
        out.append(watch.check())
    return watch, out


def test_a_blip_does_not_add_up():
    """Sostenido quiere decir seguido: una respuesta buena pone la cuenta a cero."""
    _, out = _watch([True, False, False, False, True, False, False, False])
    assert out == [None] * 8


def test_unknown_answers_count_neither_way():
    _, out = _watch([True, False, None, None, None, False])
    assert out[:-1] == [None] * 5 and out[-1].startswith("puerto sin escuchar 120 s")
    watch, out = _watch([None, None])
    assert out == [None, None] and not watch.seen


def test_a_broken_probe_never_takes_the_watchdog_down():
    def probe():
        raise RuntimeError("rota")

    assert PortWatch(probe).check() is None


@pytest.fixture
def server():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        s.settimeout(0.3)
        yield s


@windows
def test_listening_reads_the_table_without_opening_a_connection(server):
    """Nadie acepta, como con el bucle bloqueado, y aun así escucha; y no le llega conexión: una
    sonda que se corte no puede provocar el fallo que quiere detectar."""
    assert listening(server.getsockname()[1]) is True
    with pytest.raises(TimeoutError):
        server.accept()


def test_listening_says_no_when_nobody_listens():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    assert listening(port) is False


@pytest.mark.parametrize("table", [lambda p: {}, lambda p: (_ for _ in ()).throw(OSError("x"))])
def test_a_table_that_fails_silently_is_not_read_as_no(server, monkeypatch, table):
    monkeypatch.setattr(usage_win, "listeners", table)
    assert listening(server.getsockname()[1]) is True


def test_listening_is_unknown_when_it_cannot_tell(monkeypatch):
    def fail(*a, **k):
        raise TimeoutError("sin respuesta")

    monkeypatch.setattr(usage_win, "listeners", lambda p: {})
    monkeypatch.setattr(socket, "create_connection", fail)
    assert listening(1) is None


# --- registros con hora -----------------------------------------------------------------------
STAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ ")


def test_output_and_stderr_of_the_service_carry_the_time(capsys):
    code = "import sys; print('hola', flush=True); sys.stderr.write('boom\\n')"
    proc = spawn_with_tail([sys.executable, "-c", code], {}, stamp_stdout=True)
    assert proc.wait(timeout=30) == 0
    out, err = "", ""
    for _ in range(100):                        # los hilos copian al cerrarse las tuberías
        got = capsys.readouterr()
        out, err = out + got.out, err + got.err
        if "hola" in out and "boom" in err:
            break
        time.sleep(0.05)
    assert STAMP.match(out) and out.endswith("hola\n")
    assert STAMP.match(err) and err.endswith("boom\n")
    assert list(proc.tail) == ["boom"]          # el motivo del registro va sin la hora


@pytest.mark.parametrize("exc", [OSError("disco lleno"), UnicodeEncodeError("x", "y", 0, 1, "z")])
def test_the_pump_keeps_reading_when_it_cannot_write(monkeypatch, exc):
    """Si dejara de leer, la tubería se llenaría y el servicio se pararía al escribir en ella."""
    class Broken:
        def write(self, _):
            raise exc

        def flush(self):
            pass

    monkeypatch.setattr(sys, "stderr", Broken())
    tail: list = []
    watchdog._pump(io.StringIO("a\nb\nc\n"), "stderr", tail)    # type: ignore[arg-type]
    assert tail == ["a", "b", "c"]


def test_pump_needs_no_tail(capsys):
    watchdog._pump(io.StringIO("x\n"), "stdout")
    assert capsys.readouterr().out.endswith(" x\n")


def test_only_the_api_ties_its_stdout_to_the_watchdog():
    """La captura y los líderes usan el vigilante por defecto: su salida sigue heredada."""
    proc = spawn_with_tail([sys.executable, "-c", "pass"], {})
    assert proc.stdout is None and proc.wait(timeout=30) == 0


def test_spawn_does_not_leave_the_pipes_unread():
    """Más salida de la que cabe en una tubería: si nadie la leyera, el hijo no terminaría."""
    code = "import sys\nfor _ in range(4000): print('x' * 100); sys.stderr.write('y' * 100 + '\\n')"
    proc = spawn_with_tail([sys.executable, "-c", code], {}, stamp_stdout=True)
    try:
        assert proc.wait(timeout=60) == 0
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.fail("el hijo se quedó parado al escribir")
