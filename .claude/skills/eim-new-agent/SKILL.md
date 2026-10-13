---
name: eim-new-agent
description: Checklist y plantilla para crear un agente analizador EIM (paquete, params, tests, registro). Úsalo al implementar cualquier agente nuevo en eim/agents/.
---

# Crear un agente EIM

Contrato: `Agent.run(MarketSnapshot) -> AgentReport` (ver `PLAN/CONTRATOS.md`). Puro: sin red, sin disco, sin estado global, determinista.

## Checklist
1. Paquete `eim/agents/<nombre>/` con `__init__.py`, `agent.py`, `params.py` (cada archivo ≤ 300 líneas).
2. `params.py`: modelo pydantic frozen con todos los umbrales/ventanas (nada mágico en `agent.py`).
3. `agent.py`: clase con `id`, `version`, `requires` (campos del snapshot) y `run`.
   - Faltan datos requeridos → `status="no_data"`, `bias=0`, `confidence=0`, con `warnings`.
   - Datos parciales → `status="degraded"` y advertencia con la cobertura real.
   - Cada cifra relevante en `metrics`/`evidence` con su fuente; nunca datos asumidos como reales.
4. Overlays con `id` estable, `agent_id`, `confidence` y `evidence`.
5. Tests en `tests/agents/<nombre>/` con fixtures en `tests/fixtures/` (sin red): caso normal, sin datos, determinismo (dos corridas iguales), sesgo en [-1,1].
6. Registro: añadir al registro de agentes (T05) indicando la versión.
7. Gate: `python -m ruff check eim tests && python -m pytest -q`.

## Plantilla
```python
from eim.agents.<nombre>.params import Params
from eim.core import AgentReport, MarketSnapshot


class <Nombre>Agent:
    id = "<nombre>"
    version = "0.1.0"
    requires = {"candles"}

    def __init__(self, params: Params | None = None) -> None:
        self.params = params or Params()

    def run(self, snapshot: MarketSnapshot) -> AgentReport:
        if len(snapshot.candles) < self.params.min_bars:
            return AgentReport(
                agent_id=self.id, version=self.version, asof=snapshot.asof,
                bias=0, confidence=0, horizon_bars=0, status="no_data",
                warnings=["velas insuficientes"],
            )
        ...
```
