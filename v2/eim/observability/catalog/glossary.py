"""Glosario para quien no programa (T72): términos que la vista del flujo usa tal cual."""

from __future__ import annotations

GLOSSARY: dict[str, str] = {
    "sesgo": "Hacia dónde cree un analista que irá el precio, de −1 (baja con fuerza) a +1 (sube "
             "con fuerza). 0 es «no sé».",
    "confianza": "Qué tan seguro está el analista de su sesgo, de 0 a 1. Un sesgo alto con "
                 "confianza baja pesa poco.",
    "degradado": "El componente funcionó con datos parciales o con un fallo. Su resultado se "
                 "usa, pero con menos peso y avisando la cobertura real.",
    "sin datos": "No hay eventos recientes de ese componente. Nunca se pinta como sano: sin "
                 "señales no hay forma de saber que está bien.",
    "veto": "El motor de riesgo rechaza un plan. No es un error: es el sistema protegiendo el "
            "capital, y siempre deja los motivos.",
    "SL/TP": "SL (stop loss): precio donde se corta la pérdida. TP (take profit): precio "
             "objetivo donde se toma la ganancia.",
    "R": "Unidad de riesgo: 1 R es lo que se arriesga en una operación. Ganar 2 R es ganar el "
         "doble de lo arriesgado.",
    "traza": "El recorrido de una misma vela por todo el sistema: datos, análisis, plan, riesgo "
             "y orden. Todos los eventos de esa vela comparten la misma traza.",
    "evento": "Un hecho que un componente deja anotado: qué hizo, cuánto tardó y con qué datos. "
              "El mapa se dibuja con eventos reales.",
    "snapshot": "La fotografía del mercado en un instante: velas, funding, noticias y líderes, "
                "cada dato con su fuente. Los analistas solo ven esto.",
    "señal": "Lo que un analista calcula. Una señal no es una decisión ni una orden.",
    "decisión": "Lo que el motor de riesgo aprueba o veta sobre un plan. Una decisión aprobada "
                "todavía no es una orden enviada.",
    "orden": "La instrucción enviada al simulador o a la testnet. Solo existe si hubo una "
             "decisión aprobada y vigente.",
    "escenario": "Uno de tres futuros posibles (alcista, neutral, bajista) con su probabilidad "
                 "y una banda de incertidumbre.",
    "régimen": "El tipo de mercado del momento: tendencia, rango o volatilidad alta.",
    "funding": "Pago periódico entre compradores y vendedores de perpetuos; indica hacia qué "
               "lado está apretado el mercado.",
    "kill-switch": "Interruptor de emergencia: bloquea órdenes nuevas y pide cerrar lo abierto.",
    "latido": "Marca de tiempo que un servicio escribe para probar que sigue vivo.",
    "modo": "Análisis (solo mirar), Simulado (dinero de mentira en el equipo) o Testnet (cuenta "
            "de prueba de Binance). Todo se rotula con su modo; no hay dinero real.",
    "planeado": "Módulo previsto en el plan pero todavía sin código. Se dibuja punteado.",
}
