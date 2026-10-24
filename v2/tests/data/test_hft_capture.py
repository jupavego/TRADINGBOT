"""Captura HFT (T78): filas con doble reloj y tramos marcados (hueco, reordenamiento,
reconexión, saturación de cola, cambio de hora). Secuencias simuladas, sin red."""
from __future__ import annotations

import asyncio

from eim.data.collectors.hft_read import read_hour
from eim.data.collectors.hft_schema import HOUR_NS
from eim.data.collectors.hft_ws import Inbox
from tests.data.hft_helpers import (
    MS,
    SYM,
    T0,
    Exchange,
    bbo,
    capture,
    liq,
    mark,
    send,
    snap,
    trade,
)

H = T0 // HOUR_NS


def _synced(tmp_path, seed=0):
    """Captura con el libro ya sincronizado; devuelve (captura, almacén, exchange, t)."""
    cap, store = capture(tmp_path)
    ex = Exchange(seed)
    t = T0 + 10 * MS
    send(cap, ex.step(e_ms=t // MS)[0], t)
    snap(cap, ex.snapshot(), t + 50 * MS)
    return cap, store, ex, t + 100 * MS


def _gaps(tmp_path, hour=H):
    return read_hour(tmp_path, SYM, "gaps", hour)


def test_todas_las_tablas_con_los_dos_relojes(tmp_path):
    cap, store, ex, t = _synced(tmp_path)
    for i in range(5):
        send(cap, ex.step(e_ms=t // MS - 110)[0], t)
        send(cap, bbo(10 + i, 99.9, 100.1, t // MS - 120), t + MS)
        send(cap, trade(500 + i, t // MS - 115), t + 2 * MS)
        send(cap, mark(t // MS - 160), t + 3 * MS)
        t += 100 * MS
    send(cap, liq(t // MS), t)
    send(cap, {"e": "aggTrade", "s": "ETHUSDT", "a": 1}, t)       # otro símbolo: se ignora
    store.flush()
    d = read_hour(tmp_path, SYM, "depth", H)
    assert len(d) == 6 and (d["recv_ns"] // MS - d["e_ms"] >= 0).all()
    assert d["mono_ns"].is_monotonic_increasing and d["seq"].is_monotonic_increasing
    assert len(read_hour(tmp_path, SYM, "bbo", H)) == 5
    assert len(read_hour(tmp_path, SYM, "trades", H)) == 5
    m = read_hour(tmp_path, SYM, "mark", H)
    assert len(m) == 5 and (m["funding"] == 0.0001).all()
    assert read_hour(tmp_path, SYM, "liq", H)["side"].tolist() == ["SELL"]
    book = read_hour(tmp_path, SYM, "book", H)
    assert book["purpose"].tolist() == ["arranque", "sync"]
    assert set(_gaps(tmp_path)["cause"]) == {"sin_libro"}          # arranque → sincronía
    assert cap.status()["synced"] and cap.counts["depth"] == 6


def test_hueco_de_secuencia_se_marca_y_resincroniza(tmp_path):
    cap, store, ex, t = _synced(tmp_path, 1)
    send(cap, ex.step()[0], t)
    ex.step()                                                      # diff perdido
    send(cap, ex.step()[0], t + 100 * MS)
    assert cap.wants_sync()
    snap(cap, ex.snapshot(), t + 300 * MS)
    send(cap, ex.step()[0], t + 400 * MS)
    store.flush()
    g = _gaps(tmp_path)
    assert g["cause"].tolist() == ["sin_libro", "secuencia", "sin_libro"]
    sec = g[g["cause"] == "secuencia"].iloc[0]
    assert sec["start_ns"] == t and sec["end_ns"] == t + 100 * MS
    again = g.iloc[-1]                                             # sin libro hasta el snapshot
    assert again["start_ns"] == t + 100 * MS and again["end_ns"] == t + 300 * MS
    assert cap.vb.book.bids == ex.bids


def test_reordenamiento_e_ids_de_trades(tmp_path):
    cap, store, _, t = _synced(tmp_path)
    send(cap, trade(10, 1000), t)
    send(cap, trade(11, 1001), t + MS)
    send(cap, trade(14, 1002), t + 2 * MS)                         # faltan 12 y 13
    send(cap, trade(13, 999), t + 3 * MS)                          # llega tarde: reordenado
    store.flush()
    ids = _gaps(tmp_path)
    row = ids[ids["cause"] == "ids_trades"].iloc[0]
    assert row["n"] == 2 and "esperado 12" in row["detail"]
    assert cap.reorders["trades"] == 1


def test_reconexion_marca_desconexion_y_silencio(tmp_path):
    cap, store, ex, t = _synced(tmp_path, 2)
    send(cap, mark(t // MS), t)
    cap.handle(("close", "market", "ConnectionClosedError: 1006", t + MS, t + MS - T0))
    cap.handle(("open", "market"))
    send(cap, mark(t // MS + 5000), t + 5 * 10**9)                 # 5 s después
    store.flush()
    g = _gaps(tmp_path)
    assert {"desconexion", "silencio"} <= set(g["cause"])
    sil = g[g["cause"] == "silencio"].iloc[0]
    assert sil["stream"] == "mark" and sil["end_ns"] - sil["start_ns"] == 5 * 10**9


def test_cambio_de_hora_fija_el_libro_y_corta_el_tramo_sin_libro(tmp_path):
    cap, store = capture(tmp_path)
    ex = Exchange(3)
    send(cap, ex.step()[0], T0 + 10 * MS)                          # sin libro desde el arranque
    nxt = T0 + HOUR_NS + 5 * MS
    send(cap, ex.step()[0], nxt)
    snap(cap, ex.snapshot(), nxt + 100 * MS)
    send(cap, ex.step()[0], nxt + 200 * MS)
    store.flush()
    assert read_hour(tmp_path, SYM, "book", H + 1)["purpose"].tolist() == ["hora", "sync"]
    g = _gaps(tmp_path, H + 1)
    assert g["cause"].tolist() == ["sin_libro", "silencio", "sin_libro"]   # 1 h callado
    sl = g[g["cause"] == "sin_libro"]
    assert sl["start_ns"].tolist() == [T0, nxt] and sl["end_ns"].tolist() == [nxt, nxt + 100 * MS]


def test_saturacion_de_cola_descarta_y_marca(tmp_path):
    async def go():
        inbox = Inbox(maxsize=4)
        acc = [inbox.offer("bbo", ("msg", "bbo", "{}", T0 + i, i), T0 + i, i) for i in range(10)]
        assert acc == [True] * 4 + [False] * 6 and inbox.dropped == 6
        items = [inbox.q.get_nowait() for _ in range(4)]
        assert inbox.offer("bbo", ("msg", "bbo", "{}", T0 + 99, 99), T0 + 99, 99)
        return items, [inbox.q.get_nowait() for _ in range(inbox.q.qsize())]

    items, after = asyncio.run(go())
    assert after[0] == ("overflow", "bbo", 6, T0 + 4, T0 + 9, T0 + 99, 99)
    cap, store, _, t = _synced(tmp_path)
    cap.handle(after[0])
    store.flush()
    row = _gaps(tmp_path).iloc[-1]
    assert row["cause"] == "cola_llena" and row["n"] == 6 and row["stream"] == "bbo"


def test_verificacion_rest_y_salto_de_reloj_quedan_en_tablas(tmp_path):
    cap, store, ex, t = _synced(tmp_path, 4)
    for i in range(6):
        m, mid = ex.step(k=4, e_ms=t // MS, snap_at=2 if i == 3 else None)
        send(cap, m, t)
        if mid:
            snap(cap, mid, t + 50 * MS, "check")
        t += 100 * MS
    cap.handle(("clock", "salto", 250 * MS, t, t, t - T0))
    store.flush()
    c = read_hour(tmp_path, SYM, "checks", H)
    assert c["comparable"].tolist() == [True] and c["match"].tolist() == [True]
    assert len(c["book_hash"].iloc[0]) == 24 and cap.status()["match_rate"] == 1.0
    k = read_hour(tmp_path, SYM, "clock", H)
    assert k["kind"].tolist() == ["salto"] and k["jump_ns"].tolist() == [250 * MS]
    assert read_hour(tmp_path, SYM, "snap", H)["purpose"].tolist() == ["sync", "check"]
