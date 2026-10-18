"""Estado y bitácora de la ejecución de arbitraje (T45) en `root/arb_exec/`.

- `state.json`: libro del ejecutor (posiciones, órdenes, saldo spot de referencia, capital al
  inicio del día). Escritura atómica en cada cambio: sobrevive a un reinicio a mitad de una
  operación (la reconciliación retoma las órdenes anotadas).
- `journal_AAAA-MM-DD.jsonl`: bitácora completa (ciclos, decisiones de riesgo, órdenes, patas
  incompletas, rebalanceos, cierres, reconciliaciones), una línea JSON por evento (UTC).
"""

from __future__ import annotations

import json
import os
import threading
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DIR = "arb_exec"


class ArbExecStore:
    def __init__(self, root: Path | str, keep: int = 300) -> None:
        self.dir = Path(root) / DIR
        self._tail: deque[dict[str, Any]] = deque(maxlen=keep)
        self._lock = threading.Lock()

    @property
    def state_path(self) -> Path:
        return self.dir / "state.json"

    def save_state(self, d: dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        with self._lock:
            tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.state_path)

    def load_state(self) -> dict[str, Any] | None:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _active(self) -> list[dict[str, Any]]:
        d = self.load_state() or {}
        active = ("PENDIENTE", "ABIERTA", "CERRANDO", "DESCUBIERTA")
        return [p for p in d.get("positions", []) if p.get("status") in active]

    def futures_symbols(self) -> tuple[str, ...]:
        return tuple(p["legs"]["usdm"]["symbol"] for p in self._active())

    def futures_expected(self, symbol: str) -> float:
        """Futuros de arbitrajes activos según el último estado guardado (lo usa la
        reconciliación direccional T30 aunque el ejecutor de arbitraje esté apagado)."""
        return round(sum(float(p["legs"]["usdm"]["held"]) for p in self._active()
                         if p["legs"]["usdm"]["symbol"] == symbol), 12)

    def append(self, kind: str, t: int, data: dict[str, Any]) -> None:
        ev = {"t": t, "kind": kind, **data}
        day = datetime.fromtimestamp(t / 1000, UTC).strftime("%Y-%m-%d")
        self.dir.mkdir(parents=True, exist_ok=True)
        line = json.dumps(ev, ensure_ascii=False, default=str)
        with self._lock:
            with (self.dir / f"journal_{day}.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            self._tail.append(ev)

    def tail(self, n: int = 100) -> list[dict[str, Any]]:
        """Últimos eventos (los recientes primero); tras un reinicio, del archivo más nuevo."""
        with self._lock:
            if not self._tail:
                files = sorted(self.dir.glob("journal_*.jsonl")) if self.dir.is_dir() else []
                for f in files[-2:]:
                    for raw in f.read_text(encoding="utf-8").splitlines()[-self._tail.maxlen:]:
                        try:
                            self._tail.append(json.loads(raw))
                        except ValueError:
                            continue
            return list(reversed(list(self._tail)[-n:]))
