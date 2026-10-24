"""Proceso de captura HFT (T78) de punta a punta con WebSocket y REST simulados: conexión que se
corta y se recupera, diff perdido, resincronía por snapshot y latido. Sin red."""
from __future__ import annotations

import asyncio
import json

from eim.data.collectors import health, hft_ws
from eim.data.collectors.hft_clock import RecvClock
from eim.data.collectors.hft_read import hours_with_data, read_hour
from eim.data.collectors.hft_schema import AREA
from tests.data.hft_helpers import SYM, Exchange, bbo, mark, trade


class FakeWS:
    def __init__(self, msgs: list[dict], stop: asyncio.Event, fail: bool,
                 delay: float = 0.0) -> None:
        self.msgs, self.stop, self.fail, self.delay = msgs, stop, fail, delay

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        await asyncio.sleep(self.delay)
        for m in self.msgs:
            await asyncio.sleep(0.002)
            yield json.dumps({"stream": "x", "data": m})
        if self.fail:
            raise ConnectionError("corte simulado")
        while not self.stop.is_set():                       # conexión viva y callada
            await asyncio.sleep(0.01)


class FakeConnect:
    """Cada URL entrega sus tandas `(espera, mensajes)` en orden; la última no se corta."""

    def __init__(self, script: dict[str, list[tuple[float, list[dict]]]],
                 stop: asyncio.Event) -> None:
        self.script, self.stop, self.opened = script, stop, []

    def __call__(self, url: str, **kw):
        key = next(k for k in self.script if k in url)
        self.opened.append(key)
        batches = self.script[key]
        delay, msgs = batches.pop(0) if batches else (0.0, [])
        return FakeWS(msgs, self.stop, fail=bool(batches), delay=delay)


class FakeHttp:
    def __init__(self, snaps: list[dict]) -> None:
        self.snaps, self.calls = snaps, 0

    async def get(self, url, params):
        self.calls += 1
        snap = self.snaps.pop(0)

        class R:
            def raise_for_status(self):
                return None

            def json(self):
                return snap
        return R()


def test_proceso_completo_con_corte_hueco_y_resincronia(tmp_path, monkeypatch):
    monkeypatch.setattr(hft_ws, "RECONNECT_S", 0.01)
    monkeypatch.setattr(hft_ws, "SYNC_MIN_GAP_S", 0.01)
    monkeypatch.setattr(hft_ws, "CLOCK_EVERY_S", 0.05)
    monkeypatch.setattr(health, "HEARTBEAT_EVERY_S", 0.1)
    ex = Exchange(11)
    d1 = [ex.step()[0]]
    s1 = ex.snapshot()                                      # casa con el 1.er diff
    d1 += [ex.step()[0] for _ in range(9)]
    ex.step()                                               # se pierde en el corte
    d2 = [ex.step()[0]]
    s2 = ex.snapshot()
    d2 += [ex.step()[0] for _ in range(9)]
    now = 1_800_000_000_000
    trades = [trade(100 + i, now + i) for i in range(20)]

    async def go():
        stop = asyncio.Event()
        conn = FakeConnect({"depth@": [(0, d1), (0.8, d2)],      # vuelve con el libro ya listo
                            "bookTicker": [(0, [bbo(i, 99.9, 100.1, now) for i in range(5)])],
                            "market/": [(0, trades[:10] + [mark(now)]), (0, trades[10:])]}, stop)
        http = FakeHttp([s1, s2])

        async def stopper():
            for _ in range(300):                            # hasta 6 s
                await asyncio.sleep(0.02)
                if conn.opened.count("depth@") >= 2 and http.calls == 2:
                    break
            await asyncio.sleep(0.5)
            stop.set()

        await asyncio.gather(hft_ws.run(tmp_path, SYM, stop=stop, check_s=10**6, connect=conn,
                                        http=http), stopper())
        return conn, http

    conn, http = asyncio.run(go())
    assert http.calls == 2 and conn.opened.count("depth@") == 2
    hours = hours_with_data(tmp_path, SYM)
    depth = read_hour(tmp_path, SYM, "depth", hours[0])
    assert len(depth) == 20 and len(read_hour(tmp_path, SYM, "trades", hours[0])) == 20
    gaps = read_hour(tmp_path, SYM, "gaps", hours[0])
    causes = gaps["cause"].tolist()
    assert causes.count("desconexion") >= 2 and causes.count("secuencia") == 1
    assert causes.count("sin_libro") == 2
    book = read_hour(tmp_path, SYM, "book", hours[0])
    assert book["purpose"].tolist() == ["arranque", "sync", "sync"]
    hb = health.read_heartbeat(tmp_path, SYM, area=AREA)
    assert hb["synced"] and hb["counts"]["depth"] == 20 and hb["dropped"] == 0
    assert hb["gaps"]["secuencia"] == 1 and hb["write_errors"] == 0


def test_reloj_detecta_salto_y_ajusta_deriva():
    wall, mono = [1_000_000_000_000], [0]

    def w():
        wall[0] += 1                                        # cambia en cada lectura
        return wall[0]

    clk = RecvClock(wall=w, mono=lambda: mono[0])
    assert abs(clk.now()[0] - wall[0]) <= 2
    mono[0] += 10**9
    wall[0] += 10**9
    assert clk.check() is None                              # sin desviación
    wall[0] += 300_000_000                                   # NTP adelanta 300 ms
    kind, jump, _ = clk.check()
    assert kind == "salto" and abs(jump - 300_000_000) < 10
    for _ in range(6):                                      # deriva lenta de 7 ms
        mono[0] += 10**9
        wall[0] += 10**9
    wall[0] += 7_000_000
    res = [clk.check() for _ in range(6)]
    assert res[:5] == [None] * 5 and res[5][0] == "ajuste" and abs(res[5][1] - 7e6) < 20
