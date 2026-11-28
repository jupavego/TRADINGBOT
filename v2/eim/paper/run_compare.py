"""Dos corridas en papel, comparadas con la contabilidad oficial (cierre de T143).

La mesa principal (T31) y una corrida aparte (`eim/paper/variant.py`) deciden sobre los MISMOS
contextos y solo cambian la ejecución. Aquí se comparan sus libros fijos en la misma ventana y con
la misma regla de T144 (`universe.result_rows`): nada de lo que no cuenta entra en una cifra.

Ventana: la operación se abrió en `[t0, t1)` y se cerró antes de `t1`. Se exige la apertura y no
solo el cierre porque la corrida aparte nació en `t0`: una operación de T31 abierta antes no tiene
con qué compararse.

Tres lecturas, de la más gruesa a la más limpia:

- `sides`: las cifras oficiales de cada libro, por marco, perfil y tipo de entrada.
- `paired`: la misma idea en el mismo perfil, vivida en los dos libros (clave `profile`,
  `idea_id`). Es el efecto de la ejecución sobre una operación que las dos corridas tomaron.
- `only`: lo que tomó un libro y el otro no. Ahí entra la composición (posiciones ocupadas,
  límites sin llenar, marcos cerrados por la puerta): no es el mismo experimento y se dice aparte.

R neto = `r` del libro (PnL / riesgo de precio al SL); costo en R con el método del diagnóstico
de la fase 24 (`cost_ledger.trade_cost`); R bruto = neto + costo. Puro: sin red ni disco.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable, Mapping, Sequence

from eim.paper import accounting, universe
from eim.paper.cost_ledger import trade_cost

Z95 = 1.96
TIMEFRAMES = ("15m", "1h", "4h")


def _num(x: object) -> float | None:
    """Número o None: el CSV del libro trae cadenas y `''` donde la base tiene NULL."""
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def _f(x: object) -> float:
    v = _num(x)
    return v if v is not None else 0.0


def in_window(rows: Iterable[Mapping], t0: int, t1: int) -> list[Mapping]:
    """Lo que cuenta (T144) abierto en `[t0, t1)` y cerrado antes de `t1`."""
    opened = [r for r in rows if (t := _num(r.get("opened_t"))) is not None and t0 <= t < t1]
    return list(universe.result_rows(accounting.window(opened, t0, t1)))


def stats(xs: Sequence[float | None]) -> dict:
    """Media, error estándar e IC95 % normal de una serie (los None no cuentan)."""
    v = [x for x in xs if x is not None]
    n = len(v)
    if not n:
        return {"n": 0, "mean": None, "se": None, "ci95": None}
    mean = statistics.fmean(v)
    se = statistics.stdev(v) / math.sqrt(n) if n > 1 else None
    ci = [mean - Z95 * se, mean + Z95 * se] if se is not None else None
    return {"n": n, "mean": mean, "se": se, "ci95": ci}


def _cost_r(r: Mapping) -> float | None:
    return trade_cost(dict(r))["cost_r"]


def _gross_r(r: Mapping) -> float | None:
    c = _cost_r(r)
    return None if c is None else _f(r.get("r")) + c


def block(rows: Sequence[Mapping]) -> dict:
    """Resumen de un grupo de operaciones que cuentan: neto, costo y bruto en R, y USDT."""
    net = stats([_f(r.get("r")) for r in rows])
    return {"n": len(rows), "net_r": net["mean"], "net_se": net["se"], "net_ci95": net["ci95"],
            "cost_r": stats([_cost_r(r) for r in rows])["mean"],
            "gross_r": stats([_gross_r(r) for r in rows])["mean"],
            "win_rate": (sum(_f(r.get("r")) > 0 for r in rows) / len(rows)) if rows else None,
            "sl_rate": (sum(r.get("reason") == "SL" for r in rows) / len(rows)) if rows else None,
            "pnl_usdt": sum(_f(r.get("pnl_usdt")) for r in rows)}


def _by(rows: Sequence[Mapping], key: str) -> dict[str, dict]:
    keys = sorted({str(r.get(key)) for r in rows})
    return {k: block([r for r in rows if str(r.get(key)) == k]) for k in keys}


def side(rows: Sequence[Mapping], t0: int, t1: int) -> dict:
    """Cifras oficiales de un libro en la ventana, con su huella y su desglose."""
    kept = in_window(rows, t0, t1)
    fig = accounting.figures(kept)
    return {"official": {k: fig.get(k) for k in ("n", "counted_digest", "win_rate", "mean_r",
                                                  "ci95", "total_r", "pnl_usdt", "fees", "slip",
                                                  "funding", "dd", "from_t", "to_t")},
            "all": block(kept), "by_timeframe": _by(kept, "timeframe"),
            "by_profile": _by(kept, "profile"), "by_kind": _by(kept, "kind"),
            "by_profile_tf": _grid(kept)}


def _grid(kept: Sequence[Mapping]) -> dict[str, dict]:
    """Por perfil y marco (`perfil·marco`), solo las celdas con operaciones."""
    out = {}
    for p in sorted({str(r.get("profile")) for r in kept}):
        for tf in TIMEFRAMES:
            rs = [r for r in kept if r.get("profile") == p and r.get("timeframe") == tf]
            if rs:
                out[f"{p}·{tf}"] = block(rs)
    return out


def _key(r: Mapping) -> tuple[str, str]:
    return str(r.get("profile")), str(r.get("idea_id"))


def _delta(pairs: Sequence[tuple[Mapping, Mapping]]) -> dict:
    def d(fn):
        out = []
        for a, b in pairs:
            x, y = fn(a), fn(b)
            out.append(None if x is None or y is None else y - x)
        return stats(out)
    kinds: dict[str, int] = {}
    for a, b in pairs:
        k = f"{a.get('kind')}→{b.get('kind')}"
        kinds[k] = kinds.get(k, 0) + 1
    return {"n": len(pairs), "d_net_r": d(lambda r: _f(r.get("r"))), "d_cost_r": d(_cost_r),
            "d_gross_r": d(_gross_r),
            "same_reason": sum(a.get("reason") == b.get("reason") for a, b in pairs),
            "kinds": dict(sorted(kinds.items()))}


def paired(a_rows: Sequence[Mapping], b_rows: Sequence[Mapping]) -> dict:
    """La misma idea en el mismo perfil, en los dos libros: diferencia `b − a` por operación."""
    ka, kb = {_key(r): r for r in a_rows}, {_key(r): r for r in b_rows}
    common = sorted(set(ka) & set(kb))
    pairs = [(ka[k], kb[k]) for k in common]
    out = {"all": _delta(pairs),
           "by_timeframe": {tf: _delta([p for p in pairs if p[0].get("timeframe") == tf])
                            for tf in TIMEFRAMES}}
    out["only_a"] = block([ka[k] for k in sorted(set(ka) - set(kb))])
    out["only_b"] = block([kb[k] for k in sorted(set(kb) - set(ka))])
    out["only_a_by_tf"] = _by([ka[k] for k in sorted(set(ka) - set(kb))], "timeframe")
    out["only_b_by_tf"] = _by([kb[k] for k in sorted(set(kb) - set(ka))], "timeframe")
    out["converted"] = converted(pairs)
    return out


def _bps(r: Mapping, key: str) -> float | None:
    notional = _f(r.get("notional"))
    return _f(r.get(key)) / notional * 1e4 if notional else None


def converted(pairs: Sequence[tuple[Mapping, Mapping]]) -> dict:
    """Los pares que `a` abrió a mercado y `b` en límite: qué ahorró la entrada y qué cambió.

    Separa los que salieron por el mismo motivo (ahí la diferencia es la ejecución de la entrada)
    de los que no (ahí cambió la salida, y la diferencia ya no es solo de la entrada).
    """
    conv = [(a, b) for a, b in pairs if a.get("kind") == "market" and b.get("kind") == "limit"]
    same = [(a, b) for a, b in conv if a.get("reason") == b.get("reason")]
    other = [(a, b) for a, b in conv if a.get("reason") != b.get("reason")]

    def mean_bps(side_ix: int, key: str) -> float | None:
        return stats([_bps(p[side_ix], key) for p in conv])["mean"]

    def better_fill(a: Mapping, b: Mapping) -> float | None:
        fa = _f(a.get("fill"))
        return (fa - _f(b.get("fill"))) * _f(a.get("side")) / fa * 1e4 if fa else None
    return {"n": len(conv),
            "fees_bps": [mean_bps(0, "fees"), mean_bps(1, "fees")],
            "slip_bps": [mean_bps(0, "slip"), mean_bps(1, "slip")],
            "better_fill_bps": stats([better_fill(a, b) for a, b in conv])["mean"],
            "fill_delay_min": stats([(_f(b.get("fill_t")) - _f(a.get("fill_t"))) / 60_000
                                     for a, b in conv])["mean"],
            "same_exit": {"n": len(same), "d_net_r": stats([_f(b.get("r")) - _f(a.get("r"))
                                                             for a, b in same])},
            "other_exit": [{"profile": a.get("profile"), "timeframe": a.get("timeframe"),
                            "reason": [a.get("reason"), b.get("reason")],
                            "r": [_f(a.get("r")), _f(b.get("r"))],
                            "qty": [_f(a.get("qty")), _f(b.get("qty"))],
                            "exit_t": [int(_f(a.get("exit_t"))), int(_f(b.get("exit_t")))]}
                           for a, b in other]}


def gate_check(kept: Sequence[Mapping], max_cost_r: float) -> list[dict]:
    """Costo VIVIDO por perfil y marco frente al umbral de la puerta de marcos (T143 ent. 3).

    La puerta decide con el costo de la sombra calibrado (`tf_gate_profile`); esto mira lo que de
    verdad pagó cada celda que operó, para saber si la puerta dejó pasar lo que debía cerrar.
    """
    out = []
    for k, b in _grid(kept).items():
        if b["cost_r"] is not None:
            out.append({"cell": k, "n": b["n"], "cost_r": b["cost_r"],
                        "over": b["cost_r"] >= max_cost_r})
    return out


def compare(a_rows: Sequence[Mapping], b_rows: Sequence[Mapping], t0: int, t1: int) -> dict:
    """Comparación completa de `b` (corrida aparte) frente a `a` (mesa principal)."""
    ka, kb = in_window(a_rows, t0, t1), in_window(b_rows, t0, t1)
    return {"window": {"t0": t0, "t1": t1, "rule": "abierta en [t0, t1) y cerrada antes de t1",
                       "universe": universe.declaration()["universe"]},
            "a": side(a_rows, t0, t1), "b": side(b_rows, t0, t1), "paired": paired(ka, kb)}
