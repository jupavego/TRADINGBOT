"""Fixtures sintéticas de la biblioteca digital (sin red)."""

from __future__ import annotations

import pytest

from eim.library.digital.consensus import KnowledgeBase
from eim.library.digital.schema import DigitalRef


def make_ref(id_: str, cat: str, stances: list[dict], markets=("acciones",), year=2010,
             doc_type="articulo", concepts=None, reliability=None) -> DigitalRef:
    cur = {"category": cat, "concepts": concepts or [s["concept"] for s in stances] or ["momentum"],
           "description": "d", "application": "a", "stances": stances, "markets": list(markets)}
    if reliability:
        cur["reliability"] = reliability
    return DigitalRef(
        id=id_, locator={"doi": f"10.1/{id_}", "expect": f"obra {id_}"},
        curated=cur,
        verified={"title": id_.replace("_", " "), "authors": ["Ana Pérez", "Luis Gómez"],
                  "year": year, "venue": "J", "doc_type": doc_type, "url": f"https://doi.org/{id_}",
                  "access": "abierto", "availability": "texto_completo", "source": "openalex",
                  "verified_at": "2026-11-10"})


def st(concept: str, kind: str, level: str = "evidencia_empirica", terms=()) -> dict:
    return {"concept": concept, "kind": kind, "level": level, "summary": f"{kind} {concept}",
            "conditions": "c", "terms": list(terms)}


@pytest.fixture
def kb() -> KnowledgeBase:
    refs = [
        make_ref("mom_a", "E", [st("momentum", "apoya")], markets=("cripto",), year=2020),
        make_ref("mom_b", "E", [st("momentum", "apoya")], markets=("futuros",)),
        make_ref("trend_a", "E", [st("trend_following", "apoya")], markets=("cripto",)),
        make_ref("brk_a", "A", [st("breakout", "apoya")]),
        make_ref("brk_b", "A", [st("breakout", "objeta")]),
        make_ref("ta_no", "A", [st("technical_analysis", "objeta")]),
        make_ref("rev_a", "E", [st("mean_reversion", "condiciona")]),
        make_ref("sl_a", "C", [st("stop_loss", "condiciona")]),
        make_ref("liq_a", "F", [st("liquidation", "apoya", "teoria")], markets=("cripto",)),
        make_ref("kelly", "C", [st("position_sizing", "apoya", "teoria")], markets=()),
    ]
    return KnowledgeBase.build(refs)
