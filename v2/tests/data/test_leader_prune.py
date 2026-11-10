"""Poda de los líderes rechazados (T128, I/O sin red): lo anterior a 7 días se archiva ya
plegado y se borra; la evaluación da exactamente lo mismo que con todo el historial (vuelta a
vuelta, con la caché, tras cada poda y si reaparece algo podado), y nada más se toca."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging

from eim.copytrading import ScoreParams
from eim.copytrading.copy_params import CopyParams
from eim.copytrading.copy_risk import copy_config
from eim.copytrading.scorecard import score
from eim.copytrading.trip_fold import FoldTrip
from eim.data import leader_archive
from eim.data.copy_replay import funding_rates, replay
from eim.data.leader_eval import context, evaluate, gather
from eim.data.leader_fold_io import EvalCache
from eim.data.leader_prune import KEEP_MS, prune
from eim.data.leader_service import LeaderService
from eim.data.leader_store import LeaderStore
from eim.data.share_spec import LOG_DDL
from eim.leaders import cli as cli_mod
from eim.leaders.cli import main as cli
from tests.copytrading import helpers as H
from tests.copytrading.copy_helpers import SPEC
from tests.copytrading.fold_stream import stream
from tests.data import test_copy_replay as R
from tests.data.test_leader_fold_io import TICK, _feed
from tests.leaders.helpers import FakeInfo

P = ScoreParams()
OTHER = "0x" + "cd" * 20
KEEP = 30 * 60_000  # en las pruebas: 30 min de detalle (el flujo dura ~5 h)


def _store(root, status: str = "rejected") -> LeaderStore:
    store = LeaderStore.at_root(root)
    store.upsert_leader(H.leader(), 0)
    store.set_status(H.LID, status, 0)
    return store


def _check(ref: LeaderStore, store: LeaderStore, cache: EvalCache, asof: int):
    (ld,) = store.leaders()
    want, want_fwd = score(gather(ref, ld, asof), 100, asof, P)
    got, got_fwd = cache.score(store, ld, asof, 100, context(store, ld, asof))
    assert got.model_dump() == want.model_dump(), asof
    assert [t.net for t in got_fwd] == [t.net for t in want_fwd]
    return got


def test_incremental_evaluation_with_daily_pruning_equals_the_full_history(tmp_path):
    s = stream(n=1_500)
    ref, store, cache = _store(tmp_path / "ref"), _store(tmp_path / "pod"), EvalCache(P)
    prev, k, pruned = H.T0 - 1, 0, 0
    for asof in range(H.T0 + TICK, s.end + 4 * TICK, TICK):
        _feed(ref, s, prev, asof)
        _feed(store, s, prev, asof)
        if k % 12 == 11:  # «cada día»
            got = prune(store, asof, P, keep_ms=KEEP, max_rows=150)
            pruned += sum(x.fills for x in got.values())
        _check(ref, store, cache, asof)
        prev, k = asof, k + 1
    left = store.query("SELECT count(*) FROM leader_fills")[0][0]
    assert pruned > 0.8 * len(s.fills) and left + pruned == len(s.fills)
    assert cache.rebuilds > 5  # una por poda; entre podas, solo lo nuevo
    cuts = dict(store.query("SELECT symbol, cut_t FROM leader_archive"))
    assert all(t <= prev - KEEP for t in cuts.values())
    assert not store.query("SELECT count(*) FROM leader_fills f JOIN leader_archive a ON "
                           "a.symbol = f.symbol WHERE f.t <= a.cut_t")[0][0]
    assert store.query("SELECT count(*) FROM leader_follow")[0][0] < \
        ref.query("SELECT count(*) FROM leader_follow")[0][0] // 4
    for t in ("leader_funding", "leader_positions"):  # se conservan enteras
        assert store.query(f"SELECT count(*) FROM {t}") == ref.query(f"SELECT count(*) FROM {t}")
    board = evaluate(store, prev, P, record=False, cache=cache)
    assert board.model_dump() == evaluate(ref, prev, P, record=False).model_dump()


def test_only_rejected_leaders_are_pruned(tmp_path):
    s = stream(n=300, seed=4)
    store = _store(tmp_path, status="approved")
    _feed(store, s, H.T0 - 1, s.end)
    assert prune(store, s.end + KEEP_MS) == {}
    store.set_status(H.LID, "watch", 0)
    assert prune(store, s.end + KEEP_MS) == {}
    assert store.query("SELECT count(*) FROM leader_fills")[0][0] == len(s.fills)
    store.set_status(H.LID, "rejected", 0)
    got = prune(store, s.end + KEEP_MS)[H.LID]
    assert got.fills > 0.8 * len(s.fills) and got.trips > 0 and got.quotes > 0
    assert prune(store, s.end + KEEP_MS) == {}  # nada nuevo: no hace nada


def test_pruning_drops_the_t61_origin_of_what_it_deletes(tmp_path):
    s = stream(n=300, seed=7)
    store = _store(tmp_path)
    _feed(store, s, H.T0 - 1, s.end)
    for ddl in LOG_DDL:
        store.query(ddl)
    keys = [(t, f"{f.leader_id}|{f.tid}|{f.oid}") for f in s.fills
            for t in ("leader_fills", "leader_follow")]
    store.query("INSERT INTO share_origin SELECT tbl, key, 'otro', 'i1' FROM (VALUES "
                + ", ".join(["(?, ?)"] * len(keys)) + ") v(tbl, key)", [x for k in keys for x in k])
    store.query("INSERT INTO share_origin VALUES ('leader_funding', 'x', 'otro', 'i1')")
    got = prune(store, s.end, P, keep_ms=KEEP)[H.LID]
    left = store.query("SELECT count(*) FROM share_origin WHERE tbl = 'leader_fills'")[0][0]
    assert got.origins > 0 and left == len(s.fills) - got.fills  # solo lo borrado
    assert not store.query(
        "SELECT count(*) FROM share_origin o WHERE tbl = 'leader_fills' AND NOT EXISTS (SELECT 1 "
        "FROM leader_fills f WHERE concat_ws('|', f.leader_id, f.tid, f.oid) = o.key)")[0][0]
    assert store.query("SELECT count(*) FROM share_origin WHERE tbl = 'leader_funding'") == [(1,)]


def test_a_pruned_fill_that_comes_back_is_ignored_and_pruned_again(tmp_path):
    s = stream(n=500, seed=6)
    ref, store, cache = _store(tmp_path / "ref"), _store(tmp_path / "pod"), EvalCache(P)
    _feed(ref, s, H.T0 - 1, s.end)
    _feed(store, s, H.T0 - 1, s.end)
    prune(store, s.end, P, keep_ms=KEEP)
    _check(ref, store, cache, s.end)
    cut = store.query("SELECT min(cut_t) FROM leader_archive")[0][0]
    old = [f for f in s.fills if f.t <= cut][:3]  # unión de otro equipo (T61)
    store.add_fills(old)
    store.add_follow([q for _, q in s.quotes if (q.tid, q.oid) in {(f.tid, f.oid) for f in old}])
    n = cache.rebuilds
    _check(ref, store, cache, s.end + 1)
    _check(ref, store, cache, s.end + 2)
    assert cache.rebuilds <= n + 1  # como mucho una vez (cotizaciones nuevas), sin bucle
    prune(store, s.end + 3, P, keep_ms=KEEP)
    assert not store.query("SELECT count(*) FROM leader_fills WHERE t <= ?", [cut])[0][0]


def test_archive_keeps_every_trip_field_and_warns_on_other_params(tmp_path, caplog):
    keep = {"symbol", "legs", "funding", "follow"}  # moneda en la clave; funding, de nuevo
    assert {f.name for f in dataclasses.fields(FoldTrip)} == set(leader_archive.TRIP_FIELDS) | keep
    s = stream(n=300, seed=8)
    store = _store(tmp_path)
    _feed(store, s, H.T0 - 1, s.end)
    prune(store, s.end, P, keep_ms=KEEP)
    with store.reader() as cur:
        bases = leader_archive.load(cur, H.LID, P)
        assert bases and not caplog.records
        with caplog.at_level(logging.WARNING):
            leader_archive.load(cur, H.LID, ScoreParams(quote_timeout_ms=30_000))
    assert "otros parámetros" in caplog.text
    tr = next(tr for b in bases.values() for tr in b.trips if len(tr.follow.slips) > 1)
    assert tr.follow.slips.typecode == "d" and isinstance(tr.follow.src, dict)
    (lat,) = {r[0] for r in store.query("SELECT latency FROM leader_archive LIMIT 1")}
    assert all(isinstance(v, list) for v in json.loads(lat).values())


def test_service_prunes_once_a_day_after_the_first_evaluations(tmp_path):
    s = stream(n=300, seed=9)
    store = _store(tmp_path)
    _feed(store, s, H.T0 - 1, s.end)
    now = s.end + KEEP_MS
    store.save_portfolio(H.LID, now, [])  # sin pedir `portfolio` (no hay red)
    svc = LeaderService(store, FakeInfo([]), [], root=tmp_path, clock=lambda: now,
                        quote_coins=[], first_prune_s=0.0)
    asyncio.run(svc._safe("tareas extra", svc.extra_jobs()))
    left = store.query("SELECT count(*) FROM leader_fills")[0][0]
    assert left < 0.1 * len(s.fills) and not svc.errors
    assert svc._next["prune"] - svc._next["heartbeat"] > 80_000  # la siguiente, mañana
    store.close()


def test_cli_prune_archives_and_compacts(tmp_path, capsys):
    s = stream(n=300, seed=10)
    store = _store(tmp_path)
    _feed(store, s, H.T0 - 1, s.end)  # T0 es de 2026-09: más de 7 días atrás
    store.close()
    assert cli(["--root", str(tmp_path), "prune"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["podado"][H.LID]["fills"] > 0.8 * len(s.fills)
    assert out["compactado"] is None  # base pequeña: no hace falta


def test_supervise_prunes_before_compacting_and_survives_a_failure(tmp_path, monkeypatch):
    s = stream(n=200, seed=12)
    store = _store(tmp_path)
    _feed(store, s, H.T0 - 1, s.end)
    store.close()
    calls = []
    monkeypatch.setattr(cli_mod, "_compact", lambda root: calls.append(root))
    cli_mod._prune_then_compact(tmp_path)
    store = LeaderStore.at_root(tmp_path)
    assert store.query("SELECT count(*) FROM leader_archive")[0][0] > 0
    store.close()

    def boom(*a, **k):
        raise RuntimeError("disco")

    monkeypatch.setattr(cli_mod, "prune", boom)
    cli_mod._prune_then_compact(tmp_path)  # podar nunca impide arrancar
    assert calls == [tmp_path, tmp_path]


def test_copy_replay_starts_after_the_last_cut(tmp_path):
    store = R._store(tmp_path / "leaders.duckdb")
    store.set_status(H.LID, "rejected", 0)
    cut = R.T0 + 1_300 * R.S  # BTC plana tras el cierre de 1 200 s; ETH tras 300 s
    prune(store, cut + KEEP_MS)
    assert leader_archive.floor(store, H.LID) == R.T0 + 1_200 * R.S
    p = CopyParams()
    res = replay(store, H.leader(status="rejected"), p, SPEC, copy_config(p), R._bars(),
                 funding_rates(store, R.T0, R.END), R.END)
    assert res.start == R.T0 + 1_300 * R.S + 100  # primera foto tras el corte
    assert [f.kind for f in res.engine.fills] == ["open", "close", "open", "close"]
    assert any("podado" in w for w in res.warnings)
    store.close()


def test_a_leader_that_never_goes_flat_is_pruned_and_scores_the_same(tmp_path):
    """El caso que dejó crecer la base del 3 al 10 de noviembre: con una posición siempre abierta
    la poda no cortaba nunca. Ahora corta, archiva el viaje abierto y la evaluación no cambia."""
    from types import SimpleNamespace
    fills, pos = [], 0.0
    for i in range(400):
        nxt = 1.0 + (i * 7919 % 5)  # 1..5: nunca plana
        fills.append(H.fill("BTC", pos, nxt, 60_000.0 + (i % 17) * 3, H.T0 + i * 60_000, i + 1,
                            fee=0.5))
        pos = nxt
    q = H.quotes(fills)
    s = SimpleNamespace(fills=fills, quotes=[(x.follow_at, x) for x in q.values()], funding=[])
    end = H.T0 + 400 * 60_000
    ref, store, cache = _store(tmp_path / "ref"), _store(tmp_path / "pod"), EvalCache(P)
    _feed(ref, s, H.T0 - 1, end)
    _feed(store, s, H.T0 - 1, end)
    got = prune(store, end, P, keep_ms=KEEP, max_rows=50)[H.LID]
    assert got.fills > 0.85 * len(fills) and got.quotes > 0.85 * len(fills)
    (opened,) = store.query("SELECT side, pos FROM leader_archive_trips WHERE seq = -1")
    assert opened[0] == "long" and opened[1] > 0
    _check(ref, store, cache, end)
    assert evaluate(store, end, P, record=False, cache=EvalCache(P)).model_dump() == \
        evaluate(ref, end, P, record=False).model_dump()
    assert prune(store, end, P, keep_ms=KEEP) == {}  # nada nuevo
    assert store.query("SELECT count(*) FROM leader_archive_trips WHERE seq = -1") == [(1,)]


def test_service_asks_to_compact_after_pruning_only_when_it_pays(tmp_path, monkeypatch):
    """T128: con la base abierta DuckDB no encoge el archivo; si la poda deja más del 30 %
    libre, el servicio para su bucle y marca la salida para que el vigilante compacte."""
    from eim.data import leader_service as svc_mod
    s = stream(n=300, seed=13)
    store = _store(tmp_path)
    _feed(store, s, H.T0 - 1, s.end)
    now = s.end + KEEP_MS
    store.save_portfolio(H.LID, now, [])
    svc = LeaderService(store, FakeInfo([]), [], root=tmp_path, clock=lambda: now,
                        quote_coins=[], first_prune_s=0.0)
    svc._stop = asyncio.Event()
    assert svc_mod.free_share(store) is None  # base pequeña: no compensa
    monkeypatch.setattr(svc_mod, "free_share", lambda st: 0.42)
    asyncio.run(svc._safe("tareas extra", svc.extra_jobs()))
    assert svc.compact_wanted and svc._stop.is_set() and not svc.errors
    assert svc_mod.free_share(store) == 0.42
    assert svc_mod.COMPACT_EXIT not in (0, 1)
    store.close()


def test_free_share_follows_the_compact_thresholds(tmp_path):
    from eim.data.leader_service import free_share
    store = _store(tmp_path)
    store.query("CHECKPOINT")  # una base recién creada aún no tiene bloques en el archivo
    assert free_share(store, min_free=0.0, min_bytes=0) is not None
    assert free_share(store, min_free=1.01, min_bytes=0) is None
    assert free_share(store, min_free=0.0, min_bytes=2**40) is None
    store.close()
