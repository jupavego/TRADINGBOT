"""Informe de los pesos por régimen (T197) → `reports/t197_pesos_regimen.md` y `.json`.

Uso (desde `v2/`, con la copia del banco de T131 como almacén):

    python -m eim.analytics.regime_weights_report --store data/t197_banco --workers 2

El panel se guarda en `<store>/cache/agent_panel/` (`--refresh` lo recalcula). El veredicto sale
de la puerta pre-registrada (`PLAN/notas/T197_preregistro.md`): esta tarea **no** escribe
`regime_weights` en `eim/synthesis/params.py`, pase o no pase; adoptarlo es una ◆ del usuario y va
después del cierre de T31.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from eim.analytics.agent_panel import load_or_compute
from eim.analytics.regime_weights import (
    BLOCK_DAYS,
    GATE_DELTA,
    GATE_MDE,
    H_PRIMARY,
    H_SECONDARY,
    MIN_N,
    NAMES,
    PANEL_STEP,
    REGIMES,
    THR_IC,
    evaluate,
)
from eim.data.store import Store

OUT = Path(__file__).resolve().parents[2] / "reports"


def _d(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%d")


def _f(x, nd: int = 4) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "—"
    return "—" if v != v else f"{v:+.{nd}f}"


def _ci(ci, nd: int = 4) -> str:
    return f"[{_f(ci[0], nd)}, {_f(ci[1], nd)}]" if ci else "—"


def _cells_table(r: dict) -> list[str]:
    L = ["| Agente | Régimen | n | IC en el régimen | IC global | Multiplicador | Por qué |",
         "|---|---|---|---|---|---|---|"]
    for c in r.get("cells", []):
        L.append(f"| `{c['agent']}` | {NAMES.get(c['regime'], c['regime'])} | {c['n']} | "
                 f"{_f(c['ic'])} | {_f(c['ic_all'])} | {c['m']:g} | {c['why']} |")
    return L


def _test_table(t: dict) -> list[str]:
    p, s, b = t["primary"], t["secondary"], t["backtest"]
    return ["| Métrica | Plana | Por régimen | Diferencia | IC95 |", "|---|---|---|---|---|",
            f"| IC a {p['h']} velas (primaria) | {_f(p['ic_flat'])} | {_f(p['ic'])} | "
            f"{_f(p['delta'])} | {_ci(p['ci95'])} |",
            f"| IC a {s['h']} velas | {_f(s['ic_flat'])} | {_f(s['ic'])} | {_f(s['delta'])} | "
            f"{_ci(s['ci95'])} |",
            f"| Sharpe (backtest T25) | {_f(b['flat']['sharpe'], 2)} | "
            f"{_f(b['regime']['sharpe'], 2)} | {_f(t['delta_sharpe'], 2)} | — |",
            f"| E[R] por operación | {_f(b['flat']['expectancy_r'], 3)} | "
            f"{_f(b['regime']['expectancy_r'], 3)} | {_f(t['delta_expectancy_r'], 3)} | — |",
            f"| Operaciones | {b['flat']['n_trades']} | {b['regime']['n_trades']} | — | — |"]


def to_markdown(r: dict, made: str, store: str) -> str:
    L = ["# Pesos por régimen en la síntesis (T197)", "",
         f"Generado {made} con `python -m eim.analytics.regime_weights_report`. "
         "Análisis histórico sobre una copia: **no es una promesa de resultados**.", "",
         f"## Veredicto: **{r.get('verdict', '—')}**", "", r.get("why", ""), "",
         "`SynthesisParams.regime_weights` sigue `{}`: esta tarea mide y no adopta.", "",
         "## Datos", "",
         f"- Almacén: `{store}` (copia del banco de T131; el almacén vivo no se lee ni se toca).",
         f"- {r['symbol']} {r['timeframe']}, {_d(r['from'])} → {_d(r['to'])}: "
         f"**{r['asofs']} instantes** del panel (uno cada {r['panel_step']} velas).",
         f"- Partición: descubrimiento hasta {_d(r['cut'])}, prueba desde ahí.",
         f"- `regime` etiqueta {r['regime_labelled']} instantes ({r['regime_share']:.1%}).",
         "", "| Régimen | Instantes |", "|---|---|"]
    for g in REGIMES:
        L.append(f"| {NAMES[g]} | {r['regime_counts'].get(g, 0)} |")
    L += ["", f"Agentes que votan con peso > 0 y entran en la medición: "
          f"{', '.join('`' + a + '`' for a in r['voters']) or '—'}.", "",
          "### Cobertura real por agente (fracción de instantes en cada estado)", "",
          "| Agente | ok | degradado | sin datos |", "|---|---|---|---|"]
    for a, cov in r["coverage"].items():
        L.append(f"| `{a}` | {cov.get('ok', 0):.2f} | {cov.get('degraded', 0):.2f} | "
                 f"{cov.get('no_data', 0):.2f} |")
    if "cells" in r:
        L += ["", "## Multiplicadores de descubrimiento", "",
              f"Escalera pre-registrada: 1,5 si el IC del agente en ese régimen supera su IC "
              f"global en ≥ {THR_IC}; 0,5 si queda ≤ −{THR_IC}; 1,0 en otro caso y siempre que "
              f"haya menos de {MIN_N} muestras.", ""]
        L += _cells_table(r)
        L += ["", f"Candidato: `{json.dumps(r.get('multipliers', {}), ensure_ascii=False)}`."]
    if "power" in r:
        p = r["power"]
        L += ["", "## Potencia (entregable 0, antes de mirar la prueba)", "",
              f"- ΔIC en descubrimiento: {_f(p['delta_discovery'])} "
              f"(n = {p['n_discovery']}, error estándar {_f(p['se_discovery'])}).",
              f"- Mejora mínima detectable en la prueba (n = {p['n_test']}, 80 % de potencia, "
              f"α = 0,05 bilateral): **{_f(p['mde'])}**, puerta {GATE_MDE}."]
    if "test" in r:
        L += ["", "## Fuera de muestra (mitad de prueba)", ""]
        L += _test_table(r["test"])
    L += ["", "## Método", "",
          f"- Panel de T44 sin cambios (`agent_panel`), un instante cada {PANEL_STEP} velas, "
          "calentamiento de 500 velas y snapshots idénticos a los que vería el sistema.",
          f"- Métrica primaria: IC de Spearman entre `sesgo × confianza` de la síntesis y el "
          f"log-retorno a {H_PRIMARY} velas, muestras sin solape; IC95 por bootstrap emparejado "
          f"en bloques de {BLOCK_DAYS} días (1 000 remuestreos, misma semilla en las dos "
          f"variantes). Secundaria: {H_SECONDARY} velas y el backtest de T25 con costos de "
          "perpetuo y el funding del banco.",
          f"- Puerta pre-registrada: MDE ≤ {GATE_MDE}, ΔIC ≥ +{GATE_DELTA} con IC95 que excluya 0 "
          "y ΔE[R] ≥ 0. Las tres, o no se adopta.",
          "", "## Limitaciones", "",
          "- Un solo activo y un solo marco (BTCUSDT 1 h): más combinaciones serían más intentos "
          "y el pre-registro declara uno.",
          "- Sin historia point-in-time de open interest, long/short, base, calendario, líderes, "
          "arbitraje ni microestructura: sus agentes salen `no_data` en el panel (la tabla de "
          "cobertura lo muestra), así que la síntesis histórica usa menos agentes que la de vivo.",
          "- Ninguna llamada de producción pasa hoy `regime=` a `synthesize`: adoptar los "
          "multiplicadores exigiría además cablear la etiqueta en esas llamadas.",
          "- Una sola regla de operación fija, sin optimizar, igual que en T44.", ""]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", default="data/t197_banco")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    t0 = time.time()
    df = load_or_compute(a.store, a.symbol, "1h", PANEL_STEP, a.workers, a.refresh)
    print(f"panel: {df['asof'].nunique()} instantes ({time.time() - t0:.0f} s)", flush=True)
    store = Store(a.store)
    res = evaluate(df, store.read_candles(a.symbol, "1h"),
                   store.read_series("funding", a.symbol) or None, a.symbol)
    made = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "t197_pesos_regimen.json").write_text(
        json.dumps({"made": made, "store": a.store, "result": res}, ensure_ascii=False,
                   indent=1, default=float), encoding="utf-8")
    (out / "t197_pesos_regimen.md").write_text(to_markdown(res, made, a.store), encoding="utf-8")
    print(f"{res.get('verdict')}: {res.get('why')}")


if __name__ == "__main__":
    main()
