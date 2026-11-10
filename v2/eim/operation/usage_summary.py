"""Resumen por día del registro de consumo (T127), cruzado con la captura HFT (T78).

Para cada día: picos de CPU, RAM libre mínima, horas saturadas, quién gastaba (EIM por papel y
el resto por programa) y, sobre todo, las horas incompletas de la captura HFT: cuáles
coincidieron con el equipo saturado y cuáles no tienen registro (equipo apagado o registro
caído). Una hora perdida sin saturación apunta a otra causa: red, reinicio o un fallo del
recolector. Función pura de los archivos; no escribe nada.

**Cobertura real, no muestras contadas (T148).** `coverage` mide el tramo que el registro estuvo
de verdad midiendo: el día menos sus huecos (`usage_gaps.py`) y menos lo que queda fuera de la
primera y la última muestra. Así un día con 5 horas en blanco, como el 2026-11-09, no se lee como
si estuviera medido; `blind_s` y `gaps` dicen cuánto y cuándo faltó.
"""

from __future__ import annotations

import gzip
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from eim.operation import usage_gaps
from eim.operation.usage import EVERY_S, usage_dir

SAT_CPU = 90.0       # % de CPU del equipo desde el que una muestra cuenta como saturada
SAT_SHARE = 0.10     # una hora es «saturada» si lo están ≥ 10 % de sus muestras (~6 min)...
LOW_RAM_MB = 1024    # ... o si la RAM libre bajó de 1 GB en algún momento
MIN_COVER = 0.5      # con menos de la mitad de las muestras esperadas, la hora va «sin registro»


def load_day(data_dir: Path, day: str) -> list[dict]:
    """Muestras del día `AAAA-MM-DD`, del archivo vivo o del ya comprimido (las líneas
    ilegibles, p. ej. la última a medio escribir tras un corte, se saltan)."""
    path = usage_dir(data_dir) / f"{day}.jsonl"
    out = []
    try:
        if path.exists():
            lines = path.read_text(encoding="utf-8").splitlines()
        else:
            with gzip.open(path.with_name(path.name + ".gz"), "rt", encoding="utf-8") as f:
                lines = f.read().splitlines()
    except (OSError, EOFError):
        return out
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def hft_hours(data_dir: Path, symbol: str, day: str) -> dict[str, bool]:
    """Hora `HH` → completa, según los JSON de QC de la captura HFT de ese día."""
    out = {}
    folder = Path(data_dir) / "micro_hft" / "qc" / f"symbol={symbol}" / f"date={day}"
    for f in folder.glob("hour=*.json"):
        try:
            out[f.stem.removeprefix("hour=")] = bool(json.loads(f.read_text("utf-8"))["complete"])
        except (OSError, ValueError, KeyError):
            continue
    return out


def _p95(xs: list[float]) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, int(0.95 * len(s)))]


def _top(sums: dict[str, float], n: int, k: int) -> dict[str, float]:
    return {name: round(v / n, 2) for name, v in sorted(sums.items(), key=lambda x: -x[1])[:k]}


def day_ms(day: str) -> tuple[int, int]:
    """Inicio y fin del día `AAAA-MM-DD` en milisegundos UTC."""
    t0 = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC)
    return int(t0.timestamp() * 1000), int((t0 + timedelta(days=1)).timestamp() * 1000)


def day_summary(recs: list[dict], day: str, hft: dict[str, bool] | None = None,
                every_s: float = EVERY_S, until_ms: int | None = None) -> dict:
    """Resumen de un día. `until_ms` acorta el día en curso: lo que aún no ha llegado no es un
    hueco del registro."""
    t0, t1 = day_ms(day)
    # Toda muestra trae `t`; si alguna solo trae `ts` (registros antiguos), se deduce de ahí.
    timed = sorted(({**r, "t": r["t"]} if isinstance(r.get("t"), (int, float)) else
                    {**r, "t": int(datetime.strptime(r["ts"], "%Y-%m-%dT%H:%M:%SZ")
                                   .replace(tzinfo=UTC).timestamp() * 1000)}
                    for r in recs), key=lambda r: r["t"])
    cov = usage_gaps.coverage(timed, t0,
                              min(t1, until_ms) if until_ms is not None else t1)
    out: dict = {"day": day, "samples": len(recs), **cov}
    per_hour: dict[str, list[dict]] = defaultdict(list)
    for r in recs:
        per_hour[r["ts"][11:13]].append(r)
    expected = 3600 / every_s
    saturated = sorted(h for h, rs in per_hour.items() if (
        sum(r["machine"]["cpu"] >= SAT_CPU for r in rs) >= SAT_SHARE * len(rs)
        or min(r["machine"].get("ram_free_mb", LOW_RAM_MB) for r in rs) < LOW_RAM_MB))
    if recs:
        cpu = [r["machine"]["cpu"] for r in recs]
        peak = max(recs, key=lambda r: r["machine"]["cpu"])
        who = {**{k: g["cpu"] for k, g in peak.get("roles", {}).items()},
               **{o["name"]: o["cpu"] for o in peak.get("others", [])}}
        roles: dict[str, float] = defaultdict(float)
        others: dict[str, float] = defaultdict(float)
        for r in recs:
            for k, g in r.get("roles", {}).items():
                roles[k] += g["cpu"]
            for o in r.get("others", []):
                others[o["name"]] += o["cpu"]
        out.update(
            cpu={"mean": round(sum(cpu) / len(cpu), 1), "p95": round(_p95(cpu), 1),
                 "max": round(max(cpu), 1)},
            peak={"ts": peak["ts"], "cpu": peak["machine"]["cpu"],
                  "top": max(who, key=who.get) if who else None},
            ram_free_min_mb=min(r["machine"].get("ram_free_mb", 0) for r in recs),
            eim_cpu_mean=round(sum(r["eim"]["cpu"] for r in recs) / len(recs), 2),
            roles_cpu_mean=_top(roles, len(recs), 8), others_cpu_mean=_top(others, len(recs), 5))
    out["saturated_hours"] = saturated
    lost = sorted(h for h, ok in (hft or {}).items() if not ok)
    out["hft"] = {
        "hours": len(hft or {}), "incomplete": lost,
        "incomplete_saturated": [h for h in lost if h in saturated],
        "incomplete_unlogged": [h for h in lost if len(per_hour.get(h, [])) < MIN_COVER * expected],
    }
    return out


def days_between(t0_ms: int, t1_ms: int) -> list[str]:
    d = datetime.fromtimestamp(t0_ms / 1000, UTC).date()
    end = datetime.fromtimestamp((t1_ms - 1) / 1000, UTC).date()
    out = []
    while d <= end:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def summarize(data_dir: Path, days: list[str], symbol: str = "BTCUSDT",
              until_ms: int | None = None) -> list[dict]:
    """Un resumen por día con registro de consumo o con horas de QC de la captura."""
    out = []
    for day in days:
        recs, hft = load_day(data_dir, day), hft_hours(data_dir, symbol, day)
        if recs or hft:
            out.append(day_summary(recs, day, hft, until_ms=until_ms))
    return out


def week_summary(data_dir: Path, t0_ms: int, t1_ms: int, symbol: str = "BTCUSDT") -> list[dict]:
    return summarize(data_dir, days_between(t0_ms, t1_ms), symbol, t1_ms)


def for_report(data_dir: Path, t0_ms: int, t1_ms: int, symbols: tuple[str, ...]) -> list[dict]:
    """Para el informe semanal: cruzado con la captura del primer símbolo; nunca lanza."""
    try:
        return week_summary(data_dir, t0_ms, t1_ms, symbols[0] if symbols else "BTCUSDT")
    except Exception as e:  # noqa: BLE001 - un registro ilegible no impide el informe
        return [{"error": f"{type(e).__name__}: {e}"}]


def recent(data_dir: Path, days: int, symbol: str, now_s: float) -> list[dict]:
    now_ms = int(now_s * 1000)
    return week_summary(data_dir, now_ms - (days - 1) * 86_400_000, now_ms + 1, symbol)
