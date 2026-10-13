"""
EIM-F7 | Módulo 9: Bitácora de Trading
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
from datetime import datetime
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


def reconstruct_trades(fills: pd.DataFrame, leverage: float) -> list:
    """
    Reconstruye operaciones realizando ganancia/pérdida en CADA reducción de
    posición contra el precio promedio ponderado vigente — igual que el libro
    contable (REALIZED_PNL) de Binance, no solo cuando la posición vuelve
    exactamente a cero.

    Por qué el cambio: la primera versión solo "cerraba" una operación al
    llegar a cero, así que una posición que se fue reduciendo y aumentando
    parcialmente durante meses (ej. tras una liquidación parcial) quedaba
    comprimida en una sola fila con un promedio que no coincidía con la suma
    de lo que Binance fue realizando internamente en cada reducción real.
    Validado contra un export real: con este método, la pérdida reconstruida
    de una liquidación coincidió con el REALIZED_PNL real de Binance dentro
    de ~3% (la diferencia restante es comisión).

    Si `fills` trae `realized_pnl_real`/`commission_real` (viene de un
    "Historial de trading", ver parse_binance_export), cada operación usa
    ese dato real de Binance en vez de la reconstrucción por precio —
    corresponde 1:1 al fill que la genera, porque cada reducción de posición
    consume como máximo un fill (una reducción nunca queda repartida entre
    dos fills). Sin ese dato (ej. "Historial de órdenes", que no lo trae),
    se sigue estimando por precio — no hay otra fuente real disponible ahí.
    """
    trades = []

    for symbol, group in fills.groupby("symbol"):
        group = group.sort_values("timestamp").reset_index(drop=True)

        position_qty = 0.0   # con signo: + long, - short
        avg_price = 0.0      # precio promedio ponderado de la exposición abierta actual
        open_time = None     # cuándo arrancó esta racha de exposición (desde cero)

        for _, fill in group.iterrows():
            remaining = fill["qty"] if fill["side"] == "BUY" else -fill["qty"]

            while abs(remaining) > 1e-12:
                if position_qty == 0:
                    # Abre exposición nueva desde plano — no realiza nada todavía.
                    open_time = fill["timestamp"]
                    avg_price = fill["price"]
                    position_qty = remaining
                    remaining = 0.0
                    continue

                same_direction = (remaining > 0) == (position_qty > 0)

                if same_direction:
                    # Promedia hacia la posición — sigue sin realizar nada.
                    new_qty = position_qty + remaining
                    avg_price = (avg_price * abs(position_qty) + fill["price"] * abs(remaining)) / abs(new_qty)
                    position_qty = new_qty
                    remaining = 0.0
                else:
                    # Reduce (o cierra y voltea) — AQUÍ se realiza la ganancia/pérdida.
                    reducing = min(abs(remaining), abs(position_qty))
                    direction = 1 if position_qty > 0 else -1
                    pnl = (fill["price"] - avg_price) * reducing * direction
                    margin = avg_price * reducing / leverage if leverage else None
                    pct = (pnl / margin * 100) if margin else None

                    real_pnl  = fill.get("realized_pnl_real")
                    real_comm = fill.get("commission_real")
                    has_real  = real_pnl is not None and not pd.isna(real_pnl)

                    trades.append({
                        "symbol":        symbol,
                        "side":          "Long" if position_qty > 0 else "Short",
                        "qty":           reducing,
                        "open_time":     open_time,
                        "close_time":    fill["timestamp"],
                        "entry_price":   avg_price,
                        "exit_price":    fill["price"],
                        "price_diff":    fill["price"] - avg_price,
                        "duration_seconds": (fill["timestamp"] - open_time).total_seconds(),
                        "pnl_usdt":      pnl,
                        "margin_usdt":   margin,
                        "pct_return":    pct,
                        # Real de Binance (Historial de trading) si está disponible;
                        # si no, se queda en estimado por precio (pnl_usdt de arriba).
                        "pnl_source":      "trading_history" if has_real else "estimado",
                        "pnl_ledger_usdt": float(real_pnl) if has_real else None,
                        "commission_usdt": (abs(float(real_comm))
                                             if (real_comm is not None and not pd.isna(real_comm))
                                             else None),
                    })

                    position_qty -= reducing if position_qty > 0 else -reducing
                    remaining -= reducing if remaining > 0 else -reducing

                    if abs(position_qty) < 1e-9:
                        position_qty = 0.0
                        avg_price = 0.0
                        open_time = None
                    # si sobra `remaining` (la reducción volteó la posición),
                    # el while sigue y con position_qty==0 abre la nueva exposición.

    trades.sort(key=lambda t: t["close_time"])
    return trades


def parse_income_history(file_bytes: bytes) -> pd.DataFrame:
    """
    Normaliza el 'Historial de transacciones' (Income History) de Binance — el
    libro contable real: REALIZED_PNL, COMMISSION, FUNDING_FEE, TRANSFER, etc.
    """
    buf = BytesIO(file_bytes)
    raw = pd.read_excel(buf, header=None)
    header_row = None
    for i in range(len(raw)):
        vals = [_norm(v) for v in raw.iloc[i].values]
        if "hora" in vals and "tipo" in vals and "cantidad" in vals:
            header_row = i
            break
    if header_row is None:
        raise ValueError(
            "No se pudo detectar la fila de encabezado — ¿es un export de "
            "'Historial de transacciones' de Binance Futuros?"
        )

    buf.seek(0)
    df = pd.read_excel(buf, header=header_row)
    df = df.dropna(axis=1, how="all")

    hora_col = _find_col(df.columns, "Hora")
    tipo_col = _find_col(df.columns, "Tipo")
    cantidad_col = _find_col(df.columns, "Cantidad")
    simbolo_col = _find_col(df.columns, "Símbolo")

    missing = [n for n, c in [("Hora", hora_col), ("Tipo", tipo_col), ("Cantidad", cantidad_col)] if c is None]
    if missing:
        raise ValueError(f"Faltan columnas esperadas en el archivo de transacciones: {', '.join(missing)}")

    out = pd.DataFrame({
        "timestamp": pd.to_datetime(df[hora_col]),
        "tipo":      df[tipo_col].astype(str).str.upper(),
        "cantidad":  pd.to_numeric(df[cantidad_col], errors="coerce"),
        "symbol":    df[simbolo_col].astype(str) if simbolo_col else "",
    })
    out = out.dropna(subset=["timestamp", "cantidad"])
    return out.sort_values("timestamp").reset_index(drop=True)


def match_ledger(trades: list, income: pd.DataFrame) -> None:
    """
    Empareja cada operación reconstruida con el REALIZED_PNL y la COMMISSION
    reales de Binance, buscando el mismo símbolo en el mismo instante exacto
    (el cierre de una operación y su línea contable comparten timestamp — lo
    validamos contra un export real antes de implementar esto). Modifica cada
    trade en el lugar.

    Cuando no hay línea contable para ese instante (ej. la operación cerró
    antes de que empezara el periodo del archivo de transacciones), el trade
    NO se toca — puede que ya traiga datos reales desde `reconstruct_trades`
    (si el archivo primario era un "Historial de trading", pnl_source ya
    quedó en "trading_history") o, si no, sigue en "estimado". Antes esta
    función forzaba "estimado" incondicionalmente cuando no había match,
    descartando esos datos reales aunque existieran — ya no.
    """
    realized = income[income["tipo"] == "REALIZED_PNL"]
    commission = income[income["tipo"] == "COMMISSION"]

    for t in trades:
        match_pnl = realized[(realized["timestamp"] == t["close_time"]) & (realized["symbol"] == t["symbol"])]
        match_fee = commission[(commission["timestamp"] == t["close_time"]) & (commission["symbol"] == t["symbol"])]

        if len(match_pnl):
            t["pnl_ledger_usdt"] = float(match_pnl["cantidad"].sum())
            # COMMISSION en el Historial de transacciones viene negativa (es un
            # costo); se normaliza a magnitud positiva, igual que
            # reconstruct_trades hace con la comisión del Historial de trading,
            # para que el resto del pipeline reste siempre con el mismo signo.
            t["commission_usdt"] = abs(float(match_fee["cantidad"].sum())) if len(match_fee) else 0.0
            t["pnl_source"] = "ledger"
        # si no hay match, no tocar `t` — ver docstring.


def build_bitacora(
    file_bytes: bytes,
    leverage: float,
    starting_capital_usdt: float = 0.0,
    trm: float | None = None,
    current_balance_usdt: float | None = None,
    income_bytes: bytes | None = None,
) -> dict:
    """
    Pipeline completo: parsea el export, reconstruye operaciones y arma el reporte.

    Si se pasa `income_bytes` (el 'Historial de transacciones' de Binance —
    el libro contable real), cada operación se empareja por símbolo+instante
    exacto con su línea REALIZED_PNL/COMMISSION real. Cuando hay coincidencia,
    la ganancia mostrada es la REAL de Binance (neta de comisión), no la
    estimada por reconstrucción de precios — ver pnl_source por fila ("ledger"
    vs "estimado"). Las operaciones fuera del periodo cubierto por ese archivo
    (ej. antes de su fecha de inicio) quedan en "estimado", declarado así.

    Si se pasa `current_balance_usdt` (tu saldo real conocido AHORA, ej. el que
    muestra la app de Binance), se ignora `starting_capital_usdt` y en su lugar
    se calcula hacia atrás: capital_inicial = saldo_actual - PnL_total_reconstruido.
    Así la curva de saldo termina exactamente en tu saldo real.

    OJO — esto no corrige nada intermedio: si hubo abonos o retiros durante el
    periodo, quedan absorbidos en ese único ajuste del capital inicial, no
    distribuidos en el punto donde realmente ocurrieron. Y si tienes una
    posición ABIERTA ahora mismo, su PnL no realizado no está incluido aquí
    (esta bitácora solo cuenta operaciones ya cerradas) — tu saldo real puede
    diferir del calculado por esa razón también.

    Sobre "no suponer datos" — dos campos de este reporte NUNCA vienen del
    export de Binance y siempre son un supuesto externo, sin importar el
    valor por defecto: `leverage` (ninguno de los dos formatos de export lo
    trae) y, si no se pasa `current_balance_usdt`, también el punto de
    partida del "saldo" (columna acumulada, no un balance de cuenta real).
    El resultado expone `leverage_source` y `capital_source` explícitamente
    para que el consumidor del reporte (UI o Excel) pueda distinguir sin
    ambigüedad qué es dato del exchange y qué es un supuesto del usuario.
    """
    fills = parse_binance_export(file_bytes)
    if fills.empty:
        raise ValueError("El archivo no contiene ejecuciones (FILLED) reconocibles.")

    trades = reconstruct_trades(fills, leverage=leverage)
    if not trades:
        raise ValueError("No se pudo reconstruir ninguna operación completa (posición plana → plana).")

    income_summary = None
    if income_bytes is not None:
        income = parse_income_history(income_bytes)
        match_ledger(trades, income)
        income_summary = {
            "date_range_start":   income["timestamp"].min().isoformat(),
            "date_range_end":     income["timestamp"].max().isoformat(),
            "total_realized_pnl": round(float(income.loc[income["tipo"] == "REALIZED_PNL", "cantidad"].sum()), 2),
            "total_commission":   round(float(income.loc[income["tipo"] == "COMMISSION", "cantidad"].sum()), 2),
            "total_funding_fee":  round(float(income.loc[income["tipo"] == "FUNDING_FEE", "cantidad"].sum()), 2),
            "total_transfers":    round(float(income.loc[income["tipo"] == "TRANSFER", "cantidad"].sum()), 2),
        }
    # Nota: ya no hay un "else" que fuerce pnl_source="estimado" aquí. Cada
    # trade sale de reconstruct_trades con pnl_source="trading_history" (si
    # el archivo primario traía Ganancia Realizada/Comisión reales por fila)
    # o "estimado" (si no). match_ledger(), arriba, solo puede SUBIR de nivel
    # a "ledger" cuando encuentra un match exacto en el Historial de
    # transacciones — nunca degrada un trade que ya tenía datos reales.

    # Ganancia efectiva por fila: real (ledger o trading_history, neta de
    # comisión cuando la comisión real está disponible) cuando hay datos de
    # Binance; si no, la estimada por reconstrucción de precios (bruta).
    for t in trades:
        if t["pnl_source"] in ("ledger", "trading_history"):
            t["pnl_effective"] = t["pnl_ledger_usdt"] - (t["commission_usdt"] or 0.0)
        else:
            t["pnl_effective"] = t["pnl_usdt"]

    if current_balance_usdt is not None:
        total_pnl_preview = sum(t["pnl_effective"] for t in trades)
        starting_capital_usdt = current_balance_usdt - total_pnl_preview
        capital_source = "reconciliado_a_saldo_real"
    elif starting_capital_usdt:
        capital_source = "capital_inicial_declarado_por_usuario"
    else:
        # Ni saldo real ni capital inicial: el "saldo" que sigue es PnL
        # acumulado desde 0, no un balance de cuenta — debe quedar marcado
        # sin ambigüedad en vez de parecer un balance real por casualidad.
        capital_source = "sin_ancla_es_pnl_acumulado_desde_cero"

    saldo_usdt = starting_capital_usdt
    rows = []
    for t in trades:
        pnl = t["pnl_effective"]
        saldo_usdt += pnl
        rows.append({
            "symbol":        t["symbol"],
            "side":          t["side"],
            "qty":           round(t["qty"], 6),
            "leverage":      leverage,
            "leverage_source": "asumido_no_viene_en_el_export",
            "open_time":     t["open_time"].isoformat(),
            "close_time":    t["close_time"].isoformat(),
            "entry_price":   round(t["entry_price"], 4),
            "exit_price":    round(t["exit_price"], 4),
            "price_diff":    round(t["price_diff"], 4),
            "duration_seconds": t["duration_seconds"],
            "pct_return":    round(t["pct_return"], 2) if t["pct_return"] is not None else None,
            "pnl_source":    t["pnl_source"],
            # "neta" solo si de verdad restamos una comisión real; si el
            # archivo trae Ganancia Realizada pero no columna de Comisión
            # (o no hubo match en el libro contable), sigue siendo bruta —
            # no se inventa un descuento que no se pudo confirmar.
            "pnl_basis":     "neta_de_comision" if t.get("commission_usdt") is not None else "bruta",
            "pnl_estimado_usdt": round(t["pnl_usdt"], 2),
            "commission_usdt": round(t["commission_usdt"], 2) if t["commission_usdt"] is not None else None,
            "pnl_usdt":      round(pnl, 2),
            "pnl_cop":       round(pnl * trm, 0) if trm else None,
            "saldo_usdt":    round(saldo_usdt, 2),
            "saldo_cop":     round(saldo_usdt * trm, 0) if trm else None,
        })

    wins = [r for r in rows if r["pnl_usdt"] > 0]
    losses = [r for r in rows if r["pnl_usdt"] < 0]
    total_pnl = sum(r["pnl_usdt"] for r in rows)
    durations = [t["duration_seconds"] for t in trades]
    verified = [r for r in rows if r["pnl_source"] in ("ledger", "trading_history")]

    summary = {
        "total_trades":       len(rows),
        "verified_trades":     len(verified),
        "estimated_trades":    len(rows) - len(verified),
        "wins":                len(wins),
        "losses":              len(losses),
        "win_rate_pct":        round(len(wins) / len(rows) * 100, 1) if rows else 0,
        "total_pnl_usdt":      round(total_pnl, 2),
        "total_pnl_cop":       round(total_pnl * trm, 0) if trm else None,
        "avg_win_usdt":        round(sum(r["pnl_usdt"] for r in wins) / len(wins), 2) if wins else 0,
        "avg_loss_usdt":       round(sum(r["pnl_usdt"] for r in losses) / len(losses), 2) if losses else 0,
        "best_trade_usdt":     round(max(r["pnl_usdt"] for r in rows), 2),
        "worst_trade_usdt":    round(min(r["pnl_usdt"] for r in rows), 2),
        "avg_duration_seconds": sum(durations) / len(durations) if durations else 0,
        "starting_capital_usdt": round(starting_capital_usdt, 2),
        "capital_source":      capital_source,
        "final_saldo_usdt":    round(saldo_usdt, 2),
        "final_saldo_cop":     round(saldo_usdt * trm, 0) if trm else None,
        "reconciled_to_real_balance": current_balance_usdt is not None,
        "leverage":            leverage,
        "leverage_source":     "asumido_no_viene_en_el_export",
        "trm":                 trm,
        "income_ledger":       income_summary,
    }

    return {"summary": summary, "trades": rows}
