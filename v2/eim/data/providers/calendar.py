"""Calendario económico desde fuentes oficiales gratuitas (T33 §5). Todo el I/O de red.

Fuentes (dominio público EE. UU.):
- Fed FOMC (`fomccalendars.htm`): fechas; la decisión se publica a las 14:00 ET del último día
  (convención de la Fed, no figura en la página).
- BLS (`bls.ics`): fecha y hora en ET explícita (`TZID=US-Eastern`).
- BEA (`release_dates.json`): fecha y hora ya en UTC (`+00:00`).
Ninguna da consenso → `forecast=None`. Los valores reales (opcionales) los añade `fred.py`.
Sin red → `None` por fuente: nunca se devuelve un calendario parcial como si fuera completo.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from html import unescape
from zoneinfo import ZoneInfo

import httpx

from eim.core import EconEvent

ET = ZoneInfo("America/New_York")
USER_AGENT = "EIM-calendar/1.0 (uso personal; calendario macro)"
FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
BLS_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
BEA_URL = "https://apps.bea.gov/API/signup/release_dates.json"

SOURCES: dict[str, str] = {
    "fed_fomc": "Federal Reserve, calendario FOMC (decisión 14:00 ET por convención)",
    "bls": "BLS, calendario de publicaciones (ICS, hora ET)",
    "bea": "BEA, fechas de publicación (JSON, UTC)",
}

# Impacto por nombre exacto de la publicación; el resto es "bajo".
IMPACT: dict[str, str] = {
    "Decisión de tipos FOMC": "alto",
    "Consumer Price Index": "alto",
    "Employment Situation": "alto",
    "Personal Income and Outlays": "alto",
    "Gross Domestic Product": "alto",
    "Producer Price Index": "medio",
    "Job Openings and Labor Turnover Survey": "medio",
    "Employment Cost Index": "medio",
    "U.S. International Trade in Goods and Services": "medio",
}
_MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September",
     "October", "November", "December"], start=1)}
_MON3 = {m[:3]: i for m, i in _MONTHS.items()}


def et_to_utc_ms(y: int, mo: int, d: int, hh: int, mm: int) -> int:
    """Hora local de Nueva York (EST/EDT según la fecha) → ms epoch UTC."""
    return int(datetime(y, mo, d, hh, mm, tzinfo=ET).timestamp() * 1000)


def impact_of(name: str) -> str:
    return IMPACT.get(name.strip(), "bajo")


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48]


def make_event(source: str, name: str, t_utc: int, fetched_at: int,
               country: str = "US") -> EconEvent:
    name = " ".join(name.split())
    day = datetime.fromtimestamp(t_utc / 1000, tz=UTC).strftime("%Y%m%d")
    return EconEvent(id=f"{source}:{_slug(name)}:{day}", t_utc=t_utc, name=name,
                     country=country, impact=impact_of(name), source=SOURCES.get(source, source),
                     fetched_at=fetched_at)


# --- parsers (puros; probados con fixtures reales) ------------------------
_PANEL = re.compile(r"(\d{4}) FOMC Meetings")
_MEETING = re.compile(
    r'fomc-meeting__month[^>]*>\s*<strong>([^<]+)</strong>.*?fomc-meeting__date[^>]*>([^<]+)<',
    re.S)


def parse_fomc_html(html: str, fetched_at: int) -> list[EconEvent]:
    """Reuniones FOMC por año. "Oct/Nov 31-1" → 1 de noviembre; votos por notación se omiten."""
    out: list[EconEvent] = []
    heads = list(_PANEL.finditer(html))
    for i, h in enumerate(heads):
        year = int(h.group(1))
        body = html[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(html)]
        for month_txt, date_txt in _MEETING.findall(body):
            date_txt = unescape(date_txt).strip()
            m = re.match(r"(\d{1,2})(?:\s*-\s*(\d{1,2}))?", date_txt)
            if not m or "notation" in date_txt.lower():
                continue
            months = [p.strip() for p in unescape(month_txt).split("/")]
            mon = months[-1]
            mo = _MONTHS.get(mon) or _MON3.get(mon[:3])
            if mo is None:
                continue
            day = int(m.group(2) or m.group(1))
            t = et_to_utc_ms(year, mo, day, 14, 0)
            out.append(make_event("fed_fomc", "Decisión de tipos FOMC", t, fetched_at))
    return sorted(out, key=lambda e: e.t_utc)


def _ics_lines(text: str) -> list[str]:
    """Desdobla líneas (RFC 5545: continuación con espacio o tabulador)."""
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def parse_bls_ics(text: str, fetched_at: int) -> list[EconEvent]:
    """VEVENT con `DTSTART;TZID=US-Eastern:AAAAMMDDThhmmss` (hora ET) o `...Z` (UTC)."""
    out: list[EconEvent] = []
    cur: dict[str, str] = {}
    for line in _ics_lines(text):
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT":
            dt, name = cur.get("DTSTART"), cur.get("SUMMARY", "").replace("\\,", ",")
            m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})\d{2}(Z?))?", dt or "")
            if m and name:
                y, mo, d = int(m[1]), int(m[2]), int(m[3])
                hh, mm = int(m[4] or 0), int(m[5] or 0)
                t = (int(datetime(y, mo, d, hh, mm, tzinfo=UTC).timestamp() * 1000)
                     if m[6] else et_to_utc_ms(y, mo, d, hh, mm))
                out.append(make_event("bls", name, t, fetched_at))
            cur = {}
        elif ":" in line:
            key, val = line.split(":", 1)
            cur[key.split(";")[0]] = val.strip()
    return sorted(out, key=lambda e: e.t_utc)


def parse_bea_json(text: str, fetched_at: int) -> list[EconEvent]:
    """`{nombre: {release_dates: [ISO con zona]}}`; fechas repetidas se cuentan una vez."""
    out: dict[str, EconEvent] = {}
    for name, body in json.loads(text).items():
        if not isinstance(body, dict):
            continue
        for iso in body.get("release_dates", []):
            try:
                dt = datetime.fromisoformat(iso)
            except (TypeError, ValueError):
                continue
            if dt.tzinfo is None:  # sin zona → ET (convención de la BEA)
                dt = dt.replace(tzinfo=ET)
            ev = make_event("bea", name, int(dt.timestamp() * 1000), fetched_at)
            out[ev.id] = ev
    return sorted(out.values(), key=lambda e: e.t_utc)


PARSERS: dict[str, tuple[str, Callable[[str, int], list[EconEvent]]]] = {
    "fed_fomc": (FOMC_URL, parse_fomc_html),
    "bls": (BLS_URL, parse_bls_ics),
    "bea": (BEA_URL, parse_bea_json),
}


class OfficialCalendar:
    """Descarga cada fuente oficial; una fuente caída devuelve None (no lista vacía)."""

    name = "calendario-oficial"

    def __init__(self, client: httpx.Client | None = None, timeout: float = 20.0) -> None:
        self._client = client or httpx.Client(
            timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT})

    def fetch(self, source: str, fetched_at: int) -> list[EconEvent] | None:
        url, parse = PARSERS[source]
        try:
            r = self._client.get(url)
            r.raise_for_status()
            events = parse(r.text, fetched_at)
        except (httpx.HTTPError, ValueError):
            return None
        return events or None  # un calendario vacío es un formato roto, no "sin eventos"

    def fetch_all(self, fetched_at: int) -> dict[str, list[EconEvent] | None]:
        return {s: self.fetch(s, fetched_at) for s in PARSERS}
