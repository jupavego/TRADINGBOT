"""Liquidaciones y titulares llegan al snapshot desde el almacén (sin red)."""

from eim.agents.context.params import ContextParams  # noqa: F401
from eim.core import NewsItem
from eim.data.extras import read_headlines, read_liquidations, sync_headlines

DAY = 86_400_000
T0 = 1_700_000_000_000


def _csv(root, day, symbol="ETHUSD_PERP"):
    d = root / "liquidations" / symbol
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{symbol}-liquidationSnapshot-{day}.csv").write_text(
        "time,side,original_quantity,average_price\n"
        f"{T0},SELL,10,2000\n{T0},BUY,5,2100\n", encoding="utf-8")


def test_liquidaciones_leen_cache_y_marcan_obsoleto(tmp_path):
    _csv(tmp_path, "2023-11-14")
    assert read_liquidations(tmp_path, "ETHUSDT", T0 - 10 * DAY) is None  # point-in-time
    liq = read_liquidations(tmp_path, "ETHUSDT", T0 + 100 * DAY)
    assert liq is not None and liq.stale and liq.liquidation_symbol == "ETHUSD_PERP"
    assert read_liquidations(tmp_path, "SOLUSDT", T0) is None
    assert read_liquidations(tmp_path / "vacio", "ETHUSDT", T0) is None


def test_titulares_solo_los_vistos_a_asof(tmp_path):
    n = NewsItem(id="a", t=T0, title="x", source="S", url="u")
    assert sync_headlines(tmp_path, T0 + 1000, fetcher=lambda: [n]) == 1
    assert sync_headlines(tmp_path, T0 + 2000, fetcher=lambda: [n]) == 0  # sin duplicar
    assert read_headlines(tmp_path, T0 + 500) is None
    assert [h.id for h in read_headlines(tmp_path, T0 + 5000)] == ["a"]
