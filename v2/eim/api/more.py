"""Endpoints de "Más análisis" (`/v2/more/*`): pestañas portadas del legado F7.

Cada respuesta incluye `source`/cobertura. Las fuentes externas se inyectan (`MoreSources`) para
poder probar sin red.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from eim.agents.seasonality.compute import build_matrix, monthly_closes
from eim.agents.structure.agent import snapshot_frame, structure_frame
from eim.agents.vwap.compute import compute_vwap
from eim.agents.vwap.params import LABEL, PERIODS, PREFIX
from eim.analytics.bitacora import build_bitacora
from eim.backtest.vrm import WARMUP, run_backtest
from eim.core import Candle, Liquidations
from eim.data.providers import multi_asset as ma
from eim.data.providers.liquidations import BinanceLiquidations, LiquidationsUnavailable
from eim.data.snapshot import build_snapshot
from eim.data.store import Store
from eim.data.timeframes import SYMBOLS, TF_MS


def jsonable(obj: Any) -> Any:
    """numpy/pandas → nativos; NaN/Inf → None (JSON no los admite)."""
    if isinstance(obj, float):
        return None if math.isnan(obj) or math.isinf(obj) else obj
    if hasattr(obj, "item"):
        return jsonable(obj.item())
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [jsonable(v) for v in obj]
    return obj


def _liq_fetcher(cache_dir: Path | None) -> Callable[[str, int, int], Liquidations]:
    def fetch(symbol: str, days: int, bins: int) -> Liquidations:
        return BinanceLiquidations(cache_dir=cache_dir).fetch(symbol, days=days, price_bins=bins)
    return fetch


@dataclass
class MoreSources:
    """Puntos de I/O externo; los tests los sustituyen."""

    liquidations: Callable[[str, int, int], Liquidations] | None = None
    ohlcv: Callable[[str, str, int], tuple[list[Candle], str]] = ma.fetch_ohlcv
    monthly: Callable[[str, int], tuple[list[Candle], str]] = ma.fetch_monthly
    extra: dict = field(default_factory=dict)


def _check(symbol: str, tf: str) -> None:
    if symbol not in SYMBOLS:
        raise HTTPException(400, f"símbolo no soportado: {symbol} (válidos: {list(SYMBOLS)})")
    if tf not in TF_MS:
        raise HTTPException(400, f"marco no soportado: {tf} (válidos: {list(TF_MS)})")


def _ts(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat()


def build_more_router(store: Store, src: MoreSources | None = None,
                      cache_dir: Path | None = None) -> APIRouter:
    s = src or MoreSources()
    liq_fetch = s.liquidations or _liq_fetcher(cache_dir)
    r = APIRouter(prefix="/v2/more", tags=["más análisis"])

    @r.get("/assets")
    def assets() -> dict:
        return {"assets": ma.list_assets()}

    @r.get("/multi-asset")
    def multi_asset(asset: str = "ETHUSDT", tf: str = "1d", n: int = Query(300, ge=10, le=1000)):
        try:
            spec = ma.spec_of(asset)
            candles, source = s.ohlcv(asset, tf, n)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except Exception as e:  # red/proveedor
            raise HTTPException(502, f"No se pudo obtener el precio: {e}") from e
        return {"asset_key": asset.upper(), "asset_label": spec.label, "timeframe": tf,
                "source": source, "bars": len(candles),
                "coverage": {"start": _ts(candles[0].t), "end": _ts(candles[-1].t)}
                if candles else None,
                "candles": [c.model_dump() for c in candles]}

    @r.get("/seasonality")
    def seasonality(asset: str = "ETHUSDT", start_year: int = Query(2015, ge=2000, le=2100),
                    end_year: int | None = None):
        try:
            spec = ma.spec_of(asset)
            candles, source = s.monthly(asset, start_year)
            asof = int(datetime.now(UTC).timestamp() * 1000)
            matrix = build_matrix(monthly_closes(candles, "1M", asof), start_year, end_year)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except Exception as e:
            raise HTTPException(502, f"No se pudo construir la estacionalidad: {e}") from e
        return jsonable({**matrix, "asset_key": asset.upper(), "asset_label": spec.label,
                         "source": source,
                         "requested_range": {"start_year": start_year,
                                             "end_year": end_year or datetime.now(UTC).year}})

    @r.get("/liquidations")
    def liquidations(symbol: str = "ETHUSDT", days: int = Query(30, ge=1, le=365),
                     bins: int = Query(40, ge=5, le=200)):
        try:
            liq = liq_fetch(symbol, days, bins)
        except (ValueError, LiquidationsUnavailable) as e:
            raise HTTPException(400, str(e)) from e
        except Exception as e:
            raise HTTPException(502, f"No se pudo obtener liquidaciones reales: {e}") from e
        return jsonable(liq.model_dump())

    @r.get("/vwap-periods")
    def vwap_periods(symbol: str = "ETHUSDT", tf: str = "1h",
                     n: int = Query(500, ge=50, le=5000)):
        _check(symbol, tf)
        snap = build_snapshot(store, symbol, tf, max(n, 400))
        if len(snap.candles) < 24:
            raise HTTPException(404, f"sin velas almacenadas para {symbol} {tf}")
        df = compute_vwap(snapshot_frame(snap)).tail(n)
        last = df.iloc[-1]
        series, current = {}, {}
        for p in PERIODS:
            pre = PREFIX[p]
            cols = [pre, f"{pre}_UPPER_1", f"{pre}_LOWER_1", f"{pre}_UPPER_2", f"{pre}_LOWER_2"]
            series[p] = [{"t": int(t.timestamp() * 1000), "vwap": v[0], "u1": v[1], "l1": v[2],
                          "u2": v[3], "l2": v[4]}
                         for t, v in zip(df["timestamp"], df[cols].values.tolist(), strict=True)]
            current[p] = {"label": LABEL[p], "vwap": last[pre],
                          "position": last[f"{pre}_POSITION"], "slope_pct": last[f"{pre}_SLOPE"],
                          "partial": bool(last[f"{pre}_PERIOD"] < df["timestamp"].iloc[0])}
        return jsonable({"symbol": symbol, "timeframe": tf, "periods": list(PERIODS),
                         "source": snap.sources.get("candles", "desconocida"),
                         "coverage": {"start": _ts(snap.candles[0].t),
                                      "end": _ts(snap.candles[-1].t)},
                         "close": float(last["close"]), "current": current, "series": series,
                         "candles": [{"t": c.t, "o": c.o, "h": c.h, "l": c.l, "c": c.c}
                                     for c in snap.candles[-n:]]})

    @r.get("/backtest")
    def backtest(symbol: str = "ETHUSDT", tf: str = "1h",
                 candles: int = Query(2000, ge=WARMUP + 50, le=20000),
                 horizon: int = Query(6, ge=1, le=100)):
        _check(symbol, tf)
        snap = build_snapshot(store, symbol, tf, max(candles, WARMUP + horizon + 1))
        try:
            res = run_backtest(structure_frame(snapshot_frame(snap)), horizon)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        res["symbol"], res["timeframe"] = symbol, tf
        res["source"] = snap.sources.get("candles", "desconocida")
        res["coverage"] = {"start": _ts(snap.candles[0].t), "end": _ts(snap.candles[-1].t)}
        return jsonable(res)

    @r.post("/bitacora")
    async def bitacora(
        file: UploadFile = File(...),
        income_file: UploadFile | None = File(None),
        leverage: float = Form(..., gt=0),
        starting_capital_usdt: float = Form(0.0),
        trm: float | None = Form(None),
        current_balance_usdt: float | None = Form(None),
    ):
        """`leverage` es obligatorio: ningún export de Binance lo trae y no se asume."""
        if not (file.filename or "").lower().endswith((".xlsx", ".xls")):
            raise HTTPException(400, "Solo se aceptan archivos .xlsx/.xls de Binance.")
        data = await file.read()
        income = await income_file.read() if income_file is not None else None
        try:
            res = build_bitacora(
                data, leverage=leverage, starting_capital_usdt=starting_capital_usdt, trm=trm,
                current_balance_usdt=current_balance_usdt, income_bytes=income)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except Exception as e:
            raise HTTPException(502, f"No se pudo procesar el archivo: {e}") from e
        return jsonable(res)

    return r
