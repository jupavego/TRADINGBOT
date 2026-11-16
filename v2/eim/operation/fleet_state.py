"""Lo que el vigilante del conjunto recuerda entre pasadas y lo que decide (T148, T173).

Cada pasada es un proceso nuevo que muere al acabar, así que todo lo que una pasada necesita saber
de las anteriores vive en `data/operation/fleet_watch.json`: ahí no hay nada que un apagón pueda
matar. `Decision` es el veredicto de una pasada, con la razón incluida, para poder registrarlo sin
volver a razonarlo.

La regla que los usa está en `fleet_watch.decide`; las razones por las que relanzar no sirve, en
`fleet_cause.py`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class State:
    """Lo que esta pasada necesita saber de las anteriores."""

    tries: int = 0
    down_since_ms: int | None = None
    last_try_ms: int | None = None
    gave_up_ms: int | None = None
    last_missing: list[str] = field(default_factory=list)
    # T173: el latido de los que faltaban cuando se lanzó el último intento, para saber en la
    # pasada siguiente si el intento movió algo. Y lo último que se dijo, para no repetirlo
    # cada 5 min: el 2026-11-10 «rendirse» quedó 31 veces en el registro.
    last_try_beats: dict[str, int | None] = field(default_factory=dict)
    said: str = ""

    _KEYS = ("tries", "down_since_ms", "last_try_ms", "gave_up_ms")

    @classmethod
    def load(cls, path: Path) -> State:
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        f = {k: d.get(k) for k in cls._KEYS}
        beats = d.get("last_try_beats")
        return cls(int(f["tries"] or 0), f["down_since_ms"], f["last_try_ms"], f["gave_up_ms"],
                   list(d.get("last_missing") or []),
                   dict(beats) if isinstance(beats, dict) else {}, str(d.get("said") or ""))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({**{k: getattr(self, k) for k in self._KEYS},
                                   "last_missing": self.last_missing,
                                   "last_try_beats": self.last_try_beats, "said": self.said},
                                  ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)


@dataclass(frozen=True)
class Decision:
    """Qué toca en esta pasada y por qué, para poder registrarlo sin volver a razonarlo."""

    # "ok" | "recuperado" | "levantar" | "esperar" | "rendirse" | "sin_red" | "dentro_de_otro"
    action: str
    missing: tuple[str, ...] = ()
    down_s: float = 0.0          # cuánto lleva caído el conjunto, no cada servicio
    wait_s: float = 0.0          # lo que falta para el siguiente intento ("esperar")
    tries: int = 0
    blocked: dict | None = None  # T173: el corte de red en marcha, si lo hay
    inside: tuple[str, ...] = ()  # T173: los que faltan y viven dentro de otro que sí late
    no_effect: bool = False      # T173: el intento anterior no movió ningún latido

    @property
    def lift(self) -> bool:
        return self.action == "levantar"

    @property
    def holding(self) -> bool:
        """Estados en los que no se hace nada y repetir el aviso cada 5 min solo es ruido."""
        return self.action in ("esperar", "rendirse", "sin_red", "dentro_de_otro")
