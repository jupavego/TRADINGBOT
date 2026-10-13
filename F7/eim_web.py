"""
EIM-F7 | Módulo 5: Interfaz Web
=================================
Backend FastAPI que expone EIMEngine (tiempo real, histórico y backtest)
como servicio web. Sirve una única página (web/index.html) con pestañas
para los tres modos.

Uso:
    python -m uvicorn eim_web:app --reload --port 8000
    → abrir http://127.0.0.1:8000
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# El engine imprime caracteres unicode (→, ═, θ...); en Windows el stdout de
# consola por defecto usa un codepage que no los soporta y revienta el print.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from eim_engine       import EIMEngine
from eim_frm          import EIMFRM
from eim_vwap         import EIMVWAP
from eim_price_action import EIMPriceAction
from eim_elliott      import EIMElliott
from eim_bitacora     import build_bitacora
from eim_data         import EIMDataFeed
from eim_market_data  import EIMMultiAssetFeed, SUPPORTED_ASSETS
from eim_liquidations import fetch_liquidations, EIMLiquidationMap
from eim_seasonality  import build_seasonality_matrix

WEB_DIR = Path(__file__).parent / "web"

app = FastAPI(title="EIM — Diagnóstico en Tiempo Real")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

# Un engine por combinación (symbol, timeframe) — evita reabrir conexión en cada request.
_engines: dict[tuple[str, str], EIMEngine] = {}
_multi_asset_feed: EIMMultiAssetFeed | None = None


def _get_engine(symbol: str, timeframe: str) -> EIMEngine:
    key = (symbol.upper(), timeframe)
    if key not in _engines:
        _engines[key] = EIMEngine(symbol=symbol, timeframe=timeframe)
    return _engines[key]


def _get_multi_asset_feed() -> EIMMultiAssetFeed:
    # Sin EIMDataFeed() eager aquí a propósito: EIMMultiAssetFeed la crea
    # perezosamente solo si el activo pedido de verdad viene de Binance —
    # pedir S&P 500/Nasdaq (Yahoo) no debe depender de que Binance responda.
    global _multi_asset_feed
    if _multi_asset_feed is None:
        _multi_asset_feed = EIMMultiAssetFeed()
    return _multi_asset_feed


def _jsonable(obj):
    """
    Convierte tipos numpy/pandas (float64, int64...) a nativos de Python y
    reemplaza NaN/Infinity por None (las primeras velas tienen NaN en columnas
    con ventana rolling — VOLUME_RATIO, ATR_RELATIVE — que JSON no admite).
    """
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if hasattr(obj, "item"):
        return _jsonable(obj.item())
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


def _check_timeframe(timeframe: str):
    if timeframe not in {"1h", "4h", "1d"}:
        raise HTTPException(status_code=400, detail=f"Timeframe '{timeframe}' no válido.")


class DiagnoseRequest(BaseModel):
    symbol:    str = "BTCUSDT"
    timeframe: str = "4h"
    context:   int = 500


class HistoricalRequest(BaseModel):
    symbol:    str = "BTCUSDT"
    timeframe: str = "4h"
    candles:   int = 500


class BacktestRequest(BaseModel):
    symbol:    str = "BTCUSDT"
    timeframe: str = "4h"
    candles:   int = 2000
    horizon:   int = 6


class VwapRequest(BaseModel):
    symbol:    str = "BTCUSDT"
    timeframe: str = "4h"
    candles:   int = 500


class PriceActionRequest(BaseModel):
    symbol:    str = "BTCUSDT"
    timeframe: str = "4h"
    candles:   int = 500


class ElliottRequest(BaseModel):
    symbol:        str = "BTCUSDT"
    timeframe:     str = "4h"
    candles:       int = 500
    threshold_pct: float = 3.0


class VwapPeriodsRequest(BaseModel):
    symbol:    str = "BTCUSDT"
    timeframe: str = "4h"
    candles:   int = 500
    periods:   list[str] = ["daily", "weekly", "quincenal", "monthly"]


class LiquidationsRequest(BaseModel):
    symbol:      str = "BTCUSDT"
    days:        int = 30
    price_bins:  int = 40
    time_bucket: str = "1D"   # ej. "1D", "4H" — pandas floor-string


class MultiAssetRequest(BaseModel):
    asset_key: str = "ETHUSDT"
    timeframe: str = "1d"
    candles:   int = 300


class SeasonalityRequest(BaseModel):
    asset_key:  str = "ETHUSDT"
    start_year: int = 2015
    end_year:   int | None = None


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


@app.post("/api/diagnose")
def diagnose(req: DiagnoseRequest):
    """Corre el pipeline EIM completo sobre la vela actual y devuelve DIAG-001."""
    _check_timeframe(req.timeframe)
    try:
        engine = _get_engine(req.symbol, req.timeframe)
        diagnosis = engine.run_realtime(context=max(req.context, 400))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    result = diagnosis.to_dict()
    # Lectura direccional heurística: la convicción (0-100, >50 = sesgo alcista)
    # se "encoge" hacia 50 (sin sesgo) en proporción a cuánta confianza tiene el
    # propio diagnóstico — no es una probabilidad estadística validada, es una
    # forma explícita y documentada de combinar ambos scores en una sola lectura.
    conviction, confidence = result["conviction_score"], result["confidence_score"]
    prob_up = max(5.0, min(95.0, 50 + (conviction - 50) * (confidence / 95)))
    result["prob_up_pct"]   = round(prob_up, 1)
    result["prob_down_pct"] = round(100 - prob_up, 1)
    return result


# Columnas que viajan al front para el gráfico + tabla de histórico.
HISTORICAL_COLUMNS = [
    "timestamp", "open", "high", "low", "close", "EMA_9", "EMA_21", "EMA_55", "EMA_100", "EMA_200",
    "STRUCTURAL_STATE", "MOMENTUM_STATE", "ENERGY_STATE",
    "PROBABLE_SCENARIO", "CONFIDENCE_SCORE", "CONVICTION_SCORE",
]


@app.post("/api/historical")
def historical(req: HistoricalRequest):
    """Corre el pipeline EIM sobre N velas históricas para graficar precio + EMAs."""
    _check_timeframe(req.timeframe)
    try:
        engine = _get_engine(req.symbol, req.timeframe)
        df = engine.run_historical(candles=max(req.candles, 400), save=False)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    out = df[HISTORICAL_COLUMNS].copy()
    out["timestamp"] = out["timestamp"].astype(str)
    return _jsonable(out.to_dict(orient="records"))


@app.post("/api/raw")
def raw_variables(req: DiagnoseRequest):
    """
    Devuelve TODAS las variables L1/L2 del FRM + estados L3 del BRM para la
    vela actual, junto con el diagnóstico IRM. Vista de depuración/calibración
    — no filtra columnas como /api/diagnose o /api/historical.
    """
    _check_timeframe(req.timeframe)
    try:
        engine = _get_engine(req.symbol, req.timeframe)
        df = engine.feed.get_realtime_with_context(req.symbol, req.timeframe, max(req.context, 400))
        df = EIMFRM(df).run_all()
        df = engine.brm.run_all(df)
        last_row = df.iloc[-1]
        diagnosis = engine.irm.diagnose_row(
            last_row,
            comb_status=last_row.get("COMBINATION_STATUS", "NORMAL"),
            transition_status=last_row.get("TRANSITION_STATUS", "N/A"),
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    raw = last_row.to_dict()
    raw["timestamp"] = str(raw.get("timestamp", ""))
    return _jsonable({"raw": raw, "diagnosis": diagnosis.to_dict()})


VWAP_COLUMNS = [
    "timestamp", "open", "high", "low", "close",
    "VWAP_DAY", "VWAP_DAY_UPPER_1", "VWAP_DAY_LOWER_1",
    "VWAP_DAY_UPPER_2", "VWAP_DAY_LOWER_2",
    "VWAP_ANCHOR", "VWAP_DAY_POSITION", "VWAP_DAY_SLOPE",
]


@app.post("/api/vwap")
def vwap(req: VwapRequest):
    """VWAP diario + bandas y VWAP anclado, sobre la vela actual y su contexto."""
    _check_timeframe(req.timeframe)
    try:
        engine = _get_engine(req.symbol, req.timeframe)
        df = engine.feed.get_realtime_with_context(req.symbol, req.timeframe, max(req.candles, 400))
        df = EIMVWAP(df).run_all()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    out = df[VWAP_COLUMNS].copy()
    out["timestamp"] = out["timestamp"].astype(str)
    records = _jsonable(out.to_dict(orient="records"))

    last = df.iloc[-1]
    current = dict(records[-1])
    current.update(EIMVWAP.interpret(last["VWAP_DAY_POSITION"], last["VWAP_DAY_SLOPE"]))

    return {"records": records, "current": _jsonable(current)}


VWAP_PERIOD_PREFIXES = {
    "daily": "VWAP_DAY", "weekly": "VWAP_WEEK",
    "quincenal": "VWAP_QUINCENA", "monthly": "VWAP_MONTH",
}


@app.post("/api/vwap-periods")
def vwap_periods(req: VwapPeriodsRequest):
    """
    VWAP con bandas para varios períodos a la vez (diario/semanal/quincenal/
    mensual) sobre la misma ventana de velas — ver eim_vwap.py para la
    definición exacta de cada período (quincenal = días 1 y 16 del mes, no
    un bloque rodante de 14 días).
    """
    _check_timeframe(req.timeframe)
    unknown = [p for p in req.periods if p not in VWAP_PERIOD_PREFIXES]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Períodos no reconocidos: {unknown}")

    try:
        engine = _get_engine(req.symbol, req.timeframe)
        df = engine.feed.get_realtime_with_context(req.symbol, req.timeframe, max(req.candles, 400))
        df = EIMVWAP(df).run_all(periods=tuple(req.periods))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    columns = ["timestamp", "open", "high", "low", "close"]
    current = {}
    for period in req.periods:
        prefix = VWAP_PERIOD_PREFIXES[period]
        columns += [prefix, f"{prefix}_UPPER_1", f"{prefix}_LOWER_1",
                    f"{prefix}_UPPER_2", f"{prefix}_LOWER_2",
                    f"{prefix}_POSITION", f"{prefix}_SLOPE"]
        last = df.iloc[-1]
        current[period] = _jsonable({
            "vwap":     last[prefix],
            "position": last[f"{prefix}_POSITION"],
            "slope":    last[f"{prefix}_SLOPE"],
            **EIMVWAP.interpret(last[f"{prefix}_POSITION"], last[f"{prefix}_SLOPE"]),
        })

    out = df[columns].copy()
    out["timestamp"] = out["timestamp"].astype(str)
    records = _jsonable(out.to_dict(orient="records"))

    return {"records": records, "current": current, "periods": req.periods}


PRICE_ACTION_COLUMNS = [
    "timestamp", "open", "high", "low", "close", "volume",
    "SWING_HIGH", "SWING_LOW",
    "BULLISH_ENGULFING", "BEARISH_ENGULFING", "HAMMER", "SHOOTING_STAR",
    "DOJI", "INSIDE_BAR", "OUTSIDE_BAR",
    "STRUCTURE_EVENT", "STRUCTURE_STATE",
]


@app.post("/api/price-action")
def price_action(req: PriceActionRequest):
    """
    Swings, patrones de vela y estructura de mercado (HH/HL/LH/LL, BOS/CHOCH)
    + zonas de soporte/resistencia. Usa velas cerradas (no la vela en formación),
    porque los swings solo se pueden confirmar con velas completas.
    """
    _check_timeframe(req.timeframe)
    try:
        engine = _get_engine(req.symbol, req.timeframe)
        df = engine.feed.get_historical(req.symbol, req.timeframe, max(req.candles, 400))
        df, sr_zones = EIMPriceAction(df).run_all()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    out = df[PRICE_ACTION_COLUMNS].copy()
    out["timestamp"] = out["timestamp"].astype(str)
    records = _jsonable(out.to_dict(orient="records"))

    last_close = float(df["close"].iloc[-1])
    above = [z for z in sr_zones if z["price"] > last_close]
    below = [z for z in sr_zones if z["price"] <= last_close]
    nearest_resistance = min(above, key=lambda z: z["price"]) if above else None
    nearest_support    = max(below, key=lambda z: z["price"]) if below else None

    return _jsonable({
        "records":            records,
        "sr_zones":           sr_zones,
        "nearest_resistance": nearest_resistance,
        "nearest_support":    nearest_support,
        "current_close":      last_close,
    })


@app.post("/api/elliott")
def elliott(req: ElliottRequest):
    """
    Conteo TENTATIVO de ondas de Elliott vía zigzag heurístico (umbral % configurable).
    No hay forma objetiva de contar ondas: valida contra las 3 reglas duras y
    reporta violaciones explícitas en vez de forzar un conteo inválido.
    """
    _check_timeframe(req.timeframe)
    try:
        engine = _get_engine(req.symbol, req.timeframe)
        df = engine.feed.get_historical(req.symbol, req.timeframe, max(req.candles, 400))
        result = EIMElliott(df, threshold_pct=req.threshold_pct).run_all()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    price = df[["timestamp", "open", "high", "low", "close"]].copy()
    price["timestamp"] = price["timestamp"].astype(str)

    return _jsonable({
        "price": price.to_dict(orient="records"),
        **result,
    })


@app.post("/api/bitacora")
async def bitacora(
    file: UploadFile = File(...),
    income_file: UploadFile | None = File(None),
    leverage: float = Form(...),
    starting_capital_usdt: float = Form(0.0),
    trm: float | None = Form(None),
    current_balance_usdt: float | None = Form(None),
):
    """
    Reconstruye la bitácora de trading a partir de un export real de Binance
    Futuros ('Historial de órdenes' o 'Historial de trading'). Ver eim_bitacora.py
    para las limitaciones (apalancamiento fijo, COP = conversión simple).
    Si se pasa current_balance_usdt, el capital inicial se calcula hacia atrás
    para que el saldo final coincida con ese saldo real conocido.
    Si el archivo primario es un "Historial de trading", cada operación ya usa
    la Ganancia Realizada/Comisión reales que ese archivo trae por fila
    (pnl_source="trading_history") en vez de recalcularlas por precio. Si
    además se pasa income_file ('Historial de transacciones'), cada operación
    se valida/mejora contra el REALIZED_PNL/COMMISSION del libro contable real
    — ver pnl_source por fila ("ledger" > "trading_history" > "estimado" en
    orden de confiabilidad).

    `leverage` es obligatorio y sin valor por defecto a propósito: ningún
    export de Binance lo incluye, así que no hay un valor "razonable" que
    asumir en el servidor — debe venir siempre de quien sube el archivo.
    """
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos .xlsx/.xls de Binance.")

    data = await file.read()
    income_data = await income_file.read() if income_file is not None else None
    try:
        result = build_bitacora(
            data, leverage=leverage,
            starting_capital_usdt=starting_capital_usdt,
            trm=trm,
            current_balance_usdt=current_balance_usdt,
            income_bytes=income_data,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"No se pudo procesar el archivo: {e}")

    return _jsonable(result)


@app.post("/api/backtest")
def backtest(req: BacktestRequest):
    """Corre el protocolo de backtesting EIM-VRM-001 y devuelve las métricas MET-001 a MET-006."""
    _check_timeframe(req.timeframe)
    min_candles = 400 + req.horizon + 1
    try:
        engine = _get_engine(req.symbol, req.timeframe)
        metrics = engine.run_backtest(candles=max(req.candles, min_candles), horizon=req.horizon, save=False)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    return _jsonable(metrics)


# ═══════════════════════════════════════════════════════════════════
# Liquidaciones, multi-activo, estacionalidad
# ═══════════════════════════════════════════════════════════════════

@app.post("/api/liquidations")
def liquidations(req: LiquidationsRequest):
    """
    Mapa de liquidaciones REALES (no estimadas) de Binance Futuros — dataset
    oficial liquidationSnapshot de data.binance.vision, ~1 día de retraso.
    Ver eim_liquidations.py para por qué esta fuente y no una sintética o
    un stream en vivo. Devuelve una matriz precio×tiempo (para el mapa de
    calor) y totales diarios long/short (para la vista simple de barras).
    """
    try:
        raw = fetch_liquidations(req.symbol, days=req.days)
        result = EIMLiquidationMap(raw).run_all(
            price_bins=req.price_bins, time_bucket=req.time_bucket
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"No se pudo obtener liquidaciones reales: {e}")

    return _jsonable(result)


@app.get("/api/assets")
def list_assets():
    """Activos disponibles para el visor multi-activo y la matriz de estacionalidad."""
    return {"assets": EIMMultiAssetFeed.list_assets()}


@app.post("/api/multi-asset")
def multi_asset(req: MultiAssetRequest):
    """
    OHLCV puro (sin pipeline de diagnóstico FRM/BRM/IRM) para el visor de
    velas multi-activo — cripto/oro vía Binance Futuros, S&P 500/Nasdaq vía
    Yahoo Finance. Ver eim_market_data.py para las fuentes exactas por activo.
    """
    try:
        feed = _get_multi_asset_feed()
        df = feed.get_asset_ohlcv(req.asset_key, req.timeframe, candles=req.candles)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"No se pudo obtener el precio: {e}")

    out = df[["timestamp", "open", "high", "low", "close", "volume", "asset_key", "asset_label"]].copy()
    out["timestamp"] = out["timestamp"].astype(str)
    return _jsonable(out.to_dict(orient="records"))


@app.post("/api/seasonality")
def seasonality(req: SeasonalityRequest):
    """
    Matriz Año × Mes de retorno % de cierre mensual real. Un año sin datos
    reales del activo simplemente no aparece como fila — ver
    `real_data_range` en la respuesta para saber desde cuándo hay cobertura
    real (los perpetuos cripto de Binance no llegan a 2015; los índices vía
    Yahoo Finance sí).
    """
    try:
        feed = _get_multi_asset_feed()
        result = build_seasonality_matrix(
            req.asset_key, start_year=req.start_year, end_year=req.end_year,
            binance_feed=feed.binance_feed_if_ready,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"No se pudo construir la matriz de estacionalidad: {e}")

    return _jsonable(result)
