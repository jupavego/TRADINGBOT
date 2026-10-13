"""Parámetros del agente `context`."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ContextParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_headlines: int = 40  # titulares enviados al LLM (los más recientes)
    max_title_chars: int = 240  # recorte de cada titular
    max_age_hours: int = 48  # titulares más viejos se ignoran
    min_headlines: int = 3  # por debajo → no_data
    min_valid_claims: int = 1  # catalizadores con fuente válida mínimos para status ok
    max_confidence: float = 0.6
    # multiplicador de confianza global que sugiere el contexto según el riesgo de evento
    confidence_multiplier: dict[str, float] = {"bajo": 1.0, "medio": 0.8, "alto": 0.5}
    horizon_bars: int = 24
    # patrones de instrucciones inyectadas: el titular se excluye del prompt y se avisa
    injection_patterns: tuple[str, ...] = (
        r"ignor(e|a|ar)\s+(all|todas?|las|the|previous|prior|anteriores?)",
        r"(system|developer|assistant)\s*(prompt|message|:)",
        r"(instrucciones|instructions)\s+(anteriores|previous|previas)",
        r"\byou\s+(are|must|should)\s+now\b",
        r"\b(ahora\s+eres|debes\s+(responder|ignorar|ejecutar))\b",
        r"\b(execute|ejecuta|place\s+(an?\s+)?order|abre\s+(una\s+)?(posici|operaci))",
        r"<\s*/?\s*(system|tool|headline|instructions?)\b",
    )
