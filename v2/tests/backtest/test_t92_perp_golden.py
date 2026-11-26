"""Regresión de perpetuos de T92: el camino de T25/T27 no mueve una cifra.

El golden (`tests/fixtures/golden/t92_perp_backtest.json`) se generó con `main` ANTES de T92
(commit 142dc8f) sobre el fixture de ETHUSDT 1 h con una estrategia determinista y barata
(cruce de media con SL/TP por ATR) y funding sintético: tres configuraciones (costos reales,
costos cero y apalancamiento alto, que provoca liquidaciones). Si alguna cifra cambia, algo
de T92 tocó el camino de BTC/ETH. Regenerar SOLO si el cambio es intencionado y aprobado:
`python -m tests.backtest.test_t92_perp_golden` desde `v2/`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from eim.backtest.engine import BacktestResult, run_backtest
from eim.backtest.params import ZERO_COSTS, BacktestParams
from eim.backtest.strategy import Signal
from eim.core import MarketSnapshot
from tests.agents.conftest import make_snapshot

GOLDEN = Path(__file__).parents[1] / "fixtures" / "golden" / "t92_perp_backtest.json"
FUND_MS = 8 * 3_600_000

CONFIGS: dict[str, BacktestParams] = {
    "costos_reales": BacktestParams(max_hold_bars=48),
    "costos_cero": BacktestParams(costs=ZERO_COSTS, max_hold_bars=0),
    "apalancamiento_alto": BacktestParams(leverage=60.0, risk_frac=0.05, max_hold_bars=12),
}


class SmaCross:
    """Cruce del cierre con su media de 20 velas; SL a 1,5 ATR y TP a 2,5 ATR (14 velas)."""

    def on_bar(self, snap: MarketSnapshot) -> Signal | None:
        cs = snap.candles
        if len(cs) < 22:
            return None
        sma = sum(c.c for c in cs[-20:]) / 20
        sma_prev = sum(c.c for c in cs[-21:-1]) / 20
        tr = [max(c.h - c.l, abs(c.h - p.c), abs(c.l - p.c)) for p, c in zip(cs[-15:-1], cs[-14:],
                                                                            strict=True)]
        atr = sum(tr) / len(tr)
        last, prev = cs[-1].c, cs[-2].c
        if prev <= sma_prev and last > sma:
            return Signal(1, last - 1.5 * atr, last + 2.5 * atr, tag=str(cs[-1].t))
        if prev >= sma_prev and last < sma:
            return Signal(-1, last + 1.5 * atr, last - 2.5 * atr, tag=str(cs[-1].t))
        return None


def _inputs():
    cs = make_snapshot().candles
    t0 = cs[0].t - cs[0].t % FUND_MS
    fund = [(t0 + k * FUND_MS, 0.0001 * ((k % 7) - 2)) for k in range(1, len(cs) // 8 + 2)]
    return cs, fund


def _run(params: BacktestParams) -> BacktestResult:
    cs, fund = _inputs()
    return run_backtest(cs, fund, SmaCross(), params, symbol="ETHUSDT", timeframe="1h",
                        trade_from=30)


def _digest(res: BacktestResult) -> dict:
    return {"trades": res.trades_dicts(), "stats": res.stats,
            "equity_last": res.equity[-1], "equity_sum": sum(res.equity), "n_eq": len(res.equity)}


@pytest.mark.parametrize("name", list(CONFIGS))
def test_perp_backtest_matches_pre_t92_golden(name: str) -> None:
    gold = json.loads(GOLDEN.read_text(encoding="utf-8"))[name]
    got = _digest(_run(CONFIGS[name]))
    assert got["stats"] == gold["stats"]
    assert got["n_eq"] == gold["n_eq"]
    assert len(got["trades"]) == len(gold["trades"])
    for a, b in zip(got["trades"], gold["trades"], strict=True):
        assert a.keys() == b.keys()
        for k, v in b.items():
            assert a[k] == (pytest.approx(v, rel=1e-9, abs=1e-9) if isinstance(v, float) else v), k
    assert got["equity_last"] == pytest.approx(gold["equity_last"], rel=1e-10)
    assert got["equity_sum"] == pytest.approx(gold["equity_sum"], rel=1e-10)


def test_golden_covers_every_exit_reason() -> None:
    gold = json.loads(GOLDEN.read_text(encoding="utf-8"))
    reasons = {t["reason"] for g in gold.values() for t in g["trades"]}
    assert {"sl", "tp", "liq", "time", "end"} <= reasons


if __name__ == "__main__":
    GOLDEN.write_text(json.dumps({k: _digest(_run(p)) for k, p in CONFIGS.items()}, indent=1),
                      encoding="utf-8")
    print(f"golden escrito en {GOLDEN}")
