"""Catálogo: el flujo central (datos → proyección → síntesis → riesgo → ejecución).

Construido leyendo `eim/data`, `eim/forecast`, `eim/synthesis`, `eim/risk`, `eim/execution` y
`eim/operation` (tareas indicadas en cada fila; estado real en `PLAN/STATUS.md`).
"""

from __future__ import annotations

from eim.observability.catalog.components_agents import AGENTS
from eim.observability.catalog.model import Component, c

_VOTERS = ("structure", "ema", "vwap", "price_action", "elliott", "seasonality", "liquidations",
           "levels", "derivatives", "microstructure", "regime", "technical", "smart_money")

DATA: tuple[Component, ...] = (
    c("data.binance_rest", "data", "datos", "provider", "api", "T03", "Binance (consulta REST)",
      "Pide a Binance, sin claves, velas, funding e interés abierto. Es la fuente de precios del "
      "análisis; si falla, el análisis queda degradado.", cadence="cada ciclo (60 s)",
      cadence_s=60, produces=("candles", "funding", "open_interest")),
    c("data.live_ticks", "data", "datos", "provider", "api", "T09", "Precio en vivo",
      "Recibe por WebSocket el precio de Binance casi en tiempo real para mover el gráfico cada "
      "segundo. No alimenta a los agentes: ellos usan velas cerradas.", cadence="continuo",
      cadence_s=5, produces=("ticks",)),
    c("data.store", "data", "datos", "store", "api", "T03", "Almacén de velas",
      "Guarda las velas y el funding en el disco del equipo y detecta huecos. Recibe lo que "
      "pide Binance y lo entrega ordenado al snapshot.", cadence="cada ciclo (60 s)",
      cadence_s=60, consumes=(("data.binance_rest", "candles"), ("data.binance_rest", "funding")),
      produces=("candles", "funding")),
    c("data.liquidations", "data", "datos", "provider", "api", "T07", "Liquidaciones",
      "Descarga el archivo público de liquidaciones forzadas de Binance. Lo entrega al snapshot "
      "para que el agente de liquidaciones lo lea.", cadence="a demanda", produces=("liquidations",)),
    c("data.news", "data", "datos", "provider", "api", "T24", "Titulares de noticias",
      "Lee titulares por RSS. El texto es dato externo, nunca una instrucción; solo sirve de "
      "materia prima al agente de contexto.", cadence="a demanda", produces=("headlines",)),
    c("data.calendar", "data", "datos", "service", "api", "T36", "Calendario oficial",
      "Consulta Fed, BLS y BEA cada 6 horas y guarda las fechas de publicaciones. Si la fuente "
      "no da el consenso, queda vacío: no se inventa.", cadence="cada 6 h", cadence_s=21600,
      produces=("econ_events",)),
    c("data.micro_collector", "data", "datos", "service", "collector", "T23", "Recolector de órdenes",
      "Proceso aparte que escucha operaciones y libro de órdenes de Binance y los guarda por hora "
      "en el disco. Alimenta al agente de flujo de órdenes.", cadence="continuo", cadence_s=3600,
      produces=("micro_bars",)),
    c("data.arb_market", "arbitrage", "datos", "service", "api", "T39", "Mercado para arbitraje",
      "Cada ~10 s toma una fotografía de precios spot y futuros de Binance (solo lectura) para "
      "buscar diferencias que dejen ganancia neta.", cadence="cada 10 s", cadence_s=10,
      produces=("arb_market",)),
    c("leaders.service", "leaders", "datos", "service", "leaders", "T41", "Líderes de Hyperliquid",
      "Proceso aparte que sigue a los traders públicos mejor evaluados y escribe un tablero cada "
      "5 minutos. Solo lee datos públicos; sin claves.", cadence="cada 5 min", cadence_s=300,
      produces=("leader_board",)),
    c("data.snapshot", "data", "datos", "engine", "api", "T03", "Fotografía del mercado",
      "Reúne velas, funding, liquidaciones, noticias, calendario, flujo y líderes en un solo "
      "paquete con la fuente y la cobertura real de cada cifra. Es lo único que ven los agentes.",
      cadence="cada cierre de vela", cadence_s=3600,
      consumes=(("data.store", "candles"), ("data.store", "funding"),
                ("data.binance_rest", "open_interest"),
                ("data.liquidations", "liquidations"), ("data.news", "headlines"),
                ("data.calendar", "econ_events"), ("data.micro_collector", "micro_bars"),
                ("data.arb_market", "arb_market"), ("leaders.service", "leader_board")),
      produces=("snapshot",)),
)

FLOW: tuple[Component, ...] = (
    c("forecast.engine", "forecast", "proyeccion", "engine", "api", "T17", "Escenarios probables",
      "Simula muchas trayectorias de precio y las resume en tres escenarios (alcista, neutral, "
      "bajista) con probabilidad y bandas. Nunca una línea única.", cadence="cada cierre de vela",
      cadence_s=3600, consumes=(("data.snapshot", "snapshot"),), produces=("forecast_set",)),
    c("synthesis.thesis", "synthesis", "analisis", "engine", "api", "T20", "Opinión conjunta",
      "Pondera la opinión de los analistas según su confianza y resta fuerza si discrepan. "
      "Entrega una tesis con su desacuerdo; calendario y arbitraje no votan.",
      cadence="cada cierre de vela", cadence_s=3600,
      consumes=tuple((f"agent.{a}", "agent_report") for a in _VOTERS), produces=("synthesis",)),
    c("risk.killswitch", "risk", "riesgo", "gate", "api", "T29", "Interruptor de emergencia",
      "Estado global que bloquea órdenes nuevas y pide cerrar lo abierto. Se activa a mano o por "
      "pérdida máxima; ningún otro componente puede saltárselo.", produces=("kill_switch_state",)),
    c("risk.engine", "risk", "riesgo", "gate", "api", "T29", "Motor de riesgo",
      "Código fijo, sin opinión, que revisa cada plan: tamaño por riesgo, apalancamiento, "
      "calendario y pérdida diaria. Aprueba, ajusta o veta, y firma la decisión.",
      cadence="cada plan", consumes=(("agent.plan", "plan"), ("agent.calendar", "agent_report"),
                                      ("agent.context", "agent_report"),
                                      ("risk.killswitch", "kill_switch_state")),
      produces=("risk_decision",)),
    c("risk.journal", "risk", "riesgo", "store", "api", "T29", "Registro de decisiones",
      "Guarda cada decisión de riesgo con sus motivos y la versión de reglas usada, para poder "
      "reconstruir por qué se aprobó o vetó.", consumes=(("risk.engine", "risk_decision"),),
      produces=("risk_log",)),
    c("risk.arb_engine", "risk", "riesgo", "gate", "api", "T45", "Riesgo del arbitraje",
      "Revisa los planes de dos patas del arbitraje: tamaño, cuenta total y fallo de una pata. "
      "Mismo principio que el motor de riesgo: determinista y con veto.", cadence="cada ciclo",
      consumes=(("arbitrage.engine", "arb_scan"),), produces=("risk_decision",)),
    c("arbitrage.engine", "arbitrage", "analisis", "engine", "api", "T38", "Motor de arbitraje",
      "Calcula oportunidades netas de costos (carry de funding, base, perpetuos relacionados) "
      "sobre la fotografía del mercado de arbitraje.", cadence="cada 10 s", cadence_s=10,
      consumes=(("data.arb_market", "arb_market"),), produces=("arb_scan",)),
    c("execution.gateway", "execution", "ejecucion", "gate", "api", "T30", "Puerta única de órdenes",
      "Solo deja pasar decisiones aprobadas y selladas por el riesgo, vigentes (60 s). Una orden "
      "fabricada, vetada o vieja se rechaza.", cadence="por orden",
      consumes=(("risk.engine", "risk_decision"),), produces=("order",)),
    c("execution.service", "execution", "ejecucion", "service", "api", "T30", "Servicio de ejecución",
      "Convierte la orden aprobada en salida de pérdida, objetivo y entrada, en ese orden, y "
      "lleva el libro interno de posiciones.", cadence="por orden",
      consumes=(("execution.gateway", "order"),), produces=("order",)),
    c("execution.sim_broker", "execution", "ejecucion", "service", "api", "T30", "Exchange simulado",
      "Exchange en memoria con la misma interfaz que la testnet. Modo Simulado: ninguna orden "
      "sale del equipo.", cadence="por orden", consumes=(("execution.service", "order"),),
      produces=("fill",)),
    c("execution.testnet_broker", "execution", "ejecucion", "service", "api", "T30",
      "Testnet de Binance", "Envía órdenes a la testnet de Binance, solo a hosts de prueba y con "
      "claves sin permiso de retiro. Construido; falta la corrida completa con claves.",
      cadence="por orden", consumes=(("execution.service", "order"),), produces=("fill",)),
    c("execution.reconcile", "execution", "ejecucion", "service", "api", "T30", "Reconciliación",
      "Compara cada cierto tiempo el libro interno con el exchange y avisa si no coinciden.",
      cadence="cada ciclo", cadence_s=300,
      consumes=(("execution.sim_broker", "fill"), ("execution.testnet_broker", "fill")),
      produces=("alert",)),
    c("execution.sim_ledger", "execution", "ejecucion", "service", "api", "T15", "Libro simulado",
      "Reconstruye operaciones simuladas desde los planes guardados: entrada, salida, costos y "
      "resultado en R. Sirve para medir sin arriesgar dinero.", cadence="cada cierre de vela",
      cadence_s=3600, consumes=(("agent.plan", "plan"),), produces=("sim_trade",)),
    c("arbitrage.executor", "arbitrage", "ejecucion", "service", "api", "T45", "Ejecutor de arbitraje",
      "Abre y cierra las dos patas del arbitraje en testnet, con tiempo límite y deshaciendo si "
      "una falla. Construido; falta la prueba extremo a extremo.", cadence="cada 60 s",
      cadence_s=60, consumes=(("risk.arb_engine", "risk_decision"),), produces=("fill",)),
    c("paper.broker", "paper", "ejecucion", "service", "api", "T47", "Bróker simulado",
      "Prueba decenas de estrategias en papel, en 15 m, 1 h y 4 h, y aprende de cada pérdida. "
      "Todo es Simulado: nunca envía órdenes.", cadence="cada 60 s", cadence_s=60,
      consumes=(("data.store", "candles"),), produces=("paper_trade",)),
    c("leaders.copy_sim", "leaders", "ejecucion", "service", "leaders", "T42", "Copia simulada",
      "Una cuenta virtual copia a un líder con los costos reales para ver cuánto del resultado "
      "era copiable. Solo Simulado.", cadence="continuo", cadence_s=300,
      consumes=(("leaders.service", "leader_board"),), produces=("copy_trade",)),
)

OPERATION: tuple[Component, ...] = (
    c("operation.cycle", "operation", "ejecucion", "service", "api", "T31", "Ciclo de operación",
      "Cada minuto sincroniza velas, analiza las nuevas y decide. Si algo falla, el ciclo sigue "
      "y lo deja anotado.", cadence="cada ciclo (60 s)", cadence_s=60,
      consumes=(("data.snapshot", "snapshot"),), produces=("cycle_result",)),
    c("operation.supervisor", "operation", "ejecucion", "service", "api", "T31", "Supervisor",
      "Repite el ciclo con espera creciente si algo falla y escribe un latido que prueba que el "
      "servicio sigue vivo.", cadence="cada ciclo (60 s)", cadence_s=60,
      consumes=(("operation.cycle", "cycle_result"),), produces=("heartbeat",)),
    c("operation.watchdog", "operation", "ejecucion", "service", "watchdog", "T31", "Vigilante",
      "Proceso aparte que relanza el servicio si cae o si su latido se detiene.",
      cadence="continuo", cadence_s=60, consumes=(("operation.supervisor", "heartbeat"),),
      produces=("alert",)),
    c("operation.alerts", "operation", "ejecucion", "service", "api", "T31", "Alertas",
      "Avisa al entrar en una condición (desconexión, divergencia, pérdida) y al salir; no "
      "repite el aviso. Notificación local de Windows y panel.", cadence="cada ciclo (60 s)",
      cadence_s=60, consumes=(("operation.cycle", "cycle_result"),
                              ("operation.watchdog", "alert"), ("execution.reconcile", "alert")),
      produces=("alert",)),
    c("operation.backup", "operation", "validacion", "service", "api", "T32", "Copia diaria",
      "Una vez al día copia la base de reportes, el interruptor y las versiones de parámetros, "
      "con huellas para verificarla. Nunca copia claves.", cadence="cada día", cadence_s=86400,
      produces=("backup",)),
    c("operation.report", "operation", "validacion", "service", "api", "T31", "Informe semanal",
      "Resume la semana: operaciones, vetos, alertas y capital. Lo genera la API con los datos "
      "guardados.", cadence="cada semana", cadence_s=604800,
      consumes=(("risk.journal", "risk_log"), ("execution.sim_ledger", "sim_trade")),
      produces=("report",)),
    c("api.hub", "api", "analisis", "service", "api", "T08", "Difusor de la API",
      "Al cerrar cada vela corre los agentes y difunde el resultado por WebSocket a la interfaz. "
      "La API solo escucha en este equipo.", cadence="cada cierre de vela", cadence_s=3600,
      consumes=(("data.live_ticks", "ticks"), ("data.snapshot", "snapshot")),
      produces=("stream",)),
    c("web.dashboard", "web", "plan", "view", "web", "T10", "Panel de la interfaz",
      "Muestra al usuario el gráfico, los analistas, los escenarios y el plan, siempre con el "
      "modo (Análisis, Simulado o Testnet). Solo muestra; no opera.", cadence="en vivo",
      consumes=(("api.hub", "stream"), ("agent.plan", "plan"),
                ("forecast.engine", "forecast_set"))),
)

VALIDATION: tuple[Component, ...] = (
    c("forecast.calibration", "forecast", "validacion", "engine", "api", "T19",
      "Calibración de escenarios", "Mide si las probabilidades y bandas de los escenarios fueron "
      "fiables (puntaje de Brier, cobertura) frente a una caminata al azar.",
      cadence="a demanda", consumes=(("forecast.engine", "forecast_set"),),
      produces=("calibration",)),
    c("backtest.engine", "validation", "validacion", "engine", "cli", "T25", "Simulador histórico",
      "Repite la estrategia sobre el pasado, vela a vela y sin ver el futuro, con costos de "
      "perpetuos, funding y liquidación.", consumes=(("data.store", "candles"),),
      produces=("backtest_result",)),
    c("calibration.optimizer", "validation", "validacion", "engine", "cli", "T26", "Calibrador",
      "Busca parámetros mejores solo con datos de entrenamiento y los prueba en la ventana "
      "siguiente. Cada versión publicada es inmutable.",
      consumes=(("backtest.engine", "backtest_result"),), produces=("params_version",)),
    c("validation.edge_gate", "validation", "validacion", "gate", "cli", "T27", "Puerta de ventaja",
      "Decide con criterios fijados antes de calcular si la estrategia supera al azar tras "
      "costos. Veredicto vigente: no pasa, por eso no hay dinero real.",
      consumes=(("backtest.engine", "backtest_result"),), produces=("edge_verdict",)),
    c("validation.gate", "validation", "validacion", "gate", "api", "T49", "Puerta por estrategia",
      "Pone a prueba cada estrategia del bróker simulado con criterios inmutables y le da un "
      "veredicto con motivo: validada, en observación o rechazada.", cadence="a demanda",
      consumes=(("paper.broker", "paper_trade"),), produces=("validation_verdict",)),
    c("library.cards", "library", "validacion", "store", "cli", "T52", "Biblioteca de trading",
      "Fichas citadas de los libros del usuario, con búsqueda local. El texto es dato, nunca "
      "instrucción; hoy nadie decide con ellas.", produces=("library_card",)),
    c("operation.experience_sync", "operation", "validacion", "service", "api", "T61",
      "Experiencia compartida", "Une los historiales de varios equipos: cada máquina exporta lo suyo a una carpeta compartida e importa lo ajeno sin duplicar, con simulacro y copia previa. Nunca viajan claves.",
      cadence="a demanda (o cada hora si está automático)",
      consumes=(("validation.gate", "validation_verdict"), ("paper.broker", "paper_trade")),
      produces=("experience",)),
)

CORE: tuple[Component, ...] = DATA + FLOW + OPERATION + VALIDATION
ALL_BUILT: tuple[Component, ...] = AGENTS + CORE
