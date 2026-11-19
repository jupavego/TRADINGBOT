"""T195: el balance del panel muestra por defecto el universo oficial (T144); la vista va aparte.

Caso real (portátil, 2026-11-18): el panel decía «Todo 1 620» (1 500 reconstruidas y 120 vividas,
neto −9 890 USDT) mientras el universo oficial contaba 87. Esta prueba fija que la cifra por
defecto sale del libro bajo la regla única y que la vista declara su origen.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from eim.data.paper_store import PaperStore
from eim.paper import balance_lens, ledger
from tests.share.test_t196_ledger import T0, H, row

NOW = T0 + 3 * H


@dataclass
class Book:
    trades: list[dict] = field(default_factory=list)


def view_trade(i: int, origin: str, pnl: float) -> dict:
    return {"id": f"v{i}", "pnl": pnl, "r": pnl / 10, "reason": "SLD", "fees": 0.1, "slip": 0.1,
            "funding": 0.0, "side": 1, "strategy": "s", "sid": "s", "timeframe": "15m",
            "exit_t": T0 + H, "origin": origin}


def test_la_lente_oficial_manda_y_la_vista_declara_su_origen(tmp_path):
    ps = PaperStore(tmp_path / "paper.duckdb")
    try:
        ledger.ensure(ps)
        ledger.record(ps, [row("ok1"), row("ok2", r=-1.0, pnl=-50.0),
                           row("tarde", retro=True, recorded=T0 + 50 * H)])
        # la vista: 3 reconstruidas que pierden mucho y 2 vividas
        books = {"moderado": Book([view_trade(i, "backtest", -100.0) for i in range(3)]
                                  + [view_trade(9, "vivo", 5.0), view_trade(8, "vivo", 5.0)])}
        out = balance_lens.payload(ps, "BTCUSDT", books, {"s": "S"}, NOW, ("15m",))
    finally:
        ps.close()
    lens, off, calc = out["balance_lens"], out["balance"], out["balance_all"]
    assert lens["default"] == "oficial" and lens["error"] == ""
    assert set(lens["labels"]) == {"oficial", "todo"} and "No es cifra" in lens["labels"]["todo"]
    # oficial: solo las dos vividas a tiempo; la `retro` no suma
    a = off["todo"]["all"]
    assert a["n"] == 2 and a["wins"]["n"] == 1 and a["net"] == -45.0
    assert off["todo"]["profiles"]["moderado"]["n"] == 2
    assert off["todo"]["all"]["causes"] == {"direccion": 1}
    # todo lo calculado: las cinco, con su desglose por origen en cada ventana
    c = calc["todo"]
    assert c["all"]["n"] == 5 and c["by_origin"] == {"backtest": 3, "vivo": 2}
    assert calc["24h"]["by_origin"] == {"backtest": 3, "vivo": 2}


def test_un_libro_ilegible_no_tumba_el_panel():
    class Broken:
        def execute(self, *_a, **_k):
            raise RuntimeError("base cerrada")

    out = balance_lens.payload(Broken(), "BTCUSDT", {"moderado": Book()}, {}, NOW, ("15m",))
    assert out["balance"] is None and "base cerrada" in out["balance_lens"]["error"]
    assert out["balance_all"]["todo"]["all"]["n"] == 0
