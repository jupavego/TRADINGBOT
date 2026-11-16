"""T169: el banco truncado solo sabe lo de su corte, y un agente real da lo mismo en los dos."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from eim.core import Candle
from eim.data.store import Store
from eim.nursery.exam.checks import _norm, truncate_bank
from eim.nursery.exam.gen import LightGen, agents_named

SYM = "BTCUSDT"
H1 = 3_600_000
T0 = 1_767_225_600_000
BARS = {"15m": H1 // 4, "1h": H1, "4h": 4 * H1}


def _bank(root: Path, hours: int = 900) -> Store:
    rng = np.random.default_rng(3)
    st = Store(root)
    px = 60_000 * np.exp(np.cumsum(rng.normal(0, 0.002, hours * 4)))
    for tf, bar in BARS.items():
        k = bar // (H1 // 4)
        cs = []
        for j in range(0, len(px) - k + 1, k):
            seg = px[j:j + k]
            cs.append(Candle(t=T0 + j * (H1 // 4), o=float(seg[0]), h=float(seg.max()) * 1.001,
                             l=float(seg.min()) * 0.999, c=float(seg[-1]), v=10.0))
        st.upsert_candles(SYM, tf, cs, "prueba")
    st.upsert_series("funding", SYM, "-", [(T0 + i * 8 * H1, 1e-4) for i in range(hours // 8)],
                     "prueba")
    return st


def test_truncated_bank_keeps_only_what_was_known(tmp_path: Path) -> None:
    full = _bank(tmp_path / "full")
    cut = T0 + 600 * H1
    truncate_bank(tmp_path / "full", tmp_path / "cut", cut, SYM)
    cut_st = Store(tmp_path / "cut")
    for tf, bar in BARS.items():
        cs = cut_st.read_candles(SYM, tf)
        assert cs and cs[-1].t + bar == cut                 # la vela que cierra en el corte, sí
        assert len(cs) == len([c for c in full.read_candles(SYM, tf) if c.t + bar <= cut])
    fund = cut_st.read_series("funding", SYM)
    assert fund[-1][0] < cut and (cut in {t for t, _ in full.read_series("funding", SYM)})


def test_a_real_agent_gives_the_same_context_with_truncated_data(tmp_path: Path) -> None:
    _bank(tmp_path / "full")
    cut = T0 + 600 * H1
    truncate_bank(tmp_path / "full", tmp_path / "cut", cut, SYM)
    native = {"ema": ("metrics.variables.STACK_ORDER", "metrics.variables.EMA_21")}
    agents = agents_named(["ema"])
    a = LightGen(Store(tmp_path / "full"), "1h", agents, native)
    b = LightGen(Store(tmp_path / "cut"), "1h", agents, native)
    for t in (cut - 2 * H1, cut - H1, cut):
        x, y = a.ctx_at(t), b.ctx_at(t)
        assert x is not None and _norm(x) == _norm(y)
        assert x["nat"]["ema"]["variables.STACK_ORDER"] is not None and x["st"]["ema"] == "ok"
    assert b.ctx_at(cut + H1) is None                       # después del corte no hay decisión
    assert a.ctx_at(cut + H1) is not None
