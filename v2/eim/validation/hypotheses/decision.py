"""Regla de lectura y de parada de T139, sin más grados de libertad que los pre-registrados. Puro.

Lo que decide aquí es lo que el pre-registro fijó antes de calcular: qué clave sigue a la fase en
vivo, cuál queda en observación y qué recomendación sale de P0–P3. Seguir no es adoptar: nada entra
en los perfiles. Y parar no prueba que no exista ventaja, solo que no la hay por encima de lo
detectable.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from eim.validation.gate import Verdict
from eim.validation.hypotheses.pipeline import SideStats

SIGUE, OBSERVACION, FUERA = "sigue", "en observación", "fuera"
CORE = ("V1", "V2", "V3", "V4", "V6")


@dataclass(frozen=True)
class KeyReading:
    """Una clave en la lectura oficial, con lo que la regla de lectura necesita."""

    verdict: Verdict
    sides: SideStats
    null_p95: float | None
    bank_gross: float | None
    control_ok: bool | None


def checks_of(v: Verdict) -> dict[str, bool | None]:
    return {c.id: c.ok for c in v.checks}


def conditions(k: KeyReading) -> dict[str, bool]:
    """Las cinco condiciones del pre-registro, una a una, para que el informe diga cuál falla."""
    ck = checks_of(k.verdict)
    s = k.sides
    return {
        "1_puerta": all(ck[x] is True for x in CORE) and ck["V5"] is not False,
        "2_bruto_equilibrado": (s.balanced is not None and s.cost is not None
                                and s.balanced > s.cost),
        "3_costos_x1_5": s.stressed is not None and s.stressed > 0,
        "4_sustitutas": (s.gross is not None and k.null_p95 is not None
                         and s.gross > k.null_p95 and k.control_ok is True),
        "5_banco": k.bank_gross is None or k.bank_gross >= 0,       # sin operaciones no descarta
    }


def state_of(k: KeyReading) -> str:
    """Sigue si cumple las cinco; sin V1 pero con bruto equilibrado > costo, en observación."""
    c = conditions(k)
    if all(c.values()):
        return SIGUE
    if checks_of(k.verdict)["V1"] is False and c["2_bruto_equilibrado"]:
        return OBSERVACION
    return FUERA


def recommend(keys: Sequence[KeyReading], control_ok: Sequence[bool | None]) -> dict:
    """La recomendación de la lectura limpia. Es una recomendación: decide el usuario.

    P0 se resuelve antes, en la etapa de cobertura: sin cobertura esta lectura no llega a correr.
    """
    states = {k.verdict.version.label: state_of(k) for k in keys}
    follow = [x for x, s in states.items() if s == SIGUE]
    watch = [x for x, s in states.items() if s == OBSERVACION]
    if any(x is False for x in control_ok):
        return {"code": "CONTROL", "follow": follow, "watch": watch, "states": states,
                "text": "El control falla: las entradas al azar destacan sobre sus sustitutas. "
                        "La corrida no vale hasta diagnosticarlo, y no se concluye nada de ella."}
    if follow:
        return {"code": "SIGUE", "follow": follow, "watch": watch, "states": states,
                "text": "Seguir en vivo las claves que cumplen la regla de lectura, hasta "
                        "VALIDADA, P2 o P3. Nada entra en los perfiles."}
    if watch:
        return {"code": "OBSERVACION", "follow": [], "watch": watch, "states": states,
                "text": "Ninguna clave cumple la regla, pero alguna queda en observación por falta "
                        "de muestra, hasta la fecha límite (P3)."}
    return {"code": "P1", "follow": [], "watch": [], "states": states,
            "text": "Parar la búsqueda (P1): ninguna clave sigue ni queda en observación, y no hay "
                    "segunda ronda."}
