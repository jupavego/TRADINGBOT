"""Seguimiento de lo publicado (T51): registro inmutable, resolución sin anticipación,
degradación que excluye del publicador, intervalos sin sugerencia y nada «ejecutado»."""

from __future__ import annotations

from eim.core import Candle
from eim.data.paper_store import PaperStore
from eim.data.suggestion_store import SuggestionStore
from eim.paper.engine import Path
from eim.paper.params import ExecParams
from eim.suggestions.publisher import STATE, Publication
from eim.suggestions.tracker import GAP_JOIN_MS, Tracker
from eim.suggestions.tracking import LAST_N, resolve
from tests.suggestions.helpers import NOW, H, idea, run, verdict

M15 = 900_000
T0 = NOW - 100 * H


def candles(t0: int, n: int, lo: float = 99.0, hi: float = 100.5, step: int = M15):
    return [Candle(t=t0 + k * step, o=100.0, h=hi, l=lo, c=100.0, v=1.0) for k in range(n)]


def row(i: int = 0, t: int = T0, pub: int | None = None, **kw) -> dict:
    base = {"id": f"BTCUSDT:1h:{t}:ema", "symbol": "BTCUSDT", "published_ms": pub or t,
            "criteria": "validation_v1", "verdicts_asof": t - H, "vid": "ema@1h@v1",
            "sid": "ema@1h", "strategy": "ema", "timeframe": "1h", "n": 1,
            "fingerprint": "fpA", "side": 1, "kind": "market", "entry": 100.0, "sl": 98.0,
            "tp": 104.0, "fill_ms": 0, "hold_ms": 24 * H, "idea_t": t, "price": 100.0,
            "reason": "regla", "evidence": {"mean_r": 0.15, "ci95": [0.05, 0.25], "n_oos": 240}}
    return {**base, **kw}


def store() -> SuggestionStore:
    return SuggestionStore(PaperStore(":memory:"))


def test_publish_is_idempotent_and_immutable():
    s = store()
    assert s.publish(row()) is True
    assert s.publish(row(entry=101.0, pub=T0 + H)) is False        # misma idea: no se reescribe
    (r,) = s.published("BTCUSDT")
    assert r["entry"] == 100.0 and r["published_ms"] == T0 and r["evidence"]["ci95"] == [0.05, 0.25]


def test_resolution_ignores_candles_before_publication():
    # antes de publicar (T0..T0+1h) el precio habría tocado el SL; después sube hasta el TP
    cs = candles(T0, 4, lo=97.0) + candles(T0 + H, 8, lo=99.5, hi=104.5)
    path = Path(cs)
    (r,) = resolve([row(pub=T0 + H)], path, ExecParams())
    res = r["resolution"]
    assert res["state"] == "cerrada" and res["reason"] == "TP" and res["r"] > 0
    assert res["fill_t"] >= T0 + H                      # sin anticipación
    (early,) = resolve([row()], path, ExecParams())     # publicada antes: sí toca el SL
    assert early["resolution"]["reason"] == "SL"


def test_publication_mid_candle_waits_for_next_open():
    path = Path(candles(T0, 12, lo=97.0))
    (r,) = resolve([row(pub=T0 + 100)], path, ExecParams())
    assert r["resolution"]["fill_t"] == T0 + M15


def test_nothing_is_ever_executed():
    path = Path(candles(T0, 12, lo=97.0))
    (r,) = resolve([row()], path, ExecParams())
    assert r["state"] == STATE and r["executed"] is False
    (n,) = resolve([row()], None, ExecParams())
    assert n["resolution"]["state"] == "sin_datos" and n["state"] == STATE


def test_limit_not_filled_keeps_original_window():
    r = row(kind="limit", entry=95.0, sl=93.0, tp=99.0, fill_ms=2 * H, pub=T0 + H)
    (out,) = resolve([r], Path(candles(T0, 40)), ExecParams())
    assert out["resolution"]["state"] == "no_llenada"   # la ventana vence en T0+2h, ya sin llenar


def _tracker() -> tuple[Tracker, SuggestionStore]:
    s = store()
    return Tracker(s, ExecParams()), s


def _fill(s: SuggestionStore, n: int) -> Path:
    for k in range(n):
        s.publish(row(t=T0 + k * H))
    return Path(candles(T0, 4 * n + 4, lo=97.0))


def test_degradation_puts_version_in_review_and_publisher_excludes_it():
    tr, s = _tracker()
    path = _fill(s, LAST_N)
    v = verdict()
    tr.refresh("BTCUSDT", path, [v], NOW, NOW)
    assert tr.in_review("BTCUSDT") == {"ema@1h@v1"}
    ideas = [idea()]
    assert run(ideas, [v]).status == "ok"
    pub = run(ideas, [v], review=tr.in_review("BTCUSDT"))
    assert pub.setups == [] and pub.status == "sin_validadas"
    assert pub.validation["in_review"] == ["ema@1h@v1"]
    # mismo veredicto (sin veredicto nuevo): sigue en revisión
    tr.refresh("BTCUSDT", path, [v], NOW + H, NOW)
    assert tr.in_review("BTCUSDT") == {"ema@1h@v1"}


def test_no_degradation_with_fewer_than_last_n_or_good_results():
    tr, s = _tracker()
    path = _fill(s, LAST_N - 1)
    tr.refresh("BTCUSDT", path, [verdict()], NOW, NOW)
    assert tr.in_review("BTCUSDT") == set()
    tr2, s2 = _tracker()
    for k in range(LAST_N):
        s2.publish(row(t=T0 + k * H))
    good = Path(candles(T0, 4 * LAST_N + 4, lo=99.5, hi=104.5))
    tr2.refresh("BTCUSDT", good, [verdict()], NOW, NOW)
    assert tr2.in_review("BTCUSDT") == set()


def test_review_released_by_a_newer_verdict_that_absorbs_it():
    tr, s = _tracker()
    path = _fill(s, LAST_N)
    tr.refresh("BTCUSDT", path, [verdict()], NOW, NOW)
    assert tr.in_review("BTCUSDT")
    # veredicto nuevo cuya evidencia ya recoge la caída (IC95 % muy por debajo de lo realizado)
    v2 = verdict(ci_lo=-3.0)
    tr.refresh("BTCUSDT", path, [v2], NOW + 5 * H, NOW + 4 * H)
    assert tr.in_review("BTCUSDT") == set()


def test_record_stores_publication_once_and_gaps():
    tr, s = _tracker()
    v = verdict()
    pub = run([idea()], [v])
    assert pub.status == "ok"
    assert tr.record("BTCUSDT", pub, NOW, [v], NOW - H, "validation_v1") == 1
    assert tr.record("BTCUSDT", pub, NOW + 60_000, [v], NOW - H, "validation_v1") == 0
    (p,) = s.published("BTCUSDT")
    assert p["vid"] == "ema@1h@v1" and p["fingerprint"] == "fpA" and p["published_ms"] == NOW
    assert s.gaps("BTCUSDT") == []                     # con sugerencia no hay intervalo vacío
    empty = Publication("sin_validadas", "Ninguna estrategia pasa todavía la puerta.")
    for k in range(3):
        tr.record("BTCUSDT", empty, NOW + k * 60_000, [], None, "validation_v1")
    tr.record("BTCUSDT", empty, NOW + 3 * 60_000 + GAP_JOIN_MS + 1, [], None, "validation_v1")
    tr.record("BTCUSDT", Publication("sin_senal", "x"), NOW + 99 * 60_000, [], None, "v")
    g = s.gaps("BTCUSDT")
    assert [x["status"] for x in g] == ["sin_validadas", "sin_validadas", "sin_senal"]
    assert g[0]["to"] - g[0]["from"] == 2 * 60_000


def test_history_scorecard_signal_vs_result():
    tr, s = _tracker()
    path = _fill(s, 6)
    v = verdict()
    resolved = tr.refresh("BTCUSDT", path, [v], NOW, NOW)
    h = tr.history("BTCUSDT", resolved, [v], [], NOW)
    (c,) = h["scorecard"]
    assert c["vid"] == "ema@1h@v1" and c["closed"] == 6 and c["realized_mean_r"] < 0
    assert c["against"] == "debajo" and c["expected"]["ci95"] == [0.05, 0.25]
    assert h["totals"]["cum_r"] < 0 and h["totals"]["hit_rate"] == 0
    assert all(p["executed"] is False and p["state"] == STATE for p in h["published"])


def test_watch_ideas_are_recorded_apart_and_resolved_without_touching_validated():
    tr = Tracker(store())
    ideas = [idea("ema", t=NOW - H)]
    pub = run(ideas, [verdict("ema", verdict="EN OBSERVACIÓN")])
    assert pub.setups == [] and len(pub.watch) == 1
    tr.record("BTCUSDT", pub, NOW, [verdict("ema", verdict="EN OBSERVACIÓN")], NOW - H, "v1")
    tr.record("BTCUSDT", pub, NOW + 60_000, [verdict("ema", verdict="EN OBSERVACIÓN")], NOW - H,
              "v1")                                                  # idempotente
    assert tr.store.published("BTCUSDT") == []
    assert len(tr.store.published("BTCUSDT", "sug_watch")) == 1
    path = Path(candles(NOW, 8, lo=99.5, hi=105.0))
    (r,) = tr.resolve_watch("BTCUSDT", path)
    assert r["state"] == "observacion_no_validada" and r["resolution"]["state"] == "cerrada"
    h = tr.history("BTCUSDT", [], [], [], NOW + H, watch_resolved=[r])
    assert h["totals"]["published"] == 0 and h["watch"]["totals"]["published"] == 1
