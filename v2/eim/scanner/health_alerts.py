"""Avisos locales de la salud multiactivo (T102): condiciones → avisos con transición.

Las mismas reglas que `eim/operation/alerts.py` (se avisa al ENTRAR en una condición y queda un
«Resuelta» al salir; mientras dura no se repite), pero sin memoria del proceso: el escáner corre
como tarea diaria y cada vuelta es un proceso nuevo, así que las condiciones activas viajan en
`health.json` (`alerts_active`) y se recuperan en la vuelta siguiente. Puro: los canales (globo de
Windows, registro JSONL, observatorio) los pone `health_service.py`.

Solo avisan las clases **habilitadas** y el propio escáner: una clase en observación sin datos se
ve en el panel como «sin datos», pero no despierta a nadie.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from eim.operation.alerts import CRITICAL, INFO, WARN, Alert, Condition
from eim.scanner.health import ERROR, NO_DATA, STALE

KIND = "multiactivo"
BAD = (ERROR, NO_DATA, STALE)
_WHY = {ERROR: "con errores", NO_DATA: "sin datos", STALE: "con datos obsoletos"}


def conditions(health: Mapping) -> list[Condition]:
    """Una condición por clase habilitada, por fuente en uso y por el escáner."""
    out = []
    for c in health["classes"]:
        if not c["alerting"]:
            continue
        on = c["state"] in BAD
        out.append(Condition(
            key=f"{KIND}:clase:{c['asset_class']}", kind=KIND, on=on,
            level=CRITICAL if c["state"] == ERROR else WARN,
            title=f"{c['label']}: {_WHY.get(c['state'], c['state'])}",
            detail="; ".join(c["reasons"]) or c["note"]))
    for pr in health["providers"]:
        if not pr["used"]:
            continue
        out.append(Condition(
            key=f"{KIND}:fuente:{pr['name']}", kind=KIND, on=pr["state"] in BAD,
            level=WARN, title=f"Fuente {pr['name']}: {_WHY.get(pr['state'], pr['state'])}",
            detail=f"clases {', '.join(pr['classes']) or '—'}; errores {pr['errors']}"))
    sc = health["scanner"]
    out.append(Condition(
        key=f"{KIND}:escaner", kind=KIND, on=sc["state"] in BAD or sc["failed_jobs"] > 0,
        level=CRITICAL if sc["state"] == ERROR else WARN,
        title="Escáner global: " + (_WHY.get(sc["state"]) or "trabajos fallidos"),
        detail="; ".join(sc["reasons"]) or f"vista hace {health['view']['age_h']} h"))
    return out


def transitions(active: Mapping[str, int], conds: Iterable[Condition], now: int
                ) -> tuple[list[Alert], dict[str, int]]:
    """(avisos a emitir, condiciones activas tras esta vuelta). Igual que `AlertCenter.update`."""
    act = dict(active)
    out: list[Alert] = []
    for c in conds:
        since = act.get(c.key)
        if c.on and since is None:
            act[c.key] = now
            out.append(Alert(now, c.kind, c.level, c.title, c.detail, c.key))
        elif not c.on and since is not None:
            del act[c.key]
            out.append(Alert(now, c.kind, INFO, f"Resuelta: {c.title}", c.detail, c.key,
                             resolved=True))
    return out, act
