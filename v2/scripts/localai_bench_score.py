"""Puntuación pura del banco de motores locales (T62): sin red, sin disco, sin dependencias nuevas.

- `numbers_in`/`number_recall`: cifras en texto de OCR o de un modelo, con «61.250» (es) y
  «61,250» (en) leídos de las dos formas; una cifra esperada cuenta si alguna lectura coincide.
- `wer`: tasa de error por palabras (Levenshtein sobre palabras normalizadas).
- `score_claims`: afirmaciones propuestas por un LLM frente a las esperadas (activo, dirección,
  nivel ±0,5 %, segundo ±10 s) y cuántos niveles «inventados» no aparecen en la transcripción.
- `budget`: presupuesto de cómputo derivado de lo medido; cada cifra dice si es medida o supuesta.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_NUM = re.compile(r"(?<![\w.,])[-+]?\d{1,3}(?:[.,  ]\d{3})+(?:[.,]\d+)?(?![\w])"
                  r"|(?<![\w.,])[-+]?\d+(?:[.,]\d+)?(?![\w])")
ASSETS = {"BTC": ("btc", "btcusdt", "bitcoin", "xbt"),
          "ETH": ("eth", "ethusdt", "ether", "ethereum"),
          "SOL": ("sol", "solusdt", "solana"), "SPX": ("spx", "s&p", "s&p500", "sp500")}


class Claim(BaseModel):
    """Afirmación verificable; el esquema JSON de `ClaimList` es el `format` pedido al motor."""
    model_config = ConfigDict(extra="forbid")
    asset: str = Field(description="Activo: BTC, ETH, SOL…")
    direction: Literal["up", "down"] = Field(description="up = sube, down = baja")
    level: float | None = Field(default=None, description="Nivel de precio citado, si lo hay")
    horizon: str | None = Field(default=None, description="Plazo citado: 1d, 1w, 1m… o null")
    second: int | None = Field(default=None, description="Segundo de la marca [mm:ss] previa")


class ClaimList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claims: list[Claim]


def _readings(tok: str) -> set[float]:
    """Lecturas posibles de una cifra: separador de miles «.» o «,» y decimal el otro."""
    t = tok.replace(" ", "").replace(" ", "")
    out: set[float] = set()
    for thou, dec in ((".", ","), (",", ".")):
        s = t.replace(thou, "").replace(dec, ".")
        try:
            out.add(float(s))
        except ValueError:
            pass
    try:
        out.add(float(t.replace(",", ".")))
    except ValueError:
        pass
    return out


def numbers_in(text: str) -> set[float]:
    found: set[float] = set()
    for m in _NUM.finditer(text or ""):
        found |= _readings(m.group(0))
    return found


def _close(a: float, b: float, rel: float) -> bool:
    return abs(a - b) <= max(rel * abs(b), 1e-9)


def number_recall(text: str, expected: list[float], rel: float = 1e-9) -> dict:
    got = numbers_in(text)
    hit = [e for e in expected if any(_close(g, e, rel) for g in got)]
    return {"expected": len(expected), "found": len(hit),
            "recall": round(len(hit) / len(expected), 4) if expected else None,
            "missing": [e for e in expected if e not in hit]}


def _norm_words(text: str) -> list[str]:
    t = unicodedata.normalize("NFC", (text or "").lower())
    t = re.sub(r"(?<=\d)[.,](?=\d)", "", t)  # 61.250 / 61,250 / 3,5 → una sola palabra
    t = re.sub(r"[^\w\s%$]", " ", t)
    return t.split()


def wer(reference: str, hypothesis: str) -> float | None:
    ref, hyp = _norm_words(reference), _norm_words(hypothesis)
    if not ref:
        return None
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return round(prev[-1] / len(ref), 4)


def norm_asset(raw: str | None) -> str:
    s = re.sub(r"[\s/_-]", "", (raw or "").lower())
    for key, names in ASSETS.items():
        if s in names or any(s.startswith(n) for n in names if len(n) > 3):
            return key
    return s.upper()


def norm_timeframe(raw: str | None) -> str | None:
    s = re.sub(r"\s", "", (raw or "").lower())
    if not s:
        return None
    s = (s.replace("horas", "h").replace("hora", "h").replace("hours", "h").replace("hour", "h")
          .replace("min", "m").replace("diario", "1d").replace("daily", "1d")
          .replace("semanal", "1w").replace("weekly", "1w"))
    m = re.fullmatch(r"(\d+)?([mhdw])", s)
    return f"{m.group(1) or '1'}{m.group(2)}" if m else s


def _match(p: Claim, e: dict, lvl_rel: float, sec_tol: int) -> bool:
    if norm_asset(p.asset) != norm_asset(e["asset"]) or p.direction != e["direction"]:
        return False
    if (e.get("level") is None) != (p.level is None):
        return False
    if e.get("level") is not None and not _close(p.level, e["level"], lvl_rel):
        return False
    if e.get("second") is not None and p.second is not None:
        return abs(p.second - e["second"]) <= sec_tol
    return True


def score_claims(pred: list[Claim], expected: list[dict], transcript: str,
                 lvl_rel: float = 0.005, sec_tol: int = 10) -> dict:
    """Emparejamiento voraz 1 a 1; «inventado» = nivel que no está en el texto (lo que un
    verificador determinista de T67 descartaría)."""
    free = list(range(len(expected)))
    tp = 0
    for p in pred:
        j = next((k for k in free if _match(p, expected[k], lvl_rel, sec_tol)), None)
        if j is not None:
            free.remove(j)
            tp += 1
    nums = numbers_in(transcript)
    invented = sum(1 for p in pred if p.level is not None
                   and not any(_close(n, p.level, 1e-6) for n in nums))
    prec = tp / len(pred) if pred else (1.0 if not expected else 0.0)
    rec = tp / len(expected) if expected else (1.0 if not pred else 0.0)
    return {"tp": tp, "pred": len(pred), "expected": len(expected), "precision": round(prec, 4),
            "recall": round(rec, 4), "invented_levels": invented}


def aggregate(rows: list[dict]) -> dict:
    tp, pr, ex = (sum(r[k] for r in rows) for k in ("tp", "pred", "expected"))
    return {"cases": len(rows), "tp": tp, "pred": pr, "expected": ex,
            "precision": round(tp / pr, 4) if pr else None,
            "recall": round(tp / ex, 4) if ex else None,
            "invented_levels": sum(r["invented_levels"] for r in rows)}


def _fig(value, source: str) -> dict:
    return {"value": None if value is None else round(value, 3), "source": source}


def budget(m: dict, a: dict) -> dict:
    """Horas de cómputo por hora de video y videos/día de la cola nocturna, una etapa a la vez.

    `m` (medido): `asr_rtf`, `ocr_s_per_frame`, `vlm_s_per_frame`, `llm_prompt_tps`,
    `llm_gen_tps`, `scene_s_per_video_min` y `ram_peak_mb` por etapa; cualquiera puede faltar.
    `a` (supuesto, declarado): `words_per_min`, `tokens_per_word`, `frames_ocr_per_h`,
    `frames_vlm_per_h`, `out_tokens_per_1k_in`, `night_h`, `video_min`, `subs_share`.
    """
    words_h = a["words_per_min"] * 60
    tok_in = words_h * a["tokens_per_word"]
    tok_out = tok_in / 1000 * a["out_tokens_per_1k_in"]
    stages = {
        "asr_h": m.get("asr_rtf"),
        "scenes_h": None if m.get("scene_s_per_video_min") is None
        else m["scene_s_per_video_min"] * 60 / 3600,
        "ocr_h": None if m.get("ocr_s_per_frame") is None
        else m["ocr_s_per_frame"] * a["frames_ocr_per_h"] / 3600,
        "vlm_h": None if m.get("vlm_s_per_frame") is None
        else m["vlm_s_per_frame"] * a["frames_vlm_per_h"] / 3600,
        "llm_h": None if not (m.get("llm_prompt_tps") and m.get("llm_gen_tps"))
        else (tok_in / m["llm_prompt_tps"] + tok_out / m["llm_gen_tps"]) / 3600,
    }
    missing = [k for k, v in stages.items() if v is None]
    src = "derivado" if not missing else "derivado parcial (sin " + ", ".join(missing) + ")"
    def night(skip: str = "") -> tuple[float, float, float | None]:
        rest = sum(v for k, v in stages.items() if v is not None and k not in ("asr_h", skip))
        ws, wo = rest, rest + (stages["asr_h"] or 0.0)  # con subtítulos no hay ASR (T65)
        per_video_h = (a["subs_share"] * ws + (1 - a["subs_share"]) * wo) * a["video_min"] / 60
        return ws, wo, a["night_h"] / per_video_h if per_video_h else None

    if len(missing) == len(stages):
        with_subs = without = nights = nights_no_vlm = None
    else:
        with_subs, without, nights = night()
        nights_no_vlm = night("vlm_h")[2]  # el VLM es opcional (puede no caber en RAM)
    return {
        "stages_h_per_video_h": {k: _fig(v, "medido" if v is not None else "sin medir")
                                 for k, v in stages.items()},
        "h_per_video_h_with_subs": _fig(with_subs, src),
        "h_per_video_h_without_subs": _fig(without, src),
        "videos_per_night": _fig(nights, src),
        "videos_per_night_no_vlm": _fig(nights_no_vlm, src),
        "ram_cap_mb": {k: _fig(v, "medido") for k, v in (m.get("ram_peak_mb") or {}).items()},
        "assumptions": a, "incomplete": missing,
    }
