"""Kill-switch: estado global que bloquea nuevas órdenes y pide el cierre ordenado.

Se activa a mano o por reglas (drawdown, desconexión, desvío de reconciliación). Solo se
desactiva a mano: una regla nunca lo apaga. Cada cambio de estado queda en `events`. Con
`attach(path)` el estado se guarda en disco y sobrevive a un reinicio del proceso.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

from eim.risk.config import RiskConfig


@dataclass(frozen=True)
class KillEvent:
    t: int
    action: str          # activate | deactivate
    by: str              # manual | regla:<nombre>
    reason: str


class KillSwitch:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = False
        self._reason = ""
        self._since: int | None = None
        self._by = ""
        self._path: Path | None = None
        self.events: list[KillEvent] = []

    def attach(self, path: str | Path) -> None:
        """Persiste el estado en `path`; si el archivo dice activo, se reactiva al cargar."""
        p = Path(path)
        with self._lock:
            self._path = p
            if p.exists():
                d = json.loads(p.read_text(encoding="utf-8"))
                if d.get("active"):
                    self._active, self._reason = True, str(d.get("reason", ""))
                    self._since, self._by = d.get("since"), str(d.get("by", ""))
            self._save()

    def _save(self) -> None:          # llamar con el cerrojo tomado
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"active": self._active, "reason": self._reason,
                                   "since": self._since, "by": self._by}), encoding="utf-8")
        tmp.replace(self._path)

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    @property
    def close_requested(self) -> bool:
        """Mientras esté activo, la ejecución (T30) debe cerrar posiciones de forma ordenada."""
        return self.active

    def activate(self, reason: str, now: int, by: str = "manual") -> None:
        with self._lock:
            if self._active:          # ya activo: se conserva el primer motivo, sin eventos
                return
            self._active, self._reason, self._since, self._by = True, reason, now, by
            self.events.append(KillEvent(now, "activate", by, reason))
            self._save()

    def deactivate(self, now: int, by: str = "manual", reason: str = "") -> None:
        if not by.startswith("manual"):
            raise PermissionError("el kill-switch solo se desactiva manualmente")
        with self._lock:
            self._active, self._reason, self._since, self._by = False, "", None, ""
            self.events.append(KillEvent(now, "deactivate", by, reason))
            self._save()

    def check_rules(self, cfg: RiskConfig, now: int, drawdown: float | None = None,
                    disconnected_ms: int | None = None,
                    recon_drift: float | None = None) -> list[str]:
        """Evalúa las reglas automáticas; activa si alguna se incumple. Devuelve los motivos."""
        why: list[tuple[str, str]] = []
        if drawdown is not None and drawdown >= cfg.kill_max_drawdown:
            why.append(("drawdown", f"drawdown {drawdown:.2%} ≥ {cfg.kill_max_drawdown:.2%}"))
        if disconnected_ms is not None and disconnected_ms >= cfg.kill_max_disconnect_ms:
            why.append(("desconexion", f"desconectado {disconnected_ms / 1000:.0f} s ≥ "
                        f"{cfg.kill_max_disconnect_ms / 1000:.0f} s"))
        if recon_drift is not None and recon_drift >= cfg.kill_max_recon_drift:
            why.append(("reconciliacion", f"desvío de reconciliación {recon_drift:.2%} ≥ "
                        f"{cfg.kill_max_recon_drift:.2%}"))
        for rule, reason in why:
            self.activate(reason, now, by=f"regla:{rule}")
        return [r for _, r in why]

    def state(self) -> dict:
        with self._lock:
            return {"active": self._active, "reason": self._reason, "since": self._since,
                    "by": self._by, "close_requested": self._active,
                    "events": [asdict(e) for e in self.events[-50:]]}


_GLOBAL = KillSwitch()


def global_kill_switch() -> KillSwitch:
    """Instancia única del proceso (la usan el motor de riesgo, la API y la ejecución)."""
    return _GLOBAL
