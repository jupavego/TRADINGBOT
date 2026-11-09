"""Comisiones de Binance: **una sola fuente** para todo el sistema (T143).

Antes la misma tarifa estaba escrita en tres sitios con tres valores: 5 pb en el simulador
(`CostParams`), 4 pb en el bróker del papel (`SimBroker`) y 5 pb «supuestos» en `sim_ledger`. El
libro vivo cobraba de menos y, con una sola tasa, no podía distinguir una entrada a mercado de una
orden límite: justo la diferencia que T143 adoptó. Quien necesite una tarifa la pide aquí.

Las tablas son las públicas de Binance. **VIP 0 verificado el 2026-10-15**; el resto son de
referencia y hay que confirmarlas contra la cuenta con `/fapi/v1/commissionRate` (BACKLOG T38 (2)),
que además recoge el descuento por pagar en BNB y las rebajas por referido. Sin esa clave se usa
VIP 0, que es el nivel más caro y por tanto el supuesto conservador.
"""

from __future__ import annotations

FeeTable = dict[int, tuple[float, float]]  # nivel VIP → (maker, taker) en fracción

SPOT_FEES: FeeTable = {
    0: (0.0010, 0.0010), 1: (0.0009, 0.0010), 2: (0.0008, 0.0010), 3: (0.00042, 0.0006),
    4: (0.00042, 0.00054), 5: (0.00036, 0.00048), 6: (0.0003, 0.00042),
    7: (0.00024, 0.00036), 8: (0.00018, 0.0003), 9: (0.00012, 0.00024),
}
USDM_FEES: FeeTable = {
    0: (0.0002, 0.0005), 1: (0.00016, 0.0004), 2: (0.00014, 0.00035), 3: (0.00012, 0.00032),
    4: (0.0001, 0.0003), 5: (0.00008, 0.00027), 6: (0.00006, 0.00025),
    7: (0.00004, 0.00022), 8: (0.00002, 0.0002), 9: (0.0, 0.00017),
}
FEE_SOURCE = ("tabla pública Binance (VIP 0 verificado 2026-10-15; otros niveles de referencia; "
              "USDC-M sin verificar → igual que USDⓈ-M) · configurable")

#: Tarifa con la que opera el sistema mientras no se lea la real de la cuenta.
USDM_MAKER, USDM_TAKER = USDM_FEES[0]
