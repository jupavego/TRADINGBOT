"""T184: el vigía revisa solo cada 6 h, guarda el historial y avisa con alerta sostenida."""
from __future__ import annotations

import json

from eim.api import calib_watch as W
from eim.api.config import Settings
from eim.api.main import create_app
from eim.forecast.calibration import Outcome
from tests.api.test_api import FakeSource, _candles
from tests.local_client import LocalClient

H = 6 * 3_600_000


def outs(calibrated: bool, n: int = 1000) -> list[Outcome]:
    """Bandas que cubren su nominal (50/80/90 de cada 100) o que no cubren nada."""
    def band(i: int) -> dict[str, bool]:
        return {k: calibrated and i % 10 < int(k) // 10 for k in ("50", "80", "90")}
    return [Outcome(made_at=i * 3_600_000, realized=("bull", "neutral", "bear")[i % 3], ret=0.0,
                    probs={"bull": 1 / 3, "neutral": 1 / 3, "bear": 1 / 3}, top="neutral",
                    brier=0.66, brier_rw=0.66, pinball=None, pinball_rw=None, dir_pred=0,
                    dir_real=0, in_band_terminal=band(i),
                    in_band_pooled={k: 0.5 for k in ("50", "80", "90")})
            for i in range(n)]


def rig(tmp_path, monkeypatch, calibrated: bool, clock: list[int]):
    monkeypatch.setattr(W, "outcomes", lambda *a: (outs(calibrated), 3, []))
    beats: list[dict] = []
    monkeypatch.setattr(W.hooks_service, "beat", lambda c, **kw: beats.append({"c": c, **kw}))
    w = W.CalibWatch(None, None, tmp_path, symbols=("BTCUSDT",), tfs=("1h",),
                     clock=lambda: clock[0])
    return w, beats


def test_revisa_cada_6h_y_guarda_el_historial(tmp_path, monkeypatch):
    clock = [10 * H]
    w, beats = rig(tmp_path, monkeypatch, True, clock)
    assert w.maybe_run() is True and w.history[-1]["state"] == "ok" and not beats
    lines = (tmp_path / "calibration" / "watch.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["symbol"] == "BTCUSDT"
    clock[0] += H - 1
    assert w.maybe_run() is False and len(w.history) == 1      # antes de 6 h no repite
    clock[0] += 1
    w.maybe_run()
    assert len(w.history) == 2
    p = w.payload(None, None, 10)
    assert p["enabled"] and p["latest"][0]["timeframe"] == "1h" and p["next_run"] == clock[0] + H
    assert p["latest"][0]["shadow"]["state"] == "no_mejora"   # ya calibrado: nada que corregir
    assert W.CalibWatch(None, None, tmp_path).history == w.history   # sobrevive al reinicio


def test_alerta_sostenida_late_en_ambar(tmp_path, monkeypatch):
    clock = [10 * H]
    w, beats = rig(tmp_path, monkeypatch, False, clock)          # ninguna banda cubre nada
    assert w.maybe_run() is True and w.history[-1]["state"] == "alerta" and not beats
    clock[0] += H
    assert w.maybe_run() is False and w.history[-1]["state"] == "alerta_sostenida"
    assert beats and beats[-1]["c"] == "forecast.calibration"
    assert beats[-1]["status"] == "degraded"


def test_un_fallo_no_tumba_el_gancho(tmp_path, monkeypatch):
    def boom(*a):
        raise RuntimeError("base ocupada")
    monkeypatch.setattr(W, "outcomes", boom)
    w = W.CalibWatch(None, None, tmp_path, symbols=("BTCUSDT",), tfs=("1h",), clock=lambda: H)
    assert w.maybe_run() is False and "base ocupada" in w.error


def test_ruta_sin_vigia_lo_dice(tmp_path):
    cfg = Settings(data_dir=tmp_path, heartbeat_s=0.2, snapshot_bars=300)
    with LocalClient(create_app(cfg, source=FakeSource(_candles(1)[0]))) as c:
        j = c.get("/v2/calibration/watch").json()
    assert j["enabled"] is False and j["latest"] == []
