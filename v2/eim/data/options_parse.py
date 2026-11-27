"""Filas de la cadena de opciones de Deribit y calidad de cada vencimiento (T213). Puro.

`public/get_book_summary_by_currency?kind=option` da una fila por opción viva. Aquí se pasan a
un formato propio y estable, se descartan las incompletas (con el motivo contado, nunca en
silencio) y se mide la calidad de cada vencimiento con `eim/options/chain.py`.

Unidades, tal como las da Deribit y tal como se guardan:

- `bid`, `ask`, `mark`: en la **moneda base** (BTC por BTC; las opciones de Deribit son inversas).
  Para la calidad se pasan a USD multiplicando por el subyacente de la fila.
- `mark_iv`: volatilidad implícita de la marca **en %** (55.3 = 0,553).
- `underlying`: el futuro (o índice) que Deribit usa para la IV de ese vencimiento; por eso la
  calidad usa Black-76 (`b = 0`) con ese subyacente.
- `oi`: interés abierto en moneda base, **con 8 h de retraso** según la documentación.
- `expiry`: 08:00 UTC del día del nombre (hora de vencimiento de Deribit).

Una cara vacía del libro (`bid` o `ask` nulos) **no** es una fila incompleta: es un dato real (no
hay quien compre o venda) y se guarda como `None`. Incompleta es la que no trae nombre legible,
marca, IV de marca, subyacente, tipo, interés abierto o instante.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from statistics import median

from eim.options.black_scholes import CALL, PUT
from eim.options.chain import Quote, analyze

YEAR_MS = 365 * 86_400_000          # convención de año de 365 días para el plazo
EXPIRY_HOUR_UTC = 8                 # Deribit vence a las 08:00 UTC
MAX_ARB_LISTED = 5                  # violaciones de arbitraje que se anotan por vencimiento
SUSPECT_RATE = 0.5                  # un tipo |r| > 50 % no es un decimal: se avisa
_MONTHS = {m: i for i, m in enumerate(
    ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), 1)}
_NAME = re.compile(r"^([A-Z0-9_]+)-(\d{1,2})([A-Z]{3})(\d{2})-([0-9d.]+)-([CP])$")
_REQUIRED = ("mark_price", "mark_iv", "underlying_price", "interest_rate", "open_interest",
             "creation_timestamp")


def parse_name(name: str) -> tuple[str, int, float, str] | None:
    """`BTC-27DEC26-100000-C` → (subyacente, vencimiento en ms, precio de ejercicio, tipo).
    `None` si el nombre no es de una opción con ese formato."""
    m = _NAME.match(name or "")
    if not m or m.group(3) not in _MONTHS:
        return None
    base, day, mon, yy, strike, cp = m.groups()
    try:
        expiry = datetime(2000 + int(yy), _MONTHS[mon], int(day), EXPIRY_HOUR_UTC, tzinfo=UTC)
        k = float(strike.replace("d", "."))
    except ValueError:
        return None
    if not k > 0:
        return None
    return base, int(expiry.timestamp() * 1000), k, CALL if cp == "C" else PUT


def _num(x) -> float | None:
    if isinstance(x, bool) or not isinstance(x, int | float):
        return None
    return float(x) if math.isfinite(x) else None


def _side(x) -> float | None:
    v = _num(x)
    return v if v is not None and v > 0 else None


def normalize(raw: Iterable[Mapping]) -> tuple[list[dict], dict[str, int]]:
    """Filas completas en formato propio (ordenadas por vencimiento, precio y tipo) y cuántas
    se descartaron por cada motivo."""
    rows: list[dict] = []
    dropped: dict[str, int] = {}
    for r in raw:
        parsed = parse_name(str(r.get("instrument_name", "")))
        if parsed is None:
            dropped["nombre"] = dropped.get("nombre", 0) + 1
            continue
        vals = {k: _num(r.get(k)) for k in _REQUIRED}
        if any(v is None for v in vals.values()) or vals["underlying_price"] <= 0:
            dropped["campos"] = dropped.get("campos", 0) + 1
            continue
        _, expiry, strike, kind = parsed
        rows.append({
            "instrument": r["instrument_name"], "expiry": expiry, "strike": strike,
            "kind": kind, "bid": _side(r.get("bid_price")), "ask": _side(r.get("ask_price")),
            "mark": vals["mark_price"], "mark_iv": vals["mark_iv"],
            "underlying": vals["underlying_price"],
            "underlying_index": str(r.get("underlying_index") or ""),
            "rate": vals["interest_rate"], "oi": vals["open_interest"],
            "volume": _num(r.get("volume")), "ts": int(vals["creation_timestamp"]),
        })
    rows.sort(key=lambda x: (x["expiry"], x["strike"], x["kind"]))
    return rows, dropped


def by_expiry(rows: Sequence[Mapping]) -> dict[int, list[Mapping]]:
    out: dict[int, list[Mapping]] = {}
    for r in rows:
        out.setdefault(int(r["expiry"]), []).append(r)
    return dict(sorted(out.items()))


def _otm_interp(points: list[tuple[float, float]], x: float) -> float | None:
    pts = sorted(points)
    if not pts or x < pts[0][0] or x > pts[-1][0]:
        return None
    for (k0, v0), (k1, v1) in zip(pts, pts[1:], strict=False):
        if k0 <= x <= k1:
            return v0 + ((x - k0) / (k1 - k0) if k1 > k0 else 0.0) * (v1 - v0)
    return pts[-1][1]


def expiry_quality(rows: Sequence[Mapping], taken_ms: int) -> dict:
    """Calidad de un vencimiento: lo de `chain.analyze` (cruces, horquillas, arbitraje estático,
    σ ATM y sesgo 90/110) con los precios en USD, más la σ ATM de la marca de Deribit al lado
    para contrastar la conversión de unidades."""
    expiry = int(rows[0]["expiry"])
    t = (expiry - taken_ms) / YEAR_MS
    s = median(float(r["underlying"]) for r in rows)
    r_ = median(float(r["rate"]) for r in rows)
    base = {"expiry": expiry, "expiry_iso": _iso(expiry), "t_years": round(t, 6),
            "underlying": s, "rate": r_, "n_quotes": len(rows)}
    if t <= 0:
        return {**base, "status": "vencida", "warnings": ["vencimiento ya pasado en la toma"]}
    quotes = [Quote(float(r["strike"]), str(r["kind"]),
                    None if r["bid"] is None else float(r["bid"]) * float(r["underlying"]),
                    None if r["ask"] is None else float(r["ask"]) * float(r["underlying"]))
              for r in rows]
    rep = analyze(quotes, s, t, r_, b=0.0)
    marks = [(float(r["strike"]), float(r["mark_iv"]) / 100.0) for r in rows
             if (r["kind"] == PUT and r["strike"] <= s) or (r["kind"] == CALL and r["strike"] > s)]
    warnings = list(rep.warnings)
    if abs(r_) > SUSPECT_RATE:
        warnings.append(f"tipo {r_} sospechoso: ¿viene en %?")
    return {**base, "status": rep.status, "n_two_sided": rep.n_two_sided,
            "n_crossed": rep.n_crossed, "n_wide": rep.n_wide,
            "median_rel_spread": _r(rep.median_rel_spread),
            "n_arbitrage": len(rep.arbitrage), "arbitrage": rep.arbitrage[:MAX_ARB_LISTED],
            "n_iv": len(rep.iv), "n_iv_failures": len(rep.iv_failures),
            "atm_iv": _r(rep.atm_iv), "skew_90_110": _r(rep.skew_90_110),
            "mark_atm_iv": _r(_otm_interp(marks, s)), "warnings": warnings}


def snapshot_quality(rows: Sequence[Mapping], dropped: Mapping[str, int], taken_ms: int) -> dict:
    """Resumen de calidad de una toma entera: un bloque por vencimiento y el recuento de estados."""
    expiries = [expiry_quality(g, taken_ms) for g in by_expiry(rows).values()]
    status: dict[str, int] = {}
    for e in expiries:
        status[e["status"]] = status.get(e["status"], 0) + 1
    return {"n_rows": len(rows), "n_dropped": sum(dropped.values()), "dropped": dict(dropped),
            "n_expiries": len(expiries), "by_status": status, "expiries": expiries}


def _r(x: float | None) -> float | None:
    return None if x is None else round(float(x), 6)


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
