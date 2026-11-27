"""Cadena sintética con forma de respuesta de Deribit para las pruebas de T213 (sin red).

Los precios salen de Black-76 con una sonrisa conocida y se pasan a la moneda base dividiendo
por el subyacente, como cotiza Deribit. **No son cifras reales**: sirven para comprobar
unidades, descartes y calidad. Lo real está en `fixtures/options/` (recorte grabado).
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from eim.data.providers.deribit import DeribitPublic
from eim.options import black_scholes as bs

T0 = int(datetime(2026, 11, 27, 14, 1, tzinfo=UTC).timestamp() * 1000)
F = 90_000.0                                          # subyacente sintético del vencimiento
EXPIRY_NAME, EXPIRY = "25DEC26", int(datetime(2026, 12, 25, 8, tzinfo=UTC).timestamp() * 1000)
T_YEARS = (EXPIRY - T0) / (365 * 86_400_000)


def smile(k: float) -> float:
    m = k / F - 1
    return 0.50 + 0.6 * m * m - 0.20 * m


def raw_chain(width: float = 0.02, strikes=range(60_000, 125_000, 5_000)) -> list[dict]:
    out = []
    for k in strikes:
        for cp, kind in (("C", "call"), ("P", "put")):
            usd = bs.black76(F, k, T_YEARS, 0.0, smile(k), kind)
            px = usd / F
            out.append({
                "instrument_name": f"BTC-{EXPIRY_NAME}-{k}-{cp}",
                "bid_price": round(px * (1 - width / 2), 8),
                "ask_price": round(px * (1 + width / 2), 8),
                "mid_price": round(px, 8), "mark_price": round(px, 8),
                "mark_iv": round(smile(k) * 100, 4), "underlying_price": F,
                "underlying_index": f"BTC-{EXPIRY_NAME}", "interest_rate": 0.0,
                "open_interest": 12.5, "volume": 3.0, "creation_timestamp": T0 - 500,
                "base_currency": "BTC", "quote_currency": "BTC",
            })
    return out


def provider_for(rows_or_handler, *, now: int = T0) -> DeribitPublic:
    """Proveedor con transporte falso: devuelve `rows` como `result` o usa el manejador dado."""
    if callable(rows_or_handler):
        handler = rows_or_handler
    else:
        def handler(_r: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"jsonrpc": "2.0", "result": rows_or_handler})
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://deribit.test")
    return DeribitPublic(client, clock=lambda: now, sleep=lambda _s: None, min_interval=0.0)
