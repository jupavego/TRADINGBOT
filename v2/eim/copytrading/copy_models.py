"""Contratos de la copia simulada (T42): señal del líder, precio del seguidor, orden y bitácora.

Toda cifra lleva su fuente: el precio de cada orden dice si salió de una cotización grabada
(`bbo`), del precio medio (`allMids` + medio diferencial supuesto), de una vela de 1 min
(+ deslizamiento T25) o de la marca/precio del líder (supuesto).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

from eim.copytrading.trades import _chained
from eim.core.leaders import LeaderFill
from eim.core.market import Frozen

MODE = "SIMULADO"
PriceSrc = Literal["bbo", "allMids", "vela_1m", "marca", "lider"]
# señal, decisión, riesgo, orden, rechazo, stop, funding, reconciliación, pausa, reanudación,
# kill-switch, inicio
EntryKind = Literal["signal", "decision", "risk", "order", "reject", "stop", "funding", "recon",
                    "pause", "resume", "kill", "start"]


class Signal(Frozen):
    """Cambio de posición del líder en una moneda: ejecuciones vistas a la vez (mismo
    mensaje) agrupadas. `start`/`end` firmados (> 0 largo)."""

    leader_id: str
    coin: str
    t: int  # hora del exchange de la última ejecución
    observed_at: int  # cuándo lo vimos (latencia = observed_at − t)
    start: float
    end: float
    vwap: float  # precio medio ponderado de las ejecuciones del grupo
    size: float
    fills: int
    keys: tuple[tuple[int, int], ...]  # (tid, oid) de cada ejecución
    channel: str
    leader_fee: float = 0.0
    leader_pnl: float = 0.0
    open_t: int | None = None  # hora de la ejecución que abre un viaje (apertura o giro)

    @property
    def latency_ms(self) -> int:
        return self.observed_at - self.t

    @property
    def last_key(self) -> tuple[int, int]:
        return self.keys[-1]


class ExecQuote(Frozen):
    """Precio al que habría operado el seguidor en `at` (orden) con la cotización de `t`."""

    t: int
    at: int
    mid: float
    bid: float | None = None
    ask: float | None = None
    src: PriceSrc

    def price(self, side: int, half_spread: float) -> float:
        """Compra al ask y vende al bid; sin libro, medio ± medio diferencial supuesto."""
        if side > 0 and self.ask is not None:
            return self.ask
        if side < 0 and self.bid is not None:
            return self.bid
        return self.mid * (1 + half_spread * side)


class CopyFill(Frozen):
    """Orden simulada ejecutada. `side` = dirección de la orden (+1 compra, −1 venta)."""

    leader_id: str
    coin: str
    t: int
    kind: Literal["open", "increase", "reduce", "close", "stop", "kill"]
    side: int
    qty: float
    price: float
    mid: float | None = None
    leader_px: float | None = None  # precio medio del líder en la señal (None: stop/kill)
    fee: float
    realized: float = 0.0  # PnL cerrado por esta orden (sin comisión)
    src: PriceSrc
    trip_t: int | None = None  # viaje del líder al que pertenece
    signal_t: int | None = None
    latency_ms: int | None = None  # orden − ejecución del líder


class JournalEntry(Frozen):
    leader_id: str
    seq: int
    t: int
    kind: EntryKind
    coin: str = ""
    code: str = ""
    text: str
    data: dict = {}


def _signal(fs: list[LeaderFill]) -> Signal:
    size = sum(f.size for f in fs)
    return Signal(
        leader_id=fs[0].leader_id, coin=fs[0].symbol, t=max(f.t for f in fs),
        observed_at=fs[0].observed_at, start=fs[0].start_position, end=fs[-1].end_position,
        vwap=sum(f.price * f.size for f in fs) / size, size=size, fills=len(fs),
        keys=tuple((f.tid, f.oid) for f in fs), channel=fs[-1].channel,
        leader_fee=sum(f.fee for f in fs), leader_pnl=sum(f.closed_pnl for f in fs),
        open_t=next((f.t for f in reversed(fs) if f.action in ("open", "flip")), None))


def group_fills(fills: list[LeaderFill]) -> list[Signal]:
    """Ejecuciones de un líder → señales por (moneda, instante en que se vieron), en orden.
    Una orden que cruza varios niveles llega como varias ejecuciones en el mismo mensaje.
    Un lote visto a la vez (relleno REST tras un corte) se parte en cada cierre o giro: así
    un viaje terminado durante el corte no se confunde con un aumento."""
    groups: dict[tuple[str, int], list[LeaderFill]] = defaultdict(list)
    for f in fills:
        groups[(f.symbol, f.observed_at)].append(f)
    out: list[Signal] = []
    for raw in groups.values():
        cur: list[LeaderFill] = []
        for f in _chained(sorted(raw, key=lambda f: (f.t, f.tid))):
            cur.append(f)
            if f.action in ("close", "flip"):
                out.append(_signal(cur))
                cur = []
        if cur:
            out.append(_signal(cur))
    return sorted(out, key=lambda s: s.observed_at)  # estable: respeta la cadena por moneda
