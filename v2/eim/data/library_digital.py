"""Biblioteca digital (T151/T152): verificación en línea, caché y lectura de resúmenes y textos.

Toda la E/S de la biblioteca digital vive aquí. Registros consultados: OpenAlex (metadatos, acceso
abierto y resumen), arXiv (metadatos y resumen) y la URL oficial de las obras web. Cada respuesta
se guarda en `data/library/digital/cache/` (ignorada por git) y se reutiliza: sin conexión, la
biblioteca sigue con lo que ya tenía y lo dice (`problem`). El texto completo solo se descarga a
petición (`fetch_text`) y solo de obras con acceso legal (`oa_url`). Lo descargado es dato, nunca
instrucción. Las peticiones no llevan datos del usuario (agente genérico, sin correo).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from eim.library.digital.registry import (
    abstract_from_index,
    from_arxiv,
    from_openalex,
    from_web,
    html_title,
    parse_arxiv,
    title_matches,
)
from eim.library.digital.schema import DigitalCard, DigitalRef, SeedRef

PKG = Path(__file__).resolve().parents[1] / "library" / "digital"
SEED = PKG / "seed.json"
CATALOG = PKG / "catalog.json"
CARDS = PKG / "cards.json"
UA = "EIM-library-verifier/1.0"
OPENALEX = "https://api.openalex.org/works/"
ARXIV = "https://export.arxiv.org/api/query?id_list="
FIELDS = ("id,doi,title,display_name,publication_year,authorships,primary_location,open_access,"
          "best_oa_location,type,cited_by_count,abstract_inverted_index")
Log = Callable[[str], None]


@dataclass(frozen=True)
class DigitalPaths:
    root: Path

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> DigitalPaths:
        env = dict(os.environ if env is None else env)
        return cls(Path(env.get("EIM_DATA_DIR", "data")) / "library" / "digital")

    def cache(self, kind: str, key: str) -> Path:
        h = hashlib.sha1(key.lower().encode()).hexdigest()[:16]
        return self.root / "cache" / kind / f"{h}.json"

    def text(self, ref_id: str) -> Path:
        return self.root / "texts" / f"{ref_id}.txt"

    @property
    def trace(self) -> Path:
        return self.root / "trace.jsonl"

    @property
    def research_log(self) -> Path:
        return self.root / "research.jsonl"


class Http:
    """Cliente HTTP mínimo con pausa entre peticiones (cortesía con las API públicas)."""

    def __init__(self, client: httpx.Client | None = None, pause_s: float = 0.15) -> None:
        self._c = client or httpx.Client(timeout=20.0, follow_redirects=True,
                                         headers={"User-Agent": UA})
        self._pause = pause_s

    def get(self, url: str) -> httpx.Response:
        time.sleep(self._pause)
        return self._c.get(url)


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _cached(paths: DigitalPaths, kind: str, key: str, fetch: Callable[[], str | None],
            refresh: bool) -> tuple[str | None, str | None]:
    """(contenido, problema). Usa la caché si existe y no se pide refrescar; sin red, la caché."""
    f = paths.cache(kind, key)
    if f.exists() and not refresh:
        return json.loads(f.read_text(encoding="utf-8"))["body"], None
    try:
        body = fetch()
    except httpx.HTTPError as exc:
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))["body"], f"sin conexión: {exc!s:.80}"
        return None, f"sin conexión y sin caché: {exc!s:.80}"
    if body is None:
        return None, "el registro no encontró la obra"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"key": key, "fetched": _today(), "body": body}), encoding="utf-8")
    return body, None


def _openalex(http: Http, key: str) -> str | None:
    # Clave propia opcional (cupo gratuito por IP sin ella); nunca se envía un correo.
    api_key = os.environ.get("EIM_OPENALEX_KEY")
    r = http.get(f"{OPENALEX}{key}?select={FIELDS}" + (f"&api_key={api_key}" if api_key else ""))
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.text


def _arxiv(http: Http, arxiv_id: str) -> str | None:
    r = http.get(ARXIV + arxiv_id)
    r.raise_for_status()
    return r.text if parse_arxiv(r.text) else None


def _web(http: Http, url: str) -> str | None:
    r = http.get(url)
    if r.status_code >= 400:
        return None
    return html_title(r.text) if "html" in r.headers.get("content-type", "") else "(documento)"


def verify(seed: SeedRef, paths: DigitalPaths, http: Http, refresh: bool = False) -> DigitalRef:
    """Comprueba una referencia en su registro y devuelve la entrada de catálogo."""
    loc, today = seed.locator, _today()
    base = {"id": seed.id, "locator": loc, "curated": seed.curated}
    if loc.doi or (loc.arxiv and not loc.doi):
        key = f"doi:{loc.doi}" if loc.doi else f"doi:10.48550/arxiv.{loc.arxiv}"
        body, prob = _cached(paths, "openalex", key, lambda: _openalex(http, key), refresh)
        if body:
            v = from_openalex(json.loads(body), today)
            if not title_matches(loc.expect, v.title):
                return DigitalRef(**base, verified=v, problem=f"título distinto: «{v.title}»")
            return DigitalRef(**base, verified=v, problem=prob if prob and "caché" in prob
                              else None)
        if not loc.arxiv:
            return DigitalRef(**base, problem=prob)
    if loc.arxiv:
        body, prob = _cached(paths, "arxiv", loc.arxiv, lambda: _arxiv(http, loc.arxiv), refresh)
        a = parse_arxiv(body) if body else None
        if not a:
            return DigitalRef(**base, problem=prob or "arXiv no devolvió la entrada")
        v = from_arxiv(a, loc.arxiv, today)
        bad = None if title_matches(loc.expect, v.title) else f"título distinto: «{v.title}»"
        return DigitalRef(**base, verified=v, problem=bad)
    body, prob = _cached(paths, "web", loc.url or "", lambda: _web(http, loc.url or ""), refresh)
    if body is None:
        return DigitalRef(**base, problem=prob)
    return DigitalRef(**base, verified=from_web(loc.url or "", body, loc.web or {}, today))


def abstract(ref: DigitalRef, paths: DigitalPaths) -> str:
    """Resumen guardado en la caché (OpenAlex o arXiv); vacío si no hay."""
    loc = ref.locator
    keys = ([("openalex", f"doi:{loc.doi}")] if loc.doi else []) + \
        ([("openalex", f"doi:10.48550/arxiv.{loc.arxiv}"), ("arxiv", loc.arxiv)]
         if loc.arxiv else [])
    for kind, key in keys:
        f = paths.cache(kind, key)
        if not f.exists():
            continue
        body = json.loads(f.read_text(encoding="utf-8"))["body"]
        text = (abstract_from_index(json.loads(body).get("abstract_inverted_index"))
                if kind == "openalex" else (parse_arxiv(body) or {}).get("summary", ""))
        if text:
            return text
    return ""


def local_text(ref_id: str, paths: DigitalPaths) -> str:
    f = paths.text(ref_id)
    return f.read_text(encoding="utf-8") if f.exists() else ""


def load_seed(path: Path = SEED) -> list[SeedRef]:
    return [SeedRef(**r) for r in json.loads(path.read_text(encoding="utf-8"))["refs"]]


def load_catalog(path: Path = CATALOG) -> list[DigitalRef]:
    if not path.exists():
        return []
    return [DigitalRef(**r) for r in json.loads(path.read_text(encoding="utf-8"))["refs"]]


def save_catalog(refs: list[DigitalRef], path: Path = CATALOG) -> None:
    doc = {"_doc": "Generado por `python -m eim.library digital verify` desde seed.json; "
                   "lo bibliográfico viene del registro (OpenAlex/arXiv/web).",
           "refs": [r.model_dump(exclude_none=True) for r in refs]}
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def load_cards(path: Path = CARDS) -> dict[str, DigitalCard]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))["cards"]
    return {c["ref_id"]: DigitalCard(**c) for c in raw}


def save_cards(cards: dict[str, DigitalCard], path: Path = CARDS) -> None:
    doc = {"_doc": "Fichas extraídas por `python -m eim.library digital research` (T152). "
                   "Fragmentos ≤ 25 palabras del resumen o texto legal.",
           "cards": [c.model_dump() for c in sorted(cards.values(), key=lambda c: c.ref_id)]}
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def log_research(paths: DigitalPaths, entry: dict) -> None:
    paths.research_log.parent.mkdir(parents=True, exist_ok=True)
    with paths.research_log.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": datetime.now(UTC).isoformat(timespec="seconds"), **entry},
                           ensure_ascii=False) + "\n")


def load_kb(local: bool = True):
    """Base de conocimiento: catálogo digital verificado + fichas + fichas locales (T52)."""
    from eim.data.library import load_cards as load_local
    from eim.library.digital.consensus import KnowledgeBase
    loc = []
    if local:
        try:
            loc = load_local()
        except (OSError, ValueError):
            loc = []
    return KnowledgeBase.build(load_catalog(), load_cards(), loc)


def append_traces(paths: DigitalPaths, traces: list[dict]) -> int:
    """Añade al registro de aprendizaje las trazas nuevas (por `ledger_id`); nunca reescribe."""
    seen = set()
    if paths.trace.exists():
        for ln in paths.trace.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                seen.add(json.loads(ln).get("ledger_id"))
    new = [t for t in traces if t.get("ledger_id") and t["ledger_id"] not in seen]
    if new:
        paths.trace.parent.mkdir(parents=True, exist_ok=True)
        with paths.trace.open("a", encoding="utf-8") as f:
            for t in new:
                f.write(json.dumps({"recorded": _today(), **t}, ensure_ascii=False) + "\n")
    return len(new)


def read_traces(paths: DigitalPaths, n: int = 50) -> list[dict]:
    if not paths.trace.exists():
        return []
    lines = [x for x in paths.trace.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [json.loads(x) for x in reversed(lines[-n:])]


def recent_research(paths: DigitalPaths, n: int = 10) -> list[dict]:
    if not paths.research_log.exists():
        return []
    lines = paths.research_log.read_text(encoding="utf-8").splitlines()[-n:]
    return [json.loads(x) for x in reversed(lines) if x.strip()]
