"""Banco de pruebas de motores de IA locales (T62): mide en ESTE equipo, con lo instalado.

Desde `v2/` (con el entorno de motores locales si se instalaron extras; ver `docs/OPERACION.md`
§ «Motores locales»):
    python scripts/localai_bench.py [--sections system,llm,engines,gpu,frameworks,scenes,ocr,
        vlm,asr,embeddings] [--llm qwen3:4b,...] [--vlm ...] [--emb ...] [--asr small,...]
        [--audio-dir DIR] [--reps 3]
Escribe `reports/localai/bench_<equipo>.json` y `.md` (fusiona con una corrida previa: las
secciones no pedidas se conservan). Sin red salvo 127.0.0.1: nunca descarga pesos (lo que no
está se anota «no descargado»/«no instalado»). Mide con los servicios de EIM tal como estén y lo
anota: el presupuesto vale para ese estado del equipo.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import localai_bench_sys as S  # noqa: E402
from localai_bench_score import budget  # noqa: E402

ALL = ("system", "llm", "engines", "gpu", "frameworks", "scenes", "ocr", "vlm", "asr", "embeddings")
ASSUME = {"words_per_min": 150, "tokens_per_word": 1.6, "out_tokens_per_1k_in": 60,
          "frames_ocr_per_h": 120, "frames_vlm_per_h": 20, "night_h": 8, "video_min": 20,
          "subs_share": 0.7}  # supuestos declarados; T64 los medirá en la muestra real


def machine() -> str:
    """Misma prioridad que `eim.data.machine` sin importar `eim` (el entorno de motores no lo
    instala): `EIM_MACHINE` > `data/machine_id` > nombre del equipo."""
    raw = os.environ.get("EIM_MACHINE") or ""
    if not raw:
        try:
            raw = (ROOT / "data" / "machine_id").read_text(encoding="utf-8")
        except OSError:
            raw = platform.node()
    return re.sub(r"[^a-z0-9_-]+", "-", raw.strip().lower()).strip("-_")[:40] or "equipo"


def localai_dir() -> Path:
    """Pesos y entorno de motores viven en `EIM_LOCALAI_DIR` (fuera del repo); sin ella, el banco
    solo deja aquí sus fotogramas y su video de prueba (`data/` no se versiona)."""
    d = Path(os.environ.get("EIM_LOCALAI_DIR") or ROOT / "data" / "localai")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe(fn, *a) -> dict:
    """Una sección que falla queda anotada con su error y no tumba las demás."""
    try:
        return fn(*a)
    except Exception as exc:  # noqa: BLE001 — se anota y se sigue con la siguiente sección
        return {"status": f"error: {type(exc).__name__}: {exc}"[:300]}


def run(args) -> dict:
    sec = set(args.sections.split(",")) if args.sections != "all" else set(ALL)
    work = localai_dir() / "bench"
    work.mkdir(parents=True, exist_ok=True)
    res: dict = {"t62_bench": 1, "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    res["system"] = S.system_info(machine())
    llm_models = [m for m in args.llm.split(",") if m]
    if sec & {"llm", "engines", "gpu", "frameworks", "vlm", "embeddings"}:
        import localai_bench_llm as L
        res["ollama"] = {"version": L.version(), "models": L.models()}
    if "llm" in sec:
        res["llm"] = _safe(L.section_llm, llm_models, args.reps)
    if sec & {"engines", "gpu", "frameworks"}:
        import localai_bench_engines as E
        ref = llm_models[0] if llm_models else "qwen3:4b"
        if "engines" in sec:
            res["engines"] = _safe(E.section_engines, ref, args.reps)
        if "gpu" in sec:
            res["gpu"] = _safe(E.section_gpu, ref, args.reps)
        if "frameworks" in sec:
            res["frameworks"] = _safe(E.section_frameworks, ref)
    if sec & {"scenes", "ocr", "vlm"}:
        import localai_bench_frames as F
        import localai_bench_vision as V
        frames = work / "frames"
        truth = F.make_frames(frames, args.frames)
        if "scenes" in sec:
            res["scenes"] = _safe(V.section_scenes, frames, truth, work)
        if "ocr" in sec:
            res["ocr"] = _safe(V.section_ocr, frames, truth)
        if "vlm" in sec:
            res["vlm"] = _safe(V.section_vlm, frames, truth, [m for m in args.vlm.split(",") if m],
                               args.vlm_side or None, args.vlm_frames or None)
    if sec & {"asr", "embeddings"}:
        import localai_bench_audio as A
        if "asr" in sec:
            res["asr"] = _safe(A.section_asr, Path(args.audio_dir) if args.audio_dir else None,
                               [m for m in args.asr.split(",") if m], work)
        if "embeddings" in sec:
            res["embeddings"] = _safe(A.section_embeddings, [m for m in args.emb.split(",") if m])
    res["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    res["system_after"] = {"avail_mb": S.ram_mb()["avail_mb"], "services": S.services()}
    return res


def _best(d: dict | None, key: str, lower: bool = True):
    vals = [v for v in (d or {}).values() if isinstance(v, dict) and v.get(key) is not None]
    if not vals:
        return None
    return (min if lower else max)(vals, key=lambda v: v[key])


def measured(res: dict) -> dict:
    """Lo medido que entra al presupuesto (el mejor motor de cada etapa con lo instalado)."""
    m: dict = {"ram_peak_mb": {}}
    runs = [r for r in (res.get("asr") or {}).get("runs", []) if r.get("rows")]
    if runs:
        best = min(runs, key=lambda r: max(x["rtf"] or 9 for x in r["rows"]))
        m["asr_rtf"] = max(x["rtf"] or 0 for x in best["rows"])
        m["ram_peak_mb"]["asr"] = (best.get("memory") or {}).get("peak_private_mb")
    if (o := _best(res.get("ocr"), "number_recall", lower=False)):  # el que lee, no el más rápido
        m["ocr_s_per_frame"] = o["s_per_frame_median"]
        m["ram_peak_mb"]["ocr"] = o["memory"]["peak_private_mb"]
    if (v := _best(res.get("vlm"), "s_per_frame_median")):
        m["vlm_s_per_frame"] = v["s_per_frame_median"]
        m["ram_peak_mb"]["vlm"] = v["memory"]["peak_private_mb"]
    sc = res.get("scenes") or {}
    cand = [x for x in (sc.get("pyscenedetect"), sc.get("ffmpeg_scene_0.1"))
            if x and "s_per_video_min" in x]
    if cand:
        m["scene_s_per_video_min"] = cand[0]["s_per_video_min"]
    llm = ((res.get("llm") or {}).get("models") or {}).values()
    ok = [v for v in llm if v.get("status") == "ok"]
    if ok:
        b = max(ok, key=lambda v: v["claims"].get("recall") or 0)
        m["llm_model"] = b["meta"]
        m["llm_gen_tps"] = b["speed"]["gen_tps_median"]
        m["llm_prompt_tps"] = b["speed"]["prompt_tps_median"]
        m["ram_peak_mb"]["llm"] = b["speed"]["memory"]["peak_private_mb"]
    return m


def merge(old: dict, new: dict) -> dict:
    out = {**old, **new}
    out["history"] = (old.get("history") or []) + [{"started": new["started"],
                                                    "sections": sorted(set(new) & set(ALL))}]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sections", default="all")
    ap.add_argument("--llm", default="qwen3:4b")
    ap.add_argument("--vlm", default="")
    ap.add_argument("--emb", default="")
    ap.add_argument("--asr", default="small,large-v3-turbo")
    ap.add_argument("--audio-dir", default=None)
    ap.add_argument("--frames", type=int, default=36)
    ap.add_argument("--vlm-side", type=int, default=768, help="lado mayor en px (0 = original)")
    ap.add_argument("--vlm-frames", type=int, default=12, help="fotogramas para el VLM (0 = todos)")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--out", default=str(ROOT / "reports" / "localai"))
    args = ap.parse_args(argv)
    res = run(args)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    js = out / f"bench_{res['system']['machine']}.json"
    old = json.loads(js.read_text(encoding="utf-8")) if js.exists() else {}
    full = merge(old, res)
    full["budget"] = budget(measured(full), ASSUME)
    js.write_text(json.dumps(full, ensure_ascii=False, indent=1), encoding="utf-8")
    from localai_bench_report import render
    (out / js.with_suffix(".md").name).write_text(render(full), encoding="utf-8")
    print(f"escrito {js} y {js.with_suffix('.md').name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
