"""Conversor a eventos del simulador (T78): ida y vuelta, el libro reconstruido desde el archivo
es el del recolector (con hueco, resincronía, libro fantasma, cambio de hora y reinicio)."""
from __future__ import annotations

import numpy as np

from eim.data.collectors import hft_events as E
from eim.data.collectors.hft_book import book_hash
from eim.data.collectors.hft_schema import HOUR_NS
from eim.data.collectors.hft_verify import main as verify_main
from eim.data.collectors.hft_verify import verify_hour
from tests.data.hft_helpers import (
    MS,
    SYM,
    T0,
    Exchange,
    bbo,
    capture,
    depth,
    liq,
    mark,
    send,
    snap,
    trade,
)

H = T0 // HOUR_NS


def _hash(book) -> str:
    return book_hash(book.bids, book.asks)


def scenario(tmp_path):
    """Dos horas de captura con todo lo que cambia el libro; devuelve las huellas del libro del
    recolector al final de la 1.ª hora y al final de todo."""
    ex = Exchange(7)
    cap, store = capture(tmp_path)
    t = T0 + 10 * MS
    send(cap, ex.step(e_ms=t // MS)[0], t)
    snap(cap, ex.snapshot(), t + 30 * MS)
    for i in range(300):
        t += 100 * MS
        if i == 100:
            ex.step()                                              # diff perdido → resincronía
        m, mid = ex.step(k=4, e_ms=t // MS, snap_at=2 if i % 40 == 20 else None)
        send(cap, m, t)
        if i == 101:
            snap(cap, ex.snapshot(), t + 20 * MS)
        if i == 150:
            cap.vb.book.bids[99.95] = 3.0                          # libro fantasma
        if mid is not None:
            snap(cap, mid, t + 60 * MS, "check")
        send(cap, bbo(i, 99.9, 100.1, t // MS), t + MS)
        send(cap, trade(10 + i, t // MS, maker=i % 2 == 0), t + 2 * MS)
        if i % 10 == 0:
            send(cap, mark(t // MS), t + 3 * MS)
    send(cap, liq(t // MS), t + 4 * MS)
    end_h1 = _hash(cap.vb.book)
    t = T0 + HOUR_NS + 50 * MS                                     # hora siguiente
    for i in range(20):
        m, mid = ex.step(k=4, e_ms=t // MS, snap_at=2 if i == 10 else None)
        send(cap, m, t)
        if mid is not None:
            snap(cap, mid, t + 60 * MS, "check")
        t += 100 * MS
    store.flush()
    cap2, store2 = capture(tmp_path, run=t)                        # reinicio del proceso
    send(cap2, ex.step(e_ms=t // MS)[0], t + 10 * MS)
    snap(cap2, ex.snapshot(), t + 40 * MS)
    for _ in range(30):
        t += 100 * MS
        send(cap2, ex.step(k=2, e_ms=t // MS)[0], t)
    store2.flush()
    return cap, cap2, end_h1


def test_ida_y_vuelta_reproduce_el_libro_del_recolector(tmp_path):
    cap, cap2, end_h1 = scenario(tmp_path)
    assert cap.gaps["secuencia"] == 1 and cap.gaps["divergencia"] == 1
    r1 = verify_hour(tmp_path, SYM, H)
    assert r1["checks"] >= 5 and r1["checks_equal"] == r1["checks"]
    assert r1["final_compared"] and r1["final_equal"] and r1["ok"]
    ev1, _ = E.convert_hour(tmp_path, SYM, H)
    assert book_hash(*E.replay(ev1)) == end_h1
    ev2, meta = E.convert_hour(tmp_path, SYM, H + 1)
    assert book_hash(*E.replay(ev2)) == _hash(cap2.vb.book)       # tras el reinicio
    assert meta["counts"]["clear"] >= 3 and meta["source"].startswith("micro_hft")
    assert verify_hour(tmp_path, SYM, H + 1)["ok"]


def test_npz_conserva_los_eventos_y_el_orden(tmp_path):
    scenario(tmp_path)
    ev, meta = E.convert_hour(tmp_path, SYM, H)
    assert E.EVENT_DTYPE.itemsize == 64
    p = E.save_npz(tmp_path / "out" / "h.npz", ev, meta)
    ev2, meta2 = E.load_npz(p)
    assert np.array_equal(ev, ev2) and meta2 == meta
    types = ev["ev"] & E.TYPE_MASK
    assert types[0] == E.CLEAR                    # la hora arranca con el libro (vacío al inicio)
    assert (ev["local_ts"][np.isin(types, (E.DEPTH, E.BBO, E.TRADE))] > 0).all()
    tr = ev[types == E.TRADE]
    assert ((tr["ev"] & E.SELL) > 0).sum() == 150 and tr["order_id"].min() == 10
    gaps = ev[types == E.GAP]
    codes = {int(x >> 8) & 0xFF for x in gaps["ev"]}
    assert E.CAUSE_CODE["secuencia"] in codes and E.CAUSE_CODE["divergencia"] in codes
    ck = ev[types == E.CHECK]
    assert set(ck["fval"].tolist()) == {0.0, 1.0}                   # hubo una divergencia


def test_niveles_fantasma_podados_viajan_como_eventos(tmp_path):
    cap, store = capture(tmp_path)
    ex = Exchange(8)
    send(cap, ex.step()[0], T0 + MS)
    snap(cap, ex.snapshot(), T0 + 2 * MS)
    u = ex.u
    send(cap, depth(u + 1, u + 1, u, b=[(100.15, 1.0)]), T0 + 3 * MS)   # cruza: poda asks
    send(cap, depth(u + 2, u + 2, u + 1, a=[(100.05, 2.0)]), T0 + 4 * MS)
    store.flush()
    assert cap.vb.book.ghosts_pruned >= 2
    ev, _ = E.convert_hour(tmp_path, SYM, H)
    pruned = ev[(ev["ev"] & E.PRUNED) > 0]
    assert len(pruned) == cap.vb.book.ghosts_pruned and (pruned["qty"] == 0).all()
    assert book_hash(*E.replay(ev)) == _hash(cap.vb.book)


def test_cli_verifica_y_escribe_npz(tmp_path, capsys):
    scenario(tmp_path)
    label = E.hour_label(H)
    assert verify_main(["--root", str(tmp_path), "--hour", label, "--out",
                        str(tmp_path / "npz")]) == 0
    assert (tmp_path / "npz" / f"{SYM}_{label}.npz").exists()
    assert "1/1 horas reproducen" in capsys.readouterr().out
