"""Autoridad de ejecución (T114): una sola puerta, varias políticas deterministas registradas.

Toda fuente PROPONE con `TradeProposal` (`eim/core/authority.py`) y solo una autoridad
registrada aquí DECIDE con `RiskDecision`. La puerta tiene tres partes y ninguna depende de la
fuente:

1. **Ruta** (`route_check`): la fuente está en `SOURCES`, está activa, no es un LLM y decide en
   ESA autoridad con un modo de salida suyo. Si no, la autoridad veta con el motivo (el rechazo
   queda registrado como cualquier otro).
2. **Caducidad** (`expiry_check`): pasada `expires_at`, la señal ya no se decide.
3. **Verificación al ejecutar** (`verify_route`): las puertas de órdenes (`OrderGateway`,
   `ArbGateway`) y el libro del bróker simulado vuelven a comprobar la ruta de la decisión; una
   decisión sin propuesta registrada no abre nada aunque esté aprobada y sellada.

Las autoridades son código determinista con veto: el motor T29 (`risk.engine`, con
`risk_v2` o `risk_copy_v1`), el del arbitraje (`risk.arb_engine`), el del carril HFT
(`risk.hft_engine`, una decisión por orden, T83) y la política de cada perfil del bróker simulado
(`paper.broker`: vetos, topes y tamaño). Ninguna regla de salida vigente
puede anularla una señal contraria: cerrar no es algo que una fuente pueda pedir (`EXIT_RULES`).
La prueba de que no hay puerta trasera está en `tests/architecture/`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from eim.core.authority import EXIT_MODES, Check, ExitMode, RiskDecision, TradeProposal
from eim.observability.events import proposal_trace

Status = Literal["activa", "solo_informa", "planeada"]

# Autoridades deterministas (id = componente del catálogo del Observatorio).
AUTHORITIES: dict[str, str] = {
    "risk.engine": "Motor de riesgo T29: 10 reglas + tamaño, sello HMAC, caducidad de 60 s",
    "risk.arb_engine": "Riesgo del arbitraje T45: cuenta total, patas, vigencia y sello",
    "paper.broker": "Política del perfil del bróker simulado: vetos, topes y tamaño (T47–T109)",
    "risk.hft_engine": "Riesgo del carril HFT T83: inventario, pérdidas, tasas, datos, reloj; "
                       "una decisión sellada por orden, vigente 1 s",
}

# Cierres que admite cada modo de salida. Una señal contraria NO es motivo de cierre en ninguno
# (el de la copia es que el PROPIO líder cierre: es su regla, no una señal ajena).
EXIT_RULES: dict[str, tuple[str, ...]] = {
    "stop_only": ("SL", "SLD", "LIQUIDACION", "SALVAGUARDA"),
    "sl_tp_time": ("SL", "SLD", "TP", "BE", "TIEMPO", "LIQUIDACION", "SALVAGUARDA"),
    "bracket": ("SL", "TP", "cierre ordenado (kill-switch o reconciliación)"),
    "follow_leader": ("el líder reduce o cierra", "stop de protección", "kill-switch propio"),
    "arb_rules": ("neto agotado", "vencimiento", "tenencia", "margen o liquidación",
                  "kill-switch"),
    "hft_rules": ("reduce-only de la estrategia", "cierre a mercado por kill-switch",
                  "cancelar todo (datos, libro, reloj, flujo de usuario, hombre muerto)"),
    "policy": (),
}
CONTRARY_SIGNAL = "señal contraria de otra fuente"


@dataclass(frozen=True)
class Source:
    """Una fuente de señal y la única ruta por la que puede llegar a una posición."""

    id: str
    title: str
    tasks: str
    status: Status
    authorities: tuple[str, ...]        # dónde decide (vacío = sin ruta a ejecución)
    policy: str                         # política vigente, en palabras
    exit_modes: tuple[ExitMode, ...]    # modos de salida que la autoridad puede conceder
    entry: str                          # dónde nace la propuesta
    llm: bool = False
    note: str = ""


SOURCES: dict[str, Source] = {s.id: s for s in (
    Source("agents.plan", "Plan de los agentes (síntesis → agente plan)", "T13 T29 T30 T31",
           "activa", ("risk.engine",), "risk_v2", ("bracket",),
           "eim/api/risk.py · RiskDesk.evaluate"),
    Source("paper.strategies", "Estrategias del bróker simulado (ideas sombra)",
           "T47 T48 T105–T112", "activa", ("paper.broker",),
           "perfil del bróker: vetos, topes y tamaño", ("stop_only", "sl_tp_time"),
           "eim/paper/policy.py · decide", note="incluye la familia «sugerencias» (T50)"),
    Source("copy.leaders", "Copia simulada de líderes", "T41 T42", "activa", ("risk.engine",),
           "risk_copy_v1", ("follow_leader",), "eim/copytrading/copy_risk.py · CopyRisk.check"),
    Source("arb.scanner", "Arbitraje de dos patas (escáner T38 → selector)", "T38 T39 T45",
           "activa", ("risk.arb_engine",), "risk_arb_v1", ("arb_rules",),
           "eim/execution/arb_runner.py · ArbAutopilot.open_best"),
    Source("ops.smoke", "Pruebas de fontanería (humo de testnet y escenarios en papel)",
           "T30 T45", "activa", ("risk.engine", "risk.arb_engine"),
           "risk_v2 / risk_arb_v1 (risk_arb_sim_v1 en papel)", ("bracket", "arb_rules"),
           "eim/execution/{smoke,arb_smoke}.py · eim/paper/arb_tests.py",
           note="plan sintético lanzado a mano; no sale de ninguna señal de mercado"),
    Source("bots.squad", "Escuadrón de bots (postura)", "T57 T58 T59", "solo_informa", (),
           "—", ("policy",), "eim/core/bots.py · BotSignal.as_proposal",
           note="la postura solo llega al agente `bots` (peso 0 en la síntesis); el carril "
                "simulado de T58 es un libro aparte que nunca vota"),
    Source("agents.context", "Contexto con LLM (noticias y eventos)", "T24", "solo_informa",
           (), "—", ("policy",), "eim/agents/context", llm=True,
           note="solo modula la confianza o añade una pausa (veto); nunca propone ni levanta"),
    Source("hft.micro", "Carril HFT (microestructura rápida)", "T83 T85", "activa",
           ("risk.hft_engine",), "hft_risk_v1", ("hft_rules",),
           "eim/execution/hft_lane.py · HftLane.submit",
           note="T83: riesgo y ejecución, solo SIMULADO/TESTNET; las estrategias (T82) y el "
                "servicio en vivo (T85) aún no existen: hoy solo proponen las pruebas"),
    Source("video.intel", "Agente de videos", "T70", "planeada", (), "—", ("policy",),
           "eim/agents/video_intel (por construir)",
           note="como agente vota en la síntesis: llega a una orden solo por agents.plan"),
)}


def _validate(sources: dict[str, Source]) -> None:
    """Registro coherente o el proceso no arranca (validación ruidosa, como T108)."""
    for k, s in sources.items():
        if k != s.id:
            raise ValueError(f"fuente registrada con otra clave: {k} ≠ {s.id}")
        if s.llm and (s.authorities or s.status == "activa"):
            raise ValueError(f"{s.id}: un LLM solo informa; no puede tener ruta a ejecución")
        if (s.status == "activa") != bool(s.authorities):
            raise ValueError(f"{s.id}: activa ⇔ con autoridad (estado {s.status})")
        if unknown := [a for a in s.authorities if a not in AUTHORITIES]:
            raise ValueError(f"{s.id}: autoridad desconocida {unknown}")
        if not s.exit_modes or any(m not in EXIT_MODES for m in s.exit_modes):
            raise ValueError(f"{s.id}: modos de salida inválidos {s.exit_modes}")


_validate(SOURCES)


def route_reason(source: str, authority: str, exit_mode: str | None = None) -> str | None:
    """None si `source` puede proponer a `authority` (con ese modo de salida); si no, el motivo."""
    s = SOURCES.get(source)
    if s is None:
        return f"fuente no registrada «{source}»: nadie la autorizó a proponer"
    if s.llm:
        return f"{source} es un LLM: solo informa, nunca propone órdenes"
    if s.status != "activa":
        what = "solo informa" if s.status == "solo_informa" else "está planeada"
        return f"{source} {what}: no tiene ruta a ejecución"
    if authority not in s.authorities:
        return f"{source} decide en {', '.join(s.authorities)}, no en {authority}"
    if exit_mode is not None and exit_mode not in s.exit_modes:
        return f"modo de salida «{exit_mode}» no registrado para {source}"
    return None


def route_check(p: TradeProposal, authority: str, exit_mode: str | None = None) -> Check:
    why = route_reason(p.source, authority, exit_mode)
    return Check(rule="fuente", ok=why is None,
                 detail=why or f"{p.source} {p.source_version} → {authority}")


def _utc(t: int) -> str:
    return datetime.fromtimestamp(t / 1000, UTC).strftime("%Y-%m-%d %H:%M:%S")


def expiry_reason(expires_at: int, now: int) -> str | None:
    """None si la señal sigue vigente en `now`; si no, el motivo (lo usan todas las autoridades)."""
    if now > expires_at:
        return (f"la señal caducó hace {(now - expires_at) / 1000:.0f} s "
                f"(vigente hasta {_utc(expires_at)} UTC)")
    return None


def expiry_check(p: TradeProposal, now: int) -> Check:
    why = expiry_reason(p.expires_at, now)
    return Check(rule="caducidad", ok=why is None,
                 detail=why or f"vigente hasta {_utc(p.expires_at)} UTC")


def match_check(p: TradeProposal, symbol: str, side: int, stop: float | None,
                asof: int) -> Check:
    """Lo que se dimensiona es lo propuesto: una propuesta registrada no avala otro plan."""
    diff = [k for k, a, b in (("símbolo", p.symbol, symbol), ("lado", p.side, side),
                              ("stop", p.stop, stop), ("instante", p.data_asof, asof)) if a != b]
    return Check(rule="propuesta", ok=not diff,
                 detail=f"{p.proposal_id}" if not diff else
                 f"el plan no es el propuesto ({', '.join(diff)} distinto)")


def gate_checks(p: TradeProposal, authority: str, now: int, *, symbol: str, side: int,
                stop: float | None, asof: int, exit_mode: str | None = None) -> list[Check]:
    """Las reglas de la puerta, comunes a toda autoridad (van antes que las suyas)."""
    return [route_check(p, authority, exit_mode or p.exit_mode),
            match_check(p, symbol, side, stop, asof), expiry_check(p, now)]


def expires_after(asof: int, max_age_ms: float) -> int:
    """Caducidad que nunca es más estricta que la regla de vigencia de la política (techo)."""
    return asof + math.ceil(max_age_ms)


def verify_source(source: str, authority: str, exit_mode: str | None = None) -> None:
    """Lanza `PermissionError` si `source` no tiene ruta registrada a `authority` (al ejecutar)."""
    if why := route_reason(source, authority, exit_mode):
        raise PermissionError(f"ruta no autorizada: {why}")


def verify_route(p: TradeProposal | None, authority: str, exit_mode: str | None = None) -> None:
    """Lanza `PermissionError` si la decisión no trae una propuesta con ruta registrada."""
    if p is None:
        raise PermissionError("decisión sin propuesta: ninguna fuente registrada la pidió")
    verify_source(p.source, authority, exit_mode or p.exit_mode)


def verify_decision(d: RiskDecision) -> None:
    """`verify_route` sobre una `RiskDecision` (la autoridad que decidió es la de la ruta)."""
    verify_route(d.proposal, d.authority, d.exit_mode)


__all__ = ["AUTHORITIES", "CONTRARY_SIGNAL", "EXIT_RULES", "SOURCES", "Source",
           "expires_after", "expiry_check", "expiry_reason", "gate_checks", "match_check",
           "proposal_trace", "route_check", "route_reason", "verify_decision", "verify_route",
           "verify_source"]
