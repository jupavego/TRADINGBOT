"""Consenso y contradicciones entre fuentes (T157), puro.

No se cuentan libros: cada postura pesa por la calidad de su evidencia y su pertinencia para
BTCUSDT. Peso = nivel × fiabilidad × verificación × aplicabilidad × vigencia (tablas abajo, fijas
y a la vista). La biblioteca local (T52) entra con sus fichas como hipótesis de libro.

Veredictos por concepto: «a favor», «en contra», «dividido», «condicionado» o «sin evidencia», con
quién apoya, quién objeta, en qué condiciones y qué puede explicar la diferencia.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from eim.library.digital.schema import DigitalCard, DigitalRef, Stance
from eim.library.digital.taxonomy import CONCEPTS, detect
from eim.library.schema import KnowledgeCard

LEVEL_W = {"validada_eim": 1.0, "evidencia_empirica": 0.8, "teoria": 0.5,
           "estrategia_documentada": 0.4, "hipotesis": 0.25}
RELIABILITY_W = {"alta": 1.0, "media": 0.7, "baja": 0.4}
VERIFIED_W = {True: 1.0, False: 0.6}
MARKET_W = {"cripto": 1.0, "futuros": 0.8, "divisas": 0.6, "acciones": 0.6, "índices": 0.6}
NO_MARKET_W = 0.7          # teoría o método sin mercado concreto
FAVOR, MIN_MASS = 0.5, 0.4  # |neto| ≥ 0,5 y masa ≥ 0,4 (≈ un estudio empírico verificado)


@dataclass(frozen=True)
class Evidence:
    """Una postura ponderada lista para mostrar."""

    source_id: str
    cite: str
    url: str | None
    concept: str
    kind: str
    level: str
    verified: bool
    summary: str
    conditions: str
    markets: tuple[str, ...]
    weight: float
    local: bool = False       # ficha de la biblioteca local (T52)

    def to_json(self) -> dict:
        return {"source_id": self.source_id, "cite": self.cite, "url": self.url,
                "concept": self.concept, "kind": self.kind, "level": self.level,
                "verified": self.verified, "summary": self.summary,
                "conditions": self.conditions, "markets": list(self.markets),
                "weight": round(self.weight, 3), "local": self.local}


def cite(ref: DigitalRef) -> str:
    v = ref.verified
    if v is None:
        return ref.id
    a = v.authors
    who = (a[0].split()[-1] if a else "s. a.") + (" et al." if len(a) > 2 else
                                                 f" y {a[1].split()[-1]}" if len(a) == 2 else "")
    return f"{who} ({v.year or 's. f.'})"


def _applicability(markets: list[str] | tuple[str, ...]) -> float:
    return max((MARKET_W.get(m, 0.6) for m in markets), default=NO_MARKET_W)


def _vigency(year: int | None, level: str) -> float:
    if level != "evidencia_empirica" or year is None:
        return 1.0
    return 1.0 if year >= 2015 else 0.9 if year >= 2000 else 0.8


def weigh(ref: DigitalRef, s: Stance, verified: bool) -> float:
    year = ref.verified.year if ref.verified else None
    return (LEVEL_W[s.level] * RELIABILITY_W[ref.reliability] * VERIFIED_W[verified]
            * _applicability(ref.curated.markets) * _vigency(year, s.level))


@dataclass
class KnowledgeBase:
    """Catálogo digital + fichas extraídas + fichas locales, indexado por concepto."""

    refs: dict[str, DigitalRef]
    cards: dict[str, DigitalCard] = field(default_factory=dict)
    local: list[KnowledgeCard] = field(default_factory=list)
    by_concept: dict[str, list[Evidence]] = field(default_factory=dict)

    @classmethod
    def build(cls, refs: list[DigitalRef], cards: dict[str, DigitalCard] | None = None,
              local: list[KnowledgeCard] | None = None) -> KnowledgeBase:
        kb = cls({r.id: r for r in refs if r.ok}, cards or {}, local or [])
        for r in kb.refs.values():
            card = kb.cards.get(r.id)
            ok = set(card.stances_verified) if card else set()
            for s in r.curated.stances:
                kb._add(Evidence(r.id, cite(r), r.verified.url if r.verified else None,
                                 s.concept, s.kind, s.level, s.concept in ok, s.summary,
                                 s.conditions, tuple(r.curated.markets),
                                 weigh(r, s, s.concept in ok)))
        seen: set[tuple[str, str, str]] = set()     # un libro = una voz por concepto y postura
        for c in kb.local:
            kb._add_local(c, seen)
        for ev in kb.by_concept.values():
            ev.sort(key=lambda e: -e.weight)
        return kb

    def _add(self, e: Evidence) -> None:
        self.by_concept.setdefault(e.concept, []).append(e)

    def _add_local(self, c: KnowledgeCard, seen: set[tuple[str, str, str]]) -> None:
        """Ficha de libro → postura «apoya» (o «condiciona» si es advertencia), nivel hipótesis.

        Un libro cuenta una sola vez por concepto y postura, tenga 1 o 40 fichas: si no, un manual
        con muchas fichas pesaría más que un estudio empírico (eso sería contar páginas)."""
        if c.status == "descartada":
            return
        kind = "condiciona" if c.kind in ("advertencia", "gestion_riesgo") else "apoya"
        book0 = sorted(c.book_ids)[0] if c.book_ids else "cruces"
        for concept in detect(f"{c.title}. {c.claim}")[:2]:
            if (book0, concept, kind) in seen:
                continue
            seen.add((book0, concept, kind))
            w = (LEVEL_W["hipotesis"] * RELIABILITY_W["media"]
                 * VERIFIED_W[c.verification == "verificada_en_texto"]
                 * _applicability(tuple(c.applicability.original_market)))
            self._add(Evidence(c.id, f"{book0} · {c.title}", None, concept, kind, "hipotesis",
                               c.verification == "verificada_en_texto", c.claim[:280],
                               c.applicability.timeframe, tuple(c.applicability.original_market),
                               w, local=True))


def consensus(kb: KnowledgeBase, concept: str, k: int = 4) -> dict:
    """Veredicto ponderado de un concepto con las mejores `k` fuentes de cada lado."""
    ev = kb.by_concept.get(concept, [])
    sup = [e for e in ev if e.kind == "apoya"]
    obj = [e for e in ev if e.kind == "objeta"]
    cond = [e for e in ev if e.kind == "condiciona"]
    s, o, c = (sum(e.weight for e in x) for x in (sup, obj, cond))
    net = (s - o) / (s + o) if s + o > 0 else 0.0
    if not ev:
        verdict = "sin evidencia"
    elif (s + o < MIN_MASS and c > 0) or c > s + o:
        verdict = "condicionado"       # pesa más el «depende» que el sí o el no
    elif s + o < MIN_MASS:
        verdict = "sin evidencia"
    elif net >= FAVOR:
        verdict = "a favor"
    elif net <= -FAVOR:
        verdict = "en contra"
    else:
        verdict = "dividido"
    crypto = any("cripto" in e.markets for e in ev)
    return {
        "concept": concept, "name": CONCEPTS[concept].name if concept in CONCEPTS else concept,
        "verdict": verdict, "net": round(net, 3), "support_mass": round(s, 3),
        "objection_mass": round(o, 3), "conditional_mass": round(c, 3),
        "support": [e.to_json() for e in sup[:k]], "objections": [e.to_json() for e in obj[:k]],
        "conditions": [e.to_json() for e in cond[:k]],
        "n_sources": len({e.source_id for e in ev}), "crypto_evidence": crypto,
        "explanation": explain(sup, obj, cond, crypto),
    }


def explain(sup: list[Evidence], obj: list[Evidence], cond: list[Evidence],
            crypto: bool) -> list[str]:
    """Frases que explican el veredicto: dónde se estudió cada lado y qué falta."""
    out = []
    if sup and obj:
        ms, mo = ({m for e in x for m in e.markets} for x in (sup, obj))
        out.append(f"Apoyan {len(sup)} y objetan {len(obj)}. Los que apoyan estudiaron "
                   f"{', '.join(sorted(ms)) or 'teoría'}; los que objetan, "
                   f"{', '.join(sorted(mo)) or 'teoría'}.")
        emp_o = sum(e.level == "evidencia_empirica" for e in obj)
        if emp_o and any("costo" in e.summary.lower() or "fuera de muestra" in e.summary.lower()
                         for e in obj):
            out.append("Las objeciones suelen corregir por costos o probar fuera de muestra: "
                       "la diferencia puede ser de método, no de mercado.")
    if cond:
        out.append("Condiciones citadas: " + "; ".join(sorted({e.conditions for e in cond
                                                               if e.conditions})[:3]) + ".")
    if not crypto and (sup or obj):
        out.append("Ninguna fuente de este concepto estudió cripto: aplicar a BTCUSDT es un "
                   "supuesto.")
    if sum(e.verified for e in sup + obj) == 0 and (sup or obj):
        out.append("Ninguna postura está aún verificada en el texto descargado.")
    return out


def contradictions(kb: KnowledgeBase, min_each: float = 0.2) -> list[dict]:
    """Conceptos en los que hay masa apreciable a favor y en contra (T157)."""
    out = []
    for concept in sorted(kb.by_concept):
        d = consensus(kb, concept)
        if d["support_mass"] >= min_each and d["objection_mass"] >= min_each:
            out.append(d)
    return sorted(out, key=lambda d: abs(d["net"]))
