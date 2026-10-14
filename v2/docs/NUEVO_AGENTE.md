# Añadir un agente analizador

Con Claude Code: abre una sesión en el repo y pide la tarea; la skill **`eim-new-agent`**
(`.claude/skills/eim-new-agent/SKILL.md`) se carga sola al crear un agente y trae checklist y
plantilla. Esta guía es el mismo procedimiento para hacerlo a mano y lo que viene después.

## 1. Contrato
`Agent.run(MarketSnapshot) -> AgentReport` (`PLAN/CONTRATOS.md`, tipos en `eim/core`).
- `bias` ∈ [−1, +1], `confidence` ∈ [0, 1], `horizon_bars`, `evidence`, `metrics`, `warnings`, `overlays`.
- `status`: `ok` · `degraded` (datos parciales: di la cobertura real) · `no_data` (bias 0, confianza 0).
- **Puro:** sin red, sin disco, sin estado global, determinista. Lo que necesite de fuera entra por
  el snapshot; si el snapshot no lo trae, se añade en `eim/data/` (proveedor + `build_snapshot`).
- Nunca presentar datos asumidos como reales: cada cifra con su `source`.

## 2. Pasos
1. Paquete `eim/agents/<id>/`: `__init__.py`, `agent.py`, `params.py` (y `compute.py` si el cálculo
   es largo). Cada archivo ≤ 300 líneas. Identificadores en inglés, docstrings en español.
2. `params.py`: modelo pydantic `frozen` con todos los umbrales/ventanas (nada mágico en `agent.py`).
3. `agent.py`: clase con `id`, `version` (semver), `requires` (campos del snapshot) y `run`.
   Plantilla en la skill.
4. Registro: añadirlo a `default_registry()` en `eim/agents/registry.py`.
5. Tests en `tests/agents/<id>/` con fixtures en `tests/fixtures/` (sin red): caso normal, sin
   datos, datos parciales, determinismo (dos corridas iguales), sesgo en rango. Si migra lógica del
   legado: regresión contra `tests/fixtures/golden/` (ver `legacy/README.md`).
6. Gate: `python -m ruff check eim tests && python -m pytest -q`.
7. UI (opcional): overlays con `id` estable; panel en `eim/web/src/` según `PLAN/UI_SPEC.md`.
   Verificar inspeccionando los datos renderizados o con captura, no solo «sin errores».

## 3. Después: ¿vota en la síntesis o en el plan?
Un agente nuevo **no gana peso por existir**. Hoy el plan solo usa `structure` + `levels`
(calibrados en T26) y la síntesis pondera con `eim/synthesis/params.py`.
Para darle voto:
1. Medir su poder predictivo fuera de muestra (IC de rango sesgo→retorno a varios horizontes; ver
   `reports/technical_ic.md` como ejemplo) frente a costos (≈0.3 R/operación, T27).
2. Si supera el azar con validación anidada, calibrar su peso (T26) y pasar la puerta de edge (T27)
   con criterios fijados antes de calcular.
3. Si no: se queda como contexto en la UI (BACKLOG T35 (1) es el precedente).

## 4. Cambiar un agente existente
Si cambia la salida → sube `version`. El registro admite varias versiones; `get(id)` usa la más
reciente y los reportes guardados conservan la versión que los produjo.
