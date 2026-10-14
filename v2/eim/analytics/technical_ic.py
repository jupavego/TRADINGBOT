"""Valor predictivo de cada voto del agente `technical` fuera de muestra (T35).

Para cada indicador (y el sesgo agregado) se mide el IC de Spearman entre el voto en `t` y el
retorno logarítmico de `t` a `t+h`, solo en la parte de prueba (último `test_frac` de la serie).
La agrupación anti-redundancia del sesgo agregado se estima en la parte de descubrimiento.
Las muestras se toman cada `h` velas (sin solapamiento) para que el p-valor sea válido.
p-valor: aproximación normal z = IC·√(n−1) (n de cientos); corrección de Holm sobre todas las
pruebas (indicadores × horizontes × activos). Las reglas son fijas (sin ajuste a los datos).

Uso: `python -m eim.analytics.technical_ic --symbols BTCUSDT ETHUSDT --timeframes 1h 4h`
"""

from __future__ import annotations

import argparse
import math
from collections.abc import Sequence

import numpy as np
import pandas as pd

from eim.agents.technical.frame import analyze_arrays
from eim.agents.technical.params import TechnicalParams
from eim.agents.technical.rules import RULES
from eim.backtest.edge import holm
from eim.core import Candle
from eim.indicators import candle_arrays

AGG = "technical (agregado)"


def spearman(x: np.ndarray, y: np.ndarray) -> tuple[float, int, float]:
    """IC de Spearman, n válido y p-valor bilateral (aprox. normal). NaN si no hay varianza."""
    ok = ~(np.isnan(x) | np.isnan(y))
    n = int(ok.sum())
    if n < 10:
        return float("nan"), n, float("nan")
    rx, ry = pd.Series(x[ok]).rank().to_numpy(), pd.Series(y[ok]).rank().to_numpy()
    if rx.std() == 0 or ry.std() == 0:
        return float("nan"), n, float("nan")
    ic = float(np.corrcoef(rx, ry)[0, 1])
    return ic, n, math.erfc(abs(ic) * math.sqrt(n - 1) / math.sqrt(2))


def vote_series(candles: Sequence[Candle], p: TechnicalParams,
                test_frac: float) -> tuple[dict[str, np.ndarray], np.ndarray, int]:
    """Votos por indicador + sesgo agregado (plan de grupos estimado antes de la prueba)."""
    data = candle_arrays(candles)
    start = int(len(candles) * (1 - test_frac))
    disc = analyze_arrays({k: v[:start] for k, v in data.items()}, p, RULES)
    full = analyze_arrays(data, p, RULES, plan=disc.plan)
    votes = {**full.votes, AGG: full.bias}
    return votes, data["close"], start


def measure(candles: Sequence[Candle], horizons: Sequence[int], label: str,
            p: TechnicalParams | None = None, test_frac: float = 0.5) -> list[dict]:
    p = p or TechnicalParams()
    votes, close, start = vote_series(candles, p, test_frac)
    logc = np.log(close)
    rows = []
    for h in horizons:
        idx = np.arange(start, len(close) - h, h)
        fwd = logc[idx + h] - logc[idx]
        for k, v in votes.items():
            ic, n, pv = spearman(v[idx], fwd)
            rows.append({"asset": label, "indicator": k, "h": h, "ic": ic, "n": n, "p": pv})
    return rows


def adjust(rows: list[dict], alpha: float = 0.05) -> list[dict]:
    keys = {i: r["p"] for i, r in enumerate(rows) if not math.isnan(r["p"])}
    adj = holm({str(i): pv for i, pv in keys.items()})
    for i, r in enumerate(rows):
        r["p_holm"] = adj.get(str(i), float("nan"))
        r["significant"] = bool(r["p_holm"] <= alpha)
    return rows


def _fmt(x: float, f: str) -> str:
    return "—" if math.isnan(x) else format(x, f)


def report(rows: list[dict], meta: list[str], alpha: float = 0.05) -> str:
    sig = [r for r in rows if r["significant"]]
    tested = sum(1 for r in rows if not math.isnan(r["p"]))
    L = ["# Valor predictivo de los indicadores del agente `technical` (T35)", "", *meta, "",
         f"Pruebas con dato: {tested}; corrección de Holm, α = {alpha}.", ""]
    if not sig:
        L.append("**Veredicto: ningún indicador (ni el sesgo agregado) supera el azar fuera de "
                 "muestra tras corregir por pruebas múltiples.** El agente informa; no es una "
                 "señal con edge demostrado, y por eso no vota en la síntesis (T44 decide).")
    else:
        pos = sorted({f"{r['indicator']} ({r['asset']}, h={r['h']})" for r in sig if r["ic"] > 0})
        neg = sorted({f"{r['indicator']} ({r['asset']}, h={r['h']})" for r in sig if r["ic"] < 0})
        agg = [r for r in sig if r["indicator"] == AGG]
        L.append(f"**Veredicto: {len(sig)} de {tested} pruebas son significativas tras Holm; "
                 f"el sesgo agregado {'sí' if agg else 'no'} supera el azar.** Un IC "
                 "significativo de magnitud pequeña no implica operabilidad tras costos (T27).")
        L += ["", f"- IC positivo (el voto acierta): {', '.join(pos) or 'ninguno'}.",
              f"- IC negativo (el voto apunta al revés): {', '.join(neg) or 'ninguno'}."]
    L += ["", "| Activo | Indicador | h | IC | n | p | p Holm | Sig. |", "|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["asset"], r["h"], -abs(np.nan_to_num(r["ic"])))):
        L.append(f"| {r['asset']} | {r['indicator']} | {r['h']} | {_fmt(r['ic'], '+.4f')} | "
                 f"{r['n']} | {_fmt(r['p'], '.4f')} | {_fmt(r['p_holm'], '.4f')} | "
                 f"{'sí' if r['significant'] else 'no'} |")
    L.append("")
    return "\n".join(L)


def main() -> None:  # pragma: no cover - uso manual con datos reales
    from eim.data.store import Store

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    ap.add_argument("--timeframes", nargs="+", default=["1h", "4h"])
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--horizons", nargs="+", type=int, default=[1, 6, 24])
    ap.add_argument("--test-frac", type=float, default=0.5)
    ap.add_argument("--out", default="reports/technical_ic.md")
    a = ap.parse_args()
    store = Store(a.data_dir)
    rows, meta = [], []
    for sym in a.symbols:
        for tf in a.timeframes:
            cs = store.read_candles(sym, tf)
            if not cs:
                meta.append(f"- {sym} {tf}: sin velas en el almacén")
                continue
            start = int(len(cs) * (1 - a.test_frac))
            flow = sum(c.taker_buy_v is not None for c in cs[start:])
            day = lambda t: f"{pd.to_datetime(t, unit='ms'):%Y-%m-%d}"  # noqa: E731
            meta.append(f"- {sym} {tf}: {len(cs)} velas ({day(cs[0].t)} → {day(cs[-1].t)}); "
                        f"prueba desde {day(cs[start].t)}; velas de prueba con taker_buy_v: "
                        f"{flow}/{len(cs) - start}; fuente {store.source('candles', sym, tf)}")
            rows += measure(cs, a.horizons, f"{sym} {tf}", test_frac=a.test_frac)
    text = report(adjust(rows), meta)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(text)
    print(text.split("| Activo")[0])


if __name__ == "__main__":  # pragma: no cover
    main()
