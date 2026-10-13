"""Recolector: reconstrucción del libro con secuencias simuladas (incluida una con hueco)."""
from __future__ import annotations

from eim.data.collectors.binance_ws import Collector
from eim.data.collectors.book import LocalBook
from eim.data.micro import read_micro

H = 3_600_000
T0 = 1_700_000_000_000 // H * H
SNAP = {"lastUpdateId": 100, "bids": [["99", "5"], ["98", "5"]],
        "asks": [["101", "5"], ["102", "5"]]}


def _ev(U, u, pu, b=(), a=(), t=T0):
    return {"e": "depthUpdate", "T": t, "E": t, "U": U, "u": u, "pu": pu,
            "b": [list(x) for x in b], "a": [list(x) for x in a]}


def _tr(a, q, t, m):
    return {"data": {"e": "aggTrade", "a": a, "p": "100", "q": q, "T": t, "m": m}}


def _book() -> LocalBook:
    bk = LocalBook()
    bk.load_snapshot(SNAP["lastUpdateId"], SNAP["bids"], SNAP["asks"])
    return bk


def test_stale_descartado_y_primer_evento_valido():
    bk = _book()
    assert bk.apply(90, 99, 89, [], []) == "stale"
    assert bk.apply(95, 105, 94, [("99", "7")], []) == "ok"
    assert bk.bids[99.0] == 7
    assert bk.apply(106, 110, 105, [], [("101", "0")]) == "ok"
    assert 101.0 not in bk.asks


def test_hueco_de_secuencia_descarta_el_libro():
    bk = _book()
    assert bk.apply(95, 105, 94, [], []) == "ok"
    assert bk.apply(106, 110, 105, [("99", "9")], []) == "ok"
    assert bk.apply(120, 125, 115, [("99", "1")], []) == "gap"  # faltan 111..119
    assert not bk.synced and not bk.bids and not bk.asks
    assert bk.apply(126, 130, 125, [], []) == "unsynced"


def test_snapshot_mas_viejo_que_el_primer_evento_es_hueco():
    assert _book().apply(150, 160, 149, [], []) == "gap"


def test_niveles_fantasma_se_podan():
    bk = _book()
    bk.apply(95, 105, 94, [], [])
    # un bid llega por encima del ask: el ask 101 era fantasma (su borrado se perdió)
    assert bk.apply(106, 110, 105, [("101.5", "3")], []) == "ok"
    assert bk.ghosts_pruned == 1
    assert max(bk.bids) < min(bk.asks)


def test_colector_registra_hueco_pide_snapshot_y_agrega(tmp_path):
    c = Collector(tmp_path, "ETHUSDT", top_every_ms=0)
    c.load_snapshot(SNAP)
    c.on_message({"data": _ev(95, 105, 94, [("99", "6")], [("101", "4")], T0 + 1000)})
    c.on_message({"data": _ev(106, 110, 105, [("99", "8")], [], T0 + 2000)})
    c.on_message(_tr(1, "2", T0 + 2100, False))
    c.on_message(_tr(2, "1", T0 + 2200, True))
    c.on_message(_tr(5, "1", T0 + 2300, True))
    c.on_message({"data": _ev(200, 205, 199, [], [], T0 + 3000)})  # hueco de profundidad
    assert c.need_snapshot and c.gaps == 2
    c.flush()
    bars, book = read_micro(tmp_path, "ETHUSDT", T0, H, 1)
    assert len(bars) == 1
    b = bars[0]
    assert (b.buy_v, b.sell_v, b.delta, b.trades) == (2.0, 2.0, 0.0, 3)
    assert b.complete is False  # hubo huecos en la vela
    # OFI entre las dos muestras: el bid subió su tamaño 6→8 (+2) sin cambio en ask
    assert b.ofi == 2.0
    assert book is not None and book.bids[0] == (99.0, 8.0)


def test_sin_recoleccion_no_hay_micro(tmp_path):
    assert read_micro(tmp_path, "ETHUSDT", T0, H, 5) == ([], None)
