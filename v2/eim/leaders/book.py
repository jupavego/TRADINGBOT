"""Estado esperado de un líder reconstruido con sus ejecuciones (puro, sin I/O).

Cada ejecución de Hyperliquid trae `startPosition`: si no coincide con lo que el libro
esperaba, faltan ejecuciones intermedias (hueco). El libro se reancla en la posición final de
esa ejecución y el servicio rellena el hueco por REST; el historial rellenado se guarda pero
no vuelve a mover el libro (es anterior a lo ya aplicado).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from decimal import Decimal

from eim.core.leaders import Channel, Leader, LeaderFill, LeaderPosition
from eim.leaders.params import ENTRY_REL_TOL, SEEN_KEEP
from eim.leaders.parse import ZERO, dec, fill_key, parse_fill, signed_size


@dataclass
class CoinState:
    size: Decimal  # firmado: > 0 long, < 0 short
    entry: float | None  # None = desconocido (tras un hueco) hasta la próxima reconciliación


@dataclass(frozen=True)
class Gap:
    leader_id: str
    symbol: str | None  # None = todo el líder (corte del WS)
    start: int  # última información fiable
    end: int  # evento que reveló el hueco
    cause: str  # "secuencia" | "ws" | "reconciliación"
    detail: str


@dataclass(frozen=True)
class Diff:
    symbol: str
    field: str  # "size" | "entry"
    expected: str
    actual: str


@dataclass(frozen=True)
class LeverageChange:
    symbol: str
    old: float | None
    new: float | None
    old_mode: str | None
    new_mode: str | None


@dataclass(frozen=True)
class Recon:
    """Comparación libro (esperado) vs exchange (real) en la hora `t` del estado."""

    t: int
    checked: tuple[str, ...]
    skipped: tuple[str, ...]  # el libro ya aplicó ejecuciones posteriores a `t`
    diffs: tuple[Diff, ...]
    leverage: tuple[LeverageChange, ...]

    @property
    def size_ok(self) -> bool:
        return not any(d.field == "size" for d in self.diffs)

    @property
    def match(self) -> bool:
        return not self.diffs


def _signed(p: LeaderPosition) -> Decimal:
    return dec(p.size) if p.side == "long" else -dec(p.size)


class LeaderBook:
    def __init__(self, leader: Leader, seen_keep: int = SEEN_KEEP) -> None:
        self.leader = leader
        self.coins: dict[str, CoinState] = {}
        self.touched: dict[str, int] = {}  # moneda → hora de lo último aplicado (abierta o no)
        self.lev: dict[str, tuple[float | None, str | None]] = {}  # persiste tras cerrar
        self.as_of: int | None = None  # hora del último estado cargado del exchange
        self.last_fill_t = 0
        self._seen: set[tuple[int, int]] = set()
        self._order: deque[tuple[int, int]] = deque()
        self._keep = seen_keep

    # --- estado del exchange ----------------------------------------------------------------
    def load(self, t: int, positions: list[LeaderPosition]) -> None:
        """Adopta el estado real (arranque o resincronización tras una divergencia)."""
        self.coins = {p.symbol: CoinState(_signed(p), p.entry) for p in positions}
        for p in positions:
            self.lev[p.symbol] = (p.leverage, p.margin_mode)
        self.touched = {s: t for s in set(self.touched) | set(self.coins)}
        self.as_of = t

    def compare(self, t: int, actual: list[LeaderPosition]) -> Recon:
        act = {p.symbol: p for p in actual}
        checked, skipped, diffs, lev = [], [], [], []
        for s in sorted(set(self.coins) | set(act)):
            if self.touched.get(s, 0) > t:
                skipped.append(s)
                continue
            checked.append(s)
            st, a = self.coins.get(s), act.get(s)
            exp, got = (st.size if st else ZERO), (_signed(a) if a else ZERO)
            if exp != got:
                diffs.append(Diff(s, "size", str(exp), str(got)))
            elif st and a and st.entry is not None and \
                    abs(st.entry - a.entry) > ENTRY_REL_TOL * a.entry:
                diffs.append(Diff(s, "entry", f"{st.entry:.6g}", f"{a.entry:.6g}"))
        for s, a in act.items():
            old = self.lev.get(s)
            if old is not None and old != (a.leverage, a.margin_mode):
                lev.append(LeverageChange(s, old[0], a.leverage, old[1], a.margin_mode))
        return Recon(t, tuple(checked), tuple(skipped), tuple(diffs), tuple(lev))

    def refresh(self, actual: list[LeaderPosition], recon: Recon) -> None:
        """Tras una reconciliación sin diferencias de tamaño: precio medio y apalancamiento
        del exchange (autoridad) para las monedas comparadas."""
        for p in actual:
            self.lev[p.symbol] = (p.leverage, p.margin_mode)
            st = self.coins.get(p.symbol)
            if st is not None and p.symbol in recon.checked:
                st.entry = p.entry

    # --- ejecuciones ------------------------------------------------------------------------
    def is_seen(self, raw: dict) -> bool:
        return fill_key(raw) in self._seen

    def _remember(self, key: tuple[int, int]) -> None:
        self._seen.add(key)
        self._order.append(key)
        while len(self._order) > self._keep:
            self._seen.discard(self._order.popleft())

    def apply(self, raw: dict, observed_at: int, channel: Channel
              ) -> tuple[LeaderFill | None, Gap | None]:
        """(ejecución nueva o None si es repetida/spot, hueco detectado o None)."""
        key = fill_key(raw)
        if key in self._seen:
            return None, None
        self._remember(key)
        coin = raw["coin"]
        fill = parse_fill(raw, self.leader, observed_at, channel, self.lev.get(coin, (None,))[0])
        if fill is None:
            return None, None
        self.last_fill_t = max(self.last_fill_t, fill.t)
        if self.as_of is not None and fill.t <= self.as_of:
            return fill, None  # ya incluida en el estado cargado: solo historial
        cur_t = self.touched.get(coin, self.as_of or 0)
        st = self.coins.get(coin)
        start, end = dec(raw["startPosition"]), dec(raw["startPosition"]) + signed_size(raw)
        expected = st.size if st else ZERO
        if fill.t < cur_t or (fill.t == cur_t and start != expected and coin in self.touched):
            return fill, None  # anterior a lo aplicado (relleno de un hueco): solo historial
        gap = None
        if self.as_of is not None and start != expected:
            gap = Gap(self.leader.id, coin, cur_t, fill.t, "secuencia",
                      f"esperado {expected}, startPosition {start}")
        entry = _entry(st, start, end, fill.price, gap is not None)
        if end == 0:
            self.coins.pop(coin, None)
        else:
            self.coins[coin] = CoinState(end, entry)
        self.touched[coin] = fill.t
        return fill, gap

    def positions(self) -> dict[str, tuple[Decimal, float | None]]:
        return {s: (c.size, c.entry) for s, c in sorted(self.coins.items())}


def _entry(st: CoinState | None, start: Decimal, end: Decimal, px: float, after_gap: bool
           ) -> float | None:
    if end == 0:
        return None
    if start == 0 or (start > 0) != (end > 0):
        return px  # apertura o giro: la posición nueva nace a este precio
    if after_gap or st is None or st.entry is None:
        return None
    if abs(end) > abs(start):
        a, b = float(abs(start)), float(abs(end))
        return (a * st.entry + (b - a) * px) / b
    return st.entry  # reducir no cambia el precio medio
