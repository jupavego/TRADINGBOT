"""Genera `freqtrade_parity.json`: lo que el bot NATIVO (Freqtrade) decide en cada vela (T57).

Corre `freqtrade_native.py` en el entorno aparte de Freqtrade a través del ejecutor aislado de EIM
(sin red ni claves). Guarda las banderas de una corrida completa (lo que usa el adaptador) y, en
velas muestreadas, la decisión nativa con solo las velas hasta ella (`get_entry_signal`,
`get_exit_signal`). A mano, desde `v2/`:

    python tests/fixtures/bots/make_freqtrade_parity.py <python-de-freqtrade> <checkout-estrategias>
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from eim.bots.card import card_of  # noqa: E402
from eim.bots.ft_adapter import FUTURES_DIR, ft_pair  # noqa: E402
from eim.data.bots.runner import Limits, RunSpec, run_isolated  # noqa: E402

STRATEGY = "FSupertrendStrategy"
STEP = 3_600_000
FROM_BAR, EVERY = 300, 3          # velas muestreadas: desde la 300, una de cada 3


def main(python: str, checkout: str) -> None:
    here = Path(__file__).parent
    src = json.loads((here / "hummingbot_parity.json").read_text(encoding="utf-8"))
    rows = src["candles"]
    spec = RunSpec(
        python=Path(python), script=here / "freqtrade_native.py", limits=Limits(timeout_s=900),
        request={"strategy": STRATEGY, "strategy_dir": str(Path(checkout) / FUTURES_DIR),
                 "timeframe": "1h", "pair": ft_pair("ETHUSDT"), "step_ms": STEP,
                 "scripts_dir": str(ROOT / "eim" / "data" / "bots" / "scripts"),
                 "indices": list(range(FROM_BAR, len(rows), EVERY))},
        files={"candles.json": json.dumps(rows)},
        bot_dir=Path(checkout), expected_sha=card_of("freqtrade-strategies").commit_sha)
    res = run_isolated(spec)
    if res.status != "ok" or res.output is None:
        raise SystemExit(f"el bot no respondió: {res.warnings}")
    out = {"strategy": STRATEGY, "sha": spec.expected_sha, "network_isolated": res.network_isolated,
           "symbol": "ETHUSDT", "timeframe": "1h", **res.output}
    (here / "freqtrade_parity.json").write_text(json.dumps(out, separators=(",", ":")),
                                                encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
