"""Banco emparejado de salidas (T131): las MISMAS entradas, el mismo tamaño, solo cambia la salida.

Diseño de §5.3 de `PLAN/notas/T129_sl_dinamico.md`:
- **Emparejado:** todas las ideas de todas las estrategias, con **tamaño fijo** y **sin la memoria
  de los perfiles** (ni pesos, ni pausas, ni cupos, ni capital): lo único que distingue dos
  columnas es la regla de salida. El tamaño sale del riesgo pre-registrado y de la geometría
  DECLARADA de la idea (entrada y SL), nunca del llenado, así que es el mismo para todas las
  políticas y no depende de cuál se mida.
- **Sin cuenta:** no hay margen ni liquidación, porque no hay apalancamiento declarado. Lo que se
  compara es el R de la salida; el libro completo de cada perfil es el análisis secundario (T111).
- Una idea entra en la comparación emparejada solo si TODAS las políticas la cerraron dentro del
  camino. Las demás se cuentan aparte por motivo: así se ve qué deja fuera cada salida.

Puro: sin red y sin disco.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from eim.paper.engine import Outcome
from eim.paper.exits.policy import ExitContext, ExitPolicy
from eim.paper.ideas import Idea
from eim.paper.ladder import floor_qty
from eim.paper.ladder_metrics import cost_of
from eim.paper.params import SymbolSpec

CONTROL_STRATEGY = "control_aleatorio"      # entradas al azar: el control de §5.3


@dataclass(frozen=True)
class BenchTrade:
    """Una operación del banco: lo que las métricas de §5.3 necesitan y nada más."""

    id: str
    policy: str
    t: int                       # instante de la decisión (define el día del bootstrap)
    fill_t: int
    exit_t: int
    side: int
    sid: str                     # estrategia@marco
    timeframe: str
    regime: str
    origin: str
    reason: str
    qty: float
    risk_usd: float
    pnl_usd: float               # neto, al tamaño fijo del banco
    gross_usd: float
    cost_usd: float
    r: float                     # neto en R
    gross_r: float
    cost_r: float
    mfe_r: float
    mae_r: float
    elapsed_ms: int

    @property
    def day(self) -> int:
        return self.t // 86_400_000


def qty_for(idea: Idea, spec: SymbolSpec, risk_usd: float) -> float:
    """Cantidad de tamaño fijo: `risk_usd` entre la distancia DECLARADA al SL, al paso del
    instrumento. 0 si no llega al mínimo negociable o la geometría no es válida."""
    ref = idea.entry if idea.entry else 0.0
    dist = abs(ref - idea.sl)
    if ref <= 0 or dist <= 0 or risk_usd <= 0:
        return 0.0
    q = floor_qty(risk_usd / dist, spec.qty_step)
    return q if q >= spec.min_qty else 0.0


def as_trade(o: Outcome, policy: str, qty: float) -> BenchTrade | None:
    """`Outcome` cerrado → operación del banco al tamaño fijo. None si no cerró."""
    if o.status != "CERRADA" or o.r is None or o.fill is None or o.exit_t is None:
        return None
    i = o.idea
    notional = qty * o.fill
    risk_usd = qty * abs(o.fill - i.sl)
    cost = (o.fee_in + o.fee_out + o.slip + o.funding) * notional
    return BenchTrade(
        id=i.id, policy=policy, t=i.t, fill_t=int(o.fill_t or i.t), exit_t=int(o.exit_t),
        side=i.side, sid=i.sid, timeframe=i.timeframe, regime=i.regime or "sin dato",
        origin=i.origin, reason=o.reason, qty=qty, risk_usd=risk_usd,
        pnl_usd=notional * o.net, gross_usd=notional * o.gross, cost_usd=cost,
        r=float(o.r), gross_r=o.gross / o.risk if o.risk > 0 else 0.0,
        cost_r=cost_of({"fees": o.fee_in + o.fee_out, "slip": o.slip, "funding": o.funding})
        / o.risk if o.risk > 0 else 0.0,
        mfe_r=o.mfe_r, mae_r=o.mae_r, elapsed_ms=int(o.exit_t) - int(o.fill_t or i.t))


@dataclass(frozen=True)
class Row:
    """Una idea con el resultado de cada política (None si esa salida no la cerró)."""

    id: str
    t: int
    qty: float
    by_policy: dict[str, BenchTrade | None]
    status: dict[str, str]        # estado del `Outcome` por política (para contar lo excluido)

    @property
    def complete(self) -> bool:
        return all(x is not None for x in self.by_policy.values())


@dataclass(frozen=True)
class Bench:
    """Resultado de una corrida: las filas emparejadas y el recuento de lo que quedó fuera."""

    rows: tuple[Row, ...]
    policies: tuple[str, ...]
    skipped_qty: int              # ideas sin cantidad negociable con el riesgo fijo
    dropped: dict[str, dict[str, int]]   # política → estado → cuántas

    def paired(self) -> list[Row]:
        """Filas que TODAS las políticas cerraron: la única comparación emparejada honesta."""
        return [r for r in self.rows if r.complete]

    def trades(self, policy: str, paired_only: bool = True) -> list[BenchTrade]:
        src = self.paired() if paired_only else self.rows
        return [t for r in src if (t := r.by_policy.get(policy)) is not None]

    def diffs(self, policy: str, base: str) -> list[tuple[int, float]]:
        """(día, ΔR) frente a `base` sobre las filas emparejadas: la serie del bootstrap."""
        return [(r.by_policy[policy].day, r.by_policy[policy].r - r.by_policy[base].r)
                for r in self.paired()]

    def to_json(self) -> dict:
        return {"policies": list(self.policies), "ideas": len(self.rows),
                "paired": len(self.paired()), "skipped_qty": self.skipped_qty,
                "dropped": self.dropped}


def run(ideas: Sequence[Idea], policies: Sequence[ExitPolicy], ctx: ExitContext,
        risk_usd: float) -> Bench:
    """Corre todas las políticas sobre las mismas ideas con el mismo tamaño fijo."""
    ids = tuple(p.id for p in policies)
    if len(set(ids)) != len(ids):
        raise ValueError(f"políticas con identificador repetido: {sorted(ids)}")
    rows, skipped = [], 0
    dropped: dict[str, dict[str, int]] = {p.id: {} for p in policies}
    for idea in sorted(ideas, key=lambda x: (x.t, x.id)):
        qty = qty_for(idea, ctx.spec, risk_usd)
        if qty <= 0:
            skipped += 1
            continue
        by, status = {}, {}
        for p in policies:
            o = p.simulate(idea, ctx, qty)
            status[p.id] = o.status
            by[p.id] = as_trade(o, p.id, qty)
            if by[p.id] is None:
                d = dropped[p.id]
                d[o.status] = d.get(o.status, 0) + 1
        rows.append(Row(idea.id, idea.t, qty, by, status))
    return Bench(tuple(rows), ids, skipped, dropped)


def control_ideas(ideas: Sequence[Idea]) -> list[Idea]:
    """Entradas del control aleatorio (§5.3): si una salida las vuelve rentables más allá del
    ruido, hay un error o anticipación y la salida se rechaza."""
    return [i for i in ideas if i.strategy == CONTROL_STRATEGY]


def real_ideas(ideas: Sequence[Idea]) -> list[Idea]:
    """Las ideas de las estrategias, sin el control (que se mide aparte)."""
    return [i for i in ideas if i.strategy != CONTROL_STRATEGY]
