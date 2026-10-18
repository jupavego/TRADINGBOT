"""Búsqueda léxica BM25 propia (T52), pura: sin red, sin disco, sin dependencias.

Cada documento es un fragmento de ~1 página. Normalización: minúsculas, sin tildes, solo
letras y dígitos; palabras vacías en inglés y español fuera.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Sequence

_WORD = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    "a an and are as at be but by for from has have he her his i if in into is it its of on or "
    "our she so than that the their them then there these they this to was we were what when "
    "which who will with you your not no can do does did been would could should "
    "el la los las un una unos unas y o de del al en con por para es son fue que se su sus lo "
    "le les mas pero como este esta esto ese esa eso ya muy sin sobre entre cuando donde".split()
)


def fold(text: str) -> str:
    """Minúsculas y sin tildes (para comparar texto de libros y consultas)."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def words(text: str) -> list[str]:
    """Palabras normalizadas, incluidas las vacías (para comparar citas textuales)."""
    return _WORD.findall(fold(text))


def tokenize(text: str) -> list[str]:
    return [w for w in words(text) if w not in STOPWORDS and len(w) > 1]


class BM25:
    """Índice BM25 (Okapi) en memoria sobre documentos ya tokenizados."""

    def __init__(self, docs: Sequence[Sequence[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tf = [Counter(d) for d in docs]
        self.len = [len(d) for d in docs]
        self.avg = (sum(self.len) / len(docs)) if docs else 0.0
        df: Counter[str] = Counter()
        for c in self.tf:
            df.update(c.keys())
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def score(self, query: Sequence[str], i: int) -> float:
        tf, dl = self.tf[i], self.len[i]
        norm = self.k1 * (1 - self.b + self.b * dl / self.avg) if self.avg else self.k1
        s = 0.0
        for t in set(query):
            f = tf.get(t, 0)
            if f:
                s += self.idf[t] * f * (self.k1 + 1) / (f + norm)
        return s

    def top(self, query: Sequence[str], k: int = 10) -> list[tuple[int, float]]:
        """Los `k` documentos con mayor puntuación > 0, de mayor a menor (empate: orden)."""
        if not query:
            return []
        scored = [(i, self.score(query, i)) for i in range(len(self.tf))]
        scored = [x for x in scored if x[1] > 0]
        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored[:k]


def snippet(text: str, query: Sequence[str], width: int = 240) -> str:
    """Ventana corta del texto con más términos de la consulta (para ubicar el pasaje)."""
    flat = " ".join(text.split())
    if len(flat) <= width:
        return flat
    q = set(query)
    spans = [m for m in re.finditer(r"\S+", flat) if set(tokenize(m.group())) & q]
    if not spans:
        return flat[:width].rsplit(" ", 1)[0] + " …"
    best, best_hits = 0, -1
    for s in spans:
        start = max(0, s.start() - width // 4)
        hits = sum(1 for o in spans if start <= o.start() < start + width)
        if hits > best_hits:
            best, best_hits = start, hits
    if best:
        best = flat.find(" ", best) + 1
    out = flat[best:best + width].rsplit(" ", 1)[0]
    return ("… " if best else "") + out + " …"
