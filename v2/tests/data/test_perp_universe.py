"""T181: historia del universo de perpetuos USDT, despacio, reanudable y sin red en las pruebas."""

from __future__ import annotations

import json

from eim.core import Candle
from eim.data import perp_universe as pu
from eim.data.store import Store

DAY = pu.DAY_MS
T0 = pu.START_MS + 400 * DAY


class FakeFutures:
    """Un `BinanceFutures` de mentira: tres perpetuos USDT, uno cerrado, y un trimestral."""

    def __init__(self, now: int, fail: str | None = None) -> None:
        self.now, self.fail, self.calls = now, fail, []

    def request(self, path, params=None):
        assert path == "/fapi/v1/exchangeInfo"
        mk = lambda s, st, ctype="PERPETUAL", q="USDT": {  # noqa: E731
            "symbol": s, "baseAsset": s[:-4], "quoteAsset": q, "marginAsset": q, "status": st,
            "contractType": ctype, "onboardDate": T0}
        return {"symbols": [mk("AAAUSDT", "TRADING"), mk("BBBUSDT", "TRADING"),
                            mk("OLDUSDT", "SETTLING"),
                            mk("AAAUSDT_270326", "TRADING", "CURRENT_QUARTER"),
                            mk("AAAUSDC", "TRADING", q="USDC")]}

    def funding_rates(self, sym, start, end):
        self.calls.append(("funding", sym, start))
        if sym == self.fail:
            raise RuntimeError("418 baneado")
        return [(t, 0.0001) for t in range(start - start % (8 * 3_600_000), end, 8 * 3_600_000)
                if t >= start]

    def klines(self, sym, tf, start, end):
        self.calls.append(("klines", sym, start))
        return [Candle(t=t, o=1, h=1, l=1, c=1, v=1) for t in range(start, end - DAY, DAY)]


def test_el_universo_son_los_perpetuos_usdt_en_cualquier_estado():
    syms = [u["symbol"] for u in pu.universe(FakeFutures(T0))]
    assert syms == ["AAAUSDT", "BBBUSDT", "OLDUSDT"]          # ni trimestrales ni USDC


def test_sincroniza_y_al_repetir_solo_pide_lo_nuevo(tmp_path):
    f = FakeFutures(T0 + 10 * DAY)
    out = pu.sync(tmp_path, f, now=T0 + 10 * DAY, say=lambda s: None)
    assert out["errors"] == {} and out["symbols"] == 3 and out["candle_rows"] == 3 * 9
    st = Store(tmp_path)
    assert len(st.read_candles("AAAUSDT", "1d")) == 9
    assert st.read_series("funding", "AAAUSDT")[0][0] >= T0
    uni = json.loads((tmp_path / "universe.json").read_text(encoding="utf-8"))
    assert uni["by_status"] == {"TRADING": 2, "SETTLING": 1} and "supervivencia" in uni["note"]
    f2 = FakeFutures(T0 + 12 * DAY)
    out2 = pu.sync(tmp_path, f2, now=T0 + 12 * DAY, say=lambda s: None)
    starts = {(k, s): a for k, s, a in f2.calls}
    assert starts[("klines", "AAAUSDT")] == T0 + 9 * DAY                # sigue donde se quedó
    assert starts[("funding", "AAAUSDT")] > T0 + 9 * DAY
    assert out2["candle_rows"] == 3 * 2


def test_un_simbolo_que_falla_no_detiene_a_los_demas(tmp_path):
    out = pu.sync(tmp_path, FakeFutures(T0 + 5 * DAY, fail="BBBUSDT"), now=T0 + 5 * DAY,
                  say=lambda s: None)
    assert list(out["errors"]) == ["BBBUSDT"] and "418" in out["errors"]["BBBUSDT"]
    assert len(Store(tmp_path).read_candles("OLDUSDT", "1d")) == 4


def test_no_deja_bajar_el_intervalo_del_limite_compartido(tmp_path, capsys):
    assert pu.main(["sync", "--root", str(tmp_path), "--min-interval", "0.5"]) == 2
    assert "límite" in capsys.readouterr().err
