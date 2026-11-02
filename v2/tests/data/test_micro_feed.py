"""T128: la microestructura del agente sale de la captura HFT y da las mismas cifras que el
recolector viejo (T23) con los mismos mensajes de Binance; el feed nunca para la captura."""

import random

import duckdb
import pytest

from eim.data import micro
from eim.data.collectors import health
from eim.data.collectors.binance_ws import Collector
from eim.data.collectors.micro_feed import MicroFeed
from eim.data.micro import read_micro
from tests.data.hft_helpers import MS, SYM, T0, Exchange, capture, send, snap, trade

STEP, BARS, SECONDS = 60_000, 20, 1200
FIELDS = ("ofi", "delta", "buy_v", "sell_v", "depth_imb")


def same(a, b) -> bool:
    """Mismas velas: igual tiempo, nº de trades y si está completa; el resto, salvo el último
    decimal (DuckDB suma en el orden que quiere)."""
    return len(a) == len(b) and all(
        (x.t, x.trades, x.complete) == (y.t, y.trades, y.complete)
        and all(getattr(x, f) == pytest.approx(getattr(y, f), rel=1e-9, abs=1e-12)
                if getattr(x, f) is not None else getattr(y, f) is None for f in FIELDS)
        for x, y in zip(a, b, strict=True))


def both(tmp_path, lose_at=None, seed=1):
    """Los mismos mensajes al recolector viejo y a la captura con su feed."""
    old_root, new_root = tmp_path / "viejo", tmp_path / "nuevo"
    old = Collector(old_root, SYM, top_every_ms=1000)
    cap, store = capture(new_root)
    feed = MicroFeed(new_root, SYM)
    cap.on_book = feed.on_book
    ex, rng = Exchange(seed), random.Random(seed)
    for s in range(SECONDS):
        t = T0 + s * 10**9 + 100 * MS
        e = t // MS - 110
        sync = s == 0 or (lose_at is not None and s == lose_at + 2)
        m, mid = ex.step(k=3, e_ms=e, snap_at=1 if sync else None)
        if sync:          # como Binance: snapshot a mitad del diff (U ≤ L ≤ u)
            send(cap, m, t)
            snap(cap, mid, t + 10 * MS)
            old.load_snapshot(mid)
            old.on_message({"data": m})
        elif s != lose_at:                                 # el de `lose_at` se pierde
            send(cap, m, t)
            old.on_message({"data": m})
        tr = trade(1000 + s, e + 5, p=100.0, q=round(rng.uniform(0.1, 3.0), 3),
                   maker=rng.random() < 0.5)
        send(cap, tr, t + 3 * MS)
        old.on_message({"data": tr})
    old.flush()
    store.flush()
    feed.flush()
    return old_root, new_root, cap


@pytest.mark.parametrize("lose_at", [None, 500])
def test_the_agent_gets_the_same_figures_from_the_hft_capture(tmp_path, lose_at):
    old_root, new_root, cap = both(tmp_path, lose_at)
    t0 = T0 // MS
    old_bars, old_book = read_micro(old_root, SYM, t0 + STEP, STEP, BARS - 1)
    new_bars, new_book = read_micro(new_root, SYM, t0 + STEP, STEP, BARS - 1)
    assert len(new_bars) == BARS - 1 and same(new_bars, old_bars)
    assert new_book == old_book and new_book is not None
    assert [b.complete for b in new_bars].count(False) == (0 if lose_at is None else 1)
    # la vela del arranque: sin libro hasta el primer snapshot, la captura la da por incompleta
    assert not read_micro(new_root, SYM, t0, STEP, 1)[0][0].complete
    assert cap.counts["errores_feed"] == 0
    assert not (new_root / "micro" / "trades").exists()      # los trades no se duplican


def test_the_reader_prefers_the_capture_and_counts_a_repeated_trade_once(tmp_path):
    _, new_root, _ = both(tmp_path)
    t0 = T0 // MS
    before, _ = read_micro(new_root, SYM, t0, STEP, BARS)
    assert before[0].trades == 60
    files = micro._hft_files(new_root, "trades", SYM, t0, t0 + STEP)
    t_ms, p, q, maker = duckdb.connect().execute(
        f"SELECT t_ms, p, q, maker FROM read_parquet({files}) WHERE agg_id = 1001").fetchone()
    cap, store = capture(new_root, run=T0 + 10**12)               # una reconexión lo repite
    send(cap, trade(1001, t_ms, p=p, q=q, maker=maker), T0 + 10**12)
    store.flush()
    after, _ = read_micro(new_root, SYM, t0, STEP, BARS)
    assert same(after, before) and after[0].trades == 60


def test_a_long_capture_gap_leaves_every_bar_it_spans_incomplete(tmp_path):
    _, new_root, _ = both(tmp_path)
    cap, store = capture(new_root, run=T0 + 2 * 10**12)
    cap.hour = T0 // (3600 * 10**9)
    cap.gap("depth", "desconexion", T0 + 125 * 10**9, T0 + 365 * 10**9, T0 + 365 * 10**9, 0)
    cap.gap("bbo", "silencio", T0 + 600 * 10**9, T0 + 700 * 10**9, T0 + 700 * 10**9, 0)
    store.flush()
    bars, _ = read_micro(new_root, SYM, T0 // MS, STEP, BARS)
    lost = [T0 // MS + i * STEP for i in (0, 2, 3, 4, 5, 6)]   # 0: el arranque; 2-6: el corte
    assert [b.t for b in bars if not b.complete] == lost


def test_the_feed_never_stops_the_capture_and_keeps_the_panel_heartbeat(tmp_path):
    cap, store = capture(tmp_path)

    def broken(*_a):
        raise OSError("disco lleno")

    cap.on_book = broken
    ex = Exchange(2)
    send(cap, ex.step(e_ms=T0 // MS)[0], T0 + MS)
    snap(cap, ex.snapshot(), T0 + 20 * MS)
    for s in range(5):
        send(cap, ex.step(e_ms=T0 // MS + 1000 * (s + 1))[0], T0 + (s + 1) * 10**9)
    assert cap.counts["errores_feed"] == 6 and cap.vb.book.synced   # 5 diffs + la sincronía
    feed = MicroFeed(tmp_path, SYM)
    feed.heartbeat(cap.status())
    hb = health.read_heartbeat(tmp_path, SYM)
    assert hb["source"] == "hft_ws" and hb["depth_msgs"] == 6 and hb["symbol"] == SYM

