"""Lectura de las respuestas de YouTube (Data API v3 y RSS de canal) → `VideoMeta`.

Sin red. El texto de títulos y descripciones es de terceros: se guarda como dato, nunca se
interpreta como instrucción (T62 §4).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime

from eim.video.models import VideoMeta

_DUR = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")
_NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015",
       "media": "http://search.yahoo.com/mrss/"}
MAX_TEXT = 5000   # la API da hasta 5000 bytes de descripción; se corta por si acaso


def iso_duration_s(text: str | None) -> int | None:
    """`PT1H2M3S` → 3723. `P0D` (directo en curso) y lo ilegible → None."""
    m = _DUR.match(text or "")
    if not m or not any(m.groups()):
        return None
    d, h, mi, s = (int(g or 0) for g in m.groups())
    total = ((d * 24 + h) * 60 + mi) * 60 + s
    return total or None


def rfc3339_ms(text: str) -> int:
    return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1000)


def video_from_api(item: dict) -> VideoMeta | None:
    """Un elemento de `videos.list` (part=snippet,contentDetails,liveStreamingDetails)."""
    sn = item.get("snippet") or {}
    vid, ch, pub = item.get("id"), sn.get("channelId"), sn.get("publishedAt")
    if not (isinstance(vid, str) and ch and pub):
        return None
    broadcast = sn.get("liveBroadcastContent", "none")
    live = broadcast if broadcast in ("live", "upcoming") else (
        "completed" if item.get("liveStreamingDetails") else "none")
    lang = sn.get("defaultAudioLanguage") or sn.get("defaultLanguage")
    return VideoMeta(
        video_id=vid, channel_id=ch, title=str(sn.get("title", ""))[:MAX_TEXT],
        description=str(sn.get("description", ""))[:MAX_TEXT], published_at=rfc3339_ms(pub),
        duration_s=iso_duration_s((item.get("contentDetails") or {}).get("duration")),
        language=lang, live=live, source="youtube_api")


def videos_from_rss(raw: bytes, channel_id: str) -> list[VideoMeta]:
    """Feed Atom de canal (sin duración ni idioma: esos videos no pasan el filtro sin la API).
    Se rechaza cualquier DOCTYPE (entidades externas o expansivas)."""
    if b"<!DOCTYPE" in raw[:2048].upper():
        raise ValueError("RSS con DOCTYPE: rechazado")
    root = ET.fromstring(raw)
    out = []
    for e in root.findall("a:entry", _NS):
        vid = e.findtext("yt:videoId", namespaces=_NS)
        pub = e.findtext("a:published", namespaces=_NS)
        if not vid or not pub:
            continue
        desc = e.findtext("media:group/media:description", default="", namespaces=_NS)
        out.append(VideoMeta(
            video_id=vid, channel_id=e.findtext("yt:channelId", default=channel_id,
                                                namespaces=_NS),
            title=(e.findtext("a:title", default="", namespaces=_NS))[:MAX_TEXT],
            description=desc[:MAX_TEXT], published_at=rfc3339_ms(pub), source="youtube_rss"))
    return out
