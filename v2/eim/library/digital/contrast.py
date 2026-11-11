"""Motor de contraste entre estrategias y literatura (T153), puro.

Dada una operación (o idea) del bróker, elige solo los conceptos pertinentes (los de su estrategia,
el contexto y la gestión del riesgo; nunca las ~100 fuentes) y devuelve qué metodologías la
respaldan, cuáles la contradicen y cuáles la condicionan o podrían mejorarla.

Dirección: la literatura de tendencia y momentum respalda operar **a favor** de la tendencia. Si la
operación va contra la tendencia declarada, esas posturas cuentan en contra de esta operación
(y la de reversión a la media, a favor).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from eim.library.digital.consensus import KnowledgeBase, consensus
from eim.library.digital.taxonomy import METHOD_CONCEPTS, strategy_concepts, strategy_context

TREND = frozenset({"trend_following", "momentum", "breakout", "time_series"})
REVERSION = frozenset({"mean_reversion", "support_resistance"})
RISK = ("stop_loss", "position_sizing", "execution_costs")
IMPROVE = {  # concepto de gestión → cómo podría mejorar la operación
    "vol_targeting": "Dimensionar por volatilidad (riesgo constante en ATR).",
    "multiple_testing": "Juzgar la estrategia contra el máximo esperado por azar "
                        "(Holm/Romano-Wolf).",
    "trailing_stop": "Revisar la salida dinámica: su valor depende del proceso de precios.",
    "execution_costs": "Incluir costos de ida y vuelta en R antes de juzgar la relación R/B.",
    "position_sizing": "Kelly fraccionado sobre el límite inferior de E[R]: sin ventaja medida, 0.",
    "stop_loss": "Un stop ceñido con costos resta valor salvo con autocorrelación positiva.",
    "momentum_crash": "Reducir exposición de tendencia en rebotes tras pánico.",
    "regime": "Condicionar la estrategia al régimen detectado.",
}


@dataclass(frozen=True)
class TradeContext:
    """Lo mínimo que el contraste necesita de una operación o idea (todo opcional salvo lado)."""

    side: int                       # +1 compra, −1 venta
    strategy: str = ""
    family: str = ""
    timeframe: str = ""
    regime: str | None = None
    trend: int = 0                  # +1 alcista, −1 bajista, 0 desconocida
    profile: str | None = None

    @property
    def direction(self) -> int:
        """Tendencia declarada o, si no, la del régimen (`trend_up`/`trend_down`)."""
        if self.trend:
            return self.trend
        r = (self.regime or "").lower()
        return 1 if "up" in r or "alcista" in r else -1 if "down" in r or "bajista" in r else 0

    @property
    def ranging(self) -> bool:
        return (self.regime or "").lower() in ("range", "rango", "lateral")

    def key(self) -> tuple:
        return (self.side, self.strategy.split("@")[0], self.family, self.timeframe,
                self.regime, self.trend)


def relevant_concepts(ctx: TradeContext) -> tuple[list[str], list[str]]:
    """(conceptos de la entrada, conceptos de contexto y riesgo), sin repetir."""
    s = ctx.strategy or ctx.family
    entry = [c for c in strategy_concepts(s) if c not in METHOD_CONCEPTS]
    extra = [c for c in (*strategy_context(s), *RISK, "regime" if ctx.regime else "",
                         "crypto_returns", "liquidation", "vol_targeting") if c and c not in entry]
    return entry, extra


def _directional(d: dict, concept: str, ctx: TradeContext) -> dict:
    """Ajusta el veredicto al sentido de la operación respecto de la tendencia."""
    if ctx.ranging and concept in TREND and d["verdict"] == "a favor":
        return {**d, "verdict": "condicionado", "direction_note":
                "Régimen lateral: la evidencia de tendencia se estudió en mercados con tendencia."}
    against = ctx.direction != 0 and ctx.direction * ctx.side < 0
    if not against or concept not in TREND | REVERSION:
        return {**d, "direction_note": None}
    if concept in TREND:
        flip = {"a favor": "en contra", "en contra": "a favor"}
        note = "La operación va contra la tendencia: la evidencia de tendencia cuenta en contra."
    else:
        flip, note = {}, "La operación va contra la tendencia: es una apuesta de reversión."
    return {**d, "verdict": flip.get(d["verdict"], d["verdict"]),
            "support": d["objections"] if flip else d["support"],
            "objections": d["support"] if flip else d["objections"],
            "net": -d["net"] if flip else d["net"], "direction_note": note}


def contrast(kb: KnowledgeBase, ctx: TradeContext, k: int = 3) -> dict:
    """Coincidencias, contradicciones y condiciones de aplicación para una operación."""
    entry, extra = relevant_concepts(ctx)
    rows = {c: _directional(consensus(kb, c, k), c, ctx) for c in entry + extra}
    backs = [c for c in entry if rows[c]["verdict"] == "a favor"]
    against = [c for c in entry if rows[c]["verdict"] == "en contra"]
    mixed = [c for c in entry if rows[c]["verdict"] in ("dividido", "condicionado")]
    improve = [{"concept": c, "text": IMPROVE[c]} for c in extra + entry
               if c in IMPROVE and rows.get(c, {}).get("verdict") != "sin evidencia"]
    if backs and not against:
        summary = "La literatura respalda la metodología de la entrada"
    elif against and not backs:
        summary = "La literatura contradice la metodología de la entrada"
    elif backs and against:
        summary = "La literatura está dividida sobre la entrada"
    else:
        summary = "Sin consenso bibliográfico sobre la entrada"
    return {
        "context": {"side": ctx.side, "strategy": ctx.strategy, "family": ctx.family,
                    "timeframe": ctx.timeframe, "regime": ctx.regime, "trend": ctx.direction},
        "entry_concepts": entry, "context_concepts": extra,
        "summary": summary + " (complemento, no señal ni veto).",
        "backs": backs, "contradicts": against, "conditional": mixed,
        "improvements": improve[:4], "concepts": rows,
        "sources_consulted": len({e["source_id"] for r in rows.values()
                                  for e in r["support"] + r["objections"] + r["conditions"]}),
    }


class CachedContrast:
    """Contraste con caché por contexto (las ideas del bróker repiten contexto a menudo)."""

    def __init__(self, kb: KnowledgeBase, size: int = 512) -> None:
        self.kb = kb
        self._fn = lru_cache(maxsize=size)(self._run)

    def _run(self, key: tuple, ctx: TradeContext) -> dict:
        return contrast(self.kb, ctx)

    def __call__(self, ctx: TradeContext) -> dict:
        return self._fn(ctx.key(), ctx)
