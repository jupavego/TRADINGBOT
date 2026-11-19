"""Retención de lo que la poda de T128 no toca (T178, I/O sin red): las reconciliaciones que
cuadran se resumen por día y las fotos repetidas se borran, sin cambiar lo que leen el informe
de calidad (`leader_report`) ni el tiempo capturado que mide T49 (`leader_eval.context`)."""

from __future__ import annotations

from eim.data.leader_eval import context
from eim.data.leader_report import summary
from eim.data.leader_retention import DAY_MS, Retained, retain, shape, thin_photos, thin_recon
from eim.data.leader_store import LeaderStore
from eim.leaders.book import Diff, Recon
from tests.copytrading import helpers as H

HOUR = 3_600_000
MIN = 60_000
KEEP = 2 * HOUR          # en las pruebas: 2 h de detalle
T0 = 10 * DAY_MS         # empieza en un día redondo


def _store(root, status: str = "rejected") -> LeaderStore:
    store = LeaderStore.at_root(root)
    store.upsert_leader(H.leader(), 0)
    store.set_status(H.LID, status, 0)
    return store


def _recon(t: int, *, ok: bool = True) -> Recon:
    diffs = () if ok else (Diff(symbol="BTC", field="size", expected="1.0", actual="2.0"),)
    return Recon(t=t, checked=("BTC", "ETH"), skipped=("SOL",), diffs=diffs, leverage=())


def _feed_recon(store: LeaderStore, n: int, step: int = 30_000, bad_every: int = 97) -> int:
    """Una reconciliación cada `step`; una de cada `bad_every` no cuadra o resincroniza."""
    for i in range(n):
        t = T0 + i * step
        bad = i and i % bad_every == 0
        store.add_recon(H.LID, _recon(t, ok=not bad), t, resynced=bool(bad),
                        clock_offset_ms=10 + i % 5, retries=i % 3)
    return T0 + (n - 1) * step


def _feed_photos(store: LeaderStore, n: int, step: int = 5 * MIN, change_every: int = 12) -> int:
    """Una foto cada `step`; la forma cambia cada `change_every` fotos (lo demás solo PnL)."""
    for i in range(n):
        t = T0 + i * step
        size = 1.0 + i // change_every
        store.save_positions(H.LID, t, t, [H.position("BTC", "long", size, 100.0, t,
                                                      upnl=float(i))], keep_ms=0)
    return T0 + (n - 1) * step


def _times(store: LeaderStore) -> list[int]:
    return [r[0] for r in store.query(
        "SELECT observed_at FROM leader_positions ORDER BY observed_at")]


# --- reconciliaciones -------------------------------------------------------------------------

def test_recon_keeps_every_mismatch_and_one_confirmation_per_grid(tmp_path):
    store = _store(tmp_path)
    last = _feed_recon(store, 400)
    before = store.query("SELECT count(*), sum(resynced::INT) FROM leader_recon")[0]
    out = thin_recon(store, last + KEEP, keep_ms=KEEP, grid_ms=10 * MIN)
    rows = store.query("SELECT observed_at, resynced FROM leader_recon ORDER BY observed_at")
    cut = last + KEEP - KEEP
    kept_old = [t for t, r in rows if t < cut and not r]
    assert sum(1 for _, r in rows if r) == before[1]          # ninguna resincronizada se pierde
    assert len({t // (10 * MIN) for t in kept_old}) == len(kept_old)   # una por rejilla
    assert out.recon_dropped == before[0] - len(rows) > 0
    store.close()


def test_the_quality_report_adds_up_after_thinning(tmp_path):
    store = _store(tmp_path)
    last = _feed_recon(store, 400)
    want = summary(store, 0, last + 1)
    thin_recon(store, last + KEEP, keep_ms=KEEP, grid_ms=10 * MIN)
    got = summary(store, 0, last + 1)
    for key in ("checks", "size_ok", "match", "resynced", "coins_checked", "coins_skipped",
                "after_retry"):
        assert sum(r[key] for r in got["recon"]) == sum(r[key] for r in want["recon"]), key
    assert got["recon_summarized"]["days"] >= 1
    assert got["recon_summarized"]["clock_offset_max_ms"] >= 10
    store.close()


# --- fotos de posiciones ----------------------------------------------------------------------

def test_photos_keep_every_change_and_one_per_hour(tmp_path):
    store = _store(tmp_path)
    last = _feed_photos(store, 24 * 12)           # 24 h cada 5 min, forma nueva cada hora
    before = _times(store)
    out = thin_photos(store, last + KEEP, keep_ms=KEEP, photo_keep_ms=HOUR)
    after = _times(store)
    assert out.photos_dropped == len(before) - len(after) > 0
    shapes = {t: shape(r[0]) for t, r in
              ((t, store.query("SELECT positions FROM leader_positions WHERE observed_at = ?",
                               [t])[0]) for t in after)}
    assert len(set(shapes.values())) == 24        # ningún cambio de forma se pierde
    cut = last + KEEP - KEEP
    old = [t for t in after if t < cut]
    assert all(b - a <= HOUR for a, b in zip(old, old[1:], strict=False))
    store.close()


def test_the_captured_time_does_not_change_when_photos_are_deleted(tmp_path):
    ref, store = _store(tmp_path / "ref"), _store(tmp_path / "pod")
    last = _feed_photos(ref, 24 * 12)
    _feed_photos(store, 24 * 12)
    (ld,) = store.leaders()
    asof = last + KEEP
    want = context(ref, ld, asof)
    thin_photos(store, asof, keep_ms=KEEP, photo_keep_ms=HOUR)
    got = context(store, ld, asof)
    assert got.observed_ms == want.observed_ms
    assert got.forward_start == want.forward_start
    assert got.positions == want.positions           # la foto vigente sigue estando
    ref.close()
    store.close()


def test_batches_and_a_second_pass_give_the_same_result(tmp_path):
    one, many = _store(tmp_path / "a"), _store(tmp_path / "b")
    last = _feed_photos(one, 300)
    _feed_photos(many, 300)
    now = last + KEEP
    thin_photos(one, now, keep_ms=KEEP, photo_keep_ms=HOUR)
    thin_photos(many, now, keep_ms=KEEP, photo_keep_ms=HOUR, max_rows=7)
    assert _times(one) == _times(many)
    again = thin_photos(one, now, keep_ms=KEEP, photo_keep_ms=HOUR)
    assert again.photos_dropped == 0 and _times(one) == _times(many)
    one.close()
    many.close()


def test_nothing_else_is_touched(tmp_path):
    store = _store(tmp_path)
    store.add_fills([H.fill("BTC", 0, 1, 100.0, T0, 1)])
    last = max(_feed_photos(store, 100), _feed_recon(store, 100))
    def counts() -> dict:
        return {t: store.query(f"SELECT count(*) FROM {t}")[0][0]
                for t in ("leader_fills", "leader_follow", "leader_funding", "leader_gaps",
                          "leaders")}

    want = counts()
    out = retain(store, last + KEEP, keep_ms=KEEP)
    assert counts() == want
    assert isinstance(out, Retained) and bool(out)
    store.close()


def test_scoring_params_are_not_needed(tmp_path):
    """La retención no evalúa nada: no toca `ScoreParams` ni el archivo de T128."""
    store = _store(tmp_path)
    last = _feed_photos(store, 50)
    retain(store, last + KEEP, keep_ms=KEEP)
    assert store.query("SELECT count(*) FROM leader_archive")[0][0] == 0
    store.close()
