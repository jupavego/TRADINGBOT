"""Lectura de titulares (RSS). Todo el I/O de noticias vive aquí; el texto es DATO externo."""

from __future__ import annotations

import hashlib
from datetime import UTC
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx

from eim.core import NewsItem

DEFAULT_FEEDS: dict[str, str] = {
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "Cointelegraph": "https://cointelegraph.com/rss",
}


def item_id(source: str, title: str, url: str) -> str:
    return hashlib.sha1(f"{source}|{url}|{title}".encode()).hexdigest()[:10]


def parse_rss(xml_text: str, source: str) -> list[NewsItem]:
    """Parsea un RSS 2.0; omite ítems sin título o con fecha ilegible (nunca inventa datos)."""
    out: list[NewsItem] = []
    for it in ElementTree.fromstring(xml_text).iter("item"):
        title = (it.findtext("title") or "").strip()
        url = (it.findtext("link") or "").strip()
        try:
            dt = parsedate_to_datetime(it.findtext("pubDate") or "")
            ts = int((dt if dt.tzinfo else dt.replace(tzinfo=UTC)).timestamp() * 1000)
        except (TypeError, ValueError):
            continue
        if title:
            out.append(NewsItem(id=item_id(source, title, url), t=ts, title=title,
                                source=source, url=url))
    return out


def fetch_headlines(feeds: dict[str, str] | None = None, *, timeout: float = 10.0,
                    client: httpx.Client | None = None) -> list[NewsItem]:
    """Descarga los feeds; un feed caído se omite (la cobertura real = lo devuelto)."""
    http = client or httpx.Client(timeout=timeout, follow_redirects=True)
    items: list[NewsItem] = []
    try:
        for source, url in (feeds or DEFAULT_FEEDS).items():
            try:
                r = http.get(url)
                r.raise_for_status()
                items.extend(parse_rss(r.text, source))
            except (httpx.HTTPError, ElementTree.ParseError):
                continue
    finally:
        if client is None:
            http.close()
    return sorted(items, key=lambda n: -n.t)
