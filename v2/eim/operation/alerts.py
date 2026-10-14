"""Alertas de la operación continua: condiciones → avisos con transición (sin repetir).

Canal elegido por el usuario (2026-10-14): notificación local de Windows + panel de la UI.
Cada condición tiene una clave; se avisa al ENTRAR en la condición y, al salir, queda un
aviso de «resuelta». Mientras dura no se repite (salvo `repeat_ms`, recordatorio opcional).
Todas las alertas quedan en DuckDB (`op_alerts`) para la UI y el informe semanal.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass

INFO, WARN, CRITICAL = "info", "warn", "critical"
# tipos (los cinco del entregable 3 de T31 + servicio, informe y copia de seguridad de T32)
DISCONNECT, DIVERGENCE, KILL, DRAWDOWN, DEGRADED = (
    "desconexion", "divergencia", "kill_switch", "drawdown", "agentes_degradados")
SERVICE, REPORT, BACKUP = "servicio", "informe", "copia_seguridad"

_DDL = """
CREATE TABLE IF NOT EXISTS op_alerts (
    t BIGINT, kind VARCHAR, level VARCHAR, key VARCHAR, alert VARCHAR
)
"""


@dataclass(frozen=True)
class Alert:
    t: int
    kind: str
    level: str
    title: str
    detail: str = ""
    key: str = ""                 # condición (p. ej. "desconexion:BTCUSDT")
    resolved: bool = False        # True: aviso de que la condición terminó

    def to_json(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Condition:
    """Estado de una condición vigilada en un ciclo."""

    key: str
    kind: str
    on: bool
    level: str = WARN
    title: str = ""
    detail: str = ""


Sink = Callable[[Alert], None]


class AlertCenter:
    def __init__(self, con, lock: threading.Lock, sinks: Iterable[Sink] = (),
                 repeat_ms: int | None = None) -> None:
        self._con, self._lock = con, lock
        self._sinks = list(sinks)
        self._repeat = repeat_ms
        self._active: dict[str, int] = {}          # clave → hora del último aviso
        self.sink_errors: list[str] = []
        with lock:
            con.execute(_DDL)

    def emit(self, a: Alert) -> None:
        """Registra y notifica. Un canal roto nunca interrumpe la operación."""
        with self._lock:
            self._con.execute("INSERT INTO op_alerts VALUES (?,?,?,?,?)",
                              [a.t, a.kind, a.level, a.key, json.dumps(a.to_json())])
        for sink in self._sinks:
            try:
                sink(a)
            except Exception as e:  # noqa: BLE001 - el aviso queda en la tabla igualmente
                self.sink_errors = [*self.sink_errors[-9:], f"{type(e).__name__}: {e}"]

    def update(self, now: int, conditions: Iterable[Condition]) -> list[Alert]:
        """Aplica las condiciones del ciclo; devuelve los avisos emitidos."""
        out: list[Alert] = []
        for c in conditions:
            since = self._active.get(c.key)
            if c.on and (since is None or (self._repeat and now - since >= self._repeat)):
                a = Alert(now, c.kind, c.level, c.title, c.detail, c.key)
                self._active[c.key] = now
                out.append(a)
            elif not c.on and since is not None:
                del self._active[c.key]
                out.append(Alert(now, c.kind, INFO, f"Resuelta: {c.title or c.kind}", c.detail,
                                 c.key, resolved=True))
        for a in out:
            self.emit(a)
        return out

    @property
    def active(self) -> list[str]:
        return sorted(self._active)

    def recent(self, since: int = 0, until: int | None = None,
               limit: int = 100) -> list[Alert]:
        sql, args = "SELECT alert FROM op_alerts WHERE t >= ?", [since]
        if until is not None:
            sql, args = sql + " AND t < ?", [*args, until]
        with self._lock:
            rows = self._con.execute(f"{sql} ORDER BY t DESC LIMIT {int(limit)}",
                                     args).fetchall()
        return [Alert(**json.loads(r[0])) for r in rows]


# --- reglas puras: estado del ciclo → condiciones ---------------------------------------
def conditions(*, now: int, data_fail_since: dict[str, int | None], disconnect_ms: int,
               recon: dict | None, kill: dict, drawdown: float, drawdown_warn: float,
               drawdown_kill: float, agent_status: dict[str, dict[str, str]],
               critical: tuple[str, ...]) -> list[Condition]:
    """Las cinco familias de alerta del entregable 3.

    - desconexión: un símbolo sin datos del proveedor durante ≥ `disconnect_ms` (todos los
      símbolos operados aparecen en `data_fail_since`; None = con datos).
    - divergencia: la reconciliación encuentra diferencias (libro ≠ exchange, SL ausente) o
      no puede hablar con el exchange.
    - kill-switch activo (crítica).
    - drawdown ≥ `drawdown_warn` (aviso previo al kill-switch, que actúa en `drawdown_kill`).
    - agentes degradados: algún agente crítico no `ok`, u otro en `degraded` (error/timeout).
    """
    out: list[Condition] = []
    for sym, since in sorted(data_fail_since.items()):
        gone = 0 if since is None else now - since    # None: el símbolo tiene datos
        out.append(Condition(f"{DISCONNECT}:{sym}", DISCONNECT, gone >= disconnect_ms, CRITICAL,
                             f"Sin datos de {sym}", f"{gone / 1000:.0f} s sin respuesta del "
                             "proveedor de velas"))
    if recon is not None:
        bad = list(recon.get("issues", ()))
        out.append(Condition(DIVERGENCE, DIVERGENCE, bool(bad), CRITICAL,
                             "Divergencia en la reconciliación", " · ".join(bad)[:500]))
    out.append(Condition(KILL, KILL, bool(kill.get("active")), CRITICAL,
                         "Kill-switch activado",
                         f"{kill.get('by', '')}: {kill.get('reason', '')}".strip(": ")))
    out.append(Condition(DRAWDOWN, DRAWDOWN, drawdown >= drawdown_warn,
                         CRITICAL if drawdown >= drawdown_kill else WARN,
                         f"Drawdown {drawdown:.1%}",
                         f"aviso desde {drawdown_warn:.0%}; kill-switch en {drawdown_kill:.0%}"))
    for sym, status in sorted(agent_status.items()):
        bad = sorted(a for a, s in status.items()
                     if (a in critical and s != "ok") or s == "degraded")
        out.append(Condition(f"{DEGRADED}:{sym}", DEGRADED, bool(bad), WARN,
                             f"Agentes degradados en {sym}",
                             ", ".join(f"{a}={status[a]}" for a in bad)))
    return out
