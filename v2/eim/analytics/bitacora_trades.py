"""Reconstrucción de operaciones entrada→salida a partir de fills (migrado de F7)."""


import pandas as pd


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
