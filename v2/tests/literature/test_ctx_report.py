"""Contexto con `lit`, relleno de contextos viejos, informe por ficha y `/v2/setups` (T54)."""

from __future__ import annotations

import json
from dataclasses import replace

import numpy as np
import pytest

from eim.agents.literature import LiteratureAgent
from eim.core import Candle, MarketSnapshot
from eim.data.paper_store import PaperStore
from eim.data.store import Store
from eim.literature import report
from eim.literature.ctx import complete, lit_for
from eim.paper.context import CTX_VERSION, lit_summary, make_ctx
from eim.paper.engine import Path, simulate
from eim.paper.params import ExecParams
from eim.validation.lineage import Version, Window
from tests.literature.test_tilt import with_hammer
from tests.paper.helpers import H1, M15, T0, idea
from tests.paper.test_strategies import walk


def snap_of(cs: list[Candle]) -> MarketSnapshot:
    return MarketSnapshot(symbol="X", timeframe="1h", candles=cs, asof=cs[-1].t + H1,
                          sources={}, coverage={})


def test_lit_summary_is_compact_json_and_none_without_data():
    rep = LiteratureAgent().run(snap_of(with_hammer()))
    lit = lit_summary(rep)
    assert lit["v"] == rep.version and lit["n"] == rep.metrics["rules_evaluated"]
    assert any(h[0] == "nison_hammer" and h[1] == 1 and 0 < h[2] <= 1 for h in lit["hits"])
    assert set(lit["net"]) == {"bull", "neutral", "bear"} and lit["net"]["bull"] > 0
    assert json.loads(json.dumps(lit)) == lit
    short = LiteratureAgent().run(snap_of(with_hammer()[:20]))
    assert short.status == "no_data" and lit_summary(short) is None and lit_summary(None) is None


def test_make_ctx_carries_lit_and_version_is_declared():
    cs = with_hammer()
    rep = LiteratureAgent().run(snap_of(cs))
    ctx = make_ctx(snap_of(cs), [rep], ["literature"], None, H1)
    assert CTX_VERSION == 2 and ctx["v"] == 2
    assert ctx["lit"]["hits"] and ctx["lit"] == lit_summary(rep)
    assert json.loads(json.dumps(ctx))["lit"] == ctx["lit"]
    assert make_ctx(snap_of(cs), [], [], None, H1)["lit"] is None


@pytest.fixture
def store(tmp_path):
    st = Store(tmp_path)
    st.upsert_candles("BTCUSDT", "1h", walk(420, seed=3), "test")
    return st


def test_complete_fills_old_contexts_without_touching_the_rest(store):
    cs = store.read_candles("BTCUSDT", "1h")
    ps = PaperStore(":memory:")
    asofs = [cs[i].t + H1 for i in range(300, 340)]
    for a in asofs:
        ps.save("BTCUSDT", "1h", {"v": 1, "t": a, "close": 1.0, "atr": 0.1, "agents": {}},
                "vivo" if a == asofs[-1] else "backtest", 0)
    r = complete(store, ps, "BTCUSDT", "1h")
    assert r == {"symbol": "BTCUSDT", "timeframe": "1h", "completed": 40, "skipped": 0}
    got = ps.load("BTCUSDT", "1h")
    assert [c["origin"] for c in got][-1] == "vivo" and got[0]["origin"] == "backtest"
    agent, at = LiteratureAgent(), {c.t: k for k, c in enumerate(cs)}
    for c in got:
        assert c["v"] == CTX_VERSION and "lit" in c and c["close"] == 1.0   # el resto, intacto
        i = at[c["t"] - H1]
        assert c["lit"] == lit_for(cs, i, "BTCUSDT", "1h", c["t"], agent)
    assert complete(store, ps, "BTCUSDT", "1h")["completed"] == 0           # idempotente
    ps.save("BTCUSDT", "1h", {"v": 1, "t": T0 - 99 * H1, "close": 1.0}, "backtest", 0)
    assert complete(store, ps, "BTCUSDT", "1h")["skipped"] == 1             # sin vela en el almacén
    ps.close()


def test_lit_for_does_not_use_later_candles(store):
    cs = store.read_candles("BTCUSDT", "1h")
    agent = LiteratureAgent()
    i = 350
    a = lit_for(cs, i, "BTCUSDT", "1h", cs[i].t + H1, agent)
    twisted = cs[:i + 1] + [Candle(t=c.t, o=1, h=9e3, l=0.5, c=5e3, v=1) for c in cs[i + 1:]]
    assert lit_for(twisted, i, "BTCUSDT", "1h", cs[i].t + H1, agent) == a
    assert lit_for(cs, 10, "BTCUSDT", "1h", cs[10].t + H1, agent) is None   # pocas velas


# --- informe -------------------------------------------------------------------------------
def flat_path(n: int = 3000) -> Path:
    rng = np.random.default_rng(2)
    p, cs = 100.0, []
    for i in range(n):
        o, p = p, p * float(np.exp(rng.normal(0, 0.003)))
        cs.append(Candle(t=T0 + i * M15, o=o, h=max(o, p) * 1.001, l=min(o, p) * 0.999, c=p, v=1))
    return Path(cs)


def lit_outcomes(path: Path, version: str, cards=("nison_hammer", "nison_shooting_star"),
                 n: int = 60) -> list:
    out = []
    for k in range(n):
        t = T0 + k * 8 * H1
        px = float(path.o[int(np.searchsorted(path.t, t))])
        side = 1 if k % 2 else -1
        base = idea(side=side, entry=px, sl=px * (1 - 0.01 * side), tp=px * (1 + 0.02 * side),
                    t=t, strategy="lit_vela_cola", family="literatura",
                    key=f"{cards[k % 2]}:{t}", iid=f"X:1h:{t}")
        out.append(simulate(replace(base, timeframe="1h", version=version, regime="range"),
                            path, ExecParams()))
    return out


def test_trades_by_card_counts_only_closed_current_out_of_sample_and_splits_cards():
    path = flat_path()
    outs = lit_outcomes(path, "fp1") + lit_outcomes(path, "vieja")[:10]
    cur = Version("lit_vela_cola@1h", 1, "fp1", "lit_vela_cola", "1h", T0, None, "test",
                  windows=(Window(T0, T0 + 20 * H1, None, "ajuste"),))
    asof = path.end
    got = report.trades_by_card(outs, {cur.sid: cur}, [cur], "X", asof)
    closed = [o for o in outs if o.idea.version == "fp1" and o.status == "CERRADA"
              and o.idea.t >= T0 + 20 * H1]
    assert sum(len(v) for v in got.values()) == len(closed) > 0
    assert set(got) == {"nison_hammer", "nison_shooting_star"}
    assert all(t >= T0 + 20 * H1 for v in got.values() for t, _, _ in v)       # la ventana, fuera
    other = replace(outs[0].idea, family="consenso")
    assert report.trades_by_card([replace(outs[0], idea=other)], {cur.sid: cur}, [cur],
                                 "X", asof) == {}
    assert report.trades_by_card(outs, {cur.sid: cur}, [cur], "X", T0) == {}   # sin anticipación


def card_checks(ok2: bool = False) -> list[dict]:
    chk = [{"id": f"V{i}", "name": "x", "value": {}, "threshold": "", "ok": None,
            "reason": ""} for i in range(1, 7)]
    chk[1] = {**chk[1], "value": {"mean_r": -0.1, "ci": [-0.2, 0.0]}, "ok": ok2}
    chk[2] = {**chk[2], "value": {"p": 0.4, "p_holm": 1.0, "reps": 500}, "ok": False}
    return chk


def payload(verdict: str = "RECHAZADA") -> dict:
    v = {"id": "lit_vela_cola@1h@v1", "sid": "lit_vela_cola@1h", "strategy": "lit_vela_cola",
         "verdict": verdict, "n_oos": 120, "mean_r": -0.1, "checks": card_checks()}
    other = {**v, "id": "consenso_sintesis@1h@v1", "strategy": "consenso_sintesis"}
    return {"verdicts": [v, other],
            "criteria": {"version": "validation_v1"}, "attempts": 96}


def test_report_says_plainly_when_nothing_passes_and_lists_failures(tmp_path):
    claims = {"nison_hammer": {"cite": "Nison (2001), cap. 4, pp. 45–46", "claim": "(alcista) x",
                               "evidence": "anecdótica"}}
    by = {"nison_hammer": [(T0 + k * H1, float(r), "1h")
                           for k, r in enumerate(np.random.default_rng(0).normal(-0.1, 1, 80))]}
    tilt = {"version": "lit_tilt_v1", "k": 0.5, "n": 10, "n_active": 2,
            "verdict": "SIN EVIDENCIA", "reason": "muestra insuficiente (T1): sigue apagado",
            "checks": []}
    res = report.build(payload(), by, claims, tilt,
                       {"date": "2026-10-19", "symbol": "BTCUSDT", "asof": T0, "notes": ["n1"]})
    assert [v["strategy"] for v in res["versions"]] == ["lit_vela_cola"]      # solo la familia
    text = report.render(res)
    assert "**0 de 1**" in text and "ninguna regla de libro" in text
    assert "V3" in text and "**SIN EVIDENCIA**" in text and "APAGADO" in text
    assert "`nison_hammer`" in text and "Nison (2001)" in text and "SIMULADO" in text
    md, js = report.write(res, tmp_path)
    assert md.name == "lit_v1_2026-10-19.md" and json.loads(js.read_text())["tilt"]["k"] == 0.5
    assert res["by_card"]["nison_hammer"]["n"] == 80


def test_card_stats_reading_is_honest_with_small_samples():
    assert report.card_stats([], "x")["verdict"] == "sin operaciones"
    s = report.card_stats([(T0 + k * H1, 1.0, "1h") for k in range(10)], "x")
    assert s["verdict"] == "no hay muestra para juzgar" and s["mean_r"] == 1.0


# --- publicación (T50) --------------------------------------------------------------------
def test_literature_ideas_reach_the_panel_only_when_validated():
    """Sin atajos: una idea de la familia solo se publica con veredicto VALIDADA de su versión."""
    from dataclasses import replace as rep

    from eim.suggestions.publisher import OK, SIN_VALIDADAS
    from tests.suggestions.helpers import idea as sidea
    from tests.suggestions.helpers import run, verdict

    lit = rep(sidea("lit_vela_cola"), family="literatura", key="nison_hammer:1")
    for v in ("EN OBSERVACIÓN", "RECHAZADA"):
        pub = run([lit], [verdict("lit_vela_cola", verdict=v)])
        assert pub.setups == [] and pub.status == SIN_VALIDADAS
    other = run([lit], [verdict("consenso_sintesis")])                  # otra estrategia validada
    assert other.setups == []
    stale_version = run([lit], [verdict("lit_vela_cola", fp="otra")])   # otra versión no hereda
    assert stale_version.setups == []
    ok = run([lit], [verdict("lit_vela_cola")])
    assert ok.status == OK and [s["strategy"] for s in ok.setups] == ["lit_vela_cola"]
    assert ok.setups[0]["evidence"]["n_oos"] == 240            # con su evidencia fuera de muestra


def test_family_verdict_is_never_validated_without_evidence(tmp_path):
    """Con operaciones sin ventaja o muestra corta, la puerta no la valida: no hay publicación."""
    from eim.data.validation_store import ValidationStore
    from eim.paper.catalog import CATALOG
    from eim.validation.gate import OBSERVACION, RECHAZADA
    from eim.validation.service import Validator
    from tests.validation.test_service import FakeDesk, FakeView

    path, ep = flat_path(), ExecParams()
    fp = CATALOG["lit_vela_cola"].version("1h", ep)
    ps = PaperStore(":memory:")
    try:
        for n in (12, 60):
            val = Validator(FakeDesk(ep, FakeView(lit_outcomes(path, fp, n=n), path)),
                            ValidationStore(ps), lineage=tmp_path / f"l{n}.json")
            p = val.compute("X", T0 - H1)
            v = next(x for x in p["verdicts"] if x["strategy"] == "lit_vela_cola")
            assert v["verdict"] in (OBSERVACION, RECHAZADA) and v["id"].endswith("@v1")
            assert all(x["verdict"] != "VALIDADA" for x in p["verdicts"]
                       if x["strategy"].startswith("lit_"))
    finally:
        ps.close()
