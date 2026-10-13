"""
Bitácora de trading — lectura de exports (migrado de F7/eim_bitacora.py)
========================================
Reconstruye operaciones (entrada→salida) a partir de un export real de Binance
Futuros ("Historial de órdenes" o "Historial de trading"), replicando el formato
de la bitácora manual: Short/Long, Cantidad, Fechas, Precios, Duración,
Porcentaje, Ganancia y Saldo corrido.

Fuentes de dato por operación (pnl_source), de más a menos confiable:
  1. "ledger"           — REALIZED_PNL/COMMISSION del Historial de transacciones
                           (income_bytes), emparejado por símbolo+instante exacto.
  2. "trading_history"  — Ganancia Realizada/Comisión reales, leídas directo del
                           propio "Historial de trading" (archivo primario) fila
                           por fila — ya NO se descartan para recalcular por precio.
  3. "estimado"          — reconstrucción por precio (promedio ponderado de
                           entrada vs. precio de salida), única opción cuando el
                           archivo primario es "Historial de órdenes" (no trae
                           ganancia/comisión reales) y no hay income_bytes.

Limitaciones honestas que siguen siendo ciertas:
  - El apalancamiento NUNCA viene en ningún export de Binance — es un parámetro
    obligatorio que debe darlo quien sube el archivo (ver `leverage_source` en
    el resultado); no se asume un valor por defecto.
  - "estimado" es BRUTA (sin comisión) porque el "Historial de órdenes" no trae
    comisiones. "ledger" y "trading_history" son netas de comisión cuando esa
    comisión real se pudo leer — ver `pnl_basis` por fila.
  - El saldo en COP es una conversión simple (USDT × TRM), no un balance real de cuenta.
  - El saldo (columna "Saldo") es un balance de cuenta real solo si se pasa
    `current_balance_usdt` — de lo contrario es capital declarado sin verificar
    o PnL acumulado sin ancla; ver `capital_source` en el resultado.
"""

import unicodedata
from io import BytesIO

import pandas as pd


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return s.strip().lower()


def _find_col(columns, *candidates):
    normed = {_norm(c): c for c in columns}
    for cand in candidates:
        if _norm(cand) in normed:
            return normed[_norm(cand)]
    return None


def _detect_header_row(raw: pd.DataFrame) -> int:
    """Busca la fila donde Binance realmente empieza la tabla (columnas Uid/Hora)."""
    for i in range(len(raw)):
        vals = [_norm(v) for v in raw.iloc[i].values]
        if "hora" in vals and ("uid" in vals or "simbolo" in vals):
            return i
    raise ValueError(
        "No se pudo detectar la fila de encabezado — ¿es un export de "
        "Binance Futuros ('Historial de órdenes' o 'Historial de trading')?"
    )


def parse_binance_export(file_bytes: bytes) -> pd.DataFrame:
    """
    Normaliza un export de Binance Futuros (órdenes o trading) a un DataFrame
    con columnas: timestamp, symbol, side, price, qty, quote — listo para
    reconstruir operaciones.

    Si el archivo es un "Historial de trading" (trae "Ganancia Realizada" y,
    normalmente, "Comisión" por fila), esas dos columnas se conservan como
    `realized_pnl_real`/`commission_real` — son datos reales de Binance por
    ejecución, no algo a recalcular por precio. El "Historial de órdenes" no
    las trae, así que quedan en NaN para ese formato (se sigue estimando por
    precio en ese caso, no hay alternativa real disponible).
    """
    buf = BytesIO(file_bytes)
    raw = pd.read_excel(buf, header=None)
    header_row = _detect_header_row(raw)

    buf.seek(0)
    df = pd.read_excel(buf, header=header_row)
    df = df.dropna(axis=1, how="all")

    estado_col = _find_col(df.columns, "Estado")
    ganancia_col = _find_col(df.columns, "Ganancia Realizada")
    hora_col = _find_col(df.columns, "Hora")
    simbolo_col = _find_col(df.columns, "Símbolo")
    lado_col = _find_col(df.columns, "Lado")
    comision_col = None

    if estado_col:  # Historial de órdenes — no trae ganancia/comisión reales por fila
        precio_col = _find_col(df.columns, "Precio promedio")
        qty_col = _find_col(df.columns, "Cantidad Ejecutada")
        quote_col = _find_col(df.columns, "Monto Cotizado Ejecutado")
        df = df[df[estado_col].astype(str).str.upper() == "FILLED"]
    elif ganancia_col:  # Historial de trading — sí trae ganancia/comisión reales por fila
        precio_col = _find_col(df.columns, "Precio")
        # "Cantidad" aparece dos veces (base y cotizada) — pandas renombra la 2ª a "Cantidad.1".
        cantidad_matches = [c for c in df.columns if _norm(c).startswith("cantidad")]
        qty_col = cantidad_matches[0] if cantidad_matches else None
        quote_col = cantidad_matches[1] if len(cantidad_matches) > 1 else None
        comision_col = _find_col(df.columns, "Comisión", "Comision", "Fee")
    else:
        raise ValueError(
            "Formato no reconocido — se espera un export de 'Historial de órdenes' "
            "o 'Historial de trading' de Binance Futuros."
        )

    missing = [n for n, c in [("Hora", hora_col), ("Símbolo", simbolo_col),
                               ("Lado", lado_col), ("Precio", precio_col),
                               ("Cantidad", qty_col)] if c is None]
    if missing:
        raise ValueError(f"Faltan columnas esperadas en el archivo: {', '.join(missing)}")

    out = pd.DataFrame({
        "timestamp": pd.to_datetime(df[hora_col]),
        "symbol":    df[simbolo_col].astype(str),
        "side":      df[lado_col].astype(str).str.upper(),
        "price":     pd.to_numeric(df[precio_col], errors="coerce"),
        "qty":       pd.to_numeric(df[qty_col], errors="coerce"),
        # Monto en USDT tal como lo reporta Binance — se usa directo en vez de
        # recalcular precio×cantidad (son equivalentes exactos, pero preferimos
        # el dato que el archivo ya trae en vez de uno derivado por nosotros).
        "quote":     pd.to_numeric(df[quote_col], errors="coerce") if quote_col else None,
        # Reales de Binance, solo presentes si el archivo es "Historial de
        # trading" (Ganancia Realizada es BRUTA — antes de comisión, igual
        # que REALIZED_PNL en el Historial de transacciones).
        "realized_pnl_real": pd.to_numeric(df[ganancia_col], errors="coerce") if ganancia_col else None,
        "commission_real":   pd.to_numeric(df[comision_col], errors="coerce") if comision_col else None,
    })
    if quote_col is None:
        out["quote"] = out["price"] * out["qty"]
    out = out.dropna(subset=["timestamp", "price", "qty"])
    out = out[out["qty"] > 0].sort_values("timestamp").reset_index(drop=True)
    return out
