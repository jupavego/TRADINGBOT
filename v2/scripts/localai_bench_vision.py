"""Escenas, OCR y visión-lenguaje sobre los fotogramas sintéticos (T62).

Cada motor se usa solo si está instalado (extras `[video]`/`[localai]` en un entorno aparte);
si falta, la sección lo dice y sigue. Ningún motor descarga nada aquí: RapidOCR y PaddleOCR deben
tener sus modelos ya en disco y los VLM ya descargados en Ollama.
"""

from __future__ import annotations

import base64
import io
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import httpx
import localai_bench_llm as L
from localai_bench_score import norm_asset, norm_timeframe, number_recall
from localai_bench_sys import Sampler, ram_mb
from pydantic import BaseModel, ConfigDict

SECONDS_PER_FRAME = 4


class ChartRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset: str
    timeframe: str | None
    levels: list[float]


def _med(xs: list[float]) -> float | None:
    xs = sorted(xs)
    return round(xs[len(xs) // 2], 3) if xs else None


def tesseract_cmd() -> str | None:
    """Misma detección que la biblioteca (`eim/data/library_extract.py`)."""
    win = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    return os.environ.get("EIM_TESSERACT") or shutil.which("tesseract") or (
        str(win) if win.exists() else None)


def ocr_engines() -> dict:
    """Nombre → (versión, función imagen→texto) de los OCR disponibles."""
    found: dict = {}
    cmd = tesseract_cmd()
    if cmd:
        try:
            import pytesseract
            from PIL import Image
            pytesseract.pytesseract.tesseract_cmd = cmd
            langs = set(pytesseract.get_languages(config=""))
            lang = "+".join(x for x in ("spa", "eng") if x in langs) or "eng"
            found["tesseract"] = (f"{pytesseract.get_tesseract_version()} ({lang})",
                                  lambda p: pytesseract.image_to_string(Image.open(p), lang=lang))
        except Exception as exc:  # noqa: BLE001 — se anota y se sigue
            found["tesseract"] = (f"error: {type(exc).__name__}", None)
    try:
        from rapidocr import RapidOCR  # v3
        eng = RapidOCR()
        found["rapidocr"] = (_ver("rapidocr"), lambda p: " ".join(eng(str(p)).txts or ()))
    except ImportError:
        try:
            from rapidocr_onnxruntime import RapidOCR as R1
            eng1 = R1()
            found["rapidocr"] = (_ver("rapidocr_onnxruntime"),
                                 lambda p: " ".join(r[1] for r in (eng1(str(p))[0] or [])))
        except ImportError:
            pass
    try:
        from paddleocr import PaddleOCR
        pd = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False,
                       use_textline_orientation=False)
        found["paddleocr"] = (_ver("paddleocr"), lambda p: " ".join(
            t for r in pd.predict(str(p)) for t in r.get("rec_texts", [])))
    except ImportError:
        pass
    return found


def _ver(*dists: str) -> str:
    """Versión de la primera distribución instalada (`scenedetect-headless` se llama distinto)."""
    from importlib.metadata import PackageNotFoundError, version
    for dist in dists:
        try:
            return version(dist)
        except PackageNotFoundError:
            continue
    return "?"


def section_ocr(frames: Path, truth: list[dict]) -> dict:
    out: dict = {"frames": len(truth)}
    engines = ocr_engines()
    if not engines:
        return {**out, "status": "ningún OCR instalado (Tesseract, RapidOCR, PaddleOCR)"}
    for name, (ver, fn) in engines.items():
        if fn is None:
            out[name] = {"status": ver}
            continue
        rows, times = [], []
        with Sampler(pids=[os.getpid()]) as s:
            fn(frames / truth[0]["file"])  # calentamiento (carga de modelos)
            for t in truth:
                t0 = time.perf_counter()
                text = fn(frames / t["file"])
                times.append(time.perf_counter() - t0)
                r = number_recall(text, t["numbers"])
                rows.append({"file": t["file"], "low_res": t["low_res"], **r})
        hit = sum(r["found"] for r in rows)
        tot = sum(r["expected"] for r in rows)
        out[name] = {"version": ver, "s_per_frame_median": _med(times),
                     "number_recall": round(hit / tot, 4) if tot else None,
                     "frames_all_numbers_ok": sum(r["found"] == r["expected"] for r in rows),
                     "recall_480p": _recall([r for r in rows if r["low_res"]]),
                     "recall_720p": _recall([r for r in rows if not r["low_res"]]),
                     "memory": s.result(), "rows": rows}
    return out


def _rate(flags: list[bool]) -> float | None:
    return round(sum(flags) / len(flags), 3) if flags else None


def _recall(rows: list[dict]) -> float | None:
    tot = sum(r["expected"] for r in rows)
    return round(sum(r["found"] for r in rows) / tot, 4) if tot else None


def build_video(frames: Path, truth: list[dict], dst: Path) -> Path | None:
    """Video de prueba: cada fotograma 4 s → cortes conocidos cada 4 s."""
    ff = shutil.which("ffmpeg")
    if not ff:
        return None
    lst = dst.with_suffix(".txt")
    body = "".join(f"file '{(frames / t['file']).as_posix()}'\nduration {SECONDS_PER_FRAME}\n"
                   for t in truth)
    last = f"file '{(frames / truth[-1]['file']).as_posix()}'\n"  # concat ignora la última duración
    lst.write_text(body + last, encoding="utf-8")
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-vf", "scale=1280:720,fps=25,format=yuv420p", "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "28", str(dst)], check=True, timeout=600)
    return dst


def _score_cuts(found: list[float], n: int, tol: float = 0.5) -> dict:
    true = [SECONDS_PER_FRAME * i for i in range(1, n)]
    hit = [c for c in true if any(abs(f - c) <= tol for f in found)]
    fp = [f for f in found if not any(abs(f - c) <= tol for c in true)]
    return {"true_cuts": len(true), "found": len(found), "recall": round(len(hit) / len(true), 4),
            "false_positives": len(fp)}


def section_scenes(frames: Path, truth: list[dict], work: Path) -> dict:
    video = build_video(frames, truth, work / "scenes.mp4")
    if video is None:
        return {"status": "ffmpeg no instalado"}
    minutes = len(truth) * SECONDS_PER_FRAME / 60
    out: dict = {"video_min": round(minutes, 2)}
    for thr in (0.3, 0.2, 0.1, 0.05):  # 0,3 es el umbral habitual; la pantalla cambia menos
        t0 = time.perf_counter()
        err = subprocess.run([shutil.which("ffmpeg"), "-hide_banner", "-i", str(video), "-vf",
                              f"select='gt(scene,{thr})',showinfo", "-f", "null", "-"],
                             capture_output=True, text=True, timeout=600).stderr
        cuts = [float(x) for x in re.findall(r"pts_time:([\d.]+)", err)]
        out[f"ffmpeg_scene_{thr}"] = {
            "s_per_video_min": round((time.perf_counter() - t0) / minutes, 3),
            **_score_cuts(cuts, len(truth))}
    try:
        from scenedetect import ContentDetector, detect
    except ImportError:
        out["pyscenedetect"] = {"status": "no instalado"}
        return out
    t0 = time.perf_counter()
    scenes = detect(str(video), ContentDetector())
    out["pyscenedetect"] = {"version": _ver("scenedetect-headless", "scenedetect"),
                            "s_per_video_min": round((time.perf_counter() - t0) / minutes, 3),
                            **_score_cuts([s[0].get_seconds() for s in scenes[1:]], len(truth))}
    return out


VLM_PROMPT = ("Lee este fotograma de un video de trading. Devuelve el activo (BTC, ETH, SOL…), el "
              "marco temporal de las velas (15m, 1h, 4h, 1d, 1w; null si no se ve) y las cifras de "
              "los niveles horizontales o del objetivo marcados (solo números).")


def _image_b64(path: Path, max_side: int | None) -> str:
    """Fotograma en base64, reducido a `max_side` px de lado mayor: el VLM corta la imagen en
    parches y su memoria y su tiempo crecen con la resolución (720p: ~4,9 GB en `juanpablo-cpu`)."""
    if not max_side:
        return base64.b64encode(path.read_bytes()).decode()
    from PIL import Image
    im = Image.open(path).convert("RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def section_vlm(frames: Path, truth: list[dict], wanted: list[str], max_side: int | None = 768,
                limit: int | None = 12, floor_mb: int = 1500) -> dict:
    """`limit` fotogramas repartidos por toda la serie; corta un modelo si la RAM libre del
    sistema baja de `floor_mb` (los servicios de EIM comparten el equipo)."""
    have = L.models()
    out: dict = {}
    if not have and L.version() is None:
        return {"status": "Ollama no responde"}
    sub = truth[::max(1, len(truth) // limit)][:limit] if limit else truth
    for name in wanted:
        if name not in have:
            out[name] = {"status": "no descargado"}
            continue
        L.unload(name)
        rows, times, errors, load, cut = [], [], 0, None, None
        with Sampler(pid_fn=L.runner_pids) as s:
            for t in sub:
                if (free := ram_mb()["avail_mb"]) is not None and free < floor_mb:
                    cut = f"cortado: RAM libre {free} MB < {floor_mb} MB"
                    break
                img = _image_b64(frames / t["file"], max_side)
                msgs = [{"role": "user", "content": VLM_PROMPT, "images": [img]}]
                t0 = time.perf_counter()
                try:
                    txt, tim = L.chat(name, msgs, fmt=ChartRead.model_json_schema(),
                                      options={"num_predict": 200})
                    got = ChartRead.model_validate_json(txt)
                except (httpx.HTTPError, ValueError):
                    errors += 1
                    continue
                load = tim["load_s"] if load is None else load
                times.append(time.perf_counter() - t0)
                lv = number_recall(" ".join(str(x) for x in got.levels), t["levels"], rel=1e-3)
                rows.append({"file": t["file"], "asset_ok": norm_asset(got.asset) == t["asset"],
                             "tf_ok": None if t["timeframe"] is None
                             else norm_timeframe(got.timeframe) == t["timeframe"],
                             "levels_found": lv["found"], "levels_expected": lv["expected"]})
        L.unload(name)
        charts = [r for r in rows if r["tf_ok"] is not None]
        le = sum(r["levels_expected"] for r in rows)
        out[name] = {"meta": have[name], "max_side": max_side, "frames": len(rows), "cut": cut,
                     "load_s": load, "errors": errors,
                     "s_per_frame_median": _med(times[1:] or times),
                     "asset_acc": _rate([r["asset_ok"] for r in rows]),
                     "timeframe_acc": _rate([r["tf_ok"] for r in charts]),
                     "level_recall": round(sum(r["levels_found"] for r in rows) / le, 3)
                     if le else None,
                     "memory": s.result(), "rows": rows}
    return out
