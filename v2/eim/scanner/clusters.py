"""Duplicados y correlación entre oportunidades (T95, 2/3). Puro.

Diez candidatas que son la misma apuesta no son diez descubrimientos. Se agrupan en una sola
apuesta cuando comparten **subyacente o divisa** (una pata que no es la moneda de liquidación:
`1000PEPEUSDT` y `PEPEUSDT` son PEPE; `EURUSD` y `EURJPY` comparten EUR) o cuando sus
rendimientos de las últimas `CORR_BARS` velas tienen **|ρ| ≥ `MIN_CORR`** (mismo factor). La
agrupación es transitiva (componentes conexas) y se queda un **representante**, el de mayor
prioridad, con la **exposición agregada a la vista**: cuántas van en la misma dirección que él
(teniendo en cuenta el signo de ρ), cuántas la cubren y el número aproximado de apuestas
independientes, k / (1 + (k − 1)·|ρ| medio).
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence

import numpy as np

CLUSTER_VERSION = "1.0.0"
MIN_CORR = 0.75
CORR_BARS = 60
MIN_OVERLAP = 30
#: Monedas de liquidación: compartirlas no es compartir apuesta (todo el universo cotiza en USDT).
SETTLEMENT = frozenset({"USDT", "USDC", "BUSD", "FDUSD", "USD"})
_MULT = re.compile(r"^(1000000|100000|10000|1000|1M)(?=[A-Z])")


def legs(symbol: str, quote: str | None = None, underlying: str | None = None) -> frozenset[str]:
    """Patas de un instrumento sin la moneda de liquidación (`EUR/USD` → {EUR}; FX con dos
    patas fuera de USD → las dos)."""
    u = (underlying or "").upper()
    if "/" in u:
        parts = {p.strip() for p in u.split("/") if p.strip()}
    else:
        base = (u or symbol).upper()
        q = (quote or "").upper()
        if q and base.endswith(q) and len(base) > len(q):
            base = base[: -len(q)]
        parts = {_MULT.sub("", base)}
        if q:
            parts.add(q)
    return frozenset(p for p in parts if p and p not in SETTLEMENT)


def corr(a: tuple[Sequence[int], Sequence[float]] | None,
         b: tuple[Sequence[int], Sequence[float]] | None) -> float | None:
    """ρ de los rendimientos logarítmicos en las velas comunes (las últimas `CORR_BARS`)."""
    if a is None or b is None:
        return None
    ta, ca = np.asarray(a[0], dtype=np.int64), np.asarray(a[1], dtype=float)
    tb, cb = np.asarray(b[0], dtype=np.int64), np.asarray(b[1], dtype=float)
    common, ia, ib = np.intersect1d(ta, tb, return_indices=True)
    if len(common) < MIN_OVERLAP + 1:
        return None
    xa, xb = ca[ia][-(CORR_BARS + 1):], cb[ib][-(CORR_BARS + 1):]
    if np.any(~np.isfinite(xa)) or np.any(~np.isfinite(xb)) or np.any(xa <= 0) or \
            np.any(xb <= 0):
        return None
    ra, rb = np.diff(np.log(xa)), np.diff(np.log(xb))
    if np.std(ra) == 0 or np.std(rb) == 0:
        return None
    r = float(np.corrcoef(ra, rb)[0, 1])
    return r if math.isfinite(r) else None


def _side(s: str) -> int:
    return 1 if s == "largo" else -1


def cluster(rows: Sequence[Mapping], legs_of: Mapping[str, frozenset[str]],
            series: Mapping[str, tuple[Sequence[int], Sequence[float]]]) -> list[dict]:
    """`rows`: oportunidades YA ordenadas por prioridad (las de `rank.rank`). Devuelve un grupo
    por apuesta (también los de un solo miembro), en el orden de su representante."""
    n = len(rows)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    links: dict[tuple[int, int], tuple[str, float | None]] = {}
    for i in range(n):
        for j in range(i + 1, n):
            a, b = rows[i]["instrument_id"], rows[j]["instrument_id"]
            shared = legs_of.get(a, frozenset()) & legs_of.get(b, frozenset())
            rho = corr(series.get(a), series.get(b))
            if shared:
                links[(i, j)] = (f"comparten {', '.join(sorted(shared))}", rho)
            elif rho is not None and abs(rho) >= MIN_CORR:
                links[(i, j)] = (f"ρ {rho:+.2f} (mismo factor)", rho)
            else:
                continue
            parent[find(j)] = find(i)
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    out = []
    for members in sorted(groups.values(), key=lambda m: min(m)):
        rep = min(members)
        rr = rows[rep]
        same = hedge = 0
        rhos: list[float] = []
        mem = []
        for k in members:
            r = rows[k]
            if k == rep:
                same += 1
                mem.append({"opportunity_id": r["opportunity_id"], "instrument_id": r[
                    "instrument_id"], "symbol": r.get("symbol", ""), "side": r["side"],
                            "rho_to_rep": None, "link": "representante"})
                continue
            why, rho = links.get((min(rep, k), max(rep, k)), ("enlazada por otra del grupo",
                                                               None))
            if rho is None:
                rho = corr(series.get(rr["instrument_id"]), series.get(r["instrument_id"]))
            same_asset = bool(legs_of.get(rr["instrument_id"], frozenset())
                              & legs_of.get(r["instrument_id"], frozenset()))
            sign = 1 if same_asset or rho is None or rho >= 0 else -1   # mismo activo: +1
            if _side(r["side"]) * sign == _side(rr["side"]):
                same += 1
            else:
                hedge += 1
            mem.append({"opportunity_id": r["opportunity_id"], "instrument_id": r[
                "instrument_id"], "symbol": r.get("symbol", ""), "side": r["side"],
                        "rho_to_rep": None if rho is None else round(rho, 4), "link": why})
        for x, y in ((a, b) for ai, a in enumerate(members) for b in members[ai + 1:]):
            rho = links.get((x, y), (None, None))[1]
            rho = rho if rho is not None else corr(series.get(rows[x]["instrument_id"]),
                                                   series.get(rows[y]["instrument_id"]))
            rhos.append(1.0 if rho is None else abs(rho))
        k = len(members)
        mean_rho = float(np.mean(rhos)) if rhos else 0.0
        out.append({"cluster_id": "g-" + rr["opportunity_id"].removeprefix("op-"),
                    "representative": rr["opportunity_id"], "members": mem,
                    "exposure": {"n": k, "largo": sum(r["side"] == "largo" for r in mem),
                                 "corto": sum(r["side"] == "corto" for r in mem),
                                 "same_direction": same, "hedging": hedge,
                                 "mean_abs_rho": round(mean_rho, 4),
                                 "effective_bets": round(k / (1 + (k - 1) * mean_rho), 3)}})
    return out
