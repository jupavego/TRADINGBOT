"""Informe del estudio de eventos (T37): carga datos, ejecuta `event_study` y escribe el markdown.

Reproducible: la lista de eventos usada se guarda en `reports/calendar/events.csv`; sin
`--fetch` se relee de ahí (no hay red), y las velas salen del almacén local.

Uso (desde `v2/`):
  python -m eim.analytics.event_report --fetch          # descarga fuentes oficiales y guarda CSV
  python -m eim.analytics.event_report                  # re-ejecuta con el CSV guardado
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from datetime import UTC, datetime
from pathlib import Path

from eim.analytics.event_study import EVENT_TYPES, WINDOWS, Bars, StudyParams, run_study

WIN_LABEL = {"pre_60": "−60…0 min", "post_15": "0…+15 min", "post_60": "0…+1 h",
             "post_240": "0…+4 h"}


def fetch_events(t_lo: int, t_hi: int) -> list[tuple[int, str, str, str]]:
    """Fuentes oficiales (T36) + vencimientos por regla → (t, nombre, impacto, fuente)."""
    from eim.data.calendar import quarterly_expiries
    from eim.data.providers.calendar import OfficialCalendar

    now = int(time.time() * 1000)
    got = OfficialCalendar().fetch_all(now)
    missing = [s for s, ev in got.items() if ev is None]
    if missing:
        raise SystemExit(f"fuentes sin respuesta: {missing}; no se genera un estudio parcial")
    evs = [e for ev in got.values() for e in (ev or [])]
    y0 = datetime.fromtimestamp(t_lo / 1000, tz=UTC).year
    y1 = datetime.fromtimestamp(t_hi / 1000, tz=UTC).year
    for y in range(y0, y1 + 1):
        lo = int(datetime(y, 1, 1, tzinfo=UTC).timestamp() * 1000)
        evs += quarterly_expiries(lo, lo + 360 * 86_400_000, now)
    uniq = {e.id: e for e in evs if t_lo <= e.t_utc < t_hi}
    return sorted((e.t_utc, e.name, e.impact, e.id.split(":", 1)[0]) for e in uniq.values())


def save_events(path: Path, events: list[tuple[int, str, str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t_utc", "iso_utc", "name", "impact", "source"])
        for t, n, imp, s in events:
            w.writerow([t, datetime.fromtimestamp(t / 1000, tz=UTC).isoformat(), n, imp, s])


def load_events(path: Path) -> list[tuple[int, str, str, str]]:
    with path.open(encoding="utf-8") as f:
        return [(int(r["t_utc"]), r["name"], r["impact"], r["source"])
                for r in csv.DictReader(f)]


# --- formato ------------------------------------------------------------------
def _f(x: float, fmt: str = ".2f") -> str:
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else format(x, fmt)


def _p(x: float) -> str:
    return "—" if x is None or math.isnan(x) else ("<0.001" if x < 0.001 else f"{x:.3f}")


def _day(t: int) -> str:
    return datetime.fromtimestamp(t / 1000, tz=UTC).strftime("%Y-%m-%d")


def _verdict(rec: dict) -> str:
    if rec["status"] == "insuficiente":
        return "muestra insuficiente: no se fija ventana por evidencia"
    if rec["status"] == "sin_efecto":
        return ("**no mueve el mercado** de forma detectable (ninguna vela ni ventana "
                "significativa)")
    return f"pausa −{rec['pre']} min / +{rec['post']} min"


def _conclusions(res: dict, rec: dict) -> list[str]:
    moves = [ty for ty, r in rec.items() if r["status"] == "efecto"]
    flat = [ty for ty, r in rec.items() if r["status"] == "sin_efecto"]
    few = [ty for ty, r in rec.items() if r["status"] == "insuficiente"]
    drift = [f"{a} {ty} ({_f(100 * r['windows']['post_240']['ret']['mean'])} %, p Holm "
             f"{_p(r['windows']['post_240']['ret_boot']['p_holm'])})"
             for a, by in res.items() for ty, r in by.items()
             if r["windows"]["post_240"]["ret_boot"].get("significant")]
    out = ["## Conclusiones", "",
           f"- **Mueven el mercado** (rango por encima de lo normal, significativo tras Holm): "
           f"{', '.join(moves) or 'ninguno'}. Duración = columnas Pre/Post de la tabla anterior; "
           "el detalle vela a vela está en «Perfil por vela».",
           f"- **No mueven el mercado** de forma detectable: {', '.join(flat) or 'ninguno'} "
           "→ sin ventana de pausa.",
           f"- **Muestra insuficiente**: {', '.join(few) or 'ninguno'} → se mantiene la ventana "
           "por impacto del agente, marcada como «sin evidencia».",
           "- **Dirección**: el evento no anticipa el signo del movimiento. "
           + (f"Significativo tras Holm: {'; '.join(drift)} — marginal, muestra pequeña, "
              "no es una estrategia (operar eventos queda fuera de alcance)." if drift
              else "Ningún retorno medio 0…+4 h es significativo tras Holm."),
           "", "### Limitaciones", "",
           "- BLS/BEA solo publican su calendario desde 2025 → n≈20 por tipo: se detectan "
           "efectos grandes (×1.4 o más en la vela), no efectos pequeños; ausencia de "
           "significancia ≠ ausencia de efecto.",
           "- PIB y PCE se publican a menudo a la misma hora: su efecto no se puede separar.",
           "- Velas de 15 min: la resolución mínima de la ventana es 15 min.",
           "- Régimen 2023–2026; recalcular periódicamente (`--fetch`) y revisar `params.py`."]
    return out


def render(out: dict, events: list, assets: dict[str, tuple[int, int]], tf: str) -> str:
    p: StudyParams = out["params"]
    res, rec = out["results"], out["recommended"]
    lines = [
        "# Impacto histórico del calendario en BTC/ETH (T37)", "",
        f"Generado por `python -m eim.analytics.event_report` el "
        f"{datetime.now(UTC):%Y-%m-%d %H:%M} UTC. Velas {tf} de Binance USDⓈ-M (almacén local).",
        "", "## Método", "",
        f"- Ventana por evento: [−{p.pre_bars * p.bar_min} min, +{p.post_bars * p.bar_min} min] "
        f"alrededor de la hora oficial de publicación.",
        f"- **Normal** = misma hora UTC en hasta {p.n_controls} días hábiles previos "
        f"(≤ {p.max_lookback_days} d) sin eventos medio/alto a ±{p.guard_min // 60} h. Se compara "
        "con la mediana de esos controles → descuenta la estacionalidad intradía.",
        "- Medida: log(rango del evento / rango normal). Se da la distribución completa "
        "(p10…p90) y la fracción de eventos por encima de lo normal, no solo la media.",
        f"- Significancia: bootstrap ({p.n_boot} remuestreos, H0 media = 0), Holm sobre todas "
        "las pruebas de ventana (tipo × activo × ventana); por vela, Holm dentro de cada "
        f"tipo × activo. Efecto relevante: cociente ≥ {p.min_ratio}. Mínimo para fijar ventana: "
        f"n ≥ {p.min_n}.",
        "- Ventana recomendada = velas contiguas antes/después de t0 con rango significativamente "
        "elevado; se toma el máximo entre activos (el veto aplica a ambos).",
        "", "## Datos", "",
    ]
    for a, (lo, hi) in assets.items():
        lines.append(f"- {a}: velas {_day(lo)} → {_day(hi)}")
    span: dict[str, list[int]] = {}
    for t, n, _i, _s in events:
        if n in EVENT_TYPES:
            span.setdefault(EVENT_TYPES[n], []).append(t)
    mid = [t for t, _n, imp, _s in events if imp in ("medio", "alto")]
    for ty, ts in span.items():
        shared = sum(mid.count(t) > 1 for t in ts)
        lines.append(f"- {ty}: {len(ts)} eventos {_day(min(ts))} → {_day(max(ts))}; "
                     f"{shared} coinciden a la misma hora con otra publicación medio/alto")
    lines += ["- Fuentes: Fed (FOMC, histórico desde 2021), BLS y BEA (sus calendarios públicos "
              "solo traen desde 2025), vencimientos Binance por regla. Lista exacta en "
              "`reports/calendar/events.csv`.", "",
              "## Ventanas recomendadas", "",
              "| Tipo | n (BTC/ETH) | Pre | Post | Veredicto |", "|---|---|---|---|---|"]
    for ty, r in rec.items():
        ns = "/".join(str(r["per_asset"][a]["n"]) for a in res)
        lines.append(f"| {ty} | {ns} | {_f(r['pre'], 'd')} | {_f(r['post'], 'd')} | "
                     f"{_verdict(r)} |")
    lines += ["", *_conclusions(res, rec), "", "## Rango realizado frente a lo normal", "",
              "Cociente = exp(log-cociente). `>1` = más movimiento que un día normal a la misma "
              "hora.", "",
              "| Activo | Tipo | Ventana | n | mediana | p10 | p90 | % >normal | media IC95 % "
              "| p | p Holm |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for a, by in res.items():
        for ty, r in by.items():
            for w in WINDOWS:
                d, b = r["windows"][w]["range"], r["windows"][w]["boot"]
                if not d.get("n"):
                    continue
                ci = f"{_f(math.exp(b['ci'][0]))}–{_f(math.exp(b['ci'][1]))}"
                lines.append(
                    f"| {a} | {ty} | {WIN_LABEL[w]} | {d['n']} | {_f(math.exp(d['p50']))} | "
                    f"{_f(math.exp(d['p10']))} | {_f(math.exp(d['p90']))} | "
                    f"{_f(100 * d['frac_pos'], '.0f')} | {ci} | {_p(b['p'])} | "
                    f"{_p(b['p_holm'])}{' ✱' if b['significant'] else ''} |")
    lines += ["", "## Dirección (retorno 0…+4 h)", "",
              "| Activo | Tipo | n | media % | p10 % | p90 % | % al alza | p | p Holm |",
              "|---|---|---|---|---|---|---|---|---|"]
    for a, by in res.items():
        for ty, r in by.items():
            d, b = r["windows"]["post_240"]["ret"], r["windows"]["post_240"]["ret_boot"]
            if d.get("n"):
                lines.append(f"| {a} | {ty} | {d['n']} | {_f(100 * d['mean'])} | "
                             f"{_f(100 * d['p10'])} | {_f(100 * d['p90'])} | "
                             f"{_f(100 * d['frac_pos'], '.0f')} | {_p(b['p'])} | "
                             f"{_p(b['p_holm'])}{' ✱' if b['significant'] else ''} |")
    lines += ["", "## Perfil por vela (cociente de rango, ✱ = significativo tras Holm)", ""]
    offs = [b["offset_min"] for b in next(iter(next(iter(res.values())).values()))["bars"]]
    lines += ["| Activo | Tipo | " + " | ".join(f"{o:+d}" for o in offs) + " |",
              "|---|---|" + "---|" * len(offs)]
    for a, by in res.items():
        for ty, r in by.items():
            if r["n"]:
                cells = [_f(math.exp(b["mean"])) + ("✱" if b["significant"] else "")
                         for b in r["bars"]]
                lines.append(f"| {a} | {ty} | " + " | ".join(cells) + " |")
    lines += ["", "## Sorpresa", "",
              "No medible: las fuentes oficiales gratuitas no publican consenso (T33) y sin "
              "`EIM_FRED_API_KEY` tampoco hay valores reales. `event_study.by_surprise` está listo "
              "(terciles de |sorpresa|) para cuando exista una fuente de consenso.", ""]
    return "\n".join(lines)


def _json_safe(out: dict) -> dict:
    res = {a: {ty: {k: v for k, v in r.items() if k != "rows"} for ty, r in by.items()}
           for a, by in out["results"].items()}
    return {"recommended": out["recommended"], "results": res,
            "params": out["params"].__dict__}


def main(argv: list[str] | None = None) -> None:
    from eim.data.store import Store

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    ap.add_argument("--timeframe", default="15m")
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="reports")
    ap.add_argument("--fetch", action="store_true", help="descargar eventos de fuentes oficiales")
    a = ap.parse_args(argv)
    store, out_dir = Store(a.data), Path(a.out)
    bars, spans = {}, {}
    for s in a.symbols:
        cs = store.read_candles(s, a.timeframe)
        if not cs:
            raise SystemExit(f"sin velas {s} {a.timeframe} en {a.data}")
        bars[s], spans[s] = Bars.from_candles(cs), (cs[0].t, cs[-1].t)
    ev_path = out_dir / "calendar" / "events.csv"
    if a.fetch:
        lo, hi = min(v[0] for v in spans.values()), max(v[1] for v in spans.values())
        save_events(ev_path, fetch_events(lo, hi))
    events = load_events(ev_path)
    out = run_study(bars, [(t, n, i) for t, n, i, _s in events])
    md = render(out, events, spans, a.timeframe)
    (out_dir / "calendar_impact.md").write_text(md, encoding="utf-8")
    (out_dir / "calendar" / "results.json").write_text(
        json.dumps(_json_safe(out), ensure_ascii=False, indent=1, default=float),
        encoding="utf-8")
    for ty, r in out["recommended"].items():
        print(f"{ty:12s} {_verdict(r)}")


if __name__ == "__main__":
    main()
