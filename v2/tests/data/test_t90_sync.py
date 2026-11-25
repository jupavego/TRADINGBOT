"""T90: sincronización incremental genérica (tasa, reintentos, reanudación, presupuesto y
calendario) con un proveedor de mentira. Sin red."""

from __future__ import annotations

from eim.data import Store
from eim.data.providers.meta import SourceMeta
from eim.data.series import InstrumentData
from eim.data.sync_generic import RateLimiter, SyncBudget, sync_instrument_candles
from eim.instruments import registry
from tests.data.t90_helpers import ACME, HOUR, load, ms, needs_xcals

META = SourceMeta(name="fixture-sync", coverage=1, license="sintética, solo pruebas",
                  rate_limit_per_min=1000)


class FakeProvider:
    """Sirve velas de una fixture; puede fallar las primeras `fail` peticiones."""

    name = "fixture-sync"
    meta = META

    def __init__(self, candles, step: int, now: int, fail: int = 0) -> None:
        self.candles, self.step, self.now, self.fail = candles, step, now, fail
        self.calls: list[tuple[int, int]] = []

    def klines(self, symbol, timeframe, start, end):
        self.calls.append((start, end))
        if self.fail:
            self.fail -= 1
            raise ConnectionError("red caída (simulada)")
        return [c for c in self.candles if start <= c.t < end and c.t + self.step <= self.now]


def _limiter() -> RateLimiter:
    return RateLimiter(10_000, clock=lambda: 0.0, sleep=lambda s: None)


def _run(store, prov, key, tf, start, end, **kw):
    kw.setdefault("budget", SyncBudget())
    return sync_instrument_candles(store, prov, key, tf, start, end, limiter=_limiter(),
                                   sleep=kw.pop("sleep", lambda s: None),
                                   now_ms=lambda: prov.now, **kw)


def test_cripto_sincroniza_reanuda_y_no_repide_lo_vacio(tmp_path):
    d = load("crypto_gap")
    t0, end = d["candles"][0].t, d["candles"][-1].t + HOUR
    store, prov = Store(tmp_path), FakeProvider(d["candles"], HOUR, now=end + 10 * HOUR)
    r = _run(store, prov, registry.BTCUSDT, "1h", t0, end)
    assert (r["fetched"], r["complete"], r["gaps"], r["source"]) == (195, True, 1, "fixture-sync")
    assert store.count("BTCUSDT", "1h") == 195
    assert InstrumentData(store).provenance("BTCUSDT", "candles", "1h") == META
    prov.calls.clear()
    r2 = _run(store, prov, registry.BTCUSDT, "1h", t0, end)   # vuelve a pedir el hueco: vacío
    assert r2["fetched"] == 0 and len(prov.calls) == 1
    prov.calls.clear()
    r3 = _run(store, prov, registry.BTCUSDT, "1h", t0, end)   # ya sabe que la fuente no lo tiene
    assert r3["requests"] == 0 and prov.calls == [] and r3["gaps"] == 1


def test_reintenta_y_si_se_agotan_lo_dice_sin_tumbar_a_nadie(tmp_path):
    d = load("crypto_gap")
    t0, end = d["candles"][0].t, d["candles"][-1].t + HOUR
    waits: list[float] = []
    prov = FakeProvider(d["candles"], HOUR, now=end, fail=2)
    r = _run(Store(tmp_path / "a"), prov, registry.BTCUSDT, "1h", t0, end, sleep=waits.append)
    assert r["complete"] and r["requests"] == 3 and waits == [1.0, 2.0] and r["error"] is None
    dead = FakeProvider(d["candles"], HOUR, now=end, fail=99)
    r = _run(Store(tmp_path / "b"), dead, registry.BTCUSDT, "1h", t0, end)
    assert not r["complete"] and r["fetched"] == 0 and "ConnectionError" in r["error"]


def test_el_presupuesto_corta_y_la_siguiente_pasada_sigue(tmp_path):
    d = load("crypto_gap")
    t0, end = d["candles"][0].t, d["candles"][-1].t + HOUR
    store, prov = Store(tmp_path), FakeProvider(d["candles"], HOUR, now=end)
    small = SyncBudget(chunk_bars=50, max_requests=2)
    r = _run(store, prov, registry.BTCUSDT, "1h", t0, end, budget=small)
    assert not r["complete"] and r["remaining"] > 0 and r["requests"] == 2
    for _ in range(5):
        if r["complete"]:
            break
        r = _run(store, prov, registry.BTCUSDT, "1h", t0, end, budget=small)
    assert r["complete"] and store.count("BTCUSDT", "1h") == 195


def test_limite_de_tasa_por_minuto():
    now = [0.0]
    slept: list[float] = []

    def sleep(s: float) -> None:
        slept.append(s)
        now[0] += s

    lim = RateLimiter(2, clock=lambda: now[0], sleep=sleep)
    assert [lim.wait(), lim.wait()] == [0.0, 0.0]
    assert lim.wait() == 60.0 and slept == [60.0]
    now[0] += 30.0                       # la primera ya salió de la ventana de 60 s
    assert lim.wait() == 0.0 and slept == [60.0]


@needs_xcals
def test_accion_solo_repide_los_huecos_con_mercado_abierto(tmp_path):
    d = load("equity_split_dividend")
    t0, end = d["candles"][0].t, ms("2026-03-07T15:00")
    store = Store(tmp_path)
    prov = FakeProvider(d["candles"], 86_400_000, now=end)
    r = _run(store, prov, ACME, "1d", t0, end, resolver=lambda k: ACME)
    assert r["fetched"] == len(d["candles"]) and r["gaps"] == 1 and r["calendar"]
    prov.calls.clear()
    r2 = _run(store, prov, ACME, "1d", t0, end, resolver=lambda k: ACME)
    # lo previo a la primera vela (se anota vacío), el miércoles que falta y la cola; ningún
    # fin de semana ni festivo, que con la regla 24/7 serían 9 peticiones más
    assert r2["requests"] == 3 and r2["closed_skipped"] == 9
    assert any(a <= d["missing_day"] < b for a, b in prov.calls)
    prov.calls.clear()
    r3 = _run(store, prov, ACME, "1d", t0, end, resolver=lambda k: ACME)
    assert r3["requests"] == 1 and prov.calls[0][0] > d["candles"][-1].t     # solo la cola
