"""Cifras de resultado del universo oficial (T144): se calculan SOLO con lo que cuenta.

Toda cifra de esta pieza sale de `universe.result_rows`, así que una operación `retro` no puede
entrar en acierto, esperanza, capital ni drawdown por ningún camino. Lo que queda fuera no
desaparece: viaja en `tally` (cuántas y por qué) y en `retro` (las no vividas, con su etiqueta).

`cuadre` es la prueba de que las dos contabilidades cuentan lo mismo: compara operación a
operación, por `ledger_id`, lo que publica el informe semanal contra lo que tiene el libro bajo el
mismo universo, y dice exactamente qué falta, qué sobra y qué difiere.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable, Mapping, Sequence

from eim.paper.ledger import window_rows
from eim.paper.universe import (
    PROFILES,
    counts_as_result,
    declaration,
    is_retro,
    result_rows,
    tally,
)

PNL_TOL = 1e-6      # USDT: por debajo, el informe y el libro dicen el mismo número
#: La curva sobre la que se mide el drawdown oficial, declarada con la cifra.
DD_BASE = ("PnL acumulado en USDT de las operaciones que cuentan, ordenadas por cierre; la base "
           "en porcentaje es el capital con el que se dimensionó la primera de cada perfil "
           "(`capital_before`, T118) y queda en «—» si alguna fila no lo guarda")


def _num(x: object) -> float | None:
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, int | float):
        return float(x)
    s = str(x).strip()
    if s in ("", "None", "NULL", "nan"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _f(row: Mapping, key: str) -> float:
    return _num(row.get(key)) or 0.0


def digest(kept: Iterable[Mapping]) -> str:
    """Huella de EXACTAMENTE qué operaciones contó una cifra (12 hex, estilo T118).

    Con ella, quien lea el informe puede comprobar contra el libro que contó esas y no otras: si
    no coincide, `cuadre` dice cuál falta, cuál sobra y cuál difiere.
    """
    ids = sorted(str(r.get("ledger_id") or "") for r in kept)
    return hashlib.sha256("\n".join(ids).encode()).hexdigest()[:12]


def _dd(rows: Sequence[Mapping]) -> dict:
    """Máximo descenso del PnL acumulado de lo que cuenta, con su base declarada."""
    ordered = sorted(rows, key=lambda r: (_f(r, "exit_t"), str(r.get("ledger_id") or "")))
    acc, peak, dd = 0.0, 0.0, 0.0
    for r in ordered:
        acc += _f(r, "pnl_usdt")
        peak = max(peak, acc)
        dd = max(dd, peak - acc)
    first: dict[str, float] = {}
    for r in ordered:
        cb = _num(r.get("capital_before"))
        if r.get("profile") not in first:
            first[str(r.get("profile"))] = cb if cb is not None else float("nan")
    base = sum(first.values()) if first else 0.0
    ok = base > 0 and not math.isnan(base)
    return {"usdt": dd, "base_usdt": base if ok else None,
            "pct": dd / base if ok else None, "base": DD_BASE}


def figures(rows: Iterable[Mapping], profiles: Sequence[str] = PROFILES) -> dict:
    """Las cifras de resultado del universo oficial para un conjunto de filas del libro."""
    rows = list(rows)
    kept = result_rows(rows, profiles)
    out: dict = {"declaration": declaration(), "tally": tally(rows, profiles),
                 "n": len(kept), "counted_digest": digest(kept),
                 "retro_excluded": _retro_block(rows)}
    if not kept:
        out.update(win_rate=None, mean_r=None, ci95=None, total_r=None, pnl_usdt=None,
                   dd=_dd([]), by_profile={}, floor_trades=0, from_t=None, to_t=None)
        return out
    rs = [_f(r, "r") for r in kept]
    n = len(rs)
    mean = sum(rs) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in rs) / (n - 1)) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n) if n > 1 else None
    exits = [_f(r, "exit_t") for r in kept]
    out.update(
        win_rate=sum(x > 0 for x in rs) / n, mean_r=mean, sd_r=sd,
        ci95=[mean - half, mean + half] if half else None, total_r=sum(rs),
        pnl_usdt=sum(_f(r, "pnl_usdt") for r in kept),
        fees=sum(_f(r, "fees") for r in kept), slip=sum(_f(r, "slip") for r in kept),
        funding=sum(_f(r, "funding") for r in kept),
        best=max(_f(r, "pnl_usdt") for r in kept), worst=min(_f(r, "pnl_usdt") for r in kept),
        dd=_dd(kept), floor_trades=sum(1 for r in kept if str(r.get("floor_trade")).lower()
                                       in ("true", "1")),
        by_profile=_by_profile(kept), from_t=int(min(exits)), to_t=int(max(exits)),
    )
    return out


def _by_profile(kept: Sequence[Mapping]) -> dict:
    out: dict[str, dict] = {}
    for r in kept:
        b = out.setdefault(str(r.get("profile")), {"n": 0, "pnl_usdt": 0.0, "total_r": 0.0,
                                                   "wins": 0})
        b["n"] += 1
        b["pnl_usdt"] += _f(r, "pnl_usdt")
        b["total_r"] += _f(r, "r")
        b["wins"] += int(_f(r, "r") > 0)
    for b in out.values():
        b["win_rate"] = b["wins"] / b["n"] if b["n"] else None
        b["mean_r"] = b["total_r"] / b["n"] if b["n"] else None
    return dict(sorted(out.items()))


def _retro_block(rows: Sequence[Mapping]) -> dict:
    """Las no vividas, visibles aparte: cuántas son y cuánto dinero NO suman por eso."""
    rr = [r for r in rows if is_retro(r)]
    if not rr:
        return {"n": 0, "pnl_excluded": 0.0, "total_r_excluded": 0.0, "from_t": None, "to_t": None,
                "label": "retro", "why": "ninguna fila `retro` en este tramo"}
    exits = [_f(r, "exit_t") for r in rr]
    return {"n": len(rr), "pnl_excluded": sum(_f(r, "pnl_usdt") for r in rr),
            "total_r_excluded": sum(_f(r, "r") for r in rr),
            "from_t": int(min(exits)), "to_t": int(max(exits)), "label": "retro",
            "why": "registradas más de 2 h después de su cierre (estreno del libro o recálculo, "
                   "T142): se pueden consultar, no suman a ninguna cifra de resultado"}


def window(rows: Iterable[Mapping], t0: int, t1: int) -> list[Mapping]:
    """Filas cuyo cierre cae en `[t0, t1)`; la ventana se declara con la cifra."""
    out = []
    for r in rows:
        t = _num(r.get("exit_t"))
        if t is not None and t0 <= t < t1:
            out.append(r)
    return out


def from_store(pstore, symbol: str | None = None, t0: int = 0, t1: int = 2 ** 62) -> dict:
    """Cifras oficiales leídas del libro fijo, para el panel y la API (T144).

    Salen del libro y no de la vista recalculada: solo el libro sabe qué filas son `retro` (las
    trajo su estreno o un recálculo y nadie las vivió), y ninguna cifra de resultado puede
    incluirlas. Las tarjetas de capital del panel siguen siendo la mecánica del motor; esto es lo
    que decide. Si el libro no se puede leer, se dice y no se inventa una cifra oficial.
    """
    try:
        rows = [r for r in window_rows(pstore, t0, t1)
                if symbol is None or r["symbol"] == symbol]
        return {"ok": True, **figures(rows)}
    except Exception as exc:  # noqa: BLE001 - un libro ilegible no tumba la vista ni la API
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                "declaration": declaration()}


def cuadre(published: Iterable[Mapping], book: Iterable[Mapping],
           profiles: Sequence[str] = PROFILES) -> dict:
    """¿Cuentan lo mismo el informe y el libro bajo el mismo universo?

    Compara por `ledger_id` las filas que cuentan en cada lado y devuelve la diferencia operación
    a operación: `missing` (el libro la cuenta y el informe no), `extra` (al revés) y `differ`
    (los dos la cuentan con otro PnL, otro R o otro motivo). `match` es verdad solo si no hay
    ninguna de las tres y los totales coinciden dentro de `PNL_TOL`.
    """
    a = {str(r.get("ledger_id")): r for r in published if counts_as_result(r, profiles).counts}
    b = {str(r.get("ledger_id")): r for r in book if counts_as_result(r, profiles).counts}
    missing = [_op(b[k]) for k in sorted(set(b) - set(a))]
    extra = [_op(a[k]) for k in sorted(set(a) - set(b))]
    differ = []
    for k in sorted(set(a) & set(b)):
        x, y = a[k], b[k]
        if (abs(_f(x, "pnl_usdt") - _f(y, "pnl_usdt")) > PNL_TOL
                or abs(_f(x, "r") - _f(y, "r")) > PNL_TOL
                or x.get("reason") != y.get("reason")):
            differ.append({"ledger_id": k, "informe": _op(x), "libro": _op(y)})
    pa, pb = sum(_f(r, "pnl_usdt") for r in a.values()), sum(_f(r, "pnl_usdt") for r in b.values())
    return {"universe": declaration()["universe"], "n_informe": len(a), "n_libro": len(b),
            "pnl_informe": pa, "pnl_libro": pb, "missing": missing, "extra": extra,
            "differ": differ,
            "match": not missing and not extra and not differ and abs(pa - pb) <= PNL_TOL}


def _op(r: Mapping) -> dict:
    return {"ledger_id": r.get("ledger_id"), "profile": r.get("profile"),
            "symbol": r.get("symbol"), "exit_t": _num(r.get("exit_t")),
            "reason": r.get("reason"), "pnl_usdt": _f(r, "pnl_usdt"), "r": _f(r, "r")}
