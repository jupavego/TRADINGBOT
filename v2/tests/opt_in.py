"""Variables que activan a propósito una prueba opcional (T116): no son estado del equipo.

`tests/conftest.py` retira del entorno todas las variables `EIM_*` del equipo antes de importar
ninguna prueba. Las de esta lista no cambian el resultado de ninguna otra prueba: activan las
pruebas opcionales que corren el motor de verdad (`docs/BOTS.md`, reciben la ruta por argumento)
o la comprobación de sensibilidad del golden (`legacy/README.md`). Se copian aquí antes de la
limpieza para que sigan pudiendo activarse.
"""

from __future__ import annotations

import os

ENGINE_VARS = ("EIM_BOT_FREQTRADE_PY", "EIM_BOT_FREQTRADE_DIR",
               "EIM_BOT_PASSIVBOT_PY", "EIM_BOT_PASSIVBOT_DIR")
KNOB_VARS = ("EIM_LEGACY_DIR",)
OPT_IN = {k: os.environ[k] for k in ENGINE_VARS + KNOB_VARS if os.environ.get(k)}
