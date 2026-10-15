"""Fotografías de arbitraje en disco (T39): sin mirar al futuro, poda y snapshot."""

from __future__ import annotations

from eim.data.arb_store import ArbStore
from eim.data.arb_sync import ArbSync, CachedArbData
from eim.data.snapshot import build_snapshot
from eim.data.store import Store
from tests.arbitrage.helpers import ASOF, carry_market

MIN = 60_000


def at(t: int):
    return carry_market(0.0005).model_copy(update={"asof": t})


def test_save_latest_and_no_lookahead(tmp_path):
    st = ArbStore(tmp_path)
    assert st.latest() is None and st.at(ASOF) is None
    st.save(at(ASOF))
    st.save(at(ASOF + MIN))
    assert st.latest().asof == ASOF + MIN
    assert st.at(ASOF + 30_000).asof == ASOF  # nunca la posterior
    assert st.at(ASOF - 1) is None
    assert st.at(ASOF + MIN + 11 * MIN) is None  # demasiado vieja (> 10 min)
    assert st.at(ASOF + 3 * MIN, max_age_ms=5 * MIN).asof == ASOF + MIN


def test_prunes_to_keep(tmp_path):
    st = ArbStore(tmp_path, keep=3)
    for i in range(6):
        st.save(at(ASOF + i * MIN))
    files = sorted(p.name for p in (tmp_path / "arbitrage").glob("scan_*.json"))
    assert files == [f"scan_{ASOF + i * MIN}.json" for i in (3, 4, 5)]


def test_corrupt_file_is_ignored(tmp_path):
    st = ArbStore(tmp_path)
    st.save(at(ASOF))
    (tmp_path / "arbitrage" / f"scan_{ASOF + MIN}.json").write_text("{", encoding="utf-8")
    assert st.latest() is None  # la más reciente está a medio escribir: no se inventa
    assert st.at(ASOF + 1).asof == ASOF


def test_build_snapshot_attaches_photo(tmp_path):
    store = Store(tmp_path)
    assert build_snapshot(store, "BTCUSDT", "1h", 10, asof=ASOF).arb is None
    ArbStore(tmp_path).save(at(ASOF - 20_000))
    snap = build_snapshot(store, "BTCUSDT", "1h", 10, asof=ASOF)
    assert snap.arb is not None and snap.arb.asof == ASOF - 20_000
    assert snap.sources["arb"] == "binance-futures+binance-spot"
    assert snap.coverage["arb"] == (ASOF - 20_000, ASOF - 20_000)
    # reproducción de un instante anterior: la fotografía aún no existía
    assert build_snapshot(store, "BTCUSDT", "1h", 10, asof=ASOF - 60_000).arb is None


class _Counting(CachedArbData):
    def __init__(self) -> None:
        super().__init__(spot=object(), futures=object(), clock=lambda: ASOF)  # type: ignore[arg-type]
        self.calls = 0

    def _fetch(self):
        self.calls += 1
        return []


def test_metadata_is_cached(tmp_path):
    prov = _Counting()
    prov._cached("spot_pairs", prov._fetch)
    prov._cached("spot_pairs", prov._fetch)
    assert prov.calls == 1
    prov.meta_ttl_s = 0
    prov._cached("spot_pairs", prov._fetch)
    assert prov.calls == 2


class _FakeArb:
    """Proveedor mínimo sin red: un perpetuo y su libro."""

    clock = staticmethod(lambda: ASOF)

    def spot_pairs(self):
        return carry_market(0.0005).spot_pairs

    def futures_contracts(self):
        return carry_market(0.0005).contracts

    def premium_index(self):
        return carry_market(0.0005).premium

    def spot_book(self, symbol, depth):
        return carry_market(0.0005).spot_books[symbol], ASOF

    def futures_book(self, symbol, depth):
        return carry_market(0.0005).futures_books[symbol], ASOF

    def funding_history(self, symbol, start, end):
        return []


def test_sync_run_once_persists(tmp_path):
    sync = ArbSync(tmp_path, _FakeArb(), assets=("BTC",))  # type: ignore[arg-type]
    mkt = sync.run_once()
    assert ArbStore(tmp_path).latest() == mkt == sync.last
    assert "book:spot:BTCUSDT" in mkt.coverage and mkt.asof == ASOF
