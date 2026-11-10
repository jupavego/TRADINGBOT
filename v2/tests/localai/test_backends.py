"""Selección de backend por configuración y backends reales con transporte simulado (T63)."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel

from eim.localai import LocalAI
from eim.localai.backends import build_all
from eim.localai.backends.llamacpp import LlamaCppBackend
from eim.localai.backends.ollama import OllamaBackend
from eim.localai.backends.whisper import WhisperBackend
from eim.localai.config import LocalAIConfig, loopback_url
from eim.localai.engines import EngineRefused
from eim.localai.fake import FakeBackend
from eim.localai.health import HealthLog
from eim.localai.resources import ResourceManager

DIGEST = "0edcdef34593" + "a" * 52


class Out(BaseModel):
    tema: str


def _ollama(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _tags(models: list[tuple[str, str]]):
    return {"models": [{"name": n, "digest": d} for n, d in models]}


def test_everything_off_by_default():
    cfg = LocalAIConfig.from_env({})
    assert set(cfg.backends.values()) == {"off"}
    backends, problems = build_all(cfg)
    assert all(b is None for b in backends.values()) and problems == {}


def test_backend_is_chosen_by_config_not_by_caller():
    env = {"EIM_LOCALAI_LLM": "fake", "EIM_LOCALAI_OCR": "rapidocr", "EIM_LOCALAI_ASR": "nope"}
    cfg = LocalAIConfig.from_env(env)
    backends, problems = build_all(cfg)
    assert isinstance(backends["llm"], FakeBackend)
    assert backends["ocr"].engine_id == "rapidocr"       # construido sin importar rapidocr
    assert backends["asr"] is None and "no es un motor válido" in problems["asr"]
    ai = LocalAI(backends, config=cfg, problems=problems, health=HealthLog(None))
    r = ai.asr.transcribe("a.wav", caller="t")
    assert r.outcome == "off" and "no es un motor válido" in r.reason


def test_only_loopback_hosts_are_accepted():
    assert loopback_url("127.0.0.1:11434") == "http://127.0.0.1:11434"
    for bad in ("http://0.0.0.0:11434", "http://192.168.1.5:11434", "https://ollama.com"):
        with pytest.raises(EngineRefused):
            loopback_url(bad)
    cfg = LocalAIConfig.from_env({"EIM_LOCALAI_LLM": "ollama",
                                  "EIM_LOCALAI_OLLAMA_HOST": "http://10.0.0.2:11434"})
    backends, problems = build_all(cfg)
    assert backends["llm"] is None and "bucle local" in problems["llm"]


def test_unlisted_model_is_refused():
    cfg = LocalAIConfig.from_env({"EIM_LOCALAI_LLM": "ollama", "EIM_LOCALAI_LLM_MODEL": "gemma3"})
    backends, problems = build_all(cfg)
    assert backends["llm"] is None and "lista aprobada" in problems["llm"]


def test_ollama_digest_must_match_the_pin():
    ok = OllamaBackend("127.0.0.1:11434", "qwen3:4b-instruct", "llm",
                       client=_ollama(lambda r: httpx.Response(
                           200, json=_tags([("qwen3:4b-instruct", DIGEST)]))))
    assert ok.weights_sha() == f"ollama-manifest:{DIGEST}"
    bad = OllamaBackend("127.0.0.1:11434", "qwen3:4b-instruct", "llm",
                        client=_ollama(lambda r: httpx.Response(
                            200, json=_tags([("qwen3:4b-instruct", "f" * 64)]))))
    with pytest.raises(EngineRefused, match="distinto del fijado"):
        bad.weights_sha()
    missing = OllamaBackend("127.0.0.1:11434", "qwen3:4b-instruct", "llm",
                            client=_ollama(lambda r: httpx.Response(200, json=_tags([]))))
    with pytest.raises(EngineRefused, match="no está descargado"):
        missing.weights_sha()


def test_ollama_end_to_end_through_the_facade():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/tags":
            return httpx.Response(200, json=_tags([("qwen3:4b-instruct", DIGEST)]))
        body = json.loads(req.content)
        seen.append((req.url.path, body))
        if req.url.path == "/api/chat":
            return httpx.Response(200, json={"message": {"content": '{"tema": "halving"}'}})
        return httpx.Response(200, json={})

    b = OllamaBackend("127.0.0.1:11434", "qwen3:4b-instruct", "llm", client=_ollama(handler))
    ai = LocalAI({"llm": b}, config=LocalAIConfig(timeout_s=5, wait_s=5),
                 health=HealthLog(None), resources=ResourceManager(ram_probe=lambda: 16_000.0))
    r = ai.llm.complete("resume", Out, data=["titular"], caller="t")
    assert r.ok and r.data.tema == "halving" and r.provenance.weights_sha.endswith(DIGEST)
    path, body = seen[0]
    assert path == "/api/chat" and body["think"] is False and body["format"]["title"] == "Out"
    assert body["options"]["seed"] == 0 and body["options"]["temperature"] == 0.0
    ai.close()
    assert seen[-1][0] == "/api/generate" and seen[-1][1]["keep_alive"] == 0   # descarga


def test_ollama_down_is_no_data():
    def handler(req):
        raise httpx.ConnectError("rechazada")

    b = OllamaBackend("127.0.0.1:11434", "qwen3:4b-instruct", "llm", client=_ollama(handler))
    ai = LocalAI({"llm": b}, config=LocalAIConfig(timeout_s=5, wait_s=5), health=HealthLog(None),
                 resources=ResourceManager(ram_probe=lambda: 16_000.0))
    r = ai.llm.complete("x", Out, caller="t")
    assert (r.status, r.outcome, r.data) == ("no_data", "down", None) and "Ollama" in r.reason


def test_llamacpp_needs_key_and_verified_gguf(tmp_path):
    with pytest.raises(EngineRefused, match="sin clave"):
        LlamaCppBackend("127.0.0.1:8080", "", str(tmp_path / "x.gguf"))
    import hashlib

    data = b"gguf de prueba"
    blob = tmp_path / f"sha256-{hashlib.sha256(data).hexdigest()}"
    blob.write_bytes(data)
    assert LlamaCppBackend("127.0.0.1:8080", "k", str(blob)).weights_sha() == blob.name[7:]
    other = tmp_path / "modelo.gguf"
    other.write_bytes(data)
    with pytest.raises(EngineRefused, match="sin SHA-256 de referencia"):
        LlamaCppBackend("127.0.0.1:8080", "k", str(other)).weights_sha()
    tampered = tmp_path / f"sha256-{'0' * 64}"
    tampered.write_bytes(data)
    with pytest.raises(EngineRefused, match="distinto del fijado"):
        LlamaCppBackend("127.0.0.1:8080", "k", str(tampered)).weights_sha()


def test_whisper_weights_verified_against_download_metadata(tmp_path):
    import hashlib

    folder = tmp_path / "models" / "faster-whisper" / "small"
    meta = folder / ".cache" / "huggingface" / "download"
    meta.mkdir(parents=True)
    (folder / "model.bin").write_bytes(b"pesos")
    sha = hashlib.sha256(b"pesos").hexdigest()
    (meta / "model.bin.metadata").write_text(f"536b0662abc\n{sha}\n1\n", encoding="utf-8")
    assert WhisperBackend("small", str(tmp_path)).weights_sha() == sha
    (meta / "model.bin.metadata").write_text(f"536b0662abc\n{'1' * 64}\n1\n", encoding="utf-8")
    with pytest.raises(EngineRefused, match="distinto del fijado"):
        WhisperBackend("small", str(tmp_path)).weights_sha()
    (meta / "model.bin.metadata").write_text(f"deadbeef\n{sha}\n1\n", encoding="utf-8")
    with pytest.raises(EngineRefused, match="revisión"):
        WhisperBackend("small", str(tmp_path)).weights_sha()


def test_claude_backend_is_off_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg = LocalAIConfig.from_env({"EIM_LOCALAI_LLM": "claude"})
    backends, problems = build_all(cfg)
    assert backends["llm"] is None and "ANTHROPIC_API_KEY" in problems["llm"]
