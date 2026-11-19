"""El pre-registro de T187–T189 no se edita después de mirar: cambiarlo es una versión nueva."""

from __future__ import annotations

from pathlib import Path

from eim.paper.asym import prereg as P

NOTE = Path(__file__).resolve().parents[4] / "PLAN" / "notas" / "T187_preregistro.md"


def test_frozen_fingerprint_is_the_published_one():
    assert P.fingerprint() == P.FINGERPRINT, (
        "el pre-registro cambió: publica VERSION nueva y su nota, no edites la huella")


def test_the_note_carries_the_same_fingerprint():
    assert P.FINGERPRINT in NOTE.read_text(encoding="utf-8")


def test_dates_are_the_ones_announced():
    assert P.START_ISO == "2026-11-19T00:00:00+00:00"
    assert P.T31_CLOSE_ISO == "2026-11-28T00:00:00+00:00"
    days = [(t - P.START_MS) // P.DAY_MS for t in P.checkpoints_ms()]
    assert days == [28, 56, 84]


def test_t31_close_matches_the_api_default():
    import ast
    cfg = Path(__file__).resolve().parents[3] / "eim" / "api" / "config.py"
    tree = ast.parse(cfg.read_text(encoding="utf-8"))
    vals = [n.value.value for n in tree.body if isinstance(n, ast.Assign)
            and any(getattr(t, "id", "") == "T31_CLOSE_UTC" for t in n.targets)]
    assert vals == [P.T31_CLOSE_ISO]


def test_exit_rule_is_never_automatic():
    assert "t188" not in P.AUTO_RULES and "t188" in P.USER_RULES
    assert set(P.AUTO_RULES) | set(P.USER_RULES) == set(P.VERDICT_RULES)


def test_brake_never_stops_completely():
    assert P.PHASE2_DD_STEPS == ((0.05, 0.5), (0.10, 0.25))
    assert min(m for _, m in P.PHASE2_DD_STEPS) > 0
