"""Entradas de la auditoría (T159): la API local, el QC de la captura HFT y el funding público.

Solo lectura. El libro se lee por la API porque `paper.duckdb` lo tiene abierto el servicio
(diagnóstico de la fase 24, §8). El funding sale del REST público de Binance con el proveedor que
ya usa el arbitraje (`BinanceArbData`), sin claves; con `--sin-red` se marca «sin medir».
"""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

YEAR_MS = 365 * 86_400_000


def fetch_csv(api: str, path: str, timeout: float = 60.0) -> list[dict]:
    r = httpx.get(api.rstrip("/") + path, timeout=timeout)
    r.raise_for_status()
    return list(csv.DictReader(io.StringIO(r.text)))


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def variants(api: str) -> list[str]:
    try:
        r = httpx.get(api.rstrip("/") + "/v2/paper/variant", timeout=15.0)
        r.raise_for_status()
        return [v["name"] for v in r.json().get("variants", [])]
    except (httpx.HTTPError, ValueError, KeyError):
        return []


def calibration(api: str, symbol: str = "BTCUSDT", tf: str = "1h") -> dict:
    """Pronósticos persistidos frente a velas (T19/T26), tal como los publica la API."""
    try:
        r = httpx.get(api.rstrip("/") + "/v2/calibration", params={"symbol": symbol, "tf": tf},
                      timeout=60.0)
        r.raise_for_status()
        return {"symbol": symbol, "tf": tf, **r.json()}
    except (httpx.HTTPError, ValueError):
        return {}


def hft_quality(data_dir: Path, symbol: str = "BTCUSDT") -> dict:
    """Horas completas de la ventana del QC y días de libro L2 auditados (desde `t78_streak.since`)."""
    p = data_dir / "micro_hft" / "qc" / f"symbol={symbol}" / "summary.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"source": str(p), "pct_complete": None, "l2_days": None}
    streak = d.get("t78_streak") or {}
    since = streak.get("since")
    days = None
    if since:
        t0 = datetime.strptime(since, "%Y-%m-%dT%H").replace(tzinfo=UTC)
        days = (datetime.now(UTC) - t0).total_seconds() / 86_400
    return {"source": str(p), "generated_at": d.get("generated_at"),
            "pct_complete": d.get("pct_complete"), "window_h": d.get("window_h"),
            "streak_h": (streak.get("current") or {}).get("hours"),
            "best_streak_h": (streak.get("best") or {}).get("hours"), "l2_days": days}


def funding_apr(symbols: tuple[str, ...], now_ms: int) -> dict[str, float | None]:
    """Funding realizado de los últimos 12 meses, sumado y llevado a un año (tasa anual simple)."""
    from eim.data.providers.binance_arb import BinanceArbData

    prov = BinanceArbData()
    out: dict[str, float | None] = {}
    for sym in symbols:
        try:
            rows = prov.funding_history(sym, now_ms - YEAR_MS, now_ms)
        except Exception:                   # noqa: BLE001 — sin red = sin medir, no un fallo
            out[sym] = None
            continue
        if len(rows) < 2:
            out[sym] = None
            continue
        span = (rows[-1][0] - rows[0][0]) / YEAR_MS
        out[sym] = sum(r for _, r in rows) / span if span > 0 else None
    return out


def previous(out_dir: Path, today: str) -> dict | None:
    """La auditoría anterior más reciente (no la de hoy, si se repite el mismo día)."""
    files = sorted(p for p in out_dir.glob("audit_*.json") if today not in p.name)
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
