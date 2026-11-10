"""Filtro y puntuación de relevancia (T64). Puro: sin red, sin disco, sin reloj propio.

El puntaje es la suma ponderada de tres dimensiones (tema, actualidad, prioridad del canal) y se
entrega siempre con su desglose. Duración, idioma, emisión en vivo y permiso de transcripción
son filtros: no restan puntos, descartan con motivo. Todo descarte lleva uno o más motivos.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal

from eim.video.models import VideoMeta
from eim.video.watchlist import Watchlist

HOUR_MS = 3_600_000
Mode = Literal["vivo", "historico"]

REASONS: dict[str, str] = {
    "futuro": "publicado después de asof (no existía para el sistema)",
    "en_vivo": "emisión en vivo o programada: aún no hay grabación",
    "sin_duracion": "duración desconocida (la fuente no la da): no se puede presupuestar",
    "corto": "más corto que la duración mínima de la lista",
    "largo": "más largo que la duración máxima de la lista",
    "idioma": "idioma fuera de la lista",
    "sin_tema": "ningún tema de la lista en título ni descripción",
    "bajo_umbral": "puntaje por debajo del umbral",
    "sin_permiso": ("canal sin permiso de transcripción: solo metadatos (Términos de YouTube, "
                    "docs/SEGURIDAD.md)"),
    "canal_fuera": "el canal no está en la lista de esta versión",
    "borrado": "el video ya no existe en la fuente (o se hizo privado)",
    "tope_diario": "no cabe en las horas de cómputo de hoy (se reconsidera otro día)",
}


@dataclass(frozen=True)
class Score:
    total: float
    breakdown: dict[str, dict]
    reasons: tuple[str, ...]
    est_compute_s: float | None
    mode: Mode
    notes: tuple[str, ...] = field(default=())

    @property
    def candidate(self) -> bool:
        return not self.reasons


def fold(text: str) -> str:
    """Minúsculas sin tildes y con espacios simples (para comparar palabras clave)."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return " ".join("".join(ch for ch in nfkd if not unicodedata.combining(ch)).split())


def _hits(text: str, keywords: tuple[str, ...]) -> list[str]:
    return [k for k in keywords if re.search(rf"(?<![\w]){re.escape(fold(k))}(?![\w])", text)]


def topic_dim(meta: VideoMeta, wl: Watchlist) -> dict:
    """Título cuenta entero; solo en la descripción, la mitad. Tope 1."""
    title, desc = fold(meta.title), fold(meta.description)
    matched, value = {}, 0.0
    for t in wl.topics:
        in_title, in_desc = _hits(title, t.keywords), _hits(desc, t.keywords)
        if in_title or in_desc:
            factor = 1.0 if in_title else 0.5
            matched[t.name] = {"where": "titulo" if in_title else "descripcion",
                               "keywords": sorted(set(in_title or in_desc)),
                               "points": round(t.weight * factor, 4)}
            value += t.weight * factor
    assets = sorted({t.asset for t in wl.topics if t.name in matched and t.asset})
    return {"value": round(min(1.0, value), 4), "matched": matched, "assets": assets}


def freshness_dim(meta: VideoMeta, wl: Watchlist, asof: int, mode: Mode) -> dict:
    age_h = max(0.0, (asof - meta.published_at) / HOUR_MS)
    if mode == "historico":
        return {"value": 1.0, "age_h": round(age_h, 2),
                "note": "respaldo histórico: la actualidad no penaliza"}
    return {"value": round(0.5 ** (age_h / wl.freshness_half_life_h), 4), "age_h": round(age_h, 2),
            "half_life_h": wl.freshness_half_life_h}


def score(meta: VideoMeta, wl: Watchlist, asof: int, mode: Mode = "vivo") -> Score:
    reasons: list[str] = []
    notes: list[str] = []
    if meta.published_at > asof:
        reasons.append("futuro")
    ch = wl.channel(meta.channel_id)
    if ch is None:
        reasons.append("canal_fuera")
    if meta.live in ("live", "upcoming"):
        reasons.append("en_vivo")
    dur = meta.duration_s
    if dur is None:
        reasons.append("sin_duracion")
    elif dur < wl.duration_min_s:
        reasons.append("corto")
    elif dur > wl.duration_max_s:
        reasons.append("largo")
    lang =(meta.language or "").split("-")[0].lower() or None
    if lang is None and ch and ch.languages:
        lang = ch.languages[0]
        notes.append(f"idioma inferido del canal ({lang})")
    if lang is None:
        notes.append("idioma desconocido: no se filtra")
    elif lang not in wl.languages:
        reasons.append("idioma")

    topic = topic_dim(meta, wl)
    fresh = freshness_dim(meta, wl, asof, mode)
    prio = {"value": round((ch.priority if ch else 0) / 5, 4),
            "priority": ch.priority if ch else None}
    w = wl.weights
    total = round(w.topic * topic["value"] + w.freshness * fresh["value"]
                  + w.priority * prio["value"], 4)
    if topic["value"] == 0:
        reasons.append("sin_tema")
    elif total < wl.threshold:
        reasons.append("bajo_umbral")
    if ch is not None and ch.permission == "ninguno":
        reasons.append("sin_permiso")

    breakdown = {
        "tema": {"weight": w.topic, **topic},
        "actualidad": {"weight": w.freshness, **fresh},
        "prioridad": {"weight": w.priority, **prio},
        "filtros": {"duration_s": dur, "language": lang, "live": meta.live,
                    "permission": ch.permission if ch else None},
        "threshold": wl.threshold,
    }
    est = None if dur is None else round(dur * wl.budget.compute_ratio, 1)
    return Score(total, breakdown, tuple(reasons), est, mode, tuple(notes))


@dataclass(frozen=True)
class Candidate:
    video_id: str
    total: float
    published_at: int
    est_compute_s: float


def admit(cands: list[Candidate], used_s: float, wl: Watchlist) -> tuple[list[str], list[str]]:
    """Reparte las horas de cómputo del día: mejor puntaje primero (desempate: más reciente, id).
    Un video que no cabe se salta y se prueba el siguiente; nunca se pasa del tope.
    Devuelve (admitidos, fuera del tope)."""
    cap = wl.budget.compute_hours_per_day * 3600
    left = max(0.0, cap - used_s)
    inside, outside = [], []
    for c in sorted(cands, key=lambda c: (-c.total, -c.published_at, c.video_id)):
        if c.est_compute_s <= left:
            inside.append(c.video_id)
            left -= c.est_compute_s
        else:
            outside.append(c.video_id)
    return inside, outside
