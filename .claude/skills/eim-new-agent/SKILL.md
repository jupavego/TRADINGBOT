---
name: eim-new-agent
description: Checklist y plantilla para crear un agente analizador EIM (paquete, params, tests, registro). Úsalo al implementar cualquier agente nuevo en eim/agents/.
---

# Crear un agente EIM

Todo el código nuevo vive en `v2/` (rutas `eim/`, `tests/` relativas a `v2/`).

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
7. **Catálogo del observatorio (T72):** registrar el componente en `eim/observability/catalog/`
   (`components_agents.py`): `id` `agent.<nombre>`, misma `version`, `stage`, `cadence`,
   `consumes`/`produces` (qué recibe y qué entrega, con el id del componente de origen),
   `title_es` y `explain_es` (1–2 frases llanas, ≤ 280 caracteres). Si estaba `planeado`, pasarlo a
   `construido`. El test `tests/observability/test_catalog.py` lo exige. El agente sigue puro: no
   emite eventos (los emite el corredor).
8. **Capacidades (T91):** ficha en `eim/agents/capabilities.py` (datos, no lógica): clases de
   activo, `requires`/`requires_any` (su unión = `agent.requires`), marcos, `min_bars` (el mismo
   del agente), historia mínima en días, modelos de sesión (24/7 · 24/5 · bolsa), necesidad de
   volumen (`ninguno` · `opcional` · `preferible` · `obligatorio`), ancla temporal, horizonte y
   costo medido (`scripts/agents_cost.py`). Si el agente supone 24/7 o volumen real, ese supuesto
   va en `params.py` con el valor actual por defecto y su adaptación en `eim/agents/adapt.py`.
   `tests/agents/test_capabilities.py` falla si falta la ficha o si no cuadra con el agente.
9. Gate (desde `v2/`): `python -m ruff check eim tests && python -m pytest -q`.

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
