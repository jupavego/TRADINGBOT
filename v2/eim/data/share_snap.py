"""Copias coherentes en caliente para exportar (T61) cuando otro proceso tiene la base abierta.

- `reports.duckdb` y `paper.duckdb`: las abre la API → `POST /v2/share/snapshot` (bajo el cerrojo
  de los escritores, ver `eim.api.share`).
- `leaders.duckdb`: la abre el servicio de líderes → se le pide su instantánea con el mismo
  mecanismo que usa `copy-sim` (`copy_store.request_snapshot`).
Las copias viven en `data/share/_snapshot` y `data/leaders/` (nunca en la carpeta de la nube) y
se borran al terminar.
"""

from __future__ import annotations

import shutil
import time
import urllib.error
from collections.abc import Callable
from pathlib import Path

from eim.data.copy_store import request_snapshot
from eim.data.local_api import post_local
from eim.data.share_export import ShareError
from eim.data.share_spec import LEADERS

SNAPSHOT_WAIT_S = 120.0


class HotSnapshots:
    def __init__(self, data_dir: Path, api: str, *, wait_s: float = SNAPSHOT_WAIT_S,
                 post: Callable = post_local, sleep: Callable[[float], None] = time.sleep,
                 now_ms: Callable[[], int] = lambda: int(time.time() * 1000)) -> None:
        self.data_dir, self.api, self.wait_s = data_dir, api, wait_s
        self._post, self._sleep, self._now = post, sleep, now_ms
        self._api_dir: Path | None = None
        self._leaders: Path | None = None

    def __call__(self, db: str) -> Path:
        if db == LEADERS:
            return self._leaders_copy()
        if self._api_dir is None:
            try:
                res = self._post(self.api, "/v2/share/snapshot", "share", timeout=900)
            except (urllib.error.URLError, OSError) as exc:
                raise ShareError(f"{db} está en uso y la API ({self.api}) no respondió: {exc}"
                                 ) from exc
            self._api_dir = Path(res["dir"])
        return self._api_dir / db

    def _leaders_copy(self) -> Path:
        snap = request_snapshot(self.data_dir, self._now())
        end = time.monotonic() + self.wait_s
        while time.monotonic() < end:
            self._sleep(1.0)
            if snap.exists():          # aparece completa: se escribe aparte y se renombra
                self._leaders = snap
                return snap
        raise ShareError(f"leaders.duckdb está en uso y el servicio de líderes no respondió "
                         f"en {self.wait_s:.0f} s: detenlo (§6 de OPERACION.md) y repite")

    def close(self) -> None:
        if self._api_dir is not None:
            shutil.rmtree(self._api_dir, ignore_errors=True)
        if self._leaders is not None:
            self._leaders.unlink(missing_ok=True)
