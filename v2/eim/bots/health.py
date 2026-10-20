"""Degradación de un bot (T59), pura: rendimiento vivo, deriva de versión y fallos del ejecutor.

Reglas fijadas antes de mirar datos. Un bot en estado `vota` que incumple CUALQUIERA baja a
`informa` con una alerta (mismo patrón de condiciones que T31: `eim.operation.alerts.Condition`,
que el `AlertCenter` avisa al entrar y al salir):

- **Rendimiento vivo**: con ≥ `live_min` operaciones en vivo, su R medio queda por debajo del límite
  inferior del IC de su ventana fuera de muestra (el vivo no se parece a lo que lo validó).
- **Deriva entre versiones**: sobre los instantes comunes, la postura (lado) de la versión nueva
  coincide con la de la anterior en menos de `drift_min_agree` (cambió el comportamiento).
- **Fallos del ejecutor**: más de `fail_max` de las últimas `fail_window` señales no están `ok`.
- **Latencia** (opcional): mediana por encima de `latency_max_ms` si el ejecutor la reporta.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from eim.core import BotSignal
from eim.operation.alerts import WARN, Condition

KIND = "bot_degradado"


@dataclass(frozen=True)
class HealthParams:
    live_min: int = 20
    drift_min_agree: float = 0.8
    drift_min_common: int = 50
    fail_window: int = 100
    fail_max: float = 0.05
    latency_max_ms: float = 60_000.0


@dataclass(frozen=True)
class Health:
    degraded: bool
    reasons: tuple[str, ...]
    live_n: int = 0
    live_mean_r: float | None = None
    fail_rate: float | None = None
    drift_agree: float | None = None

    def to_json(self) -> dict:
        return {"degraded": self.degraded, "reasons": list(self.reasons), "live_n": self.live_n,
                "live_mean_r": self.live_mean_r, "fail_rate": self.fail_rate,
                "drift_agree": self.drift_agree}


def _side(x: float) -> int:
    return 1 if x > 0 else -1 if x < 0 else 0


def drift_agreement(old: Sequence[BotSignal], new: Sequence[BotSignal]) -> tuple[float | None, int]:
    """Coincidencia de lado entre dos versiones en los `asof` que ambas tienen en estado ok."""
    a = {s.asof: _side(s.stance) for s in old if s.status == "ok"}
    b = {s.asof: _side(s.stance) for s in new if s.status == "ok"}
    common = sorted(a.keys() & b.keys())
    if not common:
        return None, 0
    return sum(a[t] == b[t] for t in common) / len(common), len(common)


def assess(live_r: Sequence[float], oos_ci_low: float | None, recent: Sequence[BotSignal],
           previous: Sequence[BotSignal] = (), current: Sequence[BotSignal] = (),
           latency_ms: Sequence[float] = (), p: HealthParams | None = None) -> Health:
    p = p or HealthParams()
    why: list[str] = []
    live_mean = sum(live_r) / len(live_r) if live_r else None
    if live_mean is not None and len(live_r) >= p.live_min and oos_ci_low is not None \
            and live_mean < oos_ci_low:
        why.append(f"rendimiento vivo: R medio {live_mean:+.3f} en {len(live_r)} operaciones, "
                   f"por debajo del límite inferior fuera de muestra ({oos_ci_low:+.3f})")
    last = list(recent)[-p.fail_window:]
    fail = sum(s.status != "ok" for s in last) / len(last) if last else None
    if fail is not None and fail > p.fail_max:
        why.append(f"fallos del ejecutor: {fail:.0%} de las últimas {len(last)} señales sin `ok`")
    agree, common = drift_agreement(previous, current)
    if agree is not None and common >= p.drift_min_common and agree < p.drift_min_agree:
        why.append(f"deriva entre versiones: solo {agree:.0%} de coincidencia en {common} velas")
    if latency_ms and statistics.median(latency_ms) > p.latency_max_ms:
        why.append(f"latencia mediana {statistics.median(latency_ms):.0f} ms del ejecutor")
    return Health(bool(why), tuple(why), len(live_r), live_mean, fail,
                  agree if common >= p.drift_min_common else None)


def conditions(label: str, h: Health) -> list[Condition]:
    """Condición para el `AlertCenter` de T31 (avisa al entrar; al salir, «resuelta»)."""
    return [Condition(key=f"{KIND}:{label}", kind=KIND, on=h.degraded, level=WARN,
                      title=f"Bot degradado a «informa»: {label}", detail="; ".join(h.reasons))]
