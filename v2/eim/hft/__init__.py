"""Carril HFT (Fase 16): estadística del banco de latencia (T77) y cota de costos.

El riesgo y la ejecución del carril (T83) viven donde los de los demás carriles:
`eim/risk/hft_*.py` (veto determinista por orden) y `eim/execution/hft_*.py`, `user_stream*.py`,
`binance_ws_api.py`. Simulador, señales y estrategias llegan en T79–T82; el servicio, en T85.
"""
