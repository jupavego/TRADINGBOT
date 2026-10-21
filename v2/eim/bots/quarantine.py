"""Cuarentena de bots (T60): el «kill-switch» del escuadrón.

Un bot que VOTA y se degrada (el adaptador falla, deriva, version distinta…) deja de votar de
inmediato y solo se reactiva a mano (`release`), igual que el kill-switch global del riesgo:
una regla nunca lo levanta. Estado persistido en `quarantine.json` y bitácora solo-añadir en
`quarantine.jsonl`. No toca el motor de riesgo ni la ejecución: solo quita el voto del bot.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from pathlib import Path


class Quarantine:
    def __init__(self, directory: Path) -> None:
        self._dir = Path(directory)
        self._lock = threading.Lock()
        self._state: dict[str, dict] = {}
        self.on_change: list[Callable[[], None]] = []   # p. ej. rehacer la política del escuadrón
        p = self._dir / "quarantine.json"
        if p.exists():
            self._state = json.loads(p.read_text(encoding="utf-8"))

    def keys(self) -> frozenset[str]:
        with self._lock:
            return frozenset(self._state)

    def entries(self) -> dict[str, dict]:
        with self._lock:
            return {k: dict(v) for k, v in self._state.items()}

    def trip(self, key: str, reason: str, t: int) -> bool:
        """Pone el bot en cuarentena; `False` si ya lo estaba."""
        with self._lock:
            if key in self._state:
                return False
            self._state[key] = {"reason": reason, "since": t}
            self._save("trip", key, reason, t)
        self._changed()
        return True

    def release(self, key: str, t: int, by: str = "manual") -> bool:
        with self._lock:
            if self._state.pop(key, None) is None:
                return False
            self._save("release", key, by, t)
        self._changed()
        return True

    def _changed(self) -> None:
        for fn in self.on_change:
            fn()

    def _save(self, action: str, key: str, why: str, t: int) -> None:   # con el cerrojo tomado
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._dir / "quarantine.tmp"
        tmp.write_text(json.dumps(self._state), encoding="utf-8")
        tmp.replace(self._dir / "quarantine.json")
        with (self._dir / "quarantine.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"t": t, "action": action, "bot": key, "why": why}) + "\n")
