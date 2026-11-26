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


def gates(api: str, symbol: str = "BTCUSDT") -> list[dict]:
    """T212: la puerta del marco mayor tal como la publica la mesa (`htf_gates`).

    Si la API es anterior a T212, o la vista está recalculándose, la auditoría sigue sin ella.
    """
    try:
        r = httpx.get(api.rstrip("/") + "/v2/paper", params={"symbol": symbol}, timeout=90.0)
        r.raise_for_status()
        return list(r.json().get("htf_gates") or [])
    except (httpx.HTTPError, ValueError, AttributeError):
        return []


def candles(data_dir: Path, symbol: str = "BTCUSDT", tfs: tuple[str, ...] = ("1h", "4h"),
            bars: int = 3000) -> dict:
    """Velas del disco para el signo de las puertas (T213): solo lectura, sin tocar la API.

    El almacén es parquet, así que leerlo no compite con el servicio (al contrario que
    `paper.duckdb`). Si no hay velas de un marco, ese marco se queda sin medir.
    """
    from eim.data.store import Store

    st = Store(data_dir)
    out = {}
    for tf in tfs:
        try:
            out[tf] = st.read_candles(symbol, tf, last=bars)
        except Exception:               # noqa: BLE001 — sin velas = sin medir, no un fallo
            out[tf] = []
    return out


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


def nursery(path: Path) -> dict:
    """Resumen de la cantera que deja el informe de T172 (`reports/nursery/latest.json`)."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
