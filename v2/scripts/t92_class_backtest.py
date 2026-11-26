"""Backtest de prueba de T92: una acción, un par de divisas y un futuro con los costos de su
clase y el desglose en el informe (criterio de aceptación).

Series: las fixtures SINTÉTICAS de T90 (`tests/fixtures/t90/`): una acción con split 4×1 y
dividendo de 0,50, EURUSD horario con fin de semana y un futuro continuo con empalme del 3 %.
No son datos de mercado: el informe lo dice en cada sección. La estrategia sigue el lado de una
media corta con SL/TP por ATR, elegida para que haya operaciones que atraviesen el split, el
dividendo, el fin de semana y el empalme; **no es una estrategia de inversión ni una prueba de
ventaja** (eso es T95/T97–T99 con la puerta T49).

Uso (desde `v2/`):
  python scripts/t92_class_backtest.py --out reports/t92_costos_por_clase.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eim.backtest.class_engine import run_instrument_backtest  # noqa: E402
from eim.backtest.class_report import build_class_report, to_markdown  # noqa: E402
from eim.backtest.costs import cost_model_for  # noqa: E402
from eim.backtest.params import BacktestParams  # noqa: E402
from eim.backtest.strategy import Signal  # noqa: E402
from eim.core import Candle, MarketSnapshot  # noqa: E402
from eim.data.adjust import PriceEvent  # noqa: E402
from eim.instruments.models import (  # noqa: E402
    AssetClass,
    DataCapability,
    Instrument,
    MarketStructure,
    SessionKind,
    TradableLevel,
)

FIX = ROOT / "tests" / "fixtures" / "t90"
VOL = frozenset({DataCapability.CANDLES, DataCapability.REAL_VOLUME})
SYNTH = "fixture T90 (SINTÉTICA, no son datos de mercado)"


class FollowMean:
    """Del lado del cierre frente a su media de `n` velas; SL a `k_sl`·ATR y TP a `k_tp`·ATR.
    Sin cruce: en series casi monótonas (las fixtures) también opera y atraviesa los eventos."""

    def __init__(self, n: int = 5, k_sl: float = 3.0, k_tp: float = 4.0) -> None:
        self.n, self.k_sl, self.k_tp = n, k_sl, k_tp

    def on_bar(self, snap: MarketSnapshot) -> Signal | None:
        cs, n = snap.candles, self.n
        if len(cs) < n + 1:
            return None
        sma = sum(c.c for c in cs[-n:]) / n
        atr = sum(c.h - c.l for c in cs[-n:]) / n
        last = cs[-1].c
        if atr <= 0 or last == sma:
            return None
        side = 1 if last > sma else -1
        return Signal(side, last - side * self.k_sl * atr, last + side * self.k_tp * atr,
                      tag=str(cs[-1].t))


def _load(name: str) -> tuple[list[Candle], list[PriceEvent]]:
    d = json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))
    cs = [Candle(t=c[0], o=c[1], h=c[2], l=c[3], c=c[4], v=c[5]) for c in d["candles"]]
    return cs, [PriceEvent(**e) for e in d.get("events", [])]


def instruments() -> dict[str, tuple[Instrument, str, str]]:
    """(instrumento, fixture, marco). Fichas de prueba: no están en el registro."""
    acme = Instrument(
        id="equity.test.ACME", symbol="ACME", label="ACME (sintética)",
        asset_class=AssetClass.EQUITY, market_structure=MarketStructure.CONTINUOUS_BOOK,
        venue="test", currency="USD", quote_currency="USD", calendar_id="XNYS",
        session=SessionKind.EXCHANGE_HOURS, lot=1.0, tick=0.01, data_capabilities=VOL,
        source=SYNTH)
    eurusd = Instrument(
        id="fx.test.EURUSD", symbol="EURUSD", label="EUR/USD (sintético)",
        asset_class=AssetClass.FX, market_structure=MarketStructure.QUOTE_DRIVEN, venue="test",
        currency="USD", quote_currency="USD", calendar_id="24/5", session=SessionKind.WEEKDAYS,
        tradable_level=TradableLevel.RESEARCH,
        data_capabilities=frozenset({DataCapability.CANDLES}), source=SYNTH)
    clx = Instrument(
        id="future.test.CLX", symbol="CLX", label="Crudo continuo (sintético)",
        asset_class=AssetClass.FUTURE, market_structure=MarketStructure.CONTINUOUS_BOOK,
        venue="test", currency="USD", quote_currency="USD", calendar_id="CMES",
        session=SessionKind.EXCHANGE_HOURS, tick=0.01, multiplier=1000.0,
        data_capabilities=VOL, source=SYNTH)
    return {"acción": (acme, "equity_split_dividend", "1d"),
            "divisa": (eurusd, "fx_weekend", "1h"),
            "futuro": (clx, "future_roll", "1d")}


def run(initial_equity: float = 100_000.0) -> list[dict]:
    params = BacktestParams(initial_equity=initial_equity, lookback=500, max_hold_bars=0,
                            risk_frac=0.01)
    out = []
    for inst, fixture, tf in instruments().values():
        cs, ev = _load(fixture)
        model = cost_model_for(inst)
        res = run_instrument_backtest(cs, FollowMean(), inst, params=params, model=model,
                                      events=ev, timeframe=tf)
        out.append(build_class_report(res, inst, params, tf, model, SYNTH))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / "reports" / "t92_costos_por_clase.md")
    a = ap.parse_args()
    reps = run()
    md = to_markdown(reps, "T92 — Backtest de prueba por clase con costos propios")
    md = md.replace("\n\n", "\n\n> Series sintéticas de T90 y estrategia de prueba: valida "
                    "la mecánica de costos, no dice nada de rentabilidad.\n\n", 1)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(md, encoding="utf-8")
    a.out.with_suffix(".json").write_text(json.dumps(reps, indent=1, default=str),
                                          encoding="utf-8")
    print(f"informe: {a.out}")


if __name__ == "__main__":
    main()
