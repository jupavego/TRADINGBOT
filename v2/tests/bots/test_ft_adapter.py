"""Adaptador modo B (`freqtrade-strategies`): reglas de postura, degradación y extremo a extremo."""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from eim.bots.card import card_of
from eim.bots.ft_adapter import FreqtradeAdapter, ft_pair, positions
from eim.data.bots.runner import RunResult
from tests.bots.helpers import candles, snapshot

ENGINE = "2026.9"


def flags(**series: str) -> dict[str, list[int]]:
    """`flags(enter_long="1..0", exit_long="...1")`: '1' = bandera, cualquier otra cosa = 0."""
    n = max(len(v) for v in series.values())
    out = {k: [0] * n for k in ("enter_long", "exit_long", "enter_short", "exit_short")}
    for k, v in series.items():
        out[k] = [1 if ch == "1" else 0 for ch in v.ljust(n, ".")]
    return out


def test_positions_follow_freqtrade_entry_rule():
    f = flags(enter_long="..1.....", exit_long=".....1..", enter_short="........")
    assert positions(f, True, 0) == [0, 0, 1, 1, 1, 0, 0, 0]
    f = flags(enter_long="..1...1.", enter_short="....1...", exit_short="......1.")
    assert positions(f, True, 0) == [0, 0, 1, 1, -1, -1, 1, 1]      # entrada opuesta gira
    # entrada que choca con su salida o con la entrada contraria: no vale
    assert positions(flags(enter_long="1", exit_long="1"), True, 0) == [0]
    assert positions(flags(enter_long="1", enter_short="1"), True, 0) == [0]


def test_positions_ignore_shorts_when_the_strategy_cannot_short():
    assert positions(flags(enter_short="1"), False, 0) == [0]


def test_positions_are_flat_during_startup_candles():
    assert positions(flags(enter_long="11111"), True, 3) == [0, 0, 0, 1, 1]


def test_positions_never_look_ahead():
    f = flags(enter_long=".1....1...", exit_long="....1.....", enter_short="......1...")
    full = positions(f, True, 2)
    for k in range(1, len(full) + 1):
        cut = {key: v[:k] for key, v in f.items()}
        assert positions(cut, True, 2) == full[:k]


def test_pair_name():
    assert ft_pair("BTCUSDT") == "BTC/USDT:USDT" and ft_pair("ETHUSDT") == "ETH/USDT:USDT"


# --- con un ejecutor falso ------------------------------------------------------------------
def fake_output(snap, enter_long_at=None, **over):
    cs = snap.candles
    fl = {k: [0] * len(cs) for k in ("enter_long", "exit_long", "enter_short", "exit_short")}
    for i in enter_long_at or []:
        fl["enter_long"][i] = 1
    out = {"engine": ENGINE, "interface_version": 3, "can_short": True, "startup_candle_count": 18,
           "times": [c.t for c in cs], "flags": fl}
    return out | over


def adapter(out_fn, **kw):
    seen = []

    def runner(spec):
        seen.append(spec)
        return out_fn(spec)

    ad = FreqtradeAdapter(Path("/py"), Path("/co"), ENGINE, runner=runner, **kw)
    return ad, seen


def test_adapter_builds_the_signal_from_flags():
    snap = snapshot(200)
    ad, seen = adapter(lambda sp: RunResult("ok", fake_output(snap, [150]), (), 0.4, True))
    (s,) = ad.signals(snap)
    assert s.bot_id == "freqtrade-strategies" and s.strategy == "FSupertrendStrategy"
    assert s.stance == 1.0 and s.status == "ok" and s.confidence is None
    assert s.raw["held_bars"] == 50 and s.raw["engine"] == ENGINE
    assert "aislada" in s.raw["isolation"]
    assert "solo por señal" in s.evidence[0]
    assert s.version.startswith(card_of("freqtrade-strategies").commit_sha + "+")
    spec = seen[0]
    assert spec.expected_sha == card_of("freqtrade-strategies").commit_sha
    assert spec.request["pair"] == "ETH/USDT:USDT"
    assert json.loads(spec.files["candles.json"])[0][0] == snap.candles[0].t
    assert not any(k in spec.request for k in ("api_key", "secret", "order"))


def test_bot_failure_or_garbage_is_degraded_never_an_exception():
    snap = snapshot(200)
    fail = RunResult("degraded", None, ("el bot excedió 60s y fue detenido",), 60.0)
    (s,) = adapter(lambda sp: fail)[0].signals(snap)
    assert s.status == "degraded" and s.stance == 0 and "excedió" in s.evidence[0]
    for bad in ({"engine": ENGINE}, {**fake_output(snap), "times": [1, 2, 3]},
                {**fake_output(snap), "flags": {"enter_long": "x"}}):
        (s,) = adapter(lambda sp, b=bad: RunResult("ok", b, (), 0.1))[0].signals(snap)
        assert s.status == "degraded" and s.stance == 0


def test_engine_version_mismatch_is_not_accepted():
    snap = snapshot(200)
    ad, _ = adapter(lambda sp: RunResult("ok", fake_output(snap, engine="2027.1"), (), 0.1))
    (s,) = ad.signals(snap)
    assert s.status == "degraded" and "2027.1" in s.evidence[0]


def test_too_few_candles_for_the_strategy_startup_is_no_data():
    snap = snapshot(10)
    ad, _ = adapter(lambda sp: RunResult("ok", fake_output(snap), (), 0.1))
    (s,) = ad.signals(snap)
    assert s.status == "no_data" and s.stance == 0


def test_version_depends_on_sha_strategy_and_engine():
    ad, _ = adapter(lambda sp: None)
    other_engine = FreqtradeAdapter(Path("/py"), Path("/co"), "2027.1")
    other_sha = FreqtradeAdapter(Path("/py"), Path("/co"), ENGINE, card=card_of(
        "freqtrade-strategies").model_copy(update={"commit_sha": "1" * 40}))
    v = ad.version("FSupertrendStrategy")
    assert len({v, other_engine.version("FSupertrendStrategy"),
                other_sha.version("FSupertrendStrategy"), ad.version("FAdxSmaStrategy")}) == 4


# --- extremo a extremo con el ejecutor real y un «bot» de juguete ---------------------------
TOY = """
    import json
    from pathlib import Path
    req = json.loads(Path("request.json").read_text())
    rows = json.loads(Path("candles.json").read_text())
    n = len(rows)
    fl = {k: [0] * n for k in ("enter_long", "exit_long", "enter_short", "exit_short")}
    for i in range(20, n):                      # compra cuando el cierre sube dos velas seguidas
        if rows[i][4] > rows[i - 1][4] > rows[i - 2][4]:
            fl["enter_long"][i] = 1
    Path("out.json").write_text(json.dumps({"engine": "2026.9", "interface_version": 3,
        "can_short": False, "startup_candle_count": 20, "times": [r[0] for r in rows],
        "flags": fl}))
"""


def test_end_to_end_through_the_isolated_runner(tmp_path):
    repo = tmp_path / "bot"
    repo.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for args in (["init", "-q"], ["add", "."], ["commit", "-qm", "x", "--allow-empty"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True, env=env, capture_output=True)
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True,
                         text=True, check=True, env=env).stdout.strip()
    script = tmp_path / "toy.py"
    script.write_text(textwrap.dedent(TOY))
    card = card_of("freqtrade-strategies").model_copy(update={"commit_sha": sha})
    ad = FreqtradeAdapter(Path(sys.executable), repo, ENGINE, card=card, script=script)
    snap = snapshot(300)
    (s,) = ad.signals(snap)
    assert s.status == "ok", s.evidence
    cs = [c.c for c in snap.candles]
    expect = 1.0 if cs[-1] > cs[-2] > cs[-3] else None
    if expect:
        assert s.stance == 1.0
    assert s.data_quality.last_candle_t == snap.candles[-1].t <= s.asof
    # no anticipación: con menos velas la postura es la misma que en esa vela de la corrida larga
    full = positions(json.loads(json.dumps(
        {"enter_long": [1 if i >= 20 and cs[i] > cs[i - 1] > cs[i - 2] else 0
                        for i in range(300)], "exit_long": [0] * 300, "enter_short": [0] * 300,
         "exit_short": [0] * 300})), False, 20)
    (s2,) = ad.signals(snapshot(250))
    assert s2.stance == full[249] and s.stance == full[299]
    # y si alguien toca el checkout del bot, no corre
    (repo / "x.py").write_text("1")
    subprocess.run(["git", "-C", str(repo), "add", "x.py"], check=True, env=env,
                   capture_output=True)
    (s3,) = ad.signals(snap)
    assert s3.status == "degraded" and "cambios locales" in s3.evidence[0]


# --- paridad con el bot nativo (Freqtrade real, fixture generado con `make_freqtrade_parity.py`) --
FT_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "bots" / "freqtrade_parity.json"
FT = json.loads(FT_FIXTURE.read_text(encoding="utf-8"))


def replay(spec):
    """Ejecutor que responde con la salida REAL del bot recortada a las velas enviadas."""
    n = len(json.loads(spec.files["candles.json"]))
    out = {"engine": FT["engine"], "interface_version": 3, "can_short": FT["can_short"],
           "startup_candle_count": FT["startup_candle_count"], "times": FT["times"][:n],
           "flags": {k: v[:n] for k, v in FT["flags"].items()}}
    return RunResult("ok", out, (), 0.0, FT["network_isolated"])


def test_parity_with_native_freqtrade_decisions_on_same_candles():
    """El adaptador coincide con `get_entry_signal`/`get_exit_signal` del bot real en cada vela
    muestreada, calculadas por él con SOLO las velas hasta esa vela."""
    cs = candles()
    ad = FreqtradeAdapter(Path("/py"), Path("/co"), FT["engine"], runner=replay)
    assert [c.t for c in cs] == FT["times"]
    pos = positions(FT["flags"], FT["can_short"], FT["startup_candle_count"])
    checked = 0
    for key, native in FT["native"].items():
        i = FT["times"].index(int(key))
        (s,) = ad.signals(snapshot(i + 1, cs))
        assert s.status == "ok" and s.stance == pos[i]
        last = s.raw["flags_last"]
        eff_long = last["enter_long"] == 1 and not (last["exit_long"] or last["enter_short"])
        assert (native["entry"] == "long") == eff_long, key
        assert native["exit_long"] == bool(last["exit_long"]), key
        assert native["exit_short"] == bool(last["exit_short"]), key
        checked += 1
    assert checked >= 200
    assert {v["entry"] for v in FT["native"].values()} >= {"long", None}  # hay de ambas


def test_parity_fixture_documents_its_origin():
    assert FT["strategy"] == "FSupertrendStrategy" and FT["network_isolated"] in (True, False)
    assert FT["sha"] == card_of("freqtrade-strategies").commit_sha


# --- con Freqtrade de verdad (solo si el entorno aparte está configurado) ----------------------
FT_PY, FT_DIR = os.environ.get("EIM_BOT_FREQTRADE_PY"), os.environ.get("EIM_BOT_FREQTRADE_DIR")


@pytest.mark.skipif(not (FT_PY and FT_DIR), reason="sin entorno de Freqtrade (EIM_BOT_FREQTRADE_*)")
def test_real_freqtrade_runs_isolated_and_agrees_with_the_fixture():
    ad = FreqtradeAdapter(Path(FT_PY), Path(FT_DIR), FT["engine"])
    cs = candles()
    pos = positions(FT["flags"], FT["can_short"], FT["startup_candle_count"])
    for n in (len(cs), len(cs) - 40):          # con menos velas la postura es la de esa vela
        (s,) = ad.signals(snapshot(n, cs))
        assert s.status == "ok", s.evidence
        assert s.stance == pos[n - 1]
        assert "aislada" in s.raw["isolation"] or os.name == "nt"
