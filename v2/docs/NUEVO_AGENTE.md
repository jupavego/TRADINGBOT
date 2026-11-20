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
6. **Catálogo del observatorio (T72):** añadir el agente (o servicio) a `eim/observability/catalog/`
   (`components_agents.py` para agentes; `components_flow.py` para servicios) con `id`
   `agent.<id>`, `version` igual a la del agente, `stage`, `cadence`, **qué consume y qué produce**
   (`consumes=((origen, artefacto), …)`, `produces=(…)`) y los textos `title_es` y `explain_es`
   (1–2 frases llanas, ≤ 280 caracteres: qué hace, qué recibe, qué entrega). Si ya figuraba como
   `planeado`, pasarlo a `construido`. `tests/observability/test_catalog.py` falla si falta o si
   la versión no coincide. El agente **no emite eventos**: es puro; el corredor lo instrumenta (T74).
   Un servicio nuevo en segundo plano llama `hooks_service.beat("<id>")` en cada vuelta y
   `hooks_service.service_error` al fallar (`eim/observability/hooks_service.py`) y fija su nombre
   de proceso con `configure(process=…)` al arrancar.
7. Gate: `python -m ruff check eim tests && python -m pytest -q`.
8. UI (opcional): overlays con `id` estable; panel en `eim/web/src/` según `PLAN/UI_SPEC.md`.
   Verificar inspeccionando los datos renderizados o con captura, no solo «sin errores».

## 2 bis. Un instrumento nuevo se REGISTRA, no se codifica (T89)
Desde la fase 17 ningún archivo nuevo vuelve a escribir `"BTCUSDT"` ni ninguna lista de símbolos.
El catálogo único es `eim/instruments/`:

- **Alta:** si es de una fuente que ya se descubre (los USDⓈ-M de Binance), sale sola con
  `python -m eim.instruments --data-dir data discover`. Si no, una ficha en
  `eim/instruments/registry.py` (semilla) y, si hace falta, un mapeo **puro** en `discovery.py`.
  Nunca una constante en el módulo que lo usa.
- **Resolver:** `store.resolve("BTCUSDT")`, `"SP500"` o el id completo — símbolo nativo y alias
  legado siguen siendo identificadores válidos. `SYMBOLS` y `FOCUS` de `eim/data/timeframes.py`
  se derivan del registro; cambiar el foco se hace ahí, no en 73 importadores.
- **Capacidades:** un agente declara qué datos necesita y el registro dice si existen
  (`Instrument.has(...)`). Si falta uno, el agente **no corre**: `no_data` con motivo, nunca un
  número silencioso. Es la regla del punto 4 de la lista aprobada en T87 y la implanta T91;
  el caso medido fue `vwap` publicando `ok` con confianza 0,60 y un ancla muerta en el S&P 500.
- **Tiempo:** nada supone 24/7. `eim/instruments/calendars.py` dice si estaba abierto
  (`is_open`), cuántas velas debería haber (`expected_bars`) y, ante un hueco, si fue «cerrado» o
  «sin datos» (`classify_absence`). Un instrumento puede tener **dos** calendarios: el del
  contrato y el del subyacente (un perpetuo TradFi de Binance no cierra aunque CME sí).
- **Permiso:** `tradable_level` (1 investigación · 2 operativa · 3 ejecución) es el límite escrito
  de la ◆ de T88. Una tarea que vaya a publicar un veredicto pide `min_level=2` en la consulta.

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

**Bots de terceros**: no se añaden como agente propio; pasan por el escuadrón (`docs/BOTS.md`: ficha → adaptador → paridad → puerta). El agente `bots` los consolida y la política de `eim/synthesis/squad.py` decide, con el aporte marginal medido en T59, quién vota y con qué peso.
