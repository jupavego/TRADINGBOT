"""Vigía de asimetría (T187–T189): mide cada hora, decide en sus fechas y adopta lo que pasa."""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np

from eim.api import asym_watch as W
from eim.paper.asym import prereg as P
from eim.paper.params import ExecParams
from tests.paper.asym.helpers import row

CP = P.checkpoints_ms()
STEP = 15 * 60_000


def _path():
    t0 = P.START_MS
    n = 8 * 96                                               # 8 días de 15 m, plano
    t = np.array([t0 + k * STEP for k in range(n)], dtype=np.int64)
    flat = np.full(n, 100.0)
    return SimpleNamespace(t=t, o=flat, h=flat + 0.3, l=flat - 0.3, c=flat, step=STEP)


def _desk():
    view = SimpleNamespace(path=_path(), outcomes=[])
    return SimpleNamespace(symbols=("BTCUSDT",), pstore=None, ep=ExecParams(),
                           cached_view=lambda _s, wait_s=0.0: view)


def _rows(n):
    return [row(i, r=0.1 if i % 3 else -1.1, weight=1.4 if i % 2 else 0.5, day=i % 6,
                hour=1 + i % 5) for i in range(n)]


def test_runs_hourly_and_writes_strict_json(tmp_path, monkeypatch):
    monkeypatch.setattr(W.ledger, "query", lambda *_a, **_k: _rows(12))
    now = [P.START_MS + 3 * P.DAY_MS]
    w = W.AsymWatch(_desk(), tmp_path, clock=lambda: now[0])
    assert w.maybe_run() is True and w.error == ""
    assert w.maybe_run() is False                     # menos de una hora: no repite
    lines = (tmp_path / "paper" / "asym" / "reviews.jsonl").read_text("utf-8").splitlines()
    entry = json.loads(lines[-1])                     # JSON estricto (sin Infinity)
    assert entry["prereg"] == P.VERSION and entry["operaciones_medidas"] == 12
    assert entry["rules"]["t187b"]["state"] == "EN CURSO"
    assert entry["rules"]["t187a"]["state"] == "ADOPTADA POR DECISIÓN"
    assert entry["verdicts"] == {} and entry["adopted"] == {}
    assert not (tmp_path / "paper" / "asym" / "looks.json").exists()


def test_a_look_is_taken_once_with_data_before_its_date(tmp_path, monkeypatch):
    monkeypatch.setattr(W.ledger, "query", lambda *_a, **_k: _rows(12))
    w = W.AsymWatch(_desk(), tmp_path)
    w.run(CP[0] + 3_600_000)
    looks = json.loads((tmp_path / "paper" / "asym" / "looks.json").read_text("utf-8"))
    assert list(looks) == ["0"]
    # con 12 operaciones no llega a los mínimos: sigue en curso y no se adopta nada
    assert looks["0"]["results"]["t187b"]["state"] == "EN CURSO"
    w.run(CP[0] + 2 * 3_600_000)
    again = json.loads((tmp_path / "paper" / "asym" / "looks.json").read_text("utf-8"))
    assert again["0"]["at"] == looks["0"]["at"]       # la mirada no se rehace
    assert not (tmp_path / "paper" / "asym" / "adopted.json").exists()


def test_a_failure_never_breaks_the_hooks(tmp_path, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("base ocupada")
    monkeypatch.setattr(W.ledger, "query", boom)
    w = W.AsymWatch(_desk(), tmp_path, clock=lambda: P.START_MS)
    assert w.maybe_run() is False and "base ocupada" in w.error
    assert w.payload()["error"]


def test_clean_drops_non_finite_numbers():
    assert W.clean({"a": [1.0, float("inf")], "b": float("nan")}) == {"a": [1.0, None], "b": None}
