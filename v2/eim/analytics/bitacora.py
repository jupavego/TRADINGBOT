"""Libro contable, emparejado y armado final de la bitácora (migrado de F7)."""

from io import BytesIO

import pandas as pd

from eim.analytics.bitacora_parse import _find_col, _norm, parse_binance_export
from eim.analytics.bitacora_trades import reconstruct_trades


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
