"""Cuarentena de bots (T60): el «kill-switch» del escuadrón.

Un bot que VOTA y se degrada (el adaptador falla, deriva, version distinta…) deja de votar de
inmediato y solo se reactiva a mano (`release`), igual que el kill-switch global del riesgo:
una regla nunca lo levanta. Estado persistido en `quarantine.json` y bitácora solo-añadir en
`quarantine.jsonl`. No toca el motor de riesgo ni la ejecución: solo quita el voto del bot.

La reactivación es por CLI con la API en marcha (T119): la API relee `quarantine.json` cuando
otro proceso lo cambia (`sync`, en cada ciclo de bots y en cada consulta), así que no hace falta
reiniciarla y un disparo posterior no deshace la reactivación.

    python -m eim.bots.quarantine [--data-dir data] list
    python -m eim.bots.quarantine [--data-dir data] release <bot_id>@<estrategia> [--by <quién>]
"""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path


def _stamp(p: Path) -> tuple[int, int]:
    st = p.stat()
    return st.st_mtime_ns, st.st_size


class Quarantine:
    def __init__(self, directory: Path) -> None:
        self._dir = Path(directory)
        self._lock = threading.Lock()
        self._state: dict[str, dict] = {}
        self._seen: tuple[int, int] | None = None   # (mtime, tamaño) del archivo de `_state`
        self.on_change: list[Callable[[], None]] = []   # p. ej. rehacer la política del escuadrón
        self._load()

    def _load(self) -> bool:
        """Relee el archivo si cambió desde la última lectura o escritura propia (con el cerrojo
        tomado). True si el estado cambió."""
        p = self._dir / "quarantine.json"
        try:
            m = _stamp(p)
            state = json.loads(p.read_text(encoding="utf-8")) if m != self._seen else None
        except FileNotFoundError:
            m, state = None, {}
        except ValueError:          # escritura a medias de otro proceso: se relee la próxima vez
            return False
        if m == self._seen or state is None:
            return False
        self._seen, changed = m, state != self._state
        self._state = state
        return changed

    def sync(self) -> bool:
        """Recoge lo que otro proceso cambió (p. ej. `release` por CLI) y avisa a la política."""
        with self._lock:
            changed = self._load()
        if changed:
            self._changed()
        return changed

    def keys(self) -> frozenset[str]:
        self.sync()
        with self._lock:
            return frozenset(self._state)

    def entries(self) -> dict[str, dict]:
        self.sync()
        with self._lock:
            return {k: dict(v) for k, v in self._state.items()}

    def trip(self, key: str, reason: str, t: int) -> bool:
        """Pone el bot en cuarentena; `False` si ya lo estaba."""
        with self._lock:
            self._load()
            if key in self._state:
                return False
            self._state[key] = {"reason": reason, "since": t}
            self._save("trip", key, reason, t)
        self._changed()
        return True

    def release(self, key: str, t: int, by: str = "manual") -> bool:
        with self._lock:
            self._load()
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
        self._seen = _stamp(self._dir / "quarantine.json")
        with (self._dir / "quarantine.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"t": t, "action": action, "bot": key, "why": why}) + "\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="eim.bots.quarantine", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data-dir", default=os.environ.get("EIM_DATA_DIR", "data"))
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="bots en cuarentena, con motivo y desde cuándo")
    r = sub.add_parser("release", help="reactivar un bot (solo tras entender la causa)")
    r.add_argument("key", help="<bot_id>@<estrategia>, tal como sale en `list`")
    r.add_argument("--by", default="manual", help="quién reactiva (queda en la bitácora)")
    a = p.parse_args(argv)
    q = Quarantine(Path(a.data_dir) / "bots")
    if a.cmd == "list":
        got = q.entries()
        for k, v in sorted(got.items()):
            since = datetime.fromtimestamp(v["since"] / 1000, UTC).strftime("%Y-%m-%d %H:%M")
            print(f"{k}\tdesde {since} UTC\t{v['reason']}")
        print(f"{len(got)} en cuarentena")
        return 0
    ok = q.release(a.key, int(time.time() * 1000), a.by)
    print(("reactivado: " if ok else "no estaba en cuarentena: ") + a.key)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
