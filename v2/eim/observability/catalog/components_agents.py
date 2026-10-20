"""Catálogo: los agentes de `default_registry` (id = `agent.<id del agente>`).

Versión y requisitos tomados de `eim/agents/<id>/agent.py`; un test los compara con el
registro, así que subir la versión de un agente obliga a actualizar esta tabla.
"""

from __future__ import annotations

from eim.observability.catalog.model import Component, c

_SNAP = (("data.snapshot", "snapshot"),)
_H = 3600  # los agentes corren al cierre de cada vela (ciclo de operación: 1 h)


def _a(name: str, version: str, title: str, explain: str, task: str, *,
       stage: str = "analisis", consumes=_SNAP, produces=("agent_report",)) -> Component:
    return c(f"agent.{name}", "agent", stage, "agent", "api", task, title, explain,  # type: ignore[arg-type]
             cadence="cada cierre de vela", cadence_s=_H, consumes=consumes, produces=produces,
             version=version)


AGENTS: tuple[Component, ...] = (
    _a("structure", "1.0.0", "Estructura de mercado",
       "Lee la forma del mercado (máximos y mínimos, fases) sobre todo el histórico. Recibe las velas; "
       "entrega un sesgo alcista o bajista con su confianza.", "T05"),
    _a("ema", "1.0.0", "Medias móviles",
       "Mira si las medias móviles de distintos plazos están ordenadas a favor de la subida o de la "
       "bajada. Recibe velas; entrega sesgo y confianza.", "T05"),
    _a("vwap", "1.0.0", "Precio medio ponderado",
       "Compara el precio con el promedio ponderado por volumen del día, la semana y el mes. Recibe "
       "velas; entrega si el precio está caro o barato frente a ese promedio.", "T06"),
    _a("price_action", "1.0.0", "Lectura de velas",
       "Busca patrones de velas y rupturas de estructura recientes. Recibe velas; entrega sesgo, "
       "confianza y zonas de soporte y resistencia.", "T06"),
    _a("elliott", "1.0.0", "Ondas de Elliott",
       "Cuenta ondas tentativas entre giros del precio. Es una hipótesis, no un hecho: recibe velas y "
       "entrega un conteo con su nivel de invalidación.", "T07"),
    _a("seasonality", "1.0.0", "Estacionalidad",
       "Mira cómo suele comportarse el mes en curso según el promedio histórico real de ese mes. "
       "Recibe velas; entrega un sesgo suave.", "T07"),
    _a("liquidations", "2.0.0", "Liquidaciones forzadas",
       "Mide las liquidaciones forzadas en vivo (Binance, Bybit, OKX): detecta cascadas y si ya se "
       "agotaron. Recibe el flujo por vela del snapshot; entrega sesgo y confianza.", "T07"),
    _a("levels", "1.0.0", "Niveles y canales",
       "Marca zonas donde el precio rebotó antes y el canal o rango actual. Recibe velas; entrega "
       "soportes, resistencias y la posición del precio.", "T12"),
    _a("derivatives", "1.0.0", "Derivados",
       "Lee el costo de mantener posiciones (funding) y cuánto dinero hay abierto (interés abierto). "
       "Avisa si el mercado está muy apalancado hacia un lado.", "T21"),
    _a("microstructure", "1.0.0", "Flujo de órdenes",
       "Mira quién compra y vende a mercado y cómo se mueve el libro de órdenes en el muy corto "
       "plazo. Recibe el flujo del recolector; entrega un sesgo de corto plazo.", "T23"),
    _a("regime", "1.0.0", "Régimen de mercado",
       "Detecta cambios de comportamiento: tendencia, rango o volatilidad alta. Recibe velas; "
       "entrega la etiqueta del régimen y la probabilidad de que acabe de cambiar.", "T22"),
    _a("context", "1.0.0", "Contexto de noticias",
       "Un modelo de lenguaje resume titulares y sentimiento. Solo informa: nunca decide ni da "
       "sesgo; puede pedir una pausa por noticias.", "T24"),
    _a("technical", "0.1.0", "Indicadores técnicos",
       "Junta decenas de indicadores clásicos sin contar dos veces lo mismo y en varios marcos "
       "de tiempo. Entrega una confluencia de sesgo.", "T35"),
    _a("calendar", "1.1.0", "Calendario económico",
       "Sabe cuándo salen datos importantes (inflación, tasas, empleo). No opina sobre dirección: "
       "entrega ventanas de riesgo en las que conviene no operar.", "T36"),
    _a("arbitrage", "1.0.0", "Arbitraje",
       "Busca diferencias de precio o de tasas dentro de Binance que dejan ganancia neta tras "
       "costos. No vota la dirección; muestra oportunidades.", "T39",
       consumes=(("data.snapshot", "snapshot"),)),
    _a("smart_money", "0.1.0", "Dinero inteligente",
       "Mira qué posición neta tienen los traders de Hyperliquid mejor evaluados en la moneda del "
       "análisis. Recibe el tablero de líderes; entrega sesgo y confianza.", "T41"),
    _a("literature", "0.1.0", "Reglas de los libros",
       "Revisa si ahora se cumplen reglas de Nison y Murphy (velas, RSI, rupturas) y si apoyan o "
       "contradicen cada escenario, con su cita. Apoyo bibliográfico, no una señal validada.",
       "T53", consumes=_SNAP + (("library.cards", "library_card"),)),
    _a("bots", "0.1.0", "Escuadrón de bots",
       "Resume lo que opinan los bots públicos aprobados (cada uno con su versión y estado). Hasta "
       "que la puerta de validación los habilite solo informa: no suma al sesgo.", "T57",
       consumes=(("bots.runner", "bot_signal"),)),
    _a("plan", "1.0.0", "Plan de operación",
       "Propone una operación completa: precio de entrada, salida de pérdida (SL), objetivos (TP) y "
       "relación ganancia/riesgo, a partir de estructura y niveles. Siempre en modo Análisis.",
       "T13", stage="plan",
       consumes=(("agent.structure", "agent_report"), ("agent.levels", "agent_report"),
                 ("synthesis.thesis", "synthesis")),
       produces=("agent_report", "plan")),
)


# T57: el servicio que produce las posturas (modo A en proceso; modo B en subproceso aislado).
BOTS: tuple[Component, ...] = (
    c("bots.runner", "bots", "analisis", "service", "api", "T57", "Ejecutor de bots",
      "Corre los bots públicos aprobados aislados, sin claves ni poder de operar, y convierte su "
      "salida en una postura común que se guarda con su versión. No envía órdenes.",
      cadence="cada cierre de vela", cadence_s=_H, consumes=_SNAP, produces=("bot_signal",)),
    c("bots.scoring", "bots", "validacion", "engine", "api", "T59", "Puntuación de bots",
      "Mide a cada bot con la misma puerta que a las estrategias propias (neto de costos, fuera "
      "de muestra, contra el azar) y su aporte al núcleo; le da un estado (vota, informa, "
      "rechazado, deshabilitado) y lo degrada si falla. Siempre simulado.",
      cadence="cada cierre de vela de 4 h", cadence_s=4 * _H,
      consumes=(("bots.runner", "bot_signal"),), produces=("bot_score",)),
)
