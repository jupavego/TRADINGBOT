"""Los tests no escriben eventos del observatorio en `data/obs/spool` (T74).

`EIM_OBS=off` por defecto; los tests de `tests/observability/` lo encienden con su propia
carpeta temporal (`conftest.py` de esa carpeta).
"""
from __future__ import annotations

import os

os.environ.setdefault("EIM_OBS", "off")
os.environ.pop("ANTHROPIC_API_KEY", None)  # la suite nunca llama al LLM real
