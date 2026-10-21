"""Salud del recolector de microestructura (T104): latido, disco y estado legible.

El recolector escribe `data/micro/heartbeat.json` cada ~30 s; el supervisor (`supervise.py`) y la
API leen de aquí. Estados: `apagado` (sin latido o viejo) · `sin_flujo` (proceso vivo pero sin
mensajes recientes: red caída o WebSocket que conecta y no entrega) · `capturando`.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

HEARTBEAT = "heartbeat.json"
HEARTBEAT_EVERY_S = 30.0
STALE_S = 120.0          # latido más viejo que esto → proceso apagado o colgado
SILENT_S = 300.0         # sin mensajes de mercado durante tanto → «sin flujo»
GRACE_S = 120.0          # tras arrancar, aún no hay mensajes: no se avisa
FREE_GB_MIN = 5.0        # alerta si el disco tiene menos libre
DEPTH_KEEP_DAYS = 30     # los diffs crudos de profundidad son lo más pesado; el resto se conserva
KINDS = ("trades", "top", "depth", "gaps", "liqs")


DEFAULT_SYMBOL = "BTCUSDT"   # sus archivos conservan el nombre sin sufijo


def micro_dir(root: str | Path) -> Path:
    return Path(root) / "micro"


def sfx(symbol: str = DEFAULT_SYMBOL) -> str:
    """Sufijo de los archivos de control: vacío para BTCUSDT, `_SIMBOLO` para el resto."""
    sym = symbol.upper()
    return "" if sym == DEFAULT_SYMBOL else f"_{sym}"


def hb_name(symbol: str = DEFAULT_SYMBOL) -> str:
    return f"heartbeat{sfx(symbol)}.json"


def write_heartbeat(root: str | Path, row: dict, symbol: str = DEFAULT_SYMBOL) -> None:
    """Escritura atómica; un fallo de disco no detiene la captura (el supervisor lo notará)."""
    d = micro_dir(root)
    try:
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / (hb_name(symbol) + ".tmp")
        tmp.write_text(json.dumps(row), encoding="utf-8")
        tmp.replace(d / hb_name(symbol))
    except OSError:
        pass


def read_heartbeat(root: str | Path, symbol: str = DEFAULT_SYMBOL) -> dict | None:
    try:
        return json.loads((micro_dir(root) / hb_name(symbol)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def classify(hb: dict | None, now_ms: int, stale_s: float = STALE_S,
             silent_s: float = SILENT_S) -> tuple[str, str]:
    """(estado, motivo) del recolector según su último latido."""
    if not hb:
        return "apagado", "sin latido (el recolector nunca arrancó en este equipo)"
    age = (now_ms - int(hb.get("last_heartbeat", 0))) / 1000
    if age > stale_s:
        return "apagado", f"latido detenido hace {age:.0f} s"
    last = hb.get("last_msg_ms")
    quiet = (now_ms - int(last)) / 1000 if last else None
    if quiet is None or quiet > silent_s:
        return "sin_flujo", ("sin mensajes de mercado desde el arranque" if quiet is None
                             else f"sin mensajes de mercado hace {quiet:.0f} s")
    return "capturando", "ok"


def disk_report(root: str | Path, now: float | None = None) -> dict:
    """MB/día por tipo (tamaño ÷ horas con datos × 24), total en MB y espacio libre."""
    base = micro_dir(root)
    per_kind: dict[str, float] = {}
    total = 0
    for kind in KINDS:
        size, hours = 0, set()
        for f in (base / kind).glob("symbol=*/date=*/hour=*/part-*.parquet"):
            size += f.stat().st_size
            hours.add((f.parent.parent.name, f.parent.name, f.parent.parent.parent.name))
        total += size
        if hours:
            per_kind[kind] = round(size / len(hours) * 24 / 1e6, 2)
    try:
        free_gb = shutil.disk_usage(base if base.exists() else Path(root)).free / 1e9
    except OSError:
        free_gb = None
    return {"mb_per_day": per_kind, "mb_per_day_total": round(sum(per_kind.values()), 2),
            "total_mb": round(total / 1e6, 1),
            "free_gb": round(free_gb, 1) if free_gb is not None else None}


def prune_depth(root: str | Path, keep_days: int = DEPTH_KEEP_DAYS,
                now: float | None = None) -> int:
    """Borra las carpetas `date=` de `depth` más viejas que `keep_days`. Devuelve cuántas."""
    cutoff = time.strftime("date=%Y-%m-%d", time.gmtime((now or time.time()) - keep_days * 86400))
    n = 0
    for d in (micro_dir(root) / "depth").glob("symbol=*/date=*"):
        if d.name < cutoff:
            shutil.rmtree(d, ignore_errors=True)
            n += 1
    return n


def problems(root: str | Path, now_ms: int, free_gb_min: float = FREE_GB_MIN,
             symbol: str = DEFAULT_SYMBOL) -> list[str]:
    """Condiciones que merecen aviso local: recolector apagado/sin flujo o disco justo."""
    out = []
    hb = read_heartbeat(root, symbol)
    state, why = classify(hb, now_ms)
    young = hb and now_ms - int(hb.get("started_at", 0)) < GRACE_S * 1000
    if state != "capturando" and not (state == "sin_flujo" and young):
        out.append(f"Microestructura {symbol.upper()} {state}: {why}")
    free = disk_report(root)["free_gb"]
    if free is not None and free < free_gb_min:
        out.append(f"Disco con {free:.1f} GB libres (mínimo {free_gb_min:.0f} GB) en {root}")
    return out
