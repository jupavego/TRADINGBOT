"""Libro verificado (T78): sincronía con diffs acumulados y verificación contra snapshots REST."""
from __future__ import annotations

from eim.data.collectors.hft_book import Diff, VerifiedBook, book_hash, top_of
from tests.data.hft_helpers import Exchange


def _diff(msg: dict) -> Diff:
    f = lambda xs: [(float(p), float(q)) for p, q in xs]  # noqa: E731
    return Diff(msg["U"], msg["u"], msg["pu"], f(msg["b"]), f(msg["a"]))


def _same_as(vb: VerifiedBook, ex: Exchange) -> bool:
    return vb.book.bids == ex.bids and vb.book.asks == ex.asks


def test_sincroniza_con_snapshot_tardio_y_diffs_acumulados():
    ex, vb = Exchange(1), VerifiedBook()
    msgs = [ex.step()[0] for _ in range(3)]
    s = ex.snapshot()                                  # tomado tras el 3.º diff…
    msgs += [ex.step()[0] for _ in range(4)]           # …pero llega cuando ya hay 7
    assert all(vb.on_diff(_diff(m)) == "buffered" for m in msgs)
    assert vb.on_snapshot(s["lastUpdateId"], s["bids"], s["asks"]) == "synced"
    assert vb.reset == "sync" and not vb.awaiting and _same_as(vb, ex)
    m = ex.step()[0]
    assert vb.on_diff(_diff(m)) == "ok" and _same_as(vb, ex)


def test_snapshot_mas_viejo_que_lo_acumulado_no_sirve():
    ex, vb = Exchange(2), VerifiedBook()
    s = ex.snapshot()
    ex.step()                                          # este diff se perdió (no llega)
    m = ex.step()[0]
    vb.on_diff(_diff(m))
    assert vb.on_snapshot(s["lastUpdateId"], s["bids"], s["asks"]) == "stale_snapshot"
    assert vb.awaiting and len(vb.pending) == 1 and vb.reset is None
    s2 = ex.snapshot()
    assert vb.on_snapshot(s2["lastUpdateId"], s2["bids"], s2["asks"]) == "synced"


def test_verificacion_a_mitad_de_un_diff_coincide():
    ex, vb = Exchange(3), VerifiedBook()
    vb.on_diff(_diff(ex.step()[0]))
    s = ex.snapshot()
    vb.on_snapshot(s["lastUpdateId"], s["bids"], s["asks"])
    checks = []
    for i in range(40):
        m, mid = ex.step(k=4, snap_at=2 if i % 5 == 0 else None)
        vb.on_diff(_diff(m))
        if mid is not None:                            # L cae dentro del diff ya aplicado
            assert mid["lastUpdateId"] < m["u"]
            assert vb.on_snapshot(mid["lastUpdateId"], mid["bids"], mid["asks"]) == "checked"
        checks += vb.checks
        vb.checks.clear()
    assert len(checks) == 8 and all(c.comparable and c.match for c in checks)
    assert _same_as(vb, ex)


def test_snapshot_adelantado_espera_al_diff_que_lo_contiene():
    ex, vb = Exchange(4), VerifiedBook()
    vb.on_diff(_diff(ex.step()[0]))
    s = ex.snapshot()
    vb.on_snapshot(s["lastUpdateId"], s["bids"], s["asks"])
    vb.on_diff(_diff(ex.step()[0]))
    m, mid = ex.step(k=5, snap_at=3)
    assert vb.on_snapshot(mid["lastUpdateId"], mid["bids"], mid["asks"]) == "waiting"
    assert vb.on_diff(_diff(m)) == "ok"
    assert [c.match for c in vb.checks] == [True] and vb.checks[0].at_id == m["u"]


def test_libro_fantasma_se_detecta_y_se_rehace():
    ex, vb = Exchange(5), VerifiedBook()
    vb.on_diff(_diff(ex.step()[0]))
    s = ex.snapshot()
    vb.on_snapshot(s["lastUpdateId"], s["bids"], s["asks"])
    vb.reset = None
    vb.on_diff(_diff(ex.step()[0]))
    vb.book.bids[99.95] = 7.0                         # nivel que el exchange no tiene
    m, mid = ex.step(k=3, snap_at=3)
    vb.on_diff(_diff(m))
    later = ex.step()[0]
    vb.on_diff(_diff(later))                           # aplicado antes de que llegue el REST
    assert vb.on_snapshot(mid["lastUpdateId"], mid["bids"], mid["asks"]) == "checked"
    c = vb.checks[0]
    assert c.comparable and not c.match and c.n_diff > 0 and "99.95" in c.detail
    assert vb.reset == "divergencia" and _same_as(vb, ex)   # rehecho y con el diff posterior


def test_hueco_de_secuencia_pierde_el_libro_y_marca_los_pendientes():
    ex, vb = Exchange(6), VerifiedBook()
    vb.on_diff(_diff(ex.step()[0]))
    s = ex.snapshot()
    vb.on_snapshot(s["lastUpdateId"], s["bids"], s["asks"])
    vb.on_diff(_diff(ex.step()[0]))
    m, mid = ex.step(k=3, snap_at=3)
    ex.step()                                          # perdido
    vb.on_snapshot(mid["lastUpdateId"] + 50, mid["bids"], mid["asks"])  # en espera
    assert vb.on_diff(_diff(ex.step()[0])) == "gap"
    assert vb.awaiting and len(vb.pending) == 1 and not vb.book.bids
    assert [c.comparable for c in vb.checks] == [False]


def test_huella_y_top():
    b, a = {99.0: 1.0, 98.0: 2.0}, {101.0: 3.0}
    assert book_hash(b, a) == book_hash(dict(reversed(list(b.items()))), a)
    assert book_hash(b, a) != book_hash({99.0: 1.5, 98.0: 2.0}, a)
    assert top_of(b, a, 1) == (((99.0, 1.0),), ((101.0, 3.0),))
