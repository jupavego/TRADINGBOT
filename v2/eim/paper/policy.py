"""Autoridad del bróker simulado (T114): decide si un perfil toma una idea y con qué tamaño.

Es la política de riesgo determinista de cada perfil, registrada en `eim/risk/authority.py`
como `paper.broker` para la fuente `paper.strategies`: primero la ruta de la puerta única
(fuente registrada, activa y con ese modo de salida), luego los vetos del perfil (`vetoes.py`,
con el mínimo de abiertas que solo salta los blandos), el tope por dirección (`caps.py`), el
margen libre y, con escalera, la cantidad negociable (`ladder_book.open_ladder`). Es el mismo
código que vivía en `book._signal`: ninguna decisión cambia (las suites de `tests/paper` lo
fijan). El libro solo abre desde una `PaperDecision` aprobada por aquí (`book._open`).

`PaperDecision.as_record` la proyecta al contrato único `RiskDecision` (con la `TradeProposal`
de la idea) para registrarla en el Observatorio; en el bucle caliente no se construye ningún
modelo pydantic (el libro decide ≈ 250 000 ideas por cálculo de la vista).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from eim.core import Mode
from eim.core.authority import RiskDecision, params_fingerprint
from eim.paper.account import leverage_for
from eim.paper.book_events import learned_bad
from eim.paper.caps import fit_risk
from eim.paper.engine import Outcome
from eim.paper.feedback import Judgement
from eim.paper.ladder_book import LadderSim, open_ladder
from eim.paper.params import ProfileParams
from eim.paper.vetoes import vetoes
from eim.risk.authority import route_reason

if TYPE_CHECKING:
    from eim.paper.book import ProfileState

SOURCE = "paper.strategies"
AUTHORITY = "paper.broker"
POLICY_VERSION = "paper_policy_v1"     # vetos + topes + tamaño del libro (T47–T109)
EXIT_OF = {"ladder": "stop_only", "tp": "sl_tp_time"}
_GRANT = object()                      # solo `decide` firma una decisión aprobada


@dataclass(frozen=True, slots=True)
class PaperDecision:
    """Lo que la política decidió sobre una idea para un perfil (ligero: sin validación)."""

    o: Outcome                         # el resultado que se abre (la escalera lo reescribe)
    approved: bool
    reasons: tuple[str, ...] = ()      # vetos (el primero es el que se muestra) o la nota
    qty: float = 0.0
    leverage: int = 0
    margin: float = 0.0
    weight: float = 0.0
    risk_usd: float = 0.0
    entry: float = 0.0                 # precio al que se dimensionó
    equity: float = 0.0                # capital realizado al decidir
    floor: bool = False
    skipped: tuple[str, ...] = ()
    note: str = ""                     # texto añadido a la orden (mínimo de abiertas)
    grant: object = None

    @property
    def reason(self) -> str:
        return self.reasons[0] if self.reasons else ""

    def as_record(self, p: ProfileParams) -> RiskDecision:
        """La decisión en el contrato único, con la propuesta de la idea (Observatorio, T114)."""
        i, exit_mode = self.o.idea, EXIT_OF[p.exit_mode]
        dump = p.model_dump_json().encode("utf-8")
        return RiskDecision(
            approved=self.approved, symbol=i.symbol, timeframe=i.timeframe, plan_id=i.id,
            side=i.side, mode=Mode.SIMULADO, asof=i.t, decided_at=i.t, size=self.qty,
            notional=self.qty * self.entry, leverage=float(self.leverage), margin=self.margin,
            risk_amount=self.risk_usd,
            risk_frac=self.risk_usd / self.equity if self.equity > 0 else 0.0,
            entry=i.entry, sized_at=self.entry or i.entry, sl=i.sl,
            tp=() if p.exit_mode == "ladder" else (i.tp,), reasons=self.reasons,
            config_version=POLICY_VERSION, config_sha256=hashlib.sha256(dump).hexdigest(),
            account_source=f"perfil {p.id}: capital realizado {self.equity:.2f} USDT (SIMULADO)",
            proposal=i.as_proposal(), authority=AUTHORITY, profile_version=params_fingerprint(p),
            exit_mode=exit_mode)  # type: ignore[arg-type]


def _no(o: Outcome, *why: str, equity: float = 0.0) -> PaperDecision:
    return PaperDecision(o=o, approved=False, reasons=tuple(why), equity=equity)


def open_count(st: ProfileState) -> int:
    """Operaciones abiertas: posiciones llenadas y órdenes a mercado (se llenan a la apertura)."""
    return sum(1 for s in st.slots.values() if s.filled or s.o.idea.kind == "market")


def pending_count(st: ProfileState) -> int:
    """Órdenes de entrada pendientes: límites colocados y aún sin llenar."""
    return sum(1 for s in st.slots.values() if not s.filled and s.o.idea.kind == "limit")


def decide(st: ProfileState, o: Outcome, j: Judgement, jc: Judgement, ck: str, mmr: float,
           sim: LadderSim | None) -> PaperDecision:
    i, p, eq = o.idea, st.p, st.equity
    if why := route_reason(SOURCE, AUTHORITY, EXIT_OF[p.exit_mode]):
        return _no(o, f"puerta única: {why}", equity=eq)
    vs = vetoes(st, i, j, jc, ck)
    floor, skipped = False, ()
    if vs:
        # los mínimos solo saltan vetos blandos: a mercado cubren las posiciones abiertas y a
        # límite las órdenes pendientes (sin elegir por el resultado de la idea)
        keys = tuple(k for _, k in vs)
        short = (open_count(st) < p.min_open if i.kind == "market"
                 else pending_count(st) < p.min_pending)
        if None in keys or not short or learned_bad(st, keys, i.t, o):
            return _no(o, *(t for t, _ in vs), equity=eq)
        floor, skipped = True, keys
    weight = p.floor_weight if floor else j.weight
    entry = o.fill if i.kind == "market" and o.fill else i.entry
    want = eq * p.risk_pct * weight
    risk_usd = fit_risk(p.caps, eq, sum(x.risk_usd for x in st.slots.values()
                                        if x.side == i.side), want)
    if risk_usd <= 0:
        return _no(o, f"capital insuficiente: {eq:.2f} USDT realizados" if want <= 0 else
                   f"tope de riesgo abierto por dirección ({p.caps.max_dir_risk:.1%})", equity=eq)
    qty = risk_usd / abs(entry - i.sl)
    lev = leverage_for(p, entry, i.sl, mmr)
    margin = qty * entry / lev
    free = eq - st.used
    if margin > free:
        scale = max(0.0, free * 0.98 / margin)
        if scale < p.min_risk_fill:
            return _no(o, f"margen insuficiente (libre {free:.2f} USDT)", equity=eq)
        qty, margin, risk_usd = qty * scale, margin * scale, risk_usd * scale
    if sim is not None and p.exit_mode == "ladder":
        qty, o = open_ladder(p, sim, i, qty)
        if o.status == "RECHAZADA":
            return _no(o, "cantidad bajo el paso mínimo o geometría inválida", equity=eq)
        margin, risk_usd = qty * entry / lev, qty * abs(entry - i.sl)
    note = ""
    if floor:
        what = f"{p.min_open} abierta(s)" if i.kind == "market" else f"{p.min_pending} pendiente(s)"
        note = f" · mínimo de {what}: se omitió «{vs[0][0]}»"
    return PaperDecision(o=o, approved=True, reasons=(note.lstrip(" ·"),) if note else (),
                         qty=qty, leverage=lev, margin=margin, weight=weight, risk_usd=risk_usd,
                         entry=entry, equity=eq, floor=floor, skipped=skipped, note=note,
                         grant=_GRANT)


def verify(d: PaperDecision) -> None:
    """Lanza `PermissionError` si `d` no es una aprobación de esta política con ruta vigente."""
    if d.grant is not _GRANT or not d.approved:
        raise PermissionError("el libro solo abre con una decisión aprobada por la política")
    if why := route_reason(SOURCE, AUTHORITY, None):
        raise PermissionError(f"ruta no autorizada: {why}")
