"""T124: los productores reales fijan sus datos, registran el resultado y `repetir` lo reproduce."""

from __future__ import annotations

import json

import numpy as np

from eim.backtest import cli as backtest_cli
from eim.calibration.gate_cli import (
    FIGURES,
    gate_backtest,
    plan_strategy,
    register_windows,
    run,
    window_figures,
)
from eim.calibration.space import defaults
from eim.core import Candle
from eim.data.results import ResultStore
from eim.data.snapshots import SnapshotStore
from eim.data.store import Store
from eim.repro.code import fingerprint
from eim.repro.kinds import _series
from eim.repro.replay import FAIL, OK, repetir
from eim.repro.stamp import markdown_line

H = 3_600_000
T0 = 1_700_000_000_000 // H * H


def market(n: int, seed: int = 7) -> list[Candle]:
    """Paseo con tendencia y vaivén: suficiente para que el plan opere alguna vez."""
    rng = np.random.default_rng(seed)
    k = np.arange(n)
    px = 100 * np.exp(np.cumsum(rng.normal(0, 0.006, n)) + 0.08 * np.sin(k / 40))
    out, prev = [], float(px[0])
    for i, c in enumerate(px):
        c = float(c)
        w = abs(rng.normal(0, 0.004))
        out.append(Candle(t=T0 + i * H, o=prev, h=max(prev, c) * (1 + w), l=min(prev, c) * (1 - w),
                          c=c, v=1000.0 + 50 * rng.random()))
        prev = c
    return out


def store_with(tmp_path, n: int) -> Store:
    s = Store(tmp_path)
    s.upsert_candles("BTCUSDT", "1h", market(n), "sintético")
    s.upsert_series("funding", "BTCUSDT", "-", [(T0 + j * 8 * H, 1e-4) for j in range(n // 8)],
                    "sintético")
    return s


def test_edge_window_registered_like_the_gate_repeats_exactly(tmp_path):
    store, bt = store_with(tmp_path, 560), gate_backtest()
    snap = SnapshotStore(tmp_path).create(store, "BTCUSDT", "1h", origin="prueba")
    s = _series(snap, bt.lookback)
    w = (bt.lookback + 6, len(s.candles))
    fig = window_figures(s, w, run(s, w, plan_strategy(s, defaults()), bt), bt)
    out = {"meta": {"params": defaults(), "backtest": bt.model_dump(), "code": fingerprint()},
           "assets": {"BTCUSDT": {"windows": [fig]}}}
    register_windows(ResultStore(tmp_path), out, {"BTCUSDT": snap}, "1h", "edge_results.json")
    rid = fig["result_id"]
    assert set(FIGURES) <= set(fig) and ResultStore(tmp_path).get(rid).kind == "edge_window"
    chk = repetir(tmp_path, rid)
    assert (chk.verdict, chk.causes) == (OK, []), chk.lines
    c = store.read_candles("BTCUSDT", "1h", start=s.candles[-20].t, end=s.candles[-20].t + 1)[0]
    store.upsert_candles("BTCUSDT", "1h", [c.model_copy(update={"c": (c.h + c.l) / 2})], "x")
    chk = repetir(tmp_path, rid)              # la vela entra en el comprar y mantener
    assert (chk.verdict, chk.causes) == (FAIL, ["datos"]), chk.lines


def test_backtest_cli_fixes_its_data_and_repeats(tmp_path):
    store_with(tmp_path, 556)
    out = tmp_path / "rep"
    backtest_cli.main(["--store", str(tmp_path), "--symbol", "BTCUSDT", "--tf", "1h",
                       "--train", "520", "--test", "30", "--eval-step", "10", "--out", str(out)])
    rep = json.loads((out / "BTCUSDT_1h.json").read_text(encoding="utf-8"))
    repro = rep["meta"]["reproducibility"]
    assert repro["reproducible"] and repro["snapshots"][0]["frozen"]
    assert "Reproducible (T124)" in (out / "BTCUSDT_1h.md").read_text(encoding="utf-8")
    chk = repetir(tmp_path, repro["result_id"])
    assert (chk.verdict, chk.causes) == (OK, []), chk.lines


def test_result_without_snapshot_is_declared_not_reproducible():
    assert markdown_line(None).startswith("> **No reproducible** (T124)")
    assert "No reproducible" in markdown_line({"reproducible": False, "why": "x"})
