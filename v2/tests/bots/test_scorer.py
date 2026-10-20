"""Persistencia, recálculo y ruta de la puntuación de bots (T59), con mercado sintético."""

from __future__ import annotations

import threading

import duckdb
import pytest

from eim.bots.scorecard_report import render
from eim.bots.scorer import FOUR_H, BotScorer, regime_lookup
from eim.data.bots.scorestore import ScoreStore
from eim.data.bots.store import BotSignalStore
from eim.data.paper_store import PaperStore
from eim.data.store import Store
from tests.bots.score_helpers import CRIT, SYMBOL, Market, card, oracle_rows

BOT = "hummingbot-directional"


@pytest.fixture(scope="module")
def scorer(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("scorer")
    m = Market(days=100)
    store = Store(tmp_path)
    store.upsert_candles(SYMBOL, "1h", m.c1h, "sintético")
    store.upsert_candles(SYMBOL, "15m", m.c15, "sintético")
    con, lock = duckdb.connect(":memory:"), threading.Lock()
    sigs = BotSignalStore(con, lock)
    now = m.end + 1000
    prev = 0.0
    for s, created in oracle_rows(m):
        if s.stance != prev:              # solo los cambios de lado (lo que abre operaciones)
            sigs.append(s, max(created, s.asof))
        prev = s.stance
    ps = PaperStore(":memory:")
    for k in range(0, len(m.dirs), 4):
        ps.save(SYMBOL, "1h", {"t": m.c1h[k].t + 3_600_000, "regime": m.regime_at(
            m.c1h[k].t + 3_600_000)}, "backtest", now)
    sc = BotScorer(sigs, ScoreStore(con, lock), store, ps, None, {BOT: card()}, CRIT)
    sc.now = now
    return sc


def test_compute_persists_and_latest_reads_without_recomputing(scorer):
    out = scorer.compute(SYMBOL, scorer.now)
    assert out["bots"] and out["mode"] == "SIMULADO"
    saved = scorer.scores.latest(SYMBOL, CRIT.version)
    assert saved["asof"] == out["asof"] and saved["summary"] == out["summary"]
    assert scorer.latest(SYMBOL)["asof"] == out["asof"]
    assert scorer.scores.history(SYMBOL)[0]["asof"] == out["asof"]


def test_append_only_same_asof_is_not_overwritten(scorer):
    scorer.compute(SYMBOL, scorer.now)
    assert scorer.scores.save({**scorer.latest(SYMBOL), "summary": {"x": 1}}, scorer.now + 5) \
        is False
    assert "x" not in scorer.scores.latest(SYMBOL)["summary"]


def test_regime_lookup_never_looks_ahead(scorer):
    at = regime_lookup(scorer.pstore, SYMBOL)
    t = scorer.pstore.load(SYMBOL, "1h")[10]["t"]
    assert at(t - 1) != "futuro" and at(0) is None
    assert at(t) == scorer.pstore.load(SYMBOL, "1h")[10]["regime"]


def test_periodic_job_due_at_each_4h_close(scorer):
    assert scorer.due(scorer.now)
    scorer.last_run = scorer.now
    assert not scorer.due(scorer.now)
    assert scorer.due(scorer.now + FOUR_H)
    scorer.last_run = None


def test_report_renders_with_the_four_dimensions(scorer):
    md = render(scorer.compute(SYMBOL, scorer.now))
    for word in ("Rendimiento", "Evidencia", "Seguridad", "Operativa", "Holm", "Clase L"):
        assert word in md


def test_empty_store_returns_message_not_error(tmp_path):
    con, lock = duckdb.connect(":memory:"), threading.Lock()
    sc = BotScorer(BotSignalStore(con, lock), ScoreStore(con, lock), Store(tmp_path),
                   PaperStore(":memory:"), None, {})
    out = sc.compute(SYMBOL, 10**13)
    assert out["bots"] == [] and "sin posturas" in out["error"]


def test_scoring_accepts_per_timeframe_candles_and_paths():
    """Mapeo {marco: velas/camino}: las posturas de 5 m se resuelven con velas de 5 m."""
    from eim.bots.scorecard import attempts_of
    from eim.core import Candle
    from eim.paper.engine import Path

    m = Market(days=30)
    rows = oracle_rows(m)
    _, plain = attempts_of(rows, m.c1h, m.path, SYMBOL, None, None)
    _, mapped = attempts_of(rows, {"1h": m.c1h}, {"1h": m.path}, SYMBOL, None, None)
    assert [len(a.trades) for a in plain] == [len(a.trades) for a in mapped] and plain[0].trades
    # 5 m: cada vela de 15 m en tres de 5 m; postura de 5 m en cada cierre de hora
    c5 = []
    for c in m.c15:
        for j in range(3):
            o = c.o + (c.c - c.o) * j / 3
            c5.append(Candle(t=c.t + j * 300_000, o=o, h=c.h, l=c.l, c=o + (c.c - c.o) / 3, v=3.0))
    rows5 = [(s.model_copy(update={"timeframe": "5m", "bot_id": "x"}), cr) for s, cr in rows]
    _, got = attempts_of(rows5, {"5m": c5}, {"5m": Path(c5, (), 300_000)}, SYMBOL, None, None)
    assert got[0].ident.timeframe == "5m" and got[0].trades
