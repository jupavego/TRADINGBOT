"""T190–T193 en la API: el vigía de dirección revisa cada 6 h, guarda su historial y late."""

from __future__ import annotations

import json

import numpy as np

from eim.api.direction_watch import DirectionWatch, build_direction_router
from eim.direction.params import DirectionParams
from eim.direction.shadow import ABSTAIN, WEIGHTED

STEP = 3_600_000
P = DirectionParams(regime_bars=8, regime_lookback=40)


class FakeStore:
    def __init__(self, n=1500, seed=5):
        rng = np.random.default_rng(seed)
        self.t = np.arange(n, dtype=np.int64) * STEP
        self.c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))

    def read_arrays(self, symbol, timeframe, **_):
        return {"t": self.t, "c": self.c}


class FakeReports:
    def __init__(self, store, seed=9):
        rng = np.random.default_rng(seed)
        t, c = store.t, store.c
        self.rows = []
        for i in range(100, len(t) - 1):
            fut = np.sign(c[min(i + 4, len(c) - 1)] - c[i]) or 1.0
            asof = int(t[i] + STEP)
            self.rows.append((asof, "oracle", 0.5 * (fut if rng.random() < 0.7 else -fut),
                              0.8, "ok"))
            self.rows.append((asof, "noise", float(rng.choice([-0.4, 0.4])), 0.8, "ok"))

    def history(self, symbol, timeframe, bars, end=None):
        return self.rows


def synth(asof, rows):
    return next((b for a, b, *_ in rows if a == "noise"), None)


def make(tmp_path, clock=lambda: 10**12):
    store = FakeStore()
    return DirectionWatch(FakeReports(store), store, tmp_path, symbols=("BTCUSDT",),
                          tfs=("1h",), params=P, clock=clock, synth=synth)


def test_revisa_guarda_y_respeta_la_cadencia(tmp_path):
    now = [10**12]
    w = make(tmp_path, clock=lambda: now[0])
    assert w.maybe_run() is True
    assert w.maybe_run() is False                              # antes de 6 h no repite
    now[0] += P.interval_ms
    assert w.maybe_run() is True
    lines = (tmp_path / "direction" / "watch.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    e = json.loads(lines[-1])
    assert e["prereg"] == "direccion_v1" and e["timeframe"] == "1h"
    assert e["board"]["4"]["oracle"]["verdict"] in ("ventaja", "sin_ventaja")
    assert set(e["shadows"]) == {ABSTAIN, WEIGHTED}
    assert "streak" in e["shadows"][WEIGHTED]


def test_historial_sobrevive_al_reinicio(tmp_path):
    make(tmp_path).maybe_run()
    again = make(tmp_path)
    assert len(again.history) == 1 and again.latest()[0]["symbol"] == "BTCUSDT"


def test_un_fallo_no_tumba_al_broker(tmp_path):
    w = make(tmp_path)
    w.store = None
    assert w.maybe_run() is False and w.error


def test_payload_ligero_y_completo(tmp_path):
    w = make(tmp_path)
    w.maybe_run()
    light = w.payload(None, None, 10, full=False)
    assert "board" not in light["latest"][0] and light["prereg_doc"].endswith("preregistro.md")
    assert "board" in w.payload("BTCUSDT", "1h", 10, full=True)["latest"][0]
    assert build_direction_router(None) is not None and build_direction_router(w) is not None
