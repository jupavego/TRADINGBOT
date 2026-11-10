"""Contratos del catálogo de video (T64): metadatos de un video, sin contenido."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

LiveState = Literal["none", "live", "upcoming", "completed"]
"""`none` grabado · `live` emitiendo · `upcoming` programado · `completed` directo ya grabado."""
Source = Literal["youtube_api", "youtube_rss"]


class VideoMeta(BaseModel):
    """Metadatos tal como los dio la fuente; `published_at` en ms UTC."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    video_id: str
    channel_id: str
    title: str
    description: str = ""
    published_at: int
    duration_s: int | None = None
    language: str | None = None
    live: LiveState = "none"
    source: Source

    def content_key(self) -> tuple:
        """Lo que, si cambia, crea una fila nueva en el catálogo (título editado, etc.)."""
        return (self.channel_id, self.title, self.description, self.published_at,
                self.duration_s, self.language, self.live)
