"""Cada ciclo lento, reinicio y arranque lento, cruzados con el consumo del equipo (T141).

Dice qué pasaba mientras la API estaba parada: CPU, memoria comprometida, RAM de la API, RAM y cola
de la captura y quién gastaba, con su orden si el registro ya la guardaba (`usage_foreign.py`). Es
una función pura de `data/usage` y `data/operation/logs`; no escribe nada.

    python -m eim.operation.usage incidents [--days 7] [--slow 120]

**El silencio del propio registro también es un incidente (T148).** Todo lo de arriba sale del
registro de operación, que no se escribe cuando el proceso está muerto: el apagón del 2026-11-09
daba cero incidentes porque el que tomaba nota murió con los demás. Los huecos de `data/usage/` se
declaran por su propia ausencia (`usage_gaps.py`) y entran aquí como `apagon_registro`.

Las órdenes se quedan en local: esta salida se lee en pantalla y no va a ningún informe.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from eim.operation import usage_gaps
from eim.operation.usage_summary import days_between, load_day

SLOW_S = 120.0       # con mediana de 1,3 s y p99 de 29 s, un ciclo así ya no es normal
EXIT_WINDOW_S = 120  # un reinicio por salida del proceso no tiene duración: se mira lo previo
_STOPPED = re.compile(r"latido detenido (\d+(?:\.\d+)?) s")
_EVENTS = {"ciclo", "proceso_reiniciado", "proceso_lanzado", "servicio_iniciado"}
TOP = 3


def load_ops(data_dir: Path, days: Iterable[str]) -> list[dict]:
    """Eventos del registro de operación que interesan, en orden."""
    out: list[dict] = []
    for day in days:
        try:
            lines = (Path(data_dir) / "operation" / "logs" / f"op-{day}.jsonl").read_text(
                encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("event") in _EVENTS:
                out.append(row)
    return sorted(out, key=lambda r: r.get("t", 0))


def find(ops: Iterable[dict], slow_s: float = SLOW_S) -> list[dict]:
    """Tramos en los que la API no estaba al día: {kind, t0, t1, detail}, en milisegundos."""
    out, launched = [], None
    for e in ops:
        kind, t = e["event"], e["t"]
        if kind == "ciclo" and e.get("cycle_t") and t - e["cycle_t"] >= slow_s * 1000:
            out.append({"kind": "ciclo_lento", "t0": e["cycle_t"], "t1": t})
        elif kind == "proceso_reiniciado":
            why = e.get("reason") or ""
            if m := _STOPPED.search(why):
                out.append({"kind": "reinicio_latido", "t0": int(t - float(m[1]) * 1000), "t1": t,
                            "detail": why})
            else:
                out.append({"kind": "reinicio_salida", "t0": t - EXIT_WINDOW_S * 1000, "t1": t,
                            "detail": why})
        elif kind == "proceso_lanzado":
            launched = t
        elif kind == "servicio_iniciado" and launched is not None:
            if t - launched >= slow_s * 1000:
                out.append({"kind": "arranque_lento", "t0": launched, "t1": t})
            launched = None
    return sorted(out, key=lambda x: x["t0"])


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 2) if xs else None


def _group(rec: dict, name: str) -> dict:
    return rec.get("roles", {}).get(name) or {}


def _who(window: list[dict]) -> dict:
    """Quién gastaba: por nombre de programa y, si el registro lo guardó, por árbol con su orden."""
    cpu: dict[str, float] = defaultdict(float)
    commit: dict[str, float] = defaultdict(float)
    trees: dict[int, dict] = {}
    for r in window:
        for o in r.get("others", ()):
            cpu[o["name"]] += o["cpu"]
            commit[o["name"]] = max(commit[o["name"]], o["commit_mb"])
        for t in r.get("foreign", ()):
            g = trees.setdefault(t["pid"], {"cmd": t.get("cmd"), "cwd": t.get("cwd"),
                                            "name": t["name"], "n": 0, "cpu_max": 0.0,
                                            "ram_max_mb": 0.0, "commit_max_mb": 0.0, "prio": 0})
            g["n"] = max(g["n"], t["n"])
            g["cpu_max"] = max(g["cpu_max"], t["cpu"])
            g["ram_max_mb"] = max(g["ram_max_mb"], t["ram_mb"])
            g["commit_max_mb"] = max(g["commit_max_mb"], t["commit_mb"])
            g["prio"] = max(g["prio"], t["prio"])
    n = len(window)
    return {
        "top_cpu": [{"name": k, "cpu_mean": round(v / n, 2)} for k, v in
                    sorted(cpu.items(), key=lambda kv: -kv[1])[:TOP]],
        "top_commit": [{"name": k, "commit_max_mb": v} for k, v in
                       sorted(commit.items(), key=lambda kv: -kv[1])[:TOP]],
        "foreign": sorted(trees.values(), key=lambda g: -g["cpu_max"])[:TOP],
    }


def cross(samples: list[dict], t0: int, t1: int) -> dict:
    """Estado del equipo en un tramo. Sin muestras no se inventa nada: `samples: 0`."""
    w = [r for r in samples if t0 <= r["t"] <= t1]
    if not w:                                  # un tramo más corto que el intervalo de muestreo
        w = [r for r in samples if t0 - 60_000 <= r["t"] <= t1 + 60_000]
    if not w:
        return {"samples": 0}
    m = [r["machine"] for r in w]
    api = [g for r in w if (g := _group(r, "api"))]
    cap = [g for r in w if (g := _group(r, "hft_collector"))]
    faults = [g["faults"] for g in api if "faults" in g]
    queue = [(r.get("hft") or {}).get("queue") or 0 for r in w]
    return {
        "samples": len(w),
        "gap_max_s": max(r.get("dt_s", 0) for r in w),
        "machine": {"cpu_mean": _mean([x["cpu"] for x in m]), "cpu_max": max(x["cpu"] for x in m),
                    "commit_max_mb": max(x.get("commit_mb", 0) for x in m),
                    "commit_limit_mb": max(x.get("commit_limit_mb", 0) for x in m),
                    "ram_free_min_mb": min(x.get("ram_free_mb", 0) for x in m)},
        "api": {"ram_first_mb": api[0]["ram_mb"], "ram_min_mb": min(g["ram_mb"] for g in api),
                "commit_mb": max(g["commit_mb"] for g in api),
                "cpu_mean": _mean([g["cpu"] for g in api]), "prio": max(g["prio"] for g in api),
                "hard_faults": sum(max(0, b - a) for a, b in zip(faults, faults[1:], strict=False))
                               if len(faults) > 1 else None}
               if api else None,
        "capture": {"ram_min_mb": min(g["ram_mb"] for g in cap), "queue_max": max(queue)}
                   if cap else None,
        **_who(w),
    }


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def report(data_dir: Path, days: list[str], slow_s: float = SLOW_S,
           until_ms: int | None = None) -> list[dict]:
    """Los incidentes de los días pedidos, en orden. Con `until_ms`, un registro que calló y no
    ha vuelto da además el apagón abierto hasta ese instante."""
    samples = [r for d in days for r in load_day(data_dir, d)]
    samples.sort(key=lambda r: r["t"])
    out = [{"kind": x["kind"], "from": _iso(x["t0"]), "to": _iso(x["t1"]),
            "dur_s": round((x["t1"] - x["t0"]) / 1000), **({"detail": x["detail"]} if "detail" in x
                                                           else {}),
            **cross(samples, x["t0"], x["t1"])}
           for x in find(load_ops(data_dir, days), slow_s)]
    out += usage_gaps.as_incidents(usage_gaps.gaps(samples, until_ms))
    return sorted(out, key=lambda r: r["from"])


def recent(data_dir: Path, days: int, now_s: float, slow_s: float = SLOW_S) -> list[dict]:
    now_ms = int(now_s * 1000)
    return report(data_dir, days_between(now_ms - (days - 1) * 86_400_000, now_ms + 1), slow_s,
                  now_ms)
