"""Informe de contribución marginal de los agentes nuevos (T44) → `reports/agents_marginal.md`.

Uso (desde `v2/`):
    python -m eim.analytics.agents_marginal_report --symbols BTCUSDT ETHUSDT --workers 6

El panel histórico se guarda en `data/cache/agent_panel/` (`--refresh` lo recalcula). Los
números van también a `reports/agents_marginal.json`. La decisión (`RULE`) fija el peso
inicial de cada agente nuevo en `eim/synthesis/params.py` (`T44_WEIGHTS`, a mano y citando
este informe: el código nunca se reescribe solo).
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from eim.analytics.agent_panel import load_or_compute
from eim.analytics.agents_marginal import (
    BT,
    DISC_FRAC,
    HORIZONS,
    NEW,
    PANEL_STEP,
    Q_SIGNAL,
    RR,
    RULE,
    SL_ATR,
    WIN_TEST,
    evaluate,
    passes,
)
from eim.data.store import Store
from eim.synthesis.params import MODERATE_WEIGHT

OUT = Path(__file__).resolve().parents[2] / "reports"


def _d(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%d")


def _f(x, nd: int = 2, pct: bool = False) -> str:
    if x is None:
        return "—"
    return f"{x * 100:+.{nd}f} %" if pct else f"{x:+.{nd}f}"


def decide(results: list[dict]) -> dict:
    """Peso inicial por agente nuevo: moderado si aporta en TODOS los activos; si no, 0."""
    out = {}
    for a in NEW:
        why = {r["symbol"]: passes(r, a) for r in results}
        ok = bool(why) and all(v[0] for v in why.values())
        out[a] = {"aporta": ok, "weight": MODERATE_WEIGHT if ok else 0.0,
                  "why": {s: v[1] for s, v in why.items()}}
    return out


def _corr_rows(c: dict) -> list[str]:
    rows = []
    for k, v in c.items():
        a, p = k.split("~")
        rows.append(f"| {a} | {p} | {v['n']} | {_f(v['pearson'])} | {_f(v['spearman'])} |")
    return rows


def _pct0(x: float | None) -> str:
    return "—" if x is None else f"{x:.0%}"


def _ci(ci: list[float] | None, nd: int = 2) -> str:
    return f"[{_f(ci[0], nd)}, {_f(ci[1], nd)}]" if ci else "[—]"


def _variant_row(k: str, v: dict) -> str:
    m, ic, vb = v["metrics"], v["ic"], v.get("vs_base") or {}
    d_ic = "—" if k == "base" else f"{_f(ic[1]['delta'], 4)} {_ci(ic[1]['delta_ci95'], 3)}"
    p = "—" if not vb else f"{vb['sharpe_p']:.3f}"
    return (f"| {k} | {m['n_trades']} | {_f(m['total_return'], 1, True)} | "
            f"{_f(m['sharpe'])} {_ci(v['ci95'].get('sharpe'))} | {_f(m['expectancy_r'], 3)} | "
            f"{_pct0(m['win_rate'])} | {m['max_drawdown']:.1%} | {_f(ic[0]['ic'], 4)} | "
            f"{_f(ic[1]['ic'], 4)} | {d_ic} | {p} | {_pct0(vb.get('win_share'))} |")


def _reading(results: list[dict]) -> list[str]:
    """Lectura breve generada de los números (sin texto a mano que quede viejo)."""
    out = ["### Lectura", ""]
    for r in results:
        v = r["variants"]
        b = v["base"]["metrics"]
        t, t1 = v["+technical"], v["+technical (peso 1, sin penalización)"]
        d, d1 = t["metrics"]["sharpe"] - b["sharpe"], t1["metrics"]["sharpe"] - b["sharpe"]
        robust = "mismo signo" if d * d1 > 0 else "el signo cambia con el peso: no es robusto"
        deg = r["coverage"].get("technical", {}).get("degraded", 0)
        out.append(
            f"- {r['symbol']}: la síntesis base pierde en la prueba (Sharpe {_f(b['sharpe'])}, "
            f"E[R] {_f(b['expectancy_r'], 3)}): no hay ventaja que mejorar (T27). `technical` a "
            f"peso moderado: ΔSharpe {_f(d)} (p {t['vs_base']['sharpe_p']:.3f}); a peso 1 sin "
            f"penalización: ΔSharpe {_f(d1)} — {robust}. `technical` sale degradado en el "
            f"{deg:.1%} del panel (histórico sin `taker_buy_v`).")
    return out


def to_markdown(results: list[dict], dec: dict, made: str) -> str:
    L = ["# Contribución marginal de los agentes nuevos en la síntesis (T44)", "",
         f"Generado {made} con `python -m eim.analytics.agents_marginal_report`. "
         "Análisis histórico: **no es una promesa de resultados**.", "",
         "## Decisión", "",
         "| Agente | ¿Aporta fuera de muestra? | Peso inicial vigente | Motivo por activo |",
         "|---|---|---|---|"]
    for a, d in dec.items():
        why = "; ".join(f"{s}: {w}" for s, w in d["why"].items())
        L.append(f"| `{a}` | {'sí' if d['aporta'] else '**no**'} | {d['weight']:g} | {why} |")
    L += ["", f"Regla fijada antes de mirar la prueba: {RULE}.", "", *_reading(results), "",
          "## Método", "",
          f"- Panel: reportes reales de todos los agentes (salvo `plan`, `context`, "
          f"`arbitrage`) cada {PANEL_STEP} velas de 1 h, con snapshots idénticos a "
          "`build_snapshot` (recorte en memoria; probado) — `eim/analytics/agent_panel.py`.",
          f"- Partición: primera {DISC_FRAC:.0%} = descubrimiento (correlaciones y umbral), "
          "resto = prueba (todo lo que decide).",
          "- Variantes: síntesis base (pesos de `technical` y `smart_money` = 0) frente a la "
          f"síntesis con el agente a peso moderado {MODERATE_WEIGHT:g} y penalización por "
          "correlación (peso × (1 − ρ⁺ máx. con `ema`/`structure` cuando votan)); sensibilidad "
          "con peso 1 sin penalización.",
          f"- Backtest T25 (`walk_forward`, costos de perpetuo, ventanas disjuntas de "
          f"{WIN_TEST} velas = 90 días, capital nuevo por ventana): señal = signo de "
          f"sesgo × confianza de la síntesis si |s| ≥ cuantil {Q_SIGNAL:.0%} de esa variante "
          f"en descubrimiento; SL {SL_ATR:g} ATR, TP {RR:g} R, salida por tiempo "
          f"{BT.max_hold_bars} velas, riesgo {BT.risk_frac:.0%} por operación.",
          f"- IC: Spearman de s contra el log-retorno a {', '.join(map(str, HORIZONS))} velas "
          "(muestras sin solape); diferencia con la base por bootstrap pareado (IC 95 %).", ""]
    for r in results:
        sym = r["symbol"]
        L += [f"## {sym}", "",
              f"{r['asofs']} instantes de {_d(r['from'])} a {_d(r['to'])}; prueba desde "
              f"{_d(r['cut'])}.", "", "### Cobertura del panel (fracción de instantes)", "",
              "| Agente | ok | degradado | sin datos |", "|---|---|---|---|"]
        for a, c in r["coverage"].items():
            L.append(f"| {a} | {c.get('ok', 0):.0%} | {c.get('degraded', 0):.0%} | "
                     f"{c.get('no_data', 0):.0%} |")
        L += ["", "### Correlación entre reportes (sesgo; velas con datos en ambos)", "",
              "Descubrimiento (fija la penalización):", "",
              "| Nuevo | Existente | n | Pearson | Spearman |", "|---|---|---|---|---|",
              *_corr_rows(r["corr_disc"]), "", "Prueba (control de estabilidad):", "",
              "| Nuevo | Existente | n | Pearson | Spearman |", "|---|---|---|---|---|",
              *_corr_rows(r["corr_test"]), "",
              "### Resultados en la mitad de prueba", "",
              "| Variante | Ops | Retorno | Sharpe [IC95] | E[R] | Acierto | Caída máx. | "
              "IC 4 v | IC 24 v | ΔIC 24 v [IC95] | Δ Sharpe p | Gana ventanas |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for k, v in r["variants"].items():
            L.append(_variant_row(k, v))
        L += ["", "Sharpe por ventana de 90 días (base → con el agente):", ""]
        b = r["variants"]["base"]["windows"]
        for a in NEW:
            w = r["variants"][f"+{a}"]["windows"]
            L.append(f"- `{a}`: " + ", ".join(f"{_d(x['from'])} {_f(x['sharpe'])}→{_f(y['sharpe'])}"
                                               for x, y in zip(b, w, strict=True)))
        L.append("")
    L += ["## Limitaciones", "",
          "- `smart_money`: el tablero de líderes existe desde 2026-10-16 y no hay ningún líder "
          "aprobado → en todo el histórico da `no_data`; su aporte no es medible y su peso "
          "inicial queda en 0 hasta tener semanas de veredictos adelante (T41/T42).",
          "- `calendar`: no vota (bias = 0). Su efecto (confianza × 0,75 en ventana, × 0,5 con "
          "blackout; tamaño × 0,5 en ventana sin blackout con `risk_v2`; veto con blackout) es "
          "defensivo y no se evalúa aquí: no hay calendario point-in-time antes de 2026-10-14.",
          "- `derivatives`, `microstructure`, `liquidations` y `context` tampoco tienen historia "
          "completa: la síntesis histórica usa menos agentes que la de vivo.",
          "- Una sola regla de operación fija (sin optimizar); otro umbral o salida puede dar "
          "otro resultado. Las ventanas incompletas al final de la serie se descartan.", ""]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", default="data")
    ap.add_argument("--symbols", nargs="+", default=["BTCUSDT"])
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    store = Store(a.store)
    results = []
    for sym in a.symbols:
        t0 = time.time()
        df = load_or_compute(a.store, sym, "1h", PANEL_STEP, a.workers, a.refresh)
        n = df["asof"].nunique()
        print(f"{sym}: panel {n} instantes ({time.time() - t0:.0f} s)", flush=True)
        results.append(evaluate(df, store.read_candles(sym, "1h"),
                                store.read_series("funding", sym) or None, sym))
    dec = decide(results)
    made = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "agents_marginal.json").write_text(
        json.dumps({"made": made, "rule": RULE, "decision": dec, "results": results},
                   ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    (out / "agents_marginal.md").write_text(to_markdown(results, dec, made), encoding="utf-8")
    for k, d in dec.items():
        print(f"{k}: {'aporta' if d['aporta'] else 'no aporta'} → peso {d['weight']:g}")


if __name__ == "__main__":
    main()
