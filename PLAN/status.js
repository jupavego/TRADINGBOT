window.EIM_STATUS = {
 "generated": "2026-10-12T23:34:49",
 "tasks": [
  {
   "id": "T01",
   "title": "Cimientos: paquete, contratos, git, gate",
   "deps": [],
   "state": "done",
   "notes": "v2/eim/core (contratos pydantic) + v2/tests/core; pyproject, .gitignore, skill eim-new-agent. Gate OK (12 tests).",
   "effort": "medio",
   "phase": 0,
   "goal": "Crear el esqueleto del paquete `eim/` con los contratos de datos y un gate de calidad, sin tocar `F7/`."
  },
  {
   "id": "T02",
   "title": "Red de seguridad: regresión del legado",
   "deps": [
    "T01"
   ],
   "state": "done",
   "notes": "v2/tests/legacy (_runner, generate_golden, test_golden) + golden JSON en v2/tests/fixtures/golden (no parquet: sin pyarrow y *.parquet está en .gitignore) + fixture ethusdt_1h_1000.csv. Cubiertos: FRM, BRM, IRM, VWAP (día/semana/quincena/mes + anclado), price action (+zonas S/R), Elliott, estacionalidad (con cierres mensuales sintéticos: el CSV cubre ~6 semanas). NO cubiertos: eim_engine (orquesta feed de red; su pipeline FRM→BRM→IRM sí), eim_liquidations/market_data/data/web/bitacora (requieren red/estado). Tolerancia rtol/atol 1e-9; umbral θ-001 alterado en copia (EIM_LEGACY_DIR) hace fallar el test. Gate OK (19 tests).",
   "effort": "medio",
   "phase": 0,
   "goal": "Congelar el comportamiento actual de F7 (ya corregido en sesiones previas) con \"golden outputs\", para migrar sin regresiones."
  },
  {
   "id": "T03",
   "title": "Capa de datos y almacén",
   "deps": [
    "T01"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio",
   "phase": 0,
   "goal": "Proveedores de datos con interfaz común y un almacén local (DuckDB/Parquet) que alimente `MarketSnapshot` sin que los agentes toquen red ni disco."
  },
  {
   "id": "T04",
   "title": "Auditoría de repos (licencia/seguridad)",
   "deps": [],
   "state": "pending",
   "notes": "",
   "effort": "medio",
   "phase": 0,
   "goal": "Decidir qué se puede reciclar y cómo, sin riesgo legal ni de seguridad."
  },
  {
   "id": "T05",
   "title": "Runner de agentes + agente structure",
   "deps": [
    "T01",
    "T02",
    "T03"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 1,
   "goal": "Registro y ejecutor de agentes, y migrar el motor EIM (FRM→BRM→IRM) como agente `structure` sin cambiar su comportamiento."
  },
  {
   "id": "T06",
   "title": "Agentes VWAP + price action",
   "deps": [
    "T05"
   ],
   "state": "pending",
   "notes": "",
   "effort": "bajo-medio",
   "phase": 1,
   "goal": "Migrar `eim_vwap.py` y `eim_price_action.py` a agentes puros con la interfaz común."
  },
  {
   "id": "T07",
   "title": "Agentes Elliott + estacionalidad + liquidaciones",
   "deps": [
    "T05"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio",
   "phase": 1,
   "goal": "Migrar `eim_elliott.py`, `eim_seasonality.py` y `eim_liquidations.py` a la interfaz de agentes/datos."
  },
  {
   "id": "T08",
   "title": "API v2 (REST + WebSocket + persistencia)",
   "deps": [
    "T05"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio",
   "phase": 2,
   "goal": "Servidor FastAPI que expone snapshots, reportes de agentes y un canal en vivo, y persiste cada reporte."
  },
  {
   "id": "T09",
   "title": "Frontend base + gráfico de velas en vivo",
   "deps": [
    "T08"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio",
   "phase": 2,
   "goal": "Proyecto Vite + TypeScript con la \"Mesa de trading\" base: layout, tema claro/oscuro y gráfico de velas en tiempo real."
  },
  {
   "id": "T10",
   "title": "Panel de agentes + síntesis (UI)",
   "deps": [
    "T09"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio",
   "phase": 2,
   "goal": "Columna derecha con una tarjeta por agente y un panel de síntesis, actualizados en vivo. **Punto de decisión humana al cerrar:** ¿la interfaz sirve?"
  },
  {
   "id": "T11",
   "title": "Portar pestañas legadas",
   "deps": [
    "T10"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio",
   "phase": 2,
   "goal": "Llevar a la UI nueva lo que aún solo existe en `F7/web/index.html`: Backtest/VRM, Bitácora de trading, Multi-activo, Liquidaciones, Estacionalidad, VWAP por periodos."
  },
  {
   "id": "T12",
   "title": "Agente de niveles (S/R, canal, rango)",
   "deps": [
    "T05"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 3,
   "goal": "Agente puro que detecta zonas de soporte/resistencia y el canal o rango vigente, y los emite como overlays."
  },
  {
   "id": "T13",
   "title": "Agente de plan (entrada/SL/TP/R:R)",
   "deps": [
    "T12"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 3,
   "goal": "Agente que, a partir de los niveles y la síntesis disponible, propone un plan de operación analítico: dirección, entrada, SL, TP1/TP2 y relación riesgo/beneficio."
  },
  {
   "id": "T14",
   "title": "Capas sobre el gráfico + hover de evidencia",
   "deps": [
    "T09",
    "T12",
    "T13"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio-alto",
   "phase": 3,
   "goal": "Dibujar en el gráfico en tiempo real lo que marca el agente: canal/rango, zonas de soporte y resistencia, y el plan (entrada, SL, TP1, TP2)."
  },
  {
   "id": "T15",
   "title": "Marcas de operaciones + bitácora + reproducción",
   "deps": [
    "T14"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio",
   "phase": 3,
   "goal": "Ver cómo \"opera\" el agente en el gráfico (en modo simulado) y poder reproducir sus decisiones pasadas."
  },
  {
   "id": "T16",
   "title": "Proyección: trayectorias OHLC (base + Kronos opc.)",
   "deps": [
    "T03",
    "T05"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 4,
   "goal": "Generar muchas trayectorias futuras de velas OHLC (20–30 velas) desde el precio actual, con un motor base estadístico y, opcionalmente, Kronos."
  },
  {
   "id": "T17",
   "title": "Escenarios (3, probabilidad, invalidación) + API",
   "deps": [
    "T16",
    "T08"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio-alto",
   "phase": 4,
   "goal": "Convertir las trayectorias en exactamente tres escenarios (alcista, neutral, bajista) con probabilidad, banda, secuencia de velas representativa y condición de invalidación; exponerlos por API."
  },
  {
   "id": "T18",
   "title": "Escenarios sobre el gráfico (+ toggle velas)",
   "deps": [
    "T09",
    "T17"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio-alto",
   "phase": 4,
   "goal": "Dibujar los tres escenarios desde el punto actual y permitir ver cada uno como secuencia de velas."
  },
  {
   "id": "T19",
   "title": "Seguimiento y calibración de escenarios",
   "deps": [
    "T17",
    "T18"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio",
   "phase": 4,
   "goal": "Medir si las probabilidades y bandas de los escenarios son fiables, y mostrarlo."
  },
  {
   "id": "T20",
   "title": "Síntesis v1",
   "deps": [
    "T06",
    "T07",
    "T12"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio",
   "phase": 5,
   "goal": "Combinar los reportes de los agentes en una tesis con sesgo, confianza y nivel de acuerdo, y alimentar con ella al plan y a la proyección."
  },
  {
   "id": "T21",
   "title": "Agente de derivados (funding/OI/basis)",
   "deps": [
    "T03",
    "T05"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio",
   "phase": 5,
   "goal": "Agente que lee funding, open interest y (si hay) basis/long-short ratio y emite sesgo y advertencias de apalancamiento extremo."
  },
  {
   "id": "T22",
   "title": "Agente de régimen (BOCPD + transición)",
   "deps": [
    "T05"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio-alto",
   "phase": 5,
   "goal": "Detectar cambios de régimen (tendencia/rango/alta volatilidad) y validar que el esquema de regímenes es estable y no ruido."
  },
  {
   "id": "T23",
   "title": "Microestructura: recolector + agente OFI",
   "deps": [
    "T03",
    "T05"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 5,
   "goal": "Recolectar trades y order book en vivo y calcular order flow imbalance (OFI), CVD y volatilidad realizada."
  },
  {
   "id": "T24",
   "title": "Agente de contexto (LLM)",
   "deps": [
    "T05"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio",
   "phase": 5,
   "goal": "Un agente que lee noticias/sentimiento/calendario y devuelve contexto estructurado. **Solo informa; nunca ejecuta ni fija tamaño.**"
  },
  {
   "id": "T25",
   "title": "Backtest con costos de perpetuos",
   "deps": [
    "T13",
    "T20"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 6,
   "goal": "Evaluar la estrategia completa (agentes → síntesis → plan) con costos y mecánica reales de futuros perpetuos, sin sesgo de anticipación."
  },
  {
   "id": "T26",
   "title": "Calibración (optuna, walk-forward)",
   "deps": [
    "T25"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio-alto",
   "phase": 6,
   "goal": "Calibrar umbrales θ, pesos de síntesis y parámetros del plan sin sobreajustar. Salda la deuda pendiente del VRM (Fase VI)."
  },
  {
   "id": "T27",
   "title": "Puerta de edge (informe de decisión)",
   "deps": [
    "T26",
    "T19"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio",
   "phase": 6,
   "goal": "Responder con evidencia: ¿el sistema tiene ventaja estadística fuera de muestra, neta de costos? De la respuesta depende seguir a T29 o volver atrás."
  },
  {
   "id": "T28",
   "title": "(Opcional) Laboratorio ESN con conectoma",
   "deps": [
    "T27"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio",
   "phase": 6,
   "goal": "Probar si un Echo State Network con reservorio basado en el conectoma de Drosophila mejora la proyección frente a un ESN aleatorio y a los motores de T16. Evidencia previa: resistencia al sobreajuste en series caóticas (no financieras); la única prueba financiera encontrada fue negativa."
  },
  {
   "id": "T29",
   "title": "Motor de riesgo (veto determinista)",
   "deps": [
    "T27"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 7,
   "goal": "Capa determinista que decide tamaño y puede vetar cualquier plan. Ningún LLM ni agente puede saltársela."
  },
  {
   "id": "T30",
   "title": "Ejecución en testnet + reconciliación",
   "deps": [
    "T29"
   ],
   "state": "pending",
   "notes": "",
   "effort": "alto",
   "phase": 7,
   "goal": "Adaptador de ejecución para Binance Futures **testnet**, con la misma interfaz que el simulador, y reconciliación de posición."
  },
  {
   "id": "T31",
   "title": "Paper trading + kill-switch + monitoreo",
   "deps": [
    "T30"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio",
   "phase": 7,
   "goal": "Operar de forma continua en testnet/paper durante semanas con monitoreo y alertas, y producir la evidencia para decidir si se pasa a capital real."
  },
  {
   "id": "T32",
   "title": "Endurecimiento y documentación",
   "deps": [
    "T31"
   ],
   "state": "pending",
   "notes": "",
   "effort": "medio",
   "phase": 7,
   "goal": "Dejar el sistema mantenible y seguro."
  }
 ]
};
