"""Capa de motores de IA locales (T63): LLM, ASR, OCR, visión-lenguaje y embeddings.

Una sola puerta (`LocalAI`) por la que cualquier parte del proyecto usa motores de código
abierto en local. El motor es intercambiable (configuración `EIM_LOCALAI_*`), medible (registro
`localai_calls`) y auditable (cada salida trae motor, modelo, SHA de los pesos, parámetros y
tiempo). Nunca decide: los LLM solo informan. Todo el I/O de motores vive aquí y en `data/`;
los agentes siguen siendo puros.
"""

from eim.localai.engines import (
    ASREngine,
    EmbedEngine,
    EngineDown,
    EngineRefused,
    LLMEngine,
    OCREngine,
    VisionEngine,
)
from eim.localai.facade import LocalAI
from eim.localai.results import EngineResult, OCRLine, Provenance, Segment

__all__ = ["ASREngine", "EmbedEngine", "EngineDown", "EngineRefused", "EngineResult", "LLMEngine",
           "LocalAI", "OCREngine", "OCRLine", "Provenance", "Segment", "VisionEngine"]
