"""T102 — la revisión de salud: archivos publicados, avisos que sobreviven a un proceso nuevo,
desactivación automática por vista obsoleta, matriz de T101 y una revisión que nunca tumba."""

from __future__ import annotations

import json

from eim.data.scanner_view import write_view
from eim.scanner import health_service as HS
from eim.scanner import rollout as R
from tests.scanner._t102 import DAY, NOW, STATUS, make_view


def _data(tmp_path, view=None):
    d = tmp_path / "data"
    (d / "scanner").mkdir(parents=True)
    (d / "scanner" / "status.json").write_text(json.dumps(STATUS), encoding="utf-8")
    if view is not None:
        write_view(d, view)
    return d


def test_check_publishes_health_and_rollout(tmp_path):
    d = _data(tmp_path, make_view())
    got: list = []
    h = HS.check(d, now=NOW, sinks=[got.append], emit_events=False)
    assert h["overall"] == "ok" and got == []
    saved = HS.read_health(d)
    assert saved["overall"] == "ok" and saved["rollout"]["units"]["class:crypto"]["level"] == \
        "alerta"
    assert HS.read_rollout(d)["units"]["class:crypto"]["active"] is True
    assert saved["observability"]["within"] is True


def test_alerts_survive_a_new_process_and_resolve(tmp_path):
    d = _data(tmp_path)                                   # sin vista: sin datos
    got: list = []
    HS.check(d, now=NOW, sinks=[got.append], emit_events=False)
    assert {a.key for a in got} >= {"multiactivo:clase:crypto", "multiactivo:escaner"}
    n = len(got)
    HS.check(d, now=NOW + 60_000, sinks=[got.append], emit_events=False)   # otra vuelta
    assert len(got) == n                                  # no se repite
    write_view(d, make_view(now=NOW + 120_000))
    HS.check(d, now=NOW + 120_000, sinks=[got.append], emit_events=False)
    assert all(a.resolved for a in got[n:]) and HS.read_health(d)["alerts_active"] == {}


def test_a_stale_view_deactivates_the_class_and_shadows_its_candidates(tmp_path):
    v = make_view()
    d = _data(tmp_path, v)
    for k in range(3):
        h = HS.check(d, now=NOW + (4 + k) * DAY, sinks=[], emit_events=False)
    assert h["overall"] == "obsoleto"
    st = HS.read_rollout(d)
    assert st["units"]["class:crypto"]["active"] is False
    assert R.shadow_reason(v["opportunities"][0], st)
    assert any(c["what"] == "desactivada" for c in
               h["rollout"]["changes"] + [e for u in st["units"].values()
                                          for e in u["history"]])


def test_t101_matrix_is_read_as_the_best_verdict_per_class(tmp_path):
    rep = tmp_path / "reports"
    rep.mkdir()
    assert HS.t101_cells(rep)["available"] is False
    (rep / "multiasset_validation_2026-12-30.json").write_text(json.dumps({"cells": [
        {"agent": "ema", "asset_class": "crypto", "verdict": "rechazada"},
        {"agent": "regime", "asset_class": "crypto", "verdict": "en observación"},
        {"agent": "ema", "asset_class": "equity", "verdict": "no aplica"},
        {"agent": "x", "asset_class": "fx", "verdict": "inventado"}]}), encoding="utf-8")
    t = HS.t101_cells(rep)
    assert t["available"] and t["cells"] == {"crypto": "en observación", "equity": "no aplica"}
    g = HS.gates(tmp_path / "data")
    assert g["t101"]["cells"]["crypto"] == "en observación"
    assert g["t96_built"] is False and g["t103_built"] is False   # planeados en el catálogo


def test_a_failing_review_never_breaks_the_pass(tmp_path, monkeypatch):
    d = _data(tmp_path, make_view())

    def boom(*a, **k):
        raise RuntimeError("falla a propósito")

    monkeypatch.setattr(HS.health, "build", boom)
    assert HS.safe_check(d, now=NOW, sinks=[]) is None


def test_a_broken_sink_does_not_stop_the_review(tmp_path):
    d = _data(tmp_path)

    def broken(a):
        raise OSError("canal roto")

    h = HS.check(d, now=NOW, sinks=[broken], emit_events=False)
    assert h["alerts_active"]
