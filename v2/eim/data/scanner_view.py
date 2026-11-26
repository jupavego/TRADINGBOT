"""Vista publicada del escáner para la API y la pestaña «Escáner» (T94). Solo lectura.

`scanner.duckdb` tiene un solo proceso escritor (el escáner) y la API no debe abrirlo: tras cada
pasada de agentes el escáner publica `data/scanner/view.json` (escritura atómica) y la API lo lee
tal cual. La vista lleva el universo puntuado con su cobertura y el estado de su mercado, las
últimas corridas, las oportunidades candidatas y el detalle por instrumento (agentes que corrieron,
los omitidos y por qué, síntesis, proyección y avisos). Siempre en modo ANÁLISIS y con el aviso
«candidata, no validada».
"""

from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

from eim.core.opportunity import STATUS_LABEL
from eim.instruments.models import Instrument

VIEW_FILE = "view.json"
VIEW_VERSION = "1"
NOTICE = ("Oportunidades CANDIDATAS, NO VALIDADAS: salen del escáner en modo Análisis, no son "
          "órdenes ni recomendaciones, y ningún motor de riesgo ni de ejecución las usa. El "
          "control de multiplicidad (¿supera el azar?) es T95.")


def view_path(data_dir: str | Path) -> Path:
    return Path(data_dir) / "scanner" / VIEW_FILE


def _brief_run(r: Mapping) -> dict:
    d = r.get("detail") or {}
    keep = ("base_run", "n_opportunities", "n_without", "failed", "checked", "alerts",
            "exclusions", "shortlist")
    return {"run_id": r["run_id"], "rhythm": r["rhythm"], "asof": r["asof"],
            "timeframe": r["timeframe"], "started_at": r["started_at"],
            "finished_at": r["finished_at"],
            "detail": {k: (d[k][:10] if k == "shortlist" else d[k]) for k in keep if k in d}}


def build_view(*, base: Mapping, scores: Sequence[Mapping], insts: Mapping[str, Instrument],
               market_state: Mapping[str, str], deep_run: Mapping, results: Sequence[Mapping],
               runs: Sequence[Mapping], now: int | None = None) -> dict:
    """Arma la vista (pura): todo lo que muestra la pestaña sale de aquí."""
    from eim.scanner.candidates import market_of

    by_res = {r["instrument_id"]: r for r in results}
    rows, markets = [], Counter()
    for s in scores:
        inst = insts.get(s["instrument_id"])
        if inst is None:
            continue
        mkt, state = market_of(inst), market_state.get(inst.id, "sin_calendario")
        markets[(mkt, inst.asset_class.value, state)] += 1
        res = by_res.get(inst.id)
        rows.append({"instrument_id": inst.id, "symbol": inst.symbol, "label": inst.label,
                     "asset_class": inst.asset_class.value, "market": mkt, "state": state,
                     "rank": s["rank"], "score": s["score"], "quality": s["quality"],
                     "last_t": s.get("last_t"), "deep": res is not None,
                     "n_bars": (res or {}).get("coverage", {}).get("n_bars"),
                     "opportunity_id": ((res or {}).get("opportunity") or {}).get(
                         "opportunity_id")})
    mk: dict[tuple[str, str], dict] = {}
    for (m, cls, state), n in sorted(markets.items()):
        e = mk.setdefault((m, cls), {"market": m, "asset_class": cls, "n": 0, "abierto": 0,
                                     "cerrado": 0, "sin_calendario": 0})
        e["n"] += n
        e[state] = e.get(state, 0) + n
    instruments = {}
    for r in results:
        inst = insts.get(r["instrument_id"])
        instruments[r["instrument_id"]] = {
            **{k: r.get(k) for k in ("instrument_id", "symbol", "timeframe", "asof", "input_hash",
                                     "coverage", "ran", "skipped", "synthesis", "forecast",
                                     "reason", "warnings", "elapsed_ms", "version")},
            "asset_class": inst.asset_class.value if inst else None,
            "market": market_of(inst) if inst else None,
            "state": market_state.get(r["instrument_id"], "sin_calendario"),
            "opportunity_id": (r.get("opportunity") or {}).get("opportunity_id")}
    opps = [r["opportunity"] for r in results if r.get("opportunity")]
    detail = base.get("detail") or {}
    return {
        "version": VIEW_VERSION, "mode": "ANALISIS", "status_label": STATUS_LABEL,
        "notice": NOTICE, "generated_at": int(time.time() * 1000) if now is None else now,
        "universe": {"run_id": base["run_id"], "asof": base["asof"],
                     "timeframe": base["timeframe"], "exclusions": detail.get("exclusions", {}),
                     "notes": detail.get("notes", {}), "lifecycle": detail.get("lifecycle", {}),
                     "n_scored": len(rows), "markets": list(mk.values()), "rows": rows},
        "deep": {"run_id": deep_run["run_id"], "asof": deep_run["asof"],
                 "n_shortlist": len(results), "n_opportunities": len(opps),
                 "reasons": dict(Counter(r["reason"].split(" (")[0] for r in results
                                         if r.get("reason")))},
        "runs": [_brief_run(r) for r in runs],
        "opportunities": opps,
        "instruments": instruments,
    }


def write_view(data_dir: str | Path, view: dict) -> Path:
    f = view_path(data_dir)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(view, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(f)
    return f


def read_view(data_dir: str | Path) -> dict | None:
    """La última vista publicada; None si el escáner aún no corrió sus agentes aquí."""
    f = view_path(data_dir)
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
