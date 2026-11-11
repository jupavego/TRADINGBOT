"""Rutas de la biblioteca digital (T151–T158), solo lectura salvo el registro de trazas.

    GET  /v2/library/digital/overview            recuentos, investigaciones y trazas (panel T158)
    GET  /v2/library/digital/refs                búsqueda y filtros (T151)
    GET  /v2/library/digital/refs/{id}           ficha completa con lo extraído (T152)
    GET  /v2/library/digital/consensus/{concept} consenso ponderado (T157)
    GET  /v2/library/digital/contradictions      conceptos con fuentes enfrentadas (T157)
    GET  /v2/library/digital/contrast            contraste de una operación o idea (T153)
    GET  /v2/library/digital/diagnose            diagnóstico de una operación del libro (T154/T156)
    GET  /v2/library/digital/learning            utilidad del conocimiento con el libro fijo (T155)
    POST /v2/library/digital/learning/record     guarda las trazas nuevas (X-EIM-Confirm)
    GET  /v2/library/digital/profiles            lentes de los cuatro perfiles (T156)

Todo es complemento: nada aquí abre, cierra, veta ni cambia perfiles. Sin conexión funciona igual:
lee el catálogo y las fichas versionados y la caché local.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Header, HTTPException, Query

from eim.data.library_digital import (
    CARDS,
    CATALOG,
    DigitalPaths,
    append_traces,
    load_kb,
    read_traces,
    recent_research,
)
from eim.library.digital import catalog as cat
from eim.library.digital.consensus import KnowledgeBase, consensus, contradictions
from eim.library.digital.contrast import TradeContext, contrast
from eim.library.digital.diagnose import diagnose
from eim.library.digital.learning import evaluate
from eim.library.digital.profiles import LENSES
from eim.library.digital.taxonomy import CONCEPTS

CONFIRM = "library-learning"
Rows = Callable[[], list[dict]]


class _KbCache:
    """Recarga la base si cambian el catálogo o las fichas (p. ej. tras `research`)."""

    def __init__(self, loader: Callable[[], KnowledgeBase]) -> None:
        self._loader, self._key, self._kb = loader, None, None

    def __call__(self) -> KnowledgeBase:
        key = tuple(p.stat().st_mtime if p.exists() else 0 for p in (CATALOG, CARDS))
        if self._kb is None or key != self._key:
            self._kb, self._key = self._loader(), key
        return self._kb


def _counted(rows: list[dict]) -> list[dict]:
    from eim.paper.universe import counts_as_result
    return [r for r in rows if counts_as_result(r).counts]


def build_library_digital_router(rows: Rows | None = None,
                                 kb: Callable[[], KnowledgeBase] | None = None,
                                 paths: Callable[[], DigitalPaths] = DigitalPaths.from_env
                                 ) -> APIRouter:
    router = APIRouter(prefix="/v2/library/digital")
    get_kb = kb or _KbCache(load_kb)
    get_rows: Rows = rows or (lambda: [])

    def _ledger() -> list[dict]:
        try:
            return get_rows()
        except Exception:  # noqa: BLE001 — sin libro, la biblioteca sigue sirviendo
            return []

    @router.get("/overview")
    def overview() -> dict:
        k = get_kb()
        refs = list(k.refs.values())
        local_books = len({b for c in k.local for b in c.book_ids})
        p = paths()
        return {**cat.overview(refs, k.cards, local_books, len(k.local)),
                "recent_research": recent_research(p, 8), "recent_traces": read_traces(p, 8),
                "contradictions": len(contradictions(k)), "concepts": len(k.by_concept),
                "mode": "Análisis", "label": "Biblioteca digital · complemento, no señal"}

    @router.get("/refs")
    def refs(q: str = "", author: str = "", title: str = "", category: str = "",
             availability: str = "", concept: str = "", strategy: str = "",
             limit: int = Query(200, ge=1, le=500)) -> dict:
        k = get_kb()
        hits = cat.search(list(k.refs.values()), q, author, title, category, availability,
                          concept, strategy, limit)
        brief = ("id", "title", "authors", "year", "category", "category_name", "access",
                 "availability", "reliability", "url", "oa_url", "concept_names",
                 "related_strategies", "read")
        return {"refs": [{f: v[f] for f in brief} for v in
                         (cat.view(r, k.cards.get(r.id)) for r in hits)], "n": len(hits)}

    @router.get("/refs/{ref_id}")
    def ref(ref_id: str) -> dict:
        k = get_kb()
        if ref_id not in k.refs:
            raise HTTPException(404, f"obra inexistente o sin verificar: {ref_id}")
        return cat.view(k.refs[ref_id], k.cards.get(ref_id))

    @router.get("/consensus/{concept}")
    def get_consensus(concept: str) -> dict:
        if concept not in CONCEPTS:
            raise HTTPException(404, f"concepto desconocido: {concept}")
        return consensus(get_kb(), concept)

    @router.get("/contradictions")
    def get_contradictions() -> dict:
        return {"concepts": contradictions(get_kb())}

    @router.get("/contrast")
    def get_contrast(side: int = Query(1, ge=-1, le=1), strategy: str = "", family: str = "",
                     timeframe: str = "", regime: str | None = None,
                     trend: int = Query(0, ge=-1, le=1)) -> dict:
        return contrast(get_kb(), TradeContext(side=side or 1, strategy=strategy, family=family,
                                               timeframe=timeframe, regime=regime, trend=trend))

    @router.get("/diagnose")
    def get_diagnose(ledger_id: str | None = None, side: int = Query(1, ge=-1, le=1),
                     strategy: str = "", family: str = "", timeframe: str = "",
                     profile: str | None = None, entry: float | None = None,
                     sl: float | None = None, tp: float | None = None,
                     leverage: float | None = None, regime: str | None = None,
                     trend: int = Query(0, ge=-1, le=1)) -> dict:
        all_rows = _ledger()
        if ledger_id:
            row = next((r for r in all_rows if r.get("ledger_id") == ledger_id), None)
            if row is None:
                raise HTTPException(404, f"operación inexistente en el libro: {ledger_id}")
        else:
            row = {"side": side, "strategy": strategy, "family": family,
                   "timeframe": timeframe, "profile": profile, "entry": entry, "sl": sl,
                   "tp": tp, "leverage": leverage, "regime": regime}
        same = [r["r"] for r in _counted(all_rows) if r.get("strategy") == row.get("strategy")
                and r.get("r") is not None]
        from eim.library.digital.learning import summarize
        out = diagnose(get_kb(), row, summarize(same) if same else None, trend)
        out["operation"] = {k: row.get(k) for k in ("ledger_id", "profile", "strategy", "side",
                                                    "timeframe", "fill", "sl", "tp", "r")}
        return out

    @router.get("/learning")
    def learning(profile: str | None = None, traces: int = Query(20, ge=0, le=500)) -> dict:
        rs = [r for r in _counted(_ledger()) if profile is None or r.get("profile") == profile]
        res = evaluate(rs, get_kb())
        res["traces"] = res["traces"][:traces]
        return {**res, "mode": "SIMULADO", "profile": profile}

    @router.post("/learning/record")
    def record(x_eim_confirm: str | None = Header(None)) -> dict:
        if x_eim_confirm != CONFIRM:
            raise HTTPException(403, f"falta la cabecera X-EIM-Confirm: {CONFIRM}")
        res = evaluate(_counted(_ledger()), get_kb())
        return {"added": append_traces(paths(), res["traces"]), "n_traces": res["n_traces"]}

    @router.get("/profiles")
    def profiles() -> dict:
        return {"profiles": [{"id": ln.profile, "name": ln.name, "focus": ln.focus,
                              "always": [{"id": c, "name": CONCEPTS[c].name} for c in ln.always],
                              "category_w": ln.category_w,
                              "require_consensus": ln.require_consensus}
                             for ln in LENSES.values()],
                "note": "La lente reordena y anota; no cambia parámetros del perfil."}

    return router
