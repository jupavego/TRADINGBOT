"""Lo vivo manda (T182): lo reconstruido solo pesa como opinión inicial acotada (funciones puras).

Las velas reconstruidas (`origin != "vivo"`: la puesta al día tras un apagado, el antiguo botón de
backtest o un laboratorio) no se decidieron en tiempo real. Con `ExecParams.live_first` no entran
en los libros de los perfiles y, en el aprendizaje, sus resultados forman una opinión inicial
(*prior*): sus sumas ponderadas, con el mismo decaimiento que lo vivo, se escalan para valer como
mucho `cap` operaciones y además envejecen como si fueran anteriores a todo lo vivo
(× 0,5^(cierres vivos / vida media)). Con cero cierres vivos el prior habla con `cap`
operaciones; con 40 cierres vivos y vida media 40, con la mitad; con muchos, casi nada. Si lo vivo
contradice a lo reconstruido, gana lo vivo. Solo cuentan los cierres con `exit_t ≤ t`: el juicio
en `t` no conoce el futuro.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable, Sequence
from dataclasses import replace

from eim.paper.engine import Outcome
from eim.paper.feedback import (
    Judgement,
    Learner,
    _decayed_sums,
    _index,
    _verdict,
    closed,
    context_key,
)
from eim.paper.params import FeedbackParams

PriorSums = tuple[int, float, float, float]      # (n, Σw, Σw·r, Σw·r²) de lo reconstruido
EMPTY: PriorSums = (0, 0.0, 0.0, 0.0)


def is_live(o: Outcome) -> bool:
    return o.idea.origin == "vivo"


class Prior:
    """Cierres reconstruidos por estrategia@marco y por contexto, con sus sumas por prefijo."""

    def __init__(self, closes: Iterable[tuple[str, str, int, float]]) -> None:
        """`closes`: (estrategia@marco, contexto, exit_t, R) de cada cierre reconstruido."""
        by: dict[str, list[tuple[int, float]]] = {}
        ctx: dict[str, list[tuple[int, float]]] = {}
        for sid, ck, t, r in closes:
            by.setdefault(sid, []).append((t, r))
            ctx.setdefault(ck, []).append((t, r))
        self._t, self._r = _index(by)
        self._ct, self._cr = _index(ctx)
        self._sums: dict[tuple, list[tuple[float, float, float]]] = {}

    @classmethod
    def from_outcomes(cls, outcomes: Iterable[Outcome]) -> Prior:
        return cls((o.idea.sid, context_key(o), o.exit_t, o.r) for o in closed(outcomes))

    def __len__(self) -> int:
        return sum(len(v) for v in self._r.values())

    def _at(self, ts: dict[str, list[int]], rs: dict[str, list[float]], key: str, t: int,
            half_life: float) -> PriorSums:
        n = bisect_right(ts.get(key, []), t)
        if n == 0:
            return EMPTY
        sk = (id(rs), key, half_life)
        sums = self._sums.get(sk)
        if sums is None:
            sums = self._sums[sk] = _decayed_sums(rs[key], half_life)
        return (n, *sums[n])

    def strategy(self, sid: str, t: int, half_life: float) -> PriorSums:
        return self._at(self._t, self._r, sid, t, half_life)

    def context(self, ck: str, t: int, half_life: float) -> PriorSums:
        return self._at(self._ct, self._cr, ck, t, half_life)


def blend(n_live: int, live: tuple[float, float, float], prior: PriorSums, cap: float,
          half_life: float) -> tuple[int, float, float, float, float]:
    """Sumas de lo vivo más el prior acotado: (n, Σw, Σw·r, Σw·r², peso del prior)."""
    _n, sw_b, s1_b, s2_b = prior
    if cap <= 0 or sw_b <= 0:
        return n_live, *live, 0.0
    k = min(1.0, cap / sw_b) * 0.5 ** (n_live / half_life)
    w = k * sw_b
    return n_live + round(w), live[0] + w, live[1] + k * s1_b, live[2] + k * s2_b, w


def judge_blend(rs: Sequence[float], prior: PriorSums, p: FeedbackParams,
                cap: float) -> Judgement:
    """`feedback.judge` sobre los cierres vivos `rs` con la opinión inicial `prior`."""
    live = _decayed_sums(rs, p.half_life)[-1]
    n, sw, s1, s2, w = blend(len(rs), live, prior, cap, p.half_life)
    return replace(_verdict(n, sw, s1, s2, p), n_live=len(rs), prior=w)


class LiveFirstLearner(Learner):
    """`Learner` de la sombra en el que lo vivo manda: juzga con los cierres vivos y usa lo
    reconstruido solo como prior acotado (lo usan los perfiles que aprenden de la sombra y las
    cifras de la pestaña Aprendizaje)."""

    def __init__(self, outcomes: Iterable[Outcome], cap: float) -> None:
        outs = list(outcomes)
        super().__init__(o for o in outs if is_live(o))
        self.prior = Prior.from_outcomes(o for o in outs if not is_live(o))
        self.cap = cap

    def _judge(self, ts: dict[str, list[int]], rs: dict[str, list[float]], key: str, t: int,
               p: FeedbackParams) -> Judgement:
        n = bisect_right(ts.get(key, []), t)
        if n:
            sk = (id(rs), key, p.half_life)
            sums = self._sums.get(sk)
            if sums is None:
                sums = self._sums[sk] = _decayed_sums(rs[key], p.half_life)
            live = sums[n]
        else:
            live = (0.0, 0.0, 0.0)
        pri = (self.prior.strategy(key, t, p.half_life) if ts is self._t
               else self.prior.context(key, t, p.half_life))
        k, sw, s1, s2, w = blend(n, live, pri, self.cap, p.half_life)
        return replace(_verdict(k, sw, s1, s2, p), n_live=n, prior=w)
