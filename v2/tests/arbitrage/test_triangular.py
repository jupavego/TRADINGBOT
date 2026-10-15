"""Triangular spot: con comisiones realistas el ciclo simple suele dar neto ≤ 0 (se informa)."""

from __future__ import annotations

import random

import pytest

from eim.arbitrage import ArbParams, scan_triangular, select
from eim.core import CostModel, SpotPair
from tests.arbitrage.helpers import book, market

P = ArbParams()
PAIRS = [SpotPair(symbol="BTCUSDT", base="BTC", quote="USDT"),
         SpotPair(symbol="ETHUSDT", base="ETH", quote="USDT"),
         SpotPair(symbol="ETHBTC", base="ETH", quote="BTC")]


def tri(eps_bps: float, *, qty: float = 50.0, eth_btc_qty: float | None = None,
        drop: str | None = None):
    """Triángulo coherente (ETHBTC = ETH/BTC) con `eps_bps` de desajuste en ETHBTC."""
    books = {"BTCUSDT": book(60_000, qty=qty), "ETHUSDT": book(3_000, qty=qty * 20),
             "ETHBTC": book(0.05 * (1 + eps_bps / 1e4), qty=eth_btc_qty or qty * 20,
                            step_bps=0.5)}
    if drop:
        books.pop(drop)
    return market(spot=books, pairs=PAIRS, errors={f"book:spot:{drop}": "HTTP 400"}
                  if drop else None)


def test_both_directions_reported_with_breakdown():
    scan = scan_triangular(tri(0.0), CostModel(), P)
    assert scan.status == "ok" and len(scan.opportunities) == 2
    routes = {o.asset for o in scan.opportunities}
    assert routes == {"USDT→BTC→ETH→USDT", "USDT→ETH→BTC→USDT"}
    for o in scan.opportunities:
        assert len(o.legs) == 3 and o.costs.fees == pytest.approx(30.0, rel=0.01)
        assert o.costs.slippage > 0 and o.annualized is None and o.horizon_h == 0
        assert o.risk.legging >= 0.5 and o.risk.liquidation == 0


def test_realistic_fees_usually_net_nonpositive():
    rng = random.Random(7)
    nets, gross_pos = [], 0
    for _ in range(150):
        scan = scan_triangular(tri(rng.uniform(-15, 15)), CostModel(bnb_discount=True), P)
        assert len(scan.opportunities) == 2  # se informa, no se esconde
        for o in scan.opportunities:
            nets.append(o.net_edge)
            gross_pos += o.gross_edge > 0
    assert gross_pos > 100  # hay bruto positivo en uno de los sentidos…
    assert sum(n <= 0 for n in nets) / len(nets) >= 0.95  # …pero el neto no sobrevive


def test_gross_positive_net_negative():
    best = max(scan_triangular(tri(10.0), CostModel(), P).opportunities,
               key=lambda o: o.gross_edge)
    assert best.details["gross_bps"] == pytest.approx(10.0, rel=0.02)
    assert best.gross_edge > 0 > best.net_edge


def test_big_mispricing_positive_but_informative_only():
    scan = scan_triangular(tri(100.0), CostModel(), P)
    best = max(scan.opportunities, key=lambda o: o.net_edge)
    assert best.net_edge > 0
    sel = select(scan.opportunities, P)
    assert not sel.selected
    assert all(r.reason.startswith("informativa") for r in sel.rejected)


def test_zero_fees_net_is_gross_minus_slippage():
    free = CostModel(spot_fees={0: (0.0, 0.0)})
    for o in scan_triangular(tri(3.0), free, P).opportunities:
        assert o.costs.fees == 0
        assert o.net_edge == pytest.approx(o.gross_edge - o.costs.slippage)
        assert o.costs.slippage >= 0


def test_thin_book_marks_incomplete_leg():
    scan = scan_triangular(tri(0.0, eth_btc_qty=0.01), CostModel(), P)
    assert all(not o.executable for o in scan.opportunities)
    assert all(o.risk.legging == 1.0 for o in scan.opportunities)


def test_missing_book_no_data():
    scan = scan_triangular(tri(0.0, drop="ETHBTC"), CostModel(), P)
    assert scan.status == "no_data" and not scan.opportunities
    assert scan.missing == ["libro spot ETHBTC (HTTP 400)"]
