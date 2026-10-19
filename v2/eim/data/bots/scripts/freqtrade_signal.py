"""Se ejecuta DENTRO del entorno del bot (Python con freqtrade + TA-Lib), no del de EIM.

Lee `request.json` y `candles.json` del directorio de trabajo, corre las tres fases de una
estrategia de Freqtrade sobre las velas (indicadores → entrada → salida, como `analyze_ticker`) y
escribe `out.json` con las banderas por vela. No importa nada de `eim`, no abre red y no conoce
ningún exchange: solo transforma velas en banderas. La decisión de postura la toma EIM.

request: {strategy, strategy_dir, timeframe, pair}; candles: [[t_ms, o, h, l, c, v], …].
"""

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

FLAGS = ("enter_long", "exit_long", "enter_short", "exit_short")


def load_strategy(strategy_dir: str, name: str, timeframe: str):
    """Instancia la estrategia `name` (INTERFACE_VERSION 3) con una config mínima sin exchange."""
    from freqtrade.enums import RunMode

    path = Path(strategy_dir) / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(module)
    config = {"stake_currency": "USDT", "dry_run": True, "runmode": RunMode.OTHER,
              "trading_mode": "futures", "margin_mode": "isolated", "timeframe": timeframe}
    strat = getattr(module, name)(config)
    if getattr(strat, "INTERFACE_VERSION", 2) != 3:
        raise SystemExit(f"{name}: solo se admite INTERFACE_VERSION 3")
    return strat


def analyze(strat, rows: list, pair: str) -> pd.DataFrame:
    """Las tres fases de la estrategia sobre `rows` ([[t_ms, o, h, l, c, v], …])."""
    df = pd.DataFrame(rows, columns=["t", "open", "high", "low", "close", "volume"])
    df.insert(0, "date", pd.to_datetime(df.pop("t"), unit="ms", utc=True))
    return strat.analyze_ticker(df, {"pair": pair})


def flags_of(out: pd.DataFrame) -> dict:
    return {f: [int(v) if v == v else 0 for v in out[f]] if f in out else [0] * len(out)
            for f in FLAGS}


def main() -> None:
    req = json.loads(Path("request.json").read_text(encoding="utf-8"))
    rows = json.loads(Path("candles.json").read_text(encoding="utf-8"))
    from freqtrade import __version__ as engine

    strat = load_strategy(req["strategy_dir"], req["strategy"], req["timeframe"])
    out = analyze(strat, rows, req["pair"])
    Path("out.json").write_text(json.dumps({
        "engine": engine, "interface_version": strat.INTERFACE_VERSION,
        "can_short": bool(getattr(strat, "can_short", False)),
        "startup_candle_count": int(getattr(strat, "startup_candle_count", 0)),
        "times": [int(x.timestamp() * 1000) for x in out["date"]],
        "flags": flags_of(out)}), encoding="utf-8")


if __name__ == "__main__":
    main()
