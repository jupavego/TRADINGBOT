# T25 — Decisión de motor de backtest

**Decisión: motor propio (`v2/eim/backtest/engine.py`, ~200 líneas) en lugar de NautilusTrader.**

## Prueba mínima de integración con NautilusTrader (2026-10-13)
- `pip install nautilus_trader` (1.231.0, wheel nativo Windows/Py3.12) funciona: ~550 MB instalados.
- `from nautilus_trader.backtest.engine import BacktestEngine; BacktestEngine(BacktestEngineConfig())` arranca y se cierra sin errores (instalado en un directorio corto aparte; en una ruta larga falla la carga de DLL en Windows).
- Se instaló fuera del proyecto: NO se añadió a `pyproject.toml`.

## Por qué propio
1. **Paridad con T30 sin dependencia pesada:** la estrategia es `Strategy.on_bar(MarketSnapshot) -> Signal`, el mismo contrato que usará la ejecución en testnet; el motor solo decide cuándo y a qué precio se llena.
2. **Reglas del plan, explícitas y testeables:** ejecución en la apertura siguiente, SL antes que TP en la misma vela, funding cada 8 h, liquidación aislada — cada una cabe en pocas líneas y tiene test. En Nautilus habría que escribir un `FillModel`/`FeeModel`/funding a medida sobre una API en transición (`MIGRATION_V2.md`).
3. **Coste:** 550 MB, núcleo Rust/Cython, LGPL-3.0 (T04). Para velas OHLC de un solo instrumento no aporta lo que justifica ese peso.
4. **Reevaluar** si T30 necesita el ciclo de vida de órdenes completo (parciales, libro): Nautilus seguiría siendo candidato y la interfaz `Strategy` se adaptaría con un envoltorio fino.

## Supuestos conservadores del simulador (ver docstrings)
- Señal al cierre de `j` → llenado a la apertura de `j+1` (taker, con deslizamiento); nunca en la misma vela.
- SL y TP en la misma vela → SL; hueco de apertura más allá del SL → se llena a la apertura.
- TP = orden límite (maker, sin deslizamiento); SL/tiempo/fin = taker con deslizamiento.
- Deslizamiento = base + k·rango relativo de la vela + k·(notional / notional negociado en la vela).
- Funding: tasas reales del almacén en cada liquidación posterior a la entrada; si faltan se asume 0 y el informe lo advierte.
- Liquidación (margen aislado): precio `entry·(1 ∓ (1/lev − mmr))`; se pierde el margen, nunca más. Mantenimiento fijo (tramo bajo); no modela tramos de margen por tamaño.
- Intra-vela solo se conocen OHLC: el orden real de los extremos es desconocido, de ahí las reglas pesimistas.
