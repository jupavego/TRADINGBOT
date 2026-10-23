"""Auditoría de la protección progresiva (PPP): detecta cierres y estados que violan las reglas.

Desde T109 cubre a los cuatro perfiles (todos salen con escalera). Solo pueden cerrar, cada uno con
su motivo propio en el registro (`ALLOWED_CLOSE`): el stop inicial, el stop dinámico (escalón o
BE+), la liquidación simulada (T107) y una salvaguarda independiente (kill-switch de T31). Una
incidencia técnica no cierra: la posición queda abierta marcada «incidencia».

Cualquier otro motivo —tiempo, Take Profit, alcanzar un escalón, señal contraria de un agente,
retroceso del flotante sin tocar el stop, cierre manual— es una violación: el libro la registra
(bitácora y contador) y NO ejecuta ese cierre (`book._close`). Un cierre por el stop cuyo historial
tiene anomalías sí se ejecuta (el precio tocó el stop) y queda auditado aparte.
"""

from __future__ import annotations

from eim.paper.account import LIQ
from eim.paper.engine import Outcome

SAFEGUARD = "SALVAGUARDA"     # cierre ordenado por una salvaguarda independiente (kill-switch)

ALLOWED_CLOSE = {
    "SL": "stop inicial",
    "SLD": "stop dinámico (escalón o BE+)",
    LIQ: "liquidación simulada (margen aislado, T107)",
    SAFEGUARD: "salvaguarda independiente (kill-switch de T31)",
}

FORBIDDEN_CLOSE = {
    "TIEMPO": "cierre por tiempo (prohibido: el tiempo solo se registra para análisis)",
    "TP": "cierre por Take Profit (la estrategia no tiene TP final)",
    "BE": "cierre en break-even fuera del stop vigente (el BE+ solo mueve el stop: cierra «SLD»)",
    "NIVEL": "cierre al alcanzar un escalón (los escalones suben el SL, no cierran)",
    "AGENTE": "cierre por una señal contraria o recomendación de un agente (solo informa)",
    "RETROCESO": "cierre por retroceso del flotante sin tocar el SL vigente",
    "MANUAL": "cierre manual sin SL vigente tocado",
}


def check_close_request(reason: str) -> str | None:
    """Texto de la violación si `reason` no es un cierre permitido (`ALLOWED_CLOSE`)."""
    return None if reason in ALLOWED_CLOSE else FORBIDDEN_CLOSE.get(
        reason, f"motivo de cierre desconocido «{reason}»")


def audit_outcome(o: Outcome) -> list[str]:
    """Violaciones de las reglas en un resultado de la escalera (vacío = limpio)."""
    out: list[str] = []
    info, i = o.ladder, o.idea
    if info is None:
        return ["resultado sin estado de escalera (no es un resultado PPP)"]
    s = i.side
    moved = bool(info["stop_history"])
    if o.status == "CERRADA":
        bad = check_close_request(o.reason)
        if bad:
            out.append(bad)
        if o.reason == "SLD" and not moved:
            out.append("cierre por SL dinámico sin ningún escalón ni BE+ activado")
        if o.reason == "SL" and moved:
            out.append("cierre por SL inicial con la protección ya activada (pérdida de nivel)")
        if (o.reason != SAFEGUARD and o.exit is not None and info.get("stop") is not None
                and (o.exit - info["stop"]) * s > 0):
            out.append("la salida quedó mejor que el SL vigente (cierre que no fue el stop)")
        if o.exit_t is not None and o.fill_t is not None and o.exit_t < o.fill_t:
            out.append("el cierre es anterior a la apertura")
    prev_stop, prev_level, prev_nom = i.sl, 0, 0.0
    for h in info["stop_history"]:
        if (h["stop"] - prev_stop) * s <= 0:
            out.append(f"el SL retrocedió o no avanzó en el escalón {h['level']}")
        if h.get("source", "escalon") == "escalon":
            if h["level"] <= prev_level or h["nominal"] <= prev_nom:
                out.append("la protección retrocedió o repitió un nivel")
            prev_level, prev_nom = h["level"], h["nominal"]
        elif h["source"] == "recuperado":       # suelo guardado adoptado (T110): nunca baja
            if h["level"] < prev_level:
                out.append("el estado recuperado bajó el escalón")
            prev_level, prev_nom = h["level"], max(prev_nom, h["nominal"])
        elif h["level"] != prev_level:
            out.append("el BE+ cambió el escalón (solo puede mover el stop)")
        if o.fill is not None and (h["stop"] - o.fill) * s <= 0:
            out.append("el SL protegido quedó en la entrada o por debajo (vuelta a break-even)")
        prev_stop = h["stop"]
    if info["level"] != prev_level:
        out.append("el escalón vigente no coincide con el historial de SL")
    if info.get("incident") and o.status == "CERRADA":
        out.append("cierre normal con una incidencia técnica pendiente")
    return out
