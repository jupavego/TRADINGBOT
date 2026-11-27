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
    # T173 E4: la última hora de captura que se avisó como «late sin producir», para avisar una
    # vez por hora y no en cada pasada mientras el QC de esa hora siga siendo el último.
    stuck_hour: str = ""
    # T206: la interfaz se vigila aparte de los cinco, con su propia cuenta y su propia espera,
    # para que una interfaz que no arranque no gaste los intentos de la captura ni del bróker.
    web_tries: int = 0
    web_down_since_ms: int | None = None
    web_last_try_ms: int | None = None
    web_gave_up_ms: int | None = None
    web_said: str = ""

    _KEYS = ("tries", "down_since_ms", "last_try_ms", "gave_up_ms")
    _WEB = ("web_tries", "web_down_since_ms", "web_last_try_ms", "web_gave_up_ms")

    @classmethod
    def load(cls, path: Path) -> State:
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        f = {k: d.get(k) for k in cls._KEYS}
        beats = d.get("last_try_beats")
        st = cls(int(f["tries"] or 0), f["down_since_ms"], f["last_try_ms"], f["gave_up_ms"],
                 list(d.get("last_missing") or []),
                 dict(beats) if isinstance(beats, dict) else {}, str(d.get("said") or ""),
                 str(d.get("stuck_hour") or ""))
        for k in cls._WEB:
            setattr(st, k, int(d[k]) if isinstance(d.get(k), (int, float)) else None)
        st.web_tries = int(d.get("web_tries") or 0)
        st.web_said = str(d.get("web_said") or "")
        return st

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({**{k: getattr(self, k) for k in self._KEYS},
                                   "last_missing": self.last_missing,
                                   "last_try_beats": self.last_try_beats, "said": self.said,
                                   "stuck_hour": self.stuck_hour, "web_said": self.web_said,
                                   **{k: getattr(self, k) for k in self._WEB}},
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
