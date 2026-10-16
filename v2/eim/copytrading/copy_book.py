"""Subcuenta virtual (pura): saldo, posiciones, comisiones, funding, stops y marcas. SIMULADO.

Perpetuo lineal con margen en USDC: capital = saldo + PnL latente a la última marca. El saldo
cambia con el PnL cerrado, las comisiones (tomador) y el funding horario (Hyperliquid:
pago = −tamaño × precio × tasa; tasa > 0 → el largo paga). El funding se aplica con la
posición que tenía la subcuenta a la hora del pago (`size_at`), una vez por (moneda, hora).
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import asdict, dataclass, field

DAY_MS = 86_400_000
_MONDAY0 = 4 * DAY_MS  # 1970-01-05 fue lunes
KEEP_TIMELINE_MS = 3 * DAY_MS
CURVE_MAX = 5_000


def day0(t: int) -> int:
    return t - t % DAY_MS


def week0(t: int) -> int:
    return t - (t - _MONDAY0) % (7 * DAY_MS)


def _sgn(x: float) -> int:
    return (x > 0) - (x < 0)


@dataclass
class Position:
    coin: str
    size: float = 0.0  # firmado
    entry: float = 0.0
    stop: float | None = None
    trip_t: int | None = None  # viaje del líder que copia
    opened_t: int | None = None
    net: float = 0.0  # resultado del viaje propio: PnL − comisiones + funding


@dataclass
class ClosedTrip:
    coin: str
    trip_t: int | None
    opened_t: int | None
    closed_t: int
    net: float


@dataclass
class Account:
    equity0: float
    t0: int
    balance: float = 0.0
    positions: dict[str, Position] = field(default_factory=dict)
    marks: dict[str, tuple[int, float]] = field(default_factory=dict)
    fees: float = 0.0
    funding: float = 0.0
    realized: float = 0.0
    peak: float = 0.0
    max_dd: float = 0.0
    day_t: int = 0
    day_start: float = 0.0
    week_t: int = 0
    week_start: float = 0.0
    streak: int = 0
    last_loss_t: int | None = None
    trips: int = 0
    wins: int = 0
    timeline: dict[str, list[list[float]]] = field(default_factory=dict)  # [t, tamaño]
    funded: dict[str, int] = field(default_factory=dict)  # "moneda:t" → t
    curve: list[list[float]] = field(default_factory=list)  # [t, capital]

    def __post_init__(self) -> None:
        if not self.balance and not self.peak:
            self.balance = self.peak = self.day_start = self.week_start = self.equity0
            self.day_t, self.week_t = day0(self.t0), week0(self.t0)

    # --- lectura ------------------------------------------------------------------------------
    def size(self, coin: str) -> float:
        pos = self.positions.get(coin)
        return pos.size if pos else 0.0

    def mark(self, coin: str) -> float | None:
        m = self.marks.get(coin)
        return m[1] if m else None

    def unrealized(self) -> float:
        return sum(p.size * ((self.mark(p.coin) or p.entry) - p.entry)
                   for p in self.positions.values())

    def equity(self) -> float:
        return self.balance + self.unrealized()

    def notional(self, exclude: str | None = None) -> float:
        return sum(abs(p.size) * (self.mark(p.coin) or p.entry)
                   for p in self.positions.values() if p.coin != exclude)

    def open_coins(self, exclude: str | None = None) -> tuple[str, ...]:
        return tuple(sorted(c for c, p in self.positions.items() if p.size and c != exclude))

    def size_at(self, coin: str, t: int) -> float:
        tl = self.timeline.get(coin) or []
        i = bisect_right([row[0] for row in tl], t) - 1
        return tl[i][1] if i >= 0 else 0.0

    # --- cambios ------------------------------------------------------------------------------
    def roll(self, t: int) -> None:
        """Inicio de día/semana UTC (para los límites de pérdida) y caída máxima."""
        eq = self.equity()
        if day0(t) > self.day_t:
            self.day_t, self.day_start = day0(t), eq
        if week0(t) > self.week_t:
            self.week_t, self.week_start = week0(t), eq
        self.peak = max(self.peak, eq)
        if self.peak > 0:
            self.max_dd = max(self.max_dd, 1 - eq / self.peak)

    def set_mark(self, coin: str, t: int, px: float) -> None:
        self.marks[coin] = (t, px)

    def sample(self, t: int) -> None:
        if not self.curve or t - self.curve[-1][0] >= 60_000:
            self.curve.append([t, round(self.equity(), 6)])
            del self.curve[:-CURVE_MAX]

    def fill(self, coin: str, side: int, qty: float, price: float, fee: float, t: int,
             trip_t: int | None) -> tuple[float, ClosedTrip | None]:
        """Aplica una orden (nunca cruza de lado: el motor parte los giros). Devuelve el PnL
        cerrado y, si la posición queda en cero, el viaje propio terminado."""
        pos = self.positions.get(coin) or Position(coin)
        realized = 0.0
        if pos.size == 0 or _sgn(pos.size) == side:
            new = pos.size + side * qty
            pos.entry = (abs(pos.size) * pos.entry + qty * price) / abs(new)
            if pos.size == 0:
                pos.opened_t, pos.trip_t, pos.net = t, trip_t, 0.0
            pos.size = new
        else:
            q = min(qty, abs(pos.size))
            realized = (price - pos.entry) * q * _sgn(pos.size)
            pos.size = 0.0 if q >= abs(pos.size) - 1e-12 else pos.size + side * q
        self.balance += realized - fee
        self.fees += fee
        self.realized += realized
        pos.net += realized - fee
        self._track(coin, t, pos.size)
        if pos.size != 0:
            self.positions[coin] = pos
            return realized, None
        self.positions.pop(coin, None)
        self.trips += 1
        self.wins += pos.net > 0
        if pos.net < 0:
            self.streak, self.last_loss_t = self.streak + 1, t
        else:
            self.streak = 0
        return realized, ClosedTrip(coin, pos.trip_t, pos.opened_t, t, pos.net)

    def _track(self, coin: str, t: int, size: float) -> None:
        tl = self.timeline.setdefault(coin, [])
        tl.append([t, size])
        cut = t - KEEP_TIMELINE_MS
        while len(tl) > 1 and tl[1][0] <= cut:
            tl.pop(0)

    def apply_funding(self, coin: str, t: int, rate: float, px: float) -> float | None:
        """Pago de funding de la hora `t` con la posición que había en `t` (una vez)."""
        key = f"{coin}:{t}"
        if key in self.funded:
            return None
        size = self.size_at(coin, t)
        if size == 0:
            return None
        self.funded[key] = t
        if len(self.funded) > 20_000:  # memoria acotada: lo de hace más de 3 días ya no llega
            cut = t - KEEP_TIMELINE_MS
            self.funded = {k: v for k, v in self.funded.items() if v >= cut}
        amount = -size * px * rate
        self.balance += amount
        self.funding += amount
        if coin in self.positions:
            self.positions[coin].net += amount
        return amount

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Account:
        d = dict(d)
        d["positions"] = {k: Position(**v) for k, v in (d.get("positions") or {}).items()}
        d["marks"] = {k: (int(v[0]), float(v[1])) for k, v in (d.get("marks") or {}).items()}
        return cls(**d)
