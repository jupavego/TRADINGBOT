"""Puntúa el escuadrón desde la línea de comandos (T59).

    python -m eim.bots.scorecard_cli --data-dir data [--symbol BTCUSDT] [--marginal] [--workers 2]

Con `--marginal` reconstruye el panel de agentes del periodo de los bots y mide el aporte de cada
uno al núcleo (lento: minutos). Escribe `reports/bots_scorecard.{md,json}` y guarda la tabla en
`bot_scorecard`. Abre `reports.duckdb` y `paper.duckdb`: páralos de la API antes (un solo escritor)
o apunta a una copia de la carpeta de datos.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from eim.analytics.agent_panel import compute_panel
from eim.api.reports_db import ReportStore
from eim.bots.card import default_cards
from eim.bots.marginal import Marginal, agent_name, evaluate_bot
from eim.bots.scorecard_report import write
from eim.bots.scorer import FOUR_H, TF, BotScorer
from eim.bots.shadow import identities
from eim.data.bots.scorestore import ScoreStore
from eim.data.bots.simstore import SimRunStore
from eim.data.bots.store import BotSignalStore
from eim.data.machine import machine_id
from eim.data.paper_store import PaperStore
from eim.data.store import Store
from eim.data.timeframes import tf_ms


def build_panel(scorer: BotScorer, data: Path, symbol: str, workers: int, log=print):
    """Reportes de los agentes del núcleo en cada cierre de 4 h del periodo de los bots."""
    rows = scorer.rows(symbol)
    first = min(s.asof for s, _ in rows)
    step = tf_ms(TF)
    asofs = [c.t + step for c in scorer.store.read_candles(symbol, TF)
             if (c.t + step) % FOUR_H == 0 and c.t + step >= first]
    log(f"panel de agentes: {len(asofs)} instantes desde {first}")
    return compute_panel(data, symbol, TF, asofs, workers)


def measure_marginals(scorer: BotScorer, panel, symbol: str, log=print) -> dict[str, Marginal]:
    """Aporte marginal de la versión vigente de cada bot utilizable."""
    rows = scorer.rows(symbol)
    candles = scorer.store.read_candles(symbol, TF)
    funding = scorer.store.read_series("funding", symbol)
    latest = {(i.bot_id, i.strategy, i.timeframe): i for i in identities(rows)}
    out: dict[str, Marginal] = {}
    for i in latest.values():
        card = scorer.cards.get(i.bot_id)
        if card is None or not card.usable:
            continue
        mine = [s for s, _ in rows if (s.bot_id, s.strategy, s.timeframe, s.version)
                == (i.bot_id, i.strategy, i.timeframe, i.version)]
        out[i.label] = evaluate_bot(panel, agent_name(i.label), mine, candles, funding, symbol,
                                    log)
        log(f"{i.label}: {out[i.label].reason}")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="eim.bots.scorecard_cli", description=__doc__)
    p.add_argument("--data-dir", default=os.environ.get("EIM_DATA_DIR", "data"))
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--marginal", action="store_true")
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--reports-dir", default=None)
    a = p.parse_args(argv)
    data = Path(a.data_dir)
    reports = ReportStore(data / "reports.duckdb")
    scorer = BotScorer(BotSignalStore(*reports.connection), ScoreStore(*reports.connection),
                       Store(data), PaperStore(data / "paper.duckdb"),
                       SimRunStore(*reports.connection), default_cards(), symbols=(a.symbol,))
    marg = None
    if a.marginal:
        marg = measure_marginals(scorer, build_panel(scorer, data, a.symbol, a.workers),
                                 a.symbol)
    out = scorer.compute(a.symbol, marginals=marg)
    # en qué máquina y sobre qué base: el informe de otro equipo no es el de esta API (T119)
    out["measured_on"] = {"machine": machine_id(data), "data_dir": str(data.resolve())}
    md, js = write(out, Path(a.reports_dir) if a.reports_dir else None)
    print(out["summary"], "\n", md, "\n", js)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
