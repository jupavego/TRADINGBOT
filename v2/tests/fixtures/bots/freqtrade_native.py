"""Se ejecuta DENTRO del entorno de Freqtrade (lo lanza `make_freqtrade_parity.py` con el ejecutor
aislado de EIM, sin red ni claves). Pregunta a la estrategia lo que preguntaría el bot real en
cada vela: `get_entry_signal` / `get_exit_signal` sobre un `DataFrame` que solo llega hasta ella.
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

req = json.loads(Path("request.json").read_text(encoding="utf-8"))
rows = json.loads(Path("candles.json").read_text(encoding="utf-8"))
sys.path.insert(0, req["scripts_dir"])
import freqtrade_signal as sig  # noqa: E402  (el mismo código que usa el adaptador)
from freqtrade import __version__ as engine  # noqa: E402

pair, tf = req["pair"], req["timeframe"]
strat = sig.load_strategy(req["strategy_dir"], req["strategy"], tf)
full = sig.flags_of(sig.analyze(strat, rows, pair))
native = {}
for i in req["indices"]:
    df = sig.analyze(strat, rows[:i + 1], pair)
    closes = datetime.fromtimestamp((rows[i][0] + req["step_ms"]) / 1000, UTC)
    # la comprobación de «historia vieja» de Freqtrade usa el reloj: se fija en el cierre de la vela
    with patch("freqtrade.strategy.interface.dt_now", lambda c=closes: c):
        direction, _ = strat.get_entry_signal(pair, tf, df)
        exit_long = strat.get_exit_signal(pair, tf, df, is_short=False)[1]
        exit_short = strat.get_exit_signal(pair, tf, df, is_short=True)[1]
    native[str(rows[i][0])] = {"entry": direction.value if direction else None,
                               "exit_long": bool(exit_long), "exit_short": bool(exit_short)}
Path("out.json").write_text(json.dumps({
    "engine": engine, "can_short": bool(getattr(strat, "can_short", False)),
    "startup_candle_count": int(getattr(strat, "startup_candle_count", 0)),
    "times": [r[0] for r in rows], "flags": full, "native": native}), encoding="utf-8")
