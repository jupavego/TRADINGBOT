"""T214: `vol_surface` está en el registro pero el escáner no lo considera (ningún perpetuo del
universo tiene cadena de opciones). Sus huellas no cambian: el umbral del placebo de T95 sigue
vigente y la síntesis no abre intentos nuevos."""

from __future__ import annotations

from eim.agents.capabilities import CAPABILITIES
from eim.agents.registry import default_registry
from eim.core.opportunity import stable_hash
from eim.scanner import deep, jobs


def test_registered_but_out_of_the_scanner():
    assert "vol_surface" in default_registry().ids() and "vol_surface" in CAPABILITIES
    assert jobs.OUT_OF_SCANNER == {"vol_surface"}
    assert "vol_surface" not in {a.id for a in deep.default_agents()}


def test_scanner_fingerprints_ignore_it():
    rest = [a for a in default_registry().latest() if a.id != "vol_surface"]
    assert deep.agents_fingerprint(deep.default_agents()) == stable_hash(
        sorted((a.id, a.version) for a in rest), size=6)
    before = dict(CAPABILITIES)
    try:
        CAPABILITIES.pop("vol_surface")
        without = jobs.capabilities_fingerprint()
    finally:
        CAPABILITIES.clear()
        CAPABILITIES.update(before)
    assert jobs.capabilities_fingerprint() == without
