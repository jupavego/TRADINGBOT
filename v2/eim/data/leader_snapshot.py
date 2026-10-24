"""Instantánea a pedido de `data/leaders.duckdb` (T42, T115): el servicio de líderes es el único
proceso que puede abrir la base, así que quien necesite una copia (`copy-sim`, la copia de
seguridad, `share export`) se la pide por archivo y la espera.

- Cada pedido es su propio archivo `leaders/snapshot_request-<t>.json` (dos peticionarios a la
  vez no se pisan); el servicio los atiende de uno en uno, por orden, y deja la copia completa en
  `leaders/snapshot-<t>.duckdb` (la escribe en `snapshot-<t>.tmp.duckdb` y la renombra).
- Quien pide la recoge (la mueve o la abre). La limpieza solo borra restos: el `.tmp` de una
  instantánea interrumpida y las copias terminadas que nadie recogió en `STALE_S`.
- `wait_snapshot` espera mientras haya avance (la nuestra o la que va delante en la cola crecen),
  no un tiempo fijo: con 450 MB la instantánea tarda ≈ 5 min en vivo (2026-10-24).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

LEGACY_REQ = "snapshot_request.json"        # pedido único anterior a T115 (se sigue atendiendo)
STALE_S = 3600.0                            # copia terminada sin recoger → resto
PICKUP_S = 120.0                            # pedido sin atender ni nada en curso → servicio caído
STALL_S = 300.0                             # instantánea en curso que no crece → colgado
WAIT_S = 3600.0                             # tope total, incluida la cola
POLL_S = 1.0


def snapshot_path(root: str | Path, requested_at: int) -> Path:
    return Path(root) / "leaders" / f"snapshot-{requested_at}.duckdb"


def request_path(root: str | Path, requested_at: int) -> Path:
    return Path(root) / "leaders" / f"snapshot_request-{requested_at}.json"


def request_snapshot(root: str | Path, now: int) -> Path:
    """Pide al servicio una copia de `leaders.duckdb`; devuelve dónde la dejará (un archivo
    por pedido: una copia que otro proceso tenga abierta nunca bloquea la siguiente)."""
    t = now
    while request_path(root, t).exists() or snapshot_path(root, t).exists():
        t += 1                                   # mismo milisegundo que otro pedido
    req = request_path(root, t)
    req.parent.mkdir(parents=True, exist_ok=True)
    tmp = req.with_name(req.name + ".tmp")
    tmp.write_text(json.dumps({"requested_at": t}), encoding="utf-8")
    tmp.replace(req)                             # el servicio nunca ve un pedido a medias
    return snapshot_path(root, t)


def _requested_at(p: Path) -> int:
    try:
        return int(json.loads(p.read_text(encoding="utf-8"))["requested_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return 0


def _clean_leftovers(d: Path, now_s: float) -> None:
    for p in d.glob("snapshot-*.duckdb*"):
        try:
            if ".tmp.duckdb" in p.name or now_s - p.stat().st_mtime > STALE_S:
                p.unlink()
        except OSError:          # abierta por otro proceso (p. ej. `copy-sim`): en otro pedido
            pass


def take_snapshot_request(root: str | Path, now_s: float | None = None) -> Path | None:
    """Destino del pedido más antiguo (None sin pedidos); lo llama el servicio cuando NO tiene
    otra instantánea en curso, así que un `.tmp` que quede es de una interrumpida."""
    d = Path(root) / "leaders"
    reqs = sorted(d.glob("snapshot_request*.json"), key=lambda p: (_requested_at(p), p.name))
    if not reqs:
        return None
    _clean_leftovers(d, time.time() if now_s is None else now_s)
    t = _requested_at(reqs[0])
    reqs[0].unlink(missing_ok=True)
    return snapshot_path(root, t)


def _progress(root: str | Path, t: int) -> tuple:
    """(¿nuestro pedido sigue en cola?, tamaño de cada instantánea en curso)."""
    parts = []
    for p in sorted((Path(root) / "leaders").glob("snapshot-*.tmp.duckdb")):
        try:
            parts.append((p.name, p.stat().st_size))
        except OSError:           # se acaba de renombrar: también es avance
            pass
    return request_path(root, t).exists(), tuple(parts)


def _stuck(mark: tuple, idle: float, waited: float, wait_s: float) -> str:
    pending, parts = mark
    if pending and not parts and idle >= PICKUP_S:
        return f"no atendió el pedido de instantánea en {PICKUP_S:.0f} s (¿detenido?)"
    if idle >= STALL_S:
        return f"tiene la instantánea parada desde hace {STALL_S:.0f} s (¿colgado?)"
    return f"no entregó la instantánea en {wait_s:.0f} s" if waited >= wait_s else ""


def wait_snapshot(root: str | Path, snap: Path, wait_s: float = WAIT_S,
                  sleep: Callable[[float], None] = time.sleep) -> Path:
    """Espera la copia pedida con `request_snapshot`. Sin avance (pedido sin atender, copia que no
    crece) o pasado `wait_s` → TimeoutError con el motivo; el pedido sin atender se retira."""
    t = int(snap.stem.removeprefix("snapshot-"))
    waited, idle, seen = 0.0, 0.0, None
    while not snap.exists():
        mark = _progress(root, t)
        idle, seen = (0.0 if mark != seen else idle + POLL_S), mark
        if why := _stuck(mark, idle, waited, wait_s):
            request_path(root, t).unlink(missing_ok=True)
            raise TimeoutError(why)
        sleep(POLL_S)
        waited += POLL_S
    return snap
