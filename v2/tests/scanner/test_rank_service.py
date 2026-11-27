"""T95 — de punta a punta sobre DuckDB (sin red, agentes de prueba): tras la pasada de agentes,
ranking en la vista, intentos registrados (sin duplicar), maduración hacia adelante, familia
ampliada (841 + los del escáner), umbral del placebo y calibración que no adopta sin muestra."""

from __future__ import annotations

import pytest

pytest.importorskip("duckdb")

from eim.data import scanner_market as market  # noqa: E402
from eim.data.instruments_store import open_store  # noqa: E402
from eim.data.scanner_store import ScannerStore  # noqa: E402
from eim.data.scanner_view import read_view  # noqa: E402
from eim.data.store import Store  # noqa: E402
from eim.scanner import deep, multiplicity, rank  # noqa: E402
from eim.scanner import placebo_eval as pe  # noqa: E402
from eim.scanner.__main__ import main  # noqa: E402
from eim.scanner.deep_service import deep_pass  # noqa: E402
from eim.scanner.service import ScannerService  # noqa: E402
from tests.scanner._helpers import DAY, T0, candles, perp  # noqa: E402
from tests.scanner.test_deep import FakeAgent  # noqa: E402

ASOF1 = T0 + 101 * DAY + 3_600_000
ASOF2 = T0 + 130 * DAY + 3_600_000           # ≥ corte 1 + 25 velas: maduran las del corte 1
GOOD = ("AUSDT", "BUSDT", "CUSDT")
PER_INSTRUMENT = 3                            # ema, structure y la síntesis


@pytest.fixture
def world(tmp_path, monkeypatch):
    st = Store(market.universe_root(tmp_path))
    for k, s in enumerate(GOOD):
        st.upsert_candles(s, "1d", candles(200, seed=k, drift=0.002 * k, end_t=T0 + 140 * DAY),
                          "prueba")
    cat = open_store(tmp_path)
    cat.upsert([perp(s) for s in GOOD], t=T0)
    cat.close()
    fakes = [FakeAgent("ema", 0.6), FakeAgent("structure", 0.5),
             FakeAgent("microstructure", 1.0)]
    monkeypatch.setattr(deep, "_AGENTS", fakes)
    return tmp_path, fakes


def test_ranking_attempts_and_forward_maturation(world):
    path, _ = world
    svc = ScannerService(path, procs=1)
    svc.sweep(ASOF1)
    d = deep_pass(svc)
    r = d["ranking"]
    assert r["available"], r
    assert r["n_comparable"] == 3 and [x["position"] for x in r["rows"]] == [1, 2, 3]
    pr = [x["priority"] for x in r["rows"]]
    assert pr == sorted(pr, reverse=True)
    f = r["family"]
    n = len(GOOD) * PER_INSTRUMENT
    assert f["scanner"] == n and f["total"] == multiplicity.PRIOR_FAMILY + n
    assert f["new_observations"] == n and f["matured"] == 0
    for x in r["rows"]:
        m = x["multiplicity"]
        assert m["n_family"] == f["total"] and m["p_holm"] == 1.0
        assert m["validation"] == "no validada" and "sin resultados" in m["verdict"]
        assert x["above_threshold"] is False and x["cluster_id"]
    assert r["threshold"]["status"] == "sin_placebo" and r["n_above"] == 0
    assert d["detail_json"]["ranking"]["family_total"] == f["total"]
    v = read_view(path)
    assert v["ranking"]["available"] and v["version"] == "2"
    assert [o["opportunity_id"] for o in v["opportunities"]] == \
        [x["opportunity_id"] for x in r["rows"]]
    again = deep_pass(svc)                                    # misma vela: nada se duplica
    assert again["ranking"]["family"]["new_observations"] == 0
    assert again["ranking"]["family"]["scanner"] == n
    svc.sweep(ASOF2)
    d2 = deep_pass(svc)
    f2 = d2["ranking"]["family"]
    assert f2["matured_now"] == n and f2["matured"] == n          # el horizonte del corte 1
    assert f2["new_observations"] == n and f2["scanner"] == n      # mismas hipótesis, más datos
    rows = svc.store.synthesis_matured()
    assert len(rows) == len(GOOD) and set(rows[0]["scores"]) == set(rank.SCORE_KEYS)
    svc.close()


def test_placebo_threshold_marks_only_with_matching_versions(world):
    path, fakes = world
    svc = ScannerService(path, procs=1)
    svc.sweep(ASOF1)
    fp = pe.fingerprint(rank.load_weights(path), deep.agents_fingerprint(fakes), deep.versions())
    pe.write_threshold(path, {"threshold": 0.0, "replicas": 30, "alpha": 0.05}, fp,
                       {"kind": "permuted", "computed_at": 1})
    r = deep_pass(svc)["ranking"]
    assert r["threshold"]["status"] == "vigente" and r["n_above"] == 3
    pe.write_threshold(path, {"threshold": 0.0, "replicas": 30, "alpha": 0.05}, "otra",
                       {"kind": "permuted", "computed_at": 1})
    r = deep_pass(svc)["ranking"]
    assert r["threshold"]["status"] == "desactualizado" and r["n_above"] == 0
    svc.close()


def test_attempt_store_is_idempotent_and_keeps_the_family():
    st = ScannerStore(":memory:")
    a = multiplicity.Attempt("k1", "i", "AUSDT", "ema", "1", "1d", 2, 1, 100.0, 0.1, 0.002)
    b = multiplicity.Attempt("k2", "i", "AUSDT", "vwap", "1", "1d", 2, 0, 100.0, 0.1, 0.002)
    assert st.record_attempts("r1", 10 * DAY, DAY, [a, b]) == 2
    assert st.record_attempts("r1", 10 * DAY, DAY, [a, b]) == 0
    assert st.pending_obs(11 * DAY) == []                       # aún no cierra el horizonte
    pend = st.pending_obs(12 * DAY)
    assert [p["attempt_key"] for p in pend] == ["k1"]           # sin lado: no madura
    st.mature_obs([("k1", 10 * DAY, 110.0, 0.5, -0.6)])
    assert st.stale_keys() == ["k1"]
    st.set_stats([("k1", None, 1, None)])
    assert st.stale_keys() == []
    assert st.family() == {"k1": None, "k2": None}
    assert st.attempt_stats(["k1"])["k1"] == {"p_raw": None, "dsr": None, "n_obs": 1,
                                              "n_matured": 1}
    assert st.attempt_counts() == {"attempts": 2, "observations": 2, "matured": 1}
    st.close()


def test_calibrate_cli_does_not_adopt_without_sample(world, capsys):
    path, _ = world
    assert main(["--data-dir", str(path), "--procs", "1", "calibrate"]) == 0
    assert "insuficiente" in capsys.readouterr().out
    assert rank.load_weights(path) == rank.DEFAULT_WEIGHTS
