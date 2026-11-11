"""Agente de investigación y extracción (T152), puro: texto descargado → `DigitalCard`.

Reglas de honestidad:
- `coverage` es lo que de verdad se leyó (resumen o texto completo), nunca más.
- Los fragmentos son literales y de ≤ 25 palabras; un fragmento con texto dirigido a un modelo se
  descarta (es dato, no instrucción).
- Una postura curada solo pasa a «verificada» si todas sus palabras de control aparecen en el
  texto leído. Sin palabras de control, queda pendiente.
- Las «reglas operativas» son solo frases con umbral numérico y verbo de acción explícitos; se
  guardan como candidatas para el banco, jamás como reglas activas (T151–T158 no operan).
"""

from __future__ import annotations

import re

from eim.library.bm25 import fold
from eim.library.digital.schema import (
    MAX_FRAGMENT_WORDS,
    Coverage,
    DigitalCard,
    DigitalRef,
    EvidenceLevel,
    Fragment,
)
from eim.library.digital.taxonomy import detect
from eim.library.guards import injection_flags

METHODS = {
    "bootstrap": "bootstrap", "regression": "regresión", "garch": "GARCH",
    "neural network": "redes neuronales", "lstm": "LSTM", "convolutional": "redes convolucionales",
    "reinforcement": "aprendizaje por refuerzo", "random forest": "bosques aleatorios",
    "simulation": "simulación", "monte carlo": "Monte Carlo", "event study": "estudio de eventos",
    "out-of-sample": "prueba fuera de muestra", "cross-validation": "validación cruzada",
    "survey": "revisión de la literatura", "equilibrium": "modelo de equilibrio",
    "markov": "modelo de Markov", "kernel": "regresión por núcleos", "vector autoregress": "VAR",
    "panel": "datos de panel", "variance ratio": "cociente de varianzas",
    "kelly": "criterio de Kelly",
}
CONDITIONS = {
    "high volatility": "alta volatilidad", "volatile": "alta volatilidad",
    "bear market": "mercado bajista", "downturn": "mercado bajista", "decline": "caídas",
    "bull market": "mercado alcista", "trend": "tendencia", "sideways": "lateral",
    "range": "rango", "crisis": "crisis", "panic": "pánico", "crash": "crisis",
    "announcement": "anuncios", "illiquid": "baja liquidez", "liquidity": "liquidez",
    "recession": "recesión", "intraday": "intradía", "high-frequency": "alta frecuencia",
}
_FINDING = re.compile(r"\b(we find|we show|results? (show|suggest|indicate)|evidence|outperform"
                      r"|predict|significant|explain|document|we demonstrate|consistent with)\b")
_LIMIT = re.compile(r"\b(however|but|although|limit|transaction costs?|not robust|disappear"
                    r"|declin|fail|no evidence|insignificant|vanish|weaker|only when|overfit)")
_EMPIRICAL = re.compile(r"\b(data|sample|we find|empirical|evidence|observations|panel"
                        r"|historical|backtest)\b")
_THEORY = re.compile(r"\b(model|theory|we derive|we propose|theorem|equilibrium|axiom)\b")
_STRATEGY = re.compile(r"\b(strategy|strategies|trading rule|rules)\b")
_RULE = re.compile(r"\b(buy|sell|long|short|enter|exit)\b.{0,60}\b(when|if|above|below|cross)")
_NUMBER = re.compile(r"\d")


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text)) if s.strip()]


def fragment(sentence: str, where: Coverage) -> Fragment | None:
    """Fragmento literal de ≤ 25 palabras; None si trae texto dirigido a un modelo."""
    if injection_flags(sentence):
        return None
    w = sentence.split()
    text = " ".join(w[:MAX_FRAGMENT_WORDS]) + ("…" if len(w) > MAX_FRAGMENT_WORDS else "")
    return Fragment(text=text, where=where)


def _found(table: dict[str, str], t: str) -> list[str]:
    out: list[str] = []
    for k, v in table.items():
        if k in t and v not in out:
            out.append(v)
    return out


def level_of(text: str, doc_type: str) -> EvidenceLevel:
    """Nivel de la evidencia por lo que dice el texto y el tipo de obra (nunca `validada_eim`)."""
    t = fold(text)
    emp, theo, strat = (bool(_EMPIRICAL.search(t)), bool(_THEORY.search(t)),
                        bool(_STRATEGY.search(t)))
    if emp and doc_type in ("articulo", "informe"):
        return "evidencia_empirica"
    if strat and (emp or doc_type in ("preprint", "libro")):
        return "estrategia_documentada"
    if theo:
        return "teoria"
    return "evidencia_empirica" if emp else "hipotesis"


_DASHES = str.maketrans({c: "-" for c in "‐‑‒–—−"})


def norm(text: str) -> str:
    """Sin tildes, en minúsculas y con todos los guiones como «-» (los registros mezclan)."""
    return fold(text.translate(_DASHES))


def stance_check(ref: DigitalRef, text: str) -> tuple[list[str], list[str]]:
    """(conceptos con postura verificada en el texto, conceptos con postura pendiente)."""
    t = norm(text)
    ok, pending = [], []
    for s in ref.curated.stances:
        hit = bool(s.terms) and bool(t) and all(norm(x) in t for x in s.terms)
        (ok if hit else pending).append(s.concept)
    return ok, pending


def extract(ref: DigitalRef, text: str, coverage: Coverage, now: str,
            max_items: int = 3) -> DigitalCard:
    """Ficha de conocimiento de una referencia a partir de lo que se pudo leer."""
    t = fold(text)
    sents = sentences(text)
    findings = [f for s in sents if _FINDING.search(fold(s)) if (f := fragment(s, coverage))]
    limits = [f for s in sents if _LIMIT.search(fold(s)) if (f := fragment(s, coverage))]
    rules = [f.text for s in sents
             if _RULE.search(fold(s)) and _NUMBER.search(s) if (f := fragment(s, coverage))]
    doc_type = ref.verified.doc_type if ref.verified else "otro"
    ok, pending = stance_check(ref, text)
    return DigitalCard(
        ref_id=ref.id, coverage=coverage if text else "metadatos",
        concepts=detect(text) if text else [], methods=_found(METHODS, t),
        conditions=_found(CONDITIONS, t), limitations=limits[:max_items],
        findings=[f for f in findings if f not in limits][:max_items],
        level=level_of(text, doc_type) if text else "hipotesis",
        stances_verified=ok, stances_pending=pending, operational_rules=rules[:max_items],
        extracted_at=now)
