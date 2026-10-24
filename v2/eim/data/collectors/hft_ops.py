"""Operación de la captura HFT (T78): QC de horas cerradas, compactación, retención y resumen.

Lo llama el vigilante (`hft_supervise`) cada 10 min; también a mano:

    python -m eim.data.collectors.hft_ops --root data [--symbol BTCUSDT] [--keep-days 45]

- **QC**: cada hora cerrada hace `QC_MARGIN_S` (el recolector vuelca cada 30 s) recibe su JSON.
- **Compactación**: las horas con QC y más de `COMPACT_MARGIN_H` h se unen en un Parquet ZSTD
  ordenado por (`run`, `seq`), verificado (filas y suma de `seq`) antes de borrar las partes.
- **Retención**: los crudos más viejos que `keep_days` se borran (los JSON de QC se conservan).
  T80/T84 piden 14–30 días contiguos: 45 días deja margen sin llenar el disco.
- **Resumen** (`micro_hft/qc/symbol=S/summary.json`): horas completas, coincidencia top-10, huecos
  no detectados, racha contigua más larga, MB/día y proyección a 30 días. Va al informe semanal y a
  la copia diaria; los crudos no.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from eim.data.collectors import health, qc
from eim.data.collectors.compact import compact_dir
from eim.data.collectors.hft_read import hour_label, hours_with_data
from eim.data.collectors.hft_schema import AREA, KINDS
from eim.data.collectors.hft_writer import hour_dir

KEEP_DAYS = 45
QC_MARGIN_S = 300
COMPACT_MARGIN_H = 2
SUMMARY_HOURS = 72
MAX_QC_PER_PASS = 24


def summary_path(root: str | Path, symbol: str) -> Path:
    return Path(root) / AREA / "qc" / f"symbol={symbol}" / "summary.json"


def pending_qc(root: str | Path, symbol: str, now_s: float) -> list[int]:
    """Horas cerradas (con margen) que aún no tienen JSON de QC."""
    last_closed = last_auditable(now_s)
    return [h for h in hours_with_data(root, symbol)
            if h <= last_closed and not qc.qc_path(root, symbol, h).exists()]


def compact_hours(root: str | Path, symbol: str, now_s: float,
                  max_dirs: int | None = 48) -> list[tuple[str, int, int]]:
    cutoff = int(now_s // 3600) - COMPACT_MARGIN_H
    out: list[tuple[str, int, int]] = []
    for h in hours_with_data(root, symbol):
        if h >= cutoff or not qc.qc_path(root, symbol, h).exists():
            continue
        for kind in KINDS:
            if max_dirs is not None and len(out) >= max_dirs:
                return out
            d = hour_dir(root, kind, symbol, h)
            res = compact_dir(d, key="seq", order="run, seq", codec="ZSTD") if d.exists() else None
            if res:
                out.append((str(d), *res))
    return out


def prune(root: str | Path, keep_days: int, now_s: float) -> int:
    return health.prune_old(root, keep_days, now_s, area=AREA, kinds=KINDS)


def _streak(hours: list[int]) -> int:
    best = cur = 0
    prev = None
    for h in sorted(hours):
        cur = cur + 1 if prev is not None and h == prev + 1 else 1
        best, prev = max(best, cur), h
    return best


def aggregate(reps: list[dict], missing: list[int] | None = None) -> dict:
    """Agrega informes horarios de QC (una semana, las últimas 72 h...). `missing` = horas del
    tramo sin ningún dato (proceso caído): cuentan como incompletas."""
    missing = missing or []
    comp = sum(r["checks"]["comparable"] for r in reps)
    ok = sum(r["checks"]["matched"] for r in reps)
    causes: dict[str, int] = {}
    for r in reps:
        for c, n in r["gaps_marked"]["by_cause"].items():
            causes[c] = causes.get(c, 0) + n
    complete = [r["hour_index"] for r in reps if r["complete"]]
    n = len(reps) + len(missing)
    return {
        "hours": n, "hours_complete": len(complete), "hours_without_data": len(missing),
        "pct_complete": round(len(complete) / n, 4) if n else None,
        "longest_complete_streak_h": _streak(complete),
        "checks": {"comparable": comp, "matched": ok,
                   "match_rate": round(ok / comp, 4) if comp else None},
        "holes_found": sum(r["holes"]["found"] for r in reps),
        "undetected": sum(r["holes"]["undetected"] for r in reps),
        "gaps_by_cause": causes, "restarts": sum(r["restarts"] for r in reps),
        "overflow_dropped": sum(r["overflow_dropped"] for r in reps),
        "clock_jumps": sum(r["clock"]["jumps"] for r in reps),
        "first_hour": reps[0]["hour"] if reps else None,
        "last_hour": reps[-1]["hour"] if reps else None,
        "incomplete": sorted([r["hour"] for r in reps if not r["complete"]]
                             + [hour_label(h) for h in missing])[-24:],
    }


def last_auditable(now_s: float) -> int:
    """Última hora que ya debería tener su JSON de QC."""
    return int((now_s - QC_MARGIN_S) // 3600) - 1


def reports(root: str | Path, symbol: str, h0: int, h1: int,
            until: int | None = None) -> tuple[list[dict], list[int]]:
    """JSON de QC de las horas [h0, h1) y horas sin datos desde la primera auditada hasta
    `until` (incluida; si la captura murió, sus horas siguientes cuentan como incompletas)."""
    reps = [r for h in hours_with_data(root, symbol) if h0 <= h < h1
            if (r := qc.load(root, symbol, h)) is not None]
    if not reps:
        return [], []
    seen = {r["hour_index"] for r in reps}
    last = max(reps[-1]["hour_index"], min(h1 - 1, until if until is not None else -1))
    return reps, [h for h in range(reps[0]["hour_index"], last + 1) if h not in seen]


def summarize(root: str | Path, symbol: str, now_s: float, hours: int = SUMMARY_HOURS,
              keep_days: int = KEEP_DAYS) -> dict:
    h1 = int(now_s // 3600)
    out = {"symbol": symbol, "generated_at": int(now_s * 1000), "window_h": hours,
           **aggregate(*reports(root, symbol, h1 - hours, h1, last_auditable(now_s)))}
    disk = health.disk_report(root, area=AREA, kinds=KINDS)
    out["disk"] = {**disk, "keep_days": keep_days,
                   "projection_30d_gb": round(disk["mb_per_day_total"] * 30 / 1000, 2),
                   "projection_keep_gb": round(disk["mb_per_day_total"] * keep_days / 1000, 2)}
    return out


def write_summary(root: str | Path, symbol: str, summary: dict) -> Path:
    p = summary_path(root, symbol)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)
    return p


def week_summary(root: str | Path, symbol: str, t0_ms: int, t1_ms: int) -> dict | None:
    """Resumen de QC para el informe semanal (None si no hay captura HFT en el periodo)."""
    reps, missing = reports(root, symbol, t0_ms // 3_600_000, t1_ms // 3_600_000,
                            last_auditable(time.time()))
    if not reps:
        return None
    disk = health.disk_report(root, area=AREA, kinds=KINDS)
    return {"symbol": symbol, **aggregate(reps, missing), "mb_per_day": disk["mb_per_day_total"],
            "projection_30d_gb": round(disk["mb_per_day_total"] * 30 / 1000, 2)}


def maintain(root: str | Path, symbol: str, now_s: float, keep_days: int = KEEP_DAYS) -> dict:
    """Una pasada completa: QC pendiente → compactación → retención → resumen."""
    done = [qc.run_hour(root, symbol, h) for h in pending_qc(root, symbol, now_s)[:MAX_QC_PER_PASS]]
    compacted = compact_hours(root, symbol, now_s)
    pruned = prune(root, keep_days, now_s)
    summary = summarize(root, symbol, now_s, keep_days=keep_days)
    write_summary(root, symbol, summary)
    return {"qc_horas": [r["hour"] for r in done],
            "qc_incompletas": [r["hour"] for r in done if not r["complete"]],
            "no_detectados": sum(r["holes"]["undetected"] for r in done),
            "compactadas": len(compacted), "carpetas_podadas": pruned, "summary": summary}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default="data")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--keep-days", type=int, default=KEEP_DAYS)
    a = ap.parse_args(argv)
    res = maintain(a.root, a.symbol, time.time(), a.keep_days)
    print(json.dumps({k: v for k, v in res.items() if k != "summary"}, ensure_ascii=False))
    print(json.dumps(res["summary"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

