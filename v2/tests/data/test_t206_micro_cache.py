"""T206: los agregados de las velas cerradas se guardan y no se vuelven a calcular, y lo que
devuelve `read_micro` es exactamente lo mismo que calculándolo todo.

`/v2/snapshot` de 500 velas de 1 h tardaba 113 s en caliente (232 s en frío) el 2026-11-26 porque
cada carga del panel releía la ventana entera. La caché solo es aceptable si no mueve una cifra:
por eso aquí se compara campo a campo y sin tolerancia.
"""

from __future__ import annotations

import json
import random
import shutil

import pytest

from eim.data import micro, micro_cache
from eim.data.collectors.micro_feed import MicroFeed
from eim.data.micro import read_micro
from tests.data.hft_helpers import MS, SYM, T0, Exchange, capture, send, snap, trade

STEP, SEGUNDOS = 60_000, 600
T_MS = T0 // MS
BARS = SEGUNDOS * 1000 // STEP


def datos(root, seed=3):
    """Una ventana real de captura con su feed: fotos del libro cada segundo y un trade."""
    cap, store = capture(root)
    feed = MicroFeed(root, SYM)
    cap.on_book = feed.on_book
    ex, rng = Exchange(seed), random.Random(seed)
    for s in range(SEGUNDOS):
        t = T0 + s * 10**9 + 100 * MS
        e = t // MS - 110
        m, mid = ex.step(k=3, e_ms=e, snap_at=1 if s == 0 else None)
        send(cap, m, t)
        if s == 0:
            snap(cap, mid, t + 10 * MS)
        send(cap, trade(1000 + s, e + 5, p=100.0, q=round(rng.uniform(0.1, 3.0), 3),
                        maker=rng.random() < 0.5), t + 3 * MS)
    store.flush()
    feed.flush()
    return root


# `buy_v`, `sell_v` y `delta` ya variaban en el último bit entre corridas del mismo código antes
# de esta tarea (DuckDB suma en paralelo en el orden que quiere, BACKLOG T206 (4)); el OFI no.
EXACTOS = ("t", "trades", "complete", "ofi", "depth_imb")
SUMAS = ("buy_v", "sell_v", "delta")


def iguales(a, b) -> bool:
    """Mismas velas: sin tolerancia ninguna en el OFI y en el desequilibrio."""
    return len(a) == len(b) and all(
        all(getattr(x, f) == getattr(y, f) for f in EXACTOS)
        and all(getattr(x, f) == pytest.approx(getattr(y, f), rel=1e-9, abs=1e-12) for f in SUMAS)
        for x, y in zip(a, b, strict=True))


@pytest.fixture
def asentadas(monkeypatch):
    """Las velas de las pruebas son del futuro (T0): aquí se dan todas por asentadas."""
    monkeypatch.setattr(micro_cache, "settled", lambda *a, **k: True)


def sin_cache(monkeypatch, root, t0=T_MS, n=BARS):
    monkeypatch.setenv(micro.CACHE_ENV, "0")
    out = read_micro(root, SYM, t0, STEP, n)
    monkeypatch.delenv(micro.CACHE_ENV)
    return out


def test_lo_guardado_da_exactamente_lo_mismo_que_calcularlo_entero(tmp_path, monkeypatch,
                                                                   asentadas):
    root = datos(tmp_path)
    crudas, libro = sin_cache(monkeypatch, root)
    primera, lib1 = read_micro(root, SYM, T_MS, STEP, BARS)      # calcula y guarda
    segunda, lib2 = read_micro(root, SYM, T_MS, STEP, BARS)      # ya no calcula nada
    assert len(crudas) == BARS
    assert iguales(primera, crudas) and iguales(segunda, crudas)
    assert libro == lib1 == lib2 and libro is not None


def test_se_guarda_una_vela_por_archivo_de_dia_y_no_se_vuelve_a_leer_el_parquet(
        tmp_path, monkeypatch, asentadas):
    root = datos(tmp_path)
    read_micro(root, SYM, T_MS, STEP, BARS)
    archivos = list((root / micro_cache.DIR).rglob("*.json"))
    assert len(archivos) == 1
    assert len(json.loads(archivos[0].read_text(encoding="utf-8"))["bars"]) == BARS

    def no_leer(*a, **k):                      # si vuelve a tocar las fotos, falla
        raise AssertionError("releyó las fotos del libro teniéndolas guardadas")

    monkeypatch.setattr(micro, "_read_tops", no_leer)
    monkeypatch.setattr(micro, "_read_trade_bars", no_leer)
    assert len(read_micro(root, SYM, T_MS, STEP, BARS)[0]) == BARS


def test_una_ventana_que_empieza_mas_tarde_no_encadena_su_primera_vela(tmp_path, monkeypatch,
                                                                      asentadas):
    root = datos(tmp_path)
    read_micro(root, SYM, T_MS, STEP, BARS)                      # llena la caché entera
    desde = T_MS + 4 * STEP
    crudas, _ = sin_cache(monkeypatch, root, desde, BARS - 4)
    assert iguales(read_micro(root, SYM, desde, STEP, BARS - 4)[0], crudas)


def test_un_hueco_anotado_tarde_recalcula_la_vela_en_vez_de_darla_por_buena(tmp_path, monkeypatch,
                                                                           asentadas):
    root = datos(tmp_path)
    antes, _ = read_micro(root, SYM, T_MS, STEP, BARS)
    assert all(b.complete for b in antes[1:])
    cap, store = capture(root, run=T0 + 10**12)                  # el hueco llega después
    cap.hour = T0 // (3600 * 10**9)
    cap.gap("depth", "desconexion", T0 + 310 * 10**9, T0 + 320 * 10**9, T0 + 320 * 10**9, 0)
    store.flush()
    despues, _ = read_micro(root, SYM, T_MS, STEP, BARS)
    assert [b.complete for b in despues][5] is False
    assert iguales(despues, sin_cache(monkeypatch, root)[0])


def test_una_version_vieja_o_un_archivo_roto_se_ignoran(tmp_path, monkeypatch, asentadas):
    root = datos(tmp_path)
    buenas, _ = read_micro(root, SYM, T_MS, STEP, BARS)
    archivo = next((root / micro_cache.DIR).rglob("*.json"))
    archivo.write_text('{"version": 99, "bars": {}}', encoding="utf-8")
    assert iguales(read_micro(root, SYM, T_MS, STEP, BARS)[0], buenas)
    archivo.write_text("{roto", encoding="utf-8")
    assert iguales(read_micro(root, SYM, T_MS, STEP, BARS)[0], buenas)
    shutil.rmtree(root / micro_cache.DIR)                        # borrarla es seguro
    assert iguales(read_micro(root, SYM, T_MS, STEP, BARS)[0], buenas)


def test_una_vela_recien_cerrada_no_se_guarda(tmp_path):
    cierre = 1_700_000_000_000
    assert micro_cache.settled(cierre, cierre + micro_cache.SETTLE_MS) is True
    assert micro_cache.settled(cierre, cierre + micro_cache.SETTLE_MS - 1) is False
    entrada = (1.0, 2.0, 3, 4.0, 5.0, 0.5, 2, True, 0)
    assert micro_cache.save(tmp_path, SYM, STEP, False, {cierre - STEP: entrada},
                            now_ms=cierre) == 0
    assert micro_cache.save(tmp_path, SYM, STEP, False, {cierre - STEP: entrada},
                            now_ms=cierre + micro_cache.SETTLE_MS) == 1
    assert micro_cache.load(tmp_path, SYM, STEP, False, 0, cierre)[cierre - STEP] == entrada


def test_la_variable_de_entorno_apaga_la_cache(tmp_path, monkeypatch, asentadas):
    root = datos(tmp_path)
    monkeypatch.setenv(micro.CACHE_ENV, "0")
    read_micro(root, SYM, T_MS, STEP, BARS)
    assert not (root / micro_cache.DIR).exists()
