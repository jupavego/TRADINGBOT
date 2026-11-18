"""T183: intermercado en disco — solo velas cerradas a `asof`, ritmo propio y fallos aislados."""
from __future__ import annotations

from eim.core import Candle
from eim.data import intermarket as im

DAY = im.DAY_MS
T0 = 1_700_000_000_000 // DAY * DAY


def _bars(n: int, offset: int = 0) -> list[Candle]:
    return [Candle(t=T0 + i * DAY + offset, o=100 + i, h=101 + i, l=99 + i, c=100 + i, v=1)
            for i in range(n)]


def fake(calls: list, broken: set[str] = frozenset()):
    def fetch(key: str, tf: str, n: int):
        calls.append(key)
        if key in broken:
            raise RuntimeError("red caída")
        return _bars(10, 5 * 3_600_000 if key in ("SP500", "NASDAQ") else 0), "prueba"
    return fetch


def test_sync_guarda_solo_velas_cerradas_y_lee_sin_mirar_el_futuro(tmp_path):
    now = T0 + 10 * DAY + 1               # la vela 9 (que abre en T0+9d) ya cerró
    out = im.sync_intermarket(tmp_path, now, fetcher=fake([]))
    assert out["BTCUSDT"] == 10 and set(out) == set(im.ASSETS)
    bars, src, cov = im.read_intermarket(tmp_path, T0 + 5 * DAY)
    assert [c.t for c in bars["BTCUSDT"]] == [T0 + i * DAY for i in range(5)]   # cerradas a asof
    assert len(bars["SP500"]) == 4        # la sesión del día 4 cierra a las 05 UTC del 5 + 5 h
    assert src["intermarket:SP500"].startswith("yahoo") and "intermarket:BTCUSDT" in cov


def test_ritmo_propio_y_un_activo_caido_no_frena_a_los_demas(tmp_path):
    calls: list[str] = []
    now = T0 + 20 * DAY
    out = im.sync_intermarket(tmp_path, now, fetcher=fake(calls, {"SP500"}))
    assert out["SP500"].startswith("error") and out["XAUUSDT"] == 10
    calls.clear()
    assert im.sync_intermarket(tmp_path, now + 60_000, fetcher=fake(calls)) == {}   # antes de 6 h
    out = im.sync_intermarket(tmp_path, now + im.RETRY_MS, fetcher=fake(calls))
    assert calls == ["SP500"] and out["SP500"] == 10    # el caído se reintenta a los 30 min
    calls.clear()
    out = im.sync_intermarket(tmp_path, now + im.INTERVAL_MS, fetcher=fake(calls))
    assert "SP500" not in calls and out["XAUUSDT"] == 0   # nada nuevo: no se duplica


def test_sin_carpeta_es_none_y_el_interruptor(tmp_path):
    assert im.read_intermarket(tmp_path, T0) is None
    assert im.enabled({}) and not im.enabled({"EIM_INTERMARKET": "0"})
