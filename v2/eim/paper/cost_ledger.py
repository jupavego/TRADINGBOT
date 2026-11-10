"""Costo medido del libro fijo, por operación y acumulado (T143, entregable 4).

Hasta T143 el costo vivido había que sacarlo a mano del `ledger.csv`. Aquí sale del libro fijo
(`paper_ledger`) con el **mismo método del diagnóstico de la fase 24**
(`PLAN/notas/diagnostico_rentabilidad_2026-11-09.md` §3): solo operaciones de perfil (las de sombra
no tienen tamaño), sin las `retro` (T142: nadie las vivió), y el riesgo de cada operación como
`|pnl_usdt| / |r|`, que es lo que ese perfil arriesgaba de verdad. Una operación con `pnl_usdt` o
`r` en 0 no permite saber su riesgo: cuenta en USDT pero no en R, y se dice cuántas son.

Lo usan el panel (resumen de la mesa) y el informe semanal de T31. Puro salvo `from_connection`,
que solo lee.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Sequence

SOURCE = ("libro fijo `paper_ledger` · operaciones de perfil, sin `retro` · R = costo / "
          "(|pnl| / |r|), método del diagnóstico de la fase 24")
_COLS = ("exit_t", "profile", "symbol", "timeframe", "kind", "pnl_usdt", "r", "notional", "fees",
         "slip", "funding", "retro", "scope")
RECENT = 10


def _f(x) -> float:
    return float(x) if x is not None else 0.0


def trade_cost(row: dict) -> dict:
    """Costo de una operación: USDT, puntos básicos del nocional y R (si su riesgo se conoce)."""
    usdt = _f(row.get("fees")) + _f(row.get("slip")) + _f(row.get("funding"))
    pnl, r, notional = _f(row.get("pnl_usdt")), _f(row.get("r")), _f(row.get("notional"))
    risk = abs(pnl) / abs(r) if pnl and r else None
    return {"exit_t": row.get("exit_t"), "profile": row.get("profile"),
            "symbol": row.get("symbol"), "timeframe": row.get("timeframe"),
            "kind": row.get("kind"), "cost_usdt": usdt,
            "cost_bps": usdt / notional * 1e4 if notional else None,
            "cost_r": usdt / risk if risk else None}


def lived(rows: Iterable[dict]) -> list[dict]:
    """Las operaciones vividas: de perfil y sin `retro`."""
    return [r for r in rows if r.get("scope") == "perfil" and not r.get("retro")]


def _block(cs: Sequence[dict]) -> dict:
    rs = [c["cost_r"] for c in cs if c["cost_r"] is not None]
    bps = [c["cost_bps"] for c in cs if c["cost_bps"] is not None]
    return {"n": len(cs), "n_r": len(rs), "cost_usdt": sum(c["cost_usdt"] for c in cs),
            "cost_r_mean": statistics.fmean(rs) if rs else None,
            "cost_r_median": statistics.median(rs) if rs else None,
            "cost_r_sum": sum(rs) if rs else None,
            "cost_bps_mean": statistics.fmean(bps) if bps else None}


def _group(cs: Sequence[dict], key: str) -> dict[str, dict]:
    keys = sorted({str(c[key]) for c in cs if c[key] is not None})
    return {k: _block([c for c in cs if str(c[key]) == k]) for k in keys}


def summarize(rows: Iterable[dict], t0: int | None = None, t1: int | None = None) -> dict:
    """Resumen del costo vivido en `[t0, t1)` por cierre: total, por marco, por tipo de entrada.

    `recent` son las últimas operaciones con su costo, para ver el costo **por operación** y no
    solo la media. `n_r < n` dice cuántas no tienen el riesgo reconstruible.
    """
    sel = [r for r in lived(rows)
           if (t0 is None or (r.get("exit_t") or 0) >= t0)
           and (t1 is None or (r.get("exit_t") or 0) < t1)]
    cs = sorted((trade_cost(r) for r in sel), key=lambda c: c["exit_t"] or 0)
    return {"source": SOURCE, "from": t0, "to": t1, "all": _block(cs),
            "by_timeframe": _group(cs, "timeframe"), "by_kind": _group(cs, "kind"),
            "recent": cs[-RECENT:][::-1]}


def from_connection(conn_lock, t0: int | None = None, t1: int | None = None) -> dict:
    """Lee el libro de una base abierta (`(con, lock)`) y resume. Sin libro: dice por qué."""
    if conn_lock is None:
        return {"source": SOURCE, "error": "sin libro simulado abierto en este proceso"}
    con, lock = conn_lock
    try:
        with lock:
            got = con.execute(f"SELECT {', '.join(_COLS)} FROM paper_ledger "
                              "WHERE scope = 'perfil'").fetchall()
    except Exception as e:  # noqa: BLE001 - un libro ilegible no impide el informe
        return {"source": SOURCE, "error": f"{type(e).__name__}: {e}"}
    return summarize([dict(zip(_COLS, g, strict=True)) for g in got], t0, t1)
