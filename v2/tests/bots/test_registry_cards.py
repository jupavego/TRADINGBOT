"""Vigila las fichas del catálogo de bots (T56): esquema, puntuación y habilitación."""
import json
import re
from pathlib import Path

import pytest

REGISTRY = Path(__file__).resolve().parents[2] / "eim" / "bots" / "registry"
CARDS = sorted(REGISTRY.glob("*.json"))

OW = {"O1": 20, "O2": 15, "O3": 15, "O4": 15, "O5": 10, "O6": 10, "O7": 10, "O8": 5}
SW = {"S1": 15, "S2": 15, "S3": 15, "S4": 10, "S5": 10, "S6": 10, "S7": 10, "S8": 10, "S9": 5}
RED = {"R1", "R2", "R3", "R4", "R5", "R6", "R7"}
THRESHOLD = 70
APPROVED = {"hummingbot-directional", "freqtrade", "freqtrade-strategies", "passivbot"}
APPROVED_2 = {"nostalgia-for-infinity", "jesse-example-strategies", "trendrider-strategy"}
REQUIRED = {
    "id", "name", "repo", "commit_sha", "commit_date", "audited_at", "license", "bot_class",
    "integration_mode", "binance_markets", "strategies", "dependencies", "risks", "verdict",
    "squad_proposal", "reasons", "approval", "operational", "security", "evidence", "audit_scope",
    "universe_ref",
}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_catalog_not_empty():
    assert len(CARDS) >= 45


@pytest.mark.parametrize("path", CARDS, ids=lambda p: p.stem)
def test_card_schema(path):
    c = load(path)
    assert set(c) == REQUIRED
    assert c["id"] == path.stem and re.fullmatch(r"[a-z0-9][a-z0-9-]*", c["id"])
    assert re.fullmatch(r"[0-9a-f]{40}", c["commit_sha"])
    assert c["bot_class"] in {"D", "L", "IA", "INFRA"}
    assert c["integration_mode"] in {"A", "B", "C", "D"}
    assert c["verdict"] in {"usar", "referencia", "descartar"}
    assert c["squad_proposal"] in {"propuesto", "opcional", "no"}
    assert set(c["binance_markets"]) <= {"spot", "usdm_futures"}
    assert c["reasons"] and c["evidence"]
    prefix = f"https://github.com/{c['repo']}/blob/{c['commit_sha']}/"
    assert all(e["url"].startswith(prefix) for e in c["evidence"])
    assert set(c["license"]) == {"spdx", "file", "sha256", "head"}


@pytest.mark.parametrize("path", CARDS, ids=lambda p: p.stem)
def test_scores_follow_the_written_rules(path):
    c = load(path)
    ops = c["operational"]["checks"]
    assert set(ops) == set(OW)
    assert all(0 <= v <= OW[k] for k, v in ops.items())
    assert c["operational"]["total"] == sum(ops.values())
    sec = c["security"]
    assert set(sec["checks"]) == set(SW)
    assert sec["total"] == sum(SW[k] for k, ok in sec["checks"].items() if ok)
    assert set(sec["red_alerts"]) <= RED
    assert all(k in sec["notes"] for k, ok in sec["checks"].items() if not ok)
    # La seguridad es condición de habilitación y no se compensa.
    assert sec["enabled"] == (not sec["red_alerts"] and sec["total"] >= THRESHOLD)


@pytest.mark.parametrize("path", CARDS, ids=lambda p: p.stem)
def test_integration_rules(path):
    c = load(path)
    spdx = c["license"]["spdx"]
    copyleft = any(x in spdx for x in ("GPL", "AGPL"))
    if c["integration_mode"] == "A":
        assert not copyleft and spdx != "NONE", "el modo A exige licencia permisiva"
    if copyleft and c["squad_proposal"] != "no":
        assert c["integration_mode"] == "B", "GPL/AGPL solo por proceso aislado"
    if c["squad_proposal"] != "no":
        assert c["security"]["enabled"], "sin habilitación de seguridad no entra al escuadrón"
        assert c["verdict"] == "usar"
        assert c["integration_mode"] in {"A", "B"}
    if c["integration_mode"] == "D":
        assert c["verdict"] == "descartar" and c["squad_proposal"] == "no"
    if spdx == "NONE":
        assert c["license"]["file"] is None and "R2" in c["security"]["red_alerts"]
    # Aprobación: solo el usuario la cambia (decisiones escritas del 2026-10-19 y 2026-10-20).
    if c["id"] in APPROVED | APPROVED_2:
        day = "2026-10-19" if c["id"] in APPROVED else "2026-10-20"
        assert c["approval"] == {"state": "aprobada", "by": "usuario", "at": day}
        assert c["squad_proposal"] == "propuesto"
    else:
        assert c["approval"] == {"state": "pendiente", "by": None, "at": None}
