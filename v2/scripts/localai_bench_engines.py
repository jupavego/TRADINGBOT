"""Motores, GPU y marcos (T62): Ollama frente a llama.cpp con el MISMO archivo GGUF.

- `section_engines`: el mismo prompt crudo (plantilla chatml de Qwen3, sin razonamiento) en
  Ollama (`raw`) y en `llama-server` lanzado aquí con `--offline --no-webui` en 127.0.0.1
  (latencia, tokens/s, memoria, errores y salida con esquema JSON en los dos).
- `section_gpu`: Ollama con `num_gpu=0` (solo CPU) frente a su reparto automático, con la VRAM
  usada según `nvidia-smi`.
- `section_frameworks`: Pydantic AI (si está instalado) frente a la validación propia.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import time
from pathlib import Path

import httpx
import localai_bench_llm as L
from localai_bench_score import ClaimList, aggregate, score_claims
from localai_bench_sys import Sampler, gpus, proc_mem_mb, tool_version

CHATML = ("<|im_start|>system\n{system}<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n"
          "<|im_start|>assistant\n<think>\n\n</think>\n\n")


def ollama_models_dir() -> Path:
    return Path(os.environ.get("OLLAMA_MODELS") or Path.home() / ".ollama" / "models")


def gguf_of(model: str) -> Path | None:
    """Ruta del GGUF de un modelo de Ollama (capa `image.model` de su manifiesto)."""
    name, _, tag = model.partition(":")
    lib = ollama_models_dir() / "manifests" / "registry.ollama.ai" / "library"
    man = lib / name / (tag or "latest")
    try:
        layers = json.loads(man.read_text(encoding="utf-8"))["layers"]
    except (OSError, ValueError, KeyError):
        return None
    dig = next((x["digest"] for x in layers if x["mediaType"].endswith("image.model")), None)
    p = ollama_models_dir() / "blobs" / dig.replace(":", "-") if dig else None
    return p if p and p.exists() else None


def llamacpp_exe() -> Path | None:
    """`EIM_LLAMACPP_SERVER` > `EIM_LOCALAI_DIR/llama.cpp/` > el que trae Ollama."""
    cands = [os.environ.get("EIM_LLAMACPP_SERVER")]
    if os.environ.get("EIM_LOCALAI_DIR"):
        cands.append(str(Path(os.environ["EIM_LOCALAI_DIR"]) / "llama.cpp" / "llama-server.exe"))
    if os.environ.get("EIM_OLLAMA_EXE"):
        lib = Path(os.environ["EIM_OLLAMA_EXE"]).parent / "lib" / "ollama"
        cands.append(str(lib / "llama-server.exe"))
    return next((Path(c) for c in cands if c and Path(c).exists()), None)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LlamaServer:
    def __init__(self, exe: Path, gguf: Path, threads: int, ngl: int = 0, ctx: int = 4096) -> None:
        self.port = _free_port()
        self.key = secrets.token_hex(16)  # sin clave, cualquier proceso o web local lo usaría
        self.args = [str(exe), "--model", str(gguf), "--host", "127.0.0.1",
                     "--port", str(self.port), "--offline", "--no-webui", "-c", str(ctx),
                     "-np", "1", "-t", str(threads), "-ngl", str(ngl), "--api-key", self.key]
        self.proc: subprocess.Popen | None = None
        self.load_s: float | None = None

    def __enter__(self) -> LlamaServer:
        t0 = time.perf_counter()
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.proc = subprocess.Popen(self.args, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, creationflags=flags)
        with L._client(5) as c:
            for _ in range(600):
                if self.proc.poll() is not None:
                    raise RuntimeError(f"llama-server terminó con código {self.proc.returncode}")
                try:
                    if c.get(f"http://127.0.0.1:{self.port}/health").status_code == 200:
                        self.load_s = round(time.perf_counter() - t0, 2)
                        return self
                except httpx.HTTPError:
                    pass
                time.sleep(0.5)
        raise RuntimeError("llama-server no respondió en 300 s")

    def __exit__(self, *exc) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(20)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def complete(self, prompt: str, n_predict: int, schema: dict | None = None) -> tuple[str, dict]:
        body = {"prompt": prompt, "n_predict": n_predict, "temperature": 0, "seed": 62,
                "cache_prompt": False}
        if schema is not None:
            body["json_schema"] = schema
        with L._client() as c:
            r = c.post(f"http://127.0.0.1:{self.port}/completion", json=body,
                       headers={"Authorization": f"Bearer {self.key}"})
            r.raise_for_status()
            out = r.json()
        t = out.get("timings", {})
        return out.get("content", ""), {
            "prompt_tokens": t.get("prompt_n"), "prompt_tps": _r(t.get("prompt_per_second")),
            "gen_tokens": t.get("predicted_n"), "gen_tps": _r(t.get("predicted_per_second"))}


def _r(x: float | None) -> float | None:
    return None if x is None else round(x, 2)


def _ollama_raw(model: str, prompt: str, n_predict: int, schema: dict | None = None,
                threads: int | None = None) -> tuple[str, dict]:
    body = {"model": model, "prompt": prompt, "raw": True, "stream": False,
            "options": {"temperature": 0, "seed": 62, "num_ctx": 4096, "num_predict": n_predict,
                        "num_gpu": 0, **({"num_thread": threads} if threads else {})}}
    if schema is not None:
        body["format"] = schema
    with L._client() as c:
        r = c.post(f"{L.HOST}/api/generate", json=body)
        r.raise_for_status()
        out = r.json()
    return out.get("response", ""), L._timings(out)


def _claims_with(gen) -> dict:
    rows = []
    for case in L.cases():
        prompt = CHATML.format(system=L.SYSTEM,
                               user=f"<transcript_data>\n{case['text']}\n</transcript_data>")
        t0 = time.perf_counter()
        try:
            text, _ = gen(prompt)
            got = ClaimList.model_validate_json(text).claims
            rows.append({"id": case["id"], "valid": True, "s": round(time.perf_counter() - t0, 2),
                         **score_claims(got, case["claims"], case["text"])})
        except (httpx.HTTPError, ValueError) as exc:
            rows.append({"id": case["id"], "valid": False, "error": type(exc).__name__,
                         "s": round(time.perf_counter() - t0, 2),
                         **score_claims([], case["claims"], case["text"])})
    return {"valid_rate": round(sum(r["valid"] for r in rows) / len(rows), 3), **aggregate(rows),
            "s_median": sorted(r["s"] for r in rows)[len(rows) // 2], "cases": rows}


def _speed_runs(gen, reps: int) -> dict:
    runs, errors = [], 0
    for _ in range(reps):
        prompt = CHATML.format(system=L.fresh("Responde en español."), user=L.SPEED_PROMPT)
        try:
            runs.append(gen(prompt, 128)[1])
        except httpx.HTTPError:
            errors += 1
    tps = sorted(r["gen_tps"] or 0 for r in runs)
    ptps = sorted(r["prompt_tps"] or 0 for r in runs)
    return {"gen_tps_median": tps[len(tps) // 2] if tps else None,
            "prompt_tps_median": ptps[len(ptps) // 2] if ptps else None,
            "errors": errors, "runs": runs}


def section_engines(model: str = "qwen3:4b", reps: int = 3, threads: int | None = None) -> dict:
    """Los dos motores en CPU (sin GPU) para comparar solo el motor."""
    threads = threads or os.cpu_count() or 4
    gguf, exe = gguf_of(model), llamacpp_exe()
    out = {"model": model, "gguf": str(gguf) if gguf else None, "threads": threads}
    if gguf is None:
        return {**out, "status": f"sin GGUF local de {model} (no descargado en Ollama)"}
    schema = ClaimList.model_json_schema()
    L.unload(model)
    with Sampler(pid_fn=L.runner_pids) as s:
        t0 = time.perf_counter()
        _ollama_raw(model, "Hola", 1, threads=threads)
        load = round(time.perf_counter() - t0, 2)
        sp = _speed_runs(lambda p, n: _ollama_raw(model, p, n, threads=threads), reps)
        cl = _claims_with(lambda p: _ollama_raw(model, p, 400, schema, threads))
    out["ollama"] = {"version": L.version(), "load_s": load, **sp, "claims": cl,
                     "memory": s.result()}
    L.unload(model)
    if exe is None:
        out["llamacpp"] = {"status": "no instalado (EIM_LLAMACPP_SERVER / EIM_LOCALAI_DIR)"}
        return out
    info = {"exe": str(exe), "version": tool_version(str(exe), "--version"),
            "bundled_with_ollama": "ollama" in str(exe).lower()}
    try:
        with LlamaServer(exe, gguf, threads) as srv:
            pid = srv.proc.pid
            with Sampler(pids=[pid]) as s:
                sp = _speed_runs(lambda p, n: srv.complete(p, n), reps)
                cl = _claims_with(lambda p: srv.complete(p, 400, schema))
            peak = proc_mem_mb(pid)
            out["llamacpp"] = {**info, "load_s": srv.load_s, **sp, "claims": cl,
                               "memory": {**s.result(), "process_peak": peak}}
    except RuntimeError as exc:
        out["llamacpp"] = {**info, "status": f"error: {exc}"}
    return out


def section_gpu(model: str = "qwen3:4b", reps: int = 3) -> dict:
    g = gpus()
    out: dict = {"gpus": g}
    if not g:
        return {**out, "status": "sin GPU NVIDIA visible (nvidia-smi)"}
    for label, opts in (("cpu", {"num_gpu": 0}), ("auto", {})):
        r = L.speed(model, reps, options=opts)
        r["vram_used_mb_after"] = [x["used_mb"] for x in gpus()]
        out[label] = {k: r[k] for k in ("load_s", "gen_tps_median", "prompt_tps_median",
                                        "errors", "memory", "vram_used_mb_after")}
    c, a = out["cpu"]["gen_tps_median"], out["auto"]["gen_tps_median"]
    out["speedup_gen"] = round(a / c, 2) if c and a else None
    L.unload(model)
    return out


def section_frameworks(model: str = "qwen3:4b") -> dict:
    """Pydantic AI (solo si está instalado: es un extra opcional) frente a la validación propia."""
    own = L.claims_bench(model)
    out = {"own_validation": {k: own[k] for k in ("valid_rate", "retries", "s_median", "precision",
                                                 "recall", "invented_levels")}}
    try:
        import pydantic_ai
        from pydantic_ai import Agent, NativeOutput
        from pydantic_ai.providers.ollama import OllamaProvider
    except ImportError as exc:
        return {**out, "pydantic_ai": {"status": f"no instalado ({exc.name})"}}
    try:  # 2.x: modelo propio de Ollama; 1.x: el compatible con OpenAI
        from pydantic_ai.models.ollama import OllamaModel as Model
    except ImportError:
        from pydantic_ai.models.openai import OpenAIChatModel as Model
    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
    agent = Agent(Model(model, provider=OllamaProvider(base_url=f"{L.HOST}/v1")),
                  output_type=NativeOutput(ClaimList), system_prompt=L.SYSTEM,
                  retries={"output": 1})  # 2.x: `retries` por categoría (antes output_retries)
    rows = []
    for case in L.cases():
        t0 = time.perf_counter()
        try:
            res = agent.run_sync(f"<transcript_data>\n{case['text']}\n</transcript_data>")
            rows.append({"id": case["id"], "valid": True, "s": round(time.perf_counter() - t0, 2),
                         **score_claims(res.output.claims, case["claims"], case["text"])})
        except Exception as exc:  # noqa: BLE001 — cualquier fallo del marco cuenta como inválido
            rows.append({"id": case["id"], "valid": False, "error": type(exc).__name__,
                         "s": round(time.perf_counter() - t0, 2),
                         **score_claims([], case["claims"], case["text"])})
    L.unload(model)  # Pydantic AI va por /v1 y deja el modelo cargado: no ensuciar lo siguiente
    out["pydantic_ai"] = {"version": pydantic_ai.__version__,
                          "valid_rate": round(sum(r["valid"] for r in rows) / len(rows), 3),
                          "s_median": sorted(r["s"] for r in rows)[len(rows) // 2],
                          **aggregate(rows), "cases": rows}
    return out
