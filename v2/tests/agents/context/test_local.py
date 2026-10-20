"""Analizador de contexto con LLM local (Ollama simulado, sin red)."""

import json

import httpx

from eim.agents.context import ContextAgent
from eim.agents.registry import default_registry
from eim.core import NewsItem
from eim.data.providers.claude_context import CachedContextAnalyzer
from eim.data.providers.local_context import LocalContextAnalyzer

GOOD = {"tema": "ETF", "sentimiento": 0.2, "riesgo_evento": "bajo", "fuentes": ["n0"],
        "catalizadores": [{"texto": "Entradas a ETF", "fuente": "n0"}]}
ITEMS = [NewsItem(id=f"n{i}", t=1, title=f"ETH ETF day {i}", source="W") for i in range(5)]


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_respuesta_valida_y_payload_con_esquema_y_datos_delimitados():
    seen = {}

    def h(req):
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"message": {"content": json.dumps(GOOD)}})

    a = LocalContextAnalyzer(client=_client(h), model="m")
    assert a(ITEMS) == GOOD and seen["model"] == "m" and seen["stream"] is False
    assert "<headlines_data>" in seen["messages"][1]["content"] and "properties" in seen["format"]
    r = ContextAgent(analyzer=a).run(__import__("tests.agents.context.test_context",
                                                fromlist=["_snap"])._snap(ITEMS))
    assert r.status in ("ok", "no_data")


def test_servidor_caido_o_salida_rota_es_none():
    def down(req):
        raise httpx.ConnectError("sin servidor")

    assert LocalContextAnalyzer(client=_client(down))(ITEMS) is None
    bad = _client(lambda r: httpx.Response(200, json={"message": {"content": "no es json"}}))
    assert LocalContextAnalyzer(client=bad)(ITEMS) is None


def test_available_mira_el_modelo_descargado():
    ok = _client(lambda r: httpx.Response(200, json={"models": [{"name": "qwen3:4b"}]}))
    assert LocalContextAnalyzer(client=ok, model="qwen3:4b").available()
    assert not LocalContextAnalyzer(client=ok, model="otro").available()


def test_registro_con_opt_in_local(monkeypatch):
    monkeypatch.setenv("EIM_CONTEXT_LLM", "local")
    an = default_registry().get("context").analyzer
    assert isinstance(an, CachedContextAnalyzer) and isinstance(an.inner, LocalContextAnalyzer)


def test_reintenta_una_vez_si_faltan_catalizadores():
    calls = []

    def h(req):
        calls.append(1)
        body = {"tema": "x", "sentimiento": 0, "riesgo_evento": "bajo"} if len(calls) == 1 else GOOD
        return httpx.Response(200, json={"message": {"content": json.dumps(body)}})

    assert LocalContextAnalyzer(client=_client(h))(ITEMS) == GOOD and len(calls) == 2
