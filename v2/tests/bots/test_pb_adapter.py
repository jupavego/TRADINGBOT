"""Carril de simulación de Passivbot (T58): contrato, degradación, aislamiento, paridad, almacén.

Las pruebas sin entorno aparte usan un ejecutor falso con la salida NATIVA grabada
(`tests/fixtures/bots/passivbot_parity.json`). Las de integración corren el bot de verdad en su
entorno (3.12 + Rust) y se saltan si `EIM_BOT_PASSIVBOT_PY`/`EIM_BOT_PASSIVBOT_DIR` no existen.
"""

import importlib.util
import json
import threading
from pathlib import Path

import duckdb
import pytest
from pydantic import ValidationError

from eim.bots.adapter import SignalAdapter
from eim.bots.card import card_of
from eim.bots.pb_adapter import MINUTE, PassivbotSimAdapter, run_hash
from eim.core import Candle, SimFill, SimRun
from eim.data.bots.runner import Limits, RunResult, RunSpec
from eim.data.bots.simstore import SimRunStore
from tests.opt_in import OPT_IN

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "bots"
PARITY = json.loads((FIX / "passivbot_parity.json").read_text(encoding="utf-8"))
_spec = importlib.util.spec_from_file_location("make_pb_parity", FIX / "make_passivbot_parity.py")
GEN = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(GEN)

SHA = card_of("passivbot").commit_sha
PY, DIR = OPT_IN.get("EIM_BOT_PASSIVBOT_PY"), OPT_IN.get("EIM_BOT_PASSIVBOT_DIR")
real = pytest.mark.skipif(not (PY and DIR and Path(DIR).exists()),
                          reason="sin el entorno aparte de Passivbot (docs/BOTS.md)")


def candles(n: int = GEN.N) -> list[Candle]:
    return [Candle(t=r[0], o=r[1], h=r[2], l=r[3], c=r[4], v=r[5]) for r in GEN.gen_candles(n)]


def native_output(n_candles: int = GEN.N) -> dict:
    """`out.json` con la forma del script pero con los fills grabados del bot nativo."""
    cols = ["index", "timestamp", "coin", "pnl", "fee_paid", "usd_total_balance",
            "btc_cash_wallet", "usd_cash_wallet", "btc_price", "qty", "price", "psize", "pprice",
            "type", "liquidity", "wallet_exposure"]
    fills = []
    for i, (t, typ, qty, price, psize, pnl, fee) in enumerate(PARITY["fills"]):
        fills.append([i, t, "BTC", pnl, fee, 0.0, 0.0, 0.0, price, qty, price, psize, price, typ,
                      "maker", 0.1])
    return {"engine": "0.1.0", "bot_version": SHA, "fill_columns": cols, "fills": fills,
            "n_candles": n_candles, "equity": [[PARITY["fills"][0][0], 10_000.0, 0.0, 0.0]],
            "analysis": {"fills_count": len(fills), "liquidated": False}}


class FakeRunner:
    def __init__(self, output=None, status="ok", warnings=()):
        self.output, self.status, self.warnings, self.specs = output, status, warnings, []

    def __call__(self, spec: RunSpec) -> RunResult:
        self.specs.append(spec)
        return RunResult(self.status, self.output, tuple(self.warnings))


def adapter(runner, **kw) -> PassivbotSimAdapter:
    return PassivbotSimAdapter(Path("py"), Path("dir"), runner=runner, **kw)


def sim(ad, **kw) -> SimRun:
    return ad.simulate("BTCUSDT", candles(), balance=GEN.BALANCE, warmup_minutes=GEN.WARMUP,
                       overrides=GEN.OVERRIDES, **kw)


# --- contrato y carril -------------------------------------------------------------------------
def test_run_is_labeled_simulated_and_never_a_signal():
    ad = adapter(FakeRunner(native_output()))
    run = sim(ad)
    assert run.status == "ok" and run.label == "simulado"
    assert not isinstance(ad, SignalAdapter) and not hasattr(ad, "signals")   # nunca vota
    assert len(run.fills) == len(PARITY["fills"]) > 0
    assert run.costs_assumed == {"maker_fee": 0.0002, "taker_fee": 0.0005}   # T25, no el README
    assert run.start == GEN.START and run.end == GEN.START + GEN.N * MINUTE
    assert any("simulación, no operaciones" in e for e in run.evidence)


def test_contract_has_no_order_or_stance_fields():
    fields = set(SimRun.model_fields) | set(SimFill.model_fields)
    assert not fields & {"stance", "confidence", "order", "size", "leverage", "api_key", "secret"}
    with pytest.raises(ValidationError):
        SimRun.model_validate({**sim(adapter(FakeRunner(native_output()))).model_dump(),
                               "order_size": 1.0})


def test_fill_after_window_is_rejected():
    run = sim(adapter(FakeRunner(native_output()))).model_dump()
    run["fills"][0]["t"] = run["end"]
    with pytest.raises(ValidationError):
        SimRun.model_validate(run)


def test_version_changes_with_sha_params_and_costs():
    ad = adapter(FakeRunner())
    v0 = ad.version("trailing_martingale")
    assert v0.startswith(SHA + "+")
    assert ad.version("trailing_martingale", balance=5000.0) != v0
    assert ad.version("trailing_martingale", overrides={"bot.long.risk.n_positions": 2}) != v0
    assert ad.version("ema_anchor") != v0


# --- degradación: nunca lanza ------------------------------------------------------------------
def test_runner_failure_is_degraded_without_exception():
    run = sim(adapter(FakeRunner(None, "degraded", ("el bot excedió 900s",))))
    assert run.status == "degraded" and not run.fills and "excedió" in run.evidence[0]


def test_gaps_or_missing_candles_are_no_data():
    ad = adapter(FakeRunner(native_output()))
    cs = candles()
    assert ad.simulate("BTCUSDT", [], overrides={}).status == "no_data"
    assert ad.simulate("BTCUSDT", cs[:10] + cs[12:]).status == "no_data"
    assert ad.simulate("BTCUSDT", cs[:1]).status == "no_data"


@pytest.mark.parametrize("patch", [{"engine": "9.9"}, {"bot_version": "0" * 40}, {"n_candles": 5},
                                   {"fill_columns": ["x"]}])
def test_inconsistent_output_is_degraded(patch):
    out = native_output() | patch
    assert sim(adapter(FakeRunner(out))).status == "degraded"


def test_garbage_row_is_degraded():
    out = native_output()
    out["fills"][0][-2] = "mitad"      # liquidez inválida
    assert sim(adapter(FakeRunner(out))).status == "degraded"


# --- aislamiento: lo que el bot recibe ---------------------------------------------------------
def test_request_carries_data_only_no_credentials():
    fr = FakeRunner(native_output())
    sim(adapter(fr))
    spec = fr.specs[0]
    blob = json.dumps(dict(spec.request)).lower()
    assert not any(w in blob for w in ("secret", "api_key", "password", "token"))
    assert not spec.extra_env and set(spec.files) == {"candles.json"}
    assert spec.bot_dir == Path("dir").resolve()      # SHA fijado y verificado:
    assert spec.expected_sha == SHA
    assert spec.limits.timeout_s <= 900 and spec.limits.memory_mb <= 3072


# --- almacén ------------------------------------------------------------------------------------
def test_store_appends_once_and_refuses_future_windows():
    st = SimRunStore(duckdb.connect(":memory:"), threading.Lock())
    run = sim(adapter(FakeRunner(native_output())))
    assert st.append(run, run.end + 1) is True
    assert st.append(run, run.end + 2) is False        # solo se añade, nunca se reescribe
    assert [r.version for r in st.query("passivbot")] == [run.version]
    with pytest.raises(ValueError):
        st.append(run, run.end - 1)


# --- integración con el bot real ---------------------------------------------------------------
@real
def test_parity_with_native_bot():
    run = sim(PassivbotSimAdapter(Path(PY), Path(DIR)))
    assert run.status == "ok", run.evidence
    got = [(f.t, f.kind, f.qty, f.price, f.psize_after, f.pnl, f.fee_paid) for f in run.fills]
    assert len(got) == len(PARITY["fills"])
    for g, w in zip(got, PARITY["fills"], strict=True):
        assert g[:2] == tuple(w[:2])
        assert g[2:] == pytest.approx(tuple(w[2:]), rel=1e-9, abs=1e-9)   # mismo motor Rust


@real
def test_no_lookahead_and_reproducible():
    ad = PassivbotSimAdapter(Path(PY), Path(DIR))
    full = sim(ad)
    cut = GEN.START + 3000 * MINUTE
    short = ad.simulate("BTCUSDT", candles()[:3000], balance=GEN.BALANCE,
                        warmup_minutes=GEN.WARMUP, overrides=GEN.OVERRIDES)
    assert short.status == "ok"
    head = [f for f in full.fills if f.t < cut - MINUTE]
    assert [f for f in short.fills if f.t < cut - MINUTE] == head and head   # truncar no cambia
    assert run_hash(sim(ad)) == run_hash(full)                                # y es reproducible


@real
def test_time_limit_degrades_instead_of_raising():
    ad = PassivbotSimAdapter(Path(PY), Path(DIR), limits=Limits(timeout_s=0.5))
    run = sim(ad)
    assert run.status == "degraded" and "excedió" in run.evidence[0]
