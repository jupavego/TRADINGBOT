"""T137: los intentos cuentan en Holm, llegan al registro y no tocan lo que abren los perfiles."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

import pytest

from eim.data.paper_store import PaperStore
from eim.data.validation_store import ValidationStore
from eim.paper.catalog import CATALOG
from eim.paper.params import ExecParams
from eim.validation import entry_run as er
from eim.validation import entry_versions as ev
from eim.validation.attempts import load_attempts, write_attempts
from eim.validation.criteria import load_criteria
from eim.validation.entry_prereg import load_prereg
from eim.validation.gate import OBSERVACION, Check, Measure, Verdict, measure
from eim.validation.lineage import Version, Window, iso_ms
from tests.validation.helpers import trades

PR = load_prereg()
M8, S1, TOPE, M8_TOPE, S1_TOPE = PR.variants
SID = "consenso_sintesis@1h"


def _parent() -> Version:
    win = Window(0, iso_ms("2026-10-22T22:36:00Z"), None, "auto")
    return Version(SID, 2, "padre", "consenso_sintesis", "1h", iso_ms("2026-10-22T22:36:00Z"),
                   None, "auto", windows=(win,))


# --- Holm y registro -----------------------------------------------------------------------------
def test_every_attempt_counts_in_holm_even_without_trades():
    """Todos los intentos entran en la familia aunque solo uno tenga operaciones."""
    crit = load_criteria()
    sids = [f"s{k}@1h" for k in range(10)]
    versions = [(ev.version_of(s, v, PR, f"{s}{v.id}"), v.id) for v in PR.variants for s in sids]
    family = er.holm_family({"BTCUSDT|previa": 0.5}, "BTCUSDT", [x for x, _ in versions])
    assert len(family) == 1 + 50
    run = er.VariantRun("m8")
    ts = trades(n=40, mean=0.8, t0=iso_ms("2026-10-23T00:00:00Z"), step_h=1, live_last=0)
    run.trades["s0@1h"] = ts
    runs = {v.id: er.VariantRun(v.id) for v in PR.variants} | {"m8": run}
    parents = [replace(_parent(), sid=s, strategy=s.split("@")[0]) for s in sids]
    got = er.score_reading(PR.reading("oficial"), versions[:10], runs, parents, family, crit,
                           "BTCUSDT", iso_ms("2030-01-01T00:00:00Z"), None)
    assert len(got) == 10
    best = next(x for x in got if x.version.sid == "s0@1h")
    assert best.measure.n == 40 and best.measure.reps == crit.null_reps(len(family))
    assert best.p_holm >= min(1.0, best.measure.p_raw * 2)


def test_same_gate_as_t49_for_every_reading():
    """Una lectura descriptiva es la misma `measure`, solo con otras ventanas."""
    crit = load_criteria()
    ts = trades(n=60, t0=iso_ms("2026-07-20T00:00:00Z"), step_h=2, live_last=0)
    wins = ev.complement(PR.reading("reserva").ranges)
    a = measure("x", ts, wins, "BTCUSDT", iso_ms("2030-01-01T00:00:00Z"), crit, 10)
    b = measure("x", ts, (), "BTCUSDT", iso_ms("2030-01-01T00:00:00Z"), crit, 10)
    assert a.n == b.n == 60 and a.mean_r == b.mean_r


@pytest.fixture
def vstore():
    ps = PaperStore(":memory:")
    yield ValidationStore(ps)
    ps.close()


def test_attempts_are_born_retired_and_do_not_touch_the_live_version(vstore, tmp_path):
    live = vstore.ensure(SID, "consenso_sintesis", "1h", "vivo", 1000)
    attempts = [ev.version_of(SID, v, PR, f"fp{v.id}", live.n) for v in PR.variants]
    labels = {a.label: v.id for a, v in zip(attempts, PR.variants, strict=True)}
    path = tmp_path / "a.json"
    write_attempts(path, PR.version, PR.sha256, attempts, labels)
    assert vstore.register_attempts(load_attempts(path)) == 5
    assert vstore.register_attempts(load_attempts(path)) == 0        # idempotente
    fam = vstore.versions(SID)
    assert len(fam) == 6 and all(v.retired_ms is not None for v in fam if v.origin == ev.ORIGIN)
    assert next(v for v in fam if v.retired_ms is None) == live
    # la versión viva sigue igual y la siguiente sigue su propia numeración
    assert vstore.ensure(SID, "consenso_sintesis", "1h", "vivo", 2000) == live
    nxt = vstore.ensure(SID, "consenso_sintesis", "1h", "nueva", 3000)
    assert nxt.n == live.n + 1 and nxt.parent == live.n


def test_attempts_are_never_the_parent_of_a_live_version(vstore):
    """Una máquina sin versión viva: el padre no puede ser un intento, o heredaría sus ventanas."""
    attempts = [ev.version_of(SID, v, PR, f"fp{v.id}", None) for v in PR.variants]
    vstore.register_attempts(attempts)
    live = vstore.ensure(SID, "consenso_sintesis", "1h", "vivo", 1000)
    assert live.n == 1 and live.parent is None
    assert all(a.label != live.label for a in attempts)


def test_live_numbering_skips_a_number_taken_by_an_attempt(vstore):
    """La unión entre máquinas renumera los intentos: el alta no puede chocar con ellos."""
    a = replace(ev.version_of(SID, M8, PR, "fp", None), n=1)
    vstore.register_attempts([a])
    assert vstore.ensure(SID, "consenso_sintesis", "1h", "vivo", 1000).n == 2


def test_attempts_file_round_trip_keeps_windows(tmp_path):
    a = ev.version_of("x@15m", M8, PR, "fp")
    b = ev.version_of("x@1h", S1_TOPE, PR, "fq")
    path = tmp_path / "a.json"
    write_attempts(path, PR.version, PR.sha256, [a, b], {a.label: "m8", b.label: "s1_tope"})
    got = {v.label: v for v in load_attempts(path)}
    assert got[a.label].windows == a.windows and got[b.label].windows == b.windows
    assert got[a.label].retired_ms == iso_ms(PR.live_rule.alta)
    assert load_attempts(tmp_path / "no_existe.json") == []


# --- nada de esto llega a los perfiles -----------------------------------------------------------
def test_paper_package_does_not_import_the_entry_versions():
    """Lo que abren los perfiles no puede depender de T137: ni un import desde `eim/paper`."""
    from pathlib import Path

    import eim.paper
    root = Path(eim.paper.__file__).parent
    for f in root.rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        assert "entry_versions" not in text and "entry_run" not in text, f
        assert "eim.validation.attempts" not in text, f


def test_candidate_rule_needs_everything_the_prereg_says():
    """La regla de lectura no se relaja: basta que falle una de sus condiciones."""
    v = ev.version_of(SID, S1, PR, "fp")
    def verdict(ok3=True, n=50, mean=0.2):
        m = Measure("x", 0, n, 0, 0, mean, 0.01, {}, (0.1, 0.3), 0.001, 100, 0.1, 0.1, [], 0, None,
                    0.1, (None, None))
        cs = tuple(Check(k, k, None, "", ok3 if k == "V3" else True, "")
                   for k in ("V1", "V2", "V3", "V4", "V5", "V6"))
        return Verdict(v, m, OBSERVACION, "", cs, 0.01, "c", ())

    var = {v.label: "s1"}
    ctl = {"s1": {"ok": True, "tested": True}}
    good = {"banco": [verdict()], "reserva": [verdict()]}
    assert er.candidates(PR, good, {v.label: False}, var, ctl)
    bad = [
        ({"banco": [verdict(ok3=False)], "reserva": [verdict()]}, {v.label: False}, ctl),
        ({"banco": [verdict()], "reserva": [verdict(mean=-0.1)]}, {v.label: False}, ctl),
        ({"banco": [verdict()], "reserva": [verdict(n=10)]}, {v.label: False}, ctl),
        (good, {v.label: True}, ctl),
        (good, {v.label: False}, {"s1": {"ok": True, "tested": False}}),
        (good, {v.label: False}, {"s1": {"ok": False, "tested": True}}),
    ]
    for by, inert, c in bad:
        assert not er.candidates(PR, by, inert, var, c)


def test_pooled_tables_leave_out_the_control():
    """Las entradas al azar se miden aparte: en el agregado moverían las cifras de las reales."""
    ts = trades(n=30, mean=1.0, t0=iso_ms("2025-01-01T00:00:00Z"), step_h=1, live_last=0)
    ctl = "control_aleatorio@1h"
    real = ev.version_of(SID, S1, PR, "fp")
    rnd = ev.version_of(ctl, S1, PR, "fq")
    run = er.VariantRun("s1", trades={SID: ts[:10], ctl: ts})
    got = er.pooled_table(PR.reading("banco"), {}, [(real, "s1"), (rnd, "s1")], {"s1": run}, [],
                          "BTCUSDT", iso_ms("2030-01-01T00:00:00Z"), "control_aleatorio")
    assert got["s1"]["1h"]["n"] == 10 and got["s1"]["todos"]["n"] == 10


def test_cost_summary_leaves_out_the_control():
    run = er.VariantRun("s1")
    run.stats = {SID: Counter(ideas=10, moved=5, vetoed=2),
                 "control_aleatorio@1h": Counter(ideas=90, moved=90, vetoed=90)}
    run.cost_sum = {SID: 1.0, "control_aleatorio@1h": 90.0}
    x = er.cost_summary(run, "control_aleatorio")["1h"]
    assert x["ideas"] == 10 and x["moved_frac"] == 0.5 and x["cost_ex_ante_r"] == pytest.approx(0.1)


def test_repo_attempts_are_the_declared_ones_and_not_the_live_versions():
    """El archivo que llega al registro vivo: los 520 declarados, ninguno con huella viva."""
    got = load_attempts()
    ep = ExecParams()
    live = {f"{i.id}@{tf}": i.version(tf, ep) for tf in ep.timeframes for i in CATALOG.values()
            if i.runs_in(tf)}
    assert len(got) == PR.attempts.total
    assert len({(v.sid, v.n) for v in got}) == len(got)
    assert {v.n for v in got} == {v.n for v in PR.variants}
    assert {v.sid for v in got} == set(live)
    assert all(v.fingerprint != live[v.sid] for v in got)
    alta = iso_ms(PR.live_rule.alta)
    assert all(v.origin == ev.ORIGIN and v.retired_ms == alta and v.windows for v in got)
    sel = iso_ms(PR.windows.selection.from_) + 1
    assert all(any(w.covers(sel, "BTCUSDT") for w in v.windows) for v in got)

