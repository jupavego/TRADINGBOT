"""Informe Markdown del banco de motores locales (T62) a partir del JSON (sin cálculos nuevos)."""

from __future__ import annotations


def _v(x, suf: str = "") -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        x = f"{x:.3g}" if abs(x) < 10 else f"{x:,.1f}"
    return f"{x}{suf}"


def _pct(x) -> str:
    return "—" if x is None else f"{100 * x:.0f} %"


def _table(head: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(c if isinstance(c, str) else _v(c) for c in r) + " |" for r in rows]
    return out + [""]


def _mem(d: dict | None) -> tuple:
    d = d or {}
    return d.get("peak_private_mb"), d.get("min_avail_mb")


def _status(name: str, d) -> list[str]:
    return [f"_{name}: {d['status']}_", ""] if isinstance(d, dict) and "status" in d else []


def _na(name: str, d: dict, width: int) -> list:
    return [name, d["status"]] + ["—"] * width


def _system(s: dict, after: dict | None) -> list[str]:
    g = "; ".join(f"{x['name']} {x['vram_mb']} MB (cc {x['compute_cap']}, driver {x['driver']})"
                  for x in s.get("gpus", [])) or "ninguna NVIDIA visible"
    svc = ", ".join(f"{k} ({v['ws_mb']} MB)"
                    for k, v in (s.get("services") or {}).items()) or "ninguno"
    return [f"- Equipo `{s['machine']}`: {s['cpu']}, {s['threads']} hilos, RAM "
            f"{_v(s['total_mb'])} MB (libre al empezar {_v(s['avail_mb'])} MB; al terminar "
            f"{_v((after or {}).get('avail_mb'))} MB). {s['os']}, Python {s['python']}.",
            f"- GPU: {g}. ffmpeg: {s.get('ffmpeg') or 'no'}.",
            f"- Servicios en marcha al medir: {svc}.", ""]


def _llm(llm: dict) -> list[str]:
    out = [f"## LLM de texto (Ollama {_v(llm.get('version'))})", ""] + _status("LLM", llm)
    rows = []
    for name, m in (llm.get("models") or {}).items():
        if m.get("status") != "ok":
            rows.append(_na(name, m, 10))
            continue
        sp, cl = m["speed"], m["claims"]
        rows.append([name, m["meta"].get("quantization_level"), sp["load_s"],
                     sp["prompt_tps_median"], sp["gen_tps_median"], *_mem(sp["memory"]),
                     _pct(cl["valid_rate"]), _pct(cl["precision"]), _pct(cl["recall"]),
                     cl["invented_levels"], cl["s_median"]])
    return out + _table(["Modelo", "Cuant.", "Carga s", "Prompt tok/s", "Gen tok/s", "Pico MB",
                         "RAM libre mín. MB", "JSON válido", "Precisión", "Recall",
                         "Niveles inventados", "s/caso"], rows)


def _engines(e: dict) -> list[str]:
    out = [f"## Motores: Ollama frente a llama.cpp (`{e['model']}`, CPU, "
           f"{e.get('threads')} hilos)", ""] + _status("Motores", e)
    rows = []
    for k in ("ollama", "llamacpp"):
        d = e.get(k) or {}
        if "status" in d:
            rows.append(_na(k, d, 8))
        elif d:
            cl = d.get("claims") or {}
            rows.append([k, d.get("version"), d.get("load_s"), d.get("prompt_tps_median"),
                         d.get("gen_tps_median"), _mem(d.get("memory"))[0], d.get("errors"),
                         _pct(cl.get("valid_rate")), _pct(cl.get("precision")),
                         _pct(cl.get("recall"))])
    return out + _table(["Motor", "Versión", "Carga s", "Prompt tok/s", "Gen tok/s", "Pico MB",
                         "Errores", "JSON válido", "Precisión", "Recall"], rows)


def _gpu(g: dict) -> list[str]:
    out = ["## GPU", ""] + _status("GPU", g)
    rows = [[k, g[k]["gen_tps_median"], g[k]["prompt_tps_median"], g[k]["load_s"],
             ", ".join(str(x) for x in g[k]["vram_used_mb_after"])]
            for k in ("cpu", "auto") if k in g]
    if rows:
        out += _table(["Ollama", "Gen tok/s", "Prompt tok/s", "Carga s", "VRAM usada MB"], rows)
        out += [f"Aceleración de generación con GPU: ×{_v(g.get('speedup_gen'))}.", ""]
    return out


def _frameworks(f: dict) -> list[str]:
    own, p = f["own_validation"], f.get("pydantic_ai") or {}
    rows = [["validación propia", _pct(own["valid_rate"]), _pct(own["precision"]),
             _pct(own["recall"]), own["s_median"]],
            ["Pydantic AI " + str(p.get("version", "")),
             _pct(p["valid_rate"]) if "valid_rate" in p else p.get("status"),
             _pct(p.get("precision")), _pct(p.get("recall")), p.get("s_median")]]
    return ["## Marcos: salida estructurada", ""] + _table(
        ["Vía", "JSON válido", "Precisión", "Recall", "s/caso"], rows)


def _scenes(sc: dict) -> list[str]:
    out = [f"## Escenas (video sintético de {_v(sc.get('video_min'))} min, corte cada 4 s)", ""]
    rows = [_na(k, d, 3) if "status" in d else
            [k, d.get("version", "—"), d.get("s_per_video_min"), _pct(d.get("recall")),
             d.get("false_positives")] for k, d in sc.items() if isinstance(d, dict)]
    return out + _status("Escenas", sc) + _table(
        ["Detector", "Versión", "s por min de video", "Cortes hallados", "Falsos +"], rows)


def _ocr(o: dict) -> list[str]:
    out = [f"## OCR ({o.get('frames')} fotogramas sintéticos con cifras conocidas)", ""]
    rows = [_na(k, d, 6) if "status" in d else
            [k, d.get("version"), d.get("s_per_frame_median"), _pct(d.get("number_recall")),
             _pct(d.get("recall_720p")), _pct(d.get("recall_480p")),
             d.get("frames_all_numbers_ok"), _mem(d.get("memory"))[0]]
            for k, d in o.items() if isinstance(d, dict)]
    return out + _status("OCR", o) + _table(
        ["Motor", "Versión", "s/fotograma", "Cifras", "720p", "480p", "Fotogramas completos",
         "Pico MB"], rows)


def _vlm(v: dict) -> list[str]:
    rows = [_na(k, d, 9) if "status" in d else
            [k, d.get("max_side") or "original", d.get("frames"), d.get("load_s"),
             d.get("s_per_frame_median"), _pct(d.get("asset_acc")),
             _pct(d.get("timeframe_acc")), _pct(d.get("level_recall")),
             _mem(d.get("memory"))[0], _mem(d.get("memory"))[1], d.get("errors")]
            for k, d in v.items() if isinstance(d, dict)]
    cuts = [f"- {k}: {d['cut']}." for k, d in v.items() if isinstance(d, dict) and d.get("cut")]
    return ["## Visión-lenguaje (subconjunto de los mismos fotogramas)", ""] + _status(
        "VLM", v) + _table(["Modelo", "Lado px", "Fotogramas", "Carga s", "s/fotograma",
                            "Activo", "Marco", "Niveles", "Pico MB", "RAM libre mín. MB",
                            "Errores"], rows) + cuts


def _asr(a: dict) -> list[str]:
    rows = []
    for x in a.get("runs", []):
        if not x.get("rows"):
            rows.append([str(x.get("model")), x.get("status", "error")] + ["—"] * 4)
            continue
        rows.append([x.get("engine"), x.get("model"), x.get("compute", "—"),
                     "; ".join(f"{y['lang']} ×{_v(y['rtf'])}" for y in x["rows"]),
                     "; ".join(f"{y['lang']} {_pct(y['wer'])}" for y in x["rows"]),
                     (x.get("memory") or {}).get("peak_private_mb")])
    return ["## ASR", ""] + _status("ASR", a) + _table(
        ["Motor", "Modelo", "Cómputo", "Factor de tiempo real", "WER", "Pico MB"], rows)


def _emb(em: dict) -> list[str]:
    rows = [_na(k, d, 3) if "status" in d else
            [k, d.get("dims"), d.get("s_per_100_texts"), d.get("first_batch_s"),
             _mem(d.get("memory"))[0]] for k, d in em.items()]
    return ["## Embeddings (calidad: T71)", ""] + _table(
        ["Modelo", "Dim.", "s/100 textos", "Primer lote s", "Pico MB"], rows)


def _budget(b: dict) -> list[str]:
    a = b["assumptions"]
    out = ["## Presupuesto de cómputo (derivado)", "",
           "Horas de cómputo por hora de video, una etapa a la vez (sin solaparse):", ""]
    out += _table(["Etapa", "h/h de video", "Origen"],
                  [[k, d["value"], d["source"]] for k, d in b["stages_h_per_video_h"].items()])
    caps = ", ".join(f"{k} {_v(d['value'])}" for k, d in b["ram_cap_mb"].items()) or "—"
    no_vlm = (b.get("videos_per_night_no_vlm") or {}).get("value")
    return out + [
        f"- Con subtítulos (sin ASR): {_v(b['h_per_video_h_with_subs']['value'])} h/h · sin "
        f"subtítulos: {_v(b['h_per_video_h_without_subs']['value'])} h/h.",
        f"- Videos por noche ({a['night_h']} h, videos de {a['video_min']} min, "
        f"{_pct(a['subs_share'])} con subtítulos): **{_v(b['videos_per_night']['value'])}**; "
        f"sin VLM (solo OCR + LLM): **{_v(no_vlm)}**.",
        f"- Tope de RAM por etapa (pico medido, MB): {caps}.",
        f"- Supuestos (no medidos; T64 los mide en la muestra real): `{a}`.",
        "- Etapas sin medir (el presupuesto las omite): "
        f"{', '.join(b['incomplete']) or 'ninguna'}.",
        ""]


SECTIONS = (("llm", _llm), ("engines", _engines), ("gpu", _gpu), ("frameworks", _frameworks),
            ("scenes", _scenes), ("ocr", _ocr), ("vlm", _vlm), ("asr", _asr),
            ("embeddings", _emb), ("budget", _budget))


def render(r: dict) -> str:
    out = [f"# Banco de motores locales (T62) — `{r['system']['machine']}`", "",
           f"Última corrida {r['started']} → {r['finished']}. Todo medido en este equipo con "
           "`scripts/localai_bench.py`; «—» = no medido. Memoria = pico de memoria privada de "
           "los procesos del motor; «RAM libre mín.» = la del sistema durante la etapa, con los "
           "servicios de abajo en marcha.", ""]
    out += _system(r["system"], r.get("system_after"))
    for key, fn in SECTIONS:
        d = r.get(key)
        if isinstance(d, dict) and str(d.get("status", "")).startswith("error"):
            out += [f"## Sección `{key}`", "", f"_Falló: {d['status']}_", ""]  # ver _safe
        elif d:
            out += fn(d)
    return "\n".join(out)
