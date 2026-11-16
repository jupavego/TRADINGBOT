"""La cantera con su pre-registro (T170): solo los inscritos, alta anotada y todos en guardería."""

from __future__ import annotations

import pytest

from eim.api.paper_variant import make_nursery
from eim.core import Candle
from eim.data.paper_store import PaperStore
from eim.data.store import Store
from eim.nursery.desk import NurseryDesk
from eim.nursery.params import NurseryParams
from eim.nursery.prereg import family_prospects, load_prereg
from eim.nursery.prospect import load_prospects
from tests.nursery.helpers import H1, M15, T0, make_ctxs, make_path

PR = load_prereg()
N = len(PR.family.members)


@pytest.fixture()
def stores(tmp_path):
    path = make_path(96 * 5)
    store = Store(tmp_path / "data")
    cs = [Candle(t=int(t), o=o, h=h, l=lo, c=c, v=1.0)
          for t, o, h, lo, c in zip(path.t, path.o, path.h, path.l, path.c, strict=True)]
    store.upsert_candles("BTCUSDT", "15m", cs, "prueba")
    store.upsert_series("funding", "BTCUSDT", "-", list(zip(path.ft.tolist(), path.fr.tolist(),
                                                           strict=True)), "prueba")
    main = PaperStore(tmp_path / "data" / "paper.duckdb")
    for tf, ms in (("15m", M15), ("1h", H1), ("4h", 4 * H1)):
        for c in make_ctxs(path, ms, seed=ms % 97):
            main.save("BTCUSDT", tf, c, "vivo", 0)
    own = PaperStore(tmp_path / "data" / "paper_cantera.duckdb")
    yield store, main, own, tmp_path / "data"
    main.close()
    own.close()


def test_desk_with_prereg_runs_only_the_family_and_starts_in_nursery(stores):
    store, main, own, _ = stores
    ps = family_prospects(PR, load_prospects())
    d = NurseryDesk(store, main, own, prospects=ps, prereg=PR, params=NurseryParams())
    now = T0 + 2 * 24 * H1
    book = d.compute(now=now)
    assert book is not None and book.prospect_count == N
    s = d.summary()
    assert s["prereg"]["version"] == "prereg_cantera_v1" and s["prereg"]["alta_ms"] == now
    assert s["prereg"]["family_m"] == PR.m and s["prereg"]["stages"] == {"guarderia": N}
    rows = [a for a in s["accounts"] if a["kind"] == "prospecto"]
    assert len(rows) == N and all(a["stage"] == "guarderia" for a in rows)
    assert all(e.trade.fill_t is None or e.t >= now for e in book.entries)
    assert d.compute(now=now + 10 * H1) is not None
    assert own.execute("SELECT alta_ms FROM nursery_prereg")[0][0] == now   # el alta no se mueve


def test_alta_with_another_hash_is_refused(stores):
    store, main, own, _ = stores
    ps = family_prospects(PR, load_prospects())
    d = NurseryDesk(store, main, own, prospects=ps, prereg=PR)
    d.compute(now=T0)
    other = PR.model_copy(update={"sha256": "0" * 64})
    with pytest.raises(ValueError, match="cantera_v2"):
        NurseryDesk(store, main, own, prospects=ps, prereg=other).compute(now=T0 + H1)


def test_nothing_runs_before_not_before(stores):
    store, main, own, _ = stores
    ps = family_prospects(PR, load_prospects())
    d = NurseryDesk(store, main, own, prospects=ps, prereg=PR,
                    params=NurseryParams(start_ms=T0 + 10 * H1))
    assert d.compute(now=T0) is None
    assert own.execute("SELECT count(*) FROM nursery_prereg")[0][0] == 0


def test_make_nursery_loads_the_prereg_or_blocks(stores, monkeypatch):
    store, main, _, data_dir = stores
    for sub in ("x", "y"):
        (data_dir / sub).mkdir()
    d = make_nursery(True, (), store, data_dir / "x", main, {})
    assert d.prereg is not None and len(d.prospects) == N and not d.blocked
    d.pstore.close()

    def bad(*a, **k):
        raise ValueError("huella distinta")
    monkeypatch.setattr("eim.nursery.prereg.load_prereg", bad)
    blocked = make_nursery(True, (), store, data_dir / "y", main, {})
    assert blocked.blocked and not blocked.prospects
    blocked.tick()
    assert "bloqueada" in blocked.live_status()["error"]
    blocked.pstore.close()
