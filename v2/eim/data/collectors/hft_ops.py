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
- **Aceptación de T78 por ventana** (T147, `t78_window` del resumen o `--window`): el tramo
  contiguo más largo con ≥ 99 % de horas completas, 0 huecos sin detectar y ≥ 99 % de coincidencia
  top-10, que es lo que pide §Aceptación de `PLAN/T78.md`. La racha de 72 horas seguidas (T126)
  sigue en `t78_streak` y en `--streak`, ya solo como lectura informativa: una hora al 98,x %
  la reiniciaba. La regla vive en `hft_window.py`; aquí solo se leen los JSON de QC, que se
  conservan aunque se poden los crudos.
- **Mantenimiento** (T147, `--maintenance DESDE HASTA --nota "…"`): declara las horas de un
  despliegue; no cuentan ni rompen la ventana, así que desplegar ya no cuesta la corrida.
- **Recalificar** (T138, T147; `--requalify DESDE [--apply]`): aplica la regla vigente a los JSON
  de versiones anteriores. Corre aparte, sin reiniciar la captura ni el vigilante.
- **Horas ciegas del registro de consumo** (T148): `blind_hours` lee los huecos de `data/usage/`
  (`eim.operation.usage_gaps`) y se los pasa a la atribución, que cuenta como nuestras las horas
  que el registro de consumo tampoco vio. Si falta esa carpeta, no se inventa nada: conjunto vacío.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from eim.data.collectors import health, hft_window, qc
from eim.data.collectors.compact import compact_dir
from eim.data.collectors.hft_read import hour_label, hours_with_data, parse_hour
from eim.data.collectors.hft_schema import AREA, KINDS
from eim.data.collectors.hft_writer import hour_dir
from eim.operation import usage_gaps
from eim.operation.usage_summary import days_between, load_day

KEEP_DAYS = 45
QC_MARGIN_S = 300
COMPACT_MARGIN_H = 2
SUMMARY_HOURS = 72
MAX_QC_PER_PASS = 24
T78_NEED_H = hft_window.NEED_H
T78_MATCH_MIN = hft_window.MATCH_MIN
LIST_KINDS = ("depth", "snap", "book")   # filas con listas de niveles: grupos de filas pequeños
LIST_ROW_GROUP = 2048


def summary_path(root: str | Path, symbol: str) -> Path:
    return Path(root) / AREA / "qc" / f"symbol={symbol}" / "summary.json"


def pending_qc(root: str | Path, symbol: str, now_s: float) -> list[int]:
    """Horas cerradas (con margen) que aún no tienen JSON de QC."""
    last_closed = last_auditable(now_s)
    return [h for h in hours_with_data(root, symbol)
            if h <= last_closed and not qc.qc_path(root, symbol, h).exists()]


def compact_hours(root: str | Path, symbol: str, now_s: float, max_dirs: int | None = 48
                  ) -> tuple[list[tuple[str, int, int]], list[tuple[str, str]]]:
    """(compactadas, fallidas). Concatena las partes ya ordenadas (sin reordenar en memoria: el
    equipo anda corto); una carpeta que falla se registra y se reintenta en la pasada siguiente."""
    cutoff = int(now_s // 3600) - COMPACT_MARGIN_H
    out: list[tuple[str, int, int]] = []
    failed: list[tuple[str, str]] = []
    for h in hours_with_data(root, symbol):
        if h >= cutoff or not qc.qc_path(root, symbol, h).exists():
            continue
        for kind in KINDS:
            if max_dirs is not None and len(out) >= max_dirs:
                return out, failed
            d = hour_dir(root, kind, symbol, h)
            if not d.exists():
                continue
            try:
                res = compact_dir(d, key="seq", order="run, seq", codec="ZSTD", presorted=True,
                                  row_group_size=LIST_ROW_GROUP if kind in LIST_KINDS else None)
            except Exception as e:  # noqa: BLE001 - una hora problemática no frena las demás
                failed.append((str(d), f"{type(e).__name__}: {e}"[:300]))
                continue
            if res:
                out.append((str(d), *res))
    return out, failed


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
    since = h1 - keep_days * 24
    out["t78_window"] = window(root, symbol, now_s, since_h=since)
    out["t78_streak"] = streak(root, symbol, now_s, since_h=since)
    return out


def qc_reports(root: str | Path, symbol: str, since_h: int | None = None) -> list[dict]:
    """Todos los JSON de QC del símbolo desde `since_h`, por hora (no dependen de los crudos)."""
    hours = []
    for f in (Path(root) / AREA / "qc" / f"symbol={symbol}").glob("date=*/hour=*.json"):
        h = parse_hour(f"{f.parent.name.removeprefix('date=')}T{f.stem.removeprefix('hour=')}")
        if since_h is None or h >= since_h:
            hours.append(h)
    return [r for h in sorted(hours) if (r := qc.load(root, symbol, h)) is not None]


def blind_hours(root: str | Path, now_s: float, days: int = 45) -> set[int]:
    """Horas que el registro de consumo no vio, por sus propios huecos (T148 E2+E3).

    Nunca lanza: sin `data/usage/` (otro equipo, registro no instalado) devuelve un conjunto
    vacío, y entonces la atribución se queda con las demás señales."""
    try:
        now_ms = int(now_s * 1000)
        day_list = days_between(now_ms - (days - 1) * 86_400_000, now_ms + 1)
        samples = sorted((r for d in day_list for r in load_day(Path(root), d)),
                         key=lambda r: r["t"])
        return usage_gaps.blind_hours(usage_gaps.gaps(samples, now_ms))
    except Exception:  # noqa: BLE001 - una atribución sin esta señal es peor, no imposible
        return set()


def streak(root: str | Path, symbol: str, now_s: float, since_h: int | None = None,
           need_h: int = T78_NEED_H) -> dict:
    """Racha de horas completas seguidas (T126), informativa desde T147: `hft_window.streak`."""
    return hft_window.streak(qc_reports(root, symbol, since_h), last_auditable(now_s) - 1,
                             since_h, need_h)


def window(root: str | Path, symbol: str, now_s: float, since_h: int | None = None,
           need_h: int = T78_NEED_H) -> dict:
    """Veredicto de T78 por ventana (T147): `hft_window.window` sobre los JSON de QC."""
    return hft_window.window(qc_reports(root, symbol, since_h), last_auditable(now_s) - 1,
                             hft_window.load_maint(root, symbol), since_h, need_h,
                             blind_hours(root, now_s))


def requalify(root: str | Path, symbol: str, since_h: int | None = None,
              apply: bool = False) -> dict:
    """Recalifica los JSON de versiones anteriores desde `since_h` (T138, T147). Sin `apply` no
    escribe nada: solo dice qué horas cambiarían de veredicto. Se puede repetir: no vuelve a tocar
    las horas al día, así que recoge también las que audite un vigilante aún sin reiniciar."""
    done, changed = 0, []
    for h in [r["hour_index"] for r in qc_reports(root, symbol, since_h)]:
        rep = qc.requalify(root, symbol, h, write=apply)
        if rep is None:
            continue
        done += 1
        if rep["complete"] != rep["requalified"]["complete_before"]:
            m = (rep.get("streams") or {}).get("mark") or {}
            changed.append({"hour": rep["hour"], "complete": rep["complete"],
                            "coverage": m.get("coverage"),
                            "coverage_cadence": m.get("coverage_cadence"),
                            "book_usable": rep["book_usable"], "msgs": m.get("msgs")})
    return {"applied": apply, "requalified": done, "changed": changed}


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
    now_s = time.time()
    return {"symbol": symbol, **aggregate(reps, missing), "mb_per_day": disk["mb_per_day_total"],
            "projection_30d_gb": round(disk["mb_per_day_total"] * 30 / 1000, 2),
            "t78_window": hft_window.window(reps, last_auditable(now_s) - 1,
                                            hft_window.load_maint(root, symbol),
                                            blind_hours=blind_hours(root, now_s))}


def maintain(root: str | Path, symbol: str, now_s: float, keep_days: int = KEEP_DAYS) -> dict:
    """Una pasada completa: QC pendiente → compactación → retención → resumen. Un fallo en una
    hora (QC) o carpeta (compactación) queda en la salida y no impide reescribir el resumen."""
    done, qc_failed = [], []
    for h in pending_qc(root, symbol, now_s)[:MAX_QC_PER_PASS]:
        try:
            done.append(qc.run_hour(root, symbol, h))
        except Exception as e:  # noqa: BLE001 - se reintenta en la pasada siguiente
            qc_failed.append((hour_label(h), f"{type(e).__name__}: {e}"[:300]))
    compacted, comp_failed = compact_hours(root, symbol, now_s)
    pruned = prune(root, keep_days, now_s)
    summary = summarize(root, symbol, now_s, keep_days=keep_days)
    write_summary(root, symbol, summary)
    return {"qc_horas": [r["hour"] for r in done],
            "qc_incompletas": [r["hour"] for r in done if not r["complete"]],
            "no_detectados": sum(r["holes"]["undetected"] for r in done),
            "qc_fallida": qc_failed, "compactadas": len(compacted),
            "compactacion_fallida": comp_failed, "carpetas_podadas": pruned, "summary": summary}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default="data")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--keep-days", type=int, default=KEEP_DAYS)
    ap.add_argument("--window", action="store_true",
                    help="solo el veredicto de T78 por ventana (T147; no audita ni compacta)")
    ap.add_argument("--streak", action="store_true",
                    help="solo la racha de T78 (T126, informativa; no audita ni compacta)")
    ap.add_argument("--since", help="hora UTC AAAA-MM-DDTHH desde la que se cuenta")
    ap.add_argument("--maintenance", nargs=2, metavar=("DESDE", "HASTA"),
                    help="declara esas horas UTC AAAA-MM-DDTHH (ambas incluidas) como "
                         "mantenimiento conocido: no cuentan ni rompen la ventana (T147)")
    ap.add_argument("--nota", default="", help="con --maintenance, por qué se declara")
    ap.add_argument("--requalify", metavar="DESDE",
                    help="recalifica los JSON de QC antiguos desde esa hora UTC AAAA-MM-DDTHH "
                         "(T138); sin --apply solo lista lo que cambiaría")
    ap.add_argument("--apply", action="store_true", help="con --requalify, escribe los JSON")
    a = ap.parse_args(argv)
    if a.requalify:
        res = requalify(a.root, a.symbol, parse_hour(a.requalify), a.apply)
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0
    if a.maintenance:
        if not a.nota.strip():
            ap.error("--maintenance exige --nota: queda en el registro de por qué no cuentan")
        h0, h1 = (parse_hour(x) for x in a.maintenance)
        res = hft_window.declare_maint(a.root, a.symbol, h0, h1, a.nota)
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0
    if a.window or a.streak:
        since = parse_hour(a.since) if a.since else None
        f = window if a.window else streak
        print(json.dumps(f(a.root, a.symbol, time.time(), since), ensure_ascii=False, indent=1))
        return 0
    res = maintain(a.root, a.symbol, time.time(), a.keep_days)
    print(json.dumps({k: v for k, v in res.items() if k != "summary"}, ensure_ascii=False))
    print(json.dumps(res["summary"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

