"""Respuestas JSON de Hyperliquid → contratos de líderes (puro, sin I/O).

Las posiciones se calculan con `Decimal` sobre las cadenas del exchange: tras miles de
ejecuciones la suma en coma flotante dejaría de cuadrar con `szi`.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

from eim.core.leaders import (
    Channel,
    FillAction,
    Leader,
    LeaderFill,
    LeaderFunding,
    LeaderPosition,
    Side,
    leader_id,
)
from eim.leaders.params import SOURCE

ZERO = Decimal(0)


def dec(x: str | float | int) -> Decimal:
    """Decimal exacto desde la cadena del exchange (o desde un float que la conserva)."""
    return Decimal(x if isinstance(x, str) else repr(x))


def is_perp(coin: str) -> bool:
    """Perpetuo del dex principal (donde viven BTC/ETH). Fuera: spot (`@<índice>`,
    `BASE/QUOTE`) y perpetuos HIP-3 (`dex:COIN`), que `clearinghouseState` sin `dex` no
    devuelve y por tanto no se podrían reconciliar."""
    return not coin.startswith("@") and "/" not in coin and ":" not in coin


def side_of(pos: Decimal) -> Side:
    return "long" if pos > 0 else "short"


def classify(start: Decimal, end: Decimal) -> tuple[FillAction, Side]:
    """Acción sobre la posición según el tamaño firmado antes y después de la ejecución."""
    if start == 0:
        return "open", side_of(end)
    if end == 0:
        return "close", side_of(start)
    if (start > 0) != (end > 0):
        return "flip", side_of(end)
    if abs(end) > abs(start):
        return "increase", side_of(end)
    return "reduce", side_of(start)


def signed_size(raw: dict) -> Decimal:
    sz = dec(raw["sz"])
    return sz if raw["side"] == "B" else -sz


def fill_key(raw: dict) -> tuple[int, int]:
    """Clave de deduplicación: `tid` (operación) + `oid` (orden; distingue la autoejecución)."""
    return int(raw["tid"]), int(raw["oid"])


def _chain(rows: list[dict]) -> list[dict]:
    """Ordena ejecuciones del mismo milisegundo y moneda siguiendo startPosition → final.
    Si la cadena es ambigua, conserva el orden recibido."""
    starts = [dec(r["startPosition"]) for r in rows]
    ends = [s + signed_size(r) for s, r in zip(starts, rows, strict=True)]
    end_count = Counter(ends)
    firsts = [i for i, s in enumerate(starts) if end_count[s] == 0]
    if len(firsts) != 1:
        return rows
    order, cur = [firsts[0]], ends[firsts[0]]
    while len(order) < len(rows):
        nxt = [i for i, s in enumerate(starts) if s == cur and i not in order]
        if len(nxt) != 1:
            return rows
        order.append(nxt[0])
        cur = ends[nxt[0]]
    return [rows[i] for i in order]


def order_fills(raws: list[dict]) -> list[dict]:
    """Sin repetidos y en orden cronológico real. `userFills` (REST) llega del más nuevo al
    más viejo y el WS/`userFillsByTime` al revés; a igual milisegundo manda la cadena."""
    uniq: dict[tuple[int, int], dict] = {}
    for r in raws:
        uniq.setdefault(fill_key(r), r)
    groups: dict[tuple[int, str], list[dict]] = {}
    for r in uniq.values():
        groups.setdefault((int(r["time"]), r["coin"]), []).append(r)
    out: list[dict] = []
    for key in sorted(groups, key=lambda k: k[0]):
        rows = groups[key]
        out.extend(_chain(rows) if len(rows) > 1 else rows)
    return out


def parse_fill(raw: dict, leader: Leader, observed_at: int, channel: Channel,
               leverage: float | None = None) -> LeaderFill | None:
    """None si es spot (solo se siguen perpetuos)."""
    if not is_perp(raw["coin"]):
        return None
    start = dec(raw["startPosition"])
    end = start + signed_size(raw)
    action, side = classify(start, end)
    liq = raw.get("liquidation") or {}
    return LeaderFill(
        leader_id=leader.id, address=leader.address, symbol=raw["coin"], side=side,
        action=action, size=float(raw["sz"]), price=float(raw["px"]),
        start_position=float(start), end_position=float(end), fee=float(raw.get("fee") or 0),
        fee_token=raw.get("feeToken") or "USDC", closed_pnl=float(raw.get("closedPnl") or 0),
        crossed=bool(raw.get("crossed")),
        liquidated=str(liq.get("liquidatedUser", "")).lower() == leader.address,
        leverage=leverage, tid=int(raw["tid"]), oid=int(raw["oid"]), t=int(raw["time"]),
        observed_at=observed_at, channel=channel, source=SOURCE)


def parse_positions(leader: Leader, state: dict, observed_at: int
                    ) -> tuple[int, list[LeaderPosition]]:
    """`clearinghouseState` → (hora del estado, posiciones de perpetuos abiertas)."""
    t = int(state.get("time") or observed_at)
    out: list[LeaderPosition] = []
    for ap in state.get("assetPositions", []):
        p = ap.get("position", {})
        szi = dec(p.get("szi", "0"))
        if szi == 0 or not is_perp(p.get("coin", "@")):
            continue
        lev = p.get("leverage") or {}
        liq = p.get("liquidationPx")
        out.append(LeaderPosition(
            leader_id=leader.id, address=leader.address, symbol=p["coin"], side=side_of(szi),
            size=float(abs(szi)), entry=float(p["entryPx"]),
            leverage=float(lev["value"]) if lev.get("value") is not None else None,
            margin_mode=lev.get("type") if lev.get("type") in ("cross", "isolated") else None,
            liquidation_px=float(liq) if liq is not None else None,
            unrealized_pnl=float(p["unrealizedPnl"]) if p.get("unrealizedPnl") else None,
            margin_used=float(p["marginUsed"]) if p.get("marginUsed") else None,
            t=t, observed_at=observed_at, source=SOURCE))
    return t, sorted(out, key=lambda x: x.symbol)


def parse_funding(leader: Leader, rows: list[dict], observed_at: int) -> list[LeaderFunding]:
    out: list[LeaderFunding] = []
    for r in rows:
        d = r.get("delta", {})
        if d.get("type") != "funding" or not is_perp(d.get("coin", "@")):
            continue
        out.append(LeaderFunding(
            leader_id=leader.id, address=leader.address, symbol=d["coin"],
            usdc=float(d["usdc"]), rate=float(d.get("fundingRate") or 0),
            size=float(d.get("szi") or 0), t=int(r["time"]), observed_at=observed_at,
            source=SOURCE))
    return out


def vault_leader(details: dict, discovered_at: int) -> Leader:
    """`vaultDetails` → líder de origen vault (la propia dirección del vault opera)."""
    addr = str(details["vaultAddress"]).lower()
    evidence: dict[str, float | str] = {
        "apr": float(details.get("apr") or 0.0),
        "manager": str(details.get("leader", "")).lower(),
        "followers": float(len(details.get("followers") or [])),
        "closed": "sí" if details.get("isClosed") else "no",
    }
    return Leader(id=leader_id("hyperliquid", addr), venue="hyperliquid", address=addr,
                  label=str(details.get("name", ""))[:80], origin="vault",
                  discovered_at=discovered_at, source=f"{SOURCE}:vaultDetails",
                  evidence=evidence)
