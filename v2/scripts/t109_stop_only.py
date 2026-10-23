"""T109 — Corrida de aceptación: en los tres perfiles solo cierra el stop (inicial o dinámico).

    python scripts/t109_stop_only.py --data <carpeta con candles/, funding/ y paper.duckdb>

Reconstruye la vista del bróker (el mismo cálculo que sirve la API) sobre una COPIA del almacén y
cuenta, por símbolo y perfil, cada motivo de cierre, las violaciones, los cierres rechazados, las
señales contrarias, la duración y cuántas veces el BE+ fue el stop que cerró. Como referencia (no
decide nada: eso es T111) corre los mismos perfiles con la salida anterior (TP/BE+/tiempo).
`--ppp-out` guarda las operaciones del control `ppp_btcusdt` para compararlas con otra versión del
código. Informe en `reports/t109_stop_only.md` (+ `.json`). Todo es SIMULADO.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from eim.data.paper_store import PaperStore
from eim.data.store import Store
from eim.paper.book import run_profile
from eim.paper.desk import MMR, PaperDesk
from eim.paper.feedback import Learner
from eim.paper.ladder_book import LadderSim
from eim.paper.params import PPP_ID
from eim.paper.summary import profile_summary

THREE = ("conservador", "moderado", "agresivo")
DAY_MS = 86_400_000


def iso(t: int | None) -> str:
    return "—" if t is None else datetime.fromtimestamp(t / 1000, UTC).strftime("%Y-%m-%d %H:%M")


def _row(st, now: int, mmr: float) -> dict:
    s = profile_summary(st, Learner([]), [], now, mmr)
    tr = st.trades
    hours = [(t["exit_t"] - t["fill_t"]) / 3_600_000 for t in tr]
    lad = s.get("ladder") or {}
    return {"n": len(tr), "by_reason": dict(Counter(t["reason"] for t in tr)),
            "exits": lad.get("exits"), "violations": len(st.violations),
            "violation_reasons": [v["reasons"] for v in st.violations][:10],
            "rejected": sum(1 for v in st.violations if not v.get("executed", True)),
            "contrary": getattr(st, "contrary", 0), "open": len(s["positions"]),
            "be_closes": sum(1 for t in tr if (t.get("ladder") or {}).get("stop_source") == "be"),
            "pnl": round(sum(t["pnl"] for t in tr), 2),
            "win": round(sum(t["pnl"] > 0 for t in tr) / len(tr), 3) if tr else None,
            "avg_h": round(sum(hours) / len(hours), 1) if hours else None,
            "max_h": round(max(hours), 1) if hours else None,
            "max_dd_pct": round(s["max_dd_pct"] * 100, 2)}


def run_symbol(desk: PaperDesk, symbol: str) -> tuple[dict, list[dict]]:
    v = desk.view(symbol)
    if not v.outcomes or v.path is None:
        return {"symbol": symbol, "error": "sin contextos guardados"}, []
    ts = sorted(o.idea.t for o in v.outcomes)
    now, mmr = v.path.end, MMR.get(symbol, 0.005)
    sim = LadderSim(v.path, desk.ep, desk._fine(symbol, ts[0]))
    learner = Learner(v.outcomes)
    out = {"symbol": symbol, "from": ts[0], "to": ts[-1], "days": (ts[-1] - ts[0]) / DAY_MS,
           "ideas": len(v.outcomes), "fine": sim.fine is not None, "profiles": {}, "tp_mode": {}}
    for p in desk.profiles:
        out["profiles"][p.id] = _row(v.books[p.id], now, mmr)
        if p.id in THREE:                     # referencia: la salida anterior, mismo camino
            old = run_profile(p.model_copy(update={"exit_mode": "tp"}), v.outcomes, learner, mmr,
                              sim)
            out["tp_mode"][p.id] = _row(old, now, mmr)
    ppp = [{k: t.get(k) for k in ("id", "reason", "fill_t", "fill", "exit_t", "exit", "qty",
                                   "pnl")} | {"level": t["ladder"]["level"]}
           for t in v.books[PPP_ID].trades] if PPP_ID in v.books else []
    return out, ppp


def _md(res: list[dict], data: str) -> str:
    md = ["# T109 — Solo cierra el stop: corrida de aceptación", "",
          f"Datos: copia `{data}` · SIMULADO, sin dinero real. Vista reconstruida con el mismo "
          "cálculo que la API (`PaperDesk.view`).", ""]
    for r in res:
        if "error" in r:
            md += [f"## {r['symbol']}: {r['error']}", ""]
            continue
        md += [f"## {r['symbol']}", "",
               f"Ideas {iso(r['from'])} → {iso(r['to'])} UTC ({r['days']:.1f} días, "
               f"{r['ideas']} ideas simuladas) · velas de 1 min: "
               f"{'sí (solo donde existen)' if r['fine'] else 'no'}.", "",
               "| Perfil | Ops | SL ini | SL din | Liquid. | Salvag. | Otros | Rechaz. | "
               "Violac. | BE+ cerró | Contrarias | Abiertas | Neto USDT | Acierto | Dur. media h"
               " | Dur. máx h |",
               "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
        for pid, x in r["profiles"].items():
            e = x["exits"] or {}
            md.append(f"| {pid} | {x['n']} | {e.get('stop_inicial', 0)} | "
                      f"{e.get('stop_dinamico', 0)} | {e.get('liquidacion', 0)} | "
                      f"{e.get('salvaguarda', 0)} | {e.get('otros_motivos', 0)} | "
                      f"{x['rejected']} | {x['violations']} | {x['be_closes']} | "
                      f"{x['contrary']} | {x['open']} | {x['pnl']:,.2f} | "
                      f"{'—' if x['win'] is None else format(x['win'], '.0%')}"
                      f" | {x['avg_h'] or '—'} | {x['max_h'] or '—'} |")
        md += ["", "Referencia (no decide nada; la comparación es T111): los mismos perfiles "
               "con la salida anterior (SL/TP/BE+/tiempo) sobre el mismo camino.", "",
               "| Perfil | Ops | Motivos | Neto USDT | Acierto |", "|---|--:|---|--:|--:|"]
        for pid, x in r["tp_mode"].items():
            why = ", ".join(f"{k} {n}" for k, n in sorted(x["by_reason"].items()))
            md.append(f"| {pid} (TP) | {x['n']} | {why or '—'} | {x['pnl']:,.2f} | "
                      f"{'—' if x['win'] is None else format(x['win'], '.0%')} |")
        bad = {pid: x["violation_reasons"] for pid, x in r["profiles"].items() if x["violations"]}
        md += ["", f"Violaciones: {bad or 'ninguna'}.", ""]
    return "\n".join(md)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT")
    ap.add_argument("--out", default="reports/t109_stop_only")
    ap.add_argument("--ppp-out", default="")
    a = ap.parse_args()
    desk = PaperDesk(Store(a.data), PaperStore(Path(a.data) / "paper.duckdb"))
    res, ppp = [], {}
    for sym in a.symbols.split(","):
        r, trades = run_symbol(desk, sym)
        res.append(r)
        ppp[sym] = trades
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".md").write_text(_md(res, a.data), encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    if a.ppp_out:
        Path(a.ppp_out).write_text(json.dumps(ppp, ensure_ascii=False, indent=1), encoding="utf-8")
    forbidden = sum((x["exits"] or {}).get("otros_motivos", 0) + x["violations"]
                    for r in res if "profiles" in r for x in r["profiles"].values())
    print(f"informe en {out.with_suffix('.md')} · cierres prohibidos + violaciones: {forbidden}")
    return 0 if forbidden == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
