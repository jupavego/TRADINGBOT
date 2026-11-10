"""T150 entregable 5 — calibración de la confianza de la síntesis, antes (v1) y después (v2).

Regla fijada antes de calcular (◆2 de T146): **v2 se adopta en el panel sea cual sea el
resultado**; esto se publica aunque sea desfavorable. Se mide, para cada instante con dirección
(sesgo ≠ 0), si la dirección de la síntesis acierta el signo del log-retorno a `H` velas
(1 h → 24, 4 h → 6: un día en ambos marcos) y cómo se reparte la confianza frente al acierto:

- Acierto direccional y tabla de fiabilidad (confianza por tramos frente al acierto real).
- Brier con dos lecturas de la confianza, porque el contrato no la fija: (A) la confianza es la
  probabilidad de acertar la dirección (lo que dice T150: «70 % debe acertar el 70 %»); (B) la
  confianza es la distancia a una moneda: P(acierto) = 0,5 + confianza / 2. Referencia: Brier de
  decir siempre la tasa de acierto observada (A) o 0,5 (B, = 0,25).

Fuentes: (1) banco de T131 (`backups/t131_banco`, BTCUSDT 1 h 2023-01 → 2026-11) pasado por el
panel de T44 cada 4 velas (`eim.analytics.agent_panel`): las ventanas de v2 se cuentan en filas
del panel con el mismo tramo de tiempo (cobertura 12 filas = 48 h, correlación 50 = 200 h). (2) Los
reportes guardados en vivo (una copia de `reports.duckdb`), con las ventanas del panel tal cual.

Uso (por la cola, 2 procesos como mucho):
    python scripts/t150_calibracion.py --banco backups/t131_banco \
        --live-reports backups/<copia>/reports.duckdb --live-data data --workers 2
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import deque
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eim.core import AgentReport  # noqa: E402
from eim.data.store import Store  # noqa: E402
from eim.data.timeframes import tf_ms  # noqa: E402
from eim.synthesis import synthesize  # noqa: E402
from eim.synthesis.evidence import coverage_of  # noqa: E402
from eim.synthesis.params import EvidenceParams  # noqa: E402

HORIZON = {"1h": 24, "4h": 6}
PANEL_STEP = 4
LIVE = EvidenceParams()
PANEL = EvidenceParams(coverage_bars=12, min_bars=3, corr_bars=50)   # mismo tramo, filas de 4 h
BINS = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 1.0001)


def outcomes(candles, step: int, h: int) -> dict[int, int]:
    """asof → signo del retorno de cierre en `asof` (vela t = asof − step) a cierre `h` velas
    después; 0 si no se movió. Solo instantes con su vela futura en el almacén."""
    close = {c.t: c.c for c in candles}
    out = {}
    for t, c0 in close.items():
        c1 = close.get(t + h * step)
        if c1 is not None and c0 > 0:
            out[t + step] = (c1 > c0) - (c1 < c0)
    return out


def evaluate(by_asof: dict[int, list[AgentReport]], y: dict[int, int], ep: EvidenceParams,
             expected: list[str] | None) -> pd.DataFrame:
    """v1 y v2 en cada instante (v2 con la evidencia de los instantes anteriores e incluido)."""
    keep = max(ep.coverage_bars, ep.corr_bars)
    hist: deque[list[tuple]] = deque(maxlen=keep)
    rows = []
    for asof in sorted(by_asof):
        reps = by_asof[asof]
        hist.append([(asof, r.agent_id, r.bias, r.confidence, r.status) for r in reps])
        exp = expected or sorted({r.agent_id for r in reps})
        ev = coverage_of([x for b in hist for x in b], exp, ep)
        if asof not in y:
            continue
        for name, syn in (("v1", synthesize(reps, expected=exp)),
                          ("v2", synthesize(reps, expected=exp, evidence=ev,
                                            evidence_params=ep))):
            if syn is None:
                continue
            rows.append((asof, name, syn.bias, syn.confidence, syn.effective_votes,
                         syn.voters, len(syn.contributions), y[asof]))
    return pd.DataFrame(rows, columns=["asof", "variant", "bias", "conf", "n_eff", "voters",
                                       "n_contrib", "y"])


def metrics(df: pd.DataFrame, thin: int = 1) -> dict:
    """Métricas de una variante; `thin` = filas entre muestras sin solape de horizonte."""
    d = df[(df.bias != 0) & (df.y != 0)].sort_values("asof")
    if d.empty:
        return {"n": 0}
    hit = ((d.bias > 0).astype(int) * 2 - 1 == d.y).astype(float)
    pa, pb = d.conf.clip(0, 1), 0.5 + d.conf.clip(0, 1) / 2
    rate = float(hit.mean())
    rel = []
    for lo, hi in zip(BINS, BINS[1:], strict=False):
        m = (d.conf >= lo) & (d.conf < hi)
        if m.any():
            rel.append({"tramo": f"{lo:.1f}–{min(hi, 1):.1f}", "n": int(m.sum()),
                        "conf_media": float(d.conf[m].mean()), "p_b_media": float(pb[m].mean()),
                        "acierto": float(hit[m].mean())})
    def ece(p):
        return sum(r["n"] * abs((r["conf_media"] if p is pa else r["p_b_media"]) - r["acierto"])
                   for r in rel) / len(d)
    n = len(d)
    ht = hit.iloc[::thin]
    rt = float(ht.mean())
    return {"n": n, "acierto": rate, "ic95": 1.96 * math.sqrt(rate * (1 - rate) / n),
            "n_sin_solape": len(ht), "acierto_sin_solape": rt,
            "ic95_sin_solape": 1.96 * math.sqrt(rt * (1 - rt) / len(ht)),
            "conf_media": float(d.conf.mean()), "n_eff_media": _mean(d.n_eff),
            "votantes_media": _mean(d.voters),
            "brier_a": float(((pa - hit) ** 2).mean()), "ref_a": rate * (1 - rate),
            "brier_b": float(((pb - hit) ** 2).mean()), "ref_b": 0.25,
            "ece_a": ece(pa), "ece_b": ece(pb), "fiabilidad": rel}


def _mean(s: pd.Series) -> float | None:
    s = s.dropna()
    return float(s.mean()) if len(s) else None


def banco_reports(root: Path, workers: int, cache: Path) -> dict[int, list[AgentReport]]:
    from eim.analytics.agent_panel import SNAP_BARS, PanelData, compute_panel
    if cache.exists():
        df = pd.read_parquet(cache)
    else:
        data = PanelData(Store(root), "BTCUSDT", "1h")
        asofs = [t + data.step for t in data.t[SNAP_BARS::PANEL_STEP]]
        df = compute_panel(root, "BTCUSDT", "1h", asofs, workers)
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache, index=False)
    out: dict[int, list[AgentReport]] = {}
    for r in df.itertuples(index=False):
        out.setdefault(int(r.asof), []).append(AgentReport(
            agent_id=r.agent, version="panel", asof=int(r.asof), bias=float(r.bias),
            confidence=float(r.conf), horizon_bars=1, status=r.status))
    return out


def live_reports(path: Path, symbol: str, tf: str) -> dict[int, list[AgentReport]]:
    """Reportes guardados (última versión por agente e instante), tal como los vio el panel."""
    con = duckdb.connect(str(path), read_only=True)
    q = ("SELECT report FROM reports WHERE symbol = ? AND timeframe = ? QUALIFY row_number() "
         "OVER (PARTITION BY agent_id, asof_ms ORDER BY version DESC) = 1")
    out: dict[int, list[AgentReport]] = {}
    for (js,) in con.execute(q, [symbol, tf]).fetchall():
        r = AgentReport.model_validate_json(js)
        out.setdefault(r.asof, []).append(r)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--banco", type=Path, required=True)
    ap.add_argument("--live-reports", type=Path)
    ap.add_argument("--live-data", type=Path)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--cache", type=Path, default=Path("reports/t150/panel_btc_1h_s4.parquet"))
    ap.add_argument("--out", type=Path, default=Path("reports/t150_calibracion"))
    a = ap.parse_args()
    results: dict[str, dict] = {}
    frames = []
    step = tf_ms("1h")
    y = outcomes(Store(a.banco).read_candles("BTCUSDT", "1h"), step, HORIZON["1h"])
    df = evaluate(banco_reports(a.banco, min(a.workers, 2), a.cache), y, PANEL, None)
    thin = HORIZON["1h"] // PANEL_STEP
    results["banco T131 · BTCUSDT 1h (cada 4 velas)"] = {v: metrics(df[df.variant == v], thin)
                                                          for v in ("v1", "v2")}
    frames.append(df.assign(fuente="banco_btc_1h"))
    if a.live_reports and a.live_data:
        from eim.agents.registry import default_registry
        expected = [x.id for x in default_registry().latest()]
        for sym, tf in (("BTCUSDT", "1h"), ("BTCUSDT", "4h"), ("ETHUSDT", "1h")):
            yy = outcomes(Store(a.live_data).read_candles(sym, tf), tf_ms(tf), HORIZON[tf])
            d = evaluate(live_reports(a.live_reports, sym, tf), yy, LIVE, expected)
            results[f"en vivo · {sym} {tf}"] = {v: metrics(d[d.variant == v], HORIZON[tf])
                                                for v in ("v1", "v2")}
            frames.append(d.assign(fuente=f"vivo_{sym}_{tf}"))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(frames).to_csv(a.out.with_suffix(".csv"), index=False)
    a.out.with_suffix(".json").write_text(json.dumps(results, indent=1, ensure_ascii=False),
                                          encoding="utf-8")
    print(json.dumps({k: {v: {m: x for m, x in r.items() if m != "fiabilidad"}
                          for v, r in vs.items()} for k, vs in results.items()},
                     indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
