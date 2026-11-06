"""T135 — La salida en la huella de T49: otra salida es otra versión, y la de hoy no cambia."""

from __future__ import annotations

import hashlib
import json

from eim.paper.adaptive import exit_identity
from eim.paper.params import ExecParams
from eim.paper.versioning import exec_fingerprint, exit_fingerprint, version_of
from tests.paper.test_adaptive_book import adaptive_profile


def legacy_version(sid: str, family: str, rules: str, tf: str, ep: ExecParams) -> str:
    """La fórmula de antes de T135, escrita aquí a mano: es la que no se puede mover."""
    blob = json.dumps({"id": sid, "family": family, "rules": rules, "tf": tf,
                       "exec": exec_fingerprint(ep, tf)}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def test_without_exit_the_version_is_byte_identical_to_before():
    ep = ExecParams()
    assert version_of("s", "f", "r", "1h", ep) == legacy_version("s", "f", "r", "1h", ep)
    assert version_of("s", "f", "r", "1h") == legacy_version("s", "f", "r", "1h", ExecParams())


def test_changing_the_exit_is_a_new_version():
    ep = ExecParams()
    a = exit_identity(adaptive_profile(k=3.0))
    b = exit_identity(adaptive_profile(k=4.0))
    base = version_of("s", "f", "r", "1h", ep)
    with_a = version_of("s", "f", "r", "1h", ep, exit_policy=a)
    assert with_a != base
    assert with_a != version_of("s", "f", "r", "1h", ep, exit_policy=b)
    assert with_a == version_of("s", "f", "r", "1h", ep, exit_policy=dict(a))


def test_exit_fingerprint_is_stable_and_order_independent():
    assert exit_fingerprint({"a": 1, "b": 2}) == exit_fingerprint({"b": 2, "a": 1})
    assert exit_fingerprint({"a": 1}) != exit_fingerprint({"a": 2})


def test_m5_version_includes_the_costs_of_its_break_even():
    p = adaptive_profile("M5")
    assert exit_identity(p)["params"]["est_cost_frac"] == p.est_cost_frac
    other = p.model_copy(update={"est_cost_frac": p.est_cost_frac * 2})
    assert exit_identity(other) != exit_identity(p)
