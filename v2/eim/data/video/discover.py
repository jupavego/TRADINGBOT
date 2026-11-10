"""Descubrimiento en YouTube (T64): solo metadatos, nada se descarga.

- **Data API v3** (fuente principal, postura T62): `channels.list` → lista de subidas,
  `playlistItems.list` (50 por página) → ids, `videos.list` (50 por llamada) → metadatos.
  1 unidad por llamada; `search.list` (100 unidades) no se usa. Presupuesto diario declarado en
  la lista de vigilancia; al agotarse (propio o `quotaExceeded` de Google) se degrada: los canales
  que faltan quedan con error «cuota agotada» y nada se cae.
- **RSS de canal**: solo si la lista lo habilita (`rss_enabled`); en las pruebas de T62 respondió
  404 y no da duración ni idioma.

Clave (del proyecto de Google del usuario): la variable `EIM_YOUTUBE_API_KEY` o, si no existe, el
archivo `EIM_YOUTUBE_API_KEY_FILE` (por defecto `~/.eim/youtube_api_key.txt`, **fuera del repo**:
no puede acabar en git ni en la copia entre equipos). Nunca se registra: los errores se redactan
sin URL ni parámetros. Reintentos con espera creciente ante 429/5xx/red, ritmo mínimo
entre llamadas, y cada canal falla por su cuenta.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from eim.data.video.parse import rfc3339_ms, video_from_api, videos_from_rss
from eim.video.models import VideoMeta

API = "https://www.googleapis.com/youtube/v3/"
RSS = "https://www.youtube.com/feeds/videos.xml"
KEY_ENV = "EIM_YOUTUBE_API_KEY"
KEY_FILE_ENV = "EIM_YOUTUBE_API_KEY_FILE"
DEFAULT_KEY_FILE = Path.home() / ".eim" / "youtube_api_key.txt"
QUOTA_REASONS = {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"}


def load_key(env: Mapping[str, str] | None = None) -> str | None:
    """Clave de la variable o, si falta, del archivo; None si no hay ninguna (o es ilegible)."""
    env = os.environ if env is None else env
    key = env.get(KEY_ENV, "").strip()
    if key:
        return key
    path = Path(env.get(KEY_FILE_ENV) or DEFAULT_KEY_FILE)
    try:
        key = path.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return None
    return key or None


class QuotaExhausted(Exception):
    """Sin unidades: la propia del EIM o la que Google declara agotada."""


class SourceError(Exception):
    """Error de la fuente ya redactado (sin clave ni URL)."""


@dataclass
class QuotaGuard:
    """`used()` y `add(n)` leen y suman el gasto del día (en el catálogo)."""

    limit: int
    used: Callable[[], int]
    add: Callable[[int], None]
    spent: int = 0

    def spend(self, units: int) -> None:
        if self.used() + units > self.limit:
            raise QuotaExhausted(f"presupuesto diario de {self.limit} unidades agotado")
        self.add(units)
        self.spent += units


class YouTubeApi:
    def __init__(self, key: str, quota: QuotaGuard, client: httpx.Client | None = None, *,
                 min_interval_s: float = 0.2, retries: int = 3,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self._key, self.quota = key, quota
        self._client = client or httpx.Client(timeout=20.0)
        self._min, self._retries, self._sleep = min_interval_s, retries, sleep
        self._last = 0.0

    @classmethod
    def from_env(cls, quota: QuotaGuard, **kw) -> YouTubeApi | None:
        key = load_key()
        return cls(key, quota, **kw) if key else None

    def _get(self, endpoint: str, params: dict) -> dict:
        self.quota.spend(1)
        for attempt in range(self._retries):
            wait = self._min - (time.monotonic() - self._last)
            if wait > 0:
                self._sleep(wait)
            self._last = time.monotonic()
            try:
                r = self._client.get(API + endpoint, params=params | {"key": self._key})
            except httpx.HTTPError as exc:
                err = SourceError(f"{endpoint}: red ({type(exc).__name__})")
            else:
                if r.status_code == 200:
                    return r.json()
                reason = _reason(r)
                if r.status_code == 403 and reason in QUOTA_REASONS:
                    raise QuotaExhausted(f"{endpoint}: Google responde {reason}")
                err = SourceError(f"{endpoint}: HTTP {r.status_code} {reason}".strip())
                if r.status_code not in (429, 500, 502, 503, 504):
                    raise err
            if attempt < self._retries - 1:
                self._sleep(2.0 ** attempt)
        raise err

    def channel(self, channel_id: str) -> tuple[str, str]:
        """(lista de subidas, título). SourceError si el canal no existe."""
        d = self._get("channels", {"part": "contentDetails,snippet", "id": channel_id,
                                   "maxResults": 1})
        items = d.get("items") or []
        if not items:
            raise SourceError("canal no encontrado en la API")
        it = items[0]
        uploads = ((it.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads")
        if not uploads:
            raise SourceError("el canal no expone lista de subidas")
        return uploads, str((it.get("snippet") or {}).get("title", ""))

    def upload_ids(self, playlist_id: str, max_pages: int, since_ms: int | None) -> list[str]:
        """Ids de la lista de subidas (más reciente primero); para al pasar de `since_ms`."""
        ids, token = [], None
        for _ in range(max_pages):
            p = {"part": "contentDetails", "playlistId": playlist_id, "maxResults": 50}
            d = self._get("playlistItems", p | ({"pageToken": token} if token else {}))
            older = False
            for it in d.get("items") or []:
                cd = it.get("contentDetails") or {}
                pub = cd.get("videoPublishedAt")
                if since_ms is not None and pub and rfc3339_ms(pub) < since_ms:
                    older = True
                    continue
                if cd.get("videoId"):
                    ids.append(cd["videoId"])
            token = d.get("nextPageToken")
            if older or not token:
                break
        return ids

    def videos(self, ids: list[str]) -> list[VideoMeta]:
        out = []
        for i in range(0, len(ids), 50):
            d = self._get("videos", {"part": "snippet,contentDetails,liveStreamingDetails",
                                     "id": ",".join(ids[i:i + 50]), "maxResults": 50})
            out += [m for m in map(video_from_api, d.get("items") or []) if m is not None]
        return out


def _reason(r: httpx.Response) -> str:
    try:
        errs = (r.json().get("error") or {}).get("errors") or []
        return str(errs[0].get("reason", "")) if errs else ""
    except (ValueError, AttributeError):
        return ""


def rss_fetch(client: httpx.Client, channel_id: str) -> list[VideoMeta]:
    try:
        r = client.get(RSS, params={"channel_id": channel_id})
    except httpx.HTTPError as exc:
        raise SourceError(f"rss: red ({type(exc).__name__})") from None
    if r.status_code != 200:
        raise SourceError(f"rss: HTTP {r.status_code}")
    return videos_from_rss(r.content, channel_id)


@dataclass
class ChannelResult:
    channel_id: str
    source: str
    ok: bool
    metas: list[VideoMeta] = field(default_factory=list)
    title: str | None = None
    units: int = 0
    error: str | None = None


def discover(channel_ids: list[str], api: YouTubeApi | None, rss: httpx.Client | None, *,
             max_pages: int, since_ms: int | None = None) -> list[ChannelResult]:
    """Un resultado por canal; un fallo (o la cuota agotada) nunca tumba a los demás."""
    out: list[ChannelResult] = []
    exhausted: str | None = None
    for ch in channel_ids:
        if api is not None:
            if exhausted:
                out.append(ChannelResult(ch, "youtube_api", False, error=exhausted))
                continue
            before = api.quota.spent
            try:
                uploads, title = api.channel(ch)
                metas = api.videos(api.upload_ids(uploads, max_pages, since_ms))
                if since_ms is not None:
                    metas = [m for m in metas if m.published_at >= since_ms]
                out.append(ChannelResult(ch, "youtube_api", True, metas, title,
                                         api.quota.spent - before))
            except QuotaExhausted as exc:
                exhausted = f"cuota agotada: {exc}"
                out.append(ChannelResult(ch, "youtube_api", False, units=api.quota.spent - before,
                                         error=exhausted))
            except SourceError as exc:
                out.append(ChannelResult(ch, "youtube_api", False, units=api.quota.spent - before,
                                         error=str(exc)))
        elif rss is not None:
            try:
                out.append(ChannelResult(ch, "youtube_rss", True, rss_fetch(rss, ch)))
            except (SourceError, ValueError, SyntaxError) as exc:
                out.append(ChannelResult(ch, "youtube_rss", False, error=str(exc)[:200]))
        else:
            out.append(ChannelResult(ch, "ninguna", False, error=(
                f"sin fuente: define {KEY_ENV} o crea ~/.eim/{DEFAULT_KEY_FILE.name}")))
    return out


def recheck(api: YouTubeApi, ids: list[str]) -> set[str] | None:
    """Ids que siguen existiendo (para detectar borrados); None si no hay cuota o falla."""
    try:
        return {m.video_id for m in api.videos(ids)}
    except (QuotaExhausted, SourceError):
        return None
