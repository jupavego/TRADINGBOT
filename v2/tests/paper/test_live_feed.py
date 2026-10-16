"""Señales en vivo (T48c): solo decisiones en vivo, estado sombra y acción de cada perfil."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from eim.paper.engine import Outcome
from eim.paper.live_feed import live_feed
from tests.paper.helpers import H1, T0, idea


def _live(t: int, strategy: str, **kw) -> Outcome:
    i = replace(idea(t=t, strategy=strategy), origin="vivo", timeframe="1h")
    return Outcome(idea=i, **kw)


def _ev(o: Outcome, cat: str, text: str, dt: int = 0, **kw) -> dict:
    return {"t": o.idea.t + dt, "cat": cat, "idea": o.idea.id, "origin": o.idea.origin,
            "text": text, **kw}


def test_only_live_most_recent_first_with_profile_actions():
    old = Outcome(idea=idea(t=T0, strategy="bt"), status="CERRADA", reason="TP", r=2.0)
    a = _live(T0 + H1, "a", status="CERRADA", reason="TP", r=1.8, fill=100.0, fill_t=T0 + H1)
    b = _live(T0 + 2 * H1, "b", status="ABIERTA", r=0.4, mark=101.0, fill=100.0)
    c = _live(T0 + 3 * H1, "c", status="PENDIENTE")
    books = {
        "conservador": SimpleNamespace(events=[
            _ev(a, "rechazada", "estrategia en pausa (n=12)"),
            _ev(b, "rechazada", "estrategia en pausa (n=9)"),
            _ev(c, "rechazada", "costo alto: 0,4 R"),
            _ev(a, "aprendizaje", "pausa a@1h", dt=H1)]),
        "moderado": SimpleNamespace(events=[
            _ev(a, "orden", "mercado 100", leverage=5, risk_usd=50.0),
            _ev(a, "llenada", "llenada", price=100.0),
            _ev(a, "tp", "TP a 104", dt=H1, pnl=90.0, r=1.8),
            _ev(b, "orden", "mercado 100", leverage=5, risk_usd=50.0),
            _ev(b, "llenada", "llenada", price=100.0),
            _ev(c, "orden", "límite 99", leverage=4, risk_usd=40.0)]),
        "agresivo": SimpleNamespace(events=[]),
    }
    ctx = [("1h", T0 + k * H1) for k in range(4)] + [("15m", T0 + 3 * H1 + 900_000)]
    f = live_feed([old, a, b, c], books, ctx)
    assert f["mode"] == "SIMULADO" and f["total"] == 3 and f["candles_total"] == 5
    assert [d["strategy"] for d in f["decisions"]] == ["c", "b", "a"]
    assert f["status"] == {"PENDIENTE": 1, "ABIERTA": 1, "CERRADA": 1}
    d = {x["strategy"]: x["profiles"] for x in f["decisions"]}
    assert d["a"]["moderado"]["action"] == "tp" and d["a"]["moderado"]["pnl"] == 90.0
    assert d["b"]["moderado"]["action"] == "abierta"
    assert d["c"]["moderado"]["action"] == "orden" and "4x" in d["c"]["moderado"]["text"]
    assert d["a"]["conservador"]["action"] == "rechazada"       # el aprendizaje no cuenta
    assert d["a"]["agresivo"]["action"] == "fuera"
    p = f["profiles"]
    assert p["moderado"]["taken"] == 3 and p["conservador"]["taken"] == 0
    assert p["conservador"]["top_reasons"] == [("estrategia en pausa", 2), ("costo alto", 1)]
    cs = f["candles"]
    assert cs[0]["timeframe"] == "15m" and cs[0]["signals"] == 0
    assert {(x["t"], x["signals"]) for x in cs if x["timeframe"] == "1h"} == {
        (T0, 0), (T0 + H1, 1), (T0 + 2 * H1, 1), (T0 + 3 * H1, 1)}


def test_limit_and_empty():
    os_ = [_live(T0 + k * H1, f"s{k}", status="CANCELADA", reason="NO_LLENADA") for k in range(5)]
    f = live_feed(os_, {"moderado": SimpleNamespace(events=[])}, [], limit=2)
    assert f["total"] == 5 and len(f["decisions"]) == 2 and f["decisions"][0]["t"] == T0 + 4 * H1
    e = live_feed([], {}, [])
    assert e["total"] == 0 and e["decisions"] == [] and e["candles"] == []
