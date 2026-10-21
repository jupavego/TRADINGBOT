"""Auditoría de la protección progresiva (PPP): detecta cierres y estados que violan las reglas.

Un cierre por tiempo, por alcanzar un escalón, por una recomendación de un agente, un retroceso
del SL o una vuelta al punto de entrada NO es un cierre válido de la estrategia: se registra como
violación (evento «violacion» en el libro) y no se contabiliza en el resultado normal.
"""

from __future__ import annotations

from eim.paper.engine import Outcome

FORBIDDEN_CLOSE = {
    "TIEMPO": "cierre por tiempo (prohibido: el tiempo solo se registra para análisis)",
    "TP": "cierre por Take Profit (la estrategia no tiene TP final)",
    "BE": "cierre en break-even (tras activar la protección no se vuelve a la entrada)",
    "NIVEL": "cierre al alcanzar un escalón (los escalones suben el SL, no cierran)",
    "AGENTE": "cierre por recomendación de un agente (solo cierra el SL vigente)",
    "MANUAL": "cierre manual sin SL vigente tocado",
}


def check_close_request(reason: str) -> str | None:
    """Texto de la violación si `reason` no es un cierre válido (SL inicial o SL dinámico)."""
    return None if reason in ("SL", "SLD") else FORBIDDEN_CLOSE.get(
        reason, f"motivo de cierre desconocido «{reason}»")


def audit_outcome(o: Outcome) -> list[str]:
    """Violaciones de las reglas en un resultado de la escalera (vacío = limpio)."""
    out: list[str] = []
    info, i = o.ladder, o.idea
    if info is None:
        return ["resultado sin estado de escalera (no es un resultado PPP)"]
    s = i.side
    if o.status == "CERRADA":
        bad = check_close_request(o.reason)
        if bad:
            out.append(bad)
        if o.reason == "SLD" and not info["level"]:
            out.append("cierre por SL dinámico sin ningún escalón activado")
        if o.reason == "SL" and info["level"]:
            out.append("cierre por SL inicial con la protección ya activada (pérdida de nivel)")
        if o.exit is not None and info.get("stop") is not None and (o.exit - info["stop"]) * s > 0:
            out.append("la salida quedó mejor que el SL vigente (cierre que no fue el stop)")
        if o.exit_t is not None and o.fill_t is not None and o.exit_t < o.fill_t:
            out.append("el cierre es anterior a la apertura")
    prev_stop, prev_level, prev_nom = i.sl, 0, 0.0
    for h in info["stop_history"]:
        if (h["stop"] - prev_stop) * s <= 0:
            out.append(f"el SL retrocedió o no avanzó en el escalón {h['level']}")
        if h["level"] <= prev_level or h["nominal"] <= prev_nom:
            out.append("la protección retrocedió o repitió un nivel")
        if o.fill is not None and (h["stop"] - o.fill) * s <= 0:
            out.append("el SL protegido quedó en la entrada o por debajo (vuelta a break-even)")
        prev_stop, prev_level, prev_nom = h["stop"], h["level"], h["nominal"]
    if info["level"] != prev_level:
        out.append("el escalón vigente no coincide con el historial de SL")
    if info.get("incident") and o.status == "CERRADA":
        out.append("cierre normal con una incidencia técnica pendiente")
    return out
