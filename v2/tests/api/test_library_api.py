"""T53: `GET /v2/library/cards/{id}` resuelve título, paráfrasis y cita de la ficha."""
from fastapi import FastAPI

from eim.agents.literature.rules import RULES
from eim.api.library import build_library_router
from tests.local_client import LocalClient


def _client() -> LocalClient:
    app = FastAPI()
    app.include_router(build_library_router())
    return LocalClient(app)


def test_card_resolves_with_citation():
    r = _client().get("/v2/library/cards/nison_engulfing")
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "codificada" and d["title"] and d["claim"]
    ct = d["citations"][0]
    assert ct["author"] == "Steve Nison" and ct["year"] == 2001 and ct["pages"] == [53, 54]
    assert "no evidencia" in d["label"]


def test_every_literature_card_is_served_and_unknown_is_404():
    c = _client()
    assert all(c.get(f"/v2/library/cards/{k}").status_code == 200 for k in RULES)
    assert c.get("/v2/library/cards/no_existe").status_code == 404
