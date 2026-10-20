"""Se ejecuta DENTRO del entorno del bot (Python 3.12 con freqtrade + TA-Lib), no del de EIM.

Lee `request.json`, `candles.json` (velas de 5 min) e `info.json` del directorio de trabajo y
corre las tres
fases de `NostalgiaForInfinityX7` (indicadores → entrada → salida) como `analyze_ticker`, con un
`DataProvider` de mentira que entrega los marcos informativos (15m, 1h, 4h, 1d) de `info.json`
(armados por EIM, solo barras completas), el par BTC como informativo de sentimiento y nada de
red, exchange, base de datos ni órdenes. Escribe `out.json` con las banderas por vela. No importa
nada de `eim`. La decisión de postura la toma EIM (`eim/bots/nfi_adapter.py`).

request: {strategy, strategy_dir, timeframe, pair}; candles: [[t_ms, o, h, l, c, v], …].
Solo BTCUSDT: el informativo «BTC» de NFI es el propio par.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

FLAGS = ("enter_long", "exit_long", "enter_short", "exit_short")
BTC = "BTC/USDT:USDT"


class Dp:
    """Lo que NFI le pide al `DataProvider` al poblar indicadores (nada de lo de órdenes).

    Los informativos (15m, 1h, 4h, 1d) los arma EIM con historia propia y solo barras completas
    (`info.json`): así el marco de 5 min puede ser corto y el diario tener sus ~50 días."""

    def __init__(self, base: pd.DataFrame, info: dict, runmode) -> None:
        self.base, self.runmode = base, runmode
        self.info = {tf: to_frame(rows) for tf, rows in info.items()}

    def current_whitelist(self):
        return [BTC]

    def get_pair_dataframe(self, pair, timeframe=None, candle_type=""):
        tf = timeframe or "5m"
        return (self.base if tf == "5m" else self.info[tf]).copy()

    def send_msg(self, *args, **kwargs):
        pass


def to_frame(rows: list) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["t", "open", "high", "low", "close", "volume"])
    df.insert(0, "date", pd.to_datetime(df.pop("t"), unit="ms", utc=True))
    return df


def load_strategy(strategy_dir: str, name: str, timeframe: str, workdir: Path):
    from freqtrade.enums import RunMode

    path = Path(strategy_dir) / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(module)
    config = {"stake_currency": "USDT", "dry_run": True, "runmode": RunMode.BACKTEST,
              "trading_mode": "futures", "margin_mode": "isolated", "timeframe": timeframe,
              "exchange": {"name": "binance", "pair_whitelist": [BTC]}, "max_open_trades": 3,
              "user_data_dir": workdir}
    strat = getattr(module, name)(config)
    strat.ft_load_hyper_params()      # lo que hace el resolvedor de Freqtrade
    if getattr(strat, "INTERFACE_VERSION", 2) != 3:
        raise SystemExit(f"{name}: solo se admite INTERFACE_VERSION 3")
    return strat, RunMode.BACKTEST


def analyze(strat, runmode, rows: list, info: dict, pair: str) -> pd.DataFrame:
    df = to_frame(rows)
    strat.dp = Dp(df.copy(), info, runmode)
    meta = {"pair": pair}
    out = strat.populate_indicators(df, meta)
    out = strat.populate_entry_trend(out, meta)
    return strat.populate_exit_trend(out, meta)


def flags_of(out: pd.DataFrame) -> dict:
    return {f: [int(v) if v == v else 0 for v in out[f]] if f in out else [0] * len(out)
            for f in FLAGS}


def tags_of(out: pd.DataFrame, col: str) -> list:
    return [str(v) if isinstance(v, str) else "" for v in out[col]] if col in out \
        else [""] * len(out)


def main() -> None:
    req = json.loads(Path("request.json").read_text(encoding="utf-8"))
    rows = json.loads(Path("candles.json").read_text(encoding="utf-8"))
    info = json.loads(Path("info.json").read_text(encoding="utf-8"))
    from freqtrade import __version__ as engine

    if req["pair"] != BTC:
        raise SystemExit("solo BTCUSDT")
    strat, runmode = load_strategy(req["strategy_dir"], req["strategy"], req["timeframe"],
                                   Path.cwd())
    out = analyze(strat, runmode, rows, info, req["pair"])
    Path("out.json").write_text(json.dumps({
        "engine": engine, "interface_version": strat.INTERFACE_VERSION,
        "can_short": bool(getattr(strat, "can_short", False)),
        "startup_candle_count": int(getattr(strat, "startup_candle_count", 0)),
        "times": [int(x.timestamp() * 1000) for x in out["date"]],
        "flags": flags_of(out), "enter_tag": tags_of(out, "enter_tag"),
        "exit_tag": tags_of(out, "exit_tag")}), encoding="utf-8")


if __name__ == "__main__":
    main()
