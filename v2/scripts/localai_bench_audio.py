"""ASR y embeddings (T62).

ASR: muestras en `--audio-dir` con `manifest.json` = `[{"file", "lang", "ref"?, "ref_seconds"?}]`
(`ref` = transcripción corregida a mano de los primeros `ref_seconds`, por defecto 180). Cada
modelo de faster-whisper corre en un proceso hijo (este mismo archivo, `asr-one`) para medir su
pico de memoria sin arrastrar el anterior; `local_files_only`: los pesos se descargan antes, aparte.
whisper.cpp se mide si `EIM_WHISPERCPP` (o `EIM_LOCALAI_DIR/whisper.cpp/whisper-cli.exe`) existe.
Embeddings: por Ollama (`/api/embed`) con los modelos ya descargados; la calidad la mide T71.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import localai_bench_llm as L
from localai_bench_score import wer
from localai_bench_sys import Sampler, proc_mem_mb


def _duration(path: Path) -> float | None:
    probe = shutil.which("ffprobe")
    if not probe:
        return None
    out = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of",
                          "default=nw=1:nk=1", str(path)],
                         capture_output=True, text=True, timeout=60)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return None


def _manifest(audio_dir: Path) -> list[dict]:
    rows = json.loads((audio_dir / "manifest.json").read_text(encoding="utf-8"))
    for r in rows:
        r["path"] = str(audio_dir / r["file"])
        r["seconds"] = _duration(Path(r["path"]))
        if r.get("ref"):
            r["ref_text"] = (audio_dir / r["ref"]).read_text(encoding="utf-8")
    return rows


def _score(sample: dict, segments: list[tuple[float, str]], proc_s: float) -> dict:
    lim = sample.get("ref_seconds", 180)
    hyp = " ".join(t for s, t in segments if s < lim)
    return {"file": sample["file"], "lang": sample["lang"], "audio_s": sample["seconds"],
            "proc_s": round(proc_s, 1),
            "rtf": round(proc_s / sample["seconds"], 3) if sample["seconds"] else None,
            "wer": wer(sample["ref_text"], hyp) if sample.get("ref_text") else None}


def _revision(local: Path) -> str | None:
    """Commit de HF con que `snapshot_download(local_dir=...)` bajó `model.bin` (1.ª línea)."""
    meta = local / ".cache" / "huggingface" / "download" / "model.bin.metadata"
    return meta.read_text(encoding="utf-8").splitlines()[0] if meta.exists() else None


def asr_one(model: str, compute: str, beam: int, samples: list[dict], models_dir: str) -> dict:
    """Proceso hijo: un modelo de faster-whisper sobre todas las muestras. Si `models_dir/<model>`
    tiene `model.bin` (pesos bajados aparte con revisión fijada) se usa esa carpeta y no el alias,
    cuyo repo puede cambiar de dueño (auditoría, alerta 11)."""
    from faster_whisper import WhisperModel
    from faster_whisper import __version__ as fw_ver
    local = Path(models_dir) / model
    src = str(local) if (local / "model.bin").exists() else model
    t0 = time.perf_counter()
    m = WhisperModel(src, device="cpu", compute_type=compute, cpu_threads=os.cpu_count() or 4,
                     download_root=models_dir, local_files_only=True)
    load = time.perf_counter() - t0
    rows = []
    for s in samples:
        t0 = time.perf_counter()
        segs, _ = m.transcribe(s["path"], language=s["lang"], beam_size=beam, vad_filter=True)
        segs = [(x.start, x.text) for x in segs]  # el generador transcribe al recorrerlo
        rows.append(_score(s, segs, time.perf_counter() - t0))
    return {"engine": "faster-whisper", "version": fw_ver, "model": model, "compute": compute,
            "revision": _revision(local), "beam": beam, "load_s": round(load, 2), "rows": rows,
            "memory": proc_mem_mb(os.getpid())}


def _whispercpp_exe() -> Path | None:
    c = os.environ.get("EIM_WHISPERCPP") or (
        str(Path(os.environ["EIM_LOCALAI_DIR"]) / "whisper.cpp" / "whisper-cli.exe")
        if os.environ.get("EIM_LOCALAI_DIR") else None)
    return Path(c) if c and Path(c).exists() else None


def whispercpp(exe: Path, model: Path, samples: list[dict], work: Path) -> dict:
    rows, peak = [], 0
    for s in samples:
        wav = work / (Path(s["file"]).stem + "_16k.wav")
        subprocess.run([shutil.which("ffmpeg"), "-y", "-loglevel", "error", "-i", s["path"],
                        "-ar", "16000", "-ac", "1", str(wav)], check=True, timeout=600)
        stem = work / Path(s["file"]).stem
        t0 = time.perf_counter()
        p = subprocess.Popen([str(exe), "-m", str(model), "-f", str(wav), "-l", s["lang"],
                              "-t", str(os.cpu_count() or 4), "-oj", "-of", str(stem), "-np"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with Sampler(pids=[p.pid]) as smp:
            p.wait(timeout=7200)
        peak = max(peak, smp.result()["peak_private_mb"])
        js = json.loads(stem.with_suffix(".json").read_text(encoding="utf-8"))
        segs = [(x["offsets"]["from"] / 1000, x["text"]) for x in js.get("transcription", [])]
        rows.append(_score(s, segs, time.perf_counter() - t0))
    return {"engine": "whisper.cpp", "model": model.name, "rows": rows,
            "memory": {"peak_private_mb": peak}}


def section_asr(audio_dir: Path | None, fw_models: list[str], work: Path,
                compute: str = "int8", beam: int = 1) -> dict:
    if audio_dir is None or not (audio_dir / "manifest.json").exists():
        return {"status": "sin muestras de audio (--audio-dir con manifest.json)"}
    samples = _manifest(audio_dir)
    out: dict = {"samples": [{k: s.get(k) for k in ("file", "lang", "seconds", "ref")}
                             for s in samples], "runs": []}
    models_dir = str(Path(os.environ.get("EIM_LOCALAI_DIR") or work) / "models" / "faster-whisper")
    try:
        import faster_whisper  # noqa: F401
        have_fw = True
    except ImportError:
        have_fw = False
        out["faster_whisper"] = "no instalado"
    for name in fw_models if have_fw else []:
        job = work / f"asr_{name.replace('/', '_')}.json"
        cmd = [sys.executable, __file__, "asr-one", name, compute, str(beam), str(audio_dir),
               models_dir, str(job)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=4 * 3600)
        out["runs"].append(json.loads(job.read_text(encoding="utf-8")) if job.exists() else
                           {"model": name, "status": "error", "stderr": r.stderr[-600:]})
    exe = _whispercpp_exe()
    if exe:
        for mdl in sorted(exe.parent.glob("models/ggml-*.bin")):
            out["runs"].append(whispercpp(exe, mdl, samples, work))
    else:
        out["whisper_cpp"] = "no instalado"
    return out


def section_embeddings(wanted: list[str], n: int = 200) -> dict:
    texts = [c["text"] for c in L.cases()]
    texts = (texts * (n // len(texts) + 1))[:n]
    have, out = L.models(), {}
    for name in wanted:
        if name not in have:
            out[name] = {"status": "no descargado"}
            continue
        L.unload(name)
        times, dims = [], None
        with Sampler(pid_fn=L.runner_pids) as s, L._client() as c:
            for i in range(0, n, 50):
                t0 = time.perf_counter()
                r = c.post(f"{L.HOST}/api/embed", json={"model": name, "input": texts[i:i + 50]})
                r.raise_for_status()
                times.append(time.perf_counter() - t0)
                dims = len(r.json()["embeddings"][0])
        L.unload(name)
        warm = times[1:] or times
        out[name] = {"meta": have[name], "dims": dims, "first_batch_s": round(times[0], 2),
                     "s_per_100_texts": round(sum(warm) / (len(warm) * 50) * 100, 3),
                     "memory": s.result()}
    return out


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "asr-one":
    _, _, mdl, comp, bm, adir, mdir, dst = sys.argv
    try:
        res = asr_one(mdl, comp, int(bm), _manifest(Path(adir)), mdir)
    except Exception as exc:  # noqa: BLE001 — el padre lo anota como error del modelo
        res = {"model": mdl, "status": f"error: {type(exc).__name__}: {exc}"[:400]}
    Path(dst).write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
