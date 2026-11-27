"""T206: el registro del vigilante no vuelve a crecer con la misma línea repetida."""

from __future__ import annotations

import io
from collections import deque

from eim.operation import watchdog


def _pump(lines: list[str], monkeypatch, tail: deque | None = None) -> str:
    buf = io.StringIO()
    monkeypatch.setattr(watchdog.sys, "stderr", buf)
    watchdog._pump(iter(lines), "stderr", tail)
    return buf.getvalue()


def test_una_linea_repetida_se_cuenta_en_vez_de_escribirse(monkeypatch):
    ruido = "socket.send() raised exception.\n"
    salida = _pump([ruido] * 1000 + ["otra cosa\n"], monkeypatch)
    filas = salida.splitlines()
    assert sum("socket.send()" in f for f in filas) == 1          # la línea, una sola vez
    assert "otra cosa" in filas[-1]
    assert len(filas) <= 5                                        # y tres recuentos a lo sumo
    assert sum(int(f.split(", ")[1].split(" ")[0])                # 999 repeticiones contadas
               for f in filas if "la línea anterior" in f) == 999


def test_el_tope_deja_un_recuento_sin_esperar_a_que_cambie(monkeypatch):
    salida = _pump(["igual\n"] * (watchdog.REPEAT_FLUSH + 1), monkeypatch)
    assert f"la línea anterior, {watchdog.REPEAT_FLUSH} veces más" in salida


def test_las_lineas_distintas_salen_todas_y_en_orden(monkeypatch):
    salida = _pump([f"linea {i}\n" for i in range(5)], monkeypatch)
    assert [f.split(" ", 1)[1] for f in salida.splitlines()] == [f"linea {i}" for i in range(5)]


def test_el_tail_del_reinicio_deja_de_ser_ocho_veces_lo_mismo(monkeypatch):
    tail: deque = deque(maxlen=30)
    _pump(["ruido\n"] * 50 + ["IOException: se acabó\n"], monkeypatch, tail)
    assert list(tail) == ["ruido", "(la línea anterior, 49 veces más)", "IOException: se acabó"]
