# Código de terceros en EIM v2

| Origen | Licencia | Qué se usa | Dónde |
|---|---|---|---|
| [hummingbot/hummingbot](https://github.com/hummingbot/hummingbot) `9af100d6822da7d2d0291a906c730ef172284ee2` (`controllers/directional_trading/bollinger_v1.py`, `macd_bb_v1.py`) | Apache-2.0 | La **regla** de cada controlador (condiciones de %B y MACD), reimplementada con `eim.indicators`; sin el framework ni `pandas-ta`. | `eim/bots/hb_directional.py`; el generador de paridad `tests/fixtures/bots/make_hummingbot_parity.py` repite las líneas de `update_processed_data` para producir el fixture (se corre a mano en un entorno aparte con `pandas-ta`; no es dependencia de EIM). |
| [freqtrade/freqtrade-strategies](https://github.com/freqtrade/freqtrade-strategies) `f3340ce11f5bdf62f598522e64d1f5638eaa13f5` y [freqtrade](https://github.com/freqtrade/freqtrade) | GPL-3.0 | **Nada se copia ni se importa desde `eim/`**: las estrategias corren en un proceso aislado de un entorno aparte (modo B), uso privado sin distribución. | `eim/bots/ft_adapter.py`, `eim/data/bots/` |

Regla (T56): licencia permisiva → se puede portar anotando el origen aquí; GPL/AGPL → solo modo B (proceso aislado, sin importar su código).
