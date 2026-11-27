"""T102 — de punta a punta sobre DuckDB (sin red, agentes de prueba): barrido → pasada de agentes
→ revisión de salud con cobertura por clase → recorrido de una candidata por la línea de órdenes
→ sus eventos en el observatorio con la misma traza."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("duckdb")

import eim.observability.emit as E  # noqa: E402
from eim.core import Mode  # noqa: E402
from eim.data import scanner_market as market  # noqa: E402
from eim.data.instruments_store import open_store  # noqa: E402
from eim.data.scanner_view import read_view  # noqa: E402
from eim.data.store import Store  # noqa: E402
from eim.scanner import deep, trace  # noqa: E402
from eim.scanner.__main__ import main  # noqa: E402
from eim.scanner.deep_service import deep_pass  # noqa: E402
from eim.scanner.health_service import read_health, read_rollout  # noqa: E402
from eim.scanner.service import ScannerService  # noqa: E402
from tests.scanner._helpers import DAY, T0, candles, perp  # noqa: E402
from tests.scanner.test_deep import FakeAgent  # noqa: E402

ASOF = T0 + 101 * DAY + 3_600_000
GOOD = ("AUSDT", "BUSDT", "CUSDT")


@pytest.fixture
def world(tmp_path, monkeypatch):
    st = Store(market.universe_root(tmp_path))
    for k, s in enumerate(GOOD):
        st.upsert_candles(s, "1d", candles(150, seed=k, drift=0.002 * k), "prueba")
    st.upsert_candles("DUSDT", "1d", candles(30, seed=9), "prueba")      # pocas velas: fuera
    cat = open_store(tmp_path)
    cat.upsert([perp(s) for s in (*GOOD, "DUSDT")], t=T0)
    cat.close()
    monkeypatch.setattr(deep, "_AGENTS", [FakeAgent("ema", 0.6), FakeAgent("structure", 0.5)])
    monkeypatch.setenv("EIM_OBS", "on")
    spool = tmp_path / "spool"
    E.configure(process="scanner", mode=Mode.ANALISIS, spool_dir=spool, enabled=True)
    yield tmp_path
    E.close()
    E.configure(process="eim", spool_dir=tmp_path / "unused", enabled=False)


def test_a_candidate_is_followed_from_its_data_to_its_decision(world, capsys):
    svc = ScannerService(world, procs=1)
    s = svc.sweep(ASOF)
    d = deep_pass(svc)
    excl = svc.store.exclusions_by_class(s["run_id"])
    svc.close()
    assert set(excl) == {"crypto"} and sum(excl["crypto"].values()) == 1    # DUSDT, fuera
    h = read_health(world)
    crypto = next(c for c in h["classes"] if c["asset_class"] == "crypto")
    assert crypto["n_scored"] == 3 and crypto["coverage"] == 0.75
    assert crypto["candidates"] == len(d["opportunities"]) == 3
    assert h["mode"] == "ANALISIS" and h["observability"]["within"] is True
    assert read_rollout(world)["units"]["class:crypto"]["level"] == "alerta"

    assert main(["--data-dir", str(world), "trace", "--first", "--json"]) == 0
    t = json.loads(capsys.readouterr().out)
    assert [x["key"] for x in t["steps"]][0] == "dato" and t["steps"][-1]["key"] == "decision"
    assert t["steps"][-1]["detail"]["validated"] is False
    view = read_view(world)
    assert t["trace_id"] == trace.trace_id_of(view, t["instrument_id"])

    assert E.flush(5.0)
    evs = [json.loads(x) for f in (world / "spool").glob("*.jsonl")
           for x in f.read_text(encoding="utf-8").splitlines()]
    mine = [e for e in evs if e.get("trace_id") == t["trace_id"]]
    assert {e["component_id"] for e in mine} == {"scanner.service", "scanner.deep",
                                                 "scanner.rank"}
    assert any(e["kind"] == "plan" and e["detail"]["validated"] is False for e in mine)
    assert any(e["component_id"] == "scanner.health" and e["kind"] == "heartbeat" for e in evs)


def test_the_health_command_reviews_without_sweeping(world, capsys):
    svc = ScannerService(world, procs=1)
    svc.sweep(ASOF)
    deep_pass(svc)
    svc.close()
    summary = world / "salud.txt"
    assert main(["--data-dir", str(world), "health", "--quiet", "--summary", str(summary)]) == 0
    line = summary.read_text(encoding="utf-8")
    assert line.startswith("salud T102: ") and "Cripto" in line and "cobertura 75%" in line
    assert main(["--data-dir", str(world), "trace", "crypto.binance.usdm.NOPEUSDT"]) == 5
